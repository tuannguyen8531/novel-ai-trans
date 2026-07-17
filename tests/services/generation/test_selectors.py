import json

from bs4 import BeautifulSoup

from src.services.generation.analysis import ConfigAnalyzer
from src.services.generation.selectors import build_config, find_first_chapter, resolve_selectors


class RetryLlm:
    def __init__(self) -> None:
        self.call_types: list[str] = []

    @property
    def provider_name(self) -> str:
        return "retry"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        self.call_types.append(call_type)
        selector = ".missing" if call_type == "gen_config_toc" else ".chapters a"
        return json.dumps({"chapter_link_selector": selector})


def test_selector_validation_retries_once() -> None:
    llm = RetryLlm()
    soup = BeautifulSoup("<div class='chapters'><a href='1'>One</a></div>", "html.parser")

    result = resolve_selectors(ConfigAnalyzer(llm), soup, "toc", str(soup))  # type: ignore[arg-type]

    assert result.selectors["chapter_link_selector"] == ".chapters a"
    assert result.retried
    assert not result.final_issues
    assert llm.call_types == ["gen_config_toc", "gen_config_toc_retry"]


def test_valid_known_selectors_skip_llm() -> None:
    soup = BeautifulSoup("<div class='chapters'><a href='1'>One</a></div>", "html.parser")

    result = resolve_selectors(
        ConfigAnalyzer(RetryLlm()),  # type: ignore[arg-type]
        soup,
        "toc",
        str(soup),
        {"chapter_link_selector": ".chapters a"},
    )

    assert result.used_known
    assert result.selectors["chapter_link_selector"] == ".chapters a"


def test_find_first_chapter_rejects_external_links() -> None:
    soup = BeautifulSoup(
        "<a class='chapter' href='https://other.example/1'>Other</a><a class='chapter' href='/2'>Two</a>",
        "html.parser",
    )

    assert find_first_chapter(soup, "https://example.com/toc", "a.chapter") == "https://example.com/2"


def test_find_first_chapter_treats_none_as_no_selector() -> None:
    soup = BeautifulSoup("<none href='/unexpected'>Unexpected</none>", "html.parser")

    assert find_first_chapter(soup, "https://example.com/toc", None) is None


def test_build_config_normalizes_defaults_and_deduplicates_remove_selectors() -> None:
    result = build_config(
        "https://example.com/toc",
        "example",
        {"chapter_link_selector": ".chapters a", "toc_next_selector": ".next"},
        {"chapter_content_selector": ".content", "remove_selectors": ["style", "script", "style"]},
    )

    assert result["max_toc_pages"] == 50
    assert result["remove_selectors"] == ["style", "script"]
    assert result["chapter_content_selector"] == ".content"


def test_build_config_preserves_empty_selectors() -> None:
    result = build_config(
        "https://example.com/toc",
        "example",
        {"chapter_link_selector": ""},
        {"chapter_content_selector": ""},
    )

    assert result["chapter_link_selector"] == ""
    assert result["chapter_content_selector"] == ""


def test_build_config_defaults_only_none_selectors() -> None:
    result = build_config(
        "https://example.com/toc",
        "example",
        {"chapter_link_selector": None},
        {"chapter_content_selector": None},
    )

    assert result["chapter_link_selector"] == "a"
    assert result["chapter_content_selector"] == "body"
