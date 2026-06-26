from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

__all__ = [
    "ChapterLink",
    "NovelMetadata",
    "ChapterResult",
    "CrawlError",
    "CrawlResult",
    "CrawlProgress",
    "TranslationState",
    "initial_state",
]


@dataclass(frozen=True)
class ChapterLink:
    title: str
    url: str


@dataclass(frozen=True)
class NovelMetadata:
    title: str
    author: str | None
    source_url: str
    site_name: str
    translated: dict[str, str | None] = field(default_factory=lambda: {"en": None, "vi": None})
    illustration_url: str | None = None


@dataclass(frozen=True)
class ChapterResult:
    index: int
    title: str
    source_url: str
    path: str
    skipped: bool = False


class CrawlError(TypedDict):
    index: int
    url: str
    error: str


@dataclass(frozen=True)
class CrawlResult:
    metadata: NovelMetadata
    chapters: list[ChapterResult]
    output_dir: str
    chapter_output_dir: str
    errors: list[CrawlError] = field(default_factory=list)


@dataclass(frozen=True)
class CrawlProgress:
    current: int
    total: int
    status: str
    title: str
    source_url: str
    path: str | None = None
    error: str | None = None


# Re-export TranslationState and initial_state from the state module
# to preserve the original `from src.models import TranslationState` API.
from src.models.state import TranslationState, initial_state  # noqa: E402
