from __future__ import annotations

import pytest

from src.config import SiteConfig
from src.models import ChapterLink
from src.services.crawling.extraction import InvalidChapterContentError
from src.services.crawling.fetching import PageAcquirer
from src.services.http import FetchResponse


class Fetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResponse:
        self.calls.append(url)
        return FetchResponse(url=url, body="ignored", content_type="text/html")


class Extractor:
    def __init__(self, *, always_invalid: bool = False) -> None:
        self.always_invalid = always_invalid
        self.calls = 0

    def chapter(self, chapter_link: ChapterLink, html: str, source_url: str) -> tuple[str, str, str]:
        del html
        self.calls += 1
        if self.always_invalid or self.calls == 1:
            raise InvalidChapterContentError("invalid chapter")
        return chapter_link.title, "Recovered", source_url


def config(*, attempts: int) -> SiteConfig:
    return SiteConfig.from_dict(
        {
            "name": "demo",
            "toc_url": "https://example.test/book",
            "chapter_link_selector": ".chapters a",
            "chapter_content_selector": ".content",
            "retry_attempts": attempts,
            "retry_backoff_seconds": 0,
        }
    )


def test_retries_when_extractor_rejects_fetched_content() -> None:
    fetcher = Fetcher()
    extractor = Extractor()
    acquirer = PageAcquirer(config(attempts=3), fetcher, extractor)
    chapter = ChapterLink(title="Chapter 1", url="https://example.test/chapter-1")

    assert acquirer.chapter(chapter) == ("Chapter 1", "Recovered", chapter.url)
    assert fetcher.calls == [chapter.url, chapter.url]


def test_stops_at_content_retry_limit() -> None:
    fetcher = Fetcher()
    extractor = Extractor(always_invalid=True)
    acquirer = PageAcquirer(config(attempts=2), fetcher, extractor)
    chapter = ChapterLink(title="Chapter 1", url="https://example.test/chapter-1")

    with pytest.raises(InvalidChapterContentError, match="invalid chapter"):
        acquirer.chapter(chapter)

    assert fetcher.calls == [chapter.url, chapter.url]
