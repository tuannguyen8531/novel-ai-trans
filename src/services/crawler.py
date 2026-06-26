from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.config import SiteConfig
from src.models import (
    ChapterLink,
    ChapterResult,
    CrawlError,
    CrawlProgress,
    CrawlResult,
    NovelMetadata,
)
from src.services.http import FetchError, FetchResponse, HttpClient
from src.services.metadata import metadata_to_dict
from src.utils.chapters import detect_chapter_number, select_likely_chapters
from src.utils.text import html_to_plain_text, normalize_text, slugify

ProgressCallback = Callable[[CrawlProgress], None]
_CSS_URL = re.compile(r"url\((['\"]?)(.*?)\1\)", re.IGNORECASE)
CONSECUTIVE_FAILURE_LIMIT = 5


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


class ExpandableFetcher(Fetcher, Protocol):
    def fetch_with_clicks(
        self,
        url: str,
        click_selectors: list[str],
        *,
        wait_for_selector: str | None = None,
    ) -> FetchResponse: ...


class InvalidChapterContentError(FetchError):
    """A fetched page did not contain usable chapter content."""


class ConsecutiveFailureError(FetchError):
    """Raised when too many chapter fetches fail in a row and the crawl aborts."""


def _iter_apollo_refs(value: Any) -> list[str]:
    """Return Apollo cache references from nested lists/dicts."""
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
    """Prefer explicit chapter titles over generic navigation labels."""
    candidate_number = detect_chapter_number(candidate)
    current_number = detect_chapter_number(current)
    if candidate_number is not None and current_number is None:
        return True
    if candidate_number is not None and current_number is not None:
        return len(candidate) > len(current)
    return False


class NovelCrawler:
    def __init__(
        self,
        config: SiteConfig,
        *,
        respect_robots: bool = True,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.config = config
        self.client: Fetcher = fetcher or HttpClient(
            user_agent=config.user_agent,
            timeout_seconds=config.timeout_seconds,
            delay_seconds=config.request_delay_seconds,
            retry_attempts=config.retry_attempts,
            retry_backoff_seconds=config.retry_backoff_seconds,
            respect_robots=respect_robots,
        )

    def discover_chapters(self) -> tuple[NovelMetadata, list[ChapterLink]]:
        config = self.config
        toc_url = config.start_url
        start_netloc = urlparse(config.start_url).netloc
        visited_toc_urls: set[str] = set()
        seen_chapters: set[str] = set()
        chapters: list[ChapterLink] = []
        chapter_index_by_url: dict[str, int] = {}
        metadata: NovelMetadata | None = None

        for _ in range(config.max_toc_pages):
            if toc_url in visited_toc_urls:
                break
            visited_toc_urls.add(toc_url)

            response = self._fetch_toc_page(toc_url)
            soup = BeautifulSoup(response.body, "html.parser")
            if metadata is None:
                metadata = self._extract_metadata(soup, response.url)

            for anchor in soup.select(config.chapter_link_selector):
                href = anchor.get("href")
                if not isinstance(href, str) or not href:
                    continue
                chapter_url = urljoin(response.url, href)
                if config.same_domain and urlparse(chapter_url).netloc != start_netloc:
                    continue
                if chapter_url in seen_chapters:
                    continue
                title = normalize_text(anchor.get_text(" ", strip=True)) or chapter_url
                chapters.append(ChapterLink(title=title, url=chapter_url))
                seen_chapters.add(chapter_url)
                chapter_index_by_url[chapter_url] = len(chapters) - 1

            for chapter in self._extract_next_data_chapters(soup, response.url):
                if config.same_domain and urlparse(chapter.url).netloc != start_netloc:
                    continue
                if chapter.url in seen_chapters:
                    index = chapter_index_by_url.get(chapter.url)
                    if index is not None and _is_better_title(chapter.title, chapters[index].title):
                        chapters[index] = chapter
                    continue
                chapters.append(chapter)
                seen_chapters.add(chapter.url)
                chapter_index_by_url[chapter.url] = len(chapters) - 1

            next_url = self._next_toc_url(soup, response.url)
            if not next_url:
                break
            if config.same_domain and urlparse(next_url).netloc != start_netloc:
                break
            toc_url = next_url

        if config.filter_non_chapter_links:
            chapters = select_likely_chapters(
                chapters,
                title_getter=lambda chapter: chapter.title,
            )
        chapters = self._order_chapters(chapters)
        if metadata is None:
            metadata = NovelMetadata(
                title=config.name,
                author=None,
                source_url=config.start_url,
                site_name=config.name,
            )
        return metadata, chapters

    def _order_chapters(self, chapters: list[ChapterLink]) -> list[ChapterLink]:
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

    @staticmethod
    def _extract_next_data_chapters(soup: BeautifulSoup, page_url: str) -> list[ChapterLink]:
        """Extract chapter links from Next.js Apollo state when the DOM TOC is collapsed.

        Kakuyomu renders only part of long TOCs in the HTML, but the embedded
        Apollo state includes the ordered episode IDs. Some later episodes are
        represented as EmptyEpisode records without titles; their real titles are
        still read from the chapter page during crawl.
        """
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
    ) -> CrawlResult:
        metadata, chapter_links = self.discover_chapters()
        if not chapter_links:
            raise FetchError("No chapter links found. Check chapter_link_selector.")

        novel_slug = slugify(self.config.name)
        novel_dir = output_root / novel_slug
        chapter_output_dir = share_root / novel_slug / "input" if share_root else novel_dir / "chapters"
        novel_dir.mkdir(parents=True, exist_ok=True)
        chapter_output_dir.mkdir(parents=True, exist_ok=True)

        results: list[ChapterResult] = []
        errors: list[CrawlError] = []
        generated_at = datetime.now(UTC).isoformat()
        fetched_count = 0

        self._write_metadata(novel_dir / "metadata.json", metadata)
        if share_root:
            self._write_metadata(chapter_output_dir.parent / "metadata.json", metadata)
        self._write_json(novel_dir / "config.json", asdict(self.config))
        self._write_manifest(
            novel_dir / "manifest.json",
            generated_at=generated_at,
            status="running",
            metadata=metadata,
            runtime_output_dir=novel_dir,
            chapter_output_dir=chapter_output_dir,
            chapter_links=chapter_links,
            results=results,
            errors=errors,
        )

        def _write_running_manifest(*, status: str = "running") -> None:
            self._write_manifest(
                novel_dir / "manifest.json",
                generated_at=generated_at,
                status=status,
                metadata=metadata,
                runtime_output_dir=novel_dir,
                chapter_output_dir=chapter_output_dir,
                chapter_links=chapter_links,
                results=results,
                errors=errors,
            )

        def _fetch_chapter(index: int, chapter_link: ChapterLink, chapter_path: Path) -> ChapterResult:
            self._report_progress(
                progress_callback,
                current=index,
                total=len(chapter_links),
                status="started",
                title=chapter_link.title,
                source_url=chapter_link.url,
                path=str(chapter_path),
            )
            title, body, final_url = self._fetch_chapter(chapter_link)
            self._write_text_atomic(chapter_path, self._chapter_text(title, body))
            return ChapterResult(
                index=index,
                title=title,
                source_url=final_url,
                path=str(chapter_path),
            )

        if workers < 1:
            raise ValueError("Number of workers must be at least 1.")

        # A strict fail-fast crawl cannot start speculative requests because an
        # in-flight HTTP request cannot be cancelled reliably.
        effective_workers = 1 if fail_fast else workers
        next_chapter = 0
        pending: dict[Future[ChapterResult], tuple[int, ChapterLink]] = {}
        attempted_chapters: dict[int, tuple[ChapterLink, Path]] = {}
        chapter_outcomes: dict[int, bool] = {}
        next_outcome_index = 1
        consecutive_failures = 0

        def _record_chapter_outcome(index: int, *, success: bool) -> bool:
            nonlocal next_outcome_index, consecutive_failures
            chapter_outcomes[index] = success
            while next_outcome_index in chapter_outcomes:
                if chapter_outcomes[next_outcome_index]:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                        return True
                next_outcome_index += 1
            return False

        def _raise_if_too_many_consecutive_failures() -> None:
            results.sort(key=lambda r: r.index)
            errors.sort(key=lambda error: error["index"])
            _write_running_manifest(status="failed")
            for future in pending:
                future.cancel()
            raise ConsecutiveFailureError(
                f"Stopped after {CONSECUTIVE_FAILURE_LIMIT} consecutive chapter failures. Progress was saved to manifest.json."
            )

        def _fill_pending(executor: ThreadPoolExecutor) -> None:
            nonlocal next_chapter
            while next_chapter < len(chapter_links):
                if len(pending) >= effective_workers:
                    return
                if max_chapters is not None and fetched_count + len(pending) >= max_chapters:
                    return

                index = next_chapter + 1
                chapter_link = chapter_links[next_chapter]
                next_chapter += 1
                chapter_path = chapter_output_dir / f"chapter_{index}.txt"

                if not overwrite and self._is_existing_chapter(chapter_path):
                    results.append(
                        ChapterResult(
                            index=index,
                            title=chapter_link.title,
                            source_url=chapter_link.url,
                            path=str(chapter_path),
                            skipped=True,
                        )
                    )
                    self._report_progress(
                        progress_callback,
                        current=index,
                        total=len(chapter_links),
                        status="skipped",
                        title=chapter_link.title,
                        source_url=chapter_link.url,
                        path=str(chapter_path),
                    )
                    _write_running_manifest()
                    if _record_chapter_outcome(index, success=True):
                        _raise_if_too_many_consecutive_failures()
                    continue

                attempted_chapters[index] = (chapter_link, chapter_path)
                future = executor.submit(_fetch_chapter, index, chapter_link, chapter_path)
                pending[future] = (index, chapter_link)

        executor = ThreadPoolExecutor(max_workers=effective_workers)
        try:
            _fill_pending(executor)
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    index, chapter_link = pending[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        error_text = str(error)
                        errors.append(
                            {
                                "index": index,
                                "url": chapter_link.url,
                                "error": error_text,
                            }
                        )
                        self._report_progress(
                            progress_callback,
                            current=index,
                            total=len(chapter_links),
                            status="failed",
                            title=chapter_link.title,
                            source_url=chapter_link.url,
                            error=error_text,
                        )
                        _write_running_manifest(status="failed" if fail_fast else "running")
                        if fail_fast:
                            raise
                        pending.pop(future, None)
                        if _record_chapter_outcome(index, success=False):
                            _raise_if_too_many_consecutive_failures()
                    else:
                        results.append(result)
                        fetched_count += 1
                        self._report_progress(
                            progress_callback,
                            current=index,
                            total=len(chapter_links),
                            status="fetched",
                            title=result.title,
                            source_url=result.source_url,
                            path=result.path,
                        )
                        _write_running_manifest()
                        pending.pop(future, None)
                        if _record_chapter_outcome(index, success=True):
                            _raise_if_too_many_consecutive_failures()
                _fill_pending(executor)
        except KeyboardInterrupt:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            for future, (index, chapter_link) in list(pending.items()):
                if future.cancelled() or not future.done():
                    continue
                try:
                    result = future.result()
                except Exception as error:
                    errors.append(
                        {
                            "index": index,
                            "url": chapter_link.url,
                            "error": str(error),
                        }
                    )
                else:
                    results.append(result)
                    fetched_count += 1

            recorded_indexes = {result.index for result in results}
            for index, (chapter_link, chapter_path) in attempted_chapters.items():
                if index in recorded_indexes:
                    continue
                if self._is_existing_chapter(chapter_path):
                    results.append(
                        ChapterResult(
                            index=index,
                            title=chapter_link.title,
                            source_url=chapter_link.url,
                            path=str(chapter_path),
                        )
                    )
                    fetched_count += 1

            results.sort(key=lambda r: r.index)
            errors.sort(key=lambda error: error["index"])
            self._write_manifest(
                novel_dir / "manifest.json",
                generated_at=generated_at,
                status="interrupted",
                metadata=metadata,
                runtime_output_dir=novel_dir,
                chapter_output_dir=chapter_output_dir,
                chapter_links=chapter_links,
                results=results,
                errors=errors,
            )
            raise
        finally:
            executor.shutdown(wait=True)

        # Sort results by index so output is deterministic regardless of
        # parallel execution order.
        results.sort(key=lambda r: r.index)
        errors.sort(key=lambda error: error["index"])

        self._write_manifest(
            novel_dir / "manifest.json",
            generated_at=generated_at,
            status="completed",
            metadata=metadata,
            runtime_output_dir=novel_dir,
            chapter_output_dir=chapter_output_dir,
            chapter_links=chapter_links,
            results=results,
            errors=errors,
        )
        if share_root:
            self._write_metadata(chapter_output_dir.parent / "metadata.json", metadata)

        return CrawlResult(
            metadata=metadata,
            chapters=results,
            output_dir=str(novel_dir),
            chapter_output_dir=str(chapter_output_dir),
            errors=list(errors),
        )

    def _extract_metadata(self, soup: BeautifulSoup, source_url: str) -> NovelMetadata:
        title = self.config.name
        if self.config.novel_title_selector:
            title_node = soup.select_one(self.config.novel_title_selector)
            if title_node:
                title = normalize_text(title_node.get_text(" ", strip=True)) or title

        author = None
        if self.config.author_selector:
            author_node = soup.select_one(self.config.author_selector)
            if author_node:
                author = normalize_text(author_node.get_text(" ", strip=True)) or None
        illustration_url = self._extract_illustration_url(soup, source_url)

        return NovelMetadata(
            title=title,
            author=author,
            source_url=source_url,
            site_name=self.config.name,
            illustration_url=illustration_url,
        )

    def _extract_illustration_url(self, soup: BeautifulSoup, source_url: str) -> str | None:
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

    def _fetch_toc_page(self, url: str) -> FetchResponse:
        if not self.config.toc_expand_selector:
            return self.client.fetch(url)

        fetch_with_clicks = getattr(self.client, "fetch_with_clicks", None)
        if fetch_with_clicks is None:
            raise FetchError("toc_expand_selector requires browser mode (-b/--browser).")
        return fetch_with_clicks(
            url,
            [self.config.toc_expand_selector],
            wait_for_selector=self.config.chapter_link_selector,
        )

    def _next_toc_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        if not self.config.toc_next_selector:
            return None
        next_node = soup.select_one(self.config.toc_next_selector)
        if not next_node:
            return None
        href = next_node.get("href")
        if not isinstance(href, str) or not href:
            return None
        return urljoin(current_url, href)

    def _fetch_chapter(self, chapter_link: ChapterLink) -> tuple[str, str, str]:
        attempts = max(1, self.config.retry_attempts)
        for attempt in range(1, attempts + 1):
            response = self.client.fetch(chapter_link.url)
            try:
                return self._extract_chapter(chapter_link, response)
            except InvalidChapterContentError:
                if attempt == attempts:
                    raise
                delay = self.config.retry_backoff_seconds * attempt
                if delay > 0:
                    time.sleep(delay)

        raise AssertionError("Chapter retry loop exited unexpectedly.")

    def _extract_chapter(
        self,
        chapter_link: ChapterLink,
        response: FetchResponse,
    ) -> tuple[str, str, str]:
        soup = BeautifulSoup(response.body, "html.parser")

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
        return title, body, response.url

    @staticmethod
    def _write_json(path: Path, data: object) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)

    def _write_manifest(
        self,
        path: Path,
        *,
        generated_at: str,
        status: str,
        metadata: NovelMetadata,
        runtime_output_dir: Path,
        chapter_output_dir: Path,
        chapter_links: list[ChapterLink],
        results: list[ChapterResult],
        errors: list[CrawlError],
    ) -> None:
        skipped_count = sum(1 for result in results if result.skipped)
        manifest = {
            "generated_at": generated_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "status": status,
            "config": asdict(self.config),
            "metadata": metadata_to_dict(metadata),
            "runtime_output_dir": str(runtime_output_dir),
            "chapter_output_dir": str(chapter_output_dir),
            "total_chapters": len(chapter_links),
            "completed_chapters": len(results) + len(errors),
            "fetched_chapters": len(results) - skipped_count,
            "skipped_chapters": skipped_count,
            "failed_chapters": len(errors),
            "discovered_chapters": [
                {"index": index, "title": chapter.title, "source_url": chapter.url}
                for index, chapter in enumerate(chapter_links, start=1)
            ],
            "chapters": [asdict(result) for result in results],
            "errors": errors,
        }
        self._write_json(path, manifest)

    def _write_metadata(self, path: Path, metadata: NovelMetadata) -> None:
        self._write_json(path, metadata_to_dict(metadata))

    @staticmethod
    def _chapter_text(title: str, body: str) -> str:
        return f"{normalize_text(title)}\n\n{body.strip()}\n"

    @staticmethod
    def _is_existing_chapter(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    @staticmethod
    def _write_text_atomic(path: Path, text: str) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _report_progress(
        progress_callback: ProgressCallback | None,
        *,
        current: int,
        total: int,
        status: str,
        title: str,
        source_url: str,
        path: str | None = None,
        error: str | None = None,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            CrawlProgress(
                current=current,
                total=total,
                status=status,
                title=title,
                source_url=source_url,
                path=path,
                error=error,
            )
        )
