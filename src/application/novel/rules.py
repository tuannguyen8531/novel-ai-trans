"""Novel translation-rules persistence."""

from __future__ import annotations

from pathlib import Path

from src.application.errors import PersistenceError
from src.application.novel.identity import require_path


def rules(root: Path, name: str) -> str:
    rules_path = require_path(root, name) / "rules.md"
    if not rules_path.exists():
        return ""
    try:
        return rules_path.read_text(encoding="utf-8")
    except OSError as error:
        raise PersistenceError(f"Failed to read rules: {error}") from error


def save_rules(root: Path, name: str, content: str) -> None:
    rules_path = require_path(root, name) / "rules.md"
    try:
        rules_path.write_text(content, encoding="utf-8")
    except OSError as error:
        raise PersistenceError(f"Failed to write rules: {error}") from error


__all__ = ["rules", "save_rules"]
