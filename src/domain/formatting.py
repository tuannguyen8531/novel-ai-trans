"""Compact serialization of character context for LLM prompts."""

from src.domain.candidates import required_address_rule_observations
from src.domain.entities import get_character_translated_name


def format_relationships_shorthand(entities: dict, edges: list) -> str:
    """Format active character context as compact shorthand for LLM prompts."""
    if not entities:
        return ""

    character_parts = []
    for name, info in entities.items():
        translated_name = get_character_translated_name(info)
        role = info.get("role", "")
        pronoun = info.get("pronoun", "")

        identity = f"{name} => {translated_name}" if translated_name and translated_name != name else name
        attributes = []
        if role:
            attributes.append(role)
        if pronoun:
            attributes.append(f'pronoun="{pronoun}"')

        suffix = f" [{', '.join(attributes)}]" if attributes else ""
        character_parts.append(f"- {identity}{suffix}")

    rel_parts = []
    for edge in edges:
        if len(edge) < 3:
            continue
        from_char, to_char, rel_type = edge[0], edge[1], edge[2]
        rel_parts.append(f"{from_char}({rel_type})->{to_char}")

    lines = ["=== CHARACTERS ===", *character_parts]
    if rel_parts:
        lines.append("Relations: " + "; ".join(rel_parts))
    lines.append("=== END CHARACTERS ===")
    return "\n".join(lines)


def format_address_rules(entities: dict, address_rules: list, target_language: str = "vi") -> str:
    """Format active direct-address rules for translator prompts."""
    if not entities or not address_rules:
        return ""

    lines = ["=== ADDRESS RULES ==="]
    for rule in address_rules:
        speaker = rule.get("speaker", "")
        listener = rule.get("listener", "")

        parts = []
        if rule.get("self"):
            parts.append(f'self="{rule["self"]}"')
        if rule.get("other"):
            parts.append(f'other="{rule["other"]}"')

        lines.append(f"{speaker} -> {listener}: " + ", ".join(parts))
    lines.append("=== END ADDRESS RULES ===")
    return "\n".join(lines)


def format_address_rule_candidates(entities: dict, candidates: list, address_rules: list) -> str:
    """Format pending address hypotheses separately from confirmed defaults."""
    if not entities or not candidates:
        return ""

    active_by_pair = {(rule.get("speaker"), rule.get("listener")): rule for rule in address_rules}
    lines = [
        "=== UNCONFIRMED ADDRESS HYPOTHESES ===",
        "These are provisional continuity hints, not confirmed rules.",
    ]
    for candidate in candidates:
        speaker = candidate.get("speaker", "")
        listener = candidate.get("listener", "")
        parts = []
        if candidate.get("self"):
            parts.append(f'self="{candidate["self"]}"')
        if candidate.get("other"):
            parts.append(f'other="{candidate["other"]}"')

        pair = (speaker, listener)
        required = required_address_rule_observations(candidate, active_by_pair.get(pair))
        metadata = [f"observations={candidate.get('observations', 1)}/{required}"]
        if candidate.get("reason"):
            metadata.append(f'reason="{candidate["reason"]}"')
        if candidate.get("first_seen"):
            metadata.append(f"first_seen={candidate['first_seen']}")
        lines.append(f"{speaker} -> {listener}: {', '.join(parts)} [{', '.join(metadata)}]")

    lines.append("=== END UNCONFIRMED ADDRESS HYPOTHESES ===")
    return "\n".join(lines)
