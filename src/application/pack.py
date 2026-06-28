"""Application-layer packaging workflow.

The pure :func:`run_pack` function is shared by the CLI command and the
FastAPI route. It does not print, call :func:`sys.exit`, or install signal
handlers.

The pack workflow never accepts an unrestricted output filesystem path from
API callers; artifacts always write into the novel root. The CLI keeps its
``--output`` option.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from src.application.config_context import get_config
from src.application.errors import (
    ApplicationValidationError,
    OperationCancelledError,
    PersistenceError,
    ResourceNotFoundError,
)
from src.application.progress import ProgressEvent
from src.config import Config
from src.domain.target_language import normalize_target_language
from src.services.packaging import (  # type: ignore[attr-defined]
    EPUBBuilder,
    NovelPDF,
    clean_text,
    find_serif_fonts,
    image_media_type,
    load_metadata,
    package_file_stem,
    parse_chapter_file,
    resolve_book_author,
    resolve_book_title,
    resolve_cover_image,
    resolve_illustration,
)

# Re-export the building blocks so the existing CLI and tests can keep
# importing them from ``src.cli.pack`` without changing all call sites.
__all__ = [
    "EPUBBuilder",
    "NovelPDF",
    "clean_text",
    "find_serif_fonts",
    "image_media_type",
    "load_metadata",
    "parse_chapter_file",
    "resolve_book_author",
    "resolve_book_title",
    "resolve_cover_image",
    "resolve_illustration",
    "package_file_stem",
    "PackRequest",
    "PackResult",
    "ArtifactInfo",
    "run_pack",
]


@dataclass
class PackRequest:
    novel: str
    target_language: str | None = None
    formats: tuple[str, ...] = ("epub", "pdf")
    title: str = ""
    author: str = "AI Translator"
    dark_mode: bool = False
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
# Path helpers
# ---------------------------------------------------------------------------


def _output_dir(config: Config, novel_name: str, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    if config.translated_dir:
        base = Path(config.translated_dir) / novel_name / "output"
        return base if target == "vi" else base / target
    if target == "vi":
        return Path("runtime/output") / novel_name
    return Path("runtime/output") / target / novel_name


def _default_package_dir(config: Config, novel_name: str) -> Path:
    if config.translated_dir:
        return Path(config.translated_dir) / novel_name
    return Path("runtime/output")


def _novel_root_dir(config: Config, novel_name: str) -> Path:
    if config.translated_dir:
        return Path(config.translated_dir) / novel_name
    return Path("runtime/input") / novel_name


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def _emit(
    callback: Callable[[ProgressEvent], None] | None,
    event: ProgressEvent,
) -> None:
    if callback is not None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001
            pass


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
    """Build EPUB and/or PDF artifacts for *request.novel*."""
    config = get_config()
    started_at = time.time()
    target_language = request.target_language or config.target_language
    target_normalized = normalize_target_language(target_language)

    if not request.formats:
        raise ApplicationValidationError("At least one pack format must be requested.")
    for fmt in request.formats:
        if fmt not in {"epub", "pdf", "all"}:
            raise ApplicationValidationError(f"Unsupported pack format: {fmt}")

    normalized_formats: list[str] = []
    normalized_formats = ["epub", "pdf"] if "all" in request.formats else list(request.formats)

    output_dir = _output_dir(config, request.novel, target_normalized)
    chapter_files = _find_chapter_files(output_dir)
    sorted_chapters = sorted(chapter_files.items())

    metadata = load_metadata(request.novel)
    book_title = request.title or resolve_book_title(metadata, target_normalized, request.novel)
    book_author = request.author if request.author != "AI Translator" else resolve_book_author(metadata, request.author)

    cover_image = resolve_cover_image(metadata)
    illustrations_dir = _novel_root_dir(config, request.novel) / "illustrations"
    downloaded_cover = cover_image is not None and str(cover_image).startswith(tempfile.gettempdir())

    package_dir = request.output_dir or _default_package_dir(config, request.novel)
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
        if "epub" in normalized_formats:
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
            builder = EPUBBuilder(
                title=book_title,
                author=book_author,
                language=target_normalized,
                cover_image=cover_image,
                illustrations_dir=illustrations_dir,
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

        _check_cancel(cancel_event)

        if "pdf" in normalized_formats:
            _check_cancel(cancel_event)
            _emit(
                progress_callback,
                ProgressEvent(
                    kind="phase",
                    novel=request.novel,
                    message="Packaging PDF",
                    extra={"format": "pdf"},
                ),
            )
            pdf_path = package_dir / f"{package_stem}.pdf"
            font_reg, font_bold = find_serif_fonts()
            pdf = NovelPDF(
                title=book_title,
                author=book_author,
                font_reg=font_reg,
                font_bold=font_bold,
                dark_mode=request.dark_mode,
                illustrations_dir=illustrations_dir,
            )
            pdf.create_cover()
            for title, paragraphs in loaded_chapters:
                pdf.add_chapter(title, paragraphs)
            pdf.output(str(pdf_path))
            artifacts.append(
                ArtifactInfo(
                    format="pdf",
                    path=str(pdf_path),
                    size=pdf_path.stat().st_size,
                )
            )
    except OperationCancelledError:
        raise
    except OSError as error:
        raise PersistenceError(str(error)) from error
    finally:
        # Always clean up a downloaded cover (a temp file we created). The
        # ``downloaded_cover`` flag avoids touching user-provided cover paths.
        if downloaded_cover and cover_image is not None:
            cover_image.unlink(missing_ok=True)

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
