"""Pure HTML extraction for novel metadata and chapter content."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.config import SiteConfig
from src.models import ChapterLink, NovelMetadata
from src.services.http import FetchError
from src.utils.text import html_to_plain_text, normalize_text

_CSS_URL = re.compile(r"url\((['\"]?)(.*?)\1\)", re.IGNORECASE)


class InvalidChapterContentError(FetchError):
    """A fetched page did not contain usable chapter content."""


class HtmlExtractor:
    """Convert fetched HTML into crawler domain values without doing I/O."""

    def __init__(self, config: SiteConfig) -> None:
        self.config = config

    def metadata(self, html: str, source_url: str) -> NovelMetadata:
        soup = BeautifulSoup(html, "html.parser")
        title = self.config.title or self.config.name
        if self.config.title is None and self.config.novel_title_selector:
            title_node = soup.select_one(self.config.novel_title_selector)
            if title_node:
                title = normalize_text(title_node.get_text(" ", strip=True)) or title

        author = self.config.author
        if author is None and self.config.author_selector:
            author_node = soup.select_one(self.config.author_selector)
            if author_node:
                author = normalize_text(author_node.get_text(" ", strip=True)) or None

        illustration_url = self.config.illustration_url or self._illustration_url(soup, source_url)
        return NovelMetadata(
            title=title,
            author=author,
            source_url=self.config.source_url or source_url,
            site_name=self.config.name,
            illustration_url=illustration_url,
            summary=self.config.summary,
        )

    def chapter(self, chapter_link: ChapterLink, html: str, source_url: str) -> tuple[str, str, str]:
        soup = BeautifulSoup(html, "html.parser")
        title = chapter_link.title
        if self.config.chapter_title_selector:
            title_node = soup.select_one(self.config.chapter_title_selector)
            if title_node:
                title = normalize_text(title_node.get_text(" ", strip=True)) or title

        for selector in self.config.remove_selectors:
            for node in soup.select(selector):
                node.decompose()

        content_node = soup.select_one(self.config.chapter_content_selector)
        if not content_node:
            raise InvalidChapterContentError(f"No chapter content found with selector: {self.config.chapter_content_selector}")

        body = html_to_plain_text(content_node)
        if not body:
            raise InvalidChapterContentError("Chapter content was empty after cleanup.")
        return title, body, source_url

    def _illustration_url(self, soup: BeautifulSoup, source_url: str) -> str | None:
        if not self.config.illustration_selector:
            return None

        node = soup.select_one(self.config.illustration_selector)
        if node is None:
            return None
        image_node = node if node.name in ("img", "source", "meta", "link") else node.select_one("img")
        if image_node is not None:
            for attr in ("src", "data-src", "data-original", "data-url", "content", "href"):
                value = image_node.get(attr)
                if isinstance(value, str) and value.strip():
                    return urljoin(source_url, value.strip())

            srcset = image_node.get("srcset")
            if isinstance(srcset, str) and srcset.strip():
                first_candidate = srcset.split(",", 1)[0].strip().split(" ", 1)[0]
                if first_candidate:
                    return urljoin(source_url, first_candidate)

        style = node.get("style")
        if isinstance(style, str):
            match = _CSS_URL.search(style)
            if match:
                url = match.group(2).strip()
                if url:
                    return urljoin(source_url, url)
        return None
