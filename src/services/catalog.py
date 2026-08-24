"""Filesystem persistence for the novel catalog."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Collection
from pathlib import Path

from src import paths
from src.domain.quality import source_language_fragments
from src.services.translation.reports import (
    content_hash,
    issue_is_ignored,
    post_check_review_key,
    review_key_is_ignored,
)

_REPORT_FILE_RE = re.compile(r"^chapter_(\d+)\.json$")
_SOURCE_WARNING_CODE = "contains_source_language_chars"
_IMPORTANT_WARNING_CODES = frozenset({_SOURCE_WARNING_CODE, "missing_translated_title"})


def list_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted((entry for entry in root.iterdir() if entry.is_dir()), key=lambda entry: entry.name)


def create_directories(root: Path) -> None:
    root.mkdir(parents=True)
    paths.novel_input_dir_from_root(root).mkdir(parents=True)
    paths.novel_output_dir_from_root(root, "vi").mkdir(parents=True)
    paths.novel_artifact_dir_from_root(root).mkdir(parents=True)


def delete_directory(root: Path, *, ignore_errors: bool = False) -> None:
    shutil.rmtree(root, ignore_errors=ignore_errors)


def load_progress(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {"completed": [], "failed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {"completed": [], "failed": []}
    if not isinstance(data, dict):
        return {"completed": [], "failed": []}
    return {
        "completed": [int(value) for value in data.get("completed", [])],
        "failed": [int(value) for value in data.get("failed", [])],
    }


def load_warning_chapters(
    directory: Path,
    output_directory: Path | None = None,
    *,
    warning_codes: Collection[str] | None = None,
) -> list[int]:
    """Return chapters with unresolved warnings, optionally filtered by codes."""
    if not directory.exists():
        return []

    chapters: set[int] = set()
    for path in directory.iterdir():
        match = _REPORT_FILE_RE.fullmatch(path.name)
        if match is None or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            continue
        if not isinstance(data, dict):
            continue
        manual_issues = data.get("manual_post_check_issues")
        issue_codes = {code for code in manual_issues if isinstance(code, str)} if isinstance(manual_issues, list) else set()
        if warning_codes is not None:
            issue_codes.intersection_update(warning_codes)
        if not issue_codes:
            continue

        chapter = int(match.group(1))
        if output_directory is not None:
            output_path = output_directory / f"chapter_{chapter:03d}.txt"
            if not output_path.exists():
                output_path = output_directory / f"chapter_{chapter}.txt"
            try:
                output_bytes = output_path.read_bytes()
                fingerprint = content_hash(output_bytes)
                translation = output_bytes.decode("utf-8")
            except OSError, UnicodeDecodeError:
                continue

            unresolved = set(issue_codes)
            for code in issue_codes:
                if issue_is_ignored(data, code, fingerprint):
                    unresolved.discard(code)
                    continue
                decisions = data.get("ignored_post_checks")
                if (
                    code != _SOURCE_WARNING_CODE
                    and isinstance(decisions, list)
                    and any(
                        isinstance(item, dict) and item.get("code") == code and item.get("content_hash") == fingerprint
                        for item in decisions
                    )
                ):
                    unresolved.discard(code)

            if _SOURCE_WARNING_CODE in unresolved:
                fragments = list(dict.fromkeys(source_language_fragments(translation)))
                granular_ignored = bool(fragments) and all(
                    review_key_is_ignored(
                        data,
                        post_check_review_key(_SOURCE_WARNING_CODE, fragment),
                        fingerprint,
                    )
                    for fragment in fragments
                )
                if granular_ignored:
                    unresolved.discard(_SOURCE_WARNING_CODE)
            if not unresolved:
                continue
        chapters.add(chapter)
    return sorted(chapters)


def load_important_warning_chapters(directory: Path, output_directory: Path | None = None) -> list[int]:
    """Return chapters with source characters or a missing translated title."""
    return load_warning_chapters(directory, output_directory, warning_codes=_IMPORTANT_WARNING_CODES)


def glossary_counts(path: Path) -> tuple[int, int, int]:
    if not path.exists():
        return 0, 0, 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return 0, 0, 0
    return (
        len(data.get("terms", {})),
        len(data.get("entities", {})),
        len(data.get("edges", [])),
    )


def load_glossary_terms(path: Path) -> dict[str, str]:
    """Load string glossary terms defensively."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, dict):
        return {}
    return {
        original: translated
        for original, translated in terms.items()
        if isinstance(original, str) and isinstance(translated, str)
    }


def has_files(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


__all__ = [
    "create_directories",
    "delete_directory",
    "glossary_counts",
    "has_files",
    "list_directories",
    "load_glossary_terms",
    "load_progress",
    "load_warning_chapters",
    "load_important_warning_chapters",
]
