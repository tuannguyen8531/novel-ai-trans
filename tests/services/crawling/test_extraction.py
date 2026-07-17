from __future__ import annotations

import pytest

from src.config import SiteConfig
from src.models import ChapterLink
from src.services.crawling.extraction import HtmlExtractor, InvalidChapterContentError


def config() -> SiteConfig:
    return SiteConfig.from_dict(
        {
            "name": "demo",
            "toc_url": "https://example.test/book",
            "novel_title_selector": "h1.title",
            "author_selector": ".author",
            "illustration_selector": ".cover img",
            "chapter_link_selector": ".chapters a",
            "chapter_title_selector": "h1",
            "chapter_content_selector": ".content",
            "remove_selectors": [".advertisement"],
        }
    )


def test_extracts_metadata_without_network_or_filesystem() -> None:
    extractor = HtmlExtractor(config())

    metadata = extractor.metadata(
        """
        <h1 class="title">Example Novel</h1>
        <span class="author">Example Author</span>
        <div class="cover"><img data-src="/cover.jpg"></div>
        """,
        "https://example.test/book",
    )

    assert metadata.title == "Example Novel"
    assert metadata.author == "Example Author"
    assert metadata.illustration_url == "https://example.test/cover.jpg"


def test_extracts_clean_chapter_text_without_network_or_filesystem() -> None:
    extractor = HtmlExtractor(config())

    title, body, source_url = extractor.chapter(
        ChapterLink(title="Fallback", url="https://example.test/chapter-1"),
        """
        <h1>Chapter 1</h1>
        <article class="content"><p>First.</p><p class="advertisement">Ad.</p><p>Second.</p></article>
        """,
        "https://example.test/chapter-1",
    )

    assert title == "Chapter 1"
    assert body == "First.\nSecond."
    assert source_url == "https://example.test/chapter-1"


def test_rejects_html_without_chapter_content() -> None:
    extractor = HtmlExtractor(config())

    with pytest.raises(InvalidChapterContentError, match="No chapter content found"):
        extractor.chapter(
            ChapterLink(title="Fallback", url="https://example.test/chapter-1"),
            "<html><body>Loading...</body></html>",
            "https://example.test/chapter-1",
        )
