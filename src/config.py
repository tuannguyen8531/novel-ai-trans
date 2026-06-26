"""
Unified configuration for Novel AI Trans (crawler + translator).

Loads settings from .env file. Merges:
- Crawler settings: max_chapters, use_browser, share_dir (now translated_dir)
- Translator settings: target_language, chunk_size, review_threshold, etc.
- LLM provider settings: ollama, gemini, openrouter (+ optional fallback)
- SiteConfig dataclass for per-site crawler configuration
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(interpolate=True)


DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


@dataclass
class Config:
    """Application-level configuration from environment."""

    # --- Paths ---
    # Translator: directory holding per-novel {input,output,glossary,...}.
    # Crawler: same directory; crawler writes novel input/ here.
    translated_dir: str = "translated"

    # --- Crawler settings ---
    max_chapters: int = 0  # 0 = no limit
    use_browser: bool = False

    # --- LLM Provider ---
    # Crawler uses llm_temperature/llm_max_tokens; translator uses translation_*.
    # We keep both names; translator uses the translated aliases.
    llm_provider: str = "ollama"
    fallback_provider: str = ""  # Empty = no fallback
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    translation_temperature: float = 0.3
    translation_max_tokens: int = 4096

    # --- Provider settings ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-8b"

    # --- Translator settings ---
    target_language: str = "vi"
    chunk_size: int = 1500
    chunk_overlap: int = 100
    review_threshold: float = 0.7
    max_retries: int = 2
    enable_review: bool = False
    enable_summary: bool = False

    # --- Telegram notifications ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    telegram_parse_mode: str = "HTML"
    telegram_disable_notification: bool = False
    telegram_timeout_seconds: float = 10.0

    @property
    def translated_path(self) -> Path:
        return Path(self.translated_dir).expanduser()

    @property
    def telegram_enabled(self) -> bool:
        """Telegram notifications are on only when both token and chat_id are set."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.translation_temperature <= 1.0:
            raise ValueError(f"translation_temperature must be 0-1, got {self.translation_temperature}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap ({self.chunk_overlap}) must be less than chunk_size ({self.chunk_size})")
        if not 0.0 <= self.review_threshold <= 1.0:
            raise ValueError(f"review_threshold must be 0-1, got {self.review_threshold}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.translation_max_tokens < 1:
            raise ValueError(f"translation_max_tokens must be >= 1, got {self.translation_max_tokens}")
        if self.target_language not in ("vi", "en"):
            raise ValueError(f"target_language must be one of: vi, en; got {self.target_language}")
        if self.telegram_parse_mode not in ("", "HTML"):
            raise ValueError(f"telegram_parse_mode must be one of: '', 'HTML'; got {self.telegram_parse_mode!r}")
        if self.telegram_timeout_seconds <= 0:
            raise ValueError(f"telegram_timeout_seconds must be > 0, got {self.telegram_timeout_seconds}")
        if not self.telegram_api_base:
            raise ValueError("telegram_api_base must not be empty")

    @classmethod
    def from_env(cls) -> Config:
        def _bool(name: str, default: str = "false") -> bool:
            return (os.getenv(name, default) or default).lower() in ("true", "1", "yes")

        return cls(
            translated_dir=os.getenv("TRANSLATED_DIR", "translated"),
            max_chapters=int(os.getenv("MAX_CHAPTERS") or "0"),
            use_browser=_bool("USE_BROWSER", "false"),
            llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
            fallback_provider=os.getenv("FALLBACK_PROVIDER", ""),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE") or "0.0"),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS") or "4096"),
            translation_temperature=float(os.getenv("TRANSLATION_TEMPERATURE") or "0.3"),
            translation_max_tokens=int(os.getenv("TRANSLATION_MAX_TOKENS") or "4096"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "qwen/qwen3-8b"),
            target_language=os.getenv("TARGET_LANGUAGE", "vi").lower(),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1500")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
            review_threshold=float(os.getenv("REVIEW_THRESHOLD", "0.7")),
            max_retries=int(os.getenv("MAX_RETRIES", "2")),
            enable_review=_bool("ENABLE_REVIEW", "false"),
            enable_summary=_bool("ENABLE_SUMMARY", "false"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            telegram_api_base=os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org"),
            telegram_parse_mode=os.getenv("TELEGRAM_PARSE_MODE", "HTML"),
            telegram_disable_notification=_bool("TELEGRAM_DISABLE_NOTIFICATION", "false"),
            telegram_timeout_seconds=float(os.getenv("TELEGRAM_TIMEOUT_SECONDS") or "10.0"),
        )


config = Config.from_env()


@dataclass(frozen=True)
class SiteConfig:
    """Per-site configuration from JSON file (crawler only)."""

    name: str
    start_url: str
    chapter_link_selector: str
    chapter_content_selector: str
    version: int = 1
    novel_title_selector: str | None = None
    author_selector: str | None = None
    illustration_selector: str | None = None
    toc_next_selector: str | None = None
    toc_expand_selector: str | None = None
    chapter_title_selector: str | None = None
    remove_selectors: tuple[str, ...] = ()
    same_domain: bool = True
    reverse_chapter_order: bool = False
    filter_non_chapter_links: bool = True
    request_delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 2.0
    max_toc_pages: int = 50
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_file(cls, path: Any) -> SiteConfig:
        with Path(path).open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        if not isinstance(data, dict):
            raise ValueError("Config file must contain a JSON object.")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteConfig:
        data = cls._migrate(data)

        required = [
            "name",
            "start_url",
            "chapter_link_selector",
            "chapter_content_selector",
        ]
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"Missing required config fields: {', '.join(missing)}")

        remove_selectors = data.get("remove_selectors", ())
        if isinstance(remove_selectors, str):
            remove_selectors = [remove_selectors]
        if not isinstance(remove_selectors, (list, tuple)):
            raise ValueError("remove_selectors must be a list of CSS selectors.")

        return cls(
            name=str(data["name"]),
            start_url=str(data["start_url"]),
            chapter_link_selector=str(data["chapter_link_selector"]),
            chapter_content_selector=str(data["chapter_content_selector"]),
            version=int(data.get("version", 1)),
            novel_title_selector=_optional_str(data.get("novel_title_selector")),
            author_selector=_optional_str(data.get("author_selector")),
            illustration_selector=_optional_str(data.get("illustration_selector")),
            toc_next_selector=_optional_str(data.get("toc_next_selector")),
            toc_expand_selector=_optional_str(data.get("toc_expand_selector")),
            chapter_title_selector=_optional_str(data.get("chapter_title_selector")),
            remove_selectors=tuple(str(selector) for selector in remove_selectors),
            same_domain=bool(data.get("same_domain", True)),
            reverse_chapter_order=bool(data.get("reverse_chapter_order", False)),
            filter_non_chapter_links=bool(data.get("filter_non_chapter_links", True)),
            request_delay_seconds=float(data.get("request_delay_seconds", 1.0)),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
            retry_attempts=int(data.get("retry_attempts", 3)),
            retry_backoff_seconds=float(data.get("retry_backoff_seconds", 2.0)),
            max_toc_pages=int(data.get("max_toc_pages", 50)),
            user_agent=str(data.get("user_agent", DEFAULT_USER_AGENT)),
        )

    @staticmethod
    def _migrate(data: dict[str, Any]) -> dict[str, Any]:
        """Migrate older config schemas to the current version."""
        version_val = data.get("version", 1)
        try:
            version = int(version_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid config version: {version_val}") from e

        if version < 1:
            data["version"] = 1
        elif version > 1:
            raise ValueError(f"Unsupported future config version: {version}. Current schema version is 1.")
        return data


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
