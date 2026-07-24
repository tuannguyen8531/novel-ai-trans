"""Composition rules for persisted and active character context."""

from src.domain.addressing import normalize_address_rules
from src.domain.candidates import (
    ADDRESS_RULE_CANDIDATES_KEY,
    merge_address_rule_candidates,
    normalize_address_rule_candidates,
)
from src.domain.entities import (
    find_name_in_text,
    get_character_translated_name,
    normalize_character_entities,
    resolve_character_ref,
)
from src.domain.relationships import normalize_character_edges


def normalize_character_data(data: dict) -> dict:
    """Normalize the character-related sections of persisted glossary data."""
    entities = normalize_character_entities(data.get("entities", {}))
    normalized = {
        **data,
        "entities": entities,
        "edges": normalize_character_edges(data.get("edges", []), entities),
        "address_rules": normalize_address_rules(data.get("address_rules", []), entities),
    }
    candidates = normalize_address_rule_candidates(data.get(ADDRESS_RULE_CANDIDATES_KEY, []), entities)
    if candidates:
        normalized[ADDRESS_RULE_CANDIDATES_KEY] = candidates
    else:
        normalized.pop(ADDRESS_RULE_CANDIDATES_KEY, None)
    normalized.pop("pronoun_examples", None)
    return normalized


def select_active_character_context(all_entities: dict, all_edges: list, source_text: str) -> tuple[dict, list]:
    """Select characters and pair relationships that directly appear in the current source text."""
    if not all_entities:
        return {}, []

    normalized = normalize_character_data({"entities": all_entities, "edges": all_edges})
    all_entities = normalized["entities"]
    all_edges = normalized["edges"]

    active_names = {
        name
        for name, info in all_entities.items()
        if find_name_in_text(name, source_text) or any(find_name_in_text(alias, source_text) for alias in info.get("aliases", []))
    }

    if not active_names:
        return {}, []

    active_edges: list = []
    for edge in all_edges:
        if len(edge) < 3:
            continue
        from_char, to_char = edge[0], edge[1]
        if from_char in active_names and to_char in active_names:
            active_edges.append(edge)

    active_entities = {name: all_entities[name] for name in active_names if name in all_entities}
    return active_entities, active_edges


def merge_character_context(
    data: dict,
    entities: dict,
    edges: list,
    address_rules: list | None = None,
    address_rule_candidate_verdicts: list | None = None,
    chapter: int = 0,
) -> dict:
    """Merge character entities and relationship edges into glossary data."""
    data = normalize_character_data(data)
    existing_entities: dict = data.get("entities", {})
    for name, info in entities.items():
        translated_name = get_character_translated_name(info)
        if name not in existing_entities:
            existing_entities[name] = {
                "translated_name": translated_name,
                "role": info.get("role", "unknown"),
                "pronoun": info.get("pronoun", ""),
            }
        else:
            existing_name = get_character_translated_name(existing_entities[name])
            if translated_name and not existing_name:
                existing_entities[name]["translated_name"] = translated_name
            new_role = info.get("role", "")
            if new_role and new_role != "unknown":
                existing_entities[name]["role"] = new_role
            if not existing_entities[name].get("pronoun"):
                existing_entities[name]["pronoun"] = info.get("pronoun", "")

    tagged_edges = []
    for edge in edges:
        if len(edge) >= 3:
            since = edge[3] if len(edge) > 3 else chapter
            tagged_edges.append([edge[0], edge[1], edge[2], since])

    existing_entities = normalize_character_entities(existing_entities)
    existing_edges = normalize_character_edges(data.get("edges", []) + tagged_edges, existing_entities)
    existing_address_rules, address_rule_candidates = merge_address_rule_candidates(
        data.get("address_rules", []),
        data.get(ADDRESS_RULE_CANDIDATES_KEY, []),
        address_rules or [],
        address_rule_candidate_verdicts or [],
        existing_entities,
        chapter,
    )

    result = {
        **data,
        "entities": existing_entities,
        "edges": existing_edges,
        "address_rules": existing_address_rules,
    }
    if address_rule_candidates:
        result[ADDRESS_RULE_CANDIDATES_KEY] = address_rule_candidates
    else:
        result.pop(ADDRESS_RULE_CANDIDATES_KEY, None)
    return result


def upsert_relationship(
    data: dict,
    from_char: str,
    to_char: str,
    relationship: str,
    since_chapter: int | None = None,
    *,
    update_since: bool = False,
) -> dict:
    """Add or update one relationship edge, preserving the one-edge-per-pair rule."""
    data = normalize_character_data(data)
    entities = data.get("entities", {})
    from_char = resolve_character_ref(from_char, entities) or from_char
    to_char = resolve_character_ref(to_char, entities) or to_char
    relationship = relationship.strip().lower()
    should_update_since = update_since or since_chapter is not None
    edges = [list(edge) for edge in data.get("edges", [])]
    for edge in edges:
        if len(edge) >= 3 and {edge[0], edge[1]} == {from_char, to_char}:
            edge[0] = from_char
            edge[1] = to_char
            edge[2] = relationship
            if should_update_since:
                if since_chapter is None:
                    if len(edge) > 3:
                        edge.pop(3)
                elif len(edge) > 3:
                    edge[3] = since_chapter
                else:
                    edge.append(since_chapter)
            return {**data, "edges": edges}

    edge: list[str | int] = [from_char, to_char, relationship]
    if since_chapter is not None:
        edge.append(since_chapter)
    edges.append(edge)
    return {**data, "edges": edges}
