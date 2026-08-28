"""Tests for configuration: unified Config + per-site SiteConfig."""

import json
import os
from typing import Any, cast
from unittest.mock import patch

import pytest

from src.config import SECRET_FIELDS, Config, SiteConfig


class TestConfig:
    @pytest.fixture(autouse=True)
    def isolate_dotenv(self, monkeypatch):
        monkeypatch.setattr("src.config._DOTENV_VALUES", {})

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config()
            assert config.llm_provider == "ollama"
            assert config.ollama_model == "qwen3:8b"
            assert config.log_retention_days == 30
            assert config.translation_temperature == 0.3
            assert config.target_language == "vi"
            assert config.chunk_mode == "chars"
            assert config.chunk_size == 5000
            assert config.telegram_enabled is False

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            cfg = Config.from_env()
            assert cfg.translated_dir == "translated"

    def test_from_env_creates_default_settings_file(self, tmp_path):
        settings_path = tmp_path / "runtime" / "settings.json"
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            cfg = Config.from_env(settings_path)

        assert settings_path.exists()
        assert json.loads(settings_path.read_text(encoding="utf-8"))["target_language"] == "vi"
        assert cfg.target_language == "vi"

    def test_first_settings_file_is_seeded_from_environment_without_secrets(self, tmp_path):
        settings_path = tmp_path / "runtime" / "settings.json"
        env = {
            "TARGET_LANGUAGE": "en",
            "CHUNK_SIZE": "2200",
            "GEMINI_API_KEY": "secret-must-stay-out-of-json",
        }
        with patch.dict(os.environ, env, clear=True):
            Config.ensure_settings_file(settings_path)

        data = json.loads(settings_path.read_text(encoding="utf-8"))
        expected_fields = {field.name for field in Config.__dataclass_fields__.values()} - SECRET_FIELDS
        assert set(data) == expected_fields
        assert data["target_language"] == "en"
        assert data["chunk_size"] == 2200
        assert "gemini_api_key" not in data

    def test_first_settings_file_uses_dotenv_when_process_environment_is_missing(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("src.config._DOTENV_VALUES", {"TARGET_LANGUAGE": "en", "CHUNK_SIZE": "2200"}),
        ):
            Config.ensure_settings_file(settings_path)

        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data["target_language"] == "en"
        assert data["chunk_size"] == 2200

    def test_first_settings_file_uses_defaults_for_missing_environment_values(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        with (
            patch.dict(os.environ, {"TARGET_LANGUAGE": "en"}, clear=True),
            patch("src.config._DOTENV_VALUES", {}),
        ):
            Config.ensure_settings_file(settings_path)

        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data["target_language"] == "en"
        assert data["chunk_size"] == 5000

    def test_ensure_settings_file_does_not_overwrite_existing_file(self, tmp_path):
        settings_path = tmp_path / "runtime" / "settings.json"
        settings_path.parent.mkdir()
        settings_path.write_text('{"target_language": "vi"}\n', encoding="utf-8")

        with patch.dict(os.environ, {"TARGET_LANGUAGE": "en"}, clear=True):
            result = Config.ensure_settings_file(settings_path)

        assert result == settings_path
        assert json.loads(settings_path.read_text(encoding="utf-8")) == {"target_language": "vi"}

    def test_from_settings_file(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "llm_provider": "gemini",
                    "target_language": "en",
                    "chunk_size": 2200,
                    "gemini_api_key": "must-not-come-from-json",
                }
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config.from_env(settings_path)
        assert config.llm_provider == "gemini"
        assert config.target_language == "en"
        assert config.chunk_size == 2200
        assert config.gemini_api_key == ""

    def test_existing_settings_file_ignores_non_secret_environment_values(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            '{"target_language": "vi", "chunk_size": 2200, "translation_temperature": 0.5}',
            encoding="utf-8",
        )
        with (
            patch.dict(
                os.environ,
                {
                    "TARGET_LANGUAGE": "en",
                    "CHUNK_SIZE": "1800",
                    "TRANSLATION_TEMPERATURE": "0.9",
                },
                clear=True,
            ),
            patch("src.config.load_dotenv"),
        ):
            config = Config.from_env(settings_path)
        assert config.target_language == "vi"
        assert config.chunk_size == 2200
        assert config.translation_temperature == 0.5

    def test_existing_settings_file_still_reads_secrets_from_environment(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        settings_path.write_text('{"gemini_api_key": "must-not-come-from-json"}', encoding="utf-8")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-from-environment"}, clear=True):
            config = Config.from_env(settings_path)

        assert config.gemini_api_key == "secret-from-environment"

    def test_from_env_reads_env_vars(self, tmp_path):
        env = {
            "LLM_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
            "CHUNK_MODE": "tokens",
            "CHUNK_SIZE": "2000",
            "TARGET_LANGUAGE": "en",
            "TELEGRAM_ENABLED": "true",
            "LOG_RETENTION_DAYS": "14",
        }
        with patch.dict(os.environ, env, clear=True), patch("src.config.load_dotenv"):
            config = Config.from_env(tmp_path / "settings.json")
            assert config.llm_provider == "gemini"
            assert config.gemini_api_key == "test-key"
            assert config.target_language == "en"
            assert config.chunk_mode == "tokens"
            assert config.chunk_size == 2000
            assert config.telegram_enabled is True
            assert config.log_retention_days == 14

    def test_rejects_non_positive_log_retention(self):
        with pytest.raises(ValueError, match="log_retention_days"):
            Config(log_retention_days=0)

    def test_missing_settings_file_reads_crawler_settings_from_env(self, tmp_path):
        with (
            patch.dict(
                os.environ,
                {
                    "TRANSLATED_DIR": "/custom/translated",
                },
                clear=True,
            ),
            patch("src.config.load_dotenv"),
        ):
            cfg = Config.from_env(tmp_path / "settings.json")
            assert cfg.translated_dir == "/custom/translated"

    def test_translated_path_expands_user(self, tmp_path):
        env = {
            "TRANSLATED_DIR": "~/translated",
        }
        for k in ["USERPROFILE", "HOMEPATH", "HOMEDRIVE", "HOME"]:
            if k in os.environ:
                env[k] = os.environ[k]

        with (
            patch.dict(
                os.environ,
                env,
                clear=True,
            ),
            patch("src.config.load_dotenv"),
        ):
            cfg = Config.from_env(tmp_path / "settings.json")
            assert cfg.translated_path.is_absolute()

    def test_rejects_unknown_chunk_mode(self):
        with pytest.raises(ValueError, match="chunk_mode"):
            Config(chunk_mode=cast(Any, "bytes"))

    def test_fallback_provider_default(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config()
            assert config.fallback_provider == ""

    def test_missing_settings_file_reads_fallback_provider_from_env(self, tmp_path):
        with (
            patch.dict(os.environ, {"FALLBACK_PROVIDER": "gemini"}, clear=True),
            patch("src.config.load_dotenv"),
        ):
            assert Config.from_env(tmp_path / "settings.json").fallback_provider == "gemini"


class TestSiteConfig:
    def test_from_dict(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "toc_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
            }
        )
        assert config.name == "test"
        assert config.request_delay_seconds == 1.0
        assert config.filter_non_chapter_links is True
        assert config.toc_expand_selector is None

    def test_from_dict_rejects_removed_start_url(self):
        with pytest.raises(ValueError, match="Missing required config fields: toc_url"):
            SiteConfig.from_dict(
                {
                    "name": "test",
                    "start_url": "https://example.com",
                    "chapter_link_selector": ".chapters a",
                    "chapter_content_selector": ".content",
                }
            )

    def test_from_dict_accepts_toc_expand_selector(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "toc_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
                "toc_expand_selector": "text=Show all chapters",
            }
        )
        assert config.toc_expand_selector == "text=Show all chapters"

    def test_from_dict_accepts_illustration_selector(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "toc_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
                "illustration_selector": ".cover img",
            }
        )
        assert config.illustration_selector == ".cover img"

    def test_from_dict_single_remove_selector(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "toc_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
                "remove_selectors": "script",
            }
        )
        assert config.remove_selectors == ("script",)

    def test_can_disable_non_chapter_link_filtering(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "toc_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
                "filter_non_chapter_links": False,
            }
        )
        assert config.filter_non_chapter_links is False

    def test_config_migration_rejects_invalid_version(self):
        with pytest.raises(ValueError, match="Invalid config version"):
            SiteConfig.from_dict(
                {
                    "name": "demo",
                    "toc_url": "url",
                    "chapter_link_selector": "a",
                    "chapter_content_selector": "div",
                    "version": "invalid",
                }
            )

    def test_config_migration_rejects_future_version(self):
        with pytest.raises(ValueError, match="Unsupported future config version"):
            SiteConfig.from_dict(
                {
                    "name": "demo",
                    "toc_url": "url",
                    "chapter_link_selector": "a",
                    "chapter_content_selector": "div",
                    "version": 999,
                }
            )
