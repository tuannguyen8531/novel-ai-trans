"""Tests for the EPUB packaging workflow."""

from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from src.application.pack import PackRequest, run_pack


def test_run_pack_builds_single_epub_artifact(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody text.", encoding="utf-8")
    config = SimpleNamespace(translated_dir=str(translated_root), target_language="vi")

    with (
        patch("src.application.pack.get_config", return_value=config),
        patch("src.services.packaging.config", config),
    ):
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
        patch("src.services.packaging.config", config),
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
