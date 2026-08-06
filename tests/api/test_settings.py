"""Tests for API settings and settings.json persistence."""

from __future__ import annotations

import json
from pathlib import Path

from src.api.services.settings import config_to_settings_dict, persist_config_to_settings
from src.config import Config


def test_settings_dict_excludes_secrets():
    values = config_to_settings_dict(Config(gemini_api_key="secret", telegram_bot_token="token"))
    assert "gemini_api_key" not in values
    assert "telegram_bot_token" not in values
    assert values["target_language"] == "vi"


def test_persist_settings_writes_atomically_and_preserves_unknown_keys(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"custom": "preserved", "target_language": "vi"}\n', encoding="utf-8")

    changed = persist_config_to_settings(Config(target_language="en"), path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["custom"] == "preserved"
    assert data["target_language"] == "en"
    assert "target_language" in changed
    assert not list(tmp_path.glob(".*.tmp"))


def test_persist_settings_can_limit_fields(tmp_path: Path):
    path = tmp_path / "settings.json"
    persist_config_to_settings(
        Config(target_language="en", chunk_size=2200),
        path,
        field_names={"target_language"},
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"target_language": "en"}
