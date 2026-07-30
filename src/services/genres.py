"""Filesystem-backed discovery for source-specific genre rule profiles."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from src.domain.language import (
    SUPPORTED_SOURCE_LANGUAGES,
    SUPPORTED_TARGET_LANGUAGES,
    normalize_source_language,
)

RULES_DIR = Path("rules")
_GENRE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _target_genres(rules_dir: Path, target_language: str, source_language: str) -> set[str]:
    directory = rules_dir / target_language / source_language
    if not directory.is_dir():
        raise ValueError(f"Missing genre rule directory: {directory}")

    genres: set[str] = set()
    for path in directory.glob("*.md"):
        genre = path.stem
        if not _GENRE_ID_RE.fullmatch(genre):
            raise ValueError(f"Invalid genre rule filename: {path.name}")
        genres.add(genre)
    return genres


def available_genres(
    source_language: str,
    *,
    rules_dir: Path = RULES_DIR,
) -> list[str]:
    """Return genres available for every supported target for one source."""
    source = normalize_source_language(source_language)
    if source not in SUPPORTED_SOURCE_LANGUAGES:
        raise ValueError(f"Unsupported source language for genres: {source_language!r}")

    by_target = {target: _target_genres(rules_dir, target, source) for target in SUPPORTED_TARGET_LANGUAGES}
    reference_target = next(iter(SUPPORTED_TARGET_LANGUAGES))
    reference = by_target[reference_target]
    if any(genres != reference for genres in by_target.values()):
        details = ", ".join(f"{target}={genres}" for target, genres in sorted(by_target.items()))
        raise ValueError(f"Genre rules differ across targets for {source}: {details}")
    return sorted(reference)


def genre_catalog(*, rules_dir: Path = RULES_DIR) -> dict[str, list[str]]:
    """Return the dynamically discovered source-language genre catalog."""
    return {source: available_genres(source, rules_dir=rules_dir) for source in SUPPORTED_SOURCE_LANGUAGES}


def normalize_genres(
    source_language: str | None,
    genres: Iterable[str] | None,
    *,
    rules_dir: Path = RULES_DIR,
) -> list[str]:
    """Validate, deduplicate, and deterministically order selected genres."""
    if isinstance(genres, str | bytes):
        raise ValueError("Genres must be a list of genre IDs.")

    selected: set[str] = set()
    for raw_genre in genres or ():
        if not isinstance(raw_genre, str):
            raise ValueError("Every genre ID must be a string.")
        genre = raw_genre.strip()
        if not _GENRE_ID_RE.fullmatch(genre):
            raise ValueError(f"Invalid genre: {raw_genre!r}")
        selected.add(genre)

    if not selected:
        return []

    source = normalize_source_language(source_language)
    if not source:
        raise ValueError("Select a source language before choosing genres.")

    available = available_genres(source, rules_dir=rules_dir)
    unknown = sorted(selected.difference(available))
    if unknown:
        raise ValueError(f"Unsupported genre(s) for {source}: {', '.join(unknown)}")
    return [genre for genre in available if genre in selected]


__all__ = ["RULES_DIR", "available_genres", "genre_catalog", "normalize_genres"]
