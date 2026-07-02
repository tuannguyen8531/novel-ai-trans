"""
Reviewer Node — Evaluate translation quality and decide whether to retry.

Scoring criteria:
- Completeness: all content from source is present
- Naturalness: reads naturally in the target language
- Consistency: follows glossary terms
- Accuracy: meaning preserved correctly
"""

import json

from src.config import config
from src.domain.target_language import target_language_name
from src.models.state import TranslationState
from src.prompts import render_prompt
from src.services.llm import get_llm
from src.services.logger import log_ai_call
from src.utils.json import parse_json_object


def reviewer_node(state: TranslationState) -> dict:
    """Review the current translation and score it."""
    chunk_index = state["current_chunk_index"]
    chunk = state["chunks"][chunk_index]
    translation = state["current_translation"]
    total_chunks = len(state["chunks"])
    target_language = state.get("target_language", "vi")
    target_name = target_language_name(target_language)

    system_prompt = render_prompt("reviewer", target_language=target_language, target_name=target_name)

    user_prompt = f"""=== SOURCE TEXT ===
{chunk}

=== TRANSLATION ===
{translation}"""

    response = get_llm().generate(system_prompt, user_prompt, "review")

    try:
        review_data = parse_json_object(response)
        score = float(review_data.get("score", 0.8))
        feedback = review_data.get("feedback", "")
    except (json.JSONDecodeError, ValueError) as e:
        score = config.review_threshold - 0.1
        feedback = f"Review JSON parse failed — forcing retry. Raw: {response[:200]}"
        log_ai_call(
            "review_parse_error",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=response,
            error=str(e),
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        )

    post_feedback = state.get("review_feedback", "")
    if post_feedback:
        feedback = f"{feedback}\n{post_feedback}" if feedback else post_feedback
    if state.get("post_check_blocking", False):
        score = min(score, config.review_threshold - 0.1)

    log_ai_call(
        "review",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=response,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        score=score,
        feedback=feedback,
        post_check_issues=state.get("post_check_issues", []),
    )

    return {
        "review_score": score,
        "review_feedback": feedback,
    }
