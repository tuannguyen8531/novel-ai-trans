"""Application workflow for importing EPUB books."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from src.application import config as app_config
from src.application.common import check_cancel, emit
from src.application.errors import ApplicationValidationError, PersistenceError
from src.application.progress import ProgressEvent
from src.services.importer import ChapterImportChange, EpubImportError, import_epub


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
            request.epub_path,
            share_root,
            name=request.name,
            keep_existing=request.keep_existing,
            source_url=request.source_url,
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
