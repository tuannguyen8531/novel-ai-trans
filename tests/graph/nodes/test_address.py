import json
from unittest.mock import MagicMock, patch

import pytest

from src.domain.candidates import merge_address_rule_candidates
from src.graph.nodes.address import analyze_address
from src.graph.nodes.learner import _prepare_address_rule_candidate_verdicts, learner_node
from src.models.state import initial_state
from src.services.llm.cancellation import GenerationCancelledError

ENTITIES = {"李明": {"translated_name": "Lý Minh"}, "王芳": {"translated_name": "Vương Phương"}}
PAIR = {"speaker": "李明", "listener": "王芳"}


def response(verdict="inconclusive", rules=None):
    return json.dumps(
        {
            "address_rules": rules or [],
            "address_rule_candidate_verdicts": [{**PAIR, "verdict": verdict}],
        }
    )


@pytest.fixture
def llm():
    model = MagicMock()
    with (
        patch("src.graph.nodes.address.get_llm", return_value=model),
        patch("src.graph.nodes.address.log_ai_call"),
        patch("src.graph.nodes.address.log_error"),
    ):
        yield model


@pytest.mark.parametrize("verdict", ["confirmed", "temporary", "rejected", "inconclusive"])
def test_address_preserves_source_verdict_and_temporary_evidence(llm, verdict):
    rule = {**PAIR, "self": "tớ", "other": "cậu", "scope": "temporary", "reason": "joke", "since": 99}
    llm.generate.return_value = response(verdict, [rule])
    state = initial_state("李明笑着对王芳说话。", "chinese", "novel", 12)
    result = analyze_address(state, "character memory", ENTITIES)
    assert result["address_rules"] == [{**rule, "since": 12}]
    expected = [] if verdict == "inconclusive" else [{**PAIR, "verdict": verdict}]
    assert result["address_rule_candidate_verdicts"] == expected
    assert llm.generate.call_args.args[2] == "address"
    assert state["source_text"] in llm.generate.call_args.args[1]


def test_address_reads_every_source_part_and_retains_late_evidence(llm):
    paragraphs = [f"第{i}段，李明在这里。" for i in range(12)]
    state = initial_state("\n\n".join(paragraphs), "chinese", "novel", 12)

    def generate(system, user, call_type):
        return response("confirmed" if paragraphs[-1] in user else "inconclusive")

    llm.generate.side_effect = generate
    result = analyze_address(state, "character memory", ENTITIES, chunk_size=40, chunk_overlap=5)
    prompts = [call.args[1] for call in llm.generate.call_args_list]
    assert len(prompts) > 1
    assert all(any(paragraph in prompt for prompt in prompts) for paragraph in paragraphs)
    assert result["address_rule_candidate_verdicts"] == [{**PAIR, "verdict": "confirmed"}]


def test_conflicting_parts_do_not_confirm_candidate(llm):
    rule = {**PAIR, "self": "tớ", "other": "cậu", "scope": "stable", "reason": "default"}
    llm.generate.side_effect = [response("confirmed", [rule]), response("temporary")]
    state = initial_state("李明在这里。\n\n王芳在这里。", "chinese", "novel", 12)
    result = analyze_address(state, "character memory", ENTITIES, chunk_size=8, chunk_overlap=0)
    assert result["address_rule_candidate_verdicts"] == [{**PAIR, "verdict": "inconclusive"}]
    assert result["address_rules"] == []


@pytest.mark.parametrize("reverse_parts", [False, True])
@pytest.mark.parametrize(
    "metadata",
    [{"scope": "temporary"}, {"scope": "stable", "reason": "joke"}, {"scope": " TEMPORARY ", "reason": " JOKE "}],
)
def test_conflicting_parts_preserve_temporary_evidence_to_cancel_candidate(llm, reverse_parts, metadata):
    rule = {**PAIR, "self": "tớ", "other": "cậu", "scope": "stable", "reason": "default"}
    temporary = {**rule, **metadata}
    pending = {**rule, "first_seen": 11, "last_seen": 11, "observations": 1}
    stable = {**PAIR, "self": "tôi", "other": "bạn", "since": 1}
    parts = [response("confirmed", [rule]), response("temporary", [temporary])]
    llm.generate.side_effect = parts[::-1] if reverse_parts else parts
    state = initial_state("李明在这里。\n\n王芳在这里。", "chinese", "novel", 12)

    result = analyze_address(state, "character memory", ENTITIES, chunk_size=8, chunk_overlap=0)

    assert result["address_rule_candidate_verdicts"] == [{**PAIR, "verdict": "inconclusive"}]
    assert result["address_rules"] == [{**temporary, "since": 12}]
    rules, candidates = merge_address_rule_candidates(
        [stable], [pending], result["address_rules"], result["address_rule_candidate_verdicts"], ENTITIES, 12
    )
    assert candidates == []
    assert rules == [stable]


@pytest.mark.parametrize("failure", [RuntimeError("offline"), "not json", '{"address_rules":{}}'])
def test_failed_part_discards_all_address_updates(llm, failure):
    llm.generate.side_effect = [response("confirmed"), failure]
    state = initial_state("李明在这里。\n\n王芳在这里。", "chinese", "novel", 12)
    assert analyze_address(state, "character memory", ENTITIES, chunk_size=8, chunk_overlap=0) == {}


def test_address_cancellation_propagates(llm):
    llm.generate.side_effect = GenerationCancelledError("cancelled")
    state = initial_state("李明在这里。", "chinese", "novel", 12)
    with pytest.raises(GenerationCancelledError):
        analyze_address(state, "character memory", ENTITIES)


@pytest.mark.parametrize("address_fails", [False, True])
def test_learner_uses_new_characters_and_preserves_learning_on_address_failure(llm, address_fails):
    state = initial_state("李明和王芳加入玄天宗。", "chinese", "novel", 12)
    state.update(
        {
            "source_heading_present": True,
            "source_title": "重逢",
            "characters": {
                "entities": {"李明": {"translated_name": "Lý Minh", "pronoun": "hắn"}},
                "edges": [["李明", "王芳", "enemy"]],
            },
            "chunks": [state["source_text"]],
            "translated_chunks": ["Lý Minh và Vương Phương gia nhập Huyền Thiên Tông."],
        }
    )
    learned = {
        "translated_title_base": "Gặp lại",
        "terms": {"玄天宗": "Huyền Thiên Tông"},
        "characters": {
            "entities": ENTITIES,
            "edges": [["李明", "王芳", "friend"]],
            "address_rules": [{**PAIR, "self": "WRONG CALL"}],
        },
    }
    rule = {**PAIR, "self": "tớ", "other": "cậu", "scope": "stable", "reason": "default"}
    llm.generate.side_effect = [json.dumps(learned), RuntimeError("offline") if address_fails else response(rules=[rule])]
    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_characters_batch") as save_characters,
        patch("src.graph.nodes.learner.save_glossary") as save_terms,
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.address.split_into_chunks", return_value=[state["source_text"]]) as split_source,
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state, address_chunk_size=731, address_chunk_overlap=29, address_chunk_mode="tokens")
    split_source.assert_called_once_with(state["source_text"], chunk_size=731, overlap=29, mode="tokens")
    assert [call.args[2] for call in llm.generate.call_args_list] == ["learn", "address"]
    assert "Lý Minh" in llm.generate.call_args_list[1].args[0]
    assert "friend" in llm.generate.call_args_list[1].args[0]
    assert "enemy" not in llm.generate.call_args_list[1].args[0]
    assert 'pronoun="hắn"' in llm.generate.call_args_list[1].args[0]
    assert result["final_translation"].startswith("Chương 12: Gặp lại")
    assert result["new_terms"] == learned["terms"]
    save_terms.assert_called_once_with("novel", learned["terms"])
    save_characters.assert_called_once()
    assert save_characters.call_args.args[1] == ENTITIES
    assert save_characters.call_args.kwargs["address_rules"] == ([] if address_fails else [{**rule, "since": 12}])
    assert save_characters.call_args.kwargs["address_rule_candidate_verdicts"] == []


def test_repeated_parts_count_as_one_chapter_observation(llm):
    rule = {**PAIR, "self": "tớ", "other": "cậu", "scope": "stable", "reason": "default"}
    llm.generate.return_value = response(rules=[rule])
    state = initial_state("李明在这里。\n\n王芳在这里。", "chinese", "novel", 12)
    result = analyze_address(state, "character memory", ENTITIES, chunk_size=8, chunk_overlap=0)
    assert llm.generate.call_count == 2
    rules, candidates = merge_address_rule_candidates(
        [],
        [],
        result["address_rules"],
        result["address_rule_candidate_verdicts"],
        ENTITIES,
        12,
    )
    assert rules == []
    assert len(candidates) == 1
    assert candidates[0]["observations"] == 1


@pytest.mark.parametrize("verdict", ["inconclusive", "temporary", "confirmed"])
def test_pending_candidate_lifecycle_uses_one_chapter_verdict(llm, verdict):
    pending = {
        **PAIR,
        "self": "tớ",
        "other": "cậu",
        "scope": "stable",
        "reason": "default",
        "first_seen": 11,
        "last_seen": 11,
        "observations": 1,
    }
    llm.generate.return_value = response(verdict)
    state = initial_state("李明在这里。", "chinese", "novel", 12)
    result = analyze_address(state, "character memory", ENTITIES)
    verdicts = _prepare_address_rule_candidate_verdicts(
        result["address_rule_candidate_verdicts"],
        [pending],
        ENTITIES,
    )
    rules, candidates = merge_address_rule_candidates([], [pending], [], verdicts, ENTITIES, 12)
    if verdict == "inconclusive":
        assert rules == []
        assert candidates[0]["observations"] == 1
        assert candidates[0]["evaluations"] == [{"chapter": 12, "verdict": "inconclusive"}]
    elif verdict == "temporary":
        assert rules == []
        assert candidates == []
    else:
        assert len(rules) == 1
        assert rules[0]["self"] == "tớ"
        assert candidates == []
