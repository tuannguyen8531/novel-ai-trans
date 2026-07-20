from __future__ import annotations

from unittest.mock import patch

from src.api.auth import Principal
from src.api.routes.glossary import get_glossary, update_character
from src.api.schemas import GlossaryCharacterUpdate
from src.application.glossary.audit import audit_glossary
from src.application.glossary.storage import load_glossary
from src.config import Config, active_config_scope
from src.services.glossary.repository import save_characters_batch

EMPTY_GLOSSARY = {"terms": {}, "entities": {}, "edges": []}


def test_load_glossary_returns_complete_empty_shape_when_missing(tmp_path):
    with active_config_scope(Config(translated_dir=str(tmp_path))):
        assert load_glossary("demo") == EMPTY_GLOSSARY


def test_load_glossary_returns_complete_empty_shape_for_invalid_json(tmp_path):
    glossary_path = tmp_path / "demo" / "glossary.json"
    glossary_path.parent.mkdir(parents=True)
    glossary_path.write_text("{invalid", encoding="utf-8")

    with active_config_scope(Config(translated_dir=str(tmp_path))):
        assert load_glossary("demo") == EMPTY_GLOSSARY


def test_get_glossary_preserves_empty_response_contract(tmp_path):
    (tmp_path / "demo").mkdir()

    with active_config_scope(Config(translated_dir=str(tmp_path))):
        response = get_glossary("demo", Principal(authenticated=True, source="local"))

    assert response.novel == "demo"
    assert response.data == EMPTY_GLOSSARY


def test_update_character_pronoun_supports_preserve_update_and_clear(tmp_path):
    (tmp_path / "demo").mkdir()
    principal = Principal(authenticated=True, source="local")

    with active_config_scope(Config(translated_dir=str(tmp_path))):
        save_characters_batch(
            "demo",
            {"李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": "ông"}},
            [],
        )
        preserved = update_character("demo", "李白", GlossaryCharacterUpdate(role="supporting"), principal)
        updated = update_character("demo", "李白", GlossaryCharacterUpdate(pronoun="anh ấy"), principal)
        cleared = update_character("demo", "李白", GlossaryCharacterUpdate(pronoun=""), principal)

    assert preserved.data["entities"]["李白"]["pronoun"] == "ông"
    assert updated.data["entities"]["李白"]["pronoun"] == "anh ấy"
    assert cleared.data["entities"]["李白"]["pronoun"] == ""


def test_vietnamese_audit_reads_legacy_output_directory(tmp_path):
    novel_root = tmp_path / "demo"
    source_dir = novel_root / "input"
    output_dir = novel_root / "output"
    source_dir.mkdir(parents=True)
    output_dir.mkdir()
    (source_dir / "chapter_1.txt").write_text("猫", encoding="utf-8")
    (output_dir / "chapter_001.txt").write_text("cat", encoding="utf-8")

    with (
        patch("src.application.glossary.audit.load_glossary", return_value={"terms": {"猫": "mèo"}}),
        patch(
            "src.application.glossary.audit.app_config.get_config",
            return_value=Config(translated_dir=str(tmp_path)),
        ),
    ):
        issues = audit_glossary("demo", target="vi")

    assert issues == [{"chapter": 1, "term": "猫", "expected": "mèo", "issue": "missing_translation"}]
