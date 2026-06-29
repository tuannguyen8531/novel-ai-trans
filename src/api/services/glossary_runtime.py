"""Glossary read/write helpers used by the API routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import Event

from src.application.errors import ResourceConflictError, ResourceNotFoundError
from src.application.progress import ProgressEvent
from src.domain.glossary import audit_term_usage, validate_glossary_data
from src.services.glossary import (
    _resolve_glossary,
    remove_glossary_term,
    update_glossary_term,
)
from src.services.glossary import (
    remove_character as remove_character_impl,
)
from src.services.glossary import (
    remove_relationship as remove_relationship_impl,
)
from src.services.glossary import (
    save_character as _save_character,
)
from src.services.glossary import (
    save_glossary as _save_glossary,
)
from src.services.glossary import (
    save_relationship as _save_relationship,
)


def _emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001
            pass


def _check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        from src.application.errors import OperationCancelledError

        raise OperationCancelledError("Glossary operation cancelled.")


def load_glossary(novel_root: Path) -> dict:
    path = _resolve_glossary(novel_root.name)
    if not path.exists():
        return {"terms": {}, "entities": {}, "edges": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"terms": {}, "entities": {}, "edges": []}


def save_terms(novel_root: Path, terms: dict[str, str]) -> dict:
    _save_glossary(novel_root.name, terms)
    return load_glossary(novel_root)


def save_term(novel_root: Path, original: str, translated: str) -> dict:
    _save_glossary(novel_root.name, {original: translated})
    return load_glossary(novel_root)


def remove_term(novel_root: Path, original: str) -> dict:
    remove_glossary_term(novel_root.name, original)
    return load_glossary(novel_root)


def update_term(
    novel_root: Path,
    old_original: str,
    new_original: str,
    translated: str,
    *,
    overwrite: bool,
) -> dict:
    try:
        update_glossary_term(
            novel_root.name,
            old_original,
            new_original,
            translated,
            overwrite=overwrite,
        )
    except KeyError as error:
        raise ResourceNotFoundError(f"Glossary term not found: {old_original}") from error
    except FileExistsError as error:
        raise ResourceConflictError(f"Glossary term already exists: {new_original}") from error
    return load_glossary(novel_root)


def remove_character(novel_root: Path, original: str) -> dict:
    remove_character_impl(novel_root.name, original)
    return load_glossary(novel_root)


def remove_relationship(novel_root: Path, from_char: str, to_char: str) -> dict:
    remove_relationship_impl(novel_root.name, from_char, to_char)
    return load_glossary(novel_root)


def save_character(
    novel_root: Path,
    original: str,
    *,
    translated_name: str,
    role: str,
) -> dict:
    _save_character(
        novel_root.name,
        original,
        translated_name=translated_name,
        role=role,
    )
    return load_glossary(novel_root)


def save_relationship(
    novel_root: Path,
    *,
    from_char: str,
    to_char: str,
    relationship: str,
    since: int | None = None,
    update_since: bool = False,
) -> dict:
    _save_relationship(
        novel_root.name,
        from_char,
        to_char,
        relationship,
        since_chapter=since,
        update_since=update_since,
    )
    return load_glossary(novel_root)


def validate_glossary(
    novel_root: Path,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[str]:
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", novel=novel_root.name, message="Validating glossary"))
    data = load_glossary(novel_root)
    issues = validate_glossary_data(data)
    _check_cancel(cancel_event)
    return issues


def audit_glossary(
    novel_root: Path,
    *,
    target: str | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[dict]:

    data = load_glossary(novel_root)
    terms = data.get("terms", {})
    chapters = sorted((novel_root / "input").glob("chapter_*.txt"))
    target = target or "vi"
    out_dir = novel_root / "output" if target == "vi" else novel_root / "output" / target
    if not out_dir.exists():
        return []
    total = len(chapters)
    issues: list[dict] = []
    for index, source_path in enumerate(chapters, 1):
        _check_cancel(cancel_event)
        if cancel_event is not None and cancel_event.is_set():
            break
        chapter_match = source_path.stem.split("_")[-1]
        try:
            chapter_num = int(chapter_match)
        except ValueError:
            continue
        output_path = out_dir / f"chapter_{chapter_num:03d}.txt"
        if not output_path.exists():
            output_path = out_dir / source_path.name
        if not output_path.exists():
            continue
        try:
            source_text = source_path.read_text(encoding="utf-8")
            translated_text = output_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for issue in audit_term_usage(terms, source_text, translated_text):
            issues.append({"chapter": chapter_num, **issue})
        _emit(
            progress_callback,
            ProgressEvent(
                kind="progress",
                novel=novel_root.name,
                current=index,
                total=total,
                chapter=chapter_num,
                pct=round(index / total * 100, 2) if total else None,
            ),
        )
    return issues
