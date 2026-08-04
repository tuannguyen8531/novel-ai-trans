"""Tests for independent single-chapter translation."""

import json

from src.application.translation.chapter import translate_chapter
from src.services.translation.reports import ReportStore
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


def test_translate_chapter_writes_output_and_quality_report(tmp_path) -> None:
    input_path = tmp_path / "chapter_1.txt"
    input_path.write_text("source", encoding="utf-8")
    output_dir = tmp_path / "output"
    report_path = tmp_path / "reports" / "chapter_001.json"
    times = iter([10.0, 11.25])

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=1,
        source_language="chinese",
        target_language="vi",
        graph=FakeGraph(),
        output_dir=output_dir,
        report_path=report_path,
        storage=TranslationStorage(),
        reports=ReportStore(),
        clock=lambda: next(times),
    )

    assert result == (True, len("translated"), 1.25, 1)
    assert (output_dir / "chapter_001.txt").read_text(encoding="utf-8") == "translated"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report == {
        "manual_post_check_issues": [],
        "ignored_post_checks": [],
        "issues": [],
        "candidate_translation": None,
        "partial": False,
        "failed_chunk_index": None,
        "total_chunks": None,
    }


def test_translate_chapter_skips_blank_source(tmp_path) -> None:
    input_path = tmp_path / "chapter_1.txt"
    input_path.write_text("  \n", encoding="utf-8")

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=1,
        source_language="",
        target_language="vi",
        graph=FakeGraph(),
        output_dir=tmp_path / "output",
        report_path=tmp_path / "report.json",
        storage=TranslationStorage(),
        reports=ReportStore(),
    )

    assert result == (False, 0, 0, 0)
    assert not (tmp_path / "report.json").exists()


def test_translate_chapter_deduplicates_source_and_output_headings(tmp_path) -> None:
    input_path = tmp_path / "chapter_213.txt"
    source = "第213章 黎知决定主动出击（1W）\n\n第213章 黎知决定主动出击（1W）\n沈元绷着脸。"
    input_path.write_text(source, encoding="utf-8")
    output_dir = tmp_path / "output"

    result = translate_chapter(
        input_path,
        novel="novel",
        chapter=213,
        source_language="chinese",
        target_language="vi",
        graph=DuplicateHeadingGraph(),
        output_dir=output_dir,
        report_path=tmp_path / "report.json",
        storage=TranslationStorage(),
        reports=ReportStore(),
    )

    expected = "Chương 213: Lê Tri quyết định chủ động tấn công (1W)\n\nThẩm Nguyên căng mặt."
    assert result[0]
    assert (output_dir / "chapter_213.txt").read_text(encoding="utf-8") == expected
    assert input_path.read_text(encoding="utf-8") == source
