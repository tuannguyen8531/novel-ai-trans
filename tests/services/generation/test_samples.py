import json
from pathlib import Path

import pytest

from src.config import SiteConfig
from src.services.generation.samples import (
    load_known_config,
    load_sample,
    prepare_sample,
)

SAMPLE = {
    "name": "sample",
    "toc_url": "https://example.com/toc",
    "chapter_link_selector": ".chapters a",
    "remove_selectors": ["script", "style"],
    "novel_title_selector": "h1",
}


def test_load_sample_returns_independent_copy(tmp_path: Path) -> None:
    (tmp_path / "example.json").write_text(json.dumps(SAMPLE), encoding="utf-8")

    first = load_sample("example.com", tmp_path)
    second = load_sample("example.com", tmp_path)

    assert first is not None and second is not None
    first["remove_selectors"].append(".mutated")
    assert second["remove_selectors"] == ["script", "style"]


def test_load_known_config_scans_novel_directories(tmp_path: Path) -> None:
    path = tmp_path / "novel" / "config.json"
    path.parent.mkdir()
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")

    assert load_known_config("example.com", tmp_path) == SAMPLE
    assert load_known_config("other.example", tmp_path) is None


def test_load_sample_preserves_failure_for_non_object_json(tmp_path: Path) -> None:
    (tmp_path / "invalid-shape.json").write_text("[]", encoding="utf-8")

    with pytest.raises(AttributeError):
        load_sample("example.com", tmp_path)


def test_load_known_config_preserves_failure_for_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "novel" / "config.json"
    path.parent.mkdir()
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(AttributeError):
        load_known_config("example.com", tmp_path)


def test_prepare_sample_sets_novel_values_and_removes_legacy_metadata_selectors() -> None:
    result = prepare_sample(
        SAMPLE,
        name="novel-1",
        toc_url="https://example.com/novel-1/toc",
        source_url="https://example.com/novel-1",
        novel_info={"title": "Novel", "author": "Author", "summary": "Summary"},
    )

    assert result["name"] == "novel-1"
    assert result["title"] == "Novel"
    assert result["source_url"] == "https://example.com/novel-1"
    assert "novel_title_selector" not in result
    assert "novel_title_selector" in SAMPLE


def test_bundled_samples_are_complete_and_valid() -> None:
    required = {
        "name",
        "toc_url",
        "chapter_link_selector",
        "chapter_content_selector",
        "version",
        "toc_next_selector",
        "toc_expand_selector",
        "chapter_title_selector",
        "remove_selectors",
        "same_domain",
        "reverse_chapter_order",
        "filter_non_chapter_links",
        "request_delay_seconds",
        "timeout_seconds",
        "retry_attempts",
        "retry_backoff_seconds",
        "max_toc_pages",
        "user_agent",
    }
    sample_files = sorted(Path("configs").glob("*.json"))

    assert len(sample_files) >= 4
    for path in sample_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not (required - data.keys()), path.name
        SiteConfig.from_dict(data)


def test_bundled_samples_cover_supported_sites() -> None:
    from urllib.parse import urlparse

    domains = {
        urlparse(json.loads(path.read_text(encoding="utf-8"))["toc_url"]).netloc for path in Path("configs").glob("*.json")
    }

    assert {"ixdzs8.com", "www.69shuba.com", "book.sfacg.com", "kakuyomu.jp"} <= domains
