from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from src.services.generation.cache import HtmlCache
from src.services.generation.fetching import PageAcquirer
from src.services.http import FetchResponse


class StaticFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requests: list[str] = []

    def fetch(self, url: str) -> FetchResponse:
        self.requests.append(url)
        return FetchResponse(url=url, body=self.pages[url], content_type="text/html")


class BrowserContext(AbstractContextManager[StaticFetcher]):
    def __init__(self, fetcher: StaticFetcher) -> None:
        self.fetcher = fetcher

    def __enter__(self) -> StaticFetcher:
        return self.fetcher

    def __exit__(self, *_args: object) -> None:
        return None


class FailingCache(HtmlCache):
    def set(self, url: str, html: str) -> None:
        raise OSError("cache unavailable")


class FailingBrowserContext(AbstractContextManager[StaticFetcher]):
    def __enter__(self) -> StaticFetcher:
        raise RuntimeError("browser unavailable")

    def __exit__(self, *_args: object) -> None:
        return None


def test_acquirer_uses_cache_after_first_fetch(tmp_path: Path) -> None:
    url = "https://example.com/book"
    fetcher = StaticFetcher({url: "<html>" + "x" * 300 + "</html>"})
    acquirer = PageAcquirer(fetcher, HtmlCache(tmp_path))

    first = acquirer.fetch(url)
    second = acquirer.fetch(url)

    assert first is not None and not first.from_cache
    assert second is not None and second.from_cache
    assert fetcher.requests == [url]


def test_cache_write_failure_is_reported_as_fetch_failure(tmp_path: Path) -> None:
    url = "https://example.com/book"
    fetcher = StaticFetcher({url: "<html>" + "x" * 300 + "</html>"})
    acquirer = PageAcquirer(fetcher, FailingCache(tmp_path, enabled=False))

    assert acquirer.fetch(url) is None


def test_active_browser_does_not_retry_challenge(tmp_path: Path) -> None:
    url = "https://example.com/chapter"
    challenge = "<html><title>Just a moment...</title><div id='cf-wrapper'></div></html>"
    acquirer = PageAcquirer(StaticFetcher({url: challenge}), HtmlCache(tmp_path), browser_active=True)

    result = acquirer.fetch_chapter(url)

    assert result is not None
    assert not result.usable
    assert not result.used_browser_fallback


def test_http_acquisition_uses_browser_fallback_for_challenge(tmp_path: Path) -> None:
    url = "https://example.com/chapter"
    challenge = "<html><title>Just a moment...</title><div id='cf-wrapper'></div></html>"
    browser_html = "<html><section class='content'>" + "story " * 60 + "</section></html>"
    browser = StaticFetcher({url: browser_html})
    acquirer = PageAcquirer(
        StaticFetcher({url: challenge}),
        HtmlCache(tmp_path),
        browser_factory=lambda: BrowserContext(browser),
    )

    result = acquirer.fetch_chapter(url)

    assert result is not None
    assert result.usable
    assert result.used_browser_fallback
    assert result.body == browser_html
    assert browser.requests == [url]


def test_browser_fallback_failure_propagates(tmp_path: Path) -> None:
    url = "https://example.com/chapter"
    challenge = "<html><title>Just a moment...</title><div id='cf-wrapper'></div></html>"
    acquirer = PageAcquirer(
        StaticFetcher({url: challenge}),
        HtmlCache(tmp_path),
        browser_factory=lambda: FailingBrowserContext(),
    )

    with pytest.raises(RuntimeError, match="browser unavailable"):
        acquirer.fetch_chapter(url)
