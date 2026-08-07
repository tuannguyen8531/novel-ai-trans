"""Tests for graph builder logic."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from src.graph.builder import (
    TranslationQualityError,
    _accept_chunk,
    _after_quality,
    _after_review,
    _has_more_chunks,
    _increment_retry,
    _reject_chunk,
    build_graph,
)
from src.models.state import initial_state


class TestAfterReview:
    def test_score_above_threshold(self):
        with patch("src.graph.builder.config") as mock_config:
            mock_config.review_threshold = 0.7
            mock_config.max_retries = 2

            state = initial_state("text", "chinese", "novel", 1)
            state["review_score"] = 0.9
            state["retry_count"] = 0

            assert _after_review(state) == "next"

    def test_score_below_threshold(self):
        with patch("src.graph.builder.config") as mock_config:
            mock_config.review_threshold = 0.7
            mock_config.max_retries = 2

            state = initial_state("text", "chinese", "novel", 1)
            state["review_score"] = 0.5
            state["retry_count"] = 0

            assert _after_review(state) == "retry"

    def test_max_retries_exceeded(self):
        with patch("src.graph.builder.config") as mock_config:
            mock_config.review_threshold = 0.7
            mock_config.max_retries = 2

            state = initial_state("text", "chinese", "novel", 1)
            state["review_score"] = 0.5
            state["retry_count"] = 2

            assert _after_review(state) == "next"


class TestAcceptChunk:
    def test_accepts_and_increments(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["translated_chunks"] = ["chunk1"]
        state["current_translation"] = "chunk2"
        state["current_chunk_index"] = 1

        result = _accept_chunk(state)

        assert result["translated_chunks"] == ["chunk1", "chunk2"]
        assert result["current_chunk_index"] == 2
        assert result["retry_count"] == 0
        assert result["review_feedback"] == ""
        assert result["post_check_blocking"] is False
        assert result["quality_reports"] == [
            {
                "chunk_index": 1,
                "score": 0.0,
                "feedback": "",
                "post_check_issues": [],
                "retry_count": 0,
            }
        ]

    def test_accepts_quality_report(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["translated_chunks"] = []
        state["current_translation"] = "chunk"
        state["current_chunk_index"] = 0
        state["review_score"] = 0.8
        state["review_feedback"] = "Good"
        state["post_check_issues"] = ["missing_glossary_term"]
        state["retry_count"] = 1

        result = _accept_chunk(state)

        assert result["quality_reports"] == [
            {
                "chunk_index": 0,
                "score": 0.8,
                "feedback": "Good",
                "post_check_issues": ["missing_glossary_term"],
                "retry_count": 1,
            }
        ]


class TestIncrementRetry:
    def test_increments_retry(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["retry_count"] = 1

        result = _increment_retry(state)
        assert result["retry_count"] == 2


class TestAfterQuality:
    def test_clean_translation_advances(self):
        state = initial_state("text", "chinese", "novel", 1)
        assert _after_quality(state) == "next"

    def test_blocking_issue_retries_then_fails(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["post_check_blocking"] = True
        state["post_check_issues"] = ["translation_empty"]
        with patch("src.graph.builder.config") as mock_config:
            mock_config.max_retries = 2
            assert _after_quality(state) == "retry"
            state["retry_count"] = 2
            assert _after_quality(state) == "fail"

        with pytest.raises(TranslationQualityError, match="translation_empty"):
            _reject_chunk(state)

    def test_rejected_error_carries_candidate_and_post_check_context(self):
        state = initial_state("source", "chinese", "novel", 1)
        state["chunks"] = ["source-1", "source-2"]
        state["translated_chunks"] = ["translated-1"]
        state["current_chunk_index"] = 1
        state["current_translation"] = "张三 untranslated"
        state["post_check_issues"] = ["contains_source_language_chars"]
        state["review_feedback"] = "Translate 张三."
        state["retry_count"] = 2

        with pytest.raises(TranslationQualityError) as raised:
            _reject_chunk(state)

        error = raised.value
        assert error.issue_codes == ["contains_source_language_chars"]
        assert error.feedback == "Translate 张三."
        assert error.retry_count == 2
        assert error.failed_chunk_index == 1
        assert error.total_chunks == 2
        assert error.candidate_translation == "translated-1\n\n张三 untranslated"


class TestHasMoreChunks:
    def test_more_chunks(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["chunks"] = ["c1", "c2", "c3"]
        state["current_chunk_index"] = 1

        assert _has_more_chunks(state) == "translate"

    def test_no_more_chunks(self):
        state = initial_state("text", "chinese", "novel", 1)
        state["chunks"] = ["c1", "c2"]
        state["current_chunk_index"] = 2

        assert _has_more_chunks(state) == "learn"


class TestQualityFlow:
    @staticmethod
    def _patch_graph(llm):
        def detect(_state):
            return {"source_language": "chinese"}

        def context(_state):
            return {"translation_rules": "", "glossary": {}, "previous_summary": "", "characters": {}}

        def chunk(_state):
            return {"chunks": ["source"], "current_chunk_index": 0, "translated_chunks": [], "retry_count": 0}

        def learn(state, *, summary=False):
            return {
                "new_terms": {},
                "new_characters": {},
                "chapter_summary": "",
                "final_translation": "\n\n".join(state["translated_chunks"]),
            }

        return (
            patch("src.graph.builder.detector_node", detect),
            patch("src.graph.builder.context_node", context),
            patch("src.graph.builder.chunker_node", chunk),
            patch("src.graph.builder.learner_node", learn),
            patch("src.graph.nodes.translator.get_llm", return_value=llm),
            patch("src.graph.nodes.translator.log_ai_call"),
        )

    def test_retries_blocking_output_without_an_extra_review_call(self):
        llm = MagicMock()
        llm.generate.side_effect = ["", "translated"]

        with ExitStack() as stack:
            graph_config = stack.enter_context(patch("src.graph.builder.config"))
            for context_manager in self._patch_graph(llm):
                stack.enter_context(context_manager)
            graph_config.max_retries = 2
            result = build_graph(review=False).invoke(initial_state("source", "chinese", "novel", 1))

        assert result["final_translation"] == "translated"
        assert result["quality_reports"][0]["retry_count"] == 1
        assert llm.generate.call_count == 2

    def test_rejects_blocking_output_after_retry_limit(self):
        llm = MagicMock()
        llm.generate.return_value = ""

        with ExitStack() as stack:
            graph_config = stack.enter_context(patch("src.graph.builder.config"))
            for context_manager in self._patch_graph(llm):
                stack.enter_context(context_manager)
            graph_config.max_retries = 2
            graph = build_graph(review=False)

            with pytest.raises(TranslationQualityError, match="translation_empty"):
                graph.invoke(initial_state("source", "chinese", "novel", 1))

        assert llm.generate.call_count == 3

    def test_review_runs_after_clean_deterministic_checks(self):
        translator_llm = MagicMock()
        translator_llm.generate.return_value = "translated"
        reviewer = MagicMock(return_value={"review_score": 0.9, "review_feedback": "Good"})

        with ExitStack() as stack:
            graph_config = stack.enter_context(patch("src.graph.builder.config"))
            for context_manager in self._patch_graph(translator_llm):
                stack.enter_context(context_manager)
            stack.enter_context(patch("src.graph.builder.reviewer_node", reviewer))
            graph_config.max_retries = 2
            graph_config.review_threshold = 0.7
            result = build_graph(review=True).invoke(initial_state("source", "chinese", "novel", 1))

        assert result["final_translation"] == "translated"
        reviewer.assert_called_once()

    def test_blocking_deterministic_failure_skips_review(self):
        translator_llm = MagicMock()
        translator_llm.generate.return_value = ""
        reviewer = MagicMock()

        with ExitStack() as stack:
            graph_config = stack.enter_context(patch("src.graph.builder.config"))
            for context_manager in self._patch_graph(translator_llm):
                stack.enter_context(context_manager)
            stack.enter_context(patch("src.graph.builder.reviewer_node", reviewer))
            graph_config.max_retries = 0
            graph = build_graph(review=True)

            with pytest.raises(TranslationQualityError, match="Translation is empty.*translation_empty"):
                graph.invoke(initial_state("source", "chinese", "novel", 1))

        reviewer.assert_not_called()
