"""Shared chapter classification and file helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

FILE_PATTERN = re.compile(r"^chapter_(\d+)\.txt$")
CHAPTER_NUMBER_WIDTH = 3

CHAPTER_PATTERNS = (
    re.compile(r"(?<!\d)(?:제\s*)?(\d+)\s*(?:화|장)(?!\d)", re.IGNORECASE),
    re.compile(r"第\s*(\d+)\s*[章节話话回]", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d+)\s*[章节話话回](?!\d)", re.IGNORECASE),
    re.compile(r"\b(?:chương|chuong)\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(?:chapter|chap\.?|ch\.?)\s*#?\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(?:episode|ep\.?)\s*#?\s*(\d+)\b", re.IGNORECASE),
)

NOTICE_MARKERS = (
    "notice",
    "announcement",
    "공지",
    "公告",
    "通知",
)

_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff"
    r"\u3040-\u309f"
    r"\u30a0-\u30ff"
    r"\uac00-\ud7af"
    r"\u1100-\u11ff"
    r"\u3130-\u318f"
    r"\ufe30-\ufe4f"
    r"]"
)
_TITLE_REPLACEMENTS = str.maketrans(
    {
        "『": '"',
        "』": '"',
        "「": '"',
        "」": '"',
        "【": "[",
        "】": "]",
        "〖": "[",
        "〗": "]",
        "—": "-",
        "–": "-",
        "﹏": "~",
    }
)


def scan(directory: Path) -> dict[int, Path]:
    """Return chapter numbers mapped to files, sorted by chapter number."""
    if not directory.exists():
        return {}
    found: dict[int, Path] = {}
    for path in directory.iterdir():
        match = FILE_PATTERN.match(path.name)
        if match and path.is_file():
            number = int(match.group(1))
            current = found.get(number)
            if current is None or path.name == chapter_filename(number):
                found[number] = path
    return dict(sorted(found.items()))


def numbers(directory: Path) -> set[int]:
    """Return chapter numbers present in a directory."""
    return set(scan(directory))


def chapter_filename(number: int) -> str:
    """Return the canonical padded filename for a chapter number."""
    return f"chapter_{number:0{CHAPTER_NUMBER_WIDTH}d}.txt"


def chapter_path(directory: Path, number: int) -> Path:
    """Return an existing legacy/canonical path, or the canonical path for a new file."""
    canonical = directory / chapter_filename(number)
    if canonical.exists():
        return canonical
    legacy = directory / f"chapter_{number}.txt"
    if legacy.exists():
        return legacy
    return canonical


def read(directory: Path, number: int) -> str:
    """Read one chapter using canonical and legacy filename resolution."""
    return chapter_path(directory, number).read_text(encoding="utf-8")


def write(directory: Path, number: int, content: str) -> Path:
    """Persist one chapter, creating its owning directory when needed."""
    directory.mkdir(parents=True, exist_ok=True)
    path = chapter_path(directory, number)
    path.write_text(content, encoding="utf-8")
    return path


def delete(directory: Path, number: int) -> None:
    """Delete one existing chapter."""
    chapter_path(directory, number).unlink()


def read_title(file_path: Path, fallback: str, *, keep_cjk: bool = True) -> str:
    """Read and normalize a chapter title from the first non-empty lines."""
    if not file_path.exists():
        return fallback
    try:
        lines: list[str] = []
        with file_path.open(encoding="utf-8") as file:
            for line in file:
                stripped = line.strip().lstrip("\ufeff")
                if stripped:
                    lines.append(stripped)
                    if len(lines) >= 5:
                        break
        if not lines:
            return fallback

        headers: list[str] = []
        for line in lines:
            if is_translated_chapter_heading(line):
                headers.append(line)
            else:
                break

        title = headers[-1] if headers else lines[0]
        title = title.translate(_TITLE_REPLACEMENTS)
        if not keep_cjk:
            title = _CJK_PATTERN.sub("", title)
        return re.sub(r" +", " ", title).strip() or fallback
    except OSError, UnicodeError:
        return fallback


def is_translated_chapter_heading(title: str) -> bool:
    """Return whether a translated line starts with a numbered chapter marker."""
    normalized = title.lstrip("\ufeff").strip()
    return bool(re.match(r"^(?:chương|chuong|chapter)\s*#?\s*\d+\b", normalized, re.IGNORECASE))


def detect_chapter_number(title: str) -> int | None:
    """Return an explicit chapter number from a supported title format."""
    normalized_title = " ".join(title.split())
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(normalized_title)
        if match:
            return int(match.group(1))
    return None


def is_obvious_non_chapter_title(title: str) -> bool:
    """Return whether a title is clearly an announcement rather than story content."""
    normalized_title = " ".join(title.split()).casefold()
    if any(normalized_title.startswith(marker) for marker in NOTICE_MARKERS):
        return True
    if detect_chapter_number(title) is not None:
        return False
    return any(marker in normalized_title for marker in NOTICE_MARKERS)


def select_likely_chapters[T](
    items: list[T],
    *,
    title_getter: Callable[[T], str],
) -> list[T]:
    """Filter notices and prefer explicit chapter markers when the list has them."""
    candidates = [item for item in items if not is_obvious_non_chapter_title(title_getter(item))]
    explicit_chapters = [item for item in candidates if detect_chapter_number(title_getter(item)) is not None]
    return explicit_chapters or candidates
