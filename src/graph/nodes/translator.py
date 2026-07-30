"""
Translator Node — Core translation using LLM.

Builds a system prompt from template with:
- Translation rules (from rules/*.md)
- Glossary terms
- Previous chapter summary (for context continuity)
- Character relationships and direct-address rules
- Review feedback (if retrying)
"""

from src.config import config
from src.domain.chunking import overlap_suffix
from src.domain.formatting import (
    format_address_rule_candidates,
    format_address_rules,
    format_relationships_shorthand,
)
from src.domain.glossary import format_glossary_for_prompt
from src.domain.illustrations import detach_illustration_markers, restore_illustration_markers
from src.domain.language import target_language_name
from src.models.state import TranslationState
from src.prompts import render_prompt
from src.services.llm import get_llm
from src.services.logger import log_ai_call


def translator_node(state: TranslationState) -> dict:
    """Translate the current chunk."""
    chunk_index = state["current_chunk_index"]
    chunk = state["chunks"][chunk_index]
    language = state["source_language"]
    target_language = state.get("target_language", "vi")
    target_name = target_language_name(target_language)
    retry_count = state.get("retry_count", 0)
    total_chunks = len(state["chunks"])
    translatable_chunk, illustration_placements = detach_illustration_markers(chunk)

    source_context = ""
    if chunk_index > 0 and config.chunk_overlap > 0:
        previous_chunk, _ = detach_illustration_markers(state["chunks"][chunk_index - 1])
        source_context = overlap_suffix(previous_chunk, config.chunk_overlap, config.chunk_mode)

    lang_names = {
        "chinese": "Chinese",
        "korean": "Korean",
        "japanese": "Japanese",
    }
    lang_name = lang_names.get(language, language)

    # Build optional sections
    rules = state.get("translation_rules", "")
    translation_rules = f"\n{rules}" if rules else ""

    glossary_text = format_glossary_for_prompt(state.get("glossary", {}))
    glossary = f"\n{glossary_text}" if glossary_text else ""

    char_data = state.get("characters", {})
    entities = char_data.get("entities", {})
    edges = char_data.get("edges", [])
    address_rules = char_data.get("address_rules", [])
    address_rule_candidates = char_data.get("address_rule_candidates", [])
    relationships_text = format_relationships_shorthand(entities, edges)
    characters = f"\n{relationships_text}" if relationships_text else ""
    address_rules_text = format_address_rules(entities, address_rules, target_language=target_language)
    address_rules_prompt = f"\n{address_rules_text}" if address_rules_text else ""
    candidate_text = format_address_rule_candidates(entities, address_rule_candidates, address_rules)
    address_rule_candidates_prompt = f"\n{candidate_text}" if candidate_text else ""

    previous_summary = state.get("previous_summary", "")
    if previous_summary:
        previous_summary = f"\n=== CONTEXT FROM PREVIOUS CHAPTER ===\n{previous_summary}\n=== END CONTEXT ==="

    review_feedback = ""
    if retry_count > 0 and state.get("review_feedback"):
        review_feedback = (
            f"\n=== PREVIOUS TRANSLATION FEEDBACK (please improve) ===\n{state['review_feedback']}\n=== END FEEDBACK ==="
        )

    system_prompt = render_prompt(
        "translate",
        target_language=target_language,
        lang_name=lang_name,
        target_name=target_name,
        translation_rules=translation_rules,
        glossary=glossary,
        characters=characters,
        address_rules=address_rules_prompt,
        address_rule_candidates=address_rule_candidates_prompt,
        previous_summary=previous_summary,
        review_feedback=review_feedback,
    )

    context_section = ""
    if source_context:
        context_section = f"""=== PRECEDING SOURCE CONTEXT — DO NOT TRANSLATE ===
Use this only to understand continuity. Do not repeat or include any part of it in the output.
{source_context}
=== END PRECEDING SOURCE CONTEXT ===

"""

    user_prompt = f"""Translate only the source text marked for translation from {lang_name} to {target_name} \
(chunk {chunk_index + 1}/{total_chunks}).

{context_section}=== SOURCE TEXT TO TRANSLATE ===
{translatable_chunk}
=== END SOURCE TEXT TO TRANSLATE ==="""

    translation = get_llm().generate(system_prompt, user_prompt, "translate") if translatable_chunk else ""
    translation = restore_illustration_markers(translation, illustration_placements)

    log_ai_call(
        "translate",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=translation,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        chunk_length=len(chunk),
        translation_length=len(translation),
        retry_count=retry_count,
    )

    return {"current_translation": translation}
