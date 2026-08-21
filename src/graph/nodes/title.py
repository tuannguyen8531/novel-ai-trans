"""Extract and classify a source chapter heading before chunk translation."""

from src.models.state import TranslationState
from src.services.chapters import split_leading_chapter_heading, title_key


def title_node(state: TranslationState) -> dict:
    """Remove the leading numbered heading and expose its structured metadata."""
    resolved, body = split_leading_chapter_heading(
        state["source_text"],
        state["chapter_number"],
        state.get("title_catalog", {}),
    )
    if resolved is None:
        return {}

    return {
        "source_text": body,
        "source_heading_present": True,
        "source_title": resolved.parsed.title,
        "source_title_base": resolved.base,
        "source_title_key": title_key(resolved.base),
        "source_title_part": resolved.part,
        "source_title_series": resolved.is_series,
    }
