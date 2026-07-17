"""Novel chapter queries and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src import paths
from src.application.errors import ResourceNotFoundError
from src.application.novel.identity import require_path
from src.domain.language import SUPPORTED_TARGET_LANGUAGES, normalize_target_language
from src.services import chapters as chapter_service


@dataclass(frozen=True)
class Chapter:
    number: int
    has_source: bool
    has_translation: bool
    target: str | None
    title: str | None
    source_title: str | None


@dataclass(frozen=True)
class Content:
    novel: str
    chapter: int
    view: str
    target: str | None
    content: str


def list_chapters(root: Path, name: str) -> list[Chapter]:
    novel_root = require_path(root, name)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    sources = chapter_service.scan(input_dir)
    outputs = {
        target: chapter_service.scan(paths.novel_output_dir_from_root(novel_root, target))
        for target in SUPPORTED_TARGET_LANGUAGES
    }
    result: list[Chapter] = []
    for number in sources:
        source_title = chapter_service.read_title(sources[number], f"Chapter {number}")
        for target in SUPPORTED_TARGET_LANGUAGES:
            translated = number in outputs[target]
            title = f"Chapter {number}"
            if translated:
                title = chapter_service.read_title(outputs[target][number], title)
            result.append(
                Chapter(
                    number=number,
                    has_source=True,
                    has_translation=translated,
                    target=target,
                    title=title,
                    source_title=source_title,
                )
            )
    return result


def read_chapter(
    root: Path,
    name: str,
    number: int,
    *,
    view: Literal["source", "translation"],
    target: str | None = None,
) -> Content:
    novel_root = require_path(root, name)
    if view == "source":
        chapter_path = chapter_service.chapter_path(paths.novel_input_dir_from_root(novel_root), number)
        if not chapter_path.exists():
            raise ResourceNotFoundError(f"Source chapter not found: chapter {number}")
        return Content(name, number, view, None, chapter_service.read(paths.novel_input_dir_from_root(novel_root), number))

    normalized_target = normalize_target_language(target)
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    chapter_path = chapter_service.chapter_path(output_dir, number)
    if chapter_path.exists():
        return Content(name, number, view, normalized_target, chapter_service.read(output_dir, number))
    raise ResourceNotFoundError(f"Translated chapter not found: chapter {number}")


def write_chapter(
    root: Path,
    name: str,
    number: int,
    content: str,
    *,
    view: Literal["source", "translation"] = "source",
    target: str | None = None,
) -> Content:
    novel_root = require_path(root, name)
    if view == "source":
        input_dir = paths.novel_input_dir_from_root(novel_root)
        chapter_service.write(input_dir, number, content)
        return Content(name, number, view, None, content)

    normalized_target = normalize_target_language(target)
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    chapter_service.write(output_dir, number, content)
    return Content(name, number, view, normalized_target, content)


def delete_chapter(root: Path, name: str, number: int) -> None:
    novel_root = require_path(root, name)
    chapter_path = chapter_service.chapter_path(paths.novel_input_dir_from_root(novel_root), number)
    if not chapter_path.exists():
        raise ResourceNotFoundError(f"Input chapter not found: chapter {number}")
    chapter_service.delete(paths.novel_input_dir_from_root(novel_root), number)


__all__ = ["Chapter", "Content", "delete_chapter", "list_chapters", "read_chapter", "write_chapter"]
