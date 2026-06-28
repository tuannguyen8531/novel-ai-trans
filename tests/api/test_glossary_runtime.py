from __future__ import annotations

from unittest.mock import patch

from src.api.services.glossary_runtime import audit_glossary


def test_vietnamese_audit_reads_legacy_output_directory(tmp_path):
    novel_root = tmp_path / "demo"
    source_dir = novel_root / "input"
    output_dir = novel_root / "output"
    source_dir.mkdir(parents=True)
    output_dir.mkdir()
    (source_dir / "chapter_1.txt").write_text("猫", encoding="utf-8")
    (output_dir / "chapter_001.txt").write_text("cat", encoding="utf-8")

    with patch(
        "src.api.services.glossary_runtime.load_glossary",
        return_value={"terms": {"猫": "mèo"}},
    ):
        issues = audit_glossary(novel_root, target="vi")

    assert issues == [{"chapter": 1, "term": "猫", "expected": "mèo", "issue": "missing_translation"}]
