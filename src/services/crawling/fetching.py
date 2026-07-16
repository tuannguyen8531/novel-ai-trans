"""Crawler fetcher protocols and page acquisition policy."""

from __future__ import annotations

import time
from typing import Protocol

from src.config import SiteConfig
from src.models import ChapterLink
from src.services.crawling.extraction import InvalidChapterContentError
from src.services.http import FetchError, FetchResponse


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


class ChapterExtractor(Protocol):
    def chapter(self, chapter_link: ChapterLink, html: str, source_url: str) -> tuple[str, str, str]: ...


class PageAcquirer:
    """Acquire TOC and chapter pages, including crawler-specific retry policy."""

    def __init__(self, config: SiteConfig, fetcher: Fetcher, extractor: ChapterExtractor) -> None:
        self.config = config
        self.fetcher = fetcher
        self.extractor = extractor

    def toc(self, url: str) -> FetchResponse:
        if not self.config.toc_expand_selector:
            return self.fetcher.fetch(url)

        fetch_with_clicks = getattr(self.fetcher, "fetch_with_clicks", None)
        if fetch_with_clicks is None:
            raise FetchError("toc_expand_selector requires browser mode (-b/--browser).")
        return fetch_with_clicks(
            url,
            [self.config.toc_expand_selector],
            wait_for_selector=self.config.chapter_link_selector,
        )

    def chapter(self, chapter_link: ChapterLink) -> tuple[str, str, str]:
        attempts = max(1, self.config.retry_attempts)
        for attempt in range(1, attempts + 1):
            response = self.fetcher.fetch(chapter_link.url)
            try:
                return self.extractor.chapter(chapter_link, response.body, response.url)
            except InvalidChapterContentError:
                if attempt == attempts:
                    raise
                delay = self.config.retry_backoff_seconds * attempt
                if delay > 0:
                    time.sleep(delay)

        raise AssertionError("Chapter retry loop exited unexpectedly.")
