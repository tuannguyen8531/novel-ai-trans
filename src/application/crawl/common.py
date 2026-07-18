"""Shared helpers for crawl application workflows."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from threading import Event

from src.application import config as app_config
from src.application.errors import OperationCancelledError, ResourceNotFoundError
from src.application.progress import ProgressEvent
from src.paths import novel_config_path_from_root, resolve_novel_root


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        with suppress(Exception):
            callback(event)


def check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise OperationCancelledError("Crawl cancelled.")


def resolve_config_path(novel: str, *, translated_root: Path | None = None) -> Path:
    root = translated_root or Path(app_config.get_config().translated_dir)
    try:
        path = novel_config_path_from_root(resolve_novel_root(root, novel))
    except ValueError as error:
        raise ResourceNotFoundError(f"Invalid novel slug: {novel!r}") from error
    if not path.is_file():
        raise ResourceNotFoundError(f"Config not found for novel {novel!r}: {path}")
    return path


__all__ = ["check_cancel", "emit", "resolve_config_path"]
