"""Workflow for crawling novels."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from urllib.parse import urlparse

from src.application import config as app_config
from src.application.crawl.common import emit, resolve_config_path
from src.application.errors import ApplicationValidationError, ExternalServiceError
from src.application.progress import ProgressEvent
from src.config import SiteConfig
from src.models import CrawlProgress
from src.paths import BROWSER_CACHE_DIR, MANIFEST_DIR
from src.services.crawling.crawler import NovelCrawler
from src.services.crawling.execution import ConsecutiveFailureError
from src.services.crawling.storage import merge_metadata
from src.services.http import FetchError


@dataclass
class CrawlRequest:
    novel: str
    translated_output: Path | None = None
    max_chapters: int | None = None
    fail_fast: bool = False
    ignore_robots: bool = False
    overwrite: bool = False
    use_browser: bool | None = None
    headed: bool = False
    workers: int = 1
    dry_run: bool = False


@dataclass
class CrawlPreview:
    index: int
    title: str
    url: str


@dataclass
class CrawlResult:
    novel: str
    title: str
    author: str | None
    fetched: int
    skipped: int
    failed: int
    total: int
    output_dir: str
    chapter_output_dir: str
    started_at: float
    finished_at: float
    cancelled: bool = False
    dry_run: bool = False
    preview: list[CrawlPreview] = field(default_factory=list)


def run_crawl(
    request: CrawlRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> CrawlResult:
    """Run the crawler with cooperative cancellation."""
    config = app_config.get_config()
    started_at = time.time()
    share_root = request.translated_output or Path(config.translated_dir)
    try:
        config_path = resolve_config_path(request.novel, translated_root=share_root)
        site_config = SiteConfig.from_file(config_path)
    except (OSError, ValueError) as error:
        raise ApplicationValidationError(str(error)) from error
    if site_config.name != request.novel:
        raise ApplicationValidationError(f"Config name {site_config.name!r} does not match novel directory {request.novel!r}.")

    if request.headed:
        use_browser = True
    elif request.use_browser is not None:
        use_browser = request.use_browser
    else:
        use_browser = False
    workers = request.workers
    if workers < 1:
        raise ApplicationValidationError("Number of workers must be at least 1.")
    if request.headed:
        workers = 1
    max_chapters = request.max_chapters
    if max_chapters == 0:
        max_chapters = None
    elif max_chapters is None and config.max_chapters > 0:
        max_chapters = config.max_chapters
    emit(
        progress_callback,
        ProgressEvent(
            kind="phase",
            novel=site_config.name,
            message=f"Crawling {site_config.name}",
            extra={"config": str(config_path), "browser": use_browser, "headed": request.headed},
        ),
    )

    fetcher = None
    if use_browser:
        from src.services.browser import BrowserFetcher

        fetcher = BrowserFetcher(
            user_agent=None if request.headed else site_config.user_agent,
            timeout_seconds=site_config.timeout_seconds,
            delay_seconds=site_config.request_delay_seconds,
            retry_attempts=site_config.retry_attempts,
            retry_backoff_seconds=site_config.retry_backoff_seconds,
            max_concurrency=workers,
            profile_dir=browser_profile_dir(site_config.toc_url) if request.headed else None,
            headless=not request.headed,
            challenge_timeout_seconds=120.0 if request.headed else None,
        )
        crawler = NovelCrawler(
            site_config,
            respect_robots=not request.ignore_robots,
            fetcher=fetcher,
        )
    else:
        crawler = NovelCrawler(
            site_config,
            respect_robots=not request.ignore_robots,
        )

    def _crawl_progress(event) -> None:
        if not isinstance(event, CrawlProgress):
            return
        emit(
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
        if request.dry_run:
            metadata, discovered = crawler.discover_chapters()
            metadata_path = config_path.parent / "metadata.json"
            if metadata_path.is_file():
                metadata = merge_metadata(metadata_path, metadata, site_config)
            if max_chapters is not None:
                discovered = discovered[:max_chapters]
            return CrawlResult(
                novel=site_config.name,
                title=metadata.title,
                author=metadata.author,
                fetched=0,
                skipped=0,
                failed=0,
                total=len(discovered),
                output_dir="",
                chapter_output_dir="",
                started_at=started_at,
                finished_at=time.time(),
                dry_run=True,
                preview=[
                    CrawlPreview(index=index, title=chapter.title, url=chapter.url)
                    for index, chapter in enumerate(discovered, start=1)
                ],
            )
        result = crawler.crawl(
            MANIFEST_DIR,
            max_chapters=max_chapters,
            fail_fast=request.fail_fast,
            overwrite=request.overwrite,
            share_root=share_root,
            progress_callback=_crawl_progress,
            workers=workers,
            cancel_event=cancel_event,
        )
    except ConsecutiveFailureError as error:
        raise ExternalServiceError(str(error), details={"novel": site_config.name}) from error
    except (FetchError, OSError, ValueError) as error:
        raise ApplicationValidationError(str(error)) from error
    finally:
        if fetcher is not None:
            fetcher.close(suppress_errors=True)

    skipped = sum(1 for chapter in result.chapters if chapter.skipped)
    fetched = len(result.chapters) - skipped
    failed = len(result.errors)
    total = len(result.chapters) + failed
    cancelled = result.cancelled
    emit(
        progress_callback,
        ProgressEvent(
            kind="cancelled" if cancelled else "completed",
            novel=site_config.name,
            current=fetched + failed + skipped,
            total=fetched + failed + skipped,
            message=f"Fetched {fetched}, skipped {skipped}, failed {failed}",
        ),
    )
    return CrawlResult(
        novel=site_config.name,
        title=result.metadata.title,
        author=result.metadata.author,
        fetched=fetched,
        skipped=skipped,
        failed=failed,
        total=total,
        output_dir=result.output_dir,
        chapter_output_dir=result.chapter_output_dir,
        started_at=started_at,
        finished_at=time.time(),
        cancelled=cancelled,
    )


def browser_profile_dir(toc_url: str) -> Path:
    """Return the project-anchored persistent browser profile directory."""
    hostname = urlparse(toc_url).hostname
    if not hostname:
        raise ValueError(f"Could not determine browser profile domain from URL: {toc_url}")
    safe_hostname = "".join(character if character.isalnum() or character in ".-_" else "_" for character in hostname.lower())
    return BROWSER_CACHE_DIR / safe_hostname


__all__ = [
    "CrawlPreview",
    "CrawlRequest",
    "CrawlResult",
    "browser_profile_dir",
    "run_crawl",
]
