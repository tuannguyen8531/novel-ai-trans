"""Tests for API settings and settings.json persistence."""

from __future__ import annotations

import json
from pathlib import Path

from src.api.auth import Principal
from src.api.routes.system import persist_provider_settings
from src.api.schemas import ProviderSettingsPatch
from src.api.services.settings import config_to_settings_dict, persist_config_to_settings
from src.application import config as app_config
from src.config import Config


def test_settings_dict_excludes_secrets():
    values = config_to_settings_dict(Config(gemini_api_key="secret", nvidia_api_key="nvapi-secret", telegram_bot_token="token"))
    assert "gemini_api_key" not in values
    assert "nvidia_api_key" not in values
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


def test_provider_persistence_keeps_nvidia_secret_out_of_json_and_preserves_blank_key(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    monkeypatch.setattr("src.api.routes.system.DEFAULT_SETTINGS_PATH", settings_path)
    monkeypatch.setattr("src.api.routes.system.DEFAULT_ENV_PATH", env_path)
    original = app_config.get_config()
    app_config.set_default(Config())
    try:
        principal = Principal(authenticated=True, source="local")
        payload = ProviderSettingsPatch(
            llm_provider="nvidia",
            fallback_provider="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
            gemini_model="gemini-2.5-flash",
            openrouter_model="qwen/qwen3-8b",
            nvidia_model="custom/model",
            nvidia_api_key="nvapi-secret",
        )
        persist_provider_settings(payload, principal)
        assert app_config.get_config().nvidia_api_key == "nvapi-secret"
        assert json.loads(settings_path.read_text())["nvidia_model"] == "custom/model"
        assert "nvapi-secret" not in settings_path.read_text()
        assert "NVIDIA_API_KEY=nvapi-secret" in env_path.read_text()
        payload.nvidia_api_key = ""
        persist_provider_settings(payload, principal)
        assert app_config.get_config().nvidia_api_key == "nvapi-secret"
    finally:
        app_config.set_default(original)
