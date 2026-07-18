"""
Glossary Service — JSON-based per-novel glossary management.

Each novel gets its own glossary file at
{translated_dir}/{novel_name}/glossary.json (or glossary.{target}.json for
non-Vietnamese targets).
Structure:
{
    "terms": {
        "原始术语": "Target-language translation",
        "李明": "Lý Minh"
    },
    "entities": {
        "李明": {"translated_name": "Lý Minh", "role": "protagonist"}
    },
    "edges": [
        ["李明", "张伟", "friend", 3]
    ],
    "chapter_summaries": {
        "1": "Summary of chapter 1...",
        "2": "Summary of chapter 2..."
    }
}

When TRANSLATED_DIR is unavailable, glossary files fall back to the project
runtime glossary directory.

Character schema:
- entities: dict of original_name -> {translated_name, role, pronoun, aliases?}
  role: protagonist | antagonist | supporting | minor
  pronoun: target-language pronoun/reference style assigned on first appearance (immutable)
  aliases: source-language short/full-name variants resolved to the canonical entity
- edges: list of [from_orig, to_orig, relationship_type, since_chapter]
  Each relationship stored ONCE (no bidirectional duplication).
  Relationship types: mother, father, sibling, friend, enemy, master,
  disciple, rival, classmate, teacher, romantic interest, etc.
- address_rules: list of {speaker, listener, self, other, since, until?, notes?}
  Non-overlapping per-pair direct address/reference timelines in the target language.
"""

from collections.abc import Callable
from pathlib import Path

from src import paths as _paths
from src.config import config
from src.domain import glossary as glossary_domain
from src.domain.characters import (
    get_character_translated_name,
    merge_character_context,
    normalize_character_info,
    select_active_address_rules,
    select_active_character_context,
    upsert_relationship,
)
from src.domain.glossary import (
    normalize_glossary_data,
    queue_pending_replacement,
    validate_glossary_data,
)
from src.domain.language import normalize_target_language
from src.utils import files as file_utils

_read_json_locked = file_utils.read_json_locked
_merge_json_locked = file_utils.merge_json_locked

GLOSSARY_DIR = _paths.GLOSSARY_DIR
PENDING_REPLACEMENTS_KEY = glossary_domain.PENDING_REPLACEMENTS_KEY


def current_target_language() -> str:
    target = getattr(config, "target_language", "vi")
    if not isinstance(target, str):
        return "vi"
    return normalize_target_language(target)


def translated_novel_root(novel_name: str) -> Path:
    if config.translated_dir:
        return _paths.novel_root_dir(config, novel_name)
    return _paths.resolve_novel_root(Path("translated"), novel_name)


def _glossary_path(novel_name: str) -> Path:
    """Get path to glossary file for a novel (directly in config.translated_dir or fallback to GLOSSARY_DIR)."""
    return _paths.novel_glossary_path(
        config,
        novel_name,
        current_target_language(),
        fallback_root=GLOSSARY_DIR,
    )


def resolve_glossary_path(novel_name: str) -> Path:
    """Return the active target's glossary path for a novel."""
    return _glossary_path(novel_name)


def load_glossary_data(novel_name: str) -> dict:
    """Load the full glossary JSON data for a novel."""
    return _read_json_locked(_glossary_path(novel_name))


def update_glossary_data(novel_name: str, updater: Callable[[dict], dict]) -> dict:
    """Atomically update the full glossary document for a novel."""
    return _merge_json_locked(_glossary_path(novel_name), updater)


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def load_glossary(novel_name: str) -> dict[str, str]:
    """Load term glossary for a novel. Returns empty dict if not found."""
    path = _glossary_path(novel_name)
    data = _read_json_locked(path)
    return data.get("terms", {})


def save_glossary(novel_name: str, terms: dict[str, str], *, is_user_edit: bool = False):
    """Save/merge terms into the novel's glossary (thread-safe)."""
    path = _glossary_path(novel_name)

    def updater(data: dict) -> dict:
        old_terms = dict(data.get("terms", {}))
        updated = {**data, "terms": {**old_terms, **terms}}
        if is_user_edit:
            for original, translated in terms.items():
                old_value = old_terms.get(original, "")
                updated = queue_pending_replacement(
                    updated,
                    kind="term",
                    sources=[original],
                    old_value=old_value,
                    new_value=translated,
                )
        return updated

    _merge_json_locked(path, updater)


def remove_glossary_term(novel_name: str, original: str) -> bool:
    """Remove a glossary term. Returns True if the term existed."""
    path = _glossary_path(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        terms = dict(data.get("terms", {}))
        removed = original in terms
        terms.pop(original, None)
        return {**data, "terms": terms}

    _merge_json_locked(path, updater)
    return removed


def update_glossary_term(
    novel_name: str,
    old_original: str,
    new_original: str,
    translated: str,
    *,
    overwrite: bool = False,
    is_user_edit: bool = False,
) -> None:
    """Atomically update or rename a term without exposing partial state."""
    path = _glossary_path(novel_name)

    def updater(data: dict) -> dict:
        terms = dict(data.get("terms", {}))
        if old_original not in terms:
            raise KeyError(old_original)
        old_translated = terms[old_original]
        if new_original != old_original and new_original in terms and not overwrite:
            raise FileExistsError(new_original)
        terms[new_original] = translated
        if new_original != old_original:
            terms.pop(old_original)
        updated = {**data, "terms": terms}
        if is_user_edit:
            updated = queue_pending_replacement(
                updated,
                kind="term",
                sources=list(dict.fromkeys([new_original, old_original])),
                old_value=old_translated,
                new_value=translated,
            )
        return updated

    _merge_json_locked(path, updater)


def remove_character(novel_name: str, original_name: str) -> bool:
    """Remove a character entity. Returns True if the character existed."""
    path = _glossary_path(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        entities = dict(data.get("entities", {}))
        removed = original_name in entities
        entities.pop(original_name, None)
        # Also clean up any edges or address rules referencing this character!
        edges = [
            edge for edge in data.get("edges", []) if len(edge) >= 2 and edge[0] != original_name and edge[1] != original_name
        ]
        address_rules = [
            rule
            for rule in data.get("address_rules", [])
            if rule.get("speaker") != original_name and rule.get("listener") != original_name
        ]
        return {**data, "entities": entities, "edges": edges, "address_rules": address_rules}

    _merge_json_locked(path, updater)
    return removed


def remove_relationship(novel_name: str, from_char: str, to_char: str) -> bool:
    """Remove a relationship edge between characters. Returns True if existed."""
    path = _glossary_path(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        edges = []
        for edge in data.get("edges", []):
            if len(edge) >= 2 and {edge[0], edge[1]} == {from_char, to_char}:
                removed = True
                continue
            edges.append(edge)
        return {**data, "edges": edges}

    _merge_json_locked(path, updater)
    return removed


def save_character_pronoun(novel_name: str, original_name: str, pronoun: str) -> bool:
    """Set a character pronoun. Returns True if the character existed."""
    path = _glossary_path(novel_name)
    found = False

    def updater(data: dict) -> dict:
        nonlocal found
        entities = dict(data.get("entities", {}))
        if original_name not in entities:
            return data
        info = normalize_character_info(dict(entities[original_name]))
        info["pronoun"] = pronoun
        entities[original_name] = info
        found = True
        return {**data, "entities": entities}

    _merge_json_locked(path, updater)
    return found


def save_character(
    novel_name: str,
    original_name: str,
    translated_name: str = "",
    role: str = "",
    name_vi: str = "",
    *,
    is_user_edit: bool = False,
) -> bool:
    """Update a character's translated name and/or role. Returns True if found."""
    path = _glossary_path(novel_name)
    found = False
    name_value = translated_name or name_vi

    def updater(data: dict) -> dict:
        nonlocal found
        entities = dict(data.get("entities", {}))
        if original_name not in entities:
            return data
        old_info = normalize_character_info(dict(entities[original_name]))
        old_name = get_character_translated_name(old_info)
        info = dict(old_info)
        if name_value:
            info["translated_name"] = name_value
        if role:
            info["role"] = role
        entities[original_name] = info
        found = True
        updated = {**data, "entities": entities}
        if is_user_edit:
            updated = queue_pending_replacement(
                updated,
                kind="character",
                sources=[original_name, *info.get("aliases", [])],
                old_value=old_name,
                new_value=info.get("translated_name", ""),
            )
        return updated

    _merge_json_locked(path, updater)
    return found


def save_relationship(
    novel_name: str,
    from_char: str,
    to_char: str,
    relationship: str,
    since_chapter: int | None = None,
    *,
    update_since: bool = False,
) -> bool:
    """Add or update a relationship. Returns True when both characters exist."""
    path = _glossary_path(novel_name)
    updated = False

    def updater(data: dict) -> dict:
        nonlocal updated
        entities = data.get("entities", {})
        if from_char not in entities or to_char not in entities:
            return data
        updated = True
        return upsert_relationship(
            data,
            from_char,
            to_char,
            relationship,
            since_chapter=since_chapter,
            update_since=update_since,
        )

    _merge_json_locked(path, updater)
    return updated


def validate_glossary(novel_name: str) -> list[str]:
    """Validate a novel glossary file and return issues."""
    return validate_glossary_data(load_glossary_data(novel_name))


def clean_glossary(novel_name: str) -> dict:
    """Normalize a glossary file and return before/after counts."""
    path = _glossary_path(novel_name)

    stats: dict = {}

    def updater(data: dict) -> dict:
        nonlocal stats
        before_edges = len(data.get("edges", []))
        before_address_rules = len(data.get("address_rules", []))
        before_pronoun_examples = len(data.get("pronoun_examples", {}))
        cleaned = normalize_glossary_data(data)
        stats = {
            "entities": len(cleaned.get("entities", {})),
            "edges_before": before_edges,
            "edges_after": len(cleaned.get("edges", [])),
            "address_rules_before": before_address_rules,
            "address_rules_after": len(cleaned.get("address_rules", [])),
            "pronoun_examples_removed": before_pronoun_examples,
        }
        return cleaned

    _merge_json_locked(path, updater)
    return stats


# ---------------------------------------------------------------------------
# Characters — Entity + Edge graph
# ---------------------------------------------------------------------------


def get_active_context(novel_name: str, source_text: str, chapter_number: int = 0) -> tuple[dict, list, list]:
    """Load only characters and relationships relevant to the current source text.

    Algorithm:
        1. Scan source_text for known character names (active set) using boundary-aware matching.
        2. Collect only pair edges where both endpoints are in the active set.
        3. Build entity dict for directly active characters.

    Returns:
        (entities, edges, address_rules) — filtered to active context only.
        entities: {orig_name: {"translated_name": str, "role": str}}
        edges:    [[from, to, rel_type, since_chapter], ...]
        address_rules: [{speaker, listener, self, other, since, until?, notes?}, ...]
    """
    data = normalize_glossary_data(_read_json_locked(_glossary_path(novel_name)))
    all_entities: dict = data.get("entities", {})
    all_edges: list = data.get("edges", [])
    all_address_rules: list = data.get("address_rules", [])

    if not all_entities:
        return {}, [], []

    entities, edges = select_active_character_context(all_entities, all_edges, source_text)
    address_rules = select_active_address_rules(all_address_rules, entities, chapter_number)
    return entities, edges, address_rules


def save_characters_batch(
    novel_name: str,
    entities: dict,
    edges: list,
    address_rules: list | None = None,
    chapter: int = 0,
):
    """Save character entities and relationship edges (thread-safe).

    Args:
        entities: {orig_name: {"translated_name": str, "role": str}}
        edges:    [[from, to, rel_type]] or [[from, to, rel_type, since_chapter]]
                  Each relationship should be stored ONCE (no bidirectional duplicates).
        address_rules: Direct address/reference rules for character pairs.
        chapter:  Current chapter number (used as since_chapter fallback).
    """
    if not entities and not edges and not address_rules:
        return

    path = _glossary_path(novel_name)

    def updater(data: dict) -> dict:
        return merge_character_context(data, entities, edges, address_rules=address_rules, chapter=chapter)

    _merge_json_locked(path, updater)
