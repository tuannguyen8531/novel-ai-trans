"""Translation request and result values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranslationRequest:
    novel: str
    source_language: str = ""
    target_language: str | None = None
    provider: str | None = None
    enable_review: bool = False
    enable_summary: bool = False
    start_chapter: int = 0
    end_chapter: int = 0
    force: bool = False
    resume: bool = False
    failed_only: bool = False
    limit: int = 0
    dry_run: bool = False


@dataclass
class TranslationResult:
    novel: str
    total: int
    success: int
    failed: int
    skipped: bool
    dry_run: bool
    chapters_attempted: list[int]
    failures: list[int]
    started_at: float
    finished_at: float
    cancelled: bool = False
