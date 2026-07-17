"""Selector validation and retry policy for crawler config generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.config import DEFAULT_USER_AGENT
from src.services.generation import prompts
from src.services.generation.analysis import ConfigAnalyzer
from src.services.generation.samples import add_novel_info

SelectorPhase = Literal["toc", "chapter"]


@dataclass(frozen=True)
class SelectorResolution:
    selectors: dict[str, Any]
    used_known: bool = False
    known_issues: tuple[str, ...] = ()
    retried: bool = False
    final_issues: tuple[str, ...] = ()


def resolve_selectors(
    analyzer: ConfigAnalyzer,
    soup: BeautifulSoup,
    phase: SelectorPhase,
    clean_html: str,
    known: dict[str, Any] | None = None,
) -> SelectorResolution:
    """Use valid known selectors or run LLM analysis with one retry."""
    known_issues: tuple[str, ...] = ()
    if known:
        selected = selectors_for_phase(known, phase)
        known_issues = tuple(validate_selectors(selected, soup, phase))
        if not known_issues:
            return SelectorResolution(selected, used_known=True)

    system = prompts.TOC if phase == "toc" else prompts.CHAPTER
    retry_system = prompts.RETRY_TOC if phase == "toc" else prompts.RETRY_CHAPTER
    call_type = f"gen_config_{phase}"
    user = f"HTML:\n{clean_html}"
    selected = analyzer.ask(system=system, user=user, call_type=call_type)
    issues = validate_selectors(selected, soup, phase)
    if not issues:
        return SelectorResolution(selected, known_issues=known_issues)

    retry_user = f"Previous issues: {', '.join(issues)}\n\n{user}"
    selected = analyzer.ask(
        system=retry_system,
        user=retry_user,
        call_type=f"{call_type}_retry",
    )
    final_issues = tuple(validate_selectors(selected, soup, phase))
    return SelectorResolution(
        selected,
        known_issues=known_issues,
        retried=True,
        final_issues=final_issues,
    )


def selectors_for_phase(config: dict[str, Any], phase: SelectorPhase) -> dict[str, Any]:
    """Copy only selectors relevant to one analysis phase."""
    if phase == "toc":
        return {
            "chapter_link_selector": config.get("chapter_link_selector"),
            "toc_next_selector": config.get("toc_next_selector"),
            "toc_expand_selector": config.get("toc_expand_selector"),
        }
    return {
        "chapter_title_selector": config.get("chapter_title_selector"),
        "chapter_content_selector": config.get("chapter_content_selector"),
        "remove_selectors": list(config.get("remove_selectors", [])),
    }


def validate_selectors(result: dict[str, Any], soup: BeautifulSoup, phase: SelectorPhase) -> list[str]:
    """Report selectors that match no elements in the supplied HTML."""
    issues: list[str] = []
    if phase == "toc":
        selector = result.get("chapter_link_selector")
        if selector and not soup.select(selector):
            issues.append("chapter_link_selector matches 0 elements")
        return issues

    content_selector = result.get("chapter_content_selector")
    if content_selector and not soup.select(content_selector):
        issues.append("chapter_content_selector matches 0 elements")
    title_selector = result.get("chapter_title_selector")
    if title_selector and not soup.select(title_selector):
        issues.append("chapter_title_selector matches 0 elements")
    return issues


def find_first_chapter(soup: BeautifulSoup, base_url: str, selector: str | None) -> str | None:
    """Find the first same-domain chapter URL matched by a selector."""
    if not selector:
        return None
    base_domain = urlparse(base_url).netloc
    for anchor in soup.select(selector):
        href = anchor.get("href")
        if not isinstance(href, str) or not href:
            continue
        url = urljoin(base_url, href)
        if urlparse(url).netloc == base_domain:
            return url
    return None


def derive_name(url: str) -> str:
    """Derive a short novel slug from its source URL."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    return parts[-1] if parts else parsed.netloc.replace(".", "-")


def build_config(
    toc_url: str,
    name: str,
    toc: dict[str, Any],
    chapter: dict[str, Any],
    *,
    source_url: str | None = None,
    novel_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete crawler config from analyzed selectors."""
    remove = list(chapter.get("remove_selectors") or ["script", "style"])
    if "script" not in remove:
        remove.insert(0, "script")
    if "style" not in remove:
        remove.insert(1, "style")
    deduped = list(dict.fromkeys(remove))
    toc_next = toc.get("toc_next_selector")

    def value_or_default(value: Any, default: Any) -> Any:
        return value if value is not None else default

    config = {
        "name": name,
        "toc_url": toc_url,
        "version": 1,
        "chapter_link_selector": value_or_default(toc.get("chapter_link_selector"), "a"),
        "toc_next_selector": toc_next,
        "toc_expand_selector": toc.get("toc_expand_selector"),
        "chapter_title_selector": chapter.get("chapter_title_selector"),
        "chapter_content_selector": value_or_default(chapter.get("chapter_content_selector"), "body"),
        "remove_selectors": deduped,
        "same_domain": True,
        "reverse_chapter_order": False,
        "filter_non_chapter_links": True,
        "request_delay_seconds": 2.0,
        "timeout_seconds": 30,
        "max_toc_pages": 1 if toc_next is None else 50,
        "user_agent": DEFAULT_USER_AGENT,
    }
    if source_url is not None:
        add_novel_info(config, source_url, novel_info or {})
    return config


__all__ = [
    "SelectorResolution",
    "build_config",
    "derive_name",
    "find_first_chapter",
    "resolve_selectors",
    "selectors_for_phase",
    "validate_selectors",
]
