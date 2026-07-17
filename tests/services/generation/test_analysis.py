import json

import pytest

from src.services.generation.analysis import ConfigAnalyzer, normalize_novel_info, parse_json


class StubLlm:
    @property
    def provider_name(self) -> str:
        return "stub"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        return '```json\n{"selector": ".content"}\n```'


def test_analyzer_calls_llm_and_parses_json() -> None:
    analyzer = ConfigAnalyzer(StubLlm())  # type: ignore[arg-type]

    assert analyzer.ask(system="system", user="user", call_type="config") == {"selector": ".content"}


def test_parse_json_accepts_wrapped_object() -> None:
    assert parse_json('Result: {"selector": "#chapters"}') == {"selector": "#chapters"}


def test_parse_json_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_json("no structured result")


def test_normalize_novel_info_resolves_relative_urls() -> None:
    result = normalize_novel_info(
        {
            "title": " Novel ",
            "author": " Author ",
            "illustration_url": "/cover.jpg",
            "summary": " Summary ",
            "toc_url": "toc/",
        },
        "https://example.com/books/1/",
    )

    assert result == {
        "title": "Novel",
        "author": "Author",
        "illustration_url": "https://example.com/cover.jpg",
        "summary": "Summary",
        "toc_url": "https://example.com/books/1/toc/",
    }


def test_normalize_novel_info_requires_title_and_toc() -> None:
    with pytest.raises(ValueError, match="title"):
        normalize_novel_info(json.loads('{"toc_url": "/toc"}'), "https://example.com/book")
