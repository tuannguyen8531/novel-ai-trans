"""Shared helpers for crawl-related application workflows."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from threading import Event

from src.application import config as app_config
from src.application.errors import OperationCancelledError, ResourceNotFoundError
from src.application.progress import ProgressEvent
from src.paths import novel_config_path_from_root

_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        with suppress(Exception):
            callback(event)


def check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise OperationCancelledError("Crawl cancelled.")


def resolve_config_path(novel: str, *, translated_root: Path | None = None) -> Path:
    if not _SLUG_PATTERN.fullmatch(novel) or novel in {".", ".."}:
        raise ResourceNotFoundError(f"Invalid novel slug: {novel!r}")
    root = translated_root or Path(app_config.get_config().translated_dir)
    path = novel_config_path_from_root(root / novel)
    if not path.is_file():
        raise ResourceNotFoundError(f"Config not found for novel {novel!r}: {path}")
    return path


__all__ = ["check_cancel", "emit", "resolve_config_path"]
