"""Domain rules for character entities, aliases, and source-name matching."""

import re

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]")


def get_character_translated_name(info: dict) -> str:
    """Return the target-language character name, accepting legacy name_vi."""
    return info.get("translated_name") or info.get("name_vi") or ""


def normalize_character_info(info: dict) -> dict:
    """Normalize a character entity to the current glossary schema."""
    aliases = info.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []
    normalized = {
        "translated_name": get_character_translated_name(info),
        "role": info.get("role", "unknown"),
        "pronoun": info.get("pronoun", ""),
    }
    normalized_aliases = list(dict.fromkeys(alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip()))
    if normalized_aliases:
        normalized["aliases"] = normalized_aliases
    return normalized


def _name_tokens(name: str) -> list[str]:
    return [token.casefold() for token in re.split(r"[\s._-]+", name.strip()) if token]


def is_expanded_name(short_name: str, long_name: str) -> bool:
    """Return whether long_name is a clear token-level expansion of short_name."""
    short_tokens = _name_tokens(short_name)
    long_tokens = _name_tokens(long_name)
    if not short_tokens or len(short_tokens) >= len(long_tokens):
        if len(short_name) < 2 or len(short_name) >= len(long_name):
            return False
        return long_name.endswith(short_name)
    size = len(short_tokens)
    return short_tokens == long_tokens[:size] or short_tokens == long_tokens[-size:]


def _is_same_rendered_name_alias(
    short_name: str,
    long_name: str,
    short_translation: str,
    long_translation: str,
) -> bool:
    """Return whether two source variants render to the same target name."""
    if not short_translation or short_translation != long_translation:
        return False
    if len(short_name) < 2 or len(short_name) >= len(long_name):
        return False
    return short_name[0] == long_name[0]


def normalize_character_entities(raw_entities: dict) -> dict:
    """Normalize entities and merge conservative short/full-name aliases."""
    if not isinstance(raw_entities, dict):
        return {}

    entities = {
        name: normalize_character_info(info)
        for name, info in raw_entities.items()
        if isinstance(name, str) and name.strip() and isinstance(info, dict)
    }
    names = list(entities)
    alias_to_canonical: dict[str, str] = {}

    for short_name in names:
        short_translation = get_character_translated_name(entities[short_name])
        if not short_translation:
            continue
        candidates = []
        for long_name in names:
            if short_name == long_name:
                continue
            long_translation = get_character_translated_name(entities[long_name])
            if (
                is_expanded_name(short_name, long_name) and is_expanded_name(short_translation, long_translation)
            ) or _is_same_rendered_name_alias(
                short_name,
                long_name,
                short_translation,
                long_translation,
            ):
                candidates.append(long_name)
        if len(candidates) == 1:
            alias_to_canonical[short_name] = candidates[0]

    for alias, canonical in alias_to_canonical.items():
        if alias not in entities or canonical not in entities:
            continue
        alias_info = entities.pop(alias)
        canonical_info = entities[canonical]
        aliases = canonical_info.setdefault("aliases", [])
        aliases.extend([alias, *alias_info.get("aliases", [])])
        canonical_info["aliases"] = list(dict.fromkeys(aliases))
        if canonical_info.get("role") in ("", "unknown", "minor"):
            alias_role = alias_info.get("role", "")
            if alias_role and alias_role != "unknown":
                canonical_info["role"] = alias_role
        if not canonical_info.get("pronoun"):
            canonical_info["pronoun"] = alias_info.get("pronoun", "")

    return entities


def _build_character_alias_map(entities: dict) -> dict[str, str | None]:
    """Map original and translated character names to canonical original keys."""
    aliases: dict[str, str | None] = {}
    for original, info in entities.items():
        entity_aliases = info.get("aliases", []) if isinstance(info, dict) else []
        for alias in (original, get_character_translated_name(info), *entity_aliases):
            if not alias:
                continue
            if alias in aliases and aliases[alias] != original:
                aliases[alias] = None
            else:
                aliases[alias] = original
    return aliases


def resolve_character_ref(name: str, entities: dict) -> str:
    """Resolve a character reference to its original source key."""
    if name in entities:
        return name
    aliases = _build_character_alias_map(entities)
    resolved = aliases.get(name)
    return resolved or ""


def _is_name_boundary(text: str, pos: int) -> bool:
    """Check if position is a valid CJK/word boundary, not inside a longer word."""
    if pos < 0 or pos >= len(text):
        return True
    return not CJK_RE.match(text[pos]) and not text[pos].isalnum()


def find_name_in_text(name: str, source_text: str) -> bool:
    """Check if name appears in text with proper boundaries."""
    if CJK_RE.search(name):
        return name in source_text
    escaped = re.escape(name)
    for match in re.finditer(escaped, source_text):
        if _is_name_boundary(source_text, match.start() - 1) and _is_name_boundary(source_text, match.end()):
            return True
    return False


def count_name_occurrences(name: str, text: str) -> int:
    """Count occurrences of name in text with proper CJK/word boundaries."""
    if not name or not text:
        return 0
    if CJK_RE.search(name):
        return text.count(name)
    escaped = re.escape(name)
    count = 0
    for match in re.finditer(escaped, text):
        if _is_name_boundary(text, match.start() - 1) and _is_name_boundary(text, match.end()):
            count += 1
    return count
