from __future__ import annotations

import json
from pathlib import Path

from src.application.crawl.generator import _generate_config_data
from src.application.progress import ProgressEvent
from src.services.generation.analysis import ConfigAnalyzer
from src.services.generation.cache import HtmlCache
from src.services.generation.fetching import PageAcquirer
from src.services.http import FetchResponse


class StaticFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, body=self.pages[url], content_type="text/html")


class GenerationLlm:
    def __init__(self, toc_url: str) -> None:
        self.toc_url = toc_url
        self.call_types: list[str] = []

    @property
    def provider_name(self) -> str:
        return "generation"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        self.call_types.append(call_type)
        if call_type == "gen_novel_info":
            return json.dumps(
                {
                    "title": "Canonical Title",
                    "author": "Canonical Author",
                    "illustration_url": "/cover.jpg",
                    "summary": "Canonical summary.",
                    "toc_url": self.toc_url,
                }
            )
        if call_type == "gen_config_toc":
            return json.dumps(
                {
                    "chapter_link_selector": ".chapters a",
                    "toc_next_selector": None,
                    "toc_expand_selector": None,
                }
            )
        if call_type == "gen_config_chapter":
            return json.dumps(
                {
                    "chapter_title_selector": "h1",
                    "chapter_content_selector": ".content",
                    "remove_selectors": ["script", "style", "h1"],
                }
            )
        raise AssertionError(f"Unexpected call type: {call_type}")


def test_generation_short_circuits_selector_analysis_for_bundled_sample(tmp_path: Path) -> None:
    source_url = "https://example.com/books/123"
    toc_url = "https://example.com/books/123/toc"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "example.json").write_text(
        json.dumps(
            {
                "name": "example",
                "toc_url": "https://example.com/sample-toc",
                "chapter_link_selector": ".sample a",
                "chapter_content_selector": ".sample-content",
            }
        ),
        encoding="utf-8",
    )
    llm = GenerationLlm(toc_url)
    acquirer = PageAcquirer(
        StaticFetcher({source_url: "<html><h1>Novel</h1></html>"}),
        HtmlCache(tmp_path / "cache", enabled=False),
    )
    events: list[ProgressEvent] = []

    result = _generate_config_data(
        source_url,
        analyzer=ConfigAnalyzer(llm),  # type: ignore[arg-type]
        acquirer=acquirer,
        translated_root=tmp_path / "translated",
        samples_dir=samples_dir,
        name=None,
        use_samples=True,
        progress_callback=events.append,
    )

    assert result["name"] == "123"
    assert result["toc_url"] == toc_url
    assert result["chapter_link_selector"] == ".sample a"
    assert result["source_url"] == source_url
    assert result["title"] == "Canonical Title"
    assert llm.call_types == ["gen_novel_info"]
    assert any("bundled sample" in str(event.message) for event in events)


def test_generation_can_ignore_samples_and_analyze_live_html(tmp_path: Path) -> None:
    source_url = "https://example.com/books/123"
    toc_url = "https://example.com/books/123/toc"
    chapter_url = "https://example.com/books/123/1"
    llm = GenerationLlm(toc_url)
    pages = {
        source_url: "<html><h1>Novel</h1></html>",
        toc_url: "<html><div class='chapters'><a href='1'>One</a></div></html>",
        chapter_url: "<html><h1>One</h1><section class='content'>Story</section></html>",
    }

    result = _generate_config_data(
        source_url,
        analyzer=ConfigAnalyzer(llm),  # type: ignore[arg-type]
        acquirer=PageAcquirer(
            StaticFetcher(pages),
            HtmlCache(tmp_path / "cache", enabled=False),
        ),
        translated_root=tmp_path / "translated",
        samples_dir=tmp_path / "missing-samples",
        name="demo",
        use_samples=False,
        progress_callback=None,
    )

    assert result["name"] == "demo"
    assert result["chapter_link_selector"] == ".chapters a"
    assert result["chapter_content_selector"] == ".content"
    assert result["illustration_url"] == "https://example.com/cover.jpg"
    assert llm.call_types == ["gen_novel_info", "gen_config_toc", "gen_config_chapter"]
