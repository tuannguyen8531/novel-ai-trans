"""Tests for configuration: unified Config + per-site SiteConfig."""

import os
from unittest.mock import patch

import pytest

from src.config import Config, SiteConfig


class TestConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config()
            assert config.llm_provider == "ollama"
            assert config.ollama_model == "qwen3:8b"
            assert config.translation_temperature == 0.3
            assert config.target_language == "vi"
            assert config.chunk_size == 1500
            assert config.enable_review is False
            assert config.enable_summary is False
            assert config.telegram_enabled is False

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            cfg = Config.from_env()
            assert cfg.translated_dir == "translated"
            assert cfg.max_chapters == 0

    def test_from_env_reads_env_vars(self):
        env = {
            "LLM_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
            "CHUNK_SIZE": "2000",
            "TARGET_LANGUAGE": "en",
            "ENABLE_REVIEW": "true",
            "ENABLE_SUMMARY": "true",
            "TELEGRAM_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=True), patch("src.config.load_dotenv"):
            config = Config.from_env()
            assert config.llm_provider == "gemini"
            assert config.gemini_api_key == "test-key"
            assert config.target_language == "en"
            assert config.chunk_size == 2000
            assert config.enable_review is True
            assert config.enable_summary is True
            assert config.telegram_enabled is True

    def test_from_env_reads_crawler_settings(self):
        with (
            patch.dict(
                os.environ,
                {
                    "TRANSLATED_DIR": "/custom/translated",
                    "MAX_CHAPTERS": "50",
                },
                clear=True,
            ),
            patch("src.config.load_dotenv"),
        ):
            cfg = Config.from_env()
            assert cfg.translated_dir == "/custom/translated"
            assert cfg.max_chapters == 50

    def test_translated_path_expands_user(self):
        with (
            patch.dict(
                os.environ,
                {
                    "TRANSLATED_DIR": "~/translated",
                },
                clear=True,
            ),
            patch("src.config.load_dotenv"),
        ):
            cfg = Config.from_env()
            assert str(cfg.translated_path).startswith("/")

    def test_enable_review_variants(self):
        variants_true = ["true", "True", "TRUE", "1", "yes", "YES"]
        variants_false = ["false", "False", "0", "no", "NO", ""]

        with patch("src.config.load_dotenv"):
            for val in variants_true:
                with patch.dict(os.environ, {"ENABLE_REVIEW": val}, clear=True):
                    assert Config.from_env().enable_review is True, f"Failed for {val}"

            for val in variants_false:
                with patch.dict(os.environ, {"ENABLE_REVIEW": val}, clear=True):
                    assert Config.from_env().enable_review is False, f"Failed for {val}"

    def test_enable_summary_default(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config()
            assert config.enable_summary is False

    def test_enable_summary_from_env(self):
        with (
            patch.dict(os.environ, {"ENABLE_SUMMARY": "true"}, clear=True),
            patch("src.config.load_dotenv"),
        ):
            assert Config.from_env().enable_summary is True

    def test_fallback_provider_default(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            config = Config()
            assert config.fallback_provider == ""

    def test_fallback_provider_from_env(self):
        with (
            patch.dict(os.environ, {"FALLBACK_PROVIDER": "gemini"}, clear=True),
            patch("src.config.load_dotenv"),
        ):
            assert Config.from_env().fallback_provider == "gemini"


class TestSiteConfig:
    def test_from_dict(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "start_url": "https://example.com",
                "chapter_link_selector": ".chapters a",
                "chapter_content_selector": ".content",
            }
        )
        assert config.name == "test"
        assert config.request_delay_seconds == 1.0
        assert config.filter_non_chapter_links is True
        assert config.toc_expand_selector is None

    def test_from_dict_accepts_toc_expand_selector(self):
        config = SiteConfig.from_dict(
            {
                "name": "test",
                "start_url": "https://example.com",
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
                "start_url": "https://example.com",
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
                "start_url": "https://example.com",
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
                "start_url": "https://example.com",
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
                    "start_url": "url",
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
                    "start_url": "url",
                    "chapter_link_selector": "a",
                    "chapter_content_selector": "div",
                    "version": 999,
                }
            )
