"""Settings response, patch, and settings.json persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import fields
from pathlib import Path
from typing import Any

from src.api.schemas import SettingsResponse
from src.application import config as app_config
from src.application.errors import ApplicationValidationError
from src.config import SECRET_FIELDS, Config

SECRET_SETTING_KEYS = SECRET_FIELDS | {field_name.upper() for field_name in SECRET_FIELDS}


def build_settings_response() -> SettingsResponse:
    config = app_config.get_config()
    return SettingsResponse(
        translated_dir=config.translated_dir,
        target_language=config.target_language,
        llm_provider=config.llm_provider,
        fallback_provider=config.fallback_provider,
        chunk_mode=config.chunk_mode,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        review_threshold=config.review_threshold,
        max_retries=config.max_retries,
        translation_temperature=config.translation_temperature,
        translation_max_tokens=config.translation_max_tokens,
        gemini_api_key_configured=bool(config.gemini_api_key),
        openrouter_api_key_configured=bool(config.openrouter_api_key),
        telegram_enabled=config.telegram_enabled,
        telegram_configured=bool(config.telegram_bot_token and config.telegram_chat_id),
        telegram_api_base=config.telegram_api_base,
        telegram_parse_mode=config.telegram_parse_mode,
        telegram_silent=config.telegram_silent,
        telegram_timeout_seconds=config.telegram_timeout_seconds,
        ollama_base_url=config.ollama_base_url,
        ollama_model=config.ollama_model,
        gemini_model=config.gemini_model,
        openrouter_model=config.openrouter_model,
    )


def apply_settings_patch(patch: dict) -> SettingsResponse:
    try:
        app_config.apply_settings_patch(patch)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error
    return build_settings_response()


def config_to_settings_dict(
    config: Config,
    *,
    field_names: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return JSON-safe, non-secret values from *config*."""
    allowed = field_names if field_names is not None else {field.name for field in fields(Config)} - SECRET_FIELDS
    return {
        field.name: getattr(config, field.name)
        for field in fields(Config)
        if field.name in allowed and field.name not in SECRET_FIELDS
    }


def persist_config_to_settings(
    config: Config,
    path: Path,
    *,
    field_names: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Persist selected non-secret values and return changed field names."""
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to read settings file {path}: {error}") from error
        if not isinstance(raw, dict):
            raise ValueError(f"Settings file {path} must contain a JSON object.")
        existing = {key: value for key, value in raw.items() if key not in SECRET_SETTING_KEYS}

    new_values = config_to_settings_dict(config, field_names=field_names)
    changed = [key for key, value in new_values.items() if existing.get(key) != value]
    existing.update(new_values)
    content = json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
    return changed
