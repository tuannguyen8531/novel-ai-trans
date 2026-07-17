"""EPUB chapter and summary classification."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from src.services.chapters import detect_chapter_number, is_obvious_non_chapter_title
from src.services.importing.extractor import EpubSection, normalize_epub_summary, normalize_whitespace

SUMMARY_SECTION_TITLES = frozenset(
    {
        "synopsis",
        "summary",
        "description",
        "blurb",
        "book synopsis",
        "book summary",
        "book description",
        "about the book",
        "简介",
        "内容简介",
        "作品简介",
        "小说简介",
        "あらすじ",
        "줄거리",
        "책 소개",
        "작품 소개",
    }
)


@dataclass(frozen=True)
class ProcessedChapter:
    number: int
    section: EpubSection


def select_processed_chapters(sections: list[EpubSection]) -> list[ProcessedChapter]:
    explicit_chapters = []
    for section in sections:
        if should_skip_fallback_section(section):
            continue
        chapter_number = detect_chapter_number(section.title)
        if chapter_number is not None:
            explicit_chapters.append(ProcessedChapter(chapter_number, section))

    if explicit_chapters:
        return explicit_chapters

    fallback_chapters = []
    for section in sections:
        if should_skip_fallback_section(section):
            continue
        fallback_chapters.append(ProcessedChapter(len(fallback_chapters) + 1, section))
    return fallback_chapters


def should_skip_fallback_section(section: EpubSection) -> bool:
    title = normalize_whitespace(section.title)
    title_lower = title.casefold()
    source_name = Path(section.source_path).name.casefold()
    metadata_markers = ("author:", "tags:", "status:", "synopsis")
    front_matter_names = (
        "cover",
        "copyright",
        "contents",
        "nav",
        "navigation",
        "titlepage",
        "title-page",
        "toc",
    )

    if not title:
        return True
    if is_summary_section(section):
        return True
    if is_obvious_non_chapter_title(title):
        return True
    if any(name in title_lower or name in source_name for name in front_matter_names):
        return True
    return section.index <= 5 and any(marker in section.text.casefold() for marker in metadata_markers)


def normalize_summary_heading(value: str) -> str:
    value = normalize_whitespace(html.unescape(value)).casefold()
    return value.strip(" \t\r\n:：.-–—_[](){}")


def summary_label_remainder(value: str) -> str | None:
    text = normalize_whitespace(html.unescape(value)).strip()
    folded = text.casefold()
    for heading in SUMMARY_SECTION_TITLES:
        if folded == heading:
            return ""
        if not folded.startswith(heading):
            continue
        remainder = text[len(heading) :].lstrip()
        if remainder.startswith((":", "：")):
            return remainder[1:].strip()
    return None


def extract_labeled_summary(value: str) -> str | None:
    lines = value.splitlines()
    for index, line in enumerate(lines):
        inline_summary = summary_label_remainder(line)
        if inline_summary is None:
            continue
        remainder = [inline_summary, *lines[index + 1 :]] if inline_summary else lines[index + 1 :]
        summary = normalize_epub_summary("\n".join(remainder))
        if summary:
            return summary
    return None


def is_summary_section(section: EpubSection) -> bool:
    title = normalize_summary_heading(section.title)
    source_stem = normalize_summary_heading(Path(section.source_path).stem.replace("_", " ").replace("-", " "))
    paragraphs = [part.strip() for part in section.text.split("\n\n") if part.strip()]
    first_paragraph = normalize_summary_heading(paragraphs[0]) if paragraphs else ""
    explicitly_labelled = any(value in SUMMARY_SECTION_TITLES for value in (title, source_stem, first_paragraph))
    return explicitly_labelled or (section.index <= 5 and extract_labeled_summary(section.text) is not None)


def extract_summary_from_sections(sections: list[EpubSection]) -> str | None:
    """Extract a synopsis only from a clearly labelled front-matter section."""
    for section in sections:
        if not is_summary_section(section):
            continue

        labeled_summary = extract_labeled_summary(section.text)
        if labeled_summary:
            return labeled_summary

        paragraphs = [part.strip() for part in section.text.split("\n\n") if part.strip()]
        section_title = normalize_summary_heading(section.title)
        while paragraphs:
            heading = normalize_summary_heading(paragraphs[0])
            if heading == section_title or heading in SUMMARY_SECTION_TITLES:
                paragraphs.pop(0)
                continue
            break
        summary = normalize_epub_summary("\n\n".join(paragraphs))
        if summary:
            return summary
    return None


__all__ = [
    "ProcessedChapter",
    "extract_labeled_summary",
    "extract_summary_from_sections",
    "is_summary_section",
    "normalize_summary_heading",
    "select_processed_chapters",
    "should_skip_fallback_section",
    "summary_label_remainder",
]
