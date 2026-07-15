"""Application workflow for generating crawler configurations."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

from src.application import config as app_config
from src.application.common import check_cancel, emit
from src.application.errors import PersistenceError
from src.application.progress import ProgressEvent
from src.domain.language import detect_language_heuristic
from src.paths import CONFIG_DIR, RUNTIME_OUTPUT_ROOT
from src.services.configs import ConfigGenerator
from src.services.llm import get_llm
from src.utils.files import merge_json_locked

_DRAFT_TTL = timedelta(days=7)


@dataclass
class ConfigGenerationResult:
    draft_id: str
    suggested_name: str
    config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    expires_at: datetime | None = None


def generate_config(
    *,
    url: str,
    name: str | None = None,
    provider: str | None = None,
    use_browser: bool = False,
    headed: bool = False,
    no_cache: bool = False,
    ignore_sample: bool = False,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
    drafts_dir: Path | None = None,
) -> ConfigGenerationResult:
    """Generate a novel crawl config using AI and persist it as a draft."""
    if drafts_dir is not None:
        drafts_dir.mkdir(parents=True, exist_ok=True)
    if provider:
        from src.services.llm.factory import _create_provider

        llm = _create_provider(provider)
    else:
        llm = get_llm()

    effective_browser = use_browser or headed
    generator = ConfigGenerator(llm, use_browser=effective_browser, headed=headed)
    cache_dir = RUNTIME_OUTPUT_ROOT / ".gen-cache"
    check_cancel(cancel_event)
    emit(progress_callback, ProgressEvent(kind="phase", message="Generating config", extra={"url": url}))

    config_dict = generator.generate(
        url,
        name=name,
        translated_root=Path(app_config.get_config().translated_dir),
        samples_dir=CONFIG_DIR,
        cache_dir=cache_dir,
        use_cache=not no_cache,
        use_samples=not ignore_sample,
    )
    check_cancel(cancel_event)
    suggested_name = str(config_dict.get("name", "generated"))
    title = str(config_dict.pop("title", None) or suggested_name)
    detected_language = detect_language_heuristic(title)
    metadata = {
        "title": title,
        "localized": {},
        "localization_meta": {},
        "author": config_dict.pop("author", None),
        "source_url": config_dict.get("source_url") or url,
        "illustration_url": config_dict.pop("illustration_url", None),
        "summary": config_dict.pop("summary", None),
        "site_name": suggested_name,
        "source_language": detected_language if detected_language != "unknown" else None,
    }
    try:
        ConfigGenerator.validate(config_dict)
    except ValueError as error:
        emit(progress_callback, ProgressEvent(kind="log", message=f"Validation warning: {error}"))

    draft_id = ""
    expires = None
    if drafts_dir is not None:
        draft_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        expires = now + _DRAFT_TTL
        draft = {
            "draft_id": draft_id,
            "name": suggested_name,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "source_url": url,
            "config": config_dict,
            "metadata": metadata,
        }
        draft_path = drafts_dir / f"{draft_id}.json"
        draft_path.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return ConfigGenerationResult(
        draft_id=draft_id,
        suggested_name=suggested_name,
        config=config_dict,
        metadata=metadata,
        expires_at=expires,
    )


def save_generated_metadata(
    name: str,
    metadata: dict,
    *,
    translated_root: Path | None = None,
) -> Path:
    """Merge generated novel information into its canonical metadata file."""
    root = translated_root or Path(app_config.get_config().translated_dir)
    path = root / name / "metadata.json"

    def _merge(existing: dict) -> dict:
        localized = existing.get("localized")
        if not isinstance(localized, dict):
            localized = {}
        localization_meta = existing.get("localization_meta")
        if not isinstance(localization_meta, dict):
            localization_meta = {}
        return {
            **existing,
            "title": metadata.get("title") or existing.get("title") or name,
            "localized": localized,
            "localization_meta": localization_meta,
            "author": metadata.get("author") or existing.get("author"),
            "source_url": metadata.get("source_url") or existing.get("source_url"),
            "illustration_url": metadata.get("illustration_url") or existing.get("illustration_url"),
            "summary": metadata.get("summary") or existing.get("summary"),
            "site_name": metadata.get("site_name") or existing.get("site_name") or name,
            "source_language": existing.get("source_language") or metadata.get("source_language"),
        }

    merge_json_locked(path, _merge)
    return path


def save_generated_config(
    config: dict,
    *,
    metadata: dict | None = None,
    translated_root: Path | None = None,
) -> Path:
    """Persist a confirmed generated config and its extracted metadata."""
    try:
        root = translated_root or Path(app_config.get_config().translated_dir)
        path = ConfigGenerator.save(config, root)
        if metadata:
            save_generated_metadata(
                str(config.get("name", "generated")),
                metadata,
                translated_root=translated_root,
            )
        return path
    except (OSError, ValueError) as error:
        raise PersistenceError(str(error)) from error


__all__ = [
    "ConfigGenerationResult",
    "generate_config",
    "save_generated_config",
    "save_generated_metadata",
]
