"""Novel identity, root, and path validation."""

from __future__ import annotations

from pathlib import Path

from src.application.errors import ResourceNotFoundError
from src.paths import DEFAULT_TRANSLATED_ROOT, is_valid_novel_name, resolve_novel_root


def is_valid_slug(name: str) -> bool:
    return is_valid_novel_name(name)


def resolve_root(translated_dir: str | None) -> Path:
    root = Path(translated_dir) if translated_dir else DEFAULT_TRANSLATED_ROOT
    return root.resolve()


def resolve_path(root: Path, name: str) -> Path:
    try:
        return resolve_novel_root(root, name)
    except ValueError as error:
        raise ResourceNotFoundError(f"Invalid novel name or path: {name!r}") from error


def require_path(root: Path, name: str) -> Path:
    novel_root = resolve_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    return novel_root


__all__ = ["is_valid_slug", "require_path", "resolve_path", "resolve_root"]
