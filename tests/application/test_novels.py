from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.errors import (
    ApplicationValidationError,
    PersistenceError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.application.novel import artifacts, candidates, catalog, chapters, metadata, rules
from src.application.translation.chapter import normalize_translation
from src.services.translation.publisher import ChapterPublisher, PublicationError
from src.services.translation.reports import content_hash


def _write_chapter(directory: Path, number: int, content: str = "content") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"chapter_{number:03d}.txt").write_text(content, encoding="utf-8")


def test_summary_uses_stored_outputs_as_completion_truth(tmp_path: Path) -> None:
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
    assert vietnamese.completed == 1
    assert vietnamese.failed == 1
    assert vietnamese.warnings == 0
    assert catalog.progress(root, "demo", "vi", progress_root=progress_root) == {
        "completed": [1],
        "failed": [3],
        "warnings": [],
        "source_warnings": [],
    }


def test_summary_and_progress_include_source_warning_chapters(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 1)
    _write_chapter(novel_root / "output", 1)
    report_root = tmp_path / "reports"
    report_dir = report_root / "vi" / "demo"
    report_dir.mkdir(parents=True)
    (report_dir / "chapter_001.json").write_text(
        json.dumps(
            {
                "manual_post_check_issues": ["contains_source_language_chars"],
            }
        ),
        encoding="utf-8",
    )

    summary = catalog.summarize(root, "demo", report_root=report_root)
    vietnamese = next(progress for progress in summary.targets if progress.target == "vi")

    assert vietnamese.warnings == 1
    progress = catalog.progress(root, "demo", "vi", report_root=report_root)
    assert progress["warnings"] == [1]
    assert progress["source_warnings"] == [1]


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


def test_update_metadata_validates_genres_against_locked_current_profile(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"source_language": "korean", "genres": ["fantasy"]}),
        encoding="utf-8",
    )

    with pytest.raises(ApplicationValidationError, match="Unsupported genre"):
        metadata.update_metadata(root, "demo", {"genres": ["urban"]})

    assert json.loads((novel_root / "metadata.json").read_text(encoding="utf-8")) == {
        "source_language": "korean",
        "genres": ["fantasy"],
    }


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
    report_path = report_root / "vi" / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "manual_post_check_issues": ["contains_source_language_chars"],
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
    progress = catalog.progress(root, "demo", "vi", report_root=report_root)
    assert progress["warnings"] == [7]
    assert progress["source_warnings"] == [7]

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


def test_post_check_review_ignores_source_fragments_individually(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "囡和李来了")
    report_root = tmp_path / "reports"
    chapters.write_chapter(
        root,
        "demo",
        7,
        "Cô bé 囡 và 李 đã đến.",
        view="translation",
        target="vi",
        report_root=report_root,
    )

    review = chapters.chapter_post_check(root, "demo", 7, "vi", report_root=report_root)
    assert [(item.detail, item.ignored) for item in review.items] == [("囡", False), ("李", False)]

    review = chapters.review_post_check_item(
        root,
        "demo",
        7,
        "vi",
        review.items[0].key,
        ignored=True,
        report_root=report_root,
    )
    assert [item.ignored for item in review.items] == [True, False]
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == [7]

    review = chapters.review_post_check_item(
        root,
        "demo",
        7,
        "vi",
        review.items[1].key,
        ignored=True,
        report_root=report_root,
    )
    assert [item.ignored for item in review.items] == [True, True]
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == []


def test_post_check_review_lists_non_source_issues(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "A sufficiently long source paragraph.")
    report_root = tmp_path / "reports"
    chapters.write_chapter(
        root,
        "demo",
        7,
        "```text\nTranslated paragraph.\n```",
        view="translation",
        target="vi",
        report_root=report_root,
    )

    review = chapters.chapter_post_check(root, "demo", 7, "vi", report_root=report_root)

    code_fence = next(item for item in review.items if item.code == "contains_code_fence")
    assert code_fence.severity == "warning"
    assert code_fence.reviewable is True
    assert code_fence.origin == "output"
    progress = catalog.progress(root, "demo", "vi", report_root=report_root)
    assert progress["warnings"] == [7]
    assert progress["source_warnings"] == []

    review = chapters.review_post_check_item(
        root,
        "demo",
        7,
        "vi",
        code_fence.key,
        ignored=True,
        report_root=report_root,
    )

    assert next(item for item in review.items if item.code == "contains_code_fence").ignored is True
    assert catalog.progress(root, "demo", "vi", report_root=report_root)["warnings"] == []


def test_accept_candidate_publishes_normalized_output_and_clears_failure(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "张三走进房间。")
    candidate = "Chapter 7\n\nChapter 7\n\nTrương Tam 张三走 bước vào căn phòng."
    glossary_path = novel_root / "glossary.json"
    glossary_text = json.dumps(
        {"terms": {"房间": "căn phòng"}, "chapter_summaries": {"6": "Existing summary"}},
        ensure_ascii=False,
    )
    glossary_path.write_text(glossary_text, encoding="utf-8")
    report_root = tmp_path / "reports"
    report_path = report_root / "vi" / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "manual_post_check_issues": [],
                "ignored_post_checks": [{"code": "old", "content_hash": content_hash("old output")}],
                "issues": [{"key": "rejected:0:test", "code": "test", "severity": "error", "message": "Rejected."}],
                "candidate_translation": candidate,
                "partial": False,
                "failed_chunk_index": 0,
                "total_chunks": 1,
            }
        ),
        encoding="utf-8",
    )
    progress_root = tmp_path / "progress"
    progress_root.mkdir()
    (progress_root / "demo.json").write_text(
        json.dumps({"completed": [], "failed": [7]}),
        encoding="utf-8",
    )

    review = candidates.accept_candidate(
        root,
        "demo",
        7,
        "vi",
        content_hash(candidate),
        progress_root=progress_root,
        report_root=report_root,
        transaction_root=tmp_path / "transactions",
        lock_dir=tmp_path / "locks",
    )

    normalized = normalize_translation(candidate)
    assert (novel_root / "output" / "chapter_007.txt").read_text(encoding="utf-8") == normalized
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "contains_source_language_chars" in saved_report["manual_post_check_issues"]
    assert saved_report["ignored_post_checks"] == []
    assert saved_report["candidate_translation"] is None
    assert saved_report["issues"] == []
    assert json.loads((progress_root / "demo.json").read_text(encoding="utf-8")) == {
        "completed": [7],
        "failed": [],
    }
    assert review.candidate_translation is None
    assert review.candidate_hash is None
    assert all(item.origin == "output" and item.severity == "warning" for item in review.items)
    assert glossary_path.read_text(encoding="utf-8") == glossary_text


def test_accept_candidate_requires_hash_and_overwrite_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "Source chapter content.")
    _write_chapter(novel_root / "output", 7, "Existing translation.")
    candidate = "Replacement candidate translation."
    report_root = tmp_path / "reports"
    report_path = report_root / "vi" / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"candidate_translation": candidate, "partial": False}),
        encoding="utf-8",
    )

    def accept(expected_hash: str, *, overwrite: bool = False) -> chapters.PostCheckReview:
        return candidates.accept_candidate(
            root,
            "demo",
            7,
            "vi",
            expected_hash,
            overwrite=overwrite,
            progress_root=tmp_path / "progress",
            report_root=report_root,
            transaction_root=tmp_path / "transactions",
            lock_dir=tmp_path / "locks",
        )

    with pytest.raises(ResourceConflictError, match="changed"):
        accept("0" * 64, overwrite=True)
    with pytest.raises(ResourceConflictError, match="overwrite") as conflict:
        accept(content_hash(candidate))

    assert conflict.value.details == {"requires_overwrite_confirmation": True}
    assert (novel_root / "output" / "chapter_007.txt").read_text(encoding="utf-8") == "Existing translation."
    accept(content_hash(candidate), overwrite=True)
    assert (novel_root / "output" / "chapter_007.txt").read_text(encoding="utf-8") == candidate


@pytest.mark.parametrize(
    ("candidate", "partial", "message"),
    [
        ("   ", False, "empty"),
        ("Complete-looking but partial", True, "partial"),
    ],
)
def test_accept_candidate_rejects_empty_or_partial_content(
    tmp_path: Path,
    candidate: str,
    partial: bool,
    message: str,
) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "Source chapter content.")
    report_root = tmp_path / "reports"
    report_path = report_root / "vi" / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"candidate_translation": candidate, "partial": partial}),
        encoding="utf-8",
    )

    with pytest.raises(ApplicationValidationError, match=message):
        candidates.accept_candidate(
            root,
            "demo",
            7,
            "vi",
            content_hash(candidate),
            progress_root=tmp_path / "progress",
            report_root=report_root,
            transaction_root=tmp_path / "transactions",
            lock_dir=tmp_path / "locks",
        )

    assert not (novel_root / "output" / "chapter_007.txt").exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["candidate_translation"] == candidate


def test_accept_candidate_preserves_candidate_when_publication_fails(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    _write_chapter(novel_root / "input", 7, "Source chapter content.")
    candidate = "Candidate translation content."
    report_root = tmp_path / "reports"
    report_path = report_root / "vi" / "demo" / "chapter_007.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"candidate_translation": candidate, "partial": False}),
        encoding="utf-8",
    )

    with (
        patch.object(ChapterPublisher, "publish", side_effect=PublicationError("failed")),
        pytest.raises(PersistenceError, match="safely publish"),
    ):
        candidates.accept_candidate(
            root,
            "demo",
            7,
            "vi",
            content_hash(candidate),
            progress_root=tmp_path / "progress",
            report_root=report_root,
            transaction_root=tmp_path / "transactions",
            lock_dir=tmp_path / "locks",
        )

    assert not (novel_root / "output" / "chapter_007.txt").exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["candidate_translation"] == candidate


def test_accept_candidate_requires_existing_report(tmp_path: Path) -> None:
    root = tmp_path / "translated"
    _write_chapter(root / "demo" / "input", 7, "Source chapter content.")

    with pytest.raises(ResourceNotFoundError, match="report no longer exists"):
        candidates.accept_candidate(
            root,
            "demo",
            7,
            "vi",
            "0" * 64,
            progress_root=tmp_path / "progress",
            report_root=tmp_path / "reports",
            transaction_root=tmp_path / "transactions",
            lock_dir=tmp_path / "locks",
        )


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
