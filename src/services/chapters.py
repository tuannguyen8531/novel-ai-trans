"""Shared chapter classification and file helpers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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

_HEADING_PREFIX_PATTERNS = (
    re.compile(
        r"^\s*第\s*(?P<number>\d+)\s*[章节話话回]\s*[:：.\-]?\s*(?P<title>.*?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:chapter|chap\.?|ch\.?)\s*#?\s*(?P<number>\d+)\s*[:：.\-]?\s*(?P<title>.*?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:chương|chuong)\s*(?P<number>\d+)\s*[:：.\-]?\s*(?P<title>.*?)\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(?:제\s*)?(?P<number>\d+)\s*[章节話话回화]\s*[:：.\-]?\s*(?P<title>.*?)\s*$",
        re.IGNORECASE,
    ),
)
_TRAILING_PART_RE = re.compile(r"\((?P<part>[^()]*)\)\s*$")
_CHINESE_NUMERAL_DIGITS = frozenset("零〇○一二两兩三四五六七八九")
_CHINESE_NUMERAL_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10_000, "萬": 10_000, "亿": 100_000_000, "億": 100_000_000}
_CHINESE_NUMERAL_RE = re.compile(r"[零〇○一二两兩三四五六七八九十百千万萬亿億]+")


@dataclass(frozen=True)
class ParsedChapterTitle:
    """A numbered heading and a possible trailing series-part candidate."""

    heading: str
    number: int
    title: str
    candidate_base: str
    candidate_part: int | None
    candidate_key: str


@dataclass(frozen=True)
class ResolvedChapterTitle:
    """A heading after neighboring chapters confirm (or reject) its suffix."""

    parsed: ParsedChapterTitle
    base: str
    part: int | None
    is_series: bool


def _normalize_title_text(value: str) -> str:
    """Normalize spacing and full-width punctuation for title comparisons."""
    normalized = unicodedata.normalize("NFKC", value).translate(_TITLE_REPLACEMENTS)
    return re.sub(r"\s+", " ", normalized).strip()


def title_key(value: str) -> str:
    """Return a stable comparison key without discarding meaningful punctuation."""
    return _normalize_title_text(value).casefold()


def parse_chinese_numeral(value: str) -> int | None:
    """Parse a standalone Arabic or Chinese numeral, conservatively."""
    token = unicodedata.normalize("NFKC", value).strip()
    if token.isdigit():
        number = int(token)
        return number if number > 0 else None
    if not token or not _CHINESE_NUMERAL_RE.fullmatch(token):
        return None

    digit_map = {
        "零": 0,
        "〇": 0,
        "○": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "兩": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    # Positional strings such as 二〇三 are common in titles.
    if all(character in _CHINESE_NUMERAL_DIGITS for character in token):
        number = int("".join(str(digit_map[character]) for character in token))
        return number if number > 0 else None

    total = 0
    section = 0
    current = 0
    for character in token:
        if character in digit_map:
            current = digit_map[character]
            continue
        unit = _CHINESE_NUMERAL_UNITS[character]
        if unit < 10_000:
            section += (current or 1) * unit
            current = 0
        else:
            section = (section + current) * unit
            total += section
            section = 0
            current = 0
    number = total + section + current
    return number if number > 0 else None


def _split_trailing_part(title: str) -> tuple[str, int | None]:
    """Return a title base and a numeric trailing-parenthesis candidate."""
    normalized = _normalize_title_text(title)
    match = _TRAILING_PART_RE.search(normalized)
    if not match:
        return normalized, None
    part = parse_chinese_numeral(match.group("part"))
    if part is None:
        return normalized, None
    base = normalized[: match.start()].rstrip()
    return base, part


def strip_numeric_title_suffix(title: str) -> str:
    """Remove a numeric parenthesized suffix returned accidentally by an LLM."""
    base, part = _split_trailing_part(title)
    return base if part is not None else _normalize_title_text(title)


def parse_chapter_heading(line: str) -> ParsedChapterTitle | None:
    """Parse a numbered source heading and its possible trailing part marker."""
    heading = _normalize_title_text(line.lstrip("\ufeff"))
    for pattern in _HEADING_PREFIX_PATTERNS:
        match = pattern.match(heading)
        if not match:
            continue
        number = int(match.group("number"))
        title = _normalize_title_text(match.group("title"))
        candidate_base, candidate_part = _split_trailing_part(title)
        return ParsedChapterTitle(
            heading=heading,
            number=number,
            title=title,
            candidate_base=candidate_base,
            candidate_part=candidate_part,
            candidate_key=title_key(candidate_base),
        )
    return None


def resolve_chapter_title_series(
    parsed: ParsedChapterTitle,
    catalog: Mapping[int, str] | None = None,
) -> ResolvedChapterTitle:
    """Confirm a trailing part only when an adjacent title supports a sequence."""
    if not parsed.candidate_key or not catalog:
        return ResolvedChapterTitle(parsed, parsed.title, None, False)

    for neighbor_number in (parsed.number - 1, parsed.number + 1):
        neighbor_line = catalog.get(neighbor_number)
        if not neighbor_line:
            continue
        neighbor = parse_chapter_heading(neighbor_line)
        if neighbor is None or neighbor.candidate_key != parsed.candidate_key:
            continue

        current_part = parsed.candidate_part
        neighbor_part = neighbor.candidate_part
        if current_part is None and neighbor_part == 2:
            # The first chapter is an implicit part one; do not invent ``(1)``.
            return ResolvedChapterTitle(parsed, parsed.candidate_base, None, True)
        if neighbor_part is None and current_part == 2:
            return ResolvedChapterTitle(parsed, parsed.candidate_base, current_part, True)
        if current_part is not None and neighbor_part is not None and abs(current_part - neighbor_part) == 1:
            return ResolvedChapterTitle(parsed, parsed.candidate_base, current_part, True)

    return ResolvedChapterTitle(parsed, parsed.title, None, False)


def split_leading_chapter_heading(
    text: str,
    chapter_number: int,
    catalog: Mapping[int, str] | None = None,
) -> tuple[ResolvedChapterTitle | None, str]:
    """Remove one numbered heading from the source text before chunking."""
    lines = text.splitlines(keepends=True)
    first_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return None, text

    parsed = parse_chapter_heading(lines[first_index].strip())
    if parsed is None or parsed.number != chapter_number:
        return None, text

    resolved = resolve_chapter_title_series(parsed, catalog)
    remaining = [*lines[:first_index], *lines[first_index + 1 :]]
    while len(remaining) > first_index and not remaining[first_index].strip():
        remaining.pop(first_index)
    return resolved, "".join(remaining)


def format_translated_chapter_heading(
    chapter_number: int,
    translated_base: str,
    part: int | None,
    target_language: str,
) -> str:
    """Format a finalized target-language heading deterministically."""
    marker = "Chapter" if target_language == "en" else "Chương"
    base = _normalize_title_text(translated_base)
    heading = f"{marker} {chapter_number}: {base}" if base else f"{marker} {chapter_number}"
    return f"{heading} ({part})" if part is not None else heading


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


def deduplicate_leading_headings(text: str, *, allow_unnumbered: bool = False) -> str:
    """Collapse equivalent leading chapter headings, keeping the last."""
    lines = text.splitlines(keepends=True)
    while True:
        headings = [(index, line.strip().lstrip("\ufeff")) for index, line in enumerate(lines) if line.strip()][:2]
        if len(headings) < 2:
            break

        (first_index, first), (second_index, second) = headings
        if not _equivalent_headings(first, second, allow_unnumbered=allow_unnumbered):
            break

        separator = lines[first_index + 1 : second_index]
        following_line = second_index + 1
        has_following_separator = following_line < len(lines) and not lines[following_line].strip()
        replacement = [lines[second_index]] if has_following_separator else [lines[second_index], *separator]
        lines[first_index : second_index + 1] = replacement

    return "".join(lines)


def _equivalent_headings(first: str, second: str, *, allow_unnumbered: bool) -> bool:
    first_number = detect_chapter_number(first)
    if first_number is not None and first_number == detect_chapter_number(second):
        return True
    if not allow_unnumbered:
        return False

    first_key = _heading_key(first)
    return bool(first_key and first_key == _heading_key(second))


def _heading_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if unicodedata.category(character)[0] not in {"C", "P", "S", "Z"})


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
