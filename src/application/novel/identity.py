"""Novel identity, root, and path validation."""

from __future__ import annotations

import re
from pathlib import Path

from src.application.errors import ResourceNotFoundError
from src.paths import DEFAULT_TRANSLATED_ROOT

SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def is_valid_slug(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    if name in {".", ".."} or "/" in name or "\\" in name or name.startswith("."):
        return False
    return bool(SLUG_PATTERN.match(name))


def resolve_root(translated_dir: str | None) -> Path:
    root = Path(translated_dir) if translated_dir else DEFAULT_TRANSLATED_ROOT
    return root.resolve()


def resolve_path(root: Path, name: str) -> Path:
    if not is_valid_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = (root / name).resolve()
    try:
        novel_root.relative_to(root.resolve())
    except ValueError as error:
        raise ResourceNotFoundError(f"Novel path escapes root: {name}") from error
    return novel_root


def require_path(root: Path, name: str) -> Path:
    novel_root = resolve_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    return novel_root


__all__ = ["is_valid_slug", "require_path", "resolve_path", "resolve_root"]
