"""Pure chapter selection rules for translation batches."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from src.application.translation.models import TranslationRequest


def select_chapters(
    request: TranslationRequest,
    available: Iterable[int],
    translated: Collection[int],
    checkpoint: Mapping[str, list[int]],
) -> list[int]:
    """Select chapters using caller-supplied storage and checkpoint information."""
    chapters = sorted(available)
    if not request.force:
        chapters = [chapter for chapter in chapters if chapter not in translated]
    if request.start_chapter > 0:
        chapters = [chapter for chapter in chapters if chapter >= request.start_chapter]
    if request.end_chapter > 0:
        chapters = [chapter for chapter in chapters if chapter <= request.end_chapter]

    if request.failed_only:
        failed = set(checkpoint.get("failed", []))
        chapters = [chapter for chapter in chapters if chapter in failed]
    elif request.resume:
        completed = set(checkpoint.get("completed", []))
        chapters = [chapter for chapter in chapters if chapter not in completed]

    if request.limit > 0:
        chapters = chapters[: request.limit]
    return chapters
