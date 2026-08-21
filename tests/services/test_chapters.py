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


def test_detect_chapter_number_supports_existing_import_formats() -> None:
    cases = {
        "1화 - 회귀": 1,
        "제12화 재회": 12,
        "3장 시작": 3,
        "Chương 4: Khởi đầu": 4,
        "Chuong 5 - Gap lai": 5,
        "Chapter 6: Return": 6,
        "Ch. 7 - Return": 7,
        "Episode 8 - Return": 8,
        "第9章 帰還": 9,
        "第10話 帰還": 10,
        "12章 别让八班嚣张起来": 12,
    }

    assert {title: chapters.detect_chapter_number(title) for title in cases} == cases


def test_detect_chapter_number_ignores_unmarked_numbers() -> None:
    titles = ["notice 65", "일러스트 모음 65 추가", "2024 special notice", "cover"]

    assert all(chapters.detect_chapter_number(title) is None for title in titles)


def test_parse_heading_removes_separator_after_chinese_chapter_marker() -> None:
    parsed = chapters.parse_chapter_heading("第203章：暴雨夜的苏雨晴！")

    assert parsed is not None
    assert parsed.title == "暴雨夜的苏雨晴!"


def test_resolve_chinese_numeral_title_series_keeps_terminal_punctuation() -> None:
    catalog = {
        203: "第203章 暴雨夜的苏雨晴！",
        204: "第204章 暴雨夜的苏雨晴！（二）",
        205: "第205章 暴雨夜的苏雨晴！（三）",
    }

    parsed = [chapters.parse_chapter_heading(catalog[number]) for number in catalog]
    assert all(item is not None for item in parsed)
    resolved = [chapters.resolve_chapter_title_series(item, catalog) for item in parsed if item is not None]

    assert [(item.base, item.part, item.is_series) for item in resolved] == [
        ("暴雨夜的苏雨晴!", None, True),
        ("暴雨夜的苏雨晴!", 2, True),
        ("暴雨夜的苏雨晴!", 3, True),
    ]


def test_numeric_parenthetical_is_not_series_without_adjacent_sequence() -> None:
    parsed = chapters.parse_chapter_heading("第204章 暴雨夜的苏雨晴！（二）")

    assert parsed is not None
    resolved = chapters.resolve_chapter_title_series(parsed, {204: parsed.heading})

    assert resolved.is_series is False
    assert resolved.base == "暴雨夜的苏雨晴!(二)"
    assert resolved.part is None


def test_split_leading_heading_removes_heading_and_following_blank_lines() -> None:
    catalog = {1: "第1章 新年", 2: "第2章 新年（2）"}

    resolved, body = chapters.split_leading_chapter_heading(
        "第1章 新年\n\n正文第一段。\n\n正文第二段。",
        1,
        catalog,
    )

    assert resolved is not None
    assert resolved.base == "新年"
    assert resolved.part is None
    assert body == "正文第一段。\n\n正文第二段。"


def test_deduplicate_leading_headings_removes_exact_duplicate_and_preserves_spacing() -> None:
    source = "第213章 黎知决定主动出击（1W）\n\n第213章 黎知决定主动出击（1W）\n沈元绷着脸。\n"

    assert chapters.deduplicate_leading_headings(source) == ("第213章 黎知决定主动出击（1W）\n\n沈元绷着脸。\n")


def test_deduplicate_leading_headings_keeps_later_punctuation_variant() -> None:
    source = "第206章 黎知，我（1w）\n\n第206章 黎知，我……（1w）\n正文"

    assert chapters.deduplicate_leading_headings(source) == "第206章 黎知，我……（1w）\n\n正文"


def test_deduplicate_leading_headings_keeps_distinct_body_line() -> None:
    source = "第213章 黎知决定主动出击（1W）\n\n沈元绷着脸。\n"

    assert chapters.deduplicate_leading_headings(source) == source


def test_deduplicate_leading_headings_does_not_collapse_unnumbered_prose_by_default() -> None:
    source = "Run!\n\nRun!\n\nThen the race began."

    assert chapters.deduplicate_leading_headings(source) == source


def test_numbered_chapter_with_notice_marker_is_not_filtered() -> None:
    titles = ["作品更新通知", "Notice: 550화까지 왔습니다!!", "第301章 是通知还是邀请", "第302章 是体香"]

    assert chapters.is_obvious_non_chapter_title(titles[0])
    assert chapters.is_obvious_non_chapter_title(titles[1])
    assert not chapters.is_obvious_non_chapter_title(titles[2])
    assert chapters.select_likely_chapters(titles, title_getter=lambda title: title) == titles[2:]
