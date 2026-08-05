"""Tests for recoverable translated-chapter publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.translation.checkpoints import CheckpointStore
from src.services.translation.publisher import (
    ChapterPublication,
    ChapterPublisher,
    PublicationConflictError,
    PublicationError,
)
from src.services.translation.reports import ReportStore
from src.services.translation.storage import TranslationStorage
from src.utils.files import write_json_atomic

_REPORT = {
    "manual_post_check_issues": ["contains_source_language_chars"],
    "ignored_post_checks": [],
    "issues": [],
    "candidate_translation": None,
    "partial": False,
    "failed_chunk_index": None,
    "total_chunks": None,
}


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    return (
        tmp_path / "translated" / "novel" / "output",
        tmp_path / "runtime" / "reports" / "vi" / "novel" / "chapter_001.json",
        tmp_path / "runtime" / "progress" / "novel.json",
        tmp_path / "runtime" / "transactions" / "vi" / "novel",
    )


def _publication(tmp_path: Path) -> ChapterPublication:
    output_dir, report_path, progress_path, transaction_dir = _paths(tmp_path)
    return ChapterPublication(
        chapter=1,
        output_dir=output_dir,
        report_path=report_path,
        progress_path=progress_path,
        transaction_dir=transaction_dir,
        content="new translated content",
        report=dict(_REPORT),
        checkpoint={"completed": [], "failed": [1, 2]},
    )


class FailingCheckpointStore(CheckpointStore):
    def save(self, path: Path, checkpoint: dict[str, list[int]]) -> None:
        raise OSError("fault injection")


def _publisher(*, replace=None, checkpoints: CheckpointStore | None = None) -> ChapterPublisher:
    return ChapterPublisher(
        TranslationStorage(),
        ReportStore(),
        checkpoints or CheckpointStore(),
        id_factory=lambda: "transaction-id",
        replace=replace,
    )


def _recover(publisher: ChapterPublisher, tmp_path: Path) -> int:
    output_dir, report_path, progress_path, transaction_dir = _paths(tmp_path)
    return publisher.recover(
        output_dir=output_dir,
        report_dir=report_path.parent,
        progress_path=progress_path,
        transaction_dir=transaction_dir,
    )


def _fail_replacing(destination_to_fail: Path):
    def replace(source: Path, destination: Path) -> None:
        if destination.resolve() == destination_to_fail.resolve():
            raise OSError("fault injection")
        os.replace(source, destination)

    return replace


def test_publish_commits_output_report_and_progress(tmp_path: Path) -> None:
    publication = _publication(tmp_path)

    with patch("src.services.translation.publisher.write_json_atomic", wraps=write_json_atomic) as write_journal:
        checkpoint = _publisher().publish(publication)

    output_dir, report_path, progress_path, transaction_dir = _paths(tmp_path)
    assert (output_dir / "chapter_001.txt").read_text(encoding="utf-8") == publication.content
    assert json.loads(report_path.read_text(encoding="utf-8")) == _REPORT
    assert CheckpointStore().load(progress_path) == {"completed": [1], "failed": [2]}
    assert checkpoint == {"completed": [1], "failed": [2]}
    assert list(transaction_dir.glob("*.json")) == []
    assert list(tmp_path.rglob("*.stage")) == []
    assert write_journal.call_count == 1


def test_recovery_discards_prepared_transaction_before_output_commit(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    output_path = publication.output_dir / "chapter_001.txt"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"previous output bytes")
    ReportStore().save(publication.report_path, {"previous": True})
    CheckpointStore().save(publication.progress_path, {"completed": [1], "failed": [1, 2]})

    with pytest.raises(PublicationError, match="recovery state was preserved"):
        _publisher(replace=_fail_replacing(output_path)).publish(publication)

    assert output_path.read_bytes() == b"previous output bytes"
    journal = json.loads(next(publication.transaction_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert set(journal) == {
        "version",
        "chapter",
        "previous_output_hash",
        "new_output_hash",
        "previous_report_hash",
        "new_report_hash",
    }
    assert _recover(_publisher(), tmp_path) == 1
    assert json.loads(publication.report_path.read_text(encoding="utf-8")) == {"previous": True}
    assert CheckpointStore().load(publication.progress_path) == {"completed": [1], "failed": [1, 2]}
    assert list(publication.transaction_dir.glob("*.json")) == []


def test_recovery_finishes_report_and_progress_after_output_commit(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    CheckpointStore().save(publication.progress_path, publication.checkpoint)

    with pytest.raises(PublicationError):
        _publisher(replace=_fail_replacing(publication.report_path)).publish(publication)

    output_path = publication.output_dir / "chapter_001.txt"
    assert output_path.read_text(encoding="utf-8") == publication.content
    assert not publication.report_path.exists()

    assert _recover(_publisher(), tmp_path) == 1
    assert json.loads(publication.report_path.read_text(encoding="utf-8")) == _REPORT
    assert CheckpointStore().load(publication.progress_path) == {"completed": [1], "failed": [2]}


def test_recovery_reconciles_progress_after_report_commit(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    CheckpointStore().save(publication.progress_path, publication.checkpoint)

    with pytest.raises(PublicationError):
        _publisher(checkpoints=FailingCheckpointStore()).publish(publication)

    assert json.loads(publication.report_path.read_text(encoding="utf-8")) == _REPORT
    assert CheckpointStore().load(publication.progress_path) == publication.checkpoint

    assert _recover(_publisher(), tmp_path) == 1
    assert CheckpointStore().load(publication.progress_path) == {"completed": [1], "failed": [2]}


def test_recovery_preserves_journal_when_output_was_edited(tmp_path: Path) -> None:
    publication = _publication(tmp_path)

    with pytest.raises(PublicationError):
        _publisher(replace=_fail_replacing(publication.report_path)).publish(publication)

    output_path = publication.output_dir / "chapter_001.txt"
    output_path.write_text("manual edit after crash", encoding="utf-8")

    with pytest.raises(PublicationConflictError, match="changed outside transaction"):
        _recover(_publisher(), tmp_path)

    assert output_path.read_text(encoding="utf-8") == "manual edit after crash"
    assert len(list(publication.transaction_dir.glob("*.json"))) == 1


def test_recovery_removes_orphan_stages_without_a_journal(tmp_path: Path) -> None:
    output_dir, report_path, _, _ = _paths(tmp_path)
    orphan_paths = [
        output_dir / ".chapter_001.txt.orphan.stage",
        report_path.parent / ".chapter_001.json.orphan.stage",
    ]
    for path in orphan_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("staged", encoding="utf-8")

    assert _recover(_publisher(), tmp_path) == 0
    assert all(not path.exists() for path in orphan_paths)
