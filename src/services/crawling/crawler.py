"""Composed crawl service used by application workflows."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from src.config import SiteConfig
from src.models import ChapterLink, CrawlResult, NovelMetadata
from src.services.crawling.discovery import ChapterDiscovery
from src.services.crawling.execution import CrawlExecutor, ProgressCallback
from src.services.crawling.extraction import HtmlExtractor
from src.services.crawling.fetching import Fetcher, PageAcquirer
from src.services.crawling.storage import CrawlStorage
from src.services.http import FetchError, HttpClient

StorageFactory = Callable[[SiteConfig, Path, Path | None], CrawlStorage]


class NovelCrawler:
    """Compose crawler collaborators behind the application-facing interface."""

    def __init__(
        self,
        config: SiteConfig,
        *,
        respect_robots: bool = True,
        fetcher: Fetcher | None = None,
        storage_factory: StorageFactory = CrawlStorage,
    ) -> None:
        self.config = config
        page_fetcher = fetcher or HttpClient(
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            delay_seconds=config.request_delay_seconds,
            retry_attempts=config.retry_attempts,
            retry_backoff_seconds=config.retry_backoff_seconds,
            respect_robots=respect_robots,
        )
        extractor = HtmlExtractor(config)
        self.acquirer = PageAcquirer(config, page_fetcher, extractor)
        self.discovery = ChapterDiscovery(config, self.acquirer.toc, extractor)
        self.storage_factory = storage_factory

    def discover_chapters(self) -> tuple[NovelMetadata, list[ChapterLink]]:
        return self.discovery.discover()

    def crawl(
        self,
        output_root: Path,
        *,
        max_chapters: int | None = None,
        fail_fast: bool = False,
        overwrite: bool = False,
        share_root: Path | None = None,
        progress_callback: ProgressCallback | None = None,
        workers: int = 1,
        cancel_event: threading.Event | None = None,
    ) -> CrawlResult:
        metadata, chapter_links = self.discover_chapters()
        if not chapter_links:
            raise FetchError("No chapter links found. Check chapter_link_selector.")
        storage = self.storage_factory(self.config, output_root, share_root)
        executor = CrawlExecutor(self.acquirer, storage)
        return executor.execute(
            metadata,
            chapter_links,
            max_chapters=max_chapters,
            fail_fast=fail_fast,
            overwrite=overwrite,
            progress_callback=progress_callback,
            workers=workers,
            cancel_event=cancel_event,
        )
