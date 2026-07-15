from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.application.crawler import CrawlRequest, run_crawl
from src.application.generator import generate_config, save_generated_config
from src.application.importer import ImportRequest, import_epub_workflow
from src.services.importer import ChapterImportChange


def test_run_crawl_dry_run_returns_preview_without_crawling(tmp_path: Path) -> None:
    crawler = Mock()
    crawler.discover_chapters.return_value = (
        SimpleNamespace(title="Demo Novel", author="Demo Author"),
        [
            SimpleNamespace(title="Chapter 1", url="https://example.com/c1"),
            SimpleNamespace(title="Chapter 2", url="https://example.com/c2"),
        ],
    )

    novel_root = tmp_path / "example"
    novel_root.mkdir()
    (novel_root / "config.json").write_text(
        json.dumps(
            {
                "name": "example",
                "toc_url": "https://example.com/book/",
                "chapter_link_selector": "a.chapter",
                "chapter_content_selector": ".content",
            }
        ),
        encoding="utf-8",
    )

    with patch("src.application.crawler.NovelCrawler", return_value=crawler):
        result = run_crawl(
            CrawlRequest(
                novel="example",
                translated_output=tmp_path,
                dry_run=True,
                max_chapters=1,
            )
        )

    assert result.dry_run is True
    assert result.title == "Demo Novel"
    assert result.author == "Demo Author"
    assert result.total == 1
    assert [(item.index, item.title, item.url) for item in result.preview] == [(1, "Chapter 1", "https://example.com/c1")]
    crawler.discover_chapters.assert_called_once_with()
    assert not crawler.crawl.called


def test_headed_crawl_forces_one_worker_for_shared_browser_page(tmp_path: Path) -> None:
    novel_root = tmp_path / "example"
    novel_root.mkdir()
    (novel_root / "config.json").write_text(
        json.dumps(
            {
                "name": "example",
                "toc_url": "https://example.com/book/",
                "chapter_link_selector": "a.chapter",
                "chapter_content_selector": ".content",
            }
        ),
        encoding="utf-8",
    )
    crawler = Mock()
    crawler.discover_chapters.return_value = (
        SimpleNamespace(title="Demo Novel", author=None),
        [],
    )
    fetcher = Mock()

    with (
        patch("src.application.crawler.NovelCrawler", return_value=crawler),
        patch("src.services.browser.BrowserFetcher", return_value=fetcher) as fetcher_class,
    ):
        run_crawl(
            CrawlRequest(
                novel="example",
                translated_output=tmp_path,
                headed=True,
                workers=4,
                dry_run=True,
            )
        )

    assert fetcher_class.call_args.kwargs["max_concurrency"] == 1
    fetcher.close.assert_called_once_with(suppress_errors=True)


def test_generate_config_without_drafts_dir_does_not_create_draft() -> None:
    llm = object()
    generator = Mock()
    generator.generate.return_value = {
        "name": "demo",
        "toc_url": "https://example.com/book/",
        "chapter_link_selector": "a.chapter",
    }

    with (
        patch("src.application.generator.get_llm", return_value=llm),
        patch("src.application.generator.ConfigGenerator") as generator_cls,
    ):
        generator_cls.return_value = generator
        result = generate_config(url="https://example.com/book/", headed=True)

    generator_cls.assert_called_once_with(llm, use_browser=True, headed=True)
    generator.generate.assert_called_once()
    assert generator.generate.call_args.kwargs["use_cache"] is True
    generator_cls.validate.assert_called_once_with(generator.generate.return_value)
    assert result.draft_id == ""
    assert result.expires_at is None
    assert result.config == generator.generate.return_value


def test_generate_config_no_cache_disables_generator_cache() -> None:
    generator = Mock()
    generator.generate.return_value = {
        "name": "demo",
        "toc_url": "https://example.com/book/toc",
        "chapter_link_selector": "a.chapter",
    }

    with (
        patch("src.application.generator.get_llm", return_value=object()),
        patch("src.application.generator.ConfigGenerator", return_value=generator),
    ):
        generate_config(url="https://example.com/book", no_cache=True)

    assert generator.generate.call_args.kwargs["use_cache"] is False


def test_generate_config_separates_novel_metadata_from_crawler_config() -> None:
    generator = Mock()
    generator.generate.return_value = {
        "name": "demo",
        "toc_url": "https://example.com/book/toc",
        "source_url": "https://example.com/book",
        "title": "示例小说",
        "author": "Demo Author",
        "illustration_url": "https://example.com/cover.jpg",
        "summary": "Demo summary.",
        "chapter_link_selector": "a.chapter",
        "chapter_content_selector": ".content",
    }

    with (
        patch("src.application.generator.get_llm", return_value=object()),
        patch("src.application.generator.ConfigGenerator", return_value=generator),
    ):
        result = generate_config(url="https://example.com/book")

    assert result.metadata["title"] == "示例小说"
    assert result.metadata["author"] == "Demo Author"
    assert result.metadata["illustration_url"] == "https://example.com/cover.jpg"
    assert result.metadata["summary"] == "Demo summary."
    assert result.metadata["source_url"] == "https://example.com/book"
    assert result.metadata["source_language"] == "chinese"
    assert result.config["source_url"] == "https://example.com/book"
    for key in ("title", "author", "illustration_url", "summary"):
        assert key not in result.config


def test_save_generated_config_merges_metadata_without_losing_localizations(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        '{"localized":{"vi":{"title":"Tên Việt"}},"localization_meta":{},"source_language":"chinese"}',
        encoding="utf-8",
    )
    config = {
        "name": "demo",
        "toc_url": "https://example.com/book/toc",
        "source_url": "https://example.com/book",
        "chapter_link_selector": "a.chapter",
        "chapter_content_selector": ".content",
    }
    metadata = {
        "title": "Demo Novel",
        "author": "Demo Author",
        "source_url": "https://example.com/book",
        "illustration_url": "https://example.com/cover.jpg",
        "summary": "Demo summary.",
        "site_name": "demo",
    }

    save_generated_config(
        config,
        metadata=metadata,
        translated_root=translated_root,
    )

    saved_config = json.loads((novel_root / "config.json").read_text(encoding="utf-8"))
    saved_metadata = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    assert "title" not in saved_config
    assert saved_metadata["title"] == "Demo Novel"
    assert saved_metadata["localized"] == {"vi": {"title": "Tên Việt"}}
    assert saved_metadata["source_language"] == "chinese"


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

    with patch("src.application.importer.import_epub", return_value=imported):
        result = import_epub_workflow(ImportRequest(epub_path=Path("demo.epub")), progress_callback=events.append)

    assert (result.retained, result.unchanged, result.overwritten, result.added, result.removed) == (1, 1, 1, 1, 0)
    assert [(change.number, change.title) for change in result.overwritten_chapters] == [(3, "Chapter 3: Revised")]
    assert [event.message for event in events if event.kind == "log"] == [
        "Import chapters: retained 1 · unchanged 1 · overwritten 1 · added 1 · removed 0",
        "Overwritten chapter 3: Chapter 3: Revised",
    ]
