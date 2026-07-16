from __future__ import annotations

from src.config import SiteConfig
from src.services.crawling.discovery import ChapterDiscovery
from src.services.crawling.extraction import HtmlExtractor
from src.services.http import FetchResponse


def test_duplicate_dom_links_keep_first_title() -> None:
    config = SiteConfig.from_dict(
        {
            "name": "demo",
            "toc_url": "https://example.test/book",
            "chapter_link_selector": ".chapters a",
            "chapter_content_selector": ".content",
            "filter_non_chapter_links": False,
        }
    )
    response = FetchResponse(
        url=config.toc_url,
        body="""
            <nav class="chapters">
              <a href="/chapter-1">Chapter 1</a>
              <a href="/chapter-1">Chapter 1: Longer title</a>
            </nav>
        """,
        content_type="text/html",
    )
    discovery = ChapterDiscovery(config, lambda _url: response, HtmlExtractor(config))

    _, chapters = discovery.discover()

    assert [(chapter.title, chapter.url) for chapter in chapters] == [("Chapter 1", "https://example.test/chapter-1")]
