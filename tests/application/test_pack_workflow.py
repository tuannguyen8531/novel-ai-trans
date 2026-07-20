"""Tests for the EPUB packaging workflow."""

import json
import tempfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from src import paths
from src.application.errors import OperationCancelledError, ResourceConflictError
from src.application.locks import novel_lock
from src.application.novel import artifacts as novel_artifacts
from src.application.pack import PackRequest, run_pack


@pytest.fixture(autouse=True)
def _artifact_locks_in_temporary_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.application.locks.LOCK_DIR", tmp_path / "runtime" / "locks")


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

    manifest_path = translated_root / "demo" / "artifacts" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not manifest_path.with_name(".manifest.lock").exists()
    assert list((tmp_path / "runtime" / "locks").glob("*.lock")) == [
        paths.novel_lock_path("demo", lock_dir=tmp_path / "runtime" / "locks")
    ]
    recorded = manifest["artifacts"]["demo.vi.epub"]
    assert recorded["format"] == "epub"
    assert recorded["target_language"] == "vi"
    assert recorded["chapter_count"] == 1
    assert recorded["size"] == result.artifacts[0].size

    (output_dir / "chapter_002.txt").write_text("Chapter 2\n\nNew body.", encoding="utf-8")
    listed = novel_artifacts.list_artifacts(translated_root, "demo")
    assert [(artifact.chapter_count, artifact.metadata_status) for artifact in listed] == [(1, "recorded")]

    with patch("src.application.pack.get_config", return_value=config):
        run_pack(PackRequest(novel="demo"))

    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert list(updated["artifacts"]) == ["demo.vi.epub"]
    assert updated["artifacts"]["demo.vi.epub"]["chapter_count"] == 2


def test_run_pack_uses_the_shared_novel_lock(tmp_path) -> None:
    lock_dir = tmp_path / "runtime" / "locks"

    with (
        novel_lock("demo", lock_dir=lock_dir),
        pytest.raises(ResourceConflictError, match="currently locked"),
    ):
        run_pack(PackRequest(novel="demo"))


def test_run_pack_preserves_core_epub_entries_and_cleans_downloaded_cover(tmp_path) -> None:
    translated_root = tmp_path / "translated"
    output_dir = translated_root / "demo" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "chapter_001.txt").write_text("Chapter 1\n\nBody text.", encoding="utf-8")
    with tempfile.NamedTemporaryFile(prefix="novel_cover_downloaded_", suffix=".jpg", delete=False) as temporary:
        temporary.write(b"cover-image")
        downloaded_cover = Path(temporary.name)
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
    with tempfile.NamedTemporaryFile(prefix="novel_cover_cancelled_", suffix=".jpg", delete=False) as temporary:
        temporary.write(b"cover")
        temporary_cover = Path(temporary.name)
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
