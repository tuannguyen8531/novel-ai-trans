from __future__ import annotations

import json

from src.config import SiteConfig
from src.models import NovelMetadata
from src.services.crawling.storage import CrawlStorage


def config() -> SiteConfig:
    return SiteConfig.from_dict(
        {
            "name": "demo",
            "toc_url": "https://example.test/book",
            "chapter_link_selector": ".chapters a",
            "chapter_content_selector": ".content",
        }
    )


def test_storage_preserves_user_managed_metadata(tmp_path) -> None:
    storage = CrawlStorage(config(), tmp_path / "runtime", tmp_path / "translated")
    storage.prepare()
    storage.metadata_path.write_text(
        json.dumps(
            {
                "title": "Canonical title",
                "localized": {"vi": {"title": "Tieu de"}},
                "localization_meta": {"vi": {"title": {"provider": "test"}}},
                "source_language": "japanese",
                "custom": "preserved",
            }
        ),
        encoding="utf-8",
    )
    discovered = NovelMetadata(
        title="Discovered title",
        author="Author",
        source_url="https://example.test/book",
        site_name="demo",
    )

    merged = storage.merge_metadata(discovered)
    storage.write_metadata(merged)
    saved = json.loads(storage.metadata_path.read_text(encoding="utf-8"))

    assert merged.title == "Canonical title"
    assert saved["localized"] == {"vi": {"title": "Tieu de"}}
    assert saved["source_language"] == "japanese"
    assert saved["custom"] == "preserved"


def test_storage_writes_normalized_chapter(tmp_path) -> None:
    storage = CrawlStorage(config(), tmp_path / "runtime", tmp_path / "translated")
    storage.prepare()
    path = storage.chapter_path(1)

    storage.write_chapter(path, "  Chapter   1  ", " Body. \n")

    assert path.read_text(encoding="utf-8") == "Chapter 1\n\nBody.\n"


def test_storage_does_not_prepend_title_already_present_in_body(tmp_path) -> None:
    storage = CrawlStorage(config(), tmp_path / "runtime", tmp_path / "translated")
    storage.prepare()
    path = storage.chapter_path(213)

    storage.write_chapter(
        path,
        "第213章 黎知决定主动出击（1W）",
        "第213章 黎知决定主动出击（1W）\n沈元绷着脸。",
    )

    assert path.read_text(encoding="utf-8") == "第213章 黎知决定主动出击（1W）\n\n沈元绷着脸。\n"


def test_storage_prefers_later_heading_when_punctuation_differs(tmp_path) -> None:
    storage = CrawlStorage(config(), tmp_path / "runtime", tmp_path / "translated")
    storage.prepare()
    path = storage.chapter_path(206)

    storage.write_chapter(path, "第206章 黎知，我（1w）", "第206章 黎知，我……（1w）\n正文")

    assert path.read_text(encoding="utf-8") == "第206章 黎知，我……（1w）\n\n正文\n"


def test_storage_deduplicates_unnumbered_title_known_to_crawler(tmp_path) -> None:
    storage = CrawlStorage(config(), tmp_path / "runtime", tmp_path / "translated")
    storage.prepare()
    path = storage.chapter_path(352)

    storage.write_chapter(path, "番外：不完全的陌生人", "番外：不完全的陌生人\n正文")

    assert path.read_text(encoding="utf-8") == "番外：不完全的陌生人\n\n正文\n"
