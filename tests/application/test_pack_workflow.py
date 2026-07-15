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
