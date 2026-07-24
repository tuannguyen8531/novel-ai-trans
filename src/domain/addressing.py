"""Domain rules for direct-address observations and stable timelines."""

from src.domain.entities import get_character_translated_name, is_expanded_name, resolve_character_ref

ADDRESS_RULE_SCOPES = frozenset({"stable", "temporary", "uncertain"})
ADDRESS_RULE_STABLE_REASONS = frozenset({"default", "relationship_change"})
ADDRESS_RULE_TRANSIENT_REASONS = frozenset(
    {
        "drunken_speech",
        "emotional_outburst",
        "joke",
        "nickname",
        "roleplay",
    }
)
ADDRESS_RULE_REASONS = ADDRESS_RULE_STABLE_REASONS | ADDRESS_RULE_TRANSIENT_REASONS

_TRANSIENT_ADDRESS_PREFIXES = (
    "đồ ",
    "cái đồ ",
    "tên ",
    "thằng ",
    "con nhỏ ",
    "con bé ",
    "đồ chết tiệt",
)

_NON_DIRECT_SELF_REFERENCES = {
    "dạ",
    "không",
    "no",
    "vâng",
    "yes",
}

_THIRD_PERSON_REFERENCES = {
    "anh ấy",
    "anh ta",
    "bà ấy",
    "cô ấy",
    "cô ta",
    "hắn",
    "he",
    "her",
    "him",
    "họ",
    "nó",
    "she",
    "them",
    "they",
    "ông ấy",
    "y",
}

_TRANSIENT_ADDRESS_NOTES = (
    "biệt danh tạm thời",
    "châm biếm",
    "chọc ghẹo",
    "đóng vai",
    "giả vờ",
    "khi say",
    "lúc say",
    "mỉa mai",
    "người thứ ba",
    "nói đùa",
    "nói về",
    "playful",
    "pretend",
    "roleplay",
    "sarcastic",
    "say rượu",
    "speaking about",
    "tạm thời",
    "teasing",
    "third party",
    "temporary nickname",
    "while drunk",
    "joke",
    "joking",
    "mocking",
    "trêu",
    "đùa",
)

_COMMON_ADDRESS_REFERENCES = {
    "anh",
    "bà",
    "bác",
    "bạn",
    "bệ hạ",
    "bố",
    "cậu",
    "cha",
    "chị",
    "chú",
    "cô",
    "con",
    "dì",
    "em",
    "huynh",
    "mẹ",
    "mày",
    "nàng",
    "ngài",
    "ngươi",
    "ông",
    "sư phụ",
    "ta",
    "tao",
    "thiếp",
    "thầy",
    "tớ",
    "tôi",
}


def coerce_chapter(value, fallback: int = 0) -> int:
    """Coerce a chapter marker to a non-negative integer."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return fallback


def normalize_address_rule(rule: dict, entities: dict, chapter: int = 0) -> dict | None:
    """Normalize one direct-address rule to original character keys."""
    if not isinstance(rule, dict):
        return None

    speaker = resolve_character_ref(str(rule.get("speaker", "")).strip(), entities)
    listener = resolve_character_ref(str(rule.get("listener", "")).strip(), entities)
    if not speaker or not listener or speaker == listener:
        return None

    self_ref = rule.get("self", "")
    other_ref = rule.get("other", "")
    notes = rule.get("notes", "")
    self_ref = self_ref.strip() if isinstance(self_ref, str) else ""
    other_ref = other_ref.strip() if isinstance(other_ref, str) else ""
    notes = notes.strip() if isinstance(notes, str) else ""
    if not self_ref and not other_ref:
        return None

    since = coerce_chapter(rule.get("since"), fallback=max(0, chapter))
    normalized = {
        "speaker": speaker,
        "listener": listener,
        "self": self_ref,
        "other": other_ref,
        "since": since,
    }

    until = rule.get("until")
    if until is not None:
        until_chapter = coerce_chapter(until, fallback=-1)
        if until_chapter >= since:
            normalized["until"] = until_chapter

    if notes:
        normalized["notes"] = notes

    scope = rule.get("scope")
    if scope is not None:
        if not isinstance(scope, str) or scope.strip().casefold() not in ADDRESS_RULE_SCOPES:
            return None
        normalized["scope"] = scope.strip().casefold()

    reason = rule.get("reason")
    if reason is not None:
        if not isinstance(reason, str) or reason.strip().casefold() not in ADDRESS_RULE_REASONS:
            return None
        normalized["reason"] = reason.strip().casefold()

    return normalized


def has_transient_address_note(rule: dict) -> bool:
    """Return whether free-form notes describe a transient address form."""
    notes = str(rule.get("notes", "")).strip().casefold()
    return any(marker in notes for marker in _TRANSIENT_ADDRESS_NOTES)


def is_explicit_temporary_address_observation(rule: dict) -> bool:
    """Return whether structured metadata marks an observation as temporary."""
    return rule.get("scope") == "temporary" or rule.get("reason") in ADDRESS_RULE_TRANSIENT_REASONS


def is_transient_address_rule(rule: dict, entities: dict) -> bool:
    """Reject explicit temporary observations and structurally transient forms."""
    entity_names: list[tuple[str, str]] = []
    for original, info in entities.items():
        if not isinstance(info, dict):
            continue
        entity_names.append((original.casefold(), original))
        translated = get_character_translated_name(info)
        if translated:
            entity_names.append((translated.casefold(), original))
        for alias in info.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                entity_names.append((alias.strip().casefold(), original))

    self_ref = str(rule.get("self", "")).strip().casefold()
    other = str(rule.get("other", "")).strip().casefold()
    if is_explicit_temporary_address_observation(rule):
        return True
    if self_ref in _NON_DIRECT_SELF_REFERENCES:
        return True
    if self_ref in _THIRD_PERSON_REFERENCES or other in _THIRD_PERSON_REFERENCES:
        return True
    strongly_stable = rule.get("scope") == "stable" and rule.get("reason") in ADDRESS_RULE_STABLE_REASONS
    if has_transient_address_note(rule) and not strongly_stable:
        return True
    if other and other not in _COMMON_ADDRESS_REFERENCES:
        has_address_prefix = any(other.startswith(f"{reference} ") for reference in _COMMON_ADDRESS_REFERENCES)
        matched_entities = {
            original for name, original in entity_names if name and (other == name or is_expanded_name(other, name))
        }
        if matched_entities and not has_address_prefix:
            return True
    return any(other.startswith(prefix) for prefix in _TRANSIENT_ADDRESS_PREFIXES)


def normalize_address_rules(rules: list, entities: dict, chapter: int = 0) -> list[dict]:
    """Resolve address rules and build one non-overlapping timeline per pair."""
    if not isinstance(rules, list):
        return []

    candidates: list[tuple[int, dict]] = []
    transient_intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for order, rule in enumerate(rules):
        item = normalize_address_rule(rule, entities, chapter=chapter)
        if not item:
            continue
        if item.get("scope") == "uncertain":
            continue
        if is_transient_address_rule(item, entities):
            since = item.get("since", 0)
            until = item.get("until", since)
            transient_intervals.setdefault((item["speaker"], item["listener"]), []).append((since, until))
            continue
        candidates.append((order, item))

    candidates.sort(key=lambda entry: (entry[1].get("since", 0), entry[0]))
    timelines: dict[tuple[str, str], list[dict]] = {}
    for _, item in candidates:
        pair = (item["speaker"], item["listener"])
        timeline = timelines.setdefault(pair, [])
        if not timeline:
            timeline.append(item)
            continue

        previous = timeline[-1]
        same_form = previous.get("self", "") == item.get("self", "") and previous.get("other", "") == item.get("other", "")
        continuous = previous.get("until") is None or previous["until"] >= item["since"] - 1
        transient_bridge = False
        if same_form and not continuous:
            gap_start = previous["until"] + 1
            gap_end = item["since"] - 1
            covered_until = gap_start - 1
            for start, end in sorted(transient_intervals.get(pair, [])):
                if end < gap_start or start > covered_until + 1:
                    continue
                covered_until = max(covered_until, end)
                if covered_until >= gap_end:
                    transient_bridge = True
                    break
        if same_form and (continuous or transient_bridge):
            if item.get("notes"):
                previous["notes"] = item["notes"]
            if "until" in item:
                previous["until"] = item["until"]
            else:
                previous.pop("until", None)
            continue

        if item["since"] == previous["since"]:
            for field in ("self", "other", "notes"):
                if not item.get(field) and previous.get(field):
                    item[field] = previous[field]
            timeline[-1] = item
            continue

        previous["until"] = min(previous.get("until", item["since"] - 1), item["since"] - 1)
        timeline.append(item)

    return [rule for timeline in timelines.values() for rule in timeline]


def select_active_address_rules(address_rules: list, active_entities: dict, current_chapter: int = 0) -> list[dict]:
    """Select direct-address rules for active characters and the current chapter."""
    if not address_rules or not active_entities:
        return []

    active_names = set(active_entities)
    selected_by_pair: dict[tuple[str, str], dict] = {}
    for rule in address_rules:
        if rule.get("speaker") not in active_names or rule.get("listener") not in active_names:
            continue
        if current_chapter > 0:
            since = rule.get("since", 0)
            until = rule.get("until")
            if isinstance(since, int) and since > current_chapter:
                continue
            if isinstance(until, int) and until < current_chapter:
                continue
        pair = (rule["speaker"], rule["listener"])
        existing = selected_by_pair.get(pair)
        if not existing or rule.get("since", 0) >= existing.get("since", 0):
            selected_by_pair[pair] = rule
    return list(selected_by_pair.values())
