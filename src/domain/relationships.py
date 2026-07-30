"""Domain rules for directed character relationships."""

from src.domain.entities import resolve_character_ref

SYMMETRIC_RELATIONSHIPS = {
    "spouse",
    "romantic interest",
    "ex",
    "friend",
    "enemy",
    "rival",
    "ally",
    "sibling",
    "half-sibling",
    "classmate",
    "colleague",
    "acquaintance",
    "neighbor",
    "relative",
    "cousin",
}

INVERSE_RELATIONSHIPS = {
    "mother": "child",
    "father": "child",
    "parent": "child",
    "son": "parent",
    "daughter": "parent",
    "child": "parent",
    "brother": "sibling",
    "sister": "sibling",
    "husband": "wife",
    "wife": "husband",
    "master": "disciple",
    "disciple": "master",
    "teacher": "student",
    "student": "teacher",
    "servant": "employer",
    "employer": "employee",
    "boss": "employee",
    "employee": "boss",
    "grandparent": "grandchild",
    "grandchild": "grandparent",
    "adoptive parent": "adoptive child",
    "adoptive child": "adoptive parent",
    "step-parent": "step-child",
    "step-child": "step-parent",
    "mentor": "ward",
    "guardian": "ward",
    "ward": "guardian",
    "protector": "ward",
}


def invert_relationship(relationship: str) -> str:
    """Return the reverse-direction relationship label when known."""
    rel = relationship.strip().lower()
    if rel in SYMMETRIC_RELATIONSHIPS:
        return rel
    return INVERSE_RELATIONSHIPS.get(rel, rel)


def normalize_character_edges(edges: list, entities: dict) -> list[list]:
    """Resolve edge endpoints to original keys, drop unknowns, and deduplicate pairs."""
    normalized: list[list] = []
    seen_pairs: dict[frozenset, int] = {}

    for edge in edges:
        if not isinstance(edge, list) or len(edge) < 3:
            continue
        from_char = resolve_character_ref(edge[0], entities)
        to_char = resolve_character_ref(edge[1], entities)
        if not from_char or not to_char or from_char == to_char:
            continue

        rel_type = str(edge[2]).strip().lower()
        if not rel_type:
            continue

        since = edge[3] if len(edge) > 3 and isinstance(edge[3], int) else None
        pair = frozenset((from_char, to_char))
        new_edge: list[str | int] = [from_char, to_char, rel_type]
        if since is not None:
            new_edge.append(since)

        if pair not in seen_pairs:
            seen_pairs[pair] = len(normalized)
            normalized.append(new_edge)
            continue

        existing = normalized[seen_pairs[pair]]
        if existing[0] == from_char and existing[1] == to_char:
            continue

        inverted = invert_relationship(rel_type)
        if existing[0] == to_char and existing[1] == from_char and existing[2] == inverted:
            continue

    return normalized


def merge_character_edges(existing_edges: list, incoming_edges: list, entities: dict) -> list[list]:
    """Merge current relationship state without resetting unchanged edges."""
    merged = normalize_character_edges(existing_edges, entities)
    incoming = normalize_character_edges(incoming_edges, entities)
    pair_indexes = {frozenset((edge[0], edge[1])): index for index, edge in enumerate(merged)}

    for edge in incoming:
        pair = frozenset((edge[0], edge[1]))
        existing_index = pair_indexes.get(pair)
        if existing_index is None:
            pair_indexes[pair] = len(merged)
            merged.append(edge)
            continue

        current = merged[existing_index]
        same_direction = current[0] == edge[0] and current[1] == edge[1]
        same_relationship = (
            current[2] == edge[2]
            if same_direction
            else edge[2] == invert_relationship(current[2]) or current[2] == invert_relationship(edge[2])
        )
        if same_relationship:
            continue

        merged[existing_index] = edge

    return merged
