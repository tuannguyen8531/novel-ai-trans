from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application import novels
from src.application.errors import ResourceNotFoundError


def _write_chapter(directory: Path, number: int, content: str = "content") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"chapter_{number:03d}.txt").write_text(content, encoding="utf-8")


def test_summary_combines_progress_with_stored_outputs(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 1)
    _write_chapter(novel_root / "input", 2)
    _write_chapter(novel_root / "output", 1)
    progress_root = tmp_path / "progress"
    progress_root.mkdir()
    (progress_root / "demo.json").write_text(
        json.dumps({"completed": [2], "failed": [3]}),
        encoding="utf-8",
    )

    summary = novels.summarize(root, "demo", progress_root=progress_root)

    vietnamese = next(progress for progress in summary.targets if progress.target == "vi")
    assert vietnamese.total == 2
    assert vietnamese.completed == 2
    assert vietnamese.failed == 1
    assert novels.progress(root, "demo", "vi", progress_root=progress_root) == {
        "completed": [2],
        "failed": [3],
    }


def test_update_metadata_merges_and_clears_translated_titles(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Demo", "translated": {"vi": "Tên", "en": "Title"}}),
        encoding="utf-8",
    )

    updated = novels.update_metadata(root, "demo", {"translated": {"vi": None}})

    assert updated["translated"] == {"en": "Title"}
    assert json.loads((novel_root / "metadata.json").read_text(encoding="utf-8")) == updated


def test_rules_round_trip_and_default_to_empty(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    (root / "demo").mkdir(parents=True)

    assert novels.rules(root, "demo") == ""

    novels.save_rules(root, "demo", "Keep names consistent.")

    assert novels.rules(root, "demo") == "Keep names consistent."


def test_artifact_paths_prefer_artifacts_directory_and_support_legacy_root(tmp_path: Path) -> None:
    novel_root = tmp_path / "demo"
    artifacts_dir = novel_root / "artifacts"
    artifacts_dir.mkdir(parents=True)
    current = artifacts_dir / "demo.vi.epub"
    current.write_bytes(b"current")
    (novel_root / "demo.vi.epub").write_bytes(b"duplicate-legacy")
    legacy = novel_root / "demo.en.pdf"
    legacy.write_bytes(b"legacy")

    assert [path.name for path in novels.list_artifact_paths(novel_root)] == ["demo.en.pdf", "demo.vi.epub"]
    assert novels.resolve_artifact_path(novel_root, "demo.vi.epub") == current.resolve()
    assert novels.resolve_artifact_path(novel_root, "demo.en.pdf") == legacy.resolve()


@pytest.mark.parametrize("filename", ["../demo.epub", "subdir/demo.epub", ".hidden.epub"])
def test_resolve_artifact_rejects_unsafe_filename(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ResourceNotFoundError, match="Invalid artifact name"):
        novels.resolve_artifact_path(tmp_path / "demo", filename)
