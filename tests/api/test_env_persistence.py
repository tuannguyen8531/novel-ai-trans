"""Tests for the .env persistence service."""

from __future__ import annotations

import re
from pathlib import Path

from src.api.services.env_persistence import (
    config_to_env_dict,
    persist_config_to_env,
)
from src.config import Config


def _write_env(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_config_to_env_dict_includes_nonempty_secrets():
    config = Config(
        gemini_api_key="sk-test",
        openrouter_api_key="sk-or-test",
        telegram_bot_token="bot-token",
        translation_temperature=0.42,
        chunk_size=2000,
    )
    env = config_to_env_dict(config)
    assert env["TRANSLATION_TEMPERATURE"] == "0.42"
    assert env["CHUNK_SIZE"] == "2000"
    # Non-empty secrets are persisted when the user has set them.
    assert env["GEMINI_API_KEY"] == "sk-test"
    assert env["OPENROUTER_API_KEY"] == "sk-or-test"
    assert env["TELEGRAM_BOT_TOKEN"] == "bot-token"


def test_config_to_env_dict_skips_empty_secrets():
    config = Config(translation_temperature=0.3)
    env = config_to_env_dict(config)
    for secret_env in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert secret_env not in env, f"{secret_env} should not be persisted when empty"


def test_persist_creates_file_when_missing(tmp_path: Path):
    config = Config(translation_temperature=0.7, target_language="en")
    env_path = tmp_path / ".env"
    written = persist_config_to_env(config, env_path)
    assert env_path.exists()
    content = _read(env_path)
    assert "TRANSLATION_TEMPERATURE=0.7" in content
    assert "TARGET_LANGUAGE=en" in content
    # All non-secret fields are written when the file is new; the returned
    # list captures every key the function emitted.
    assert "TARGET_LANGUAGE" in written
    assert "TRANSLATION_TEMPERATURE" in written
    assert len(written) >= 2
    # Empty secrets are not written.
    for secret_env in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN"):
        assert secret_env not in written


def test_persist_writes_nonempty_secrets(tmp_path: Path):
    config = Config(gemini_api_key="sk-persisted", openrouter_api_key="or-persisted")
    env_path = tmp_path / ".env"
    written = persist_config_to_env(config, env_path)
    content = _read(env_path)
    assert "GEMINI_API_KEY=sk-persisted" in content
    assert "OPENROUTER_API_KEY=or-persisted" in content
    assert "GEMINI_API_KEY" in written
    assert "OPENROUTER_API_KEY" in written


def test_persist_updates_existing_keys_preserves_comments(tmp_path: Path):
    env_path = tmp_path / ".env"
    _write_env(
        env_path,
        "# Top-level config\nTRANSLATED_DIR=translated\nTARGET_LANGUAGE=vi\n\n# Crawler section\nMAX_CHAPTERS=0\n",
    )
    config = Config(translated_dir="books", target_language="en", max_chapters=5)
    persist_config_to_env(config, env_path)

    content = _read(env_path)
    assert "# Top-level config" in content
    assert "# Crawler section" in content
    assert "TRANSLATED_DIR=books" in content
    assert "TARGET_LANGUAGE=en" in content
    assert "MAX_CHAPTERS=5" in content


def test_persist_preserves_secrets_in_existing_file(tmp_path: Path):
    env_path = tmp_path / ".env"
    _write_env(
        env_path,
        "GEMINI_API_KEY=sk-keep-me\n"
        "OPENROUTER_API_KEY=or-keep-me\n"
        "TELEGRAM_BOT_TOKEN=bot-keep-me\n"
        "TELEGRAM_CHAT_ID=12345\n"
        "TRANSLATION_TEMPERATURE=0.3\n",
    )
    config = Config(translation_temperature=0.5)
    persist_config_to_env(config, env_path)
    content = _read(env_path)
    assert "GEMINI_API_KEY=sk-keep-me" in content
    assert "OPENROUTER_API_KEY=or-keep-me" in content
    assert "TELEGRAM_BOT_TOKEN=bot-keep-me" in content
    assert "TELEGRAM_CHAT_ID=12345" in content
    assert "TRANSLATION_TEMPERATURE=0.5" in content


def test_persist_writes_atomically(tmp_path: Path):
    """The temp file is cleaned up on success or failure."""
    env_path = tmp_path / ".env"
    config = Config(translation_temperature=0.6)
    persist_config_to_env(config, env_path)
    leftovers = list(tmp_path.glob(".*.tmp"))
    assert not leftovers
    # The final file is the real .env, not a leftover temp.
    assert env_path.exists()
    assert env_path.read_text(encoding="utf-8").startswith("TRANSLATED_DIR=")


def test_persist_quotes_values_with_special_characters(tmp_path: Path):
    config = Config(translated_dir='path with spaces and "quotes"')
    env_path = tmp_path / ".env"
    persist_config_to_env(config, env_path)
    content = _read(env_path)
    # The special characters must survive a roundtrip through the writer.
    match = re.search(r"^TRANSLATED_DIR=(.+)$", content, re.MULTILINE)
    assert match is not None
    assert match.group(1).startswith('"') and match.group(1).endswith('"')
    assert "quotes" in content
    # Round-trip parsing recovers the value (escape handling).
    round_tripped = Config(translated_dir=match.group(1)[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
    assert round_tripped.translated_dir == config.translated_dir
