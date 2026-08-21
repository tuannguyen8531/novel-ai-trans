"""Tests for independent single-chapter translation."""

from src.application.translation.chapter import translate_chapter
from src.services.translation.storage import TranslationStorage


class FakeGraph:
    def invoke(self, state):
        assert state["source_text"] == "source"
        return {
            "final_translation": "translated",
            "new_terms": {"李白": "Lý Bạch"},
            "new_characters": {"entities": {"李白": {}}},
            "quality_reports": [{"score": 0.9}],
        }


class DuplicateHeadingGraph:
    def invoke(self, state):
        assert state["source_text"] == "第213章 黎知决定主动出击（1W）\n\n沈元绷着脸。"
        heading = "Chương 213: Lê Tri quyết định chủ động tấn công (1W)"
        return {"final_translation": f"{heading}\n\n{heading}\n\nThẩm Nguyên căng mặt."}


class MissingTitleGraph:
    def invoke(self, state):
        return {"final_translation": "Chương 1\n\nNội dung."}


def test_translate_chapter_prepares_output_and_quality_report(tmp_path) -> None:
    input_path = tmp_path / "chapter_1.txt"
    input_path.write_text("source", encoding="utf-8")
    times = iter([10.0, 11.25])
    published: list[tuple[str, list[str]]] = []

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=1,
        source_language="chinese",
        target_language="vi",
        graph=FakeGraph(),
        storage=TranslationStorage(),
        publish=lambda content, issues: published.append((content, issues)),
        clock=lambda: next(times),
    )

    assert result == (True, len("translated"), 1.25, 1)
    assert published == [("translated", [])]


def test_translate_chapter_skips_blank_source(tmp_path) -> None:
    input_path = tmp_path / "chapter_1.txt"
    input_path.write_text("  \n", encoding="utf-8")

    published: list[tuple[str, list[str]]] = []
    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=1,
        source_language="",
        target_language="vi",
        graph=FakeGraph(),
        storage=TranslationStorage(),
        publish=lambda content, issues: published.append((content, issues)),
    )

    assert result == (False, 0, 0, 0)
    assert published == []


def test_translate_chapter_deduplicates_source_and_output_headings(tmp_path) -> None:
    input_path = tmp_path / "chapter_213.txt"
    source = "第213章 黎知决定主动出击（1W）\n\n第213章 黎知决定主动出击（1W）\n沈元绷着脸。"
    input_path.write_text(source, encoding="utf-8")
    published: list[tuple[str, list[str]]] = []

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=213,
        source_language="chinese",
        target_language="vi",
        graph=DuplicateHeadingGraph(),
        storage=TranslationStorage(),
        publish=lambda content, issues: published.append((content, issues)),
    )

    expected = "Chương 213: Lê Tri quyết định chủ động tấn công (1W)\n\nThẩm Nguyên căng mặt."
    assert result[0]
    assert published[0][0] == expected
    assert input_path.read_text(encoding="utf-8") == source


def test_translate_chapter_reports_missing_translated_title(tmp_path) -> None:
    input_path = tmp_path / "chapter_1.txt"
    input_path.write_text("第1章 新年\n\n正文", encoding="utf-8")
    published: list[tuple[str, list[str]]] = []

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=1,
        source_language="chinese",
        target_language="vi",
        graph=MissingTitleGraph(),
        storage=TranslationStorage(),
        publish=lambda content, issues: published.append((content, issues)),
    )

    assert result[0]
    assert published == [("Chương 1\n\nNội dung.", ["missing_translated_title"])]
