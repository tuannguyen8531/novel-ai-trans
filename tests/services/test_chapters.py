from pathlib import Path

from src.services import chapters


def test_scan_returns_sorted_chapter_files_and_ignores_other_entries(tmp_path: Path) -> None:
    (tmp_path / "chapter_10.txt").write_text("ten", encoding="utf-8")
    (tmp_path / "chapter_002.txt").write_text("two", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "chapter_3.txt").mkdir()

    found = chapters.scan(tmp_path)

    assert list(found) == [2, 10]
    assert found[2].name == "chapter_002.txt"
    assert chapters.numbers(tmp_path) == {2, 10}


def test_scan_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    assert chapters.scan(tmp_path / "missing") == {}


def test_chapter_path_uses_padding_for_new_files_and_preserves_legacy_files(tmp_path: Path) -> None:
    assert chapters.chapter_path(tmp_path, 7).name == "chapter_007.txt"

    legacy = tmp_path / "chapter_7.txt"
    legacy.write_text("legacy", encoding="utf-8")

    assert chapters.chapter_path(tmp_path, 7) == legacy


def test_scan_prefers_canonical_file_when_both_names_exist(tmp_path: Path) -> None:
    legacy = tmp_path / "chapter_2.txt"
    canonical = tmp_path / "chapter_002.txt"
    legacy.write_text("legacy", encoding="utf-8")
    canonical.write_text("canonical", encoding="utf-8")

    assert chapters.scan(tmp_path)[2] == canonical


def test_read_title_uses_last_consecutive_header_and_normalizes_punctuation(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter_1.txt"
    chapter.write_text(
        "\ufeffChương 1\nChương 1: 『Khởi đầu』—Phần 一\n\nNội dung",
        encoding="utf-8",
    )

    assert chapters.read_title(chapter, "fallback") == 'Chương 1: "Khởi đầu"-Phần 一'
    assert chapters.read_title(chapter, "fallback", keep_cjk=False) == 'Chương 1: "Khởi đầu"-Phần'


def test_read_title_returns_fallback_for_missing_or_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "chapter_1.txt"
    empty.write_text("\n", encoding="utf-8")

    assert chapters.read_title(empty, "Chapter 1") == "Chapter 1"
    assert chapters.read_title(tmp_path / "missing.txt", "Chapter 2") == "Chapter 2"


def test_read_title_does_not_treat_author_note_as_chapter_heading(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter_13.txt"
    chapter.write_text(
        "Chương 13: Làm anh em, khắc ghi trong lòng!\n\n"
        "【PS: Chương này không mô tả chi tiết hành vi bạo lực học đường.】\n\n"
        "Nội dung",
        encoding="utf-8",
    )

    assert chapters.read_title(chapter, "fallback") == "Chương 13: Làm anh em, khắc ghi trong lòng!"
