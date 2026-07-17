"""Filesystem persistence for the novel catalog."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src import paths


def list_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted((entry for entry in root.iterdir() if entry.is_dir()), key=lambda entry: entry.name)


def create_directories(root: Path) -> None:
    root.mkdir(parents=True)
    paths.novel_input_dir_from_root(root).mkdir(parents=True)
    paths.novel_output_dir_from_root(root, "vi").mkdir(parents=True)
    paths.novel_artifact_dir_from_root(root).mkdir(parents=True)


def delete_directory(root: Path, *, ignore_errors: bool = False) -> None:
    shutil.rmtree(root, ignore_errors=ignore_errors)


def load_progress(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {"completed": [], "failed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {"completed": [], "failed": []}
    if not isinstance(data, dict):
        return {"completed": [], "failed": []}
    return {
        "completed": [int(value) for value in data.get("completed", [])],
        "failed": [int(value) for value in data.get("failed", [])],
    }


def glossary_counts(path: Path) -> tuple[int, int, int]:
    if not path.exists():
        return 0, 0, 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return 0, 0, 0
    return (
        len(data.get("terms", {})),
        len(data.get("entities", {})),
        len(data.get("edges", [])),
    )


def has_files(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


__all__ = [
    "create_directories",
    "delete_directory",
    "glossary_counts",
    "has_files",
    "list_directories",
    "load_progress",
]
