"""Application-layer packaging workflow.

The pure :func:`run_pack` function is shared by the CLI command and the
FastAPI route. It does not print, call :func:`sys.exit`, or install signal
handlers.

The pack workflow never accepts an unrestricted output filesystem path from
API callers; artifacts always write into the novel root. The CLI keeps its
``--output`` option.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from src import paths as _paths
from src.application.config import get_config
from src.application.errors import (
    OperationCancelledError,
    PersistenceError,
    ResourceNotFoundError,
)
from src.application.progress import ProgressEvent
from src.domain.language import normalize_target_language
from src.services.packaging.builder import EPUBBuilder, package_file_stem
from src.services.packaging.chapters import parse_chapter_file
from src.services.packaging.covers import cleanup_cover_image, resolve_cover_image
from src.services.packaging.images import resolve_chapter_images
from src.services.packaging.metadata import load_metadata, resolve_book_author, resolve_book_title

__all__ = [
    "PackRequest",
    "PackResult",
    "ArtifactInfo",
    "run_pack",
]


@dataclass
class PackRequest:
    novel: str
    target_language: str | None = None
    title: str = ""
    author: str = "AI Translator"
    output_dir: Path | None = None


@dataclass
class ArtifactInfo:
    format: str
    path: str
    size: int


@dataclass
class PackResult:
    novel: str
    title: str
    author: str
    artifacts: list[ArtifactInfo] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def _emit(
    callback: Callable[[ProgressEvent], None] | None,
    event: ProgressEvent,
) -> None:
    if callback is not None:
        with suppress(Exception):
            callback(event)


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError("Pack cancelled.")


def _find_chapter_files(output_dir: Path) -> dict[int, Path]:
    import re

    if not output_dir.exists():
        raise ResourceNotFoundError(f"Translation output folder not found: {output_dir}")
    pattern = re.compile(r"^chapter_(\d+)\.txt$")
    files: dict[int, Path] = {}
    for f in output_dir.iterdir():
        if f.is_file():
            match = pattern.match(f.name)
            if match:
                files[int(match.group(1))] = f
    if not files:
        raise ResourceNotFoundError(f"No translated chapter files (chapter_*.txt) found in {output_dir}")
    return files


def run_pack(
    request: PackRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> PackResult:
    """Build an EPUB artifact for *request.novel*."""
    config = get_config()
    started_at = time.time()
    target_language = request.target_language or config.target_language
    target_normalized = normalize_target_language(target_language)

    output_dir = _paths.novel_output_dir(config, request.novel, target_normalized)
    chapter_files = _find_chapter_files(output_dir)
    sorted_chapters = sorted(chapter_files.items())

    novel_root = _paths.novel_root_dir(config, request.novel)
    metadata = load_metadata(novel_root / "metadata.json")
    book_title = request.title or resolve_book_title(metadata, target_normalized, request.novel)
    book_author = request.author if request.author != "AI Translator" else resolve_book_author(metadata, request.author)

    cover_image = resolve_cover_image(metadata, novel_root)
    illustrations_dir = novel_root / "illustrations"

    package_dir = request.output_dir or _paths.novel_artifact_dir(config, request.novel)
    package_dir.mkdir(parents=True, exist_ok=True)
    package_stem = package_file_stem(request.novel, target_normalized)

    loaded_chapters: list[tuple[str, list[str]]] = []
    for num, path in sorted_chapters:
        _emit(
            progress_callback,
            ProgressEvent(
                kind="chapter_loaded",
                novel=request.novel,
                chapter=num,
                message=f"Reading chapter {num}",
            ),
        )
        title, paragraphs = parse_chapter_file(path)
        loaded_chapters.append((title, paragraphs))

    artifacts: list[ArtifactInfo] = []
    try:
        _check_cancel(cancel_event)
        _emit(
            progress_callback,
            ProgressEvent(
                kind="phase",
                novel=request.novel,
                message="Packaging EPUB",
                extra={"format": "epub"},
            ),
        )
        epub_path = package_dir / f"{package_stem}.epub"
        illustrations = resolve_chapter_images(illustrations_dir, loaded_chapters)
        builder = EPUBBuilder(
            title=book_title,
            author=book_author,
            language=target_normalized,
            cover_image=cover_image,
            illustrations=illustrations,
        )
        for title, paragraphs in loaded_chapters:
            builder.add_chapter(title, paragraphs)
        builder.write(epub_path)
        artifacts.append(
            ArtifactInfo(
                format="epub",
                path=str(epub_path),
                size=epub_path.stat().st_size,
            )
        )
    except OperationCancelledError:
        raise
    except OSError as error:
        raise PersistenceError(str(error)) from error
    finally:
        cleanup_cover_image(cover_image)

    _emit(
        progress_callback,
        ProgressEvent(
            kind="completed",
            novel=request.novel,
            message="Packaging complete",
        ),
    )

    return PackResult(
        novel=request.novel,
        title=book_title,
        author=book_author,
        artifacts=artifacts,
        started_at=started_at,
        finished_at=time.time(),
    )
