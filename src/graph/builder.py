"""
Graph Builder — Assembles the LangGraph translation pipeline.

Flow (with review):
    START → detect → context → chunk → translate → quality → review
    quality →|blocking issue| retry or fail
    review →|score OK or max retries| accept_chunk
    review →|score low| retry → translate
    accept_chunk →|more chunks| translate
    accept_chunk →|done| learn → END

Flow (skip review):
    START → detect → context → chunk → translate → quality
    quality →|clean| accept_chunk
    quality →|blocking issue| retry or fail
    accept_chunk →|more chunks| translate
    accept_chunk →|done| learn → END
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.config import config
from src.graph.nodes.chunker import chunker_node
from src.graph.nodes.context import context_node
from src.graph.nodes.detector import detector_node
from src.graph.nodes.learner import learner_node
from src.graph.nodes.quality import quality_node
from src.graph.nodes.reviewer import reviewer_node
from src.graph.nodes.translator import translator_node
from src.models.state import TranslationState


class TranslationQualityError(RuntimeError):
    """Raised when deterministic quality checks still fail after retries."""


def _after_review(state: TranslationState) -> str:
    """
    Decide what to do after reviewing a translation.

    Returns:
        "retry" — re-translate current chunk (score too low)
        "next"  — accept and move to next chunk or learn phase
    """
    score = state["review_score"]
    retry_count = state["retry_count"]

    if score < config.review_threshold and retry_count < config.max_retries:
        return "retry"
    return "next"


def _after_quality(state: TranslationState) -> str:
    """Retry blocking deterministic failures, then reject instead of saving them."""
    if not state.get("post_check_blocking", False):
        return "next"
    if state["retry_count"] < config.max_retries:
        return "retry"
    return "fail"


def _reject_chunk(state: TranslationState) -> dict:
    issue_codes = ", ".join(state.get("post_check_issues", [])) or "unknown_quality_failure"
    feedback = state.get("review_feedback", "").strip() or "The translated chunk failed deterministic quality checks."
    raise TranslationQualityError(f"Deterministic quality checks failed after retries: {feedback} [{issue_codes}]")


def _accept_chunk(state: TranslationState) -> dict:
    """Accept the current translation and move to next chunk."""
    translated_chunks = list(state["translated_chunks"])
    translated_chunks.append(state["current_translation"])

    quality_reports = list(state.get("quality_reports", []))
    quality_reports.append(
        {
            "chunk_index": state["current_chunk_index"],
            "score": state.get("review_score", 0.0),
            "feedback": state.get("review_feedback", ""),
            "post_check_issues": state.get("post_check_issues", []),
            "retry_count": state.get("retry_count", 0),
        }
    )

    next_index = state["current_chunk_index"] + 1

    return {
        "translated_chunks": translated_chunks,
        "current_chunk_index": next_index,
        "retry_count": 0,
        "review_feedback": "",
        "post_check_issues": [],
        "post_check_blocking": False,
        "quality_reports": quality_reports,
    }


def _increment_retry(state: TranslationState) -> dict:
    """Increment retry counter before re-translation."""
    return {"retry_count": state["retry_count"] + 1}


def _has_more_chunks(state: TranslationState) -> str:
    """Check if there are more chunks to translate."""
    current_index = state["current_chunk_index"]
    total_chunks = len(state["chunks"])

    if current_index < total_chunks:
        return "translate"
    return "learn"


def build_graph() -> CompiledStateGraph[
    TranslationState,
    None,
    TranslationState,
    TranslationState,
]:
    """
    Build and compile the translation pipeline graph.

    If config.enable_review is False, the review node is skipped entirely.
    """
    graph = StateGraph(TranslationState)
    enable_review = config.enable_review

    # Add nodes
    graph.add_node("detect", detector_node)
    graph.add_node("context", context_node)
    graph.add_node("chunk", chunker_node)
    graph.add_node("translate", translator_node)
    graph.add_node("quality", quality_node)
    graph.add_node("accept_chunk", _accept_chunk)
    graph.add_node("increment_retry", _increment_retry)
    graph.add_node("reject_chunk", _reject_chunk)
    graph.add_node("learn", learner_node)

    # Wire edges: linear start
    graph.add_edge(START, "detect")
    graph.add_edge("detect", "context")
    graph.add_edge("context", "chunk")
    graph.add_edge("chunk", "translate")
    graph.add_edge("translate", "quality")

    quality_next = "review" if enable_review else "accept_chunk"
    graph.add_conditional_edges(
        "quality",
        _after_quality,
        {"retry": "increment_retry", "fail": "reject_chunk", "next": quality_next},
    )
    graph.add_edge("increment_retry", "translate")

    if enable_review:
        # With review: mechanically clean translations receive the optional LLM review.
        graph.add_node("review", reviewer_node)

        graph.add_conditional_edges(
            "review",
            _after_review,
            {"retry": "increment_retry", "next": "accept_chunk"},
        )

    # After accepting: more chunks or learn
    graph.add_conditional_edges(
        "accept_chunk",
        _has_more_chunks,
        {"translate": "translate", "learn": "learn"},
    )

    # Learn → END
    graph.add_edge("learn", END)

    return graph.compile()
