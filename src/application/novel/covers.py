"""Novel cover upload workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.errors import ApplicationValidationError, PersistenceError, ResourceNotFoundError
from src.application.novel import metadata
from src.application.novel.identity import require_path
from src.paths import resolve_within
from src.services.covers import normalize_cover, remove_superseded_covers, restore_cover, write_cover

_COVER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def save(root: Path, name: str, data: bytes) -> dict[str, Any]:
    """Normalize an uploaded cover, persist ``cover.jpg``, and update metadata."""
    novel_root = require_path(root, name)
    try:
        normalized = normalize_cover(data)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error

    try:
        target, previous = write_cover(novel_root, normalized)
    except OSError as error:
        raise PersistenceError(f"Failed to save novel cover: {error}") from error

    try:
        updated = metadata.update_metadata(root, name, {"illustration_url": "cover.jpg"})
    except Exception:
        restore_cover(target, previous)
        raise

    try:
        remove_superseded_covers(novel_root, target)
    except OSError as error:
        raise PersistenceError(f"Cover was saved, but old cover files could not be removed: {error}") from error
    return updated


def cover(root: Path, name: str) -> Path:
    """Return the first canonical local cover contained by a novel directory."""
    novel_root = require_path(root, name)
    for parts in ((f"cover{suffix}",) for suffix in _COVER_SUFFIXES):
        candidate = resolve_within(novel_root, *parts)
        if candidate.is_file():
            return candidate
    for suffix in _COVER_SUFFIXES:
        try:
            candidate = resolve_within(novel_root, "illustrations", f"cover{suffix}")
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    raise ResourceNotFoundError(f"Local cover not found for novel: {name}")


__all__ = ["cover", "save"]
