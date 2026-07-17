"""Workflow for generating crawler configurations."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.application import config as app_config
from src.application.crawl.common import check_cancel, emit
from src.application.errors import PersistenceError
from src.application.progress import ProgressEvent
from src.domain.language import detect_language_heuristic
from src.paths import CONFIG_DIR, RUNTIME_OUTPUT_ROOT
from src.services import documents
from src.services.generation import prompts
from src.services.generation.analysis import ConfigAnalyzer, clean_novel_html, normalize_novel_info
from src.services.generation.cache import HtmlCache
from src.services.generation.drafts import DraftRepository
from src.services.generation.fetching import PageAcquirer, is_error_page, open_acquirer
from src.services.generation.repository import ConfigRepository
from src.services.generation.samples import load_known_config, load_sample, prepare_sample
from src.services.generation.selectors import (
    SelectorResolution,
    build_config,
    derive_name,
    find_first_chapter,
    resolve_selectors,
)
from src.services.llm import get_llm
from src.utils.html import clean_html_for_analysis
from src.utils.logging import get_logger

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
    if provider:
        from src.services.llm.factory import _create_provider

        llm = _create_provider(provider)
    else:
        llm = get_llm()

    cache_dir = RUNTIME_OUTPUT_ROOT / ".gen-cache"
    check_cancel(cancel_event)
    emit(progress_callback, ProgressEvent(kind="phase", message="Generating config", extra={"url": url}))
    translated_root = Path(app_config.get_config().translated_dir)
    analyzer = ConfigAnalyzer(llm)
    cache = HtmlCache(cache_dir, enabled=not no_cache)
    with open_acquirer(cache, use_browser=use_browser, headed=headed) as acquirer:
        config_dict = _generate_config_data(
            url,
            analyzer=analyzer,
            acquirer=acquirer,
            translated_root=translated_root,
            samples_dir=CONFIG_DIR,
            name=name,
            use_samples=not ignore_sample,
            progress_callback=progress_callback,
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
        ConfigRepository(translated_root).validate(config_dict)
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
        DraftRepository(drafts_dir).save(draft)
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

    documents.update(path.parent, _merge)
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
        path = ConfigRepository(root).save(config)
        if metadata:
            save_generated_metadata(
                str(config.get("name", "generated")),
                metadata,
                translated_root=translated_root,
            )
        return path
    except (OSError, ValueError) as error:
        raise PersistenceError(str(error)) from error


def _generate_config_data(
    source_url: str,
    *,
    analyzer: ConfigAnalyzer,
    acquirer: PageAcquirer,
    translated_root: Path,
    samples_dir: Path,
    name: str | None,
    use_samples: bool,
    progress_callback: Callable[[ProgressEvent], None] | None,
) -> dict[str, Any]:
    """Coordinate the infrastructure collaborators for one generated config."""
    source_html = _fetch_page(acquirer, source_url, "Novel info", progress_callback)
    if source_html is None:
        raise RuntimeError(f"Failed to fetch novel information page: {source_url}")
    novel_info = normalize_novel_info(
        analyzer.ask(
            system=prompts.NOVEL_INFO,
            user=f"Page URL: {source_url}\n\nHTML:\n{clean_novel_html(source_html)}",
            call_type="gen_novel_info",
        ),
        source_url,
    )
    toc_url = str(novel_info["toc_url"])
    domain = urlparse(toc_url).netloc
    site_name = name or derive_name(source_url)

    if use_samples:
        sample = load_sample(domain, samples_dir)
        if sample is not None:
            _log(progress_callback, f"Using bundled sample template for domain {domain}.")
            return prepare_sample(
                sample,
                name=site_name,
                toc_url=toc_url,
                source_url=source_url,
                novel_info=novel_info,
            )

    known = load_known_config(domain, translated_root) if use_samples else None
    toc_html = _fetch_page(acquirer, toc_url, "TOC", progress_callback)
    if toc_html is None:
        raise RuntimeError(f"Failed to fetch TOC page: {toc_url}")
    if is_error_page(toc_html) and not toc_url.endswith("/"):
        alternative_url = toc_url.rstrip("/") + "/"
        _log(progress_callback, f"Page looks like a 404; retrying with: {alternative_url}")
        alternative_html = _fetch_page(acquirer, alternative_url, "TOC", progress_callback)
        if alternative_html is not None and not is_error_page(alternative_html):
            toc_html = alternative_html
            toc_url = alternative_url
        else:
            get_logger().warning("Alternative TOC URL is still an error page; using the original page")

    toc_soup = BeautifulSoup(toc_html, "html.parser")
    toc_resolution = resolve_selectors(
        analyzer,
        toc_soup,
        "toc",
        clean_html_for_analysis(toc_html),
        known,
    )
    _emit_selector_status(progress_callback, "toc", toc_resolution)
    chapter_url = find_first_chapter(
        toc_soup,
        toc_url,
        toc_resolution.selectors.get("chapter_link_selector"),
    )

    chapter_selectors: dict[str, Any] = {}
    if chapter_url:
        chapter_page = acquirer.fetch_chapter(chapter_url)
        if chapter_page is not None:
            source = "cache hit" if chapter_page.from_cache else "cache miss"
            _log(progress_callback, f"Chapter {source}: {chapter_url}")
        if chapter_page is not None and chapter_page.usable:
            chapter_html = chapter_page.body
            chapter_resolution = resolve_selectors(
                analyzer,
                BeautifulSoup(chapter_html, "html.parser"),
                "chapter",
                clean_html_for_analysis(chapter_html),
                known,
            )
            _emit_selector_status(progress_callback, "chapter", chapter_resolution)
            chapter_selectors = chapter_resolution.selectors
        else:
            get_logger().warning("Could not acquire usable chapter content; skipping chapter selector analysis")
    else:
        get_logger().warning("Could not find a chapter link; skipping chapter selector analysis")

    return build_config(
        toc_url,
        site_name,
        toc_resolution.selectors,
        chapter_selectors,
        source_url=source_url,
        novel_info=novel_info,
    )


def _fetch_page(
    acquirer: PageAcquirer,
    url: str,
    label: str,
    progress_callback: Callable[[ProgressEvent], None] | None,
) -> str | None:
    result = acquirer.fetch(url)
    if result is None:
        return None
    source = "cache hit" if result.from_cache else "cache miss"
    _log(progress_callback, f"{label} {source}: {url}")
    return result.body


def _emit_selector_status(
    progress_callback: Callable[[ProgressEvent], None] | None,
    phase: str,
    resolution: SelectorResolution,
) -> None:
    if resolution.used_known:
        _log(progress_callback, f"Reusing known {phase} selectors for this domain.")
    elif resolution.known_issues:
        _log(
            progress_callback,
            f"Known {phase} selectors stale ({', '.join(resolution.known_issues)}); using LLM analysis.",
        )
    if resolution.retried:
        if resolution.final_issues:
            _log(
                progress_callback,
                f"{phase.title()} selectors still have issues after retry: {', '.join(resolution.final_issues)}",
            )
        else:
            _log(progress_callback, f"Retried {phase} selector analysis after validation issues.")


def _log(
    progress_callback: Callable[[ProgressEvent], None] | None,
    message: str,
) -> None:
    emit(progress_callback, ProgressEvent(kind="log", message=message))


__all__ = [
    "ConfigGenerationResult",
    "generate_config",
    "save_generated_config",
    "save_generated_metadata",
]
