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
