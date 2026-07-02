"""Token-free deterministic checks for each translated chunk."""

from src.domain.quality import has_blocking_issues, post_check_translation
from src.models.state import TranslationState


def quality_node(state: TranslationState) -> dict:
    """Validate the current translation without making another LLM call."""
    chunk = state["chunks"][state["current_chunk_index"]]
    issues = post_check_translation(chunk, state["current_translation"], state.get("glossary", {}))
    feedback = ""
    if issues:
        feedback = "Post-check issues: " + "; ".join(issue.message for issue in issues)

    return {
        "post_check_issues": [issue.code for issue in issues],
        "post_check_blocking": has_blocking_issues(issues),
        "review_feedback": feedback,
    }
