from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.application.crawl import CrawlRequest, ImportRequest, generate_config, import_epub_workflow, run_crawl
from src.services.importer import ChapterImportChange


def test_run_crawl_dry_run_returns_preview_without_crawling() -> None:
    crawler = Mock()
    crawler.discover_chapters.return_value = (
        SimpleNamespace(title="Demo Novel", author="Demo Author"),
        [
            SimpleNamespace(title="Chapter 1", url="https://example.com/c1"),
            SimpleNamespace(title="Chapter 2", url="https://example.com/c2"),
        ],
    )

    with patch("src.application.crawl.NovelCrawler", return_value=crawler):
        result = run_crawl(CrawlRequest(target="example", dry_run=True, max_chapters=1))

    assert result.dry_run is True
    assert result.title == "Demo Novel"
    assert result.author == "Demo Author"
    assert result.total == 1
    assert [(item.index, item.title, item.url) for item in result.preview] == [(1, "Chapter 1", "https://example.com/c1")]
    crawler.discover_chapters.assert_called_once_with()
    assert not crawler.crawl.called


def test_generate_config_without_drafts_dir_does_not_create_draft() -> None:
    llm = object()
    generator = Mock()
    generator.generate.return_value = {
        "name": "demo",
        "start_url": "https://example.com/book/",
        "chapter_link_selector": "a.chapter",
    }

    with (
        patch("src.application.crawl.get_llm", return_value=llm),
        patch("src.application.crawl.ConfigGenerator") as generator_cls,
    ):
        generator_cls.return_value = generator
        result = generate_config(url="https://example.com/book/", headed=True)

    generator_cls.assert_called_once_with(llm, use_browser=True, headed=True)
    generator.generate.assert_called_once()
    generator_cls.validate.assert_called_once_with(generator.generate.return_value)
    assert result.draft_id == ""
    assert result.expires_at is None
    assert result.config == generator.generate.return_value


def test_import_workflow_reports_chapter_changes_in_result_and_logs() -> None:
    imported = SimpleNamespace(
        metadata=SimpleNamespace(title="Demo"),
        chapters=[object(), object(), object()],
        illustrations=[object()],
        output_dir="translated/demo",
        retained_chapters=(1,),
        unchanged_chapters=(2,),
        overwritten_chapters=(ChapterImportChange(number=3, title="Chapter 3: Revised"),),
        added_chapters=(4,),
        removed_chapters=(),
        warnings=(),
    )
    events = []

    with patch("src.application.crawl.import_epub", return_value=imported):
        result = import_epub_workflow(ImportRequest(epub_path=Path("demo.epub")), progress_callback=events.append)

    assert (result.retained, result.unchanged, result.overwritten, result.added, result.removed) == (1, 1, 1, 1, 0)
    assert [(change.number, change.title) for change in result.overwritten_chapters] == [(3, "Chapter 3: Revised")]
    assert [event.message for event in events if event.kind == "log"] == [
        "Import chapters: retained 1 · unchanged 1 · overwritten 1 · added 1 · removed 0",
        "Overwritten chapter 3: Chapter 3: Revised",
    ]
