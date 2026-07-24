"""Domain rules for glossary terms, validation, and rendered replacements."""

import re

from src.domain.addressing import ADDRESS_RULE_STABLE_REASONS
from src.domain.candidates import (
    ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT,
    ADDRESS_RULE_CANDIDATE_VERDICTS,
    ADDRESS_RULE_CANDIDATES_KEY,
)
from src.domain.context import normalize_character_data
from src.domain.entities import find_name_in_text

PENDING_REPLACEMENTS_KEY = "_pending_replacements"


def queue_pending_replacement(
    data: dict,
    *,
    kind: str,
    sources: list[str],
    old_value: str,
    new_value: str,
) -> dict:
    """Queue or collapse a pending rendered-value replacement."""
    sources = list(dict.fromkeys(source for source in sources if source))
    if not sources or not old_value or not new_value or old_value == new_value:
        return data

    pending = [dict(item) for item in data.get(PENDING_REPLACEMENTS_KEY, []) if isinstance(item, dict)]
    for index, item in enumerate(pending):
        if item.get("kind") == kind and item.get("sources") == sources and item.get("new") == old_value:
            if item.get("old") == new_value:
                pending.pop(index)
            else:
                item["new"] = new_value
            return {**data, PENDING_REPLACEMENTS_KEY: pending}
    pending.append({"kind": kind, "sources": sources, "old": old_value, "new": new_value})
    return {**data, PENDING_REPLACEMENTS_KEY: pending}


def merge_pending_replacements(restored: list[dict], current: list[dict]) -> list[dict]:
    """Merge a restored pending chain with edits made after the backup."""
    merged = [dict(item) for item in restored]
    for current_item in current:
        item = dict(current_item)
        collapsed = False
        for previous in merged:
            if (
                previous.get("kind") == item.get("kind")
                and previous.get("sources") == item.get("sources")
                and previous.get("new") == item.get("old")
            ):
                previous["new"] = item.get("new")
                collapsed = True
                break
        if not collapsed and item not in merged:
            merged.append(item)
    return merged


def normalize_glossary_data(data: dict) -> dict:
    """Normalize persisted glossary memory into the current schema."""
    return normalize_character_data(data)


def format_glossary_for_prompt(terms: dict[str, str]) -> str:
    """Format glossary terms for inclusion in LLM prompts."""
    if not terms:
        return ""
    lines = ["=== GLOSSARY (use these translations consistently) ==="]
    for original, translated in terms.items():
        lines.append(f"  {original} → {translated}")
    lines.append("=== END GLOSSARY ===")
    return "\n".join(lines)


def validate_glossary_data(data: dict) -> list[str]:
    """Validate glossary JSON shape and return human-readable issues."""
    issues: list[str] = []

    if not isinstance(data, dict):
        return ["glossary root must be an object"]

    terms = data.get("terms", {})
    if terms is not None and not isinstance(terms, dict):
        issues.append("terms must be an object")
    elif isinstance(terms, dict):
        for original, translated in terms.items():
            if not isinstance(original, str) or not original.strip():
                issues.append("terms contains an empty or non-string source term")
            if not isinstance(translated, str) or not translated.strip():
                issues.append(f"term {original!r} has an empty or non-string translation")

    source_language = data.get("source_language", "")
    if source_language is not None and not isinstance(source_language, str):
        issues.append("source_language must be a string")

    entities = data.get("entities", {})
    if entities is not None and not isinstance(entities, dict):
        issues.append("entities must be an object")
        entities = {}
    elif isinstance(entities, dict):
        for original, info in entities.items():
            if not isinstance(original, str) or not original.strip():
                issues.append("entities contains an empty or non-string original name")
                continue
            if not isinstance(info, dict):
                issues.append(f"entity {original!r} must be an object")
                continue
            for key in ("translated_name", "name_vi", "role", "pronoun"):
                if key in info and not isinstance(info[key], str):
                    issues.append(f"entity {original!r}.{key} must be a string")
            aliases = info.get("aliases")
            if aliases is not None and not isinstance(aliases, list):
                issues.append(f"entity {original!r}.aliases must be a list")
            elif isinstance(aliases, list):
                for alias in aliases:
                    if not isinstance(alias, str) or not alias.strip():
                        issues.append(f"entity {original!r}.aliases contains an empty or non-string alias")

    edges = data.get("edges", [])
    if edges is not None and not isinstance(edges, list):
        issues.append("edges must be a list")
    elif isinstance(edges, list):
        entity_names = set(entities) if isinstance(entities, dict) else set()
        for index, edge in enumerate(edges):
            if not isinstance(edge, list) or len(edge) < 3:
                issues.append(f"edge {index} must be [from, to, relationship, since_chapter?]")
                continue
            from_char, to_char, relationship = edge[0], edge[1], edge[2]
            if not isinstance(from_char, str) or not from_char.strip():
                issues.append(f"edge {index} has an invalid from character")
            if not isinstance(to_char, str) or not to_char.strip():
                issues.append(f"edge {index} has an invalid to character")
            if not isinstance(relationship, str) or not relationship.strip():
                issues.append(f"edge {index} has an invalid relationship")
            if len(edge) > 3 and not isinstance(edge[3], int):
                issues.append(f"edge {index} since_chapter must be an integer")
            if entity_names:
                if isinstance(from_char, str) and from_char not in entity_names:
                    issues.append(f"edge {index} references unknown character {from_char!r}")
                if isinstance(to_char, str) and to_char not in entity_names:
                    issues.append(f"edge {index} references unknown character {to_char!r}")

    address_rules = data.get("address_rules", [])
    if address_rules is not None and not isinstance(address_rules, list):
        issues.append("address_rules must be a list")
    elif isinstance(address_rules, list):
        entity_names = set(entities) if isinstance(entities, dict) else set()
        for index, rule in enumerate(address_rules):
            if not isinstance(rule, dict):
                issues.append(f"address rule {index} must be an object")
                continue
            speaker = rule.get("speaker")
            listener = rule.get("listener")
            if not isinstance(speaker, str) or not speaker.strip():
                issues.append(f"address rule {index} has an invalid speaker")
            if not isinstance(listener, str) or not listener.strip():
                issues.append(f"address rule {index} has an invalid listener")
            for key in ("self", "other", "notes"):
                if key in rule and not isinstance(rule[key], str):
                    issues.append(f"address rule {index}.{key} must be a string")
            has_self = isinstance(rule.get("self"), str) and bool(rule["self"].strip())
            has_other = isinstance(rule.get("other"), str) and bool(rule["other"].strip())
            if not has_self and not has_other:
                issues.append(f"address rule {index} must define self or other")
            if "scope" in rule and rule["scope"] != "stable":
                issues.append(f"address rule {index}.scope must be stable")
            if "reason" in rule and (not isinstance(rule["reason"], str) or rule["reason"] not in ADDRESS_RULE_STABLE_REASONS):
                issues.append(f"address rule {index}.reason is invalid")
            for key in ("since", "until"):
                if key in rule and not isinstance(rule[key], int):
                    issues.append(f"address rule {index}.{key} must be an integer")
            if entity_names:
                if isinstance(speaker, str) and speaker not in entity_names:
                    issues.append(f"address rule {index} references unknown speaker {speaker!r}")
                if isinstance(listener, str) and listener not in entity_names:
                    issues.append(f"address rule {index} references unknown listener {listener!r}")

    address_rule_candidates = data.get(ADDRESS_RULE_CANDIDATES_KEY, [])
    if address_rule_candidates is not None and not isinstance(address_rule_candidates, list):
        issues.append(f"{ADDRESS_RULE_CANDIDATES_KEY} must be a list")
    elif isinstance(address_rule_candidates, list):
        entity_names = set(entities) if isinstance(entities, dict) else set()
        seen_pairs: set[tuple[str, str]] = set()
        for index, candidate in enumerate(address_rule_candidates):
            label = f"address rule candidate {index}"
            if not isinstance(candidate, dict):
                issues.append(f"{label} must be an object")
                continue

            speaker = candidate.get("speaker")
            listener = candidate.get("listener")
            speaker_value = speaker if isinstance(speaker, str) else ""
            listener_value = listener if isinstance(listener, str) else ""
            valid_speaker = bool(speaker_value.strip())
            valid_listener = bool(listener_value.strip())
            if not valid_speaker:
                issues.append(f"{label} has an invalid speaker")
            if not valid_listener:
                issues.append(f"{label} has an invalid listener")
            if valid_speaker and speaker_value not in entity_names:
                issues.append(f"{label} references unknown speaker {speaker_value!r}")
            if valid_listener and listener_value not in entity_names:
                issues.append(f"{label} references unknown listener {listener_value!r}")
            if valid_speaker and valid_listener:
                pair = (speaker_value, listener_value)
                if speaker_value == listener_value:
                    issues.append(f"{label} speaker and listener must differ")
                if pair in seen_pairs:
                    issues.append(f"{label} duplicates an existing pair")
                seen_pairs.add(pair)

            for key in ("self", "other", "notes"):
                if key in candidate and not isinstance(candidate[key], str):
                    issues.append(f"{label}.{key} must be a string")
            has_self = isinstance(candidate.get("self"), str) and bool(candidate["self"].strip())
            has_other = isinstance(candidate.get("other"), str) and bool(candidate["other"].strip())
            if not has_self and not has_other:
                issues.append(f"{label} must define self or other")
            if "scope" in candidate and candidate["scope"] != "stable":
                issues.append(f"{label}.scope must be stable")
            if "reason" in candidate and (
                not isinstance(candidate["reason"], str) or candidate["reason"] not in ADDRESS_RULE_STABLE_REASONS
            ):
                issues.append(f"{label}.reason is invalid")

            first_seen = candidate.get("first_seen")
            last_seen = candidate.get("last_seen")
            observations = candidate.get("observations")
            if isinstance(first_seen, bool) or not isinstance(first_seen, int) or first_seen <= 0:
                issues.append(f"{label}.first_seen must be a positive integer")
            if isinstance(last_seen, bool) or not isinstance(last_seen, int) or last_seen <= 0:
                issues.append(f"{label}.last_seen must be a positive integer")
            elif isinstance(first_seen, int) and not isinstance(first_seen, bool) and last_seen < first_seen:
                issues.append(f"{label}.last_seen must not precede first_seen")
            if isinstance(observations, bool) or not isinstance(observations, int) or observations < 1:
                issues.append(f"{label}.observations must be a positive integer")
            evaluations = candidate.get("evaluations", [])
            if not isinstance(evaluations, list):
                issues.append(f"{label}.evaluations must be a list")
            else:
                evaluation_chapters = []
                for evaluation_index, evaluation in enumerate(evaluations):
                    evaluation_label = f"{label}.evaluations[{evaluation_index}]"
                    if not isinstance(evaluation, dict):
                        issues.append(f"{evaluation_label} must be an object")
                        continue
                    evaluation_chapter = evaluation.get("chapter")
                    if isinstance(evaluation_chapter, bool) or not isinstance(evaluation_chapter, int) or evaluation_chapter <= 0:
                        issues.append(f"{evaluation_label}.chapter must be a positive integer")
                    else:
                        evaluation_chapters.append(evaluation_chapter)
                        if isinstance(first_seen, int) and not isinstance(first_seen, bool) and evaluation_chapter < first_seen:
                            issues.append(f"{evaluation_label}.chapter must not precede first_seen")
                    verdict = evaluation.get("verdict")
                    if not isinstance(verdict, str) or verdict not in ADDRESS_RULE_CANDIDATE_VERDICTS:
                        issues.append(f"{evaluation_label}.verdict is invalid")
                if len(set(evaluation_chapters)) != len(evaluation_chapters):
                    issues.append(f"{label}.evaluations must not contain duplicate chapters")
                if len(evaluations) > ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT:
                    issues.append(f"{label}.evaluations exceeds the candidate evaluation limit")

    summaries = data.get("chapter_summaries", {})
    if summaries is not None and not isinstance(summaries, dict):
        issues.append("chapter_summaries must be an object")
    elif isinstance(summaries, dict):
        for chapter, summary in summaries.items():
            if not isinstance(chapter, str) or not chapter.isdigit():
                issues.append(f"chapter summary key {chapter!r} must be a numeric string")
            if not isinstance(summary, str):
                issues.append(f"chapter summary {chapter!r} must be a string")

    pronoun_examples = data.get("pronoun_examples", {})
    if pronoun_examples is not None and not isinstance(pronoun_examples, dict):
        issues.append("pronoun_examples must be an object")
    elif isinstance(pronoun_examples, dict):
        for name, examples in pronoun_examples.items():
            if not isinstance(name, str) or not name.strip():
                issues.append("pronoun_examples contains an empty or non-string character name")
            if not isinstance(examples, list):
                issues.append(f"pronoun_examples[{name!r}] must be a list")
            else:
                for i, ex in enumerate(examples):
                    if not isinstance(ex, str) or not ex.strip():
                        issues.append(f"pronoun_examples[{name!r}][{i}] must be a non-empty string")

    return issues


def audit_term_usage(terms: dict[str, str], source_text: str, translated_text: str) -> list[dict]:
    """Find glossary terms that look inconsistent between source and translation."""
    issues: list[dict] = []
    for original, translated in sorted(terms.items()):
        if not original or not translated or original not in source_text:
            continue
        if translated not in translated_text:
            issues.append(
                {
                    "term": original,
                    "expected": translated,
                    "issue": "missing_translation",
                }
            )
        if original in translated_text:
            issues.append(
                {
                    "term": original,
                    "expected": translated,
                    "issue": "source_term_leaked",
                }
            )
    return issues


_SENTENCE_ENDINGS = frozenset(".!?…")
_SENTENCE_PREFIX_MARKS = frozenset("\"'“‘([{—-")


def uppercase_first_cased(value: str) -> str:
    """Uppercase only the first cased character without lowercasing the rest."""
    for index, char in enumerate(value):
        if char.lower() != char.upper():
            return f"{value[:index]}{char.upper()}{value[index + 1 :]}"
    return value


def _is_sentence_start(text: str, position: int) -> bool:
    index = position - 1
    saw_newline = False
    while index >= 0:
        char = text[index]
        if char.isspace():
            saw_newline = saw_newline or char in "\r\n"
            index -= 1
            continue
        if char in _SENTENCE_PREFIX_MARKS:
            index -= 1
            continue
        break
    return index < 0 or saw_newline or text[index] in _SENTENCE_ENDINGS


def replace_glossary_value(
    text: str,
    old_value: str,
    new_value: str,
    *,
    capitalize_sentence_start: bool,
) -> tuple[str, int]:
    """Replace an old rendered glossary value while respecting word boundaries."""
    if not old_value or old_value == new_value:
        return text, 0

    old_variants = {old_value, uppercase_first_cased(old_value)}
    choices = "|".join(re.escape(value) for value in sorted(old_variants, key=len, reverse=True))
    left_boundary = r"(?<!\w)" if old_value[0].isalnum() else ""
    right_boundary = r"(?!\w)" if old_value[-1].isalnum() else ""
    pattern = re.compile(f"{left_boundary}(?:{choices}){right_boundary}")

    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        replacements += 1
        if capitalize_sentence_start and _is_sentence_start(text, match.start()):
            return uppercase_first_cased(new_value)
        return new_value

    return pattern.sub(replace, text), replacements


def replace_glossary_values(
    text: str,
    replacements: list[dict],
) -> tuple[str, dict[str, int]]:
    """Replace multiple glossary values in a single pass to avoid substring collision and cascading.

    replacements: list of dict with keys: 'kind' ('term' or 'character'), 'old', 'new'
    Returns: (updated_text, dict mapping old_value -> replacements_count)
    """
    conflicts = find_glossary_replacement_conflicts(replacements)
    if conflicts:
        raise ValueError("Conflicting glossary replacement match variants")

    mapping = {}
    counts = {}

    for item in replacements:
        old_val = item["old"]
        new_val = item["new"]
        kind = item.get("kind", "term")
        if not old_val or old_val == new_val:
            continue

        counts[old_val] = 0

        # Add variants
        mapping[old_val] = (new_val, kind, old_val)
        # Only terms can be capitalized at sentence start
        mapping[uppercase_first_cased(old_val)] = (new_val, kind, old_val)

    if not mapping:
        return text, counts

    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keys))

    def _has_boundary(text: str, start: int, end: int, key: str) -> bool:
        left_match = (key[0].isalnum() or key[0] == "_") and start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_")
        right_match = (key[-1].isalnum() or key[-1] == "_") and end < len(text) and (text[end].isalnum() or text[end] == "_")
        return not (left_match or right_match)

    def replace(match: re.Match[str]) -> str:
        matched_str = match.group(0)
        start, end = match.span()
        if not _has_boundary(text, start, end, matched_str):
            return matched_str

        new_val, kind, original_old = mapping[matched_str]
        counts[original_old] += 1

        if kind == "term" and _is_sentence_start(text, start):
            return uppercase_first_cased(new_val)
        return new_val

    return pattern.sub(replace, text), counts


def find_glossary_replacement_conflicts(replacements: list[dict]) -> dict[int, list[str]]:
    """Return replacement indexes whose exact/capitalized match variants collide."""
    claims: dict[str, list[int]] = {}
    for index, item in enumerate(replacements):
        old_value = str(item.get("old", ""))
        new_value = str(item.get("new", ""))
        if not old_value or old_value == new_value:
            continue
        for variant in {old_value, uppercase_first_cased(old_value)}:
            claims.setdefault(variant, []).append(index)

    conflicts: dict[int, set[str]] = {}
    for indexes in claims.values():
        signatures = {
            (
                str(replacements[index].get("old", "")),
                str(replacements[index].get("new", "")),
                str(replacements[index].get("kind", "term")),
            )
            for index in indexes
        }
        if len(signatures) <= 1:
            continue
        conflicting_news = {signature[1] for signature in signatures}
        for index in indexes:
            conflicts.setdefault(index, set()).update(conflicting_news)
    return {index: sorted(values) for index, values in conflicts.items()}


def select_active_glossary_terms(terms: dict[str, str], source_text: str) -> dict[str, str]:
    """Select glossary terms that appear in the current source text."""
    if not terms or not source_text:
        return {}
    return {
        original: translated
        for original, translated in terms.items()
        if isinstance(original, str) and isinstance(translated, str) and original and find_name_in_text(original, source_text)
    }
