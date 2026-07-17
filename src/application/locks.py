"""Application-level novel operation locking."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src import paths
from src.application.errors import ResourceConflictError
from src.utils import files

LOCK_DIR = paths.LOCK_DIR
_ACTIVE_LOCKS: set[str] = set()


def novel_runtime_key(novel: str) -> str:
    return hashlib.sha256(novel.encode("utf-8")).hexdigest()


@contextmanager
def novel_lock(novel: str, *, lock_dir: Path | None = None) -> Iterator[None]:
    """Prevent overlapping translation and glossary operations for one novel."""
    message = f"Novel {novel!r} is currently locked by another translation or glossary apply operation."
    if novel in _ACTIVE_LOCKS:
        raise ResourceConflictError(message)

    _ACTIVE_LOCKS.add(novel)
    try:
        path = (lock_dir or LOCK_DIR) / f"{novel_runtime_key(novel)}.lock"
        try:
            with files.exclusive_file_lock(path, blocking=False):
                yield
        except BlockingIOError as error:
            raise ResourceConflictError(message) from error
    finally:
        _ACTIVE_LOCKS.discard(novel)
