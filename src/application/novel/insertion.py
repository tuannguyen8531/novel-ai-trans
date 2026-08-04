"""Insert a source chapter while keeping chapter-indexed data aligned."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from src import paths
from src.application import config as app_config
from src.application.errors import (
    ApplicationValidationError,
    OperationCancelledError,
    PersistenceError,
)
from src.application.locks import novel_lock
from src.application.novel.identity import require_path
from src.application.progress import ProgressEvent
from src.domain.candidates import ADDRESS_RULE_CANDIDATES_KEY
from src.domain.language import SUPPORTED_TARGET_LANGUAGES
from src.services import chapters as chapter_service
from src.services import insertion as insertion_storage

_OPERATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class InsertRequest:
    novel: str
    number: int
    content: str
    operation_id: str


@dataclass(frozen=True)
class InsertResult:
    novel: str
    chapter: int
    previous_last_chapter: int
    current_last_chapter: int
    shifted_sources: int
    shifted_translations: int
    shifted_reports: int
    updated_progress_files: int
    updated_glossaries: int
    backup_id: str
    repack_required: bool


ProgressCallback = Callable[[ProgressEvent], None]


def _emit(
    callback: ProgressCallback | None,
    *,
    novel: str,
    current: int,
    total: int,
    message: str,
    kind: str = "phase",
) -> None:
    if callback is not None:
        callback(ProgressEvent(kind=kind, novel=novel, current=current, total=total, message=message))


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return insertion_storage.load_json(path)
    except (OSError, ValueError) as error:
        raise PersistenceError(f"Could not read {label}: {path}") from error


def _shift_progress(data: dict[str, Any], number: int) -> dict[str, Any]:
    updated = deepcopy(data)
    for key in ("completed", "failed"):
        values = updated.get(key)
        if not isinstance(values, list):
            continue
        shifted = [value + 1 if isinstance(value, int) and value >= number else value for value in values]
        integers = sorted({value for value in shifted if isinstance(value, int)})
        others = [value for value in shifted if not isinstance(value, int)]
        updated[key] = [*integers, *others]
    return updated


def _shift_glossary(data: dict[str, Any], number: int) -> dict[str, Any]:
    updated = deepcopy(data)

    edges = updated.get("edges")
    if isinstance(edges, list):
        for edge in edges:
            if isinstance(edge, list) and len(edge) > 3 and isinstance(edge[3], int) and edge[3] >= number:
                edge[3] += 1

    rules = updated.get("address_rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            for key in ("since", "until"):
                value = rule.get(key)
                if isinstance(value, int) and value >= number:
                    rule[key] = value + 1

    candidates = updated.get(ADDRESS_RULE_CANDIDATES_KEY)
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in ("first_seen", "last_seen"):
                value = candidate.get(key)
                if isinstance(value, int) and value >= number:
                    candidate[key] = value + 1
            evaluations = candidate.get("evaluations")
            if isinstance(evaluations, list):
                for evaluation in evaluations:
                    if not isinstance(evaluation, dict):
                        continue
                    value = evaluation.get("chapter")
                    if isinstance(value, int) and value >= number:
                        evaluation["chapter"] = value + 1
            hinted_chapters = candidate.get("hinted_chapters")
            if isinstance(hinted_chapters, list):
                candidate["hinted_chapters"] = [
                    value + 1 if isinstance(value, int) and value >= number else value for value in hinted_chapters
                ]

    summaries = updated.get("chapter_summaries")
    if isinstance(summaries, dict):
        shifted_summaries: dict[str, Any] = {}
        for key, value in summaries.items():
            shifted_key = str(int(key) + 1) if isinstance(key, str) and key.isdigit() and int(key) >= number else key
            shifted_summaries[shifted_key] = value
        updated["chapter_summaries"] = shifted_summaries

    return updated


def _prepare_state_files(
    request: InsertRequest,
    config: Any,
    *,
    progress_root: Path,
) -> list[insertion_storage.StateFile]:
    state_files: list[insertion_storage.StateFile] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        progress_path = paths.translation_progress_path(
            config,
            request.novel,
            target,
            progress_root=progress_root,
        )
        if progress_path.exists():
            data = _load_json(progress_path, label=f"{target} translation progress")
            state_files.append(
                insertion_storage.StateFile(
                    f"progress-{target}",
                    progress_path,
                    data,
                    _shift_progress(data, request.number),
                )
            )

        glossary_path = paths.novel_glossary_path(config, request.novel, target)
        if glossary_path.exists():
            data = _load_json(glossary_path, label=f"{target} glossary")
            state_files.append(
                insertion_storage.StateFile(
                    f"glossary-{target}",
                    glossary_path,
                    data,
                    _shift_glossary(data, request.number),
                )
            )
    return state_files


def _create_backup(
    request: InsertRequest,
    backup_root: Path,
    groups: list[insertion_storage.FileGroup],
    state_files: list[insertion_storage.StateFile],
    *,
    previous_last: int,
) -> Path:
    try:
        return insertion_storage.create_backup(
            novel=request.novel,
            operation_id=request.operation_id,
            number=request.number,
            previous_last=previous_last,
            backup_root=backup_root,
            groups=groups,
            state_files=state_files,
        )
    except FileExistsError as error:
        raise PersistenceError(f"Insert backup already exists: {request.operation_id}") from error
    except OSError as error:
        raise PersistenceError("Could not create the insert backup.") from error


def insert_chapter(
    request: InsertRequest,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
    config: Any | None = None,
    progress_root: Path | None = None,
    report_root: Path | None = None,
    backup_root: Path | None = None,
    lock_dir: Path | None = None,
) -> InsertResult:
    """Insert one source chapter and shift every later chapter-indexed record."""
    if request.number < 1:
        raise ApplicationValidationError("Chapter number must be at least 1.")
    if not _OPERATION_ID_RE.fullmatch(request.operation_id):
        raise ApplicationValidationError("Invalid insert operation ID.")
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError()

    active_config = config or app_config.get_config()
    progress_root = progress_root or paths.PROGRESS_DIR
    report_root = report_root or paths.REPORT_DIR
    backup_root = backup_root or paths.INSERT_BACKUP_DIR
    translated_root = Path(active_config.translated_dir or paths.DEFAULT_TRANSLATED_ROOT)
    novel_root = require_path(translated_root, request.novel)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    source_chapters = chapter_service.scan(input_dir)
    previous_last = max(source_chapters, default=0)
    if request.number > previous_last + 1:
        raise ApplicationValidationError(
            f"Cannot insert chapter {request.number}; the next available chapter is {previous_last + 1}."
        )

    output_groups = [
        insertion_storage.FileGroup(
            f"output-{target}",
            paths.novel_output_dir_from_root(novel_root, target),
            "txt",
        )
        for target in SUPPORTED_TARGET_LANGUAGES
    ]
    report_groups = [
        insertion_storage.FileGroup(
            f"reports-{target}",
            paths.translation_report_path(
                active_config,
                request.novel,
                request.number,
                target,
                report_root=report_root,
            ).parent,
            "json",
        )
        for target in SUPPORTED_TARGET_LANGUAGES
    ]
    source_group = insertion_storage.FileGroup("input", input_dir, "txt")
    groups = [source_group, *output_groups, *report_groups]

    with novel_lock(request.novel, lock_dir=lock_dir):
        _emit(
            progress_callback,
            novel=request.novel,
            current=0,
            total=5,
            message=f"Preparing to insert chapter {request.number}...",
        )
        state_files = _prepare_state_files(request, active_config, progress_root=progress_root)
        for group in report_groups:
            for _, report_path in insertion_storage.numbered_files(group, start=request.number):
                _load_json(report_path, label="translation report")

        backup_dir = _create_backup(
            request,
            backup_root,
            groups,
            state_files,
            previous_last=previous_last,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelledError()

        shifted_sources = 0
        shifted_translations = 0
        shifted_reports = 0
        try:
            _emit(
                progress_callback,
                novel=request.novel,
                current=1,
                total=5,
                message="Shifting source chapters...",
            )
            shifted_sources = len(insertion_storage.shift_group(source_group, request.number))
            chapter_service.write(input_dir, request.number, request.content)

            _emit(
                progress_callback,
                novel=request.novel,
                current=2,
                total=5,
                message="Shifting translated chapters...",
            )
            for group in output_groups:
                shifted_translations += len(insertion_storage.shift_group(group, request.number))

            _emit(
                progress_callback,
                novel=request.novel,
                current=3,
                total=5,
                message="Shifting translation reports...",
            )
            for group in report_groups:
                shifted_reports += len(insertion_storage.shift_group(group, request.number))

            _emit(
                progress_callback,
                novel=request.novel,
                current=4,
                total=5,
                message="Updating translation progress and glossary history...",
            )
            insertion_storage.write_state_files(state_files)
            insertion_storage.update_backup_status(backup_dir, "completed")
        except Exception:
            insertion_storage.restore(backup_dir)
            raise

        repack_required = any(paths.novel_artifact_dir_from_root(novel_root).glob("*.epub"))
        final_message = f"Inserted chapter {request.number}."
        if repack_required:
            final_message += " Pack the novel again to update its EPUB."
        _emit(
            progress_callback,
            novel=request.novel,
            current=5,
            total=5,
            message=final_message,
        )

    return InsertResult(
        novel=request.novel,
        chapter=request.number,
        previous_last_chapter=previous_last,
        current_last_chapter=previous_last + 1,
        shifted_sources=shifted_sources,
        shifted_translations=shifted_translations,
        shifted_reports=shifted_reports,
        updated_progress_files=sum(1 for item in state_files if item.label.startswith("progress-")),
        updated_glossaries=sum(1 for item in state_files if item.label.startswith("glossary-")),
        backup_id=request.operation_id,
        repack_required=repack_required,
    )


__all__ = ["InsertRequest", "InsertResult", "insert_chapter"]
