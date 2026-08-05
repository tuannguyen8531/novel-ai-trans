"""Recoverable publication of translated chapter state."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.services.translation.checkpoints import CheckpointStore
from src.services.translation.reports import ReportStore
from src.services.translation.storage import TranslationStorage
from src.utils.files import write_json_atomic

_JOURNAL_VERSION = 1


class PublicationError(RuntimeError):
    """A chapter publication could not safely finish."""


class PublicationConflictError(PublicationError):
    """Recovery found data that differs from both transaction versions."""


@dataclass(frozen=True)
class ChapterPublication:
    chapter: int
    output_dir: Path
    report_path: Path
    progress_path: Path
    transaction_dir: Path
    content: str
    report: dict[str, Any]
    checkpoint: dict[str, list[int]]


class ChapterPublisher:
    """Publish output, report, and progress with recoverable commit state."""

    def __init__(
        self,
        storage: TranslationStorage,
        reports: ReportStore,
        checkpoints: CheckpointStore,
        *,
        id_factory: Callable[[], str] | None = None,
        replace: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.storage = storage
        self.reports = reports
        self.checkpoints = checkpoints
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._replace = replace or os.replace

    def publish(self, publication: ChapterPublication) -> dict[str, list[int]]:
        """Publish one prepared chapter and return its normalized checkpoint."""
        transaction_id = self._id_factory()
        output_path = self.storage.path(publication.output_dir, publication.chapter)
        output_stage = _stage_path(output_path, transaction_id)
        report_stage = _stage_path(publication.report_path, transaction_id)
        journal_path = publication.transaction_dir / f"{transaction_id}.json"
        staged_paths = (output_stage, report_stage)
        if journal_path.exists() or any(path.exists() for path in staged_paths):
            raise PublicationError(f"Transaction ID collision: {transaction_id}")
        journal_written = False

        completed = self.storage.translated_numbers(publication.output_dir)
        completed.add(publication.chapter)
        planned_checkpoint = self.checkpoints.normalize(
            {
                "completed": list(completed),
                "failed": [value for value in publication.checkpoint.get("failed", []) if value != publication.chapter],
            }
        )
        report_text = self.reports.serialize(publication.report)

        journal: dict[str, Any] = {
            "version": _JOURNAL_VERSION,
            "chapter": publication.chapter,
            "previous_output_hash": _file_hash(output_path),
            "new_output_hash": _content_hash(publication.content),
            "previous_report_hash": _file_hash(publication.report_path),
            "new_report_hash": _content_hash(report_text),
        }

        try:
            _write_stage(output_stage, publication.content)
            _write_stage(report_stage, report_text)
            write_json_atomic(journal_path, journal)
            journal_written = True

            self._replace(output_stage, output_path)
            self._replace(report_stage, publication.report_path)
            self.checkpoints.save(publication.progress_path, planned_checkpoint)
            journal_path.unlink()
            _discard_paths(staged_paths)
            return planned_checkpoint
        except Exception as error:
            if not journal_written:
                _discard_paths(staged_paths)
                journal_path.unlink(missing_ok=True)
            raise PublicationError(f"Could not publish chapter {publication.chapter}; recovery state was preserved.") from error

    def recover(
        self,
        *,
        output_dir: Path,
        report_dir: Path,
        progress_path: Path,
        transaction_dir: Path,
    ) -> int:
        """Resolve every interrupted publication for one locked novel target."""
        recovered = 0
        journal_paths = sorted(transaction_dir.glob("*.json")) if transaction_dir.exists() else []
        for journal_path in journal_paths:
            try:
                self._recover_one(
                    journal_path,
                    output_dir=output_dir,
                    report_dir=report_dir,
                    progress_path=progress_path,
                )
            except PublicationError:
                raise
            except Exception as error:
                raise PublicationError(f"Could not recover transaction journal: {journal_path}") from error
            recovered += 1
        _cleanup_orphan_stages(output_dir, report_dir)
        return recovered

    def _recover_one(
        self,
        journal_path: Path,
        *,
        output_dir: Path,
        report_dir: Path,
        progress_path: Path,
    ) -> None:
        journal = _load_journal(journal_path)
        transaction_id = journal_path.stem
        chapter = journal.get("chapter")
        if journal.get("version") != _JOURNAL_VERSION or not isinstance(chapter, int) or chapter < 1:
            raise PublicationConflictError(f"Invalid translation transaction journal: {journal_path}")

        output_path = self.storage.path(output_dir, chapter)
        output_stage = _stage_path(output_path, transaction_id)
        report_path = report_dir / f"chapter_{chapter:03d}.json"
        report_stage = _stage_path(report_path, transaction_id)

        previous_output_hash = _optional_hash(journal, "previous_output_hash")
        new_output_hash = _required_hash(journal, "new_output_hash")
        current_output_hash = _file_hash(output_path)
        if current_output_hash == new_output_hash:
            self._finish_committed(
                chapter=chapter,
                output_dir=output_dir,
                report_path=report_path,
                report_stage=report_stage,
                previous_report_hash=_optional_hash(journal, "previous_report_hash"),
                new_report_hash=_required_hash(journal, "new_report_hash"),
                progress_path=progress_path,
            )
        elif current_output_hash == previous_output_hash:
            current_report_hash = _file_hash(report_path)
            previous_report_hash = _optional_hash(journal, "previous_report_hash")
            if current_report_hash != previous_report_hash:
                raise PublicationConflictError(f"Report changed before transaction {transaction_id} committed; recovery stopped.")
        else:
            raise PublicationConflictError(f"Output changed outside transaction {transaction_id}; recovery stopped.")

        _discard_paths((output_stage, report_stage))
        journal_path.unlink()

    def _finish_committed(
        self,
        *,
        chapter: int,
        output_dir: Path,
        report_path: Path,
        report_stage: Path,
        previous_report_hash: str | None,
        new_report_hash: str,
        progress_path: Path,
    ) -> None:
        current_report_hash = _file_hash(report_path)
        if current_report_hash != new_report_hash:
            if current_report_hash != previous_report_hash:
                raise PublicationConflictError(f"Report changed outside the transaction for chapter {chapter}.")
            if _file_hash(report_stage) != new_report_hash:
                raise PublicationConflictError(f"Staged report is missing or invalid for chapter {chapter}.")
            self._replace(report_stage, report_path)

        checkpoint = self.checkpoints.load(progress_path)
        checkpoint["completed"] = sorted(self.storage.translated_numbers(output_dir))
        checkpoint["failed"] = [value for value in checkpoint.get("failed", []) if value != chapter]
        self.checkpoints.save(progress_path, checkpoint)


def _stage_path(destination: Path, transaction_id: str) -> Path:
    return destination.with_name(f".{destination.name}.{transaction_id}.stage")


def _write_stage(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_journal(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationConflictError(f"Could not read transaction journal: {path}") from error
    if not isinstance(data, dict):
        raise PublicationConflictError(f"Invalid transaction journal: {path}")
    return data


def _required_hash(journal: dict[str, Any], key: str) -> str:
    value = journal.get(key)
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PublicationConflictError(f"Transaction hash {key!r} is invalid.")
    return value


def _optional_hash(journal: dict[str, Any], key: str) -> str | None:
    value = journal.get(key)
    if value is None:
        return None
    return _required_hash(journal, key)


def _discard_paths(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _cleanup_orphan_stages(output_dir: Path, report_dir: Path) -> None:
    candidates = [
        *(output_dir.glob(".chapter_*.txt.*.stage") if output_dir.exists() else []),
        *(report_dir.glob(".chapter_*.json.*.stage") if report_dir.exists() else []),
    ]
    _discard_paths(tuple(candidates))


__all__ = [
    "ChapterPublication",
    "ChapterPublisher",
    "PublicationConflictError",
    "PublicationError",
]
