"""Analyze dialogue address across the complete source, without persisting partial results."""

import logging

from src.domain.addressing import is_explicit_temporary_address_observation, normalize_address_rule
from src.domain.candidates import ADDRESS_RULE_CANDIDATE_VERDICTS
from src.domain.chunking import split_into_chunks
from src.domain.entities import resolve_character_ref
from src.models.state import TranslationState
from src.prompts import render_prompt
from src.services.llm import get_llm
from src.services.llm.cancellation import GenerationCancelledError
from src.services.logger import log_ai_call, log_error
from src.utils.json import parse_json_object

_logger = logging.getLogger("novel_ai_trans.job")


def analyze_address(
    state: TranslationState,
    character_context: str,
    entities: dict,
    *,
    chunk_size: int = 5000,
    chunk_overlap: int = 100,
    chunk_mode: str = "chars",
) -> dict:
    """Return chapter-level evidence; any failed part leaves address memory untouched."""
    if not entities or not state["source_text"].strip():
        return {}
    system = render_prompt(
        "address",
        target_language=state.get("target_language", "vi"),
        translation_rules=state.get("translation_rules", "").strip() or "(none)",
        existing_chars_str=character_context,
        chapter_number=str(state["chapter_number"]),
    )
    parts = split_into_chunks(
        state["source_text"],
        chunk_size=chunk_size,
        overlap=chunk_overlap,
        mode=chunk_mode,
    )
    observations: list[dict] = []
    verdicts: dict[tuple[str, str], set[str]] = {}
    try:
        for index, source in enumerate(parts, 1):
            user = f"SOURCE — chapter {state['chapter_number']}, part {index}/{len(parts)}:\n\n{source}"
            response = get_llm().generate(system, user, "address")
            log_ai_call(
                "address",
                system_prompt=system,
                user_prompt=user,
                response=response,
                chapter=state["chapter_number"],
            )
            data = parse_json_object(response)
            for key in ("address_rules", "address_rule_candidate_verdicts"):
                if not isinstance(data.get(key), list) or any(not isinstance(item, dict) for item in data[key]):
                    raise ValueError(f"Invalid address response field: {key}")
            for raw in data["address_rules"]:
                speaker = resolve_character_ref(str(raw.get("speaker", "")), entities)
                listener = resolve_character_ref(str(raw.get("listener", "")), entities)
                if speaker not in entities or listener not in entities or speaker == listener:
                    continue
                item = {**raw, "speaker": speaker, "listener": listener, "since": state["chapter_number"]}
                if item not in observations:
                    observations.append(item)
            for item in data["address_rule_candidate_verdicts"]:
                speaker = resolve_character_ref(str(item.get("speaker", "")), entities)
                listener = resolve_character_ref(str(item.get("listener", "")), entities)
                verdict = item.get("verdict")
                if (
                    speaker in entities
                    and listener in entities
                    and speaker != listener
                    and isinstance(verdict, str)
                    and verdict in ADDRESS_RULE_CANDIDATE_VERDICTS
                    and verdict != "inconclusive"
                ):
                    verdicts.setdefault((speaker, listener), set()).add(verdict)
    except GenerationCancelledError:
        raise
    except Exception as error:
        log_error("Failed to analyze address evidence", error, chapter=state["chapter_number"])
        _logger.warning("Address analysis failed; keeping existing address memory: %s", error)
        return {}

    conflicting_pairs = {pair for pair, values in verdicts.items() if len(values) > 1}
    observations = [
        item
        for item in observations
        if (item["speaker"], item["listener"]) not in conflicting_pairs
        or is_explicit_temporary_address_observation(normalize_address_rule(item, entities) or {})
    ]

    return {
        "address_rules": observations,
        "address_rule_candidate_verdicts": [
            {"speaker": speaker, "listener": listener, "verdict": next(iter(values)) if len(values) == 1 else "inconclusive"}
            for (speaker, listener), values in verdicts.items()
        ],
    }
