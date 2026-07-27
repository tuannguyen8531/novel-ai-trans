"""Chapter, metadata, and illustration persistence for EPUB imports."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from src.models import ChapterResult, NovelMetadata
from src.paths import resolve_novel_root
from src.services import chapters as chapter_service
from src.services.importing.changes import ChapterImportChange, ImportChanges, calculate_changes, classify_chapter
from src.services.importing.extractor import EPUB_IMAGE_PLACEHOLDER
from src.services.importing.selection import ProcessedChapter
from src.services.metadata import metadata_to_dict
from src.utils.files import merge_json_locked, write_bytes_atomic, write_json_atomic, write_text_atomic
from src.utils.text import normalize_text

ILLUSTRATION_MARKER = "[[ILLUSTRATION:{filename}]]"


@dataclass(frozen=True)
class StoragePaths:
    novel_dir: Path
    chapter_output_dir: Path
    illustrations_dir: Path


@dataclass(frozen=True)
class EpubIllustration:
    index: int
    chapter_number: int
    source_path: str
    path: str


@dataclass(frozen=True)
class PersistedImport:
    chapters: list[ChapterResult]
    illustrations: list[EpubIllustration]
    changes: ImportChanges
    warnings: tuple[str, ...]


def prepare_storage(share_root: Path, novel_slug: str, *, keep_existing: bool) -> tuple[StoragePaths, dict[int, Path]]:
    novel_dir = resolve_novel_root(share_root, novel_slug)
    chapter_output_dir = novel_dir / "input"
    illustrations_dir = novel_dir / "illustrations"
    chapter_output_dir.mkdir(parents=True, exist_ok=True)
    illustrations_dir.mkdir(parents=True, exist_ok=True)
    existing_chapters = chapter_service.scan(chapter_output_dir)
    if not keep_existing:
        clean_existing_illustrations(illustrations_dir)
    return (
        StoragePaths(
            novel_dir=novel_dir,
            chapter_output_dir=chapter_output_dir,
            illustrations_dir=illustrations_dir,
        ),
        existing_chapters,
    )


def persist_metadata(paths: StoragePaths, metadata: NovelMetadata, summary: str | None) -> None:
    metadata_path = paths.novel_dir / "metadata.json"
    if not metadata_path.exists():
        write_json_atomic(metadata_path, metadata_to_dict(metadata))
    elif summary:
        merge_json_locked(
            metadata_path,
            lambda current: (
                current
                if isinstance(current.get("summary"), str) and current["summary"].strip()
                else {**current, "summary": summary}
            ),
        )


def persist_chapters(
    epub_path: Path,
    chapters_to_import: list[ProcessedChapter],
    source_url: str,
    paths: StoragePaths,
    existing_chapters: dict[int, Path],
    *,
    keep_existing: bool,
) -> PersistedImport:
    chapters: list[ChapterResult] = []
    illustrations: list[EpubIllustration] = []
    warnings: list[str] = []
    unchanged_chapters: list[int] = []
    overwritten_chapters: list[ChapterImportChange] = []
    added_chapters: list[int] = []
    used_chapters: set[int] = set()
    illustration_index = 0

    with zipfile.ZipFile(epub_path) as epub:
        for chapter in chapters_to_import:
            chapter_number = chapter.number
            section = chapter.section
            if chapter_number in used_chapters:
                warnings.append(f"duplicate chapter {chapter_number} skipped: {section.title}")
                continue

            used_chapters.add(chapter_number)
            chapter_text = section.text
            chapter_illustration_index = 0
            for image_index, image_path in enumerate(section.image_paths, start=1):
                try:
                    image_data = epub.read(image_path)
                except KeyError:
                    warnings.append(f"missing image skipped: {image_path}")
                    chapter_text = chapter_text.replace(
                        EPUB_IMAGE_PLACEHOLDER.format(index=image_index),
                        "",
                    )
                    continue

                illustration_index += 1
                chapter_illustration_index += 1
                illustration_output = paths.illustrations_dir / illustration_filename(
                    chapter_number,
                    chapter_illustration_index,
                    image_path,
                )
                write_bytes_atomic(illustration_output, image_data)
                chapter_text = chapter_text.replace(
                    EPUB_IMAGE_PLACEHOLDER.format(index=image_index),
                    ILLUSTRATION_MARKER.format(filename=illustration_output.name),
                )
                illustrations.append(
                    EpubIllustration(
                        index=illustration_index,
                        chapter_number=chapter_number,
                        source_path=image_path,
                        path=str(illustration_output),
                    )
                )

            path = chapter_service.chapter_path(paths.chapter_output_dir, chapter_number)
            imported_text = format_imported_chapter(section.title, chapter_text, chapter_number)
            status = classify_chapter(path, imported_text)
            if status == "unchanged":
                unchanged_chapters.append(chapter_number)
            else:
                write_text_atomic(path, imported_text)
                if status == "overwritten":
                    overwritten_chapters.append(ChapterImportChange(number=chapter_number, title=section.title))
                else:
                    added_chapters.append(chapter_number)
            chapters.append(
                ChapterResult(
                    index=chapter_number,
                    title=section.title,
                    source_url=f"{source_url}#{section.source_path}",
                    path=str(path),
                )
            )

    changes = calculate_changes(
        set(existing_chapters),
        used_chapters,
        keep_existing=keep_existing,
        unchanged=unchanged_chapters,
        overwritten=overwritten_chapters,
        added=added_chapters,
    )
    for chapter_number in changes.removed:
        existing_chapters[chapter_number].unlink()

    chapters.sort(key=lambda chapter_result: chapter_result.index)
    return PersistedImport(
        chapters=chapters,
        illustrations=illustrations,
        changes=changes,
        warnings=tuple(warnings),
    )


def format_imported_chapter(title: str, body: str, chapter_number: int) -> str:
    normalized_title = " ".join(normalize_text(title).split()) or f"Chapter {chapter_number}"
    normalized_body = body.strip()
    if normalized_body:
        first_line, separator, remainder = normalized_body.partition("\n")
        if normalize_text(first_line).lstrip("\ufeff").casefold() == normalized_title.casefold():
            normalized_body = remainder.strip() if separator else ""
    if not normalized_body:
        return normalized_title + "\n"
    return f"{normalized_title}\n\n{normalized_body}\n"


def clean_existing_illustrations(illustrations_dir: Path) -> None:
    for existing_file in illustrations_dir.glob("*-*.*"):
        if existing_file.is_file():
            existing_file.unlink()


def illustration_filename(chapter_number: int, chapter_image_number: int, source_path: str) -> str:
    suffix = Path(source_path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        suffix = ".img"
    return f"{chapter_number:03d}-{chapter_image_number:03d}{suffix}"


__all__ = [
    "EpubIllustration",
    "PersistedImport",
    "StoragePaths",
    "clean_existing_illustrations",
    "format_imported_chapter",
    "illustration_filename",
    "persist_chapters",
    "persist_metadata",
    "prepare_storage",
]
