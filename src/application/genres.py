"""Application validation for source-specific genre rule profiles."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from src.application.errors import ApplicationValidationError
from src.services import genres as genre_rules

RULES_DIR = genre_rules.RULES_DIR


def available_genres(
    source_language: str,
    *,
    rules_dir: Path = RULES_DIR,
) -> list[str]:
    """Return genres available for every target as an application value."""
    try:
        return genre_rules.available_genres(source_language, rules_dir=rules_dir)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error


def genre_catalog(*, rules_dir: Path = RULES_DIR) -> dict[str, list[str]]:
    """Return the discovered catalog as an application value."""
    try:
        return genre_rules.genre_catalog(rules_dir=rules_dir)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error


def normalize_genres(
    source_language: str | None,
    genres: Iterable[str] | None,
    *,
    rules_dir: Path = RULES_DIR,
) -> list[str]:
    """Validate selected genres as an application value."""
    try:
        return genre_rules.normalize_genres(
            source_language,
            genres,
            rules_dir=rules_dir,
        )
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error


__all__ = ["RULES_DIR", "available_genres", "genre_catalog", "normalize_genres"]
