"""Tests for translation quality-report persistence."""

import json

from src.services.translation.reports import ReportStore


def test_report_store_creates_parent_and_preserves_unicode(tmp_path) -> None:
    path = tmp_path / "reports" / "chapter_001.json"

    ReportStore().save(path, {"chapter": 1, "feedback": "Tốt"})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "chapter": 1,
        "feedback": "Tốt",
    }
