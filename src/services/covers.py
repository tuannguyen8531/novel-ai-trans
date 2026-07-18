"""Cover image validation and normalization."""

from __future__ import annotations

import warnings
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from src.paths import resolve_within
from src.utils.files import write_bytes_atomic

MAX_COVER_PIXELS = 40_000_000
MAX_COVER_SIZE = (1600, 2400)
SUPPORTED_COVER_FORMATS = frozenset({"GIF", "JPEG", "PNG", "WEBP"})
_COVER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def normalize_cover(data: bytes) -> bytes:
    """Validate an uploaded raster image and encode it as a metadata-free JPEG."""
    if not data:
        raise ValueError("The uploaded cover image is empty.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in SUPPORTED_COVER_FORMATS:
                    raise ValueError("Cover must be a JPEG, PNG, WebP, or GIF image.")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_COVER_PIXELS:
                    raise ValueError(f"Cover dimensions must not exceed {MAX_COVER_PIXELS:,} pixels.")

                source.seek(0)
                frame = ImageOps.exif_transpose(source)
                frame.load()
                frame.thumbnail(MAX_COVER_SIZE, Image.Resampling.LANCZOS)
                normalized = _flatten_to_rgb(frame)

                output = BytesIO()
                normalized.save(
                    output,
                    format="JPEG",
                    quality=85,
                    optimize=True,
                    progressive=True,
                )
                return output.getvalue()
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Cover image dimensions are too large.") from error
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("The uploaded file is not a valid supported image.") from error


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def write_cover(novel_root: Path, data: bytes) -> tuple[Path, bytes | None]:
    """Atomically replace the canonical cover and return rollback data."""
    target = novel_root / "cover.jpg"
    previous = target.read_bytes() if target.is_file() and not target.is_symlink() else None
    write_bytes_atomic(target, data)
    return target, previous


def restore_cover(target: Path, previous: bytes | None) -> None:
    """Best-effort rollback for a failed metadata update."""
    with suppress(OSError):
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            write_bytes_atomic(target, previous)


def remove_superseded_covers(novel_root: Path, target: Path) -> None:
    """Remove managed ``cover.*`` variants without following escaping symlinks."""
    for suffix in _COVER_SUFFIXES:
        for parts in ((f"cover{suffix}",), ("illustrations", f"cover{suffix}")):
            try:
                candidate = resolve_within(novel_root, *parts)
            except ValueError:
                continue
            if candidate != target and candidate.is_file():
                candidate.unlink()


__all__ = [
    "MAX_COVER_PIXELS",
    "MAX_COVER_SIZE",
    "SUPPORTED_COVER_FORMATS",
    "normalize_cover",
    "remove_superseded_covers",
    "restore_cover",
    "write_cover",
]
