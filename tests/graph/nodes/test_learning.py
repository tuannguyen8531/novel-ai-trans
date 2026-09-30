import json
from unittest.mock import MagicMock, patch

import pytest

from src.graph.nodes.learner import learner_node
from src.models.state import initial_state


@pytest.mark.parametrize(
    "broken",
    [
        '{"terms":{"前端":"front-end"},"characters":{"entities":{},"edges":[]}',
        '{"前端":"front-end"}',
        '{"terms":{},"characters":{"entities":{},"edges":[[1,2,3]]}}',
    ],
)
def test_invalid_learning_response_retries_once_and_keeps_valid_result(broken):
    state = initial_state("他们测试前端。", "chinese", "novel", 494)
    state.update({"chunks": [state["source_text"]], "translated_chunks": ["Họ kiểm tra front-end."]})
    valid = {"terms": {"前端": "front-end"}, "characters": {"entities": {}, "edges": []}}
    llm = MagicMock()
    llm.generate.side_effect = [broken, json.dumps(valid)]
    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_glossary") as save,
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_error") as errors,
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)
    assert llm.generate.call_count == 2
    assert all(call.args[2] == "learn" for call in llm.generate.call_args_list)
    assert result["new_terms"] == valid["terms"]
    save.assert_called_once_with("novel", valid["terms"])
    errors.assert_called_once()


def test_repeated_invalid_learning_response_preserves_existing_memory():
    state = initial_state("正文。", "chinese", "novel", 494)
    state.update({"chunks": [state["source_text"]], "translated_chunks": ["Nội dung."]})
    llm = MagicMock()
    llm.generate.return_value = '{"terms":{"坏数据":"bad data"}'
    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_glossary") as save_terms,
        patch("src.graph.nodes.learner.save_characters_batch") as save_characters,
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_error") as errors,
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)
    assert llm.generate.call_count == 2
    assert result["new_terms"] == {}
    assert result["final_translation"] == "Nội dung."
    save_terms.assert_not_called()
    save_characters.assert_not_called()
    assert errors.call_count == 2
