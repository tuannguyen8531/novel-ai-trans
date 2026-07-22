from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.errors import ApplicationValidationError
from src.application.novel.insertion import InsertRequest, insert_chapter
from src.config import Config
from src.utils import files


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _run_insert(
    tmp_path: Path,
    *,
    number: int,
    content: str = "inserted",
    operation_id: str = "insert-test",
):
    translated = tmp_path / "translated"
    return insert_chapter(
        InsertRequest(novel="demo", number=number, content=content, operation_id=operation_id),
        config=Config(translated_dir=str(translated)),
        progress_root=tmp_path / "runtime" / "progress",
        report_root=tmp_path / "runtime" / "reports",
        backup_root=tmp_path / "runtime" / "insert-backups",
        lock_dir=tmp_path / "runtime" / "locks",
    )


def test_insert_shifts_chapter_indexed_files_and_state(tmp_path: Path) -> None:
    novel = tmp_path / "translated" / "demo"
    for number in (1, 2, 3):
        _write(novel / "input" / f"chapter_{number:03d}.txt", f"source-{number}")
    for number in (2, 3):
        _write(novel / "output" / f"chapter_{number:03d}.txt", f"vi-{number}")
    _write(novel / "output" / "en" / "chapter_003.txt", "en-3")
    _write(novel / "artifacts" / "demo.vi.epub", "book")

    runtime = tmp_path / "runtime"
    _write_json(runtime / "reports" / "demo" / "chapter_002.json", {"chapter": 2, "target_language": "vi"})
    _write_json(runtime / "reports" / "demo" / "chapter_003.json", {"chapter": 3, "target_language": "vi"})
    _write_json(runtime / "reports" / "en" / "demo" / "chapter_003.json", {"chapter": 3, "target_language": "en"})
    _write_json(runtime / "progress" / "demo.json", {"completed": [1, 2, 3], "failed": [4]})
    _write_json(runtime / "progress" / "en" / "demo.json", {"completed": [3], "failed": []})
    _write_json(
        novel / "glossary.json",
        {
            "terms": {},
            "entities": {},
            "edges": [["A", "B", "friend", 2]],
            "address_rules": [{"speaker": "A", "listener": "B", "since": 2, "until": 3}],
            "_address_rule_candidates": [
                {
                    "speaker": "A",
                    "listener": "B",
                    "first_seen": 2,
                    "last_seen": 3,
                    "observations": 1,
                    "hinted_chapters": [2, 3],
                }
            ],
            "chapter_summaries": {"1": "one", "2": "two", "3": "three"},
        },
    )

    result = _run_insert(tmp_path, number=2, content="new-source")

    assert (novel / "input" / "chapter_001.txt").read_text(encoding="utf-8") == "source-1"
    assert (novel / "input" / "chapter_002.txt").read_text(encoding="utf-8") == "new-source"
    assert (novel / "input" / "chapter_003.txt").read_text(encoding="utf-8") == "source-2"
    assert (novel / "input" / "chapter_004.txt").read_text(encoding="utf-8") == "source-3"
    assert not (novel / "output" / "chapter_002.txt").exists()
    assert (novel / "output" / "chapter_003.txt").read_text(encoding="utf-8") == "vi-2"
    assert (novel / "output" / "chapter_004.txt").read_text(encoding="utf-8") == "vi-3"
    assert (novel / "output" / "en" / "chapter_004.txt").read_text(encoding="utf-8") == "en-3"

    vi_report = json.loads((runtime / "reports" / "demo" / "chapter_003.json").read_text(encoding="utf-8"))
    en_report = json.loads((runtime / "reports" / "en" / "demo" / "chapter_004.json").read_text(encoding="utf-8"))
    assert vi_report["chapter"] == 3
    assert en_report["chapter"] == 4
    assert json.loads((runtime / "progress" / "demo.json").read_text(encoding="utf-8")) == {
        "completed": [1, 3, 4],
        "failed": [5],
    }

    glossary = json.loads((novel / "glossary.json").read_text(encoding="utf-8"))
    assert glossary["edges"][0][3] == 3
    assert glossary["address_rules"][0]["since"] == 3
    assert glossary["address_rules"][0]["until"] == 4
    assert glossary["_address_rule_candidates"][0]["first_seen"] == 3
    assert glossary["_address_rule_candidates"][0]["last_seen"] == 4
    assert glossary["_address_rule_candidates"][0]["hinted_chapters"] == [3, 4]
    assert glossary["chapter_summaries"] == {"1": "one", "3": "two", "4": "three"}
    assert result.shifted_sources == 2
    assert result.shifted_translations == 3
    assert result.shifted_reports == 3
    assert result.current_last_chapter == 4
    assert result.repack_required is True
    backup_manifest = runtime / "insert-backups" / "demo" / "insert-test" / "manifest.json"
    assert json.loads(backup_manifest.read_text(encoding="utf-8"))["status"] == "completed"


def test_insert_appends_without_shifting_existing_files(tmp_path: Path) -> None:
    novel = tmp_path / "translated" / "demo"
    _write(novel / "input" / "chapter_001.txt", "one")

    result = _run_insert(tmp_path, number=2, content="two")

    assert (novel / "input" / "chapter_001.txt").read_text(encoding="utf-8") == "one"
    assert (novel / "input" / "chapter_002.txt").read_text(encoding="utf-8") == "two"
    assert result.shifted_sources == 0
    assert result.current_last_chapter == 2


def test_insert_preserves_legacy_and_canonical_filename_styles(tmp_path: Path) -> None:
    novel = tmp_path / "translated" / "demo"
    _write(novel / "input" / "chapter_1.txt", "legacy one")
    _write(novel / "input" / "chapter_002.txt", "canonical two")

    _run_insert(tmp_path, number=1, content="new one")

    assert (novel / "input" / "chapter_001.txt").read_text(encoding="utf-8") == "new one"
    assert (novel / "input" / "chapter_2.txt").read_text(encoding="utf-8") == "legacy one"
    assert (novel / "input" / "chapter_003.txt").read_text(encoding="utf-8") == "canonical two"


def test_insert_rejects_a_gap_after_the_last_chapter(tmp_path: Path) -> None:
    novel = tmp_path / "translated" / "demo"
    _write(novel / "input" / "chapter_001.txt", "one")

    with pytest.raises(ApplicationValidationError, match="next available chapter is 2"):
        _run_insert(tmp_path, number=3)


def test_insert_rolls_back_when_state_commit_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    novel = tmp_path / "translated" / "demo"
    _write(novel / "input" / "chapter_001.txt", "one")
    _write(novel / "input" / "chapter_002.txt", "two")
    progress_path = tmp_path / "runtime" / "progress" / "demo.json"
    _write_json(progress_path, {"completed": [1, 2], "failed": []})
    original_write_json_atomic = files.write_json_atomic

    def fail_progress_write(path: Path, data: object) -> None:
        if path == progress_path:
            raise OSError("disk full")
        original_write_json_atomic(path, data)

    monkeypatch.setattr(files, "write_json_atomic", fail_progress_write)

    with pytest.raises(OSError, match="disk full"):
        _run_insert(tmp_path, number=1, content="new")

    assert (novel / "input" / "chapter_001.txt").read_text(encoding="utf-8") == "one"
    assert (novel / "input" / "chapter_002.txt").read_text(encoding="utf-8") == "two"
    assert not (novel / "input" / "chapter_003.txt").exists()
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {"completed": [1, 2], "failed": []}
    manifest = tmp_path / "runtime" / "insert-backups" / "demo" / "insert-test" / "manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "rolled_back"
