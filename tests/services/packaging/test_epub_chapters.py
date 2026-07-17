from src.services.packaging.chapters import parse_chapter_file


def test_parse_chapter_file_keeps_author_note_out_of_title(tmp_path) -> None:
    chapter = tmp_path / "chapter_013.txt"
    chapter.write_text(
        "Chương 13: Làm anh em, khắc ghi trong lòng!\n\n"
        "【PS: Chương này không mô tả chi tiết hành vi bạo lực học đường.】\n\n"
        "Nội dung",
        encoding="utf-8",
    )

    title, paragraphs = parse_chapter_file(chapter)

    assert title == "Chương 13: Làm anh em, khắc ghi trong lòng!"
    assert paragraphs == ["[PS: Chương này không mô tả chi tiết hành vi bạo lực học đường.]", "Nội dung"]


def test_parse_chapter_file_preserves_missing_file_fallback(tmp_path) -> None:
    title, paragraphs = parse_chapter_file(tmp_path / "chapter_404.txt")

    assert title == "Chương chapter_404"
    assert paragraphs == []
