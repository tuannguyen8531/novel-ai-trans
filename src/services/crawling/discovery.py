"""Table-of-contents traversal and chapter ordering."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.config import SiteConfig
from src.models import ChapterLink, NovelMetadata
from src.services.chapters import detect_chapter_number, select_likely_chapters
from src.services.crawling.extraction import HtmlExtractor
from src.services.http import FetchResponse
from src.utils.text import normalize_text


def _iter_apollo_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        ref = value.get("__ref")
        if isinstance(ref, str):
            refs.append(ref)
        else:
            for child in value.values():
                refs.extend(_iter_apollo_refs(child))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_iter_apollo_refs(item))
    return refs


def _is_better_title(candidate: str, current: str) -> bool:
    candidate_number = detect_chapter_number(candidate)
    current_number = detect_chapter_number(current)
    if candidate_number is not None and current_number is None:
        return True
    if candidate_number is not None and current_number is not None:
        return len(candidate) > len(current)
    return False


class ChapterDiscovery:
    """Traverse TOC pages and return normalized, ordered chapter links."""

    def __init__(
        self,
        config: SiteConfig,
        fetch_toc: Callable[[str], FetchResponse],
        extractor: HtmlExtractor,
    ) -> None:
        self.config = config
        self.fetch_toc = fetch_toc
        self.extractor = extractor

    def discover(self) -> tuple[NovelMetadata, list[ChapterLink]]:
        toc_url = self.config.toc_url
        toc_netloc = urlparse(toc_url).netloc
        visited_toc_urls: set[str] = set()
        seen_chapters: set[str] = set()
        chapters: list[ChapterLink] = []
        chapter_index_by_url: dict[str, int] = {}
        metadata: NovelMetadata | None = None

        for _ in range(self.config.max_toc_pages):
            if toc_url in visited_toc_urls:
                break
            visited_toc_urls.add(toc_url)

            response = self.fetch_toc(toc_url)
            soup = BeautifulSoup(response.body, "html.parser")
            if metadata is None:
                metadata = self.extractor.metadata(response.body, response.url)

            for chapter in self.page_chapters(soup, response.url):
                if self.config.same_domain and urlparse(chapter.url).netloc != toc_netloc:
                    continue
                if chapter.url in seen_chapters:
                    index = chapter_index_by_url.get(chapter.url)
                    if index is not None and _is_better_title(chapter.title, chapters[index].title):
                        chapters[index] = chapter
                    continue
                chapters.append(chapter)
                seen_chapters.add(chapter.url)
                chapter_index_by_url[chapter.url] = len(chapters) - 1

            next_url = self.next_url(soup, response.url)
            if not next_url:
                break
            if self.config.same_domain and urlparse(next_url).netloc != toc_netloc:
                break
            toc_url = next_url

        if self.config.filter_non_chapter_links:
            chapters = select_likely_chapters(chapters, title_getter=lambda chapter: chapter.title)
        chapters = self.order(chapters)
        if metadata is None:
            metadata = NovelMetadata(
                title=self.config.title or self.config.name,
                author=self.config.author,
                source_url=self.config.source_url or self.config.toc_url,
                site_name=self.config.name,
                illustration_url=self.config.illustration_url,
                summary=self.config.summary,
            )
        return metadata, chapters

    def page_chapters(self, soup: BeautifulSoup, page_url: str) -> list[ChapterLink]:
        chapters: list[ChapterLink] = []
        for anchor in soup.select(self.config.chapter_link_selector):
            href = anchor.get("href")
            if not isinstance(href, str) or not href:
                continue
            url = urljoin(page_url, href)
            title = normalize_text(anchor.get_text(" ", strip=True)) or url
            chapters.append(ChapterLink(title=title, url=url))
        chapters.extend(self.next_data_chapters(soup, page_url))
        return chapters

    def order(self, chapters: list[ChapterLink]) -> list[ChapterLink]:
        numbered = [(detect_chapter_number(chapter.title), index, chapter) for index, chapter in enumerate(chapters)]
        if numbered and all(number is not None for number, _, _ in numbered):

            def sort_key(item: tuple[int | None, int, ChapterLink]) -> tuple[int, int]:
                number, index, _ = item
                assert number is not None
                return (-number if self.config.reverse_chapter_order else number, index)

            return [chapter for _, _, chapter in sorted(numbered, key=sort_key)]

        if self.config.reverse_chapter_order:
            return list(reversed(chapters))
        return chapters

    def next_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        if not self.config.toc_next_selector:
            return None
        next_node = soup.select_one(self.config.toc_next_selector)
        if not next_node:
            return None
        href = next_node.get("href")
        if not isinstance(href, str) or not href:
            return None
        return urljoin(current_url, href)

    @staticmethod
    def next_data_chapters(soup: BeautifulSoup, page_url: str) -> list[ChapterLink]:
        script = soup.select_one("script#__NEXT_DATA__")
        raw_json = script.string if script else None
        if not raw_json:
            return []

        match = re.search(r"/works/([^/?#]+)", page_url)
        if not match:
            return []
        work_id = match.group(1)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return []

        apollo = data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})
        if not isinstance(apollo, dict):
            return []
        work = apollo.get(f"Work:{work_id}", {})
        if not isinstance(work, dict):
            return []

        chapters: list[ChapterLink] = []
        position = 0
        for toc_ref in _iter_apollo_refs(work.get("tableOfContentsV2")):
            toc = apollo.get(toc_ref, {})
            if not isinstance(toc, dict):
                continue
            for episode_ref in _iter_apollo_refs(toc.get("episodeUnions")):
                typename, _, episode_id = episode_ref.partition(":")
                if typename not in {"Episode", "EmptyEpisode"} or not episode_id:
                    continue
                episode = apollo.get(episode_ref, {})
                title = ""
                if isinstance(episode, dict):
                    title = normalize_text(str(episode.get("title") or ""))
                if not title:
                    title = f"Episode {position + 1}"
                elif detect_chapter_number(title) is None:
                    title = f"Episode {position + 1} {title}"
                chapters.append(
                    ChapterLink(
                        title=title,
                        url=urljoin(page_url, f"/works/{work_id}/episodes/{episode_id}"),
                    )
                )
                position += 1
        return chapters
