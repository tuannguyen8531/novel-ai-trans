"""Helpers for safely reading and listing novel directories.

All paths are normalised through the configured ``translated_dir`` root and
verified to remain under it. A novel name is treated as a slug; absolute
paths, path separators, and dot segments are rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.api.errors import ResourceNotFoundError
from src.application.paths import DEFAULT_TRANSLATED_ROOT

SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def is_valid_novel_slug(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    if name in {".", ".."}:
        return False
    if "/" in name or "\\" in name:
        return False
    if name.startswith("."):
        return False
    return bool(SLUG_PATTERN.match(name))


def safe_novel_path(root: Path, novel: str) -> Path:
    if not is_valid_novel_slug(novel):
        raise ResourceNotFoundError(f"Invalid novel name: {novel!r}")
    base = (root / novel).resolve()
    root_resolved = root.resolve()
    try:
        base.relative_to(root_resolved)
    except ValueError as error:
        raise ResourceNotFoundError(f"Novel path escapes root: {novel}") from error
    return base


def resolve_translated_root(translated_dir: str | None) -> Path:
    root = Path(translated_dir) if translated_dir else DEFAULT_TRANSLATED_ROOT
    return root.resolve()


def list_novels(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir() and is_valid_novel_slug(entry.name))
