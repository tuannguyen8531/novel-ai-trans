"""Glossary validation and translated-output auditing."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from threading import Event

from src import paths
from src.application import config as app_config
from src.application.errors import OperationCancelledError
from src.application.glossary.storage import load_glossary
from src.application.progress import ProgressEvent
from src.domain.glossary import audit_term_usage, validate_glossary_data
from src.services import chapters as chapter_service


def _emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        with suppress(Exception):
            callback(event)


def _check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise OperationCancelledError("Glossary operation cancelled.")


def validate_glossary(
    novel_name: str,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[str]:
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", novel=novel_name, message="Validating glossary"))
    issues = validate_glossary_data(load_glossary(novel_name))
    _check_cancel(cancel_event)
    return issues


def audit_glossary(
    novel_name: str,
    *,
    target: str | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[dict]:
    terms = load_glossary(novel_name).get("terms", {})
    return audit_terms(
        novel_name,
        terms,
        target=target,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )


def audit_terms(
    novel_name: str,
    terms: dict[str, str],
    *,
    target: str | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[dict]:
    """Audit translated chapters against an explicit set of terms."""
    novel_root = paths.novel_root_dir(app_config.get_config(), novel_name)
    chapters = list(chapter_service.scan(paths.novel_input_dir_from_root(novel_root)).values())
    output_dir = paths.novel_output_dir_from_root(novel_root, target or "vi")
    if not output_dir.exists():
        return []

    issues: list[dict] = []
    total = len(chapters)
    for index, source_path in enumerate(chapters, 1):
        _check_cancel(cancel_event)
        try:
            chapter_number = int(source_path.stem.split("_")[-1])
        except ValueError:
            continue
        output_path = chapter_service.chapter_path(output_dir, chapter_number)
        if not output_path.exists():
            continue
        try:
            source_text = chapter_service.read(source_path.parent, chapter_number)
            translated_text = chapter_service.read(output_dir, chapter_number)
        except OSError:
            continue
        issues.extend({"chapter": chapter_number, **issue} for issue in audit_term_usage(terms, source_text, translated_text))
        _emit(
            progress_callback,
            ProgressEvent(
                kind="progress",
                novel=novel_name,
                current=index,
                total=total,
                chapter=chapter_number,
                pct=round(index / total * 100, 2) if total else None,
            ),
        )
    return issues
