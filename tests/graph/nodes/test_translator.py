from unittest.mock import MagicMock, patch

from src.graph.nodes.translator import translator_node
from src.models.state import initial_state


def test_translator_uses_previous_source_overlap_as_context_only():
    state = initial_state("前文需要上下文。\n\n当前文本需要翻译。", "chinese", "novel", 1)
    state["chunks"] = ["前文需要上下文。", "当前文本需要翻译。"]
    state["current_chunk_index"] = 1

    llm = MagicMock()
    llm.generate.return_value = "Bản dịch hiện tại."

    with (
        patch("src.graph.nodes.translator.config") as config,
        patch("src.graph.nodes.translator.get_llm", return_value=llm),
        patch("src.graph.nodes.translator.log_ai_call"),
    ):
        config.chunk_overlap = 5
        config.chunk_mode = "chars"

        result = translator_node(state)

    _, user_prompt, call_type = llm.generate.call_args.args
    assert call_type == "translate"
    assert "PRECEDING SOURCE CONTEXT — DO NOT TRANSLATE" in user_prompt
    assert "要上下文。" in user_prompt
    assert user_prompt.count("当前文本需要翻译。") == 1
    assert result["current_translation"] == "Bản dịch hiện tại."


def test_translator_does_not_add_context_to_first_chunk():
    state = initial_state("当前文本需要翻译。", "chinese", "novel", 1)
    state["chunks"] = ["当前文本需要翻译。"]

    llm = MagicMock()
    llm.generate.return_value = "Bản dịch."

    with (
        patch("src.graph.nodes.translator.config") as config,
        patch("src.graph.nodes.translator.get_llm", return_value=llm),
        patch("src.graph.nodes.translator.log_ai_call"),
    ):
        config.chunk_overlap = 5
        config.chunk_mode = "chars"

        translator_node(state)

    _, user_prompt, _ = llm.generate.call_args.args
    assert "PRECEDING SOURCE CONTEXT" not in user_prompt
    assert user_prompt.count("当前文本需要翻译。") == 1


def test_translator_receives_uncertain_candidate_separately_from_confirmed_rule():
    state = initial_state("李明看着张伟。", "chinese", "novel", 11)
    state["chunks"] = ["李明看着张伟。"]
    state["characters"] = {
        "entities": {
            "李明": {"translated_name": "Lý Minh"},
            "张伟": {"translated_name": "Trương Vĩ"},
        },
        "edges": [],
        "address_rules": [
            {
                "speaker": "李明",
                "listener": "张伟",
                "self": "tôi",
                "other": "cậu",
                "since": 1,
            }
        ],
        "address_rule_candidates": [
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
        ],
    }

    llm = MagicMock()
    llm.generate.return_value = "Lý Minh nhìn Trương Vĩ."

    with (
        patch("src.graph.nodes.translator.config") as config,
        patch("src.graph.nodes.translator.get_llm", return_value=llm),
        patch("src.graph.nodes.translator.log_ai_call"),
    ):
        config.chunk_overlap = 0
        config.chunk_mode = "chars"

        translator_node(state)

    system_prompt, _, _ = llm.generate.call_args.args
    assert '李明 -> 张伟: self="tôi", other="cậu"' in system_prompt
    assert "=== UNCONFIRMED ADDRESS HYPOTHESES ===" in system_prompt
    assert '李明 -> 张伟: self="anh", other="em"' in system_prompt
    assert 'observations=1/2, reason="relationship_change"' in system_prompt
