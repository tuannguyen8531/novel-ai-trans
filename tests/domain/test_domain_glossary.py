import pytest

from src.domain.addressing import normalize_address_rules, select_active_address_rules
from src.domain.candidates import ADDRESS_RULE_CANDIDATES_KEY
from src.domain.context import (
    merge_character_context,
    select_active_character_context,
    upsert_relationship,
)
from src.domain.formatting import (
    format_address_rule_candidates,
    format_address_rules,
    format_relationships_shorthand,
)
from src.domain.glossary import (
    PENDING_REPLACEMENTS_KEY,
    audit_term_usage,
    find_glossary_replacement_conflicts,
    format_glossary_for_prompt,
    merge_pending_replacements,
    normalize_glossary_data,
    queue_pending_replacement,
    replace_glossary_value,
    replace_glossary_values,
    select_active_glossary_terms,
    validate_glossary_data,
)
from src.domain.relationships import normalize_character_edges


def test_queue_pending_replacement_collapses_edit_chain_and_revert():
    data = queue_pending_replacement(
        {},
        kind="term",
        sources=["魔法"],
        old_value="ma thuật",
        new_value="ma pháp",
    )
    data = queue_pending_replacement(
        data,
        kind="term",
        sources=["魔法"],
        old_value="ma pháp",
        new_value="huyền thuật",
    )

    assert data[PENDING_REPLACEMENTS_KEY] == [
        {
            "kind": "term",
            "sources": ["魔法"],
            "old": "ma thuật",
            "new": "huyền thuật",
        }
    ]

    reverted = queue_pending_replacement(
        data,
        kind="term",
        sources=["魔法"],
        old_value="huyền thuật",
        new_value="ma thuật",
    )
    assert reverted[PENDING_REPLACEMENTS_KEY] == []


def test_merge_pending_replacements_connects_restored_and_current_edits():
    restored = [{"kind": "term", "sources": ["魔法"], "old": "ma thuật", "new": "ma pháp"}]
    current = [{"kind": "term", "sources": ["魔法"], "old": "ma pháp", "new": "huyền thuật"}]

    assert merge_pending_replacements(restored, current) == [
        {
            "kind": "term",
            "sources": ["魔法"],
            "old": "ma thuật",
            "new": "huyền thuật",
        }
    ]


def test_format_glossary_for_prompt():
    terms = {"李白": "Lý Bạch", "杜甫": "Đỗ Phủ"}
    result = format_glossary_for_prompt(terms)
    assert "GLOSSARY" in result
    assert "李白 → Lý Bạch" in result
    assert "杜甫 → Đỗ Phủ" in result
    assert "END GLOSSARY" in result


def test_format_empty_glossary():
    assert format_glossary_for_prompt({}) == ""


def test_select_active_glossary_terms_only_keeps_terms_in_source_text():
    terms = {
        "玄天宗": "Huyền Thiên Tông",
        "归墟": "Quy Khư",
        "dao": "đạo",
    }

    result = select_active_glossary_terms(terms, "玄天宗 đệ tử dùng dao, không phải daode.")

    assert result == {
        "玄天宗": "Huyền Thiên Tông",
        "dao": "đạo",
    }


def test_validate_glossary_data_accepts_current_schema():
    data = {
        "terms": {"李明": "Lý Minh"},
        "source_language": "chinese",
        "entities": {"李明": {"translated_name": "Lý Minh", "role": "protagonist", "pronoun": "cậu"}},
        "edges": [["李明", "张伟", "friend", 1]],
        "address_rules": [{"speaker": "李明", "listener": "张伟", "self": "ta", "other": "ngươi", "since": 1}],
        "chapter_summaries": {"1": "Summary"},
    }

    issues = validate_glossary_data(data)

    assert "edge 0 references unknown character '张伟'" in issues
    assert "address rule 0 references unknown listener '张伟'" in issues
    assert len(issues) == 2


def test_validate_glossary_data_accepts_legacy_name_vi():
    data = {
        "entities": {"李明": {"name_vi": "Lý Minh", "role": "protagonist", "pronoun": "cậu"}},
    }

    assert validate_glossary_data(data) == []


def test_validate_glossary_data_reports_bad_shapes():
    issues = validate_glossary_data(
        {
            "terms": {"": ""},
            "entities": {"李明": {"translated_name": 123}},
            "edges": [["李明"]],
            "address_rules": [{"speaker": "李明", "listener": "", "self": 1, "since": "1"}],
            "chapter_summaries": {"one": 1},
        }
    )

    assert "terms contains an empty or non-string source term" in issues
    assert "term '' has an empty or non-string translation" in issues
    assert "entity '李明'.translated_name must be a string" in issues
    assert "edge 0 must be [from, to, relationship, since_chapter?]" in issues
    assert "address rule 0 has an invalid listener" in issues
    assert "address rule 0.self must be a string" in issues
    assert "address rule 0.since must be an integer" in issues
    assert "chapter summary key 'one' must be a numeric string" in issues
    assert "chapter summary 'one' must be a string" in issues


def test_validate_glossary_data_accepts_address_rule_candidate_schema():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        ADDRESS_RULE_CANDIDATES_KEY: [
            {
                "speaker": "李明",
                "listener": "张伟",
                "self": "tôi",
                "other": "cậu",
                "scope": "stable",
                "reason": "default",
                "first_seen": 10,
                "last_seen": 10,
                "observations": 1,
                "evaluations": [
                    {"chapter": 11, "verdict": "confirmed"},
                    {"chapter": 12, "verdict": "inconclusive"},
                ],
            }
        ],
    }

    assert validate_glossary_data(data) == []


def test_validate_glossary_data_reports_invalid_address_rule_candidates():
    issues = validate_glossary_data(
        {
            "entities": {"李明": {"translated_name": "Lý Minh"}},
            ADDRESS_RULE_CANDIDATES_KEY: [
                {
                    "speaker": "missing",
                    "listener": 3,
                    "self": 1,
                    "scope": "temporary",
                    "reason": "joke",
                    "first_seen": "10",
                    "last_seen": -1,
                    "observations": 0,
                    "evaluations": [
                        {"chapter": 9, "verdict": "bad"},
                        {"chapter": 9, "verdict": "confirmed"},
                        {"chapter": "10", "verdict": 3},
                    ],
                },
                {
                    "speaker": "李明",
                    "listener": "李明",
                    "other": "cậu",
                    "first_seen": 10,
                    "last_seen": 9,
                    "observations": "two",
                    "evaluations": [{"chapter": 9, "verdict": "inconclusive"}],
                },
            ],
        }
    )

    assert "address rule candidate 0 has an invalid listener" in issues
    assert "address rule candidate 0 references unknown speaker 'missing'" in issues
    assert "address rule candidate 0.self must be a string" in issues
    assert "address rule candidate 0.scope must be stable" in issues
    assert "address rule candidate 0.reason is invalid" in issues
    assert "address rule candidate 0.first_seen must be a positive integer" in issues
    assert "address rule candidate 0.last_seen must be a positive integer" in issues
    assert "address rule candidate 0.observations must be a positive integer" in issues
    assert "address rule candidate 0.evaluations[0].verdict is invalid" in issues
    assert "address rule candidate 0.evaluations[2].chapter must be a positive integer" in issues
    assert "address rule candidate 0.evaluations[2].verdict is invalid" in issues
    assert "address rule candidate 0.evaluations must not contain duplicate chapters" in issues
    assert "address rule candidate 0.evaluations exceeds the candidate evaluation limit" in issues
    assert "address rule candidate 1 speaker and listener must differ" in issues
    assert "address rule candidate 1.last_seen must not precede first_seen" in issues
    assert "address rule candidate 1.observations must be a positive integer" in issues
    assert "address rule candidate 1.evaluations[0].chapter must not precede first_seen" in issues


def test_validate_glossary_data_reports_candidate_collection_shape():
    issues = validate_glossary_data({ADDRESS_RULE_CANDIDATES_KEY: {}})

    assert issues == [f"{ADDRESS_RULE_CANDIDATES_KEY} must be a list"]


def test_validate_glossary_data_rejects_notes_only_address_memory():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        "address_rules": [{"speaker": "李明", "listener": "张伟", "notes": "context"}],
        ADDRESS_RULE_CANDIDATES_KEY: [
            {
                "speaker": "李明",
                "listener": "张伟",
                "notes": "context",
                "first_seen": 10,
                "last_seen": 10,
                "observations": 1,
            }
        ],
    }

    issues = validate_glossary_data(data)

    assert "address rule 0 must define self or other" in issues
    assert "address rule candidate 0 must define self or other" in issues


def test_validate_glossary_data_reports_bad_character_aliases():
    issues = validate_glossary_data(
        {
            "entities": {
                "李明": {"translated_name": "Lý Minh", "aliases": ["", 123]},
                "张伟": {"translated_name": "Trương Vĩ", "aliases": "伟"},
            },
        }
    )

    assert "entity '李明'.aliases contains an empty or non-string alias" in issues
    assert "entity '张伟'.aliases must be a list" in issues


def test_audit_term_usage_reports_missing_translation_and_source_leak():
    issues = audit_term_usage(
        {"李明": "Lý Minh", "张伟": "Trương Vĩ"},
        "李明 gặp 张伟.",
        "李明 gặp Trương Vĩ.",
    )

    assert issues == [
        {"term": "李明", "expected": "Lý Minh", "issue": "missing_translation"},
        {"term": "李明", "expected": "Lý Minh", "issue": "source_term_leaked"},
    ]


def test_replace_glossary_term_capitalizes_only_at_sentence_start():
    updated, count = replace_glossary_value(
        'Ma thuật cũ. "ma thuật" mới và ma thuật khác.',
        "ma thuật",
        "ma pháp AI",
        capitalize_sentence_start=True,
    )

    assert count == 3
    assert updated == 'Ma pháp AI cũ. "Ma pháp AI" mới và ma pháp AI khác.'


def test_replace_character_name_keeps_configured_casing():
    updated, count = replace_glossary_value(
        "Lý Bạch gặp Lý Bạch.",
        "Lý Bạch",
        "lý thái bạch",
        capitalize_sentence_start=False,
    )

    assert count == 2
    assert updated == "lý thái bạch gặp lý thái bạch."


def test_select_active_character_context_excludes_first_degree_neighbors():
    entities = {
        "李明": {"translated_name": "Lý Minh", "role": "protagonist"},
        "张伟": {"translated_name": "Trương Vĩ", "role": "supporting"},
        "王芳": {"translated_name": "Vương Phương", "role": "minor"},
    }
    edges = [["李明", "张伟", "friend", 1], ["王芳", "张伟", "sibling", 2]]

    active_entities, active_edges = select_active_character_context(entities, edges, "李明，走进房间。")

    assert set(active_entities) == {"李明"}
    assert active_edges == []


def test_merge_character_context_keeps_first_pronoun_and_dedupes_reverse_edges():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh", "role": "minor", "pronoun": "cậu"},
            "张伟": {"translated_name": "Trương Vĩ", "role": "supporting", "pronoun": ""},
        },
        "edges": [["李明", "张伟", "friend", 1]],
    }

    result = merge_character_context(
        data,
        {"李明": {"translated_name": "Lý Minh", "role": "protagonist", "pronoun": "anh ấy"}},
        [["张伟", "李明", "rival"]],
        chapter=3,
    )

    assert result["entities"]["李明"]["role"] == "protagonist"
    assert result["entities"]["李明"]["translated_name"] == "Lý Minh"
    assert "name_vi" not in result["entities"]["李明"]
    assert result["entities"]["李明"]["pronoun"] == "cậu"
    assert result["edges"] == [["李明", "张伟", "friend", 1]]


def test_merge_character_context_migrates_legacy_name_vi():
    data = {
        "entities": {"李明": {"name_vi": "Lý Minh", "role": "minor", "pronoun": "cậu"}},
    }

    result = merge_character_context(data, {}, [], chapter=1)

    assert result["entities"]["李明"] == {
        "translated_name": "Lý Minh",
        "role": "minor",
        "pronoun": "cậu",
    }


def test_normalize_character_edges_resolves_translated_names_and_dedupes():
    entities = {
        "카일 윈프레드": {"translated_name": "Kyle Winfred"},
        "이사벨 유스티아": {"translated_name": "Isabelle Justia"},
    }
    edges = [
        ["카일 윈프레드", "이사벨 유스티아", "romantic interest", 1],
        ["Kyle Winfred", "Isabelle Justia", "ex", 13],
        ["Unknown", "Kyle Winfred", "friend", 13],
    ]

    assert normalize_character_edges(edges, entities) == [
        ["카일 윈프레드", "이사벨 유스티아", "romantic interest", 1],
    ]


def test_normalize_glossary_data_drops_pronoun_examples():
    data = {
        "entities": {"李明": {"name_vi": "Lý Minh", "role": "minor", "pronoun": "cậu"}},
        "edges": [["Lý Minh", "missing", "friend", 1]],
        "pronoun_examples": {"李明": ["Cậu bước vào phòng."]},
    }

    result = normalize_glossary_data(data)

    assert result["entities"]["李明"]["translated_name"] == "Lý Minh"
    assert result["edges"] == []
    assert result["address_rules"] == []
    assert "pronoun_examples" not in result


def test_normalize_address_rules_resolves_names_and_dedupes():
    entities = {
        "카일": {"translated_name": "Kyle"},
        "이사벨": {"translated_name": "Isabelle"},
    }
    rules = [
        {"speaker": "Kyle", "listener": "Isabelle", "self": "ta", "other": "nàng", "since": "3"},
        {"speaker": "카일", "listener": "이사벨", "self": "", "other": "em", "since": 3, "notes": "warmer later"},
        {"speaker": "Unknown", "listener": "Kyle", "self": "ta", "other": "ngươi", "since": 3},
    ]

    result = normalize_address_rules(rules, entities, chapter=2)

    assert result == [
        {
            "speaker": "카일",
            "listener": "이사벨",
            "self": "ta",
            "other": "em",
            "since": 3,
            "notes": "warmer later",
        }
    ]


def test_select_active_address_rules_filters_by_pair_and_chapter():
    active_entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1, "until": 3},
        {"speaker": "张伟", "listener": "李明", "self": "tao", "other": "mày", "since": 5},
        {"speaker": "李明", "listener": "王芳", "self": "tôi", "other": "cô", "since": 1},
    ]

    assert select_active_address_rules(rules, active_entities, current_chapter=2) == [rules[0]]
    assert select_active_address_rules(rules, active_entities, current_chapter=5) == [rules[1]]


def test_normalize_address_rules_builds_non_overlapping_pair_timeline():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 2},
        {"speaker": "李明", "listener": "张伟", "self": "tao", "other": "mày", "since": 5},
    ]

    assert normalize_address_rules(rules, entities) == [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "tôi",
            "other": "cậu",
            "since": 1,
            "until": 4,
        },
        {"speaker": "李明", "listener": "张伟", "self": "tao", "other": "mày", "since": 5},
    ]


def test_normalize_address_rules_drops_names_and_one_off_insults():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
        "王芳": {"translated_name": "Vương Phương"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "Vĩ", "since": 1},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "đồ ngốc", "since": 2},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "Phương", "since": 3},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 4},
    ]

    assert normalize_address_rules(rules, entities) == [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 4},
    ]


def test_normalize_address_rules_drops_non_direct_and_temporary_references():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "vâng", "other": "anh", "since": 1},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cô ấy", "since": 2},
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "em",
            "other": "thầy",
            "since": 3,
            "scope": "stable",
            "reason": "roleplay",
        },
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "vợ",
            "other": "chồng",
            "since": 4,
            "notes": "nói đùa về việc kết hôn",
        },
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 5},
    ]

    assert normalize_address_rules(rules, entities) == [rules[-1]]


def test_normalize_address_rules_keeps_structured_stable_rule_despite_ambiguous_notes():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rule = {
        "speaker": "李明",
        "listener": "张伟",
        "self": "anh",
        "other": "em",
        "since": 10,
        "scope": "stable",
        "reason": "default",
        "notes": "ban đầu nói đùa nhưng nay đã nghiêm túc",
    }

    assert normalize_address_rules([rule], entities) == [rule]


def test_notes_only_address_rule_is_rejected_before_candidate_persistence():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rule = [{"speaker": "李明", "listener": "张伟", "notes": "stable relationship"}]

    result = merge_character_context({}, entities, [], rule, chapter=10)

    assert normalize_address_rules(rule, entities, chapter=10) == []
    assert result["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in result


def test_normalize_address_rules_bridges_transient_rule_between_stable_forms():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1, "until": 2},
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "em",
            "other": "thầy",
            "since": 3,
            "until": 3,
            "notes": "temporary roleplay",
        },
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 4},
    ]

    assert normalize_address_rules(rules, entities) == [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1}
    ]


def test_normalize_address_rules_preserves_closed_gap_between_same_forms():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1, "until": 2},
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 10},
    ]

    assert normalize_address_rules(rules, entities) == rules


def test_temporary_scope_and_vietnamese_notes_never_become_candidates():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    temporary_rules = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "em",
            "other": "thầy",
            "scope": "stable",
            "notes": "đóng vai thầy trò tạm thời",
        },
        {
            "speaker": "张伟",
            "listener": "李明",
            "self": "thầy",
            "other": "em",
            "scope": "temporary",
        },
    ]

    first = merge_character_context({}, entities, [], temporary_rules, chapter=1)
    second = merge_character_context(first, {}, [], temporary_rules, chapter=2)

    assert first["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in first
    assert second["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in second


def test_merge_character_context_confirms_address_rule_in_two_distinct_chapters():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    observed = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "tôi",
            "other": "cậu",
            "scope": "stable",
            "reason": "default",
        }
    ]

    first = merge_character_context({}, entities, [], observed, chapter=10)
    conflicting_retry = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "tao",
            "other": "mày",
            "scope": "stable",
            "reason": "default",
        }
    ]
    repeated_same_chapter = merge_character_context(first, {}, [], conflicting_retry, chapter=10)
    confirmed = merge_character_context(repeated_same_chapter, {}, [], observed, chapter=11)

    assert first["address_rules"] == []
    assert first[ADDRESS_RULE_CANDIDATES_KEY][0]["observations"] == 1
    assert repeated_same_chapter[ADDRESS_RULE_CANDIDATES_KEY][0]["observations"] == 1
    assert repeated_same_chapter[ADDRESS_RULE_CANDIDATES_KEY][0]["self"] == "tôi"
    assert confirmed["address_rules"] == [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "tôi",
            "other": "cậu",
            "since": 10,
            "scope": "stable",
            "reason": "default",
        }
    ]
    assert ADDRESS_RULE_CANDIDATES_KEY not in confirmed


def test_candidate_verdict_confirms_first_address_rule_from_continuing_context():
    entities = {
        "许韵": {"translated_name": "Hứa Vận"},
        "温渝": {"translated_name": "Ôn Du"},
    }
    first_observation = [
        {
            "speaker": "许韵",
            "listener": "温渝",
            "self": "tớ",
            "other": "cậu",
            "scope": "stable",
            "reason": "default",
        }
    ]

    pending = merge_character_context({}, entities, [], first_observation, chapter=2)
    confirmed = merge_character_context(
        pending,
        {},
        [],
        address_rule_candidate_verdicts=[
            {
                "speaker": "许韵",
                "listener": "温渝",
                "verdict": "confirmed",
            }
        ],
        chapter=3,
    )

    assert confirmed["address_rules"] == [
        {
            "speaker": "许韵",
            "listener": "温渝",
            "self": "tớ",
            "other": "cậu",
            "since": 2,
            "scope": "stable",
            "reason": "default",
        }
    ]
    assert ADDRESS_RULE_CANDIDATES_KEY not in confirmed


@pytest.mark.parametrize("verdict", ["temporary", "rejected"])
def test_decisive_negative_verdict_removes_candidate_without_changing_stable_memory(verdict):
    entities = {
        "许韵": {"translated_name": "Hứa Vận"},
        "温渝": {"translated_name": "Ôn Du"},
    }
    pending = merge_character_context(
        {},
        entities,
        [],
        [
            {
                "speaker": "许韵",
                "listener": "温渝",
                "self": "tớ",
                "other": "cậu",
                "scope": "stable",
                "reason": "default",
            }
        ],
        chapter=2,
    )

    resolved = merge_character_context(
        pending,
        {},
        [],
        address_rule_candidate_verdicts=[
            {
                "speaker": "许韵",
                "listener": "温渝",
                "verdict": verdict,
            }
        ],
        chapter=3,
    )

    assert resolved["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in resolved


def test_legacy_hint_history_does_not_consume_learner_evaluation_budget():
    normalized = normalize_glossary_data(
        {
            "entities": {
                "许韵": {"translated_name": "Hứa Vận"},
                "温渝": {"translated_name": "Ôn Du"},
            },
            ADDRESS_RULE_CANDIDATES_KEY: [
                {
                    "speaker": "许韵",
                    "listener": "温渝",
                    "self": "tớ",
                    "other": "cậu",
                    "first_seen": 2,
                    "last_seen": 2,
                    "observations": 1,
                    "hinted_chapters": [3, 4],
                    "scope": "stable",
                    "reason": "default",
                }
            ],
        }
    )

    candidate = normalized[ADDRESS_RULE_CANDIDATES_KEY][0]
    assert "hinted_chapters" not in candidate
    assert "evaluations" not in candidate


def test_merge_character_context_ignores_observation_without_scope():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    observation = [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu"}]

    result = merge_character_context({}, entities, [], observation, chapter=10)

    assert result["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in result


def test_temporary_observation_cancels_matching_stable_candidate():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    stable_misclassification = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "em",
            "other": "thầy",
            "scope": "stable",
            "reason": "default",
        }
    ]
    corrected = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "em",
            "other": "thầy",
            "scope": "temporary",
            "reason": "roleplay",
        }
    ]

    first = merge_character_context({}, entities, [], stable_misclassification, chapter=10)
    corrected_result = merge_character_context(first, {}, [], corrected, chapter=11)

    assert first[ADDRESS_RULE_CANDIDATES_KEY][0]["observations"] == 1
    assert corrected_result["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in corrected_result


def test_reconfirmed_active_rule_rejects_pending_phase_change():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    confirmed = {
        "speaker": "李明",
        "listener": "张伟",
        "self": "tôi",
        "other": "cô",
        "since": 1,
        "scope": "stable",
        "reason": "default",
    }
    proposed_change = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "relationship_change",
        }
    ]

    pending = merge_character_context(
        {"entities": entities, "address_rules": [confirmed]},
        {},
        [],
        proposed_change,
        chapter=10,
    )
    rejected = merge_character_context(
        pending,
        {},
        [],
        [{**confirmed, "since": 11}],
        chapter=11,
    )

    assert pending[ADDRESS_RULE_CANDIDATES_KEY][0]["self"] == "anh"
    assert rejected["address_rules"] == [confirmed]
    assert ADDRESS_RULE_CANDIDATES_KEY not in rejected


def test_suspicious_notes_do_not_cancel_a_stable_candidate():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    stable = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "default",
        }
    ]
    ambiguous_notes = [
        {
            **stable[0],
            "notes": "ban đầu nói đùa nhưng nay đã nghiêm túc",
        }
    ]

    first = merge_character_context({}, entities, [], stable, chapter=10)
    ambiguous = merge_character_context(first, {}, [], ambiguous_notes, chapter=11)
    confirmed = merge_character_context(ambiguous, {}, [], stable, chapter=12)

    assert ambiguous[ADDRESS_RULE_CANDIDATES_KEY][0]["observations"] == 1
    assert confirmed["address_rules"] == [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "since": 10,
            "scope": "stable",
            "reason": "default",
        }
    ]
    assert ADDRESS_RULE_CANDIDATES_KEY not in confirmed


def test_stable_candidate_survives_sparse_character_appearances():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    stable = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "default",
        }
    ]

    first = merge_character_context({}, entities, [], stable, chapter=10)
    confirmed = merge_character_context(first, {}, [], stable, chapter=30)

    assert confirmed["address_rules"][0]["since"] == 10
    assert ADDRESS_RULE_CANDIDATES_KEY not in confirmed


def test_temporary_observation_does_not_retract_confirmed_stable_phase():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    original_rule = {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1}
    data = {"entities": entities, "address_rules": [original_rule]}
    misclassified = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "relationship_change",
        }
    ]
    corrected = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "temporary",
            "reason": "joke",
        }
    ]

    first = merge_character_context(data, {}, [], misclassified, chapter=10)
    promoted = merge_character_context(first, {}, [], misclassified, chapter=11)
    after_temporary = merge_character_context(promoted, {}, [], corrected, chapter=12)

    assert promoted["address_rules"][0]["until"] == 9
    assert len(promoted["address_rules"]) == 2
    assert after_temporary["address_rules"] == promoted["address_rules"]
    assert ADDRESS_RULE_CANDIDATES_KEY not in after_temporary


def test_temporary_observations_across_chapters_never_become_stable():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    joke = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "vợ",
            "other": "chồng",
            "scope": "temporary",
            "reason": "joke",
        }
    ]

    result: dict = {}
    for chapter in (10, 11, 12):
        result = merge_character_context(result, entities, [], joke, chapter=chapter)

    assert result["address_rules"] == []
    assert ADDRESS_RULE_CANDIDATES_KEY not in result


def test_phase_change_requires_three_default_observations():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    data = {
        "entities": entities,
        "address_rules": [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1}],
    }
    changed = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "default",
        }
    ]

    first = merge_character_context(data, {}, [], changed, chapter=10)
    second = merge_character_context(first, {}, [], changed, chapter=11)
    third = merge_character_context(second, {}, [], changed, chapter=12)

    assert second["address_rules"] == data["address_rules"]
    assert second[ADDRESS_RULE_CANDIDATES_KEY][0]["observations"] == 2
    assert third["address_rules"] == [
        {"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1, "until": 9},
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "since": 10,
            "scope": "stable",
            "reason": "default",
        },
    ]
    assert ADDRESS_RULE_CANDIDATES_KEY not in third


def test_explicit_relationship_change_requires_two_observations():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    data = {
        "entities": entities,
        "address_rules": [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1}],
    }
    changed = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "scope": "stable",
            "reason": "relationship_change",
        }
    ]

    first = merge_character_context(data, {}, [], changed, chapter=10)
    confirmed = merge_character_context(first, {}, [], changed, chapter=11)

    assert confirmed["address_rules"][-1] == {
        "speaker": "李明",
        "listener": "张伟",
        "self": "anh",
        "other": "em",
        "since": 10,
        "scope": "stable",
        "reason": "relationship_change",
    }
    assert ADDRESS_RULE_CANDIDATES_KEY not in confirmed


def test_merge_character_context_does_not_relearn_active_address_rule():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        "address_rules": [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu", "since": 1}],
    }

    result = merge_character_context(
        data,
        {},
        [],
        [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cậu"}],
        chapter=20,
    )

    assert result["address_rules"] == data["address_rules"]
    assert ADDRESS_RULE_CANDIDATES_KEY not in result


def test_normalize_address_rules_keeps_common_references_that_prefix_entity_names():
    entities = {
        "陆远秋": {"translated_name": "Lục Viễn Thu"},
        "白清夏": {"translated_name": "Bạch Thanh Hạ"},
        "强哥": {"translated_name": "anh Cường"},
        "梁先生": {"translated_name": "ông Lương"},
        "丽姐": {"translated_name": "chị Lệ"},
        "刘老师": {"translated_name": "Cô Lưu"},
        "白颂哲": {"translated_name": "Bác Bạch"},
        "陆城": {"translated_name": "Bác cả"},
    }
    rules = [
        {"speaker": "白清夏", "listener": "陆远秋", "self": "em", "other": "anh", "since": 1},
        {"speaker": "陆远秋", "listener": "梁先生", "self": "cháu", "other": "ông", "since": 2},
        {"speaker": "陆远秋", "listener": "丽姐", "self": "em", "other": "chị", "since": 3},
        {"speaker": "白清夏", "listener": "刘老师", "self": "em", "other": "cô", "since": 4},
        {"speaker": "陆远秋", "listener": "白颂哲", "self": "cháu", "other": "bác Bạch", "since": 5},
        {"speaker": "陆远秋", "listener": "陆城", "self": "con", "other": "bác cả", "since": 6},
    ]

    assert normalize_address_rules(rules, entities) == rules


def test_normalize_glossary_merges_clear_short_full_name_aliases():
    data = {
        "entities": {
            "아테나": {"translated_name": "Athena", "role": "minor", "pronoun": "cô ấy"},
            "아테나 바바라": {
                "translated_name": "Athena Barbara",
                "role": "supporting",
                "pronoun": "cô ấy",
            },
            "금태양": {"translated_name": "Kim Tae Yang", "role": "protagonist"},
        },
        "edges": [["아테나", "금태양", "friend", 1]],
        "address_rules": [
            {"speaker": "아테나", "listener": "금태양", "self": "em", "other": "anh", "since": 1},
        ],
    }

    result = normalize_glossary_data(data)

    assert "아테나" not in result["entities"]
    assert result["entities"]["아테나 바바라"]["aliases"] == ["아테나"]
    assert result["edges"] == [["아테나 바바라", "금태양", "friend", 1]]
    assert result["address_rules"][0]["speaker"] == "아테나 바바라"


def test_normalize_glossary_merges_cjk_short_full_name_aliases():
    data = {
        "entities": {
            "若安": {"translated_name": "Nhược An", "role": "minor", "pronoun": "anh"},
            "白若安": {"translated_name": "Bạch Nhược An", "role": "supporting", "pronoun": ""},
            "陆": {"translated_name": "Lục", "role": "minor", "pronoun": "anh"},
            "陆远秋": {"translated_name": "Lục Viễn Thu", "role": "protagonist", "pronoun": "cậu"},
        },
        "edges": [["若安", "陆远秋", "friend", 1]],
    }

    result = normalize_glossary_data(data)

    assert "若安" not in result["entities"]
    assert result["entities"]["白若安"]["aliases"] == ["若安"]
    assert "陆" in result["entities"]
    assert result["edges"] == [["白若安", "陆远秋", "friend", 1]]


def test_normalize_glossary_does_not_merge_cjk_prefix_names():
    data = {
        "entities": {
            "小李": {"translated_name": "Tiểu Lý", "role": "supporting", "pronoun": "anh"},
            "小李飞镖": {"translated_name": "Tiểu Lý Phi Tiêu", "role": "supporting", "pronoun": "anh"},
        },
    }

    result = normalize_glossary_data(data)

    assert set(result["entities"]) == {"小李", "小李飞镖"}
    assert "aliases" not in result["entities"]["小李飞镖"]


def test_normalize_glossary_merges_same_rendered_title_aliases():
    data = {
        "entities": {
            "张姨": {"translated_name": "dì Trương", "role": "minor", "pronoun": "bà"},
            "张阿姨": {"translated_name": "dì Trương", "role": "minor", "pronoun": "bà"},
            "刘妈": {"translated_name": "dì Lưu", "role": "minor", "pronoun": "bà"},
            "刘阿姨": {"translated_name": "dì Lưu", "role": "minor", "pronoun": "bà"},
        },
        "address_rules": [
            {"speaker": "张姨", "listener": "刘妈", "self": "dì", "other": "em", "since": 1},
        ],
    }

    result = normalize_glossary_data(data)

    assert "张姨" not in result["entities"]
    assert result["entities"]["张阿姨"]["aliases"] == ["张姨"]
    assert "刘妈" not in result["entities"]
    assert result["entities"]["刘阿姨"]["aliases"] == ["刘妈"]
    assert result["address_rules"][0]["speaker"] == "张阿姨"
    assert result["address_rules"][0]["listener"] == "刘阿姨"


def test_character_alias_activates_canonical_entity():
    entities = {
        "아테나 바바라": {
            "translated_name": "Athena Barbara",
            "aliases": ["아테나"],
        },
        "금태양": {"translated_name": "Kim Tae Yang"},
    }
    edges = [["아테나 바바라", "금태양", "friend", 1]]

    active_entities, _ = select_active_character_context(entities, edges, "아테나가 웃었다.")

    assert set(active_entities) == {"아테나 바바라"}


def test_active_character_context_excludes_non_appearing_neighbors():
    entities = {
        "陆远秋": {"translated_name": "Lục Viễn Thu"},
        "白清夏": {"translated_name": "Bạch Thanh Hạ"},
        "梁先生": {"translated_name": "ông Lương"},
    }
    edges = [
        ["陆远秋", "白清夏", "friend", 1],
        ["陆远秋", "梁先生", "teacher", 1],
    ]

    active_entities, active_edges = select_active_character_context(
        entities,
        edges,
        "陆远秋 nhìn 白清夏.",
    )

    assert set(active_entities) == {"陆远秋", "白清夏"}
    assert active_edges == [["陆远秋", "白清夏", "friend", 1]]


def test_upsert_relationship_updates_reverse_pair():
    data = {"edges": [["李明", "张伟", "friend", 1]]}

    result = upsert_relationship(data, "张伟", "李明", "rival", since_chapter=5)

    assert result["edges"] == [["张伟", "李明", "rival", 5]]


def test_upsert_relationship_preserves_since_when_not_supplied():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        "edges": [["李明", "张伟", "friend", 1]],
    }

    result = upsert_relationship(data, "李明", "张伟", "rival")

    assert result["edges"] == [["李明", "张伟", "rival", 1]]


def test_upsert_relationship_removes_since_when_explicitly_null():
    data = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        "edges": [["李明", "张伟", "friend", 1]],
    }

    result = upsert_relationship(data, "李明", "张伟", "rival", since_chapter=None, update_since=True)

    assert result["edges"] == [["李明", "张伟", "rival"]]


def test_format_relationships_shorthand():
    entities = {
        "李明": {"translated_name": "Lý Minh", "role": "protagonist", "pronoun": "cậu"},
        "张伟": {"translated_name": "Trương Vĩ", "role": "supporting"},
    }
    edges = [["李明", "张伟", "friend", 1]]

    result = format_relationships_shorthand(entities, edges)

    assert (
        result
        == """=== CHARACTERS ===
- 李明 => Lý Minh [protagonist, pronoun="cậu"]
- 张伟 => Trương Vĩ [supporting]
Relations: 李明(friend)->张伟
=== END CHARACTERS ==="""
    )


def test_format_relationships_shorthand_keeps_pronoun_with_character_without_role():
    entities = {"李明": {"translated_name": "Lý Minh", "pronoun": "cậu"}}

    result = format_relationships_shorthand(entities, [])

    assert '- 李明 => Lý Minh [pronoun="cậu"]' in result
    assert "Names:" not in result
    assert "Roles:" not in result


def test_format_address_rules():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "tôi",
            "other": "cậu",
            "since": 2,
            "notes": "formal in public",
        }
    ]

    result = format_address_rules(entities, rules, target_language="vi")

    assert "=== ADDRESS RULES ===" in result
    assert '李明 -> 张伟: self="tôi", other="cậu"' in result
    assert "xưng hô;" not in result
    assert "Lý Minh -> Trương Vĩ" not in result
    assert "formal in public" not in result
    assert "notes=" not in result
    assert "since chapter" not in result


def test_format_address_rule_candidates_keeps_hypotheses_separate():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cô", "since": 1}]
    candidates = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "first_seen": 10,
            "last_seen": 10,
            "observations": 1,
            "scope": "stable",
            "reason": "relationship_change",
        }
    ]

    result = format_address_rule_candidates(entities, candidates, rules)

    assert "=== UNCONFIRMED ADDRESS HYPOTHESES ===" in result
    assert "provisional continuity hints, not confirmed rules" in result
    assert '李明 -> 张伟: self="anh", other="em"' in result
    assert 'observations=1/2, reason="relationship_change", first_seen=10' in result
    assert "tôi" not in result


def test_validate_glossary_data_pronoun_examples():
    data = {
        "pronoun_examples": {
            "李明": ["Cậu bước vào phòng.", "Cậu mỉm cười."],
        },
    }
    issues = validate_glossary_data(data)
    assert issues == []


def test_validate_glossary_data_bad_pronoun_examples():
    issues = validate_glossary_data(
        {
            "pronoun_examples": {"": ["valid"]},
        }
    )
    assert "pronoun_examples contains an empty or non-string character name" in issues

    issues = validate_glossary_data(
        {
            "pronoun_examples": {"李明": "not a list"},
        }
    )
    assert "pronoun_examples['李明'] must be a list" in issues


def test_replace_glossary_values_handles_substring_collisions_and_cascading():
    replacements = [
        {"kind": "term", "old": "ma thuật đen", "new": "hắc ma pháp"},
        {"kind": "term", "old": "ma thuật", "new": "ma pháp"},
        {"kind": "term", "old": "A", "new": "B"},
        {"kind": "term", "old": "B", "new": "C"},
    ]

    text = "Ma thuật đen và ma thuật. Cả A và B đều tốt."
    updated, counts = replace_glossary_values(text, replacements)

    # ma thuật đen -> hắc ma pháp (starts sentence, capitalized) -> Hắc ma pháp
    # ma thuật -> ma pháp (not start of sentence) -> ma pháp
    # A -> B (start of sentence, capitalized) -> B
    # B -> C (not start of sentence) -> C
    assert updated == "Hắc ma pháp và ma pháp. Cả B và C đều tốt."
    assert counts == {"ma thuật đen": 1, "ma thuật": 1, "A": 1, "B": 1}


def test_replace_glossary_values_character_retains_glossary_casing():
    replacements = [
        {"kind": "character", "old": "Lý Bạch", "new": "lý thái bạch"},
        {"kind": "term", "old": "ma thuật", "new": "ma pháp"},
    ]

    text = "Lý Bạch nói ma thuật. ma thuật là của Lý Bạch."
    updated, counts = replace_glossary_values(text, replacements)

    # Lý Bạch -> lý thái bạch (retains lowercase from glossary, even at start of sentence)
    # ma thuật -> ma pháp (capitalized at sentence start: Ma pháp)
    assert updated == "lý thái bạch nói ma pháp. Ma pháp là của lý thái bạch."
    assert counts == {"Lý Bạch": 2, "ma thuật": 2}


def test_replace_glossary_values_rejects_capitalization_collisions():
    replacements = [
        {"kind": "term", "old": "ma thuật", "new": "ma pháp"},
        {"kind": "term", "old": "Ma thuật", "new": "huyền thuật"},
    ]

    conflicts = find_glossary_replacement_conflicts(replacements)
    assert conflicts == {0: ["huyền thuật", "ma pháp"], 1: ["huyền thuật", "ma pháp"]}
    with pytest.raises(ValueError, match="Conflicting glossary replacement"):
        replace_glossary_values("Ma thuật.", replacements)
