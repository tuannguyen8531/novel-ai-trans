"""
LangGraph State definition for the Novel Translation Pipeline.

The State flows through every node in the graph:
  detect → title → context → chunk → [translate → review]* → learn → save
"""

from collections.abc import Mapping
from typing import TypedDict


class TranslationState(TypedDict):
    """Central state object for the translation pipeline."""

    # --- Input (set at invocation) ---
    source_text: str  # Raw text initially; title node replaces it with the body to translate
    source_language: str  # "chinese" | "korean" | "japanese" | "" (auto-detect)
    target_language: str  # "vi" | "en"
    novel_name: str  # For glossary lookup
    chapter_number: int  # Current chapter number
    genres: list[str]  # Selected source-specific genre rule profiles
    title_catalog: dict[int, str]  # Source headings used to confirm numbered title series
    source_heading_present: bool  # Whether a numbered source heading was extracted
    source_title: str  # Extracted source heading, if the chapter has one
    source_title_base: str  # Heading text without a confirmed series suffix
    source_title_key: str  # Normalized key used by title translation memory
    source_title_part: int | None  # Confirmed series part number, if any
    source_title_series: bool  # Whether neighboring chapters confirmed a title series
    title_translation_hint: str  # Previously persisted translation for the title base

    # --- Context (loaded by context node) ---
    translation_rules: str  # Bundled and per-novel translation rules
    glossary: dict[str, str]  # Term → Translation mapping
    previous_summary: str  # Summary of previous chapter
    characters: dict  # Active entities, edges, confirmed rules, and pending candidates awaiting learner verdicts

    # --- Chunk Processing ---
    chunks: list[str]  # Text split into translatable chunks
    current_chunk_index: int  # Which chunk we're translating (0-based)
    translated_chunks: list[str]  # Completed translations (parallel to chunks)
    current_translation: str  # Working translation for current chunk

    # --- Review Loop ---
    review_score: float  # Quality score (0.0 - 1.0)
    review_feedback: str  # What to improve
    retry_count: int  # Current retry count for this chunk
    post_check_issues: list[str]  # Deterministic quality issue codes
    post_check_blocking: bool  # Whether deterministic checks require a retry/failure
    quality_reports: list[dict]  # Per-accepted-chunk quality records

    # --- Learning Output ---
    new_terms: dict[str, str]  # New glossary terms extracted
    new_characters: dict  # New entities/edges discovered this chapter
    chapter_summary: str  # Summary for next chapter context
    translated_title_base: str  # Finalized title base returned by the learner

    # --- Final Output ---
    final_translation: str  # Complete translated text


def initial_state(
    source_text: str,
    source_language: str,
    novel_name: str,
    chapter_number: int,
    target_language: str = "vi",
    genres: list[str] | None = None,
    title_catalog: Mapping[int, str] | None = None,
) -> TranslationState:
    """Create a properly initialized TranslationState."""
    return TranslationState(
        source_text=source_text,
        source_language=source_language,
        target_language=target_language,
        novel_name=novel_name,
        chapter_number=chapter_number,
        genres=list(genres or []),
        title_catalog=dict(title_catalog or {}),
        source_heading_present=False,
        source_title="",
        source_title_base="",
        source_title_key="",
        source_title_part=None,
        source_title_series=False,
        title_translation_hint="",
        translation_rules="",
        glossary={},
        previous_summary="",
        characters={},
        chunks=[],
        current_chunk_index=0,
        translated_chunks=[],
        current_translation="",
        review_score=0.0,
        review_feedback="",
        retry_count=0,
        post_check_issues=[],
        post_check_blocking=False,
        quality_reports=[],
        new_terms={},
        new_characters={},
        chapter_summary="",
        translated_title_base="",
        final_translation="",
    )
