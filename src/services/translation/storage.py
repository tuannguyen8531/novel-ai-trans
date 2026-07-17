"""Filesystem storage used by translation workflows."""

from __future__ import annotations

from pathlib import Path

from src.services import chapters


class TranslationStorage:
    """Read source chapters and persist translated chapter text."""

    def directory_exists(self, directory: Path) -> bool:
        return directory.exists()

    def scan(self, directory: Path) -> dict[int, Path]:
        return chapters.scan(directory)

    def translated_numbers(self, directory: Path) -> set[int]:
        return chapters.numbers(directory)

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write(self, directory: Path, chapter: int, content: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        chapters.chapter_path(directory, chapter).write_text(content, encoding="utf-8")

    def read_translation(self, directory: Path, chapter: int) -> str:
        return chapters.chapter_path(directory, chapter).read_text(encoding="utf-8")
