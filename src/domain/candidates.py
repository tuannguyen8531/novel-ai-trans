"""Domain rules for confirming provisional direct-address hypotheses."""

from src.domain.addressing import (
    coerce_chapter,
    has_transient_address_note,
    is_explicit_temporary_address_observation,
    is_transient_address_rule,
    normalize_address_rule,
    normalize_address_rules,
    select_active_address_rules,
)
from src.domain.entities import resolve_character_ref

ADDRESS_RULE_CANDIDATES_KEY = "_address_rule_candidates"
ADDRESS_RULE_INITIAL_CONFIRMATION_COUNT = 2
ADDRESS_RULE_CHANGE_CONFIRMATION_COUNT = 3
ADDRESS_RULE_CONFIRMATION_WINDOW = 20
ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT = 2
ADDRESS_RULE_CANDIDATE_VERDICTS = frozenset({"confirmed", "temporary", "rejected", "inconclusive"})


def normalize_address_rule_candidates(candidates: list, entities: dict) -> list[dict]:
    """Normalize unconfirmed rules, keeping only the latest candidate per pair."""
    if not isinstance(candidates, list):
        return []

    normalized_by_pair: dict[tuple[str, str], dict] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        first_seen = coerce_chapter(candidate.get("first_seen"))
        last_seen = coerce_chapter(candidate.get("last_seen"), fallback=first_seen)
        if first_seen <= 0 or last_seen < first_seen:
            continue
        rule = normalize_address_rule(
            {
                **candidate,
                "since": first_seen,
            },
            entities,
            chapter=first_seen,
        )
        if not rule or rule.get("scope") not in (None, "stable") or is_transient_address_rule(rule, entities):
            continue
        item = {
            "speaker": rule["speaker"],
            "listener": rule["listener"],
            "self": rule.get("self", ""),
            "other": rule.get("other", ""),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "observations": max(1, coerce_chapter(candidate.get("observations"), fallback=1)),
        }
        raw_evaluations = candidate.get("evaluations", [])
        evaluations_by_chapter: dict[int, dict[str, str | int]] = {}
        for evaluation in raw_evaluations if isinstance(raw_evaluations, list) else []:
            if not isinstance(evaluation, dict):
                continue
            evaluation_chapter = coerce_chapter(evaluation.get("chapter"))
            verdict_value = evaluation.get("verdict", "")
            verdict = verdict_value.strip().casefold() if isinstance(verdict_value, str) else ""
            if evaluation_chapter >= first_seen and verdict in ADDRESS_RULE_CANDIDATE_VERDICTS:
                evaluations_by_chapter[evaluation_chapter] = {
                    "chapter": evaluation_chapter,
                    "verdict": verdict,
                }
        evaluations = [evaluations_by_chapter[key] for key in sorted(evaluations_by_chapter)]
        if evaluations:
            item["evaluations"] = evaluations[:ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT]
        if rule.get("notes"):
            item["notes"] = rule["notes"]
        if rule.get("scope"):
            item["scope"] = rule["scope"]
        if rule.get("reason"):
            item["reason"] = rule["reason"]
        normalized_by_pair[(rule["speaker"], rule["listener"])] = item
    return list(normalized_by_pair.values())


def merge_address_rule_candidates(
    address_rules: list,
    candidates: list,
    incoming_rules: list,
    candidate_verdicts: list,
    entities: dict,
    chapter: int,
) -> tuple[list[dict], list[dict]]:
    """Confirm learned address rules across distinct nearby chapters."""
    stable_rules = normalize_address_rules(address_rules, entities)
    pending = normalize_address_rule_candidates(candidates, entities)
    observed_chapter = max(0, chapter)
    if observed_chapter > 0:
        pending = [item for item in pending if observed_chapter - item["last_seen"] <= ADDRESS_RULE_CONFIRMATION_WINDOW]

    pending_by_pair = {(item["speaker"], item["listener"]): item for item in pending}
    evaluated_signatures: dict[tuple[str, str, str, str, int], str] = {}
    verdict_blocked_forms: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    rules_to_merge = list(incoming_rules) if isinstance(incoming_rules, list) else []
    seen_verdict_pairs: set[tuple[str, str]] = set()
    for raw_verdict in candidate_verdicts if isinstance(candidate_verdicts, list) else []:
        if not isinstance(raw_verdict, dict):
            continue
        speaker = resolve_character_ref(str(raw_verdict.get("speaker", "")).strip(), entities)
        listener = resolve_character_ref(str(raw_verdict.get("listener", "")).strip(), entities)
        verdict_value = raw_verdict.get("verdict", "")
        verdict = verdict_value.strip().casefold() if isinstance(verdict_value, str) else ""
        pair = (speaker, listener)
        if (
            not speaker
            or not listener
            or speaker == listener
            or verdict not in ADDRESS_RULE_CANDIDATE_VERDICTS
            or pair in seen_verdict_pairs
        ):
            continue
        seen_verdict_pairs.add(pair)
        verdict_candidate = pending_by_pair.get(pair)
        if verdict_candidate is None:
            continue

        form = (verdict_candidate.get("self", ""), verdict_candidate.get("other", ""))
        evaluated_signatures[(pair[0], pair[1], form[0], form[1], verdict_candidate["first_seen"])] = verdict
        if verdict == "confirmed":
            rules_to_merge.append(
                {
                    "speaker": pair[0],
                    "listener": pair[1],
                    "self": form[0],
                    "other": form[1],
                    "scope": "stable",
                    "reason": verdict_candidate.get("reason", "default"),
                }
            )
        elif verdict in {"temporary", "rejected"}:
            verdict_blocked_forms.add((pair, form))
            pending_by_pair.pop(pair, None)

    incoming_by_pair: dict[tuple[str, str], dict] = {}
    blocked_forms = set(verdict_blocked_forms)
    for raw_rule in rules_to_merge:
        item = normalize_address_rule(raw_rule, entities, chapter=observed_chapter)
        if not item:
            continue
        pair = (item["speaker"], item["listener"])
        form = (item.get("self", ""), item.get("other", ""))
        scope = item.get("scope", "")
        if is_explicit_temporary_address_observation(item):
            # Explicit temporary evidence may cancel pending evidence, but confirmed stable phases stay sticky.
            blocked_forms.add((pair, form))
            existing_candidate = pending_by_pair.get(pair)
            if existing_candidate is not None and form == (
                existing_candidate.get("self", ""),
                existing_candidate.get("other", ""),
            ):
                pending_by_pair.pop(pair, None)
            existing_incoming = incoming_by_pair.get(pair)
            if existing_incoming is not None and form == (
                existing_incoming.get("self", ""),
                existing_incoming.get("other", ""),
            ):
                incoming_by_pair.pop(pair, None)
            continue
        # Free-form notes and structural heuristics are weak evidence: ignore the observation without mutating memory.
        if has_transient_address_note(item) or is_transient_address_rule(item, entities):
            continue
        # A source-grounded uncertain observation is useful evidence for a pending
        # hypothesis, but it must never become an active rule without confirmation.
        if scope not in {"stable", "uncertain"} or (pair, form) in blocked_forms:
            continue
        incoming_by_pair[pair] = item

    for pair, item in incoming_by_pair.items():
        seen_chapter = observed_chapter or item.get("since", 0)
        if seen_chapter <= 0:
            continue

        active = select_active_address_rules(
            stable_rules,
            {pair[0]: entities[pair[0]], pair[1]: entities[pair[1]]},
            seen_chapter,
        )
        active_rule = next((rule for rule in active if (rule["speaker"], rule["listener"]) == pair), None)
        form = (item.get("self", ""), item.get("other", ""))
        if active_rule and form == (active_rule.get("self", ""), active_rule.get("other", "")):
            pending_by_pair.pop(pair, None)
            continue

        existing_candidate = pending_by_pair.get(pair)
        same_candidate = existing_candidate is not None and form == (
            existing_candidate.get("self", ""),
            existing_candidate.get("other", ""),
        )
        if existing_candidate is not None and seen_chapter <= existing_candidate["last_seen"]:
            continue
        within_window = (
            existing_candidate is not None and seen_chapter - existing_candidate["last_seen"] <= ADDRESS_RULE_CONFIRMATION_WINDOW
        )
        candidate: dict
        if existing_candidate is not None and same_candidate and within_window:
            candidate = existing_candidate
            if seen_chapter > candidate["last_seen"]:
                candidate["last_seen"] = seen_chapter
                candidate["observations"] += 1
                if item.get("notes"):
                    candidate["notes"] = item["notes"]
                candidate["scope"] = "stable"
                if item.get("reason") and (item["reason"] == "relationship_change" or not candidate.get("reason")):
                    candidate["reason"] = item["reason"]
        else:
            candidate = {
                "speaker": pair[0],
                "listener": pair[1],
                "self": form[0],
                "other": form[1],
                "first_seen": seen_chapter,
                "last_seen": seen_chapter,
                "observations": 1,
                "scope": "stable",
            }
            if item.get("notes"):
                candidate["notes"] = item["notes"]
            candidate["scope"] = "stable"
            if item.get("reason"):
                candidate["reason"] = item["reason"]
            pending_by_pair[pair] = candidate

        confirmation_count = required_address_rule_observations(candidate, active_rule)
        if candidate["observations"] >= confirmation_count:
            promoted = {
                "speaker": pair[0],
                "listener": pair[1],
                "self": candidate.get("self", ""),
                "other": candidate.get("other", ""),
                "since": candidate["first_seen"],
            }
            if candidate.get("notes"):
                promoted["notes"] = candidate["notes"]
            if candidate.get("scope"):
                promoted["scope"] = candidate["scope"]
            if candidate.get("reason"):
                promoted["reason"] = candidate["reason"]
            stable_rules = normalize_address_rules([*stable_rules, promoted], entities)
            pending_by_pair.pop(pair, None)

    if observed_chapter > 0:
        for candidate in pending_by_pair.values():
            signature = (
                candidate["speaker"],
                candidate["listener"],
                candidate.get("self", ""),
                candidate.get("other", ""),
                candidate["first_seen"],
            )
            verdict = evaluated_signatures.get(signature)
            if verdict is None:
                continue
            evaluations = candidate.setdefault("evaluations", [])
            evaluated_chapters = {evaluation.get("chapter") for evaluation in evaluations if isinstance(evaluation, dict)}
            if observed_chapter not in evaluated_chapters and len(evaluations) < ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT:
                evaluations.append({"chapter": observed_chapter, "verdict": verdict})

    return stable_rules, list(pending_by_pair.values())


def required_address_rule_observations(candidate: dict, active_rule: dict | None) -> int:
    """Return the stable-observation threshold for one pending hypothesis."""
    if active_rule is None or candidate.get("reason") == "relationship_change":
        return ADDRESS_RULE_INITIAL_CONFIRMATION_COUNT
    return ADDRESS_RULE_CHANGE_CONFIRMATION_COUNT


def select_active_address_rule_candidates(
    candidates: list,
    active_entities: dict,
    current_chapter: int = 0,
) -> list[dict]:
    """Select pending hypotheses for active pairs with remaining learner evaluations."""
    if not candidates or not active_entities:
        return []

    active_names = set(active_entities)
    selected: list[dict] = []
    for candidate in candidates:
        if candidate.get("speaker") not in active_names or candidate.get("listener") not in active_names:
            continue
        first_seen = candidate.get("first_seen", 0)
        last_seen = candidate.get("last_seen", first_seen)
        evaluations = candidate.get("evaluations", [])
        evaluation_items = evaluations if isinstance(evaluations, list) else []
        evaluated_chapters = {evaluation.get("chapter") for evaluation in evaluation_items if isinstance(evaluation, dict)}
        if current_chapter > 0:
            if not isinstance(first_seen, int) or first_seen > current_chapter:
                continue
            if isinstance(last_seen, int) and last_seen > current_chapter:
                continue
            if isinstance(last_seen, int) and last_seen == current_chapter and current_chapter not in evaluated_chapters:
                continue
            if isinstance(last_seen, int) and current_chapter - last_seen > ADDRESS_RULE_CONFIRMATION_WINDOW:
                continue
        if current_chapter not in evaluated_chapters and len(evaluation_items) >= ADDRESS_RULE_CANDIDATE_EVALUATION_LIMIT:
            continue
        selected.append(candidate)
    return selected
