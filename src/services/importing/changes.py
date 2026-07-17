"""EPUB import chapter change calculations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ChapterStatus = Literal["added", "unchanged", "overwritten"]


@dataclass(frozen=True)
class ChapterImportChange:
    number: int
    title: str


@dataclass(frozen=True)
class ImportChanges:
    retained: tuple[int, ...]
    unchanged: tuple[int, ...]
    overwritten: tuple[ChapterImportChange, ...]
    added: tuple[int, ...]
    removed: tuple[int, ...]


def classify_chapter(path: Path, imported_text: str) -> ChapterStatus:
    if not path.exists():
        return "added"
    if path.read_text(encoding="utf-8") == imported_text:
        return "unchanged"
    return "overwritten"


def calculate_changes(
    existing_chapters: set[int],
    used_chapters: set[int],
    *,
    keep_existing: bool,
    unchanged: list[int],
    overwritten: list[ChapterImportChange],
    added: list[int],
) -> ImportChanges:
    remaining = sorted(existing_chapters - used_chapters)
    return ImportChanges(
        retained=tuple(remaining if keep_existing else ()),
        unchanged=tuple(sorted(unchanged)),
        overwritten=tuple(sorted(overwritten, key=lambda change: change.number)),
        added=tuple(sorted(added)),
        removed=tuple(() if keep_existing else remaining),
    )


__all__ = ["ChapterImportChange", "ChapterStatus", "ImportChanges", "calculate_changes", "classify_chapter"]
