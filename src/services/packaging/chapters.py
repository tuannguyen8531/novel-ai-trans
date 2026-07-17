"""Translated chapter parsing for EPUB packaging."""

from __future__ import annotations

from pathlib import Path

from src.services.chapters import is_translated_chapter_heading
from src.services.packaging.cleaning import clean_text


def parse_chapter_file(file_path: Path) -> tuple[str, list[str]]:
    """Extract a cleaned title and paragraphs from a translated chapter."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - unreadable chapters retain the legacy fallback
        return f"Chương {file_path.stem}", []

    lines = [line.strip() for line in content.split("\n")]
    lines = [stripped for stripped in lines if stripped]
    if not lines:
        return f"Chương {file_path.stem}", []

    header_lines: list[tuple[int, str]] = []
    for index, line in enumerate(lines[:5]):
        if is_translated_chapter_heading(line):
            header_lines.append((index, line))
        else:
            break

    if header_lines:
        title_index, title = header_lines[-1]
        body_start_index = title_index + 1
    else:
        title = lines[0]
        body_start_index = 1

    title = clean_text(title)
    paragraphs = [clean_text(paragraph) for paragraph in lines[body_start_index:]]
    return title, [paragraph for paragraph in paragraphs if paragraph]


__all__ = ["parse_chapter_file"]
