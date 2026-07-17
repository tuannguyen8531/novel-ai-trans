import zipfile
from unittest.mock import patch

import pytest

from src.models import NovelMetadata
from src.services.importing.extractor import EpubSection
from src.services.importing.selection import ProcessedChapter
from src.services.importing.storage import persist_chapters, persist_metadata, prepare_storage
from src.utils.files import write_text_atomic


def prepared_chapters() -> list[ProcessedChapter]:
    return [
        ProcessedChapter(1, EpubSection(1, "one.xhtml", "Chapter 1", "First body.")),
        ProcessedChapter(2, EpubSection(2, "two.xhtml", "Chapter 2", "Second body.")),
    ]


def test_persistence_accepts_prepared_parsed_data(tmp_path) -> None:
    epub_path = tmp_path / "input.epub"
    with zipfile.ZipFile(epub_path, "w"):
        pass
    paths, existing = prepare_storage(tmp_path / "translated", "demo", keep_existing=False)
    metadata = NovelMetadata(title="Demo", author=None, source_url=epub_path.resolve().as_uri(), site_name="demo")

    persist_metadata(paths, metadata, None)
    result = persist_chapters(
        epub_path,
        prepared_chapters(),
        epub_path.resolve().as_uri(),
        paths,
        existing,
        keep_existing=False,
    )

    assert result.changes.added == (1, 2)
    assert (paths.chapter_output_dir / "chapter_001.txt").read_text(encoding="utf-8") == "First body.\n"
    assert (paths.novel_dir / "metadata.json").is_file()


def test_persistence_failure_keeps_existing_partial_writes(tmp_path) -> None:
    epub_path = tmp_path / "input.epub"
    with zipfile.ZipFile(epub_path, "w"):
        pass
    paths, existing = prepare_storage(tmp_path / "translated", "demo", keep_existing=False)
    metadata = NovelMetadata(title="Demo", author=None, source_url=epub_path.resolve().as_uri(), site_name="demo")
    persist_metadata(paths, metadata, None)
    write_count = 0

    def fail_on_second_write(path, text):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise OSError("second chapter failed")
        write_text_atomic(path, text)

    with (
        patch("src.services.importing.storage.write_text_atomic", side_effect=fail_on_second_write),
        pytest.raises(OSError, match="second chapter failed"),
    ):
        persist_chapters(
            epub_path,
            prepared_chapters(),
            epub_path.resolve().as_uri(),
            paths,
            existing,
            keep_existing=False,
        )

    assert (paths.novel_dir / "metadata.json").is_file()
    assert (paths.chapter_output_dir / "chapter_001.txt").read_text(encoding="utf-8") == "First body.\n"
    assert not (paths.chapter_output_dir / "chapter_002.txt").exists()
