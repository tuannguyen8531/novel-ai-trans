"""EPUB illustration resolution and media types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.illustrations import parse_illustration_marker


@dataclass(frozen=True)
class ResolvedImage:
    filename: str
    path: Path
    media_type: str


def resolve_illustration(illustrations_dir: Path | None, filename: str) -> Path | None:
    """Resolve a safe marker filename inside an illustrations directory."""
    if illustrations_dir is None or Path(filename).name != filename:
        return None
    path = illustrations_dir / filename
    return path if path.is_file() else None


def image_media_type(path: Path) -> str:
    """Return the EPUB media type for an illustration file."""
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower(), "application/octet-stream")


def resolve_chapter_images(
    illustrations_dir: Path | None,
    chapters: list[tuple[str, list[str]]],
) -> dict[str, ResolvedImage]:
    """Resolve chapter illustration markers in their first-seen order."""
    resolved: dict[str, ResolvedImage] = {}
    for _, paragraphs in chapters:
        for paragraph in paragraphs:
            filename = parse_illustration_marker(paragraph)
            if filename is None or filename in resolved:
                continue
            path = resolve_illustration(illustrations_dir, filename)
            if path is not None:
                resolved[filename] = ResolvedImage(
                    filename=filename,
                    path=path,
                    media_type=image_media_type(path),
                )
    return resolved


__all__ = ["ResolvedImage", "image_media_type", "resolve_chapter_images", "resolve_illustration"]
