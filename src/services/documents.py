"""Filesystem persistence for novel metadata documents."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.utils import files as file_utils


def load(root: Path) -> dict[str, Any]:
    path = root / "metadata.json"
    try:
        return file_utils.read_json_locked(path)
    except json.JSONDecodeError, OSError:
        return {}


def write(root: Path, metadata: dict[str, Any], *, trailing_newline: bool = True) -> None:
    content = json.dumps(metadata, ensure_ascii=False, indent=2)
    (root / "metadata.json").write_text(
        content + ("\n" if trailing_newline else ""),
        encoding="utf-8",
    )


def update(root: Path, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return file_utils.merge_json_locked(root / "metadata.json", updater)


__all__ = ["load", "update", "write"]
