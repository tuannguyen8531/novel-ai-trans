"""Filesystem persistence for per-novel translation rules."""

from __future__ import annotations

from pathlib import Path


def read(root: Path) -> str:
    path = root / "rules.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(root: Path, content: str) -> None:
    (root / "rules.md").write_text(content, encoding="utf-8")


__all__ = ["read", "write"]
