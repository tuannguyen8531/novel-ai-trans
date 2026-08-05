"""Translate one chapter independently of batch selection."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Event
from typing import Any, Protocol

from src.application.errors import OperationCancelledError
from src.domain.quality import post_check_translation
from src.models.state import TranslationState, initial_state
from src.services.chapters import deduplicate_leading_headings
from src.services.translation.storage import TranslationStorage
from src.utils.text import normalize_paragraph_spacing


class TranslationGraph(Protocol):
    def invoke(self, state: TranslationState) -> Mapping[str, Any]: ...


PublishChapter = Callable[[str, list[str]], None]


def normalize_translation(content: str) -> str:
    """Normalize text exactly as chapter publication expects."""
    return deduplicate_leading_headings(normalize_paragraph_spacing(content))


def translate_chapter(
    input_path: Path,
    *,
    novel: str,
    chapter: int,
    source_language: str,
    target_language: str,
    graph: TranslationGraph,
    storage: TranslationStorage,
    publish: PublishChapter,
    genres: list[str] | None = None,
    clock: Callable[[], float] = time.time,
    cancel_event: Event | None = None,
) -> tuple[bool, int, float, int]:
    """Translate a chapter and return success, output size, duration, and new terms."""
    source_text = deduplicate_leading_headings(storage.read(input_path))
    if not source_text.strip():
        return False, 0, 0, 0

    started_at = clock()
    result = graph.invoke(
        initial_state(
            source_text=source_text,
            source_language=source_language,
            target_language=target_language,
            novel_name=novel,
            chapter_number=chapter,
            genres=genres,
        )
    )
    elapsed = clock() - started_at

    final_text = result.get("final_translation", "")
    normalized_text = normalize_translation(str(final_text))
    new_terms = result.get("new_terms", {})
    glossary_value = result.get("glossary", {})
    glossary = dict(glossary_value) if isinstance(glossary_value, Mapping) else {}
    new_terms_count = len(new_terms) if isinstance(new_terms, Mapping) else 0
    issue_codes = [issue.code for issue in post_check_translation(source_text, normalized_text, glossary)]

    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError("Translation cancelled before publication.")
    publish(normalized_text, issue_codes)
    return True, len(normalized_text), elapsed, new_terms_count
