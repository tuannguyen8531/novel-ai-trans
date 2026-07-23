"""
Context Node — Load translation rules, glossary, and previous chapter summaries.

Loads rules in order:
1. rules/{target}/common.md (or legacy rules/common.md)
2. rules/{target}/{language}.md (or legacy rules/{language}.md)

For chapter summaries, only loads the last 3 chapters for conciseness.
"""

import logging
from pathlib import Path

from src.config import config
from src.domain.glossary import select_active_glossary_terms
from src.models.state import TranslationState
from src.services.glossary.memory import load_recent_chapter_summaries
from src.services.glossary.repository import (
    get_active_context_with_candidates,
    load_glossary,
)
from src.services.metadata import load_source_language

RULES_DIR = Path("rules")
MAX_RECENT_SUMMARIES = 3  # Only keep context from last 3 chapters
_logger = logging.getLogger("novel_ai_trans.job")


def context_node(state: TranslationState) -> dict:
    """Load all context needed for translation."""
    language = state["source_language"]
    target_language = state.get("target_language", "vi")
    novel_name = state["novel_name"]
    chapter_number = state["chapter_number"]
    source_text = state.get("source_text", "")

    # 0. Load source language from metadata if not specified by user
    if not language:
        language = load_source_language(novel_name)
        if language:
            _logger.info(
                "Loaded source language from metadata: %s",
                language,
                extra={
                    "presentation_event": "cli_message",
                    "presentation_message": f"  🌐 Loaded source language from metadata: {language}",
                },
            )

    # 1. Load translation rules (common + language-specific)
    rules_parts = []

    common_rules_file = RULES_DIR / target_language / "common.md"
    if not common_rules_file.exists():
        common_rules_file = RULES_DIR / "common.md"
    if common_rules_file.exists():
        rules_parts.append(common_rules_file.read_text(encoding="utf-8"))

    lang_rules_file = RULES_DIR / target_language / f"{language}.md"
    if not lang_rules_file.exists():
        lang_rules_file = RULES_DIR / f"{language}.md"
    if lang_rules_file.exists():
        rules_parts.append(lang_rules_file.read_text(encoding="utf-8"))

    # Load novel-specific rules if they exist
    if config.translated_dir:
        novel_rules_file = Path(config.translated_dir) / novel_name / "rules.md"
        if novel_rules_file.exists():
            content = novel_rules_file.read_text(encoding="utf-8").strip()
            if content:
                rules_parts.append(content)

    rules = "\n\n".join(rules_parts)

    # 2. Load glossary terms used in this chapter.
    glossary = select_active_glossary_terms(load_glossary(novel_name), source_text)

    # 3. Load recent chapter summaries (last 3 chapters)
    previous_summary = ""
    if chapter_number > 1:
        recent_summaries = load_recent_chapter_summaries(novel_name, chapter_number, max_count=MAX_RECENT_SUMMARIES)
        if recent_summaries:
            previous_summary = recent_summaries

    # 4. Load character context — only characters directly active in this chapter.
    entities, edges, address_rules, address_rule_candidates = get_active_context_with_candidates(
        novel_name,
        source_text,
        chapter_number,
    )
    if entities:
        _logger.info(
            "Loaded %s active character(s) with %s relationship(s), %s address rule(s), %s pending candidate(s)",
            len(entities),
            len(edges),
            len(address_rules),
            len(address_rule_candidates),
            extra={
                "presentation_event": "cli_message",
                "presentation_message": (
                    f"  👥 Loaded {len(entities)} active character(s) with "
                    f"{len(edges)} relationship(s), {len(address_rules)} address rule(s), "
                    f"{len(address_rule_candidates)} pending candidate(s)"
                ),
            },
        )

    return {
        "source_language": language,
        "translation_rules": rules,
        "glossary": glossary,
        "previous_summary": previous_summary,
        "characters": {
            "entities": entities,
            "edges": edges,
            "address_rules": address_rules,
            "address_rule_candidates": address_rule_candidates,
        },
    }
