"""Novel translation-rules persistence."""

from __future__ import annotations

from pathlib import Path

from src.application.errors import PersistenceError
from src.application.novel.identity import require_path
from src.services import rules as rules_repository


def rules(root: Path, name: str) -> str:
    try:
        return rules_repository.read(require_path(root, name))
    except OSError as error:
        raise PersistenceError(f"Failed to read rules: {error}") from error


def save_rules(root: Path, name: str, content: str) -> None:
    try:
        rules_repository.write(require_path(root, name), content)
    except OSError as error:
        raise PersistenceError(f"Failed to write rules: {error}") from error


__all__ = ["rules", "save_rules"]
