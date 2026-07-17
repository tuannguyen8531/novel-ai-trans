from pathlib import Path
from unittest.mock import patch

from src.application.glossary.replacements import apply_pending_replacements
from src.config import Config, active_config_scope
from src.services.glossary.repository import save_glossary, update_glossary_term


def test_apply_pending_replacements_uses_explicit_target_scope(tmp_path: Path) -> None:
    novel_root = tmp_path / "translated" / "demo"
    input_dir = novel_root / "input"
    output_dir = novel_root / "output" / "en"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (input_dir / "chapter_1.txt").write_text("魔法", encoding="utf-8")
    output_path = output_dir / "chapter_001.txt"
    output_path.write_text("Old magic", encoding="utf-8")

    english_config = Config(translated_dir=str(tmp_path / "translated"), target_language="en")
    with active_config_scope(english_config):
        save_glossary("demo", {"魔法": "Old magic"})
        update_glossary_term("demo", "魔法", "魔法", "New magic", is_user_edit=True)

    vietnamese_config = Config(translated_dir=str(tmp_path / "translated"), target_language="vi")
    with (
        active_config_scope(vietnamese_config),
        patch("src.application.locks.LOCK_DIR", tmp_path / "locks"),
        patch("src.application.glossary.replacements.GLOSSARY_BACKUP_DIR", tmp_path / "backups"),
    ):
        result = apply_pending_replacements("demo", target_language="en", write=True)

    assert result["target"] == "en"
    assert result["changed_files"] == 1
    assert output_path.read_text(encoding="utf-8") == "New magic"
