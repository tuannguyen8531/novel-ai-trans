"""Domain rules for glossary term selection."""

import re

MIN_TERM_FREQUENCY = 3
SOURCE_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]")


def count_occurrences(text: str, term: str) -> int:
    """Count case-insensitive occurrences of term."""
    if not term or len(term) < 2:
        return 0
    escaped = re.escape(term)
    return len(re.findall(escaped, text, re.IGNORECASE))


def filter_terms_by_frequency(text: str, terms: dict[str, str], min_count: int) -> dict[str, str]:
    """Keep only terms that appear at least min_count times in the text."""
    filtered = {}
    for original, translation in terms.items():
        count = count_occurrences(text, original)
        if count >= min_count:
            filtered[original] = translation
    return filtered


def filter_extracted_terms(
    source_text: str,
    terms: dict[str, str],
    *,
    translated_text: str | None = None,
    existing_terms: dict[str, str] | None = None,
) -> dict[str, str]:
    """Keep new LLM-extracted term pairs grounded in source and translation."""
    filtered = {}
    translated_folded = translated_text.casefold() if translated_text is not None else None
    existing_keys = {original.casefold() for original in (existing_terms or {}) if isinstance(original, str)}
    for original, translation in terms.items():
        if not isinstance(original, str) or not isinstance(translation, str):
            continue
        original = original.strip()
        translation = translation.strip()
        translation_is_grounded = translated_folded is None or translation.casefold() in translated_folded
        if (
            original
            and translation
            and original.casefold() not in existing_keys
            and original in source_text
            and not SOURCE_CHAR_RE.search(translation)
            and translation_is_grounded
        ):
            filtered[original] = translation
    return filtered
