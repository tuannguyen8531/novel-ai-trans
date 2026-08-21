from unittest.mock import MagicMock, patch

from src.graph.nodes.learner import learner_node
from src.models.state import initial_state


def test_learner_finalizes_series_title_and_reuses_canonical_hint() -> None:
    state = initial_state("正文。", "chinese", "novel", 204)
    state.update(
        {
            "source_heading_present": True,
            "source_title": "新年(2)",
            "source_title_base": "新年",
            "source_title_key": "新年",
            "source_title_part": 2,
            "source_title_series": True,
            "title_translation_hint": "Năm mới",
            "chunks": ["正文。"],
            "translated_chunks": ["Nội dung."],
        }
    )
    llm = MagicMock()
    llm.generate.return_value = '{"translated_title_base":"Đầu năm","terms":{},"characters":{"entities":{},"edges":[]}}'

    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_chapter_title"),
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)

    assert result["translated_title_base"] == "Năm mới"
    assert result["final_translation"] == "Chương 204: Năm mới (2)\n\nNội dung."
    assert "SOURCE TITLE BASE: 新年" in llm.generate.call_args.args[1]


def test_learner_does_not_invent_part_one_suffix() -> None:
    state = initial_state("正文。", "chinese", "novel", 203)
    state.update(
        {
            "source_heading_present": True,
            "source_title": "暴雨夜的苏雨晴!",
            "source_title_base": "暴雨夜的苏雨晴!",
            "source_title_key": "暴雨夜的苏雨晴!",
            "source_title_part": None,
            "source_title_series": True,
            "chunks": ["正文。"],
            "translated_chunks": ["Nội dung."],
        }
    )
    llm = MagicMock()
    llm.generate.return_value = '{"translated_title_base":"Tô Vũ Tình trong đêm mưa bão! (1)"}'

    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_chapter_title"),
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)

    assert result["final_translation"] == "Chương 203: Tô Vũ Tình trong đêm mưa bão!\n\nNội dung."


def test_learner_keeps_marker_when_source_heading_has_no_title() -> None:
    state = initial_state("正文。", "chinese", "novel", 7)
    state.update(
        {
            "source_heading_present": True,
            "chunks": ["正文。"],
            "translated_chunks": ["Nội dung."],
        }
    )
    llm = MagicMock()
    llm.generate.return_value = '{"terms":{},"characters":{"entities":{},"edges":[]}}'

    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)

    assert result["final_translation"] == "Chương 7\n\nNội dung."


def test_learner_uses_marker_fallback_when_title_translation_is_missing() -> None:
    state = initial_state("正文。", "chinese", "novel", 7)
    state.update(
        {
            "source_heading_present": True,
            "source_title": "新年",
            "source_title_base": "新年",
            "chunks": ["正文。"],
            "translated_chunks": ["Nội dung."],
        }
    )
    llm = MagicMock()
    llm.generate.return_value = '{"terms":{},"characters":{"entities":{}}}'

    with (
        patch("src.graph.nodes.learner.get_llm", return_value=llm),
        patch("src.graph.nodes.learner.save_source_language"),
        patch("src.graph.nodes.learner.log_ai_call"),
    ):
        result = learner_node(state)

    assert result["final_translation"] == "Chương 7\n\nNội dung."
