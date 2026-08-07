"""
Unified configuration for Novel AI Trans (crawler + translator).

Loads settings from settings.json and .env file. Merges:
- Crawler settings: translated_dir
- Translator settings: target_language, chunk_size, review_threshold, etc.
- LLM provider settings: ollama, gemini, openrouter (+ optional fallback)
- SiteConfig dataclass for per-site crawler configuration
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values, load_dotenv

from src import paths
from src.utils.files import write_json_atomic

_ENVIRONMENT_BEFORE_DOTENV = frozenset(os.environ)
load_dotenv(interpolate=True)
_DOTENV_VALUES = dotenv_values()


DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "gemini_api_key",
        "openrouter_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
    }
)

ENV_FIELDS: dict[str, str] = {
    "translated_dir": "TRANSLATED_DIR",
    "log_retention_days": "LOG_RETENTION_DAYS",
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
    "chunk_mode": "CHUNK_MODE",
    "chunk_size": "CHUNK_SIZE",
    "chunk_overlap": "CHUNK_OVERLAP",
    "review_threshold": "REVIEW_THRESHOLD",
    "max_retries": "MAX_RETRIES",
    "telegram_enabled": "TELEGRAM_ENABLED",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "telegram_api_base": "TELEGRAM_API_BASE",
    "telegram_parse_mode": "TELEGRAM_PARSE_MODE",
    "telegram_silent": "TELEGRAM_SILENT",
    "telegram_timeout_seconds": "TELEGRAM_TIMEOUT_SECONDS",
}

# Application settings now live in runtime/settings.json. Keep dotenv loading
# for secrets and deployment variables, but remove legacy non-secret settings
# that python-dotenv injected into the process environment.
for _field_name, _env_name in ENV_FIELDS.items():
    if _field_name in SECRET_FIELDS or _env_name in _ENVIRONMENT_BEFORE_DOTENV:
        continue
    if _DOTENV_VALUES.get(_env_name) == os.environ.get(_env_name):
        os.environ.pop(_env_name, None)


def _read_settings(path: Path, allowed_fields: set[str]) -> dict[str, Any]:
    """Read non-secret settings from *path*, returning defaults for missing files."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read settings file {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Settings file {path} must contain a JSON object.")
    return {key: value for key, value in data.items() if key in allowed_fields}


@dataclass
class Config:
    """Application-level configuration from environment."""

    # --- Paths ---
    # Translator: directory holding per-novel {input,output,glossary,...}.
    # Crawler: same directory; crawler writes novel input/ here.
    translated_dir: str = "translated"
    log_retention_days: int = 30  # Number of most recent daily log folders to keep

    # --- LLM Provider ---
    # Translation/summary calls use translation_*; structured and analysis calls
    # (learning, crawler config, detection, review) use llm_*.
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
    chunk_mode: Literal["chars", "tokens"] = "chars"
    chunk_size: int = 1500
    chunk_overlap: int = 100
    review_threshold: float = 0.7
    max_retries: int = 2
    # --- Telegram notifications ---
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    telegram_parse_mode: str = "HTML"
    telegram_silent: bool = False
    telegram_timeout_seconds: float = 10.0

    @property
    def translated_path(self) -> Path:
        return Path(self.translated_dir).expanduser()

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not self.translated_dir or not self.translated_dir.strip():
            raise ValueError("TRANSLATED_DIR configuration must not be empty.")
        if self.log_retention_days < 1:
            raise ValueError(f"log_retention_days must be >= 1, got {self.log_retention_days}")
        if self.fallback_provider and self.fallback_provider == self.llm_provider:
            raise ValueError(f"fallback_provider ({self.fallback_provider}) must differ from llm_provider")
        if not 0.0 <= self.translation_temperature <= 1.0:
            raise ValueError(f"translation_temperature must be 0-1, got {self.translation_temperature}")
        if self.chunk_mode not in ("chars", "tokens"):
            raise ValueError(f"chunk_mode must be one of: chars, tokens; got {self.chunk_mode}")
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
    def ensure_settings_file(cls, settings_path: Path | None = None) -> Path:
        """Create the runtime settings file from code defaults when missing."""
        path = settings_path or paths.SETTINGS_PATH
        if not path.exists():
            defaults = cls()
            write_json_atomic(
                path,
                {field.name: getattr(defaults, field.name) for field in fields(cls) if field.name not in SECRET_FIELDS},
            )
        return path

    @classmethod
    def from_env(cls, settings_path: Path | None = None) -> Config:
        """Load JSON settings and apply environment overrides.

        JSON is the normal home for application settings. Environment values
        take precedence so Docker, CI, and existing installations continue to
        work. Secrets are deliberately excluded from the JSON layer.
        """
        settings_path = cls.ensure_settings_file(settings_path)
        defaults = cls()
        values = {field.name: getattr(defaults, field.name) for field in fields(cls)}
        values.update(_read_settings(settings_path, set(values) - SECRET_FIELDS))

        for field_name, env_name in ENV_FIELDS.items():
            raw = os.getenv(env_name)
            if raw is None:
                continue
            default = values[field_name]
            if isinstance(default, bool):
                values[field_name] = raw.lower() in ("true", "1", "yes")
            elif isinstance(default, int) and not isinstance(default, bool):
                values[field_name] = int(raw or str(default))
            elif isinstance(default, float):
                values[field_name] = float(raw or str(default))
            elif field_name in {"target_language", "chunk_mode"}:
                values[field_name] = raw.lower()
            else:
                values[field_name] = raw
        return cls(**values)

    def clone(self, **overrides: Any) -> Config:
        """Return a copy of this Config with the given field overrides applied.

        Uses dataclasses.replace so __post_init__ validation runs on the
        resulting instance. Any field that is None in overrides is treated
        as "no change" so callers can pass ``override=None`` to mean
        "keep the existing value".
        """
        clean: dict[str, Any] = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)


_INITIAL_CONFIG = Config.from_env()
_DEFAULT_CONFIG = _INITIAL_CONFIG
_CURRENT_CONFIG: ContextVar[Config | None] = ContextVar("novel_ai_trans_config", default=None)
_CONFIG_LOCK = threading.RLock()


def get_active_config() -> Config:
    """Return the current job snapshot or the process-wide default."""
    current = _CURRENT_CONFIG.get()
    if current is not None:
        return current
    with _CONFIG_LOCK:
        return _DEFAULT_CONFIG


def set_default_config(value: Config) -> None:
    """Replace defaults used by future contexts without changing active jobs."""
    global _DEFAULT_CONFIG
    with _CONFIG_LOCK:
        _DEFAULT_CONFIG = value


def reset_default_config() -> None:
    set_default_config(_INITIAL_CONFIG)


@contextmanager
def active_config_scope(snapshot: Config) -> Iterator[Config]:
    token = _CURRENT_CONFIG.set(snapshot)
    try:
        yield snapshot
    finally:
        _CURRENT_CONFIG.reset(token)


class _ConfigProxy:
    """Backward-compatible proxy resolving configuration at execution time.

    Existing graph, provider, glossary, notifier, and packaging modules import
    ``config`` directly. Keeping that public object as a proxy makes those
    imports context-aware without allowing a job snapshot to leak globally.
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(get_active_config(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(get_active_config(), name, value)

    def clone(self, **overrides: Any) -> Config:
        return get_active_config().clone(**overrides)


config = _ConfigProxy()


@dataclass(frozen=True)
class SiteConfig:
    """Per-site configuration from JSON file (crawler only)."""

    name: str
    toc_url: str
    chapter_link_selector: str
    chapter_content_selector: str
    version: int = 1
    source_url: str | None = None
    title: str | None = None
    author: str | None = None
    illustration_url: str | None = None
    summary: str | None = None
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
            "toc_url",
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
            toc_url=str(data["toc_url"]),
            chapter_link_selector=str(data["chapter_link_selector"]),
            chapter_content_selector=str(data["chapter_content_selector"]),
            version=int(data.get("version", 1)),
            source_url=_optional_str(data.get("source_url")),
            title=_optional_str(data.get("title")),
            author=_optional_str(data.get("author")),
            illustration_url=_optional_str(data.get("illustration_url")),
            summary=_optional_str(data.get("summary")),
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
