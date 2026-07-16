"""Tests for independent single-chapter translation."""

import json

from src.application.translation.chapter import translate_chapter
from src.services.reports import ReportStore
from src.services.translations import TranslationStorage


class FakeGraph:
    def invoke(self, state):
        assert state["source_text"] == "source"
        return {
            "final_translation": "translated",
            "new_terms": {"李白": "Lý Bạch"},
            "new_characters": {"entities": {"李白": {}}},
            "quality_reports": [{"score": 0.9}],
        }


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
        "chapter": 1,
        "target_language": "vi",
        "output_chars": len("translated"),
        "elapsed_seconds": 1.25,
        "new_terms_count": 1,
        "new_characters_count": 1,
        "chunks": [{"score": 0.9}],
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
