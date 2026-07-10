from __future__ import annotations

from unittest.mock import patch

from src.application.glossary import audit_glossary
from src.config import Config


def test_vietnamese_audit_reads_legacy_output_directory(tmp_path):
    novel_root = tmp_path / "demo"
    source_dir = novel_root / "input"
    output_dir = novel_root / "output"
    source_dir.mkdir(parents=True)
    output_dir.mkdir()
    (source_dir / "chapter_1.txt").write_text("猫", encoding="utf-8")
    (output_dir / "chapter_001.txt").write_text("cat", encoding="utf-8")

    with (
        patch("src.application.glossary.load_glossary", return_value={"terms": {"猫": "mèo"}}),
        patch(
            "src.application.glossary.app_config.get_config",
            return_value=Config(translated_dir=str(tmp_path)),
        ),
    ):
        issues = audit_glossary("demo", target="vi")

    assert issues == [{"chapter": 1, "term": "猫", "expected": "mèo", "issue": "missing_translation"}]
