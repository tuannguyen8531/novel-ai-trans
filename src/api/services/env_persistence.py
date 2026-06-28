"""Persist the current in-process config back to ``.env``.

Only non-secret fields are written — provider API keys and Telegram tokens
are intentionally left untouched in the file even if their default values
are empty in memory. Writes are atomic (write to tmp file + ``os.replace``)
so a crash mid-write can't corrupt the env file.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from src.config import Config

# Fields that are never written back to .env (provider keys, telegram tokens).
# The plan explicitly excluded these from browser-driven .env edits.
SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "gemini_api_key",
        "openrouter_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
    }
)

# Mapping from Config attribute to the .env variable name. Keep in sync with
# ``Config.from_env`` in src/config.py.
_FIELD_TO_ENV: dict[str, str] = {
    "translated_dir": "TRANSLATED_DIR",
    "max_chapters": "MAX_CHAPTERS",
    "use_browser": "USE_BROWSER",
    "llm_provider": "LLM_PROVIDER",
    "fallback_provider": "FALLBACK_PROVIDER",
    "llm_temperature": "LLM_TEMPERATURE",
    "llm_max_tokens": "LLM_MAX_TOKENS",
    "translation_temperature": "TRANSLATION_TEMPERATURE",
    "translation_max_tokens": "TRANSLATION_MAX_TOKENS",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "ollama_model": "OLLAMA_MODEL",
    "gemini_api_key": "GEMINI_API_KEY",
    "gemini_model": "GEMINI_MODEL",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openrouter_model": "OPENROUTER_MODEL",
    "target_language": "TARGET_LANGUAGE",
    "chunk_size": "CHUNK_SIZE",
    "chunk_overlap": "CHUNK_OVERLAP",
    "review_threshold": "REVIEW_THRESHOLD",
    "max_retries": "MAX_RETRIES",
    "enable_review": "ENABLE_REVIEW",
    "enable_summary": "ENABLE_SUMMARY",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "telegram_api_base": "TELEGRAM_API_BASE",
    "telegram_parse_mode": "TELEGRAM_PARSE_MODE",
    "telegram_disable_notification": "TELEGRAM_DISABLE_NOTIFICATION",
    "telegram_timeout_seconds": "TELEGRAM_TIMEOUT_SECONDS",
}


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def config_to_env_dict(config: Config) -> dict[str, str]:
    """Return *config*'s fields as env-var entries.

    Non-secret fields are always written. Secret fields (API keys, Telegram
    tokens) are only included when the user has set a non-empty value
    in-memory; empty secrets are skipped so a freshly-cleared field is
    not written as an empty line.
    """
    env: dict[str, str] = {}
    for field_name, env_name in _FIELD_TO_ENV.items():
        value = getattr(config, field_name)
        if field_name in SECRET_FIELD_NAMES and not value:
            continue
        env[env_name] = _format_value(value)
    return env


_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _parse_existing_env(path: Path) -> tuple[list[tuple[str, str, str]], dict[str, str]]:
    """Return (lines, key->value_map) of an existing .env file.

    Preserves comments and blank lines so the rewrite keeps the same shape.
    Unknown keys are kept in the line list verbatim.
    """
    lines: list[tuple[str, str, str]] = []  # (kind, key, raw_value_or_line)
    parsed: dict[str, str] = {}
    if not path.exists():
        return lines, parsed
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(("raw", "", raw))
            continue
        match = _LINE_RE.match(raw)
        if not match:
            lines.append(("raw", "", raw))
            continue
        key, value = match.group(1), match.group(2)
        # Strip optional surrounding quotes.
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        lines.append(("kv", key, value))
        parsed[key] = value
    return lines, parsed


def _format_env_line(key: str, value: str) -> str:
    if value == "" or re.search(r"\s|[#\"']", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def _format_env_content(entries: Iterable[tuple[str, str, str]]) -> str:
    rendered: list[str] = []
    for kind, key, value in entries:
        if kind == "raw":
            rendered.append(value)
        else:
            rendered.append(_format_env_line(key, value))
    return "\n".join(rendered) + "\n"


def persist_config_to_env(config: Config, path: Path) -> list[str]:
    """Write *config*'s non-secret fields to *path*. Return the keys that
    changed (newly added or updated in place).

    Preserves comments, blank lines, and the relative order of unrelated
    keys already in the file. Secrets in ``SECRET_FIELD_NAMES`` are never
    written, but their existing values are preserved on disk.
    """
    lines, parsed = _parse_existing_env(path)
    new_values = config_to_env_dict(config)

    changed: list[str] = []
    # Apply the updates in place while preserving line order.
    for index, (kind, key, _) in enumerate(lines):
        if kind != "kv" or key not in new_values:
            continue
        lines[index] = ("kv", key, new_values[key])
        changed.append(key)
    for env_name, value in new_values.items():
        if env_name in parsed:
            continue
        lines.append(("kv", env_name, value))
        changed.append(env_name)

    content = _format_env_content(lines)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return changed


__all__ = [
    "SECRET_FIELD_NAMES",
    "config_to_env_dict",
    "persist_config_to_env",
]
