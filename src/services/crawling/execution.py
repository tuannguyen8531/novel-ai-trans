"""Concurrent crawl execution, progress, cancellation, and failure policy."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Protocol

from src.models import ChapterLink, ChapterResult, CrawlError, CrawlProgress, CrawlResult, NovelMetadata
from src.services.crawling.storage import CrawlStorage
from src.services.http import FetchError

ProgressCallback = Callable[[CrawlProgress], None]
CONSECUTIVE_FAILURE_LIMIT = 5


class ChapterFetcher(Protocol):
    def chapter(self, chapter_link: ChapterLink) -> tuple[str, str, str]: ...


class ConsecutiveFailureError(FetchError):
    """Raised when too many chapter fetches fail in a row and the crawl aborts."""


class CrawlExecutor:
    """Execute a prepared chapter plan against fetch and storage collaborators."""

    def __init__(self, chapter_fetcher: ChapterFetcher, storage: CrawlStorage) -> None:
        self.chapter_fetcher = chapter_fetcher
        self.storage = storage

    def execute(
        self,
        metadata: NovelMetadata,
        chapter_links: list[ChapterLink],
        *,
        max_chapters: int | None = None,
        fail_fast: bool = False,
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
        workers: int = 1,
        cancel_event: threading.Event | None = None,
    ) -> CrawlResult:
        self.storage.prepare()
        metadata = self.storage.merge_metadata(metadata)
        results: list[ChapterResult] = []
        errors: list[CrawlError] = []
        generated_at = self.storage.generated_at()
        fetched_count = 0

        self.storage.write_metadata(metadata)
        self._write_manifest(generated_at, "running", metadata, chapter_links, results, errors)
        planned_fetch_total = 0
        for plan_index, _chapter_link in enumerate(chapter_links, start=1):
            chapter_path = self.storage.chapter_path(plan_index)
            if not overwrite and self.storage.chapter_exists(chapter_path):
                continue
            planned_fetch_total += 1
            if max_chapters is not None and planned_fetch_total >= max_chapters:
                break

        def write_running_manifest(*, status: str = "running") -> None:
            self._write_manifest(generated_at, status, metadata, chapter_links, results, errors)

        def fetch_chapter(
            index: int,
            progress_index: int,
            chapter_link: ChapterLink,
            chapter_path: Path,
        ) -> ChapterResult:
            self._report_progress(
                progress_callback,
                current=progress_index - 1,
                total=planned_fetch_total,
                status="started",
                title=chapter_link.title,
                source_url=chapter_link.url,
                path=str(chapter_path),
            )
            title, body, final_url = self.chapter_fetcher.chapter(chapter_link)
            self.storage.write_chapter(chapter_path, title, body)
            return ChapterResult(index=index, title=title, source_url=final_url, path=str(chapter_path))

        if workers < 1:
            raise ValueError("Number of workers must be at least 1.")

        effective_workers = 1 if fail_fast else workers
        next_chapter = 0
        pending: dict[Future[ChapterResult], tuple[int, int, ChapterLink]] = {}
        attempted_chapters: dict[int, tuple[ChapterLink, Path]] = {}
        chapter_outcomes: dict[int, bool] = {}
        next_outcome_index = 1
        consecutive_failures = 0
        scheduled_fetch_count = 0
        completed_fetch_count = 0

        def record_chapter_outcome(index: int, *, success: bool) -> bool:
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

        def raise_if_too_many_consecutive_failures() -> None:
            results.sort(key=lambda result: result.index)
            errors.sort(key=lambda error: error["index"])
            write_running_manifest(status="failed")
            for future in pending:
                future.cancel()
            raise ConsecutiveFailureError(
                f"Stopped after {CONSECUTIVE_FAILURE_LIMIT} consecutive chapter failures. Progress was saved to manifest.json."
            )

        def is_cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def fill_pending(executor: ThreadPoolExecutor) -> None:
            nonlocal next_chapter, planned_fetch_total, scheduled_fetch_count
            while next_chapter < len(chapter_links):
                if is_cancelled() or len(pending) >= effective_workers:
                    return
                if max_chapters is not None and fetched_count + len(pending) >= max_chapters:
                    return

                index = next_chapter + 1
                chapter_link = chapter_links[next_chapter]
                next_chapter += 1
                chapter_path = self.storage.chapter_path(index)

                if not overwrite and self.storage.chapter_exists(chapter_path):
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
                    write_running_manifest()
                    if record_chapter_outcome(index, success=True):
                        raise_if_too_many_consecutive_failures()
                    continue

                scheduled_fetch_count += 1
                progress_index = scheduled_fetch_count
                if scheduled_fetch_count > planned_fetch_total:
                    planned_fetch_total = scheduled_fetch_count
                attempted_chapters[index] = (chapter_link, chapter_path)
                future = executor.submit(fetch_chapter, index, progress_index, chapter_link, chapter_path)
                pending[future] = (index, progress_index, chapter_link)

        executor = ThreadPoolExecutor(max_workers=effective_workers)
        cancelled = False
        try:
            fill_pending(executor)
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    index, _progress_index, chapter_link = pending[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        completed_fetch_count += 1
                        error_text = str(error)
                        errors.append({"index": index, "url": chapter_link.url, "error": error_text})
                        self._report_progress(
                            progress_callback,
                            current=completed_fetch_count,
                            total=planned_fetch_total,
                            status="failed",
                            title=chapter_link.title,
                            source_url=chapter_link.url,
                            error=error_text,
                        )
                        write_running_manifest(status="failed" if fail_fast else "running")
                        if fail_fast:
                            raise
                        pending.pop(future, None)
                        if record_chapter_outcome(index, success=False):
                            raise_if_too_many_consecutive_failures()
                    else:
                        results.append(result)
                        fetched_count += 1
                        completed_fetch_count += 1
                        self._report_progress(
                            progress_callback,
                            current=completed_fetch_count,
                            total=planned_fetch_total,
                            status="fetched",
                            title=result.title,
                            source_url=result.source_url,
                            path=result.path,
                        )
                        write_running_manifest()
                        pending.pop(future, None)
                        if record_chapter_outcome(index, success=True):
                            raise_if_too_many_consecutive_failures()
                if is_cancelled():
                    cancelled = True
                    break
                fill_pending(executor)
        except KeyboardInterrupt:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            self._drain_completed(pending, results, errors)
            fetched_count += self._recover_written(attempted_chapters, results)
            results.sort(key=lambda result: result.index)
            errors.sort(key=lambda error: error["index"])
            self._write_manifest(generated_at, "interrupted", metadata, chapter_links, results, errors)
            raise
        finally:
            executor.shutdown(wait=True)

        if cancelled:
            fetched_count += self._drain_completed(pending, results, errors)
            fetched_count += self._recover_written(attempted_chapters, results)

        results.sort(key=lambda result: result.index)
        errors.sort(key=lambda error: error["index"])
        final_status = "cancelled" if cancelled else "completed"
        self._write_manifest(generated_at, final_status, metadata, chapter_links, results, errors)
        return CrawlResult(
            metadata=metadata,
            chapters=results,
            output_dir=str(self.storage.output_root),
            chapter_output_dir=str(self.storage.chapter_output_dir),
            errors=list(errors),
            cancelled=cancelled,
        )

    def _write_manifest(
        self,
        generated_at: str,
        status: str,
        metadata: NovelMetadata,
        chapter_links: list[ChapterLink],
        results: list[ChapterResult],
        errors: list[CrawlError],
    ) -> None:
        self.storage.write_manifest(
            generated_at=generated_at,
            status=status,
            metadata=metadata,
            chapter_links=chapter_links,
            results=results,
            errors=errors,
        )

    @staticmethod
    def _drain_completed(
        pending: dict[Future[ChapterResult], tuple[int, int, ChapterLink]],
        results: list[ChapterResult],
        errors: list[CrawlError],
    ) -> int:
        fetched = 0
        for future, (index, _progress_index, chapter_link) in list(pending.items()):
            if future.cancelled() or not future.done():
                continue
            try:
                result = future.result()
            except Exception as error:
                errors.append({"index": index, "url": chapter_link.url, "error": str(error)})
            else:
                results.append(result)
                fetched += 1
        return fetched

    def _recover_written(
        self,
        attempted_chapters: dict[int, tuple[ChapterLink, Path]],
        results: list[ChapterResult],
    ) -> int:
        fetched = 0
        recorded_indexes = {result.index for result in results}
        for index, (chapter_link, chapter_path) in attempted_chapters.items():
            if index in recorded_indexes or not self.storage.chapter_exists(chapter_path):
                continue
            results.append(
                ChapterResult(
                    index=index,
                    title=chapter_link.title,
                    source_url=chapter_link.url,
                    path=str(chapter_path),
                )
            )
            fetched += 1
        return fetched

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
