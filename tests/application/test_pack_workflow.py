"""Tests for the EPUB packaging workflow."""

import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from src.application.errors import OperationCancelledError
from src.application.pack import PackRequest, run_pack


def test_run_pack_builds_single_epub_artifact(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody text.", encoding="utf-8")
    config = SimpleNamespace(translated_dir=str(translated_root), target_language="vi")

    with patch("src.application.pack.get_config", return_value=config):
        result = run_pack(PackRequest(novel="demo"))

    assert [(artifact.format, artifact.path) for artifact in result.artifacts] == [
        ("epub", str(translated_root / "demo" / "artifacts" / "demo.vi.epub"))
    ]
    with ZipFile(result.artifacts[0].path) as epub:
        assert epub.testzip() is None


def test_run_pack_preserves_core_epub_entries_and_cleans_downloaded_cover(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody text.", encoding="utf-8")
    downloaded_cover = tmp_path / "novel_cover_downloaded.jpg"
    downloaded_cover.write_bytes(b"cover-image")
    config = SimpleNamespace(translated_dir=str(translated_root), target_language="vi")

    with (
        patch("src.application.pack.get_config", return_value=config),
        patch("src.application.pack.load_metadata", return_value={"title": "Demo Title", "author": "Demo Author"}),
        patch("src.application.pack.resolve_cover_image", return_value=downloaded_cover),
    ):
        result = run_pack(PackRequest(novel="demo"))

    assert not downloaded_cover.exists()
    with ZipFile(result.artifacts[0].path) as epub:
        entries = set(epub.namelist())
        content = epub.read("OEBPS/content.opf").decode("utf-8")

    assert {
        "mimetype",
        "META-INF/container.xml",
        "OEBPS/content.opf",
        "OEBPS/chapter_1.xhtml",
        "OEBPS/cover.jpg",
        "OEBPS/cover.xhtml",
    } <= entries
    assert "<dc:title>Demo Title</dc:title>" in content
    assert '<dc:creator opf:role="aut">Demo Author</dc:creator>' in content


def test_run_pack_resolves_target_specific_paths_in_application(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output" / "en"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody text.", encoding="utf-8")
    config = SimpleNamespace(translated_dir=str(translated_root), target_language="vi")

    with patch("src.application.pack.get_config", return_value=config):
        result = run_pack(PackRequest(novel="demo", target_language="en"))

    assert result.artifacts[0].path == str(translated_root / "demo" / "artifacts" / "demo.en.epub")


def test_run_pack_preserves_metadata_fallback_illustrations_layout_and_progress(tmp_path) -> None:
    novel_root = tmp_path / "translated" / "demo"
    output_dir = novel_root / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_010.txt").write_text("Chapter 10\n\nLast.", encoding="utf-8")
    (output_dir / "chapter_002.txt").write_text(
        "Chapter 2\n\nBefore.\n\n[[ILLUSTRATION:002-001.png]]\n\nAfter.",
        encoding="utf-8",
    )
    (novel_root / "metadata.json").write_text(
        json.dumps({"title": "Original", "localized": {"vi": {"title": "Bản dịch"}}, "author": "Author"}),
        encoding="utf-8",
    )
    illustrations_dir = novel_root / "illustrations"
    illustrations_dir.mkdir()
    (illustrations_dir / "002-001.png").write_bytes(b"illustration")
    config = SimpleNamespace(translated_dir=str(tmp_path / "translated"), target_language="vi")
    events = []

    with patch("src.application.pack.get_config", return_value=config):
        result = run_pack(PackRequest(novel="demo"), progress_callback=events.append)

    assert result.title == "Bản dịch"
    assert result.author == "Author"
    assert [(event.kind, event.chapter) for event in events] == [
        ("chapter_loaded", 2),
        ("chapter_loaded", 10),
        ("phase", None),
        ("completed", None),
    ]
    with ZipFile(result.artifacts[0].path) as epub:
        assert set(epub.namelist()) == {
            "mimetype",
            "META-INF/container.xml",
            "OEBPS/style.css",
            "OEBPS/images/002-001.png",
            "OEBPS/chapter_1.xhtml",
            "OEBPS/chapter_2.xhtml",
            "OEBPS/toc.ncx",
            "OEBPS/content.opf",
        }
        first_chapter = epub.read("OEBPS/chapter_1.xhtml").decode("utf-8")
        toc = epub.read("OEBPS/toc.ncx").decode("utf-8")

    assert first_chapter.index("Before.") < first_chapter.index("images/002-001.png") < first_chapter.index("After.")
    assert toc.index("Chapter 2") < toc.index("Chapter 10")


def test_run_pack_preserves_cancel_boundary_and_cover_cleanup(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody.", encoding="utf-8")
    temporary_cover = tmp_path / "novel_cover_cancelled.jpg"
    temporary_cover.write_bytes(b"cover")
    config = SimpleNamespace(translated_dir=str(translated_root), target_language="vi")
    cancel_event = Event()
    cancel_event.set()

    with (
        patch("src.application.pack.get_config", return_value=config),
        patch("src.application.pack.resolve_cover_image", return_value=temporary_cover),
        pytest.raises(OperationCancelledError, match="Pack cancelled"),
    ):
        run_pack(PackRequest(novel="demo"), cancel_event=cancel_event)

    assert not temporary_cover.exists()
    assert not (translated_root / "demo" / "artifacts" / "demo.vi.epub").exists()
