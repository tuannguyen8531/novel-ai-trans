"""Workflow for importing EPUB books."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from src.application import config as app_config
from src.application.crawl.common import check_cancel, emit
from src.application.errors import ApplicationValidationError, PersistenceError
from src.application.progress import ProgressEvent
from src.models import ChapterResult, NovelMetadata
from src.services.importing.changes import ChapterImportChange, ImportChanges
from src.services.importing.extractor import normalize_whitespace
from src.services.importing.reader import EpubImportError, read_epub_book, resolve_epub_path
from src.services.importing.selection import extract_summary_from_sections, select_processed_chapters
from src.services.importing.storage import (
    EpubIllustration,
    persist_chapters,
    persist_metadata,
    prepare_storage,
)
from src.utils.text import slugify


@dataclass
class ImportRequest:
    epub_path: Path
    name: str | None = None
    translated_output: Path | None = None
    keep_existing: bool = False
    source_url: str | None = None


@dataclass
class ImportResult:
    novel: str
    title: str
    chapters: int
    illustrations: int
    output_dir: str
    retained: int
    unchanged: int
    overwritten: int
    added: int
    removed: int
    overwritten_chapters: list[ChapterImportChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EpubImportResult:
    metadata: NovelMetadata
    chapters: list[ChapterResult]
    illustrations: list[EpubIllustration]
    output_dir: str
    chapter_output_dir: str
    illustrations_dir: str
    changes: ImportChanges
    warnings: tuple[str, ...]

    @property
    def retained_chapters(self) -> tuple[int, ...]:
        return self.changes.retained

    @property
    def unchanged_chapters(self) -> tuple[int, ...]:
        return self.changes.unchanged

    @property
    def overwritten_chapters(self) -> tuple[ChapterImportChange, ...]:
        return self.changes.overwritten

    @property
    def added_chapters(self) -> tuple[int, ...]:
        return self.changes.added

    @property
    def removed_chapters(self) -> tuple[int, ...]:
        return self.changes.removed


def import_epub(request: ImportRequest, share_root: Path) -> EpubImportResult:
    """Coordinate EPUB reading, classification, comparison, and persistence."""
    epub_path = resolve_epub_path(request.epub_path)
    book = read_epub_book(epub_path)

    fallback_title = request.name or epub_path.stem
    title = normalize_whitespace(book.metadata.title or fallback_title)
    author = normalize_whitespace(book.metadata.author or "") or None
    summary = book.metadata.description or extract_summary_from_sections(book.sections)
    source_url = request.source_url
    if source_url is None:
        source_url = epub_path.resolve().as_uri()
    fallback_slug = slugify(epub_path.stem, fallback="epub")
    novel_slug = slugify(request.name or epub_path.stem, fallback=fallback_slug)
    processed_chapters = select_processed_chapters(book.sections)
    if not processed_chapters:
        raise EpubImportError(f"no importable chapters found in {epub_path}")

    paths, existing_chapters = prepare_storage(
        share_root,
        novel_slug,
        keep_existing=request.keep_existing,
    )
    metadata = NovelMetadata(
        title=title,
        author=author,
        source_url=source_url,
        site_name=novel_slug,
        summary=summary,
    )
    persist_metadata(paths, metadata, summary)
    persisted = persist_chapters(
        epub_path,
        processed_chapters,
        source_url,
        paths,
        existing_chapters,
        keep_existing=request.keep_existing,
    )
    return EpubImportResult(
        metadata=metadata,
        chapters=persisted.chapters,
        illustrations=persisted.illustrations,
        output_dir=str(paths.novel_dir),
        chapter_output_dir=str(paths.chapter_output_dir),
        illustrations_dir=str(paths.illustrations_dir),
        changes=persisted.changes,
        warnings=persisted.warnings,
    )


def import_epub_workflow(
    request: ImportRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> ImportResult:
    config = app_config.get_config()
    share_root = request.translated_output or (Path(config.translated_dir) if config.translated_dir else None)
    if share_root is None:
        share_root = Path("translated")
    check_cancel(cancel_event)
    emit(progress_callback, ProgressEvent(kind="phase", message=f"Importing {request.epub_path.name}"))
    try:
        result = import_epub(
            request,
            share_root,
        )
    except EpubImportError as error:
        raise ApplicationValidationError(str(error)) from error
    except (OSError, ValueError) as error:
        raise PersistenceError(str(error)) from error
    check_cancel(cancel_event)
    emit(
        progress_callback,
        ProgressEvent(
            kind="log",
            message=(
                "Import chapters: "
                f"retained {len(result.retained_chapters)} · "
                f"unchanged {len(result.unchanged_chapters)} · "
                f"overwritten {len(result.overwritten_chapters)} · "
                f"added {len(result.added_chapters)} · "
                f"removed {len(result.removed_chapters)}"
            ),
        ),
    )
    for change in result.overwritten_chapters:
        emit(
            progress_callback,
            ProgressEvent(kind="log", chapter=change.number, message=f"Overwritten chapter {change.number}: {change.title}"),
        )
    return ImportResult(
        novel=Path(result.output_dir).name,
        title=result.metadata.title,
        chapters=len(result.chapters),
        illustrations=len(result.illustrations),
        output_dir=result.output_dir,
        retained=len(result.retained_chapters),
        unchanged=len(result.unchanged_chapters),
        overwritten=len(result.overwritten_chapters),
        added=len(result.added_chapters),
        removed=len(result.removed_chapters),
        overwritten_chapters=list(result.overwritten_chapters),
        warnings=list(result.warnings),
    )


__all__ = ["ImportRequest", "ImportResult", "import_epub_workflow"]
