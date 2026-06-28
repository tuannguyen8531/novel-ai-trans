"""Application-layer crawl, config generation, validation, and import workflows."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

from src.application import config_context
from src.application.errors import (
    ApplicationValidationError,
    ExternalServiceError,
    OperationCancelledError,
    PersistenceError,
    ResourceNotFoundError,
)
from src.application.paths import CONFIG_DIR, RUNTIME_OUTPUT_ROOT
from src.application.progress import ProgressEvent
from src.config import SiteConfig
from src.services.config_generator import ConfigGenerator
from src.services.crawler import ConsecutiveFailureError, NovelCrawler
from src.services.epub_importer import EpubImportError, import_epub
from src.services.http import FetchError
from src.services.llm import get_llm

_DRAFT_TTL = timedelta(days=7)
_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


# ---------------------------------------------------------------------------
# Crawl workflow
# ---------------------------------------------------------------------------


@dataclass
class CrawlRequest:
    target: str
    translated_output: Path | None = None
    max_chapters: int | None = None
    fail_fast: bool = False
    ignore_robots: bool = False
    overwrite: bool = False
    use_browser: bool | None = None
    workers: int = 1


@dataclass
class CrawlResult:
    novel: str
    title: str
    fetched: int
    skipped: int
    failed: int
    output_dir: str
    chapter_output_dir: str
    started_at: float
    finished_at: float
    cancelled: bool = False


def _emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001
            pass


def _check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise OperationCancelledError("Crawl cancelled.")


def _resolve_config_path(target: str) -> Path:
    path = Path(target)
    if path.is_file():
        return path
    candidates = []
    if path.suffix == ".json":
        candidates.append(CONFIG_DIR / path)
    else:
        candidates.append(CONFIG_DIR / f"{target}.json")
        candidates.append(CONFIG_DIR / target / "config.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    checked = ", ".join(str(c) for c in candidates)
    raise ResourceNotFoundError(f"Config not found for {target!r}. Checked: {checked}")


def run_crawl(
    request: CrawlRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> CrawlResult:
    """Run the crawler with cooperative cancellation."""
    config = config_context.get_config()
    started_at = time.time()
    config_path = _resolve_config_path(request.target)
    site_config = SiteConfig.from_file(config_path)
    use_browser = request.use_browser if request.use_browser is not None else config.use_browser
    workers = request.workers or 1
    if workers < 1:
        raise ApplicationValidationError("Number of workers must be at least 1.")
    max_chapters = request.max_chapters
    if max_chapters == 0:
        max_chapters = None
    elif max_chapters is None and config.max_chapters > 0:
        max_chapters = config.max_chapters
    share_root = request.translated_output or (Path(config.translated_dir) if config.translated_dir else None)

    _emit(
        progress_callback,
        ProgressEvent(
            kind="phase",
            novel=site_config.name,
            message=f"Crawling {site_config.name}",
            extra={"config": str(config_path), "browser": use_browser},
        ),
    )

    if use_browser:
        from src.services.browser import BrowserFetcher

        fetcher = BrowserFetcher(
            user_agent=site_config.user_agent,
            timeout_seconds=site_config.timeout_seconds,
            delay_seconds=site_config.request_delay_seconds,
            retry_attempts=site_config.retry_attempts,
            retry_backoff_seconds=site_config.retry_backoff_seconds,
            max_concurrency=workers,
        )
        crawler = NovelCrawler(
            site_config,
            respect_robots=not request.ignore_robots,
            fetcher=fetcher,
        )
    else:
        fetcher = None
        crawler = NovelCrawler(
            site_config,
            respect_robots=not request.ignore_robots,
        )

    def _crawl_progress(event) -> None:
        from src.services.crawler import CrawlProgress as _CP

        if not isinstance(event, _CP):
            return
        
        _emit(
            progress_callback,
            ProgressEvent(
                kind="chapter",
                novel=site_config.name,
                current=event.current,
                total=event.total,
                message=event.title,
                extra={
                    "status": event.status,
                    "title": event.title,
                    "url": event.source_url,
                    "path": event.path,
                    "error": event.error,
                },
            ),
        )

    try:
        result = crawler.crawl(
            RUNTIME_OUTPUT_ROOT,
            max_chapters=max_chapters,
            fail_fast=request.fail_fast,
            overwrite=request.overwrite,
            share_root=share_root,
            progress_callback=_crawl_progress,
            workers=workers,
            cancel_event=cancel_event,
        )
    except ConsecutiveFailureError as error:
        raise ExternalServiceError(str(error)) from error
    except (FetchError, OSError, ValueError) as error:
        raise ApplicationValidationError(str(error)) from error
    finally:
        if fetcher is not None:
            fetcher.close(suppress_errors=True)

    skipped = sum(1 for ch in result.chapters if ch.skipped)
    fetched = len(result.chapters) - skipped
    failed = len(result.errors)
    cancelled = result.cancelled
    _emit(
        progress_callback,
        ProgressEvent(
            kind="cancelled" if cancelled else "completed",
            novel=site_config.name,
            current=fetched,
            total=fetched + failed + skipped,
            message=f"Fetched {fetched}, skipped {skipped}, failed {failed}",
        ),
    )
    return CrawlResult(
        novel=site_config.name,
        title=result.metadata.title,
        fetched=fetched,
        skipped=skipped,
        failed=failed,
        output_dir=result.output_dir,
        chapter_output_dir=result.chapter_output_dir,
        started_at=started_at,
        finished_at=time.time(),
        cancelled=cancelled,
    )


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


@dataclass
class ConfigGenerationRequest:
    url: str
    name: str | None = None
    provider: str | None = None
    use_browser: bool = False
    no_cache: bool = False
    ignore_sample: bool = False


@dataclass
class ConfigGenerationResult:
    draft_id: str
    suggested_name: str
    config: dict = field(default_factory=dict)
    expires_at: datetime | None = None


def generate_config(
    *,
    url: str,
    name: str | None = None,
    provider: str | None = None,
    use_browser: bool = False,
    no_cache: bool = False,
    ignore_sample: bool = False,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
    drafts_dir: Path,
) -> ConfigGenerationResult:
    """Generate a site config using AI and persist it as a draft."""
    drafts_dir.mkdir(parents=True, exist_ok=True)
    if provider:
        from src.services.llm.factory import _create_provider

        llm = _create_provider(provider)
    else:
        llm = get_llm()

    generator = ConfigGenerator(llm, use_browser=use_browser)
    cache_dir = None if no_cache else RUNTIME_OUTPUT_ROOT / ".gen-cache"
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", message="Generating config", extra={"url": url}))

    config_dict = generator.generate(
        url,
        name=name,
        cache_dir=cache_dir,
        use_samples=not ignore_sample,
    )
    _check_cancel(cancel_event)
    try:
        ConfigGenerator.validate(config_dict)
    except ValueError as error:
        _emit(progress_callback, ProgressEvent(kind="log", message=f"Validation warning: {error}"))

    draft_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    expires = now + _DRAFT_TTL
    suggested_name = str(config_dict.get("name", "generated"))
    draft = {
        "draft_id": draft_id,
        "name": suggested_name,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "source_url": url,
        "config": config_dict,
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
        expires_at=expires,
    )


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


@dataclass
class ConfigIssue:
    label: str
    selector: str | None
    matches: int
    status: str  # "ok" | "fail" | "skipped"


@dataclass
class ConfigValidationResult:
    ok: bool
    target: str
    issues: list[ConfigIssue] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    chapter_count: int = 0


def validate_config(
    *,
    target: str,
    use_browser: bool | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> ConfigValidationResult:
    """Test selectors from a config against live HTML."""

    config = config_context.get_config()
    config_path = _resolve_config_path(target)
    site_config = SiteConfig.from_file(config_path)
    use_browser = use_browser if use_browser is not None else config.use_browser
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", message=f"Validating {site_config.name}"))

    if use_browser:
        from src.services.browser import BrowserFetcher

        fetcher = BrowserFetcher(
            user_agent=site_config.user_agent,
            timeout_seconds=site_config.timeout_seconds,
            delay_seconds=site_config.request_delay_seconds,
        )
        fetcher.__enter__()
        try:
            return _validate_with_fetcher(site_config, fetcher, cancel_event, progress_callback)
        finally:
            fetcher.__exit__(None, None, None)
    else:
        from src.services.http import HttpClient

        fetcher = HttpClient(
            user_agent=site_config.user_agent,
            timeout_seconds=site_config.timeout_seconds,
            delay_seconds=site_config.request_delay_seconds,
            respect_robots=False,
        )
        return _validate_with_fetcher(site_config, fetcher, cancel_event, progress_callback)


def _validate_with_fetcher(site_config, fetcher, cancel_event, progress_callback) -> ConfigValidationResult:
    from bs4 import BeautifulSoup

    issues: list[ConfigIssue] = []
    metadata: dict = {}
    chapter_count = 0
    ok = True

    if site_config.toc_expand_selector:
        if not hasattr(fetcher, "fetch_with_clicks"):
            raise ApplicationValidationError("toc_expand_selector requires browser mode.")
        response = fetcher.fetch_with_clicks(
            site_config.start_url,
            [site_config.toc_expand_selector],
            wait_for_selector=site_config.chapter_link_selector,
        )
    else:
        response = fetcher.fetch(site_config.start_url)
    toc_soup = BeautifulSoup(response.body, "html.parser")
    _check_cancel(cancel_event)
    for label, selector in [
        ("novel_title_selector", site_config.novel_title_selector),
        ("author_selector", site_config.author_selector),
        ("chapter_link_selector", site_config.chapter_link_selector),
        ("toc_next_selector", site_config.toc_next_selector),
        ("toc_expand_selector", site_config.toc_expand_selector),
    ]:
        if not selector:
            issues.append(ConfigIssue(label=label, selector=None, matches=0, status="skipped"))
            continue
        matches = len(toc_soup.select(selector))
        status = "ok" if matches > 0 else "fail"
        if status == "fail":
            ok = False
        issues.append(ConfigIssue(label=label, selector=selector, matches=matches, status=status))

    crawler = NovelCrawler(site_config, fetcher=fetcher)
    discovered_meta, chapters = crawler.discover_chapters()
    metadata = {
        "title": discovered_meta.title,
        "author": discovered_meta.author,
    }
    chapter_count = len(chapters)
    _check_cancel(cancel_event)

    if chapters:
        first = chapters[0]
        _check_cancel(cancel_event)
        ch_html = fetcher.fetch(first.url).body
        ch_soup = BeautifulSoup(ch_html, "html.parser")
        for label, selector in [
            ("chapter_title_selector", site_config.chapter_title_selector),
            ("chapter_content_selector", site_config.chapter_content_selector),
        ]:
            if not selector:
                issues.append(ConfigIssue(label=label, selector=None, matches=0, status="skipped"))
                continue
            matches = len(ch_soup.select(selector))
            status = "ok" if matches > 0 else "fail"
            if status == "fail":
                ok = False
            issues.append(ConfigIssue(label=label, selector=selector, matches=matches, status=status))
        for sel in site_config.remove_selectors:
            matches = len(ch_soup.select(sel))
            status = "ok" if matches > 0 else "warn"
            issues.append(ConfigIssue(label="remove_selectors", selector=sel, matches=matches, status=status))

    return ConfigValidationResult(
        ok=ok,
        target=site_config.name,
        issues=issues,
        metadata=metadata,
        chapter_count=chapter_count,
    )


# ---------------------------------------------------------------------------
# EPUB import
# ---------------------------------------------------------------------------


@dataclass
class ImportRequest:
    epub_path: Path
    name: str | None = None
    translated_output: Path | None = None
    keep_existing: bool = False


@dataclass
class ImportResult:
    novel: str
    title: str
    chapters: int
    illustrations: int
    output_dir: str
    warnings: list[str] = field(default_factory=list)


def import_epub_workflow(
    request: ImportRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> ImportResult:
    config = config_context.get_config()
    share_root = request.translated_output or (Path(config.translated_dir) if config.translated_dir else None)
    if share_root is None:
        share_root = Path("translated")
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", message=f"Importing {request.epub_path.name}"))
    try:
        result = import_epub(
            request.epub_path,
            share_root,
            name=request.name,
            keep_existing=request.keep_existing,
        )
    except EpubImportError as error:
        raise ApplicationValidationError(str(error)) from error
    except (OSError, ValueError) as error:
        raise PersistenceError(str(error)) from error
    _check_cancel(cancel_event)
    return ImportResult(
        novel=Path(result.output_dir).name,
        title=result.metadata.title,
        chapters=len(result.chapters),
        illustrations=len(result.illustrations),
        output_dir=result.output_dir,
        warnings=list(result.warnings),
    )


# ---------------------------------------------------------------------------
# Helper to import ExternalServiceError if needed
# ---------------------------------------------------------------------------


__all__ = [
    "CrawlRequest",
    "CrawlResult",
    "run_crawl",
    "ConfigGenerationRequest",
    "ConfigGenerationResult",
    "generate_config",
    "ConfigIssue",
    "ConfigValidationResult",
    "validate_config",
    "ImportRequest",
    "ImportResult",
    "import_epub_workflow",
]
