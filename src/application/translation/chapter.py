"""Translate one chapter independently of batch selection."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from src.models.state import TranslationState, initial_state
from src.services.chapters import deduplicate_leading_headings
from src.services.translation.reports import ReportStore
from src.services.translation.storage import TranslationStorage
from src.utils.text import normalize_paragraph_spacing


class TranslationGraph(Protocol):
    def invoke(self, state: TranslationState) -> Mapping[str, Any]: ...


def translate_chapter(
    input_path: Path,
    *,
    novel: str,
    chapter: int,
    source_language: str,
    target_language: str,
    graph: TranslationGraph,
    output_dir: Path,
    report_path: Path,
    storage: TranslationStorage,
    reports: ReportStore,
    genres: list[str] | None = None,
    clock: Callable[[], float] = time.time,
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
    normalized_text = deduplicate_leading_headings(normalize_paragraph_spacing(str(final_text)))
    new_terms = result.get("new_terms", {})
    new_characters = result.get("new_characters", {})
    quality_reports = result.get("quality_reports", [])
    new_terms_count = len(new_terms) if isinstance(new_terms, Mapping) else 0
    entities = new_characters.get("entities", {}) if isinstance(new_characters, Mapping) else {}

    storage.write(output_dir, chapter, normalized_text)
    reports.save(
        report_path,
        {
            "chapter": chapter,
            "target_language": target_language,
            "output_chars": len(normalized_text),
            "elapsed_seconds": round(elapsed, 3),
            "new_terms_count": new_terms_count,
            "new_characters_count": len(entities) if isinstance(entities, Mapping) else 0,
            "chunks": quality_reports,
        },
    )
    return True, len(normalized_text), elapsed, new_terms_count
