from pathlib import Path

from src.config import Config, active_config_scope
from src.services.chapter_memory import (
    load_chapter_summary,
    load_recent_chapter_summaries,
    save_chapter_summary,
)


def test_save_and_load_chapter_summary(tmp_path: Path) -> None:
    with active_config_scope(Config(translated_dir=str(tmp_path))):
        save_chapter_summary("demo", 1, "Chapter 1 summary")
        assert load_chapter_summary("demo", 1) == "Chapter 1 summary"


def test_load_nonexistent_summary(tmp_path: Path) -> None:
    with active_config_scope(Config(translated_dir=str(tmp_path))):
        assert load_chapter_summary("missing", 1) == ""


def test_load_recent_chapter_summaries(tmp_path: Path) -> None:
    with active_config_scope(Config(translated_dir=str(tmp_path))):
        for chapter in range(1, 6):
            save_chapter_summary("demo", chapter, f"Summary {chapter}")

        result = load_recent_chapter_summaries("demo", 6, max_count=3)

    assert "Chapter 3" in result
    assert "Chapter 4" in result
    assert "Chapter 5" in result
    assert "Chapter 2" not in result


def test_recent_chapter_summaries_keep_chapter_order(tmp_path: Path) -> None:
    with active_config_scope(Config(translated_dir=str(tmp_path))):
        save_chapter_summary("demo", 1, "First")
        save_chapter_summary("demo", 2, "Second")
        save_chapter_summary("demo", 3, "Third")
        result = load_recent_chapter_summaries("demo", 4, max_count=3)

    assert result == "Chapter 1: First\n\nChapter 2: Second\n\nChapter 3: Third"


def test_chapter_memory_is_scoped_to_target_language(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    with active_config_scope(Config(translated_dir=str(translated_root), target_language="vi")):
        save_chapter_summary("demo", 1, "Vietnamese summary")

    with active_config_scope(Config(translated_dir=str(translated_root), target_language="en")):
        assert load_chapter_summary("demo", 1) == ""
        save_chapter_summary("demo", 1, "English summary")

    with active_config_scope(Config(translated_dir=str(translated_root), target_language="vi")):
        assert load_chapter_summary("demo", 1) == "Vietnamese summary"

    with active_config_scope(Config(translated_dir=str(translated_root), target_language="en")):
        assert load_chapter_summary("demo", 1) == "English summary"
