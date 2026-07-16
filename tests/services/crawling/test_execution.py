from __future__ import annotations

import time
from pathlib import Path

from src.models import ChapterLink, ChapterResult, CrawlError, NovelMetadata
from src.services.crawling.execution import CrawlExecutor
from src.services.crawling.storage import CrawlStorage


class Fetcher:
    def chapter(self, chapter_link: ChapterLink) -> tuple[str, str, str]:
        if chapter_link.url.endswith("1"):
            time.sleep(0.03)
        return chapter_link.title, f"Body for {chapter_link.title}", chapter_link.url


class Storage(CrawlStorage):
    def __init__(self) -> None:
        self.output_root = Path("runtime")
        self.chapter_output_dir = Path("chapters")
        self.written: dict[Path, str] = {}
        self.statuses: list[str] = []

    def prepare(self) -> None:
        pass

    def chapter_path(self, index: int) -> Path:
        return self.chapter_output_dir / f"chapter_{index:03d}.txt"

    def chapter_exists(self, path: Path) -> bool:
        return path in self.written

    def merge_metadata(self, metadata: NovelMetadata) -> NovelMetadata:
        return metadata

    def write_chapter(self, path: Path, title: str, body: str) -> None:
        self.written[path] = f"{title}\n\n{body}\n"

    def write_metadata(self, metadata: NovelMetadata) -> None:
        pass

    def write_manifest(
        self,
        *,
        generated_at: str,
        status: str,
        metadata: NovelMetadata,
        chapter_links: list[ChapterLink],
        results: list[ChapterResult],
        errors: list[CrawlError],
    ) -> None:
        self.statuses.append(status)


def test_parallel_execution_uses_fake_fetcher_and_storage_and_sorts_results() -> None:
    storage = Storage()
    executor = CrawlExecutor(Fetcher(), storage)
    metadata = NovelMetadata(title="Demo", author=None, source_url="url", site_name="demo")
    chapters = [
        ChapterLink(title="Chapter 1", url="https://example.test/1"),
        ChapterLink(title="Chapter 2", url="https://example.test/2"),
    ]

    result = executor.execute(metadata, chapters, workers=2)

    assert [chapter.index for chapter in result.chapters] == [1, 2]
    assert len(storage.written) == 2
    assert storage.statuses[0] == "running"
    assert storage.statuses[-1] == "completed"
