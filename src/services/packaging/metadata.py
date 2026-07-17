"""EPUB metadata loading and title or author resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.domain.language import normalize_target_language
from src.services.metadata import localized_value


def load_metadata(metadata_path: Path) -> dict[str, Any]:
    """Load metadata from an explicit path, returning empty data on failure."""
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}


def resolve_book_title(metadata: dict[str, Any], target_language: str, fallback_novel_name: str) -> str:
    """Resolve the title using the existing target-language fallback chain."""
    target = normalize_target_language(target_language)
    title = localized_value(metadata, target, "title")
    if title:
        return title
    return fallback_novel_name.replace("-", " ").title()


def resolve_book_author(metadata: dict[str, Any], fallback_author: str) -> str:
    """Resolve the author, treating null or blank values as missing."""
    author = metadata.get("author")
    if author is None:
        return fallback_author
    author_text = str(author).strip()
    return author_text or fallback_author


__all__ = ["load_metadata", "resolve_book_author", "resolve_book_title"]
