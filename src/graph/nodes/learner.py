"""
Learner Node — Extract glossary terms and create chapter summary.

Runs after all chunks are translated. Responsible for:
1. Extracting new terms (character names, place names, special terms)
2. Creating a chapter summary for cross-chapter context
3. Saving both to the glossary JSON file
"""

import logging
import re

from src.domain.candidates import ADDRESS_RULE_CANDIDATE_VERDICTS
from src.domain.entities import (
    get_character_translated_name,
    resolve_character_ref,
)
from src.domain.language import target_language_name
from src.domain.relationships import normalize_character_edges
from src.domain.terms import filter_extracted_terms
from src.models.state import TranslationState
from src.prompts import render_prompt
from src.services.glossary.memory import save_chapter_summary
from src.services.glossary.repository import (
    save_characters_batch,
    save_glossary,
)
from src.services.llm import get_llm
from src.services.logger import log_ai_call, log_error
from src.services.metadata import save_source_language
from src.utils.json import parse_json_object

_logger = logging.getLogger("novel_ai_trans.job")

KINSHIP_TERMS = {
    # English
    "papa",
    "mama",
    "dad",
    "mom",
    "father",
    "mother",
    "uncle",
    "aunt",
    "grandpa",
    "grandma",
    "grandfather",
    "grandmother",
    "brother",
    "sister",
    "son",
    "daughter",
    "child",
    "children",
    "husband",
    "wife",
    "spouse",
    "boyfriend",
    "girlfriend",
    "fiance",
    "fiancee",
    # Chinese
    "爸爸",
    "妈妈",
    "父亲",
    "母亲",
    "爹",
    "娘",
    "爸",
    "妈",
    "叔叔",
    "阿姨",
    "爷爷",
    "奶奶",
    "外公",
    "外婆",
    "祖父",
    "祖母",
    "哥哥",
    "姐姐",
    "弟弟",
    "妹妹",
    "大哥",
    "大姐",
    "小弟",
    "小妹",
    "儿子",
    "女儿",
    "孩子",
    "丈夫",
    "妻子",
    "老公",
    "老婆",
    # Korean
    "아빠",
    "엄마",
    "아버지",
    "어머니",
    "할아버지",
    "할머니",
    "형",
    "오빠",
    "누나",
    "언니",
    "남동생",
    "여동생",
    "아들",
    "딸",
    "남편",
    "아내",
    # Japanese
    "お父さん",
    "お母さん",
    "父",
    "母",
    "パパ",
    "ママ",
    "おじいさん",
    "おばあさん",
    "兄",
    "姉",
    "弟",
    "妹",
    "息子",
    "夫",
    "妻",
    "旦那",
    "家内",
    # Generic role descriptors (not proper names)
    "teacher",
    "student",
    "master",
    "servant",
    "guard",
    "doctor",
    "nurse",
    "driver",
    "cook",
    "chef",
    "maid",
    "butler",
    "soldier",
    "general",
    "king",
    "queen",
    "prince",
    "princess",
    "lord",
    "lady",
    "先生",
    "学生",
    "老师",
    "师傅",
    "徒弟",
    "仆人",
    "护卫",
    "医生",
    "护士",
    "司机",
    "厨师",
    "士兵",
    "将军",
    "国王",
    "女王",
    "王子",
    "公主",
    "선생님",
    "학생",
    "의사",
    "간호사",
    "왕",
    "여왕",
    "왕자",
    "공주",
    "生徒",
    "医者",
    "看護師",
    "王様",
    "王女",
}


ALLOWED_RELATIONSHIP_TYPES = {
    "mother",
    "father",
    "parent",
    "son",
    "daughter",
    "child",
    "sibling",
    "brother",
    "sister",
    "half-sibling",
    "half-brother",
    "half-sister",
    "husband",
    "wife",
    "spouse",
    "romantic interest",
    "crush",
    "ex",
    "ex-partner",
    "friend",
    "enemy",
    "rival",
    "ally",
    "master",
    "disciple",
    "teacher",
    "student",
    "classmate",
    "colleague",
    "servant",
    "employer",
    "boss",
    "employee",
    "acquaintance",
    "neighbor",
    "relative",
    "cousin",
    "grandparent",
    "grandchild",
    "adoptive parent",
    "adoptive child",
    "adoptive sibling",
    "step-parent",
    "step-child",
    "step-sibling",
    "mentor",
    "protector",
    "guardian",
    "ward",
}

LEARNER_SAMPLE_CHARS = 4000


def _sample_across_text(text: str, max_chars: int = LEARNER_SAMPLE_CHARS) -> str:
    """Sample the beginning, middle, and end without increasing prompt size."""
    if len(text) <= max_chars:
        return text

    separator = "\n\n[... omitted ...]\n\n"
    available = max_chars - len(separator) * 2
    section_size = available // 3
    middle_start = max(0, (len(text) - section_size) // 2)
    sections = [
        text[:section_size],
        text[middle_start : middle_start + section_size],
        text[-section_size:],
    ]
    return separator.join(section.strip() for section in sections)


def _sample_aligned_chunks(
    source_chunks: list[str],
    translated_chunks: list[str],
    source_language: str,
    target_name: str,
    max_chars_per_language: int = LEARNER_SAMPLE_CHARS,
) -> str:
    """Sample matching beginning, middle, and ending chunk pairs."""
    pair_count = min(len(source_chunks), len(translated_chunks))
    if pair_count == 0:
        return ""

    indexes = list(range(pair_count)) if pair_count <= 3 else [0, pair_count // 2, pair_count - 1]

    per_chunk_budget = max(1, max_chars_per_language // len(indexes))
    sections = []
    for index in indexes:
        source_sample = _sample_across_text(source_chunks[index], per_chunk_budget)
        translated_sample = _sample_across_text(translated_chunks[index], per_chunk_budget)
        sections.append(
            f"""=== ALIGNED CHUNK {index + 1}/{pair_count} ===
SOURCE ({source_language}):
{source_sample}

TRANSLATION ({target_name}):
{translated_sample}"""
        )
    return "\n\n".join(sections)


def _is_kinship_or_role(name: str) -> bool:
    """Check if a name is actually a kinship term or role descriptor."""
    return name.strip().lower() in KINSHIP_TERMS


def _is_english(text: str) -> bool:
    """Check if text contains only ASCII characters (basic English check)."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


# Pattern to match trailing parenthetical annotations in entity keys.
# Examples: "준기 (Jun Gi)" → "준기", "노을 (No Eul)" → "노을"
_PAREN_ANNOTATION_RE = re.compile(r"\s*\([^)]+\)\s*$")
# Also catch " - annotation" style.
_DASH_ANNOTATION_RE = re.compile(r"\s+-\s+[A-Za-z].*$")


def _strip_entity_key_annotation(key: str) -> str:
    """Remove trailing parenthetical or dash annotations from an entity key.

    LLMs sometimes produce keys like '준기 (Jun Gi)' or '준기 - Jun Gi'
    instead of the bare original name '준기'. This strips those annotations.
    """
    cleaned = _PAREN_ANNOTATION_RE.sub("", key)
    cleaned = _DASH_ANNOTATION_RE.sub("", cleaned)
    return cleaned.strip() or key


def _sanitize_entity_keys(characters: dict) -> dict:
    """Strip parenthetical annotations from entity keys, edges, and address rules."""
    entities = characters.get("entities", {})
    if not entities:
        return characters

    # Build key mapping: old_key -> cleaned_key
    key_map: dict[str, str] = {}
    cleaned_entities: dict = {}
    for old_key, info in entities.items():
        new_key = _strip_entity_key_annotation(old_key)
        if new_key != old_key:
            _logger.warning(
                "Cleaned entity key: %r -> %r",
                old_key,
                new_key,
                extra={
                    "presentation_event": "cli_message",
                    "presentation_message": f"  ⚠ Cleaned entity key: '{old_key}' → '{new_key}'",
                },
            )
        key_map[old_key] = new_key
        # If two old keys map to the same new key, merge (keep last)
        if new_key in cleaned_entities:
            existing = cleaned_entities[new_key]
            for field in ("translated_name", "role", "pronoun"):
                if info.get(field) and not existing.get(field):
                    existing[field] = info[field]
        else:
            cleaned_entities[new_key] = info
    characters["entities"] = cleaned_entities

    # Remap edge references
    edges = characters.get("edges", [])
    if edges:
        cleaned_edges = []
        for edge in edges:
            if len(edge) >= 3:
                edge = list(edge)
                edge[0] = key_map.get(edge[0], _strip_entity_key_annotation(edge[0]))
                edge[1] = key_map.get(edge[1], _strip_entity_key_annotation(edge[1]))
            cleaned_edges.append(edge)
        characters["edges"] = cleaned_edges

    # Remap address_rules references
    rules = characters.get("address_rules", [])
    if rules:
        for rule in rules:
            if isinstance(rule, dict):
                for field in ("speaker", "listener"):
                    val = rule.get(field, "")
                    if val:
                        rule[field] = key_map.get(val, _strip_entity_key_annotation(val))

    return characters


def _normalize_relationship(rel_type: str) -> str:
    """Normalize relationship type to closest allowed English type."""
    rel_lower = rel_type.strip().lower()

    if rel_lower in ALLOWED_RELATIONSHIP_TYPES:
        return rel_lower

    mapping = {
        # Vietnamese
        "mẹ": "mother",
        "cha": "father",
        "bố": "father",
        "ba": "father",
        "con trai": "son",
        "con gái": "daughter",
        "con": "child",
        "anh em": "sibling",
        "chị em": "sibling",
        "anh trai": "brother",
        "chị gái": "sister",
        "em trai": "brother",
        "em gái": "sister",
        "vợ": "wife",
        "chồng": "husband",
        "bạn": "friend",
        "kẻ thù": "enemy",
        "đối thủ": "rival",
        "thầy": "teacher",
        "trò": "disciple",
        "bạn học": "classmate",
        "ông chủ": "boss",
        "người hầu": "servant",
        "người quen": "acquaintance",
        "hàng xóm": "neighbor",
        "ông nội": "grandparent",
        "bà nội": "grandparent",
        "ông ngoại": "grandparent",
        "bà ngoại": "grandparent",
        "cháu": "grandchild",
        "họ hàng": "relative",
        # Chinese
        "母亲": "mother",
        "妈妈": "mother",
        "妈": "mother",
        "父亲": "father",
        "爸爸": "father",
        "爸": "father",
        "儿子": "son",
        "女儿": "daughter",
        "孩子": "child",
        "兄弟": "sibling",
        "姐妹": "sibling",
        "哥哥": "brother",
        "姐姐": "sister",
        "弟弟": "brother",
        "妹妹": "sister",
        "妻子": "wife",
        "老婆": "wife",
        "丈夫": "husband",
        "老公": "husband",
        "朋友": "friend",
        "敌人": "enemy",
        "对手": "rival",
        "老师": "teacher",
        "学生": "student",
        "同学": "classmate",
        "老板": "boss",
        "仆人": "servant",
        "熟人": "acquaintance",
        "邻居": "neighbor",
        "祖父母": "grandparent",
        "孙子": "grandchild",
        "孙女": "grandchild",
        # Korean
        "어머니": "mother",
        "엄마": "mother",
        "아버지": "father",
        "아빠": "father",
        "아들": "son",
        "딸": "daughter",
        "형제": "sibling",
        "자매": "sibling",
        "아내": "wife",
        "남편": "husband",
        "친구": "friend",
        "적": "enemy",
        "ライバル": "rival",
        "선생님": "teacher",
        "제자": "disciple",
        "동창": "classmate",
        # Japanese
        "母": "mother",
        "お母さん": "mother",
        "父": "father",
        "お父さん": "father",
        "息子": "son",
        "娘": "daughter",
        "姉妹": "sibling",
        "妻": "wife",
        "夫": "husband",
        "友達": "friend",
        "敵": "enemy",
        "先生": "teacher",
        "弟子": "disciple",
        "同級生": "classmate",
    }

    if rel_lower in mapping:
        return mapping[rel_lower]

    if _is_english(rel_type):
        return rel_lower

    return rel_type


def _prepare_address_rule_candidate_verdicts(
    raw_verdicts: object,
    candidates: list,
    entities: dict,
) -> list[dict[str, str]]:
    """Return one valid verdict per presented candidate, defaulting omissions to inconclusive."""
    explicit_by_pair: dict[tuple[str, str], str] = {}
    if isinstance(raw_verdicts, list):
        for raw_verdict in raw_verdicts:
            if not isinstance(raw_verdict, dict):
                continue
            speaker = resolve_character_ref(str(raw_verdict.get("speaker", "")).strip(), entities)
            listener = resolve_character_ref(str(raw_verdict.get("listener", "")).strip(), entities)
            verdict_value = raw_verdict.get("verdict", "")
            verdict = verdict_value.strip().casefold() if isinstance(verdict_value, str) else ""
            if speaker and listener and speaker != listener and verdict in ADDRESS_RULE_CANDIDATE_VERDICTS:
                explicit_by_pair[(speaker, listener)] = verdict

    prepared = []
    for candidate in candidates:
        speaker = candidate.get("speaker", "")
        listener = candidate.get("listener", "")
        if not isinstance(speaker, str) or not isinstance(listener, str) or not speaker or not listener:
            continue
        prepared.append(
            {
                "speaker": speaker,
                "listener": listener,
                "verdict": explicit_by_pair.get((speaker, listener), "inconclusive"),
            }
        )
    return prepared


def _build_existing_chars_str(
    entities: dict,
    edges: list,
    address_rules: list | None = None,
    address_rule_candidates: list | None = None,
) -> str:
    """Build existing characters context string for the learner prompt."""
    if not entities:
        return "(none)"

    entity_parts = []
    for name_orig, info in entities.items():
        translated_name = get_character_translated_name(info)
        role = info.get("role", "")
        pronoun = info.get("pronoun", "")
        pronoun_str = f' pronoun="{pronoun}"' if pronoun else ""
        translated_str = f" ({translated_name})" if translated_name else ""
        role_str = f" [{role}{pronoun_str}]" if role or pronoun else ""
        entity_parts.append(f"  {name_orig}{translated_str}{role_str}")

    parts = ["Entities:", *entity_parts]
    if edges:
        edge_parts = []
        for edge in edges:
            if len(edge) >= 3:
                from_name = get_character_translated_name(entities.get(edge[0], {})) or edge[0]
                to_name = get_character_translated_name(entities.get(edge[1], {})) or edge[1]
                edge_parts.append(f"  {from_name}({edge[2]})->{to_name}")
        parts.extend(["Relations:", *edge_parts])

    if address_rules:
        rule_parts = []
        for rule in address_rules:
            speaker = rule.get("speaker", "")
            listener = rule.get("listener", "")
            refs = []
            if rule.get("self"):
                refs.append(f'self="{rule["self"]}"')
            if rule.get("other"):
                refs.append(f'other="{rule["other"]}"')
            if rule.get("notes"):
                refs.append(f'notes="{rule["notes"]}"')
            rule_parts.append(f"  {speaker}->{listener}: " + ", ".join(refs))
        parts.extend(["Address rules:", *rule_parts])

    if address_rule_candidates:
        candidate_parts = []
        for candidate in address_rule_candidates:
            speaker = candidate.get("speaker", "")
            listener = candidate.get("listener", "")
            refs = []
            if candidate.get("self"):
                refs.append(f'self="{candidate["self"]}"')
            if candidate.get("other"):
                refs.append(f'other="{candidate["other"]}"')
            refs.append(f"observations={candidate.get('observations', 1)}")
            if candidate.get("reason"):
                refs.append(f'reason="{candidate["reason"]}"')
            candidate_parts.append(f"  {speaker}->{listener}: " + ", ".join(refs))
        parts.extend(["Pending address hypotheses (re-evaluate from source only):", *candidate_parts])

    return "\n".join(parts)


def learner_node(state: TranslationState, *, summary: bool = False) -> dict:
    """Extract terms and create summary from the translated chapter."""
    novel_name = state["novel_name"]
    chapter_number = state["chapter_number"]
    language = state["source_language"]
    target_language = state.get("target_language", "vi")
    target_name = target_language_name(target_language)

    full_translation = "\n\n".join(state["translated_chunks"])
    source_text = state["source_text"]

    # --- 1. Extract terms + character relationships (single call) ---
    existing_glossary = state.get("glossary", {})
    existing_terms_str = "\n".join(f"  {k} → {v}" for k, v in existing_glossary.items()) if existing_glossary else "(none)"

    existing_characters = state.get("characters", {})
    existing_entities = existing_characters.get("entities", {})
    existing_edges = existing_characters.get("edges", [])
    existing_address_rules = existing_characters.get("address_rules", [])
    existing_address_rule_candidates = existing_characters.get("address_rule_candidates", [])
    existing_chars_str = _build_existing_chars_str(
        existing_entities,
        existing_edges,
        existing_address_rules,
        existing_address_rule_candidates,
    )
    translation_rules = state.get("translation_rules", "").strip() or "(none)"

    learn_system_prompt = render_prompt(
        "learn",
        target_language=target_language,
        target_name=target_name,
        translation_rules=translation_rules,
        existing_terms_str=existing_terms_str,
        existing_chars_str=existing_chars_str,
        chapter_number=str(chapter_number),
    )

    learn_user_prompt = _sample_aligned_chunks(
        state["chunks"],
        state["translated_chunks"],
        language,
        target_name,
    )

    new_terms = {}
    new_characters = {}
    learn_response = ""
    learn_succeeded = False
    try:
        learn_response = get_llm().generate(learn_system_prompt, learn_user_prompt, "learn")

        learn_data = parse_json_object(learn_response)
        new_terms = learn_data.get("terms", {})
        new_characters = learn_data.get("characters", {})
        learn_succeeded = True
    except Exception as e:
        log_error("Failed to extract terms and characters", e, chapter=chapter_number)
        _logger.warning(
            "Failed to extract terms and characters: %s",
            e,
            extra={
                "presentation_event": "cli_message",
                "presentation_message": f"\n  [Warning] Failed to extract terms and characters: {e}",
            },
        )

    # Sanitize entity keys: strip parenthetical annotations from keys/edges/rules
    new_characters = _sanitize_entity_keys(new_characters)

    # Filter out kinship terms and role descriptors from entities
    new_entities = new_characters.get("entities", {})
    filtered_entities = {}
    for name, info in new_entities.items():
        if not _is_kinship_or_role(name):
            filtered_entities[name] = info
        else:
            _logger.warning(
                "Skipped kinship/role term as entity: %s",
                name,
                extra={
                    "presentation_event": "cli_message",
                    "presentation_message": f"  ⚠ Skipped kinship/role term as entity: {name}",
                },
            )
    new_characters["entities"] = filtered_entities

    # Normalize and validate edge relationship types
    new_edges = new_characters.get("edges", [])
    cleaned_edges = []
    edge_entities = {**existing_entities, **filtered_entities}
    for edge in new_edges:
        if len(edge) < 3:
            continue
        from_char, to_char, rel_type = edge[0], edge[1], edge[2]
        if _is_kinship_or_role(from_char) or _is_kinship_or_role(to_char):
            _logger.warning(
                "Skipped edge with kinship term: %s -> %s",
                from_char,
                to_char,
                extra={
                    "presentation_event": "cli_message",
                    "presentation_message": f"  ⚠ Skipped edge with kinship term: {from_char} -> {to_char}",
                },
            )
            continue
        normalized_rel = _normalize_relationship(rel_type)
        cleaned_edges.append([from_char, to_char, normalized_rel] + edge[3:])
    new_characters["edges"] = normalize_character_edges(cleaned_edges, edge_entities)

    # Keep learner-selected terms only when they are grounded in this chapter.
    if new_terms:
        new_terms = filter_extracted_terms(
            source_text,
            new_terms,
            translated_text=full_translation,
            existing_terms=existing_glossary,
        )

    if new_terms:
        save_glossary(novel_name, new_terms)

    new_entities = new_characters.get("entities", {})
    raw_address_rule_observations = new_characters.get("address_rules", [])
    address_rule_observations = raw_address_rule_observations if isinstance(raw_address_rule_observations, list) else []
    raw_candidate_verdicts = new_characters.get("address_rule_candidate_verdicts", [])
    candidate_verdicts = (
        _prepare_address_rule_candidate_verdicts(
            raw_candidate_verdicts,
            existing_address_rule_candidates,
            existing_entities,
        )
        if learn_succeeded
        else []
    )
    new_edges = new_characters.get("edges", [])

    new_characters["address_rules"] = address_rule_observations
    new_characters["address_rule_candidate_verdicts"] = candidate_verdicts

    if new_entities or new_edges or address_rule_observations or candidate_verdicts:
        save_characters_batch(
            novel_name,
            new_entities,
            new_edges,
            address_rules=address_rule_observations,
            address_rule_candidate_verdicts=candidate_verdicts,
            chapter=chapter_number,
        )
        _logger.info(
            "Updated %s character(s), %s relationship(s); observed %s address rule observation(s), "
            "evaluated %s pending hypothesis(es)",
            len(new_entities),
            len(new_edges),
            len(address_rule_observations),
            len(candidate_verdicts),
            extra={
                "presentation_event": "cli_message",
                "presentation_message": (
                    f"  📝 Updated {len(new_entities)} character(s), {len(new_edges)} relationship(s), "
                    f"observed {len(address_rule_observations)} address rule observation(s), "
                    f"evaluated {len(candidate_verdicts)} pending hypothesis(es)"
                ),
            },
        )

    save_source_language(novel_name, state["source_language"])

    log_ai_call(
        "learn",
        system_prompt=learn_system_prompt,
        user_prompt=learn_user_prompt,
        response=learn_response,
        chapter=chapter_number,
        new_terms_count=len(new_terms),
        terms=new_terms,
        characters_count=len(new_characters),
    )

    # --- 2. Create chapter summary ---
    if not summary:
        summary_response = ""
    else:
        summary_system_prompt = render_prompt("summarize", target_language=target_language, target_name=target_name)
        summary_user_prompt = f"Summarize chapter {chapter_number}:\n\n{_sample_across_text(full_translation)}"

        try:
            summary_response = get_llm().generate(summary_system_prompt, summary_user_prompt, "summarize")
            save_chapter_summary(novel_name, chapter_number, summary_response)

            log_ai_call(
                "summarize",
                system_prompt=summary_system_prompt,
                user_prompt=summary_user_prompt,
                response=summary_response,
                chapter=chapter_number,
                summary_length=len(summary_response),
            )
        except Exception as e:
            log_error("Failed to generate summary", e, chapter=chapter_number)
            _logger.warning(
                "Failed to generate summary: %s",
                e,
                extra={
                    "presentation_event": "cli_message",
                    "presentation_message": f"\n  [Warning] Failed to generate summary: {e}",
                },
            )
            summary_response = ""

    return {
        "new_terms": new_terms,
        "new_characters": new_characters,
        "chapter_summary": summary_response,
        "final_translation": full_translation,
    }
