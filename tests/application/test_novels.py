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


def test_summary_resolves_title_for_requested_target_language(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Original", "localized": {"vi": {"title": "Tên truyện"}}}),
        encoding="utf-8",
    )

    assert novels.summarize(root, "demo").title == "Original"
    assert novels.summarize(root, "demo", target_language="vi").title == "Tên truyện"


def test_update_metadata_merges_and_clears_localized_titles(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Demo", "localized": {"vi": {"title": "Tên"}, "en": {"title": "Title"}}}),
        encoding="utf-8",
    )

    updated = novels.update_metadata(root, "demo", {"localized": {"vi": {"title": None}}})

    assert updated["localized"] == {"en": {"title": "Title"}}
    assert json.loads((novel_root / "metadata.json").read_text(encoding="utf-8")) == updated


def test_update_metadata_deep_merges_localized_fields_as_manual(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Demo", "summary": "Source", "localized": {"vi": {"title": "Tên"}}}),
        encoding="utf-8",
    )

    updated = novels.update_metadata(
        root,
        "demo",
        {"localized": {"vi": {"summary": "Tóm tắt"}, "en": {"title": "Title"}}},
        localized_origin="manual",
    )

    assert updated["localized"] == {
        "vi": {"title": "Tên", "summary": "Tóm tắt"},
        "en": {"title": "Title"},
    }
    assert updated["localization_meta"]["vi"]["summary"]["origin"] == "manual"
    assert updated["localization_meta"]["en"]["title"]["origin"] == "manual"


@pytest.mark.parametrize(
    ("target", "relative_path"),
    [
        ("vi", Path("output/chapter_007.txt")),
        ("en", Path("output/en/chapter_007.txt")),
    ],
)
def test_write_chapter_can_update_translation(tmp_path: Path, target: str, relative_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)

    result = novels.write_chapter(
        root,
        "demo",
        7,
        "Translated chapter",
        view="translation",
        target=target,
    )

    assert result.view == "translation"
    assert result.target == target
    assert (novel_root / relative_path).read_text(encoding="utf-8") == "Translated chapter"
    assert novels.read_chapter(root, "demo", 7, view="translation", target=target).content == "Translated chapter"


def test_write_chapter_preserves_legacy_unpadded_translation_filename(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    legacy_path = root / "demo" / "output" / "chapter_7.txt"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("Old translation", encoding="utf-8")

    novels.write_chapter(root, "demo", 7, "Updated translation", view="translation", target="vi")

    assert legacy_path.read_text(encoding="utf-8") == "Updated translation"
    assert not (legacy_path.parent / "chapter_007.txt").exists()


def test_source_chapter_operations_preserve_legacy_unpadded_filename(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    legacy_path = root / "demo" / "input" / "chapter_7.txt"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("Old source", encoding="utf-8")

    assert novels.read_chapter(root, "demo", 7, view="source").content == "Old source"
    novels.write_chapter(root, "demo", 7, "Updated source")

    assert legacy_path.read_text(encoding="utf-8") == "Updated source"
    assert not (legacy_path.parent / "chapter_007.txt").exists()

    novels.delete_chapter(root, "demo", 7)
    assert not legacy_path.exists()


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
