"""Cross-chapter summary persistence backed by the novel glossary document."""

from src.services.glossary import load_glossary_data, update_glossary_data


def _format_recent_summaries(summaries: dict, current_chapter: int, max_count: int = 3) -> str:
    parts = []
    for chapter in range(current_chapter - 1, max(0, current_chapter - 1 - max_count), -1):
        summary = summaries.get(str(chapter), "")
        if summary:
            parts.append(f"Chapter {chapter}: {summary}")
    parts.reverse()
    return "\n\n".join(parts)


def load_chapter_summary(novel_name: str, chapter_number: int) -> str:
    """Load a chapter summary, returning an empty string when absent."""
    summaries = load_glossary_data(novel_name).get("chapter_summaries", {})
    return summaries.get(str(chapter_number), "")


def load_recent_chapter_summaries(
    novel_name: str,
    current_chapter: int,
    max_count: int = 3,
) -> str:
    """Format the most recent summaries before the current chapter."""
    summaries = load_glossary_data(novel_name).get("chapter_summaries", {})
    return _format_recent_summaries(summaries, current_chapter, max_count=max_count)


def save_chapter_summary(novel_name: str, chapter_number: int, summary: str) -> None:
    """Persist a chapter summary atomically."""
    update_glossary_data(
        novel_name,
        lambda data: {
            **data,
            "chapter_summaries": {**data.get("chapter_summaries", {}), str(chapter_number): summary},
        },
    )
