"""LLM invocation and JSON analysis for crawler config generation."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.services.llm.base import BaseProvider


class ConfigAnalyzer:
    """Ask an LLM for structured config-generation analysis."""

    def __init__(self, llm: BaseProvider) -> None:
        self._llm = llm

    def ask(self, *, system: str, user: str, call_type: str) -> dict[str, Any]:
        raw = self._llm.generate(system, user, call_type)
        return parse_json(raw)


def clean_novel_html(html: str, *, max_length: int = 60_000) -> str:
    """Remove noisy markup while preserving metadata-bearing attributes."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, svg, iframe"):
        tag.decompose()
    cleaned = str(soup)
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "\n<!-- truncated -->"
    return cleaned


def normalize_novel_info(info: dict[str, Any], source_url: str) -> dict[str, Any]:
    """Validate novel metadata and resolve relative URLs."""

    def text(key: str, *, required: bool = False) -> str | None:
        value = info.get(key)
        if value is None:
            if required:
                raise ValueError(f"LLM did not return a {key} for the novel page.")
            return None
        result = str(value).strip()
        if not result and required:
            raise ValueError(f"LLM did not return a {key} for the novel page.")
        return result or None

    def absolute_url(key: str, *, required: bool = False) -> str | None:
        value = text(key)
        if value is None:
            if required:
                raise ValueError(f"LLM did not return a {key} for the novel page.")
            return None
        result = urljoin(source_url, value)
        if urlparse(result).scheme not in {"http", "https"}:
            if required:
                raise ValueError(f"LLM returned an invalid {key}: {value!r}")
            return None
        return result

    return {
        "title": text("title", required=True),
        "author": text("author"),
        "illustration_url": absolute_url("illustration_url"),
        "summary": text("summary"),
        "toc_url": absolute_url("toc_url", required=True),
    }


def parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response."""
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    braced = re.search(r"\{.*}", text, re.DOTALL)
    if braced:
        try:
            return json.loads(braced.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"LLM output is not valid JSON:\n{text[:500]}")


__all__ = ["ConfigAnalyzer", "clean_novel_html", "normalize_novel_info", "parse_json"]
