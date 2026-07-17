"""HTTP and browser acquisition for crawler config generation."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Protocol

from bs4 import BeautifulSoup

from src.config import DEFAULT_USER_AGENT
from src.services.generation.cache import HtmlCache
from src.services.http import FetchResponse, HttpClient
from src.utils.logging import get_logger


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


BrowserFactory = Callable[[], AbstractContextManager[Fetcher]]


@dataclass(frozen=True)
class FetchResult:
    body: str
    from_cache: bool


@dataclass(frozen=True)
class ChapterFetchResult:
    body: str
    from_cache: bool
    usable: bool
    used_browser_fallback: bool = False


class PageAcquirer:
    """Acquire pages through one fetcher, cache, and optional browser fallback."""

    def __init__(
        self,
        fetcher: Fetcher,
        cache: HtmlCache,
        *,
        browser_active: bool = False,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._cache = cache
        self._browser_active = browser_active
        self._browser_factory = browser_factory

    def fetch(self, url: str) -> FetchResult | None:
        cached = self._cache.get(url)
        if cached is not None:
            get_logger().debug("Generated-config HTML cache hit for %s", url)
            return FetchResult(cached, from_cache=True)
        get_logger().debug("Generated-config HTML cache miss for %s", url)
        try:
            response = self._fetcher.fetch(url)
            self._cache.set(url, response.body)
        except Exception as error:  # noqa: BLE001 - acquisition failure is represented as no page.
            get_logger().warning("Failed to fetch %s: %s", url, error)
            return None
        return FetchResult(response.body, from_cache=False)

    def fetch_chapter(self, url: str) -> ChapterFetchResult | None:
        result = self.fetch(url)
        if result is None:
            return None
        if not is_challenge_page(result.body):
            return ChapterFetchResult(result.body, result.from_cache, usable=True)
        if self._browser_active:
            get_logger().warning("Chapter page is an anti-bot challenge; selector analysis will be skipped")
            return ChapterFetchResult(result.body, result.from_cache, usable=False)
        if self._browser_factory is None:
            get_logger().warning("Chapter page is an anti-bot challenge and no browser fallback is available")
            return ChapterFetchResult(result.body, result.from_cache, usable=False)

        get_logger().warning("Chapter page is an anti-bot challenge; trying browser fallback")
        with self._browser_factory() as browser:
            body = browser.fetch(url).body
        self._cache.set(url, body)
        if is_challenge_page(body):
            get_logger().warning("Browser fallback also returned an anti-bot challenge")
            return ChapterFetchResult(body, from_cache=False, usable=False, used_browser_fallback=True)
        get_logger().info("Browser fallback fetch succeeded for %s", url)
        return ChapterFetchResult(body, from_cache=False, usable=True, used_browser_fallback=True)


@contextmanager
def open_acquirer(
    cache: HtmlCache,
    *,
    use_browser: bool = False,
    headed: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Generator[PageAcquirer]:
    """Open the selected primary fetcher and yield a configured acquirer."""
    browser_active = use_browser or headed
    if browser_active:
        from src.services.browser import BrowserFetcher

        if headed:
            manager: AbstractContextManager[Fetcher] = BrowserFetcher(
                user_agent=None,
                headless=False,
                challenge_timeout_seconds=120.0,
            )
        else:
            manager = BrowserFetcher(
                user_agent=user_agent,
                timeout_seconds=30,
                delay_seconds=1.0,
            )
        with manager as fetcher:
            yield PageAcquirer(fetcher, cache, browser_active=True)
        return

    http = HttpClient(
        user_agent=user_agent,
        timeout_seconds=30,
        delay_seconds=1.5,
        respect_robots=False,
    )

    def browser_factory() -> AbstractContextManager[Fetcher]:
        from src.services.browser import BrowserFetcher

        return BrowserFetcher(
            user_agent=user_agent,
            timeout_seconds=30,
            delay_seconds=1.0,
        )

    yield PageAcquirer(http, cache, browser_factory=browser_factory)


def is_error_page(html: str) -> bool:
    """Return whether a page appears to be a missing-page response."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").lower() if soup.title else ""
    if any(signal in title for signal in ("404", "not found", "错误", "不存在")):
        return True
    body_text = soup.get_text(" ", strip=True)[:500].lower()
    return any(signal in body_text for signal in ("页面不存在", "页面已删除", "page not found"))


def is_challenge_page(html: str) -> bool:
    """Return whether a page appears to be an anti-bot challenge."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").lower() if soup.title else ""
    title_signals = (
        "just a moment",
        "checking your browser",
        "ddos protection",
        "attention required",
        "cloudflare",
        "wait",
    )
    if any(signal in title for signal in title_signals):
        return True
    body_text = soup.get_text(" ", strip=True)[:500].lower()
    text_signals = (
        "just a moment",
        "checking your browser",
        "ddos protection",
        "cloudflare",
        "please enable javascript",
        "please wait",
        "redirecting",
    )
    if any(signal in body_text for signal in text_signals):
        return True
    return len(html) < 1500 and bool(soup.select_one(".main-wrapper, #cf-wrapper, #challenge-form"))


__all__ = [
    "ChapterFetchResult",
    "FetchResult",
    "Fetcher",
    "PageAcquirer",
    "is_challenge_page",
    "is_error_page",
    "open_acquirer",
]
