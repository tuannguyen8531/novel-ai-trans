"""Input inspection used by translation adapters."""

from __future__ import annotations

from pathlib import Path

from src.services.metadata import load_source_language
from src.services.translation.storage import TranslationStorage


def scan_input(directory: Path) -> dict[int, Path]:
    storage = TranslationStorage()
    return storage.scan(directory) if storage.directory_exists(directory) else {}


def source_language(novel: str) -> str:
    return load_source_language(novel)


__all__ = ["scan_input", "source_language"]
