from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.errors import ResourceNotFoundError
from src.application.novel import artifacts, catalog, chapters, metadata, rules


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

    summary = catalog.summarize(root, "demo", progress_root=progress_root)

    vietnamese = next(progress for progress in summary.targets if progress.target == "vi")
    assert vietnamese.total == 2
    assert vietnamese.completed == 2
    assert vietnamese.failed == 1
    assert vietnamese.warnings == 0
    assert catalog.progress(root, "demo", "vi", progress_root=progress_root) == {
        "completed": [2],
        "failed": [3],
        "warnings": [],
    }


def test_summary_and_progress_include_source_warning_chapters(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 1)
    _write_chapter(novel_root / "output", 1)
    report_root = tmp_path / "reports"
    report_dir = report_root / "demo"
    report_dir.mkdir(parents=True)
    (report_dir / "chapter_001.json").write_text(
        json.dumps(
            {
                "chapter": 1,
                "chunks": [
                    {
                        "post_check_issues": ["contains_source_language_chars"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = catalog.summarize(root, "demo", report_root=report_root)
    vietnamese = next(progress for progress in summary.targets if progress.target == "vi")

    assert vietnamese.warnings == 1
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == [1]


def test_summary_resolves_title_for_requested_target_language(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Original", "localized": {"vi": {"title": "Tên truyện"}}}),
        encoding="utf-8",
    )

    assert catalog.summarize(root, "demo").title == "Original"
    assert catalog.summarize(root, "demo", target_language="vi").title == "Tên truyện"


def test_update_metadata_merges_and_clears_localized_titles(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Demo", "localized": {"vi": {"title": "Tên"}, "en": {"title": "Title"}}}),
        encoding="utf-8",
    )

    updated = metadata.update_metadata(root, "demo", {"localized": {"vi": {"title": None}}})

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

    updated = metadata.update_metadata(
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

    result = chapters.write_chapter(
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
    assert chapters.read_chapter(root, "demo", 7, view="translation", target=target).content == "Translated chapter"


def test_write_translation_refreshes_manual_source_warning(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "囡囡来了")
    report_root = tmp_path / "reports"
    report_path = report_root / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "chapter": 7,
                "chunks": [{"post_check_issues": ["contains_source_language_chars"]}],
            }
        ),
        encoding="utf-8",
    )

    chapters.write_chapter(
        root,
        "demo",
        7,
        "Cô bé 囡 đến rồi.",
        view="translation",
        target="vi",
        report_root=report_root,
    )
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == [7]

    chapters.write_chapter(
        root,
        "demo",
        7,
        "Cô bé đã đến.",
        view="translation",
        target="vi",
        report_root=report_root,
    )
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == []
    assert json.loads(report_path.read_text(encoding="utf-8"))["manual_post_check_issues"] == []


def test_source_warning_review_is_tied_to_exact_translation(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "囡囡来了")
    report_root = tmp_path / "reports"
    translation = "Cô bé 囡 đến rồi."
    chapters.write_chapter(
        root,
        "demo",
        7,
        translation,
        view="translation",
        target="vi",
        report_root=report_root,
    )

    status = chapters.source_warning_status(root, "demo", 7, "vi", report_root=report_root)
    assert status.present is True
    assert status.ignored is False
    assert status.fragments == ["囡"]

    status = chapters.review_source_warning(
        root,
        "demo",
        7,
        "vi",
        ignored=True,
        report_root=report_root,
    )
    assert status.ignored is True
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == []

    chapters.write_chapter(
        root,
        "demo",
        7,
        translation,
        view="translation",
        target="vi",
        report_root=report_root,
    )
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == []

    chapters.write_chapter(
        root,
        "demo",
        7,
        "Cô bé 囡 đang đến.",
        view="translation",
        target="vi",
        report_root=report_root,
    )
    status = chapters.source_warning_status(root, "demo", 7, "vi", report_root=report_root)
    assert status.ignored is False
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == [7]


def test_write_chapter_preserves_legacy_unpadded_translation_filename(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    legacy_path = root / "demo" / "output" / "chapter_7.txt"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("Old translation", encoding="utf-8")

    chapters.write_chapter(root, "demo", 7, "Updated translation", view="translation", target="vi")

    assert legacy_path.read_text(encoding="utf-8") == "Updated translation"
    assert not (legacy_path.parent / "chapter_007.txt").exists()


def test_source_chapter_operations_preserve_legacy_unpadded_filename(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    legacy_path = root / "demo" / "input" / "chapter_7.txt"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("Old source", encoding="utf-8")

    assert chapters.read_chapter(root, "demo", 7, view="source").content == "Old source"
    chapters.write_chapter(root, "demo", 7, "Updated source")

    assert legacy_path.read_text(encoding="utf-8") == "Updated source"
    assert not (legacy_path.parent / "chapter_007.txt").exists()

    chapters.delete_chapter(root, "demo", 7)
    assert not legacy_path.exists()


def test_rules_round_trip_and_default_to_empty(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    (root / "demo").mkdir(parents=True)

    assert rules.rules(root, "demo") == ""

    rules.save_rules(root, "demo", "Keep names consistent.")

    assert rules.rules(root, "demo") == "Keep names consistent."


def test_artifact_paths_prefer_artifacts_directory_and_ignore_unsupported_formats(tmp_path: Path) -> None:
    novel_root = tmp_path / "demo"
    artifacts_dir = novel_root / "artifacts"
    artifacts_dir.mkdir(parents=True)
    current = artifacts_dir / "demo.vi.epub"
    current.write_bytes(b"current")
    (novel_root / "demo.vi.epub").write_bytes(b"duplicate-legacy")
    unsupported = novel_root / "demo.en.mobi"
    unsupported.write_bytes(b"unsupported")

    assert [path.name for path in artifacts.list_artifact_paths(novel_root)] == ["demo.vi.epub"]
    assert artifacts.resolve_artifact_path(novel_root, "demo.vi.epub") == current.resolve()
    with pytest.raises(ResourceNotFoundError, match="Artifact not found"):
        artifacts.resolve_artifact_path(novel_root, "demo.en.mobi")


def test_legacy_artifact_metadata_is_marked_as_inferred(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    artifact_dir = novel_root / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "demo.vi.epub").write_bytes(b"legacy")
    _write_chapter(novel_root / "output", 1)

    listed = artifacts.list_artifacts(root, "demo")

    assert len(listed) == 1
    assert listed[0].size == 6
    assert listed[0].chapter_count == 1
    assert listed[0].metadata_status == "inferred"


@pytest.mark.parametrize("filename", ["../demo.epub", "subdir/demo.epub", ".hidden.epub"])
def test_resolve_artifact_rejects_unsafe_filename(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ResourceNotFoundError, match="Invalid artifact name"):
        artifacts.resolve_artifact_path(tmp_path / "demo", filename)
