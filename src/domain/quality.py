"""Deterministic quality checks for translated text."""

import re
from dataclasses import dataclass

from src.domain.illustrations import illustration_marker_counts

SOURCE_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]")
SOURCE_RUN_RE = re.compile(SOURCE_CHAR_RE.pattern + "+")
EXPLAINED_TERM_RE = re.compile(
    r"(?:\(|（|\[|【|「|『|“|'|\")"
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{1,10}"
    r"(?:\)|）|\]|】|」|』|”|'|\")"
)
CODE_FENCE_RE = re.compile(r"```")
QUOTE_MARKS = ('"', "'", "“", "”", "‘", "’", "「", "」", "『", "』")


@dataclass(frozen=True)
class TranslationIssue:
    """A deterministic post-check issue found in translated text."""

    code: str
    severity: str
    message: str


def _count_dialogue_lines(text: str) -> int:
    """Count lines that look like dialogue."""
    return sum(1 for line in text.splitlines() if any(mark in line for mark in QUOTE_MARKS))


def source_language_fragments(text: str) -> list[str]:
    """Return source-language runs still present in text, ignoring explained terminology in brackets."""
    cleaned = EXPLAINED_TERM_RE.sub("", text)
    return SOURCE_RUN_RE.findall(cleaned)


def post_check_translation(
    source: str,
    translation: str,
    glossary: dict[str, str] | None = None,
) -> list[TranslationIssue]:
    """Check a translation for mechanical quality issues that do not require an LLM."""
    issues: list[TranslationIssue] = []
    glossary = glossary or {}
    stripped_translation = translation.strip()

    if not stripped_translation:
        issues.append(TranslationIssue("translation_empty", "error", "Translation is empty."))
        return issues

    if CODE_FENCE_RE.search(translation):
        issues.append(TranslationIssue("contains_code_fence", "error", "Translation contains markdown code fences."))

    if illustration_marker_counts(source) != illustration_marker_counts(translation):
        issues.append(
            TranslationIssue(
                "illustration_marker_mismatch",
                "error",
                "Translation must preserve every [[ILLUSTRATION:...]] marker exactly.",
            )
        )

    source_runs = source_language_fragments(translation)
    source_char_count = sum(len(run) for run in source_runs)
    if source_char_count:
        unique_runs = list(dict.fromkeys(source_runs))
        fragments = ", ".join(run[:20] for run in unique_runs[:10])
        issues.append(
            TranslationIssue(
                "contains_source_language_chars",
                "error" if source_char_count >= 3 else "warning",
                "Translation still contains source-language characters. "
                f"Translate or transliterate every occurrence of these source fragments: {fragments}. "
                "Do not retain source characters, including in notes or parentheses.",
            )
        )

    source_len = len(source.strip())
    translation_len = len(stripped_translation)
    if source_len > 0:
        ratio = translation_len / source_len
        if ratio < 0.25:
            issues.append(TranslationIssue("translation_too_short", "error", f"Translation/source length ratio is {ratio:.2f}."))
        elif ratio > 5.0:
            issues.append(TranslationIssue("translation_too_long", "warning", f"Translation/source length ratio is {ratio:.2f}."))

    source_dialogue_lines = _count_dialogue_lines(source)
    translation_dialogue_lines = _count_dialogue_lines(translation)
    if source_dialogue_lines >= 3 and translation_dialogue_lines < source_dialogue_lines * 0.5:
        issues.append(
            TranslationIssue(
                "possibly_missing_dialogue",
                "warning",
                f"Dialogue-like lines dropped from {source_dialogue_lines} to {translation_dialogue_lines}.",
            )
        )

    for original, translated in glossary.items():
        if original in source and translated and translated not in translation:
            issues.append(
                TranslationIssue(
                    "missing_glossary_term",
                    "warning",
                    f'Glossary term "{original}" should appear as "{translated}".',
                )
            )

    return issues


def has_blocking_issues(issues: list[TranslationIssue]) -> bool:
    """Return True when any post-check issue should force a retry."""
    return any(issue.severity == "error" for issue in issues)
