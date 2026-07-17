"""Local and remote cover acquisition and cleanup."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def resolve_cover_image(metadata: dict[str, Any], novel_root: Path | None = None) -> Path | None:
    """Resolve a local cover or download a remote cover to a temporary file."""
    illustration_url = metadata.get("illustration_url", "")
    if not illustration_url:
        return None

    if not illustration_url.startswith(("http://", "https://")):
        local_path = Path(illustration_url)
        if local_path.is_absolute() and local_path.exists():
            return local_path
        if novel_root is not None:
            path_in_root = novel_root / local_path
            if path_in_root.exists():
                return path_in_root
            path_in_illustrations = novel_root / "illustrations" / local_path
            if path_in_illustrations.exists():
                return path_in_illustrations
        return local_path if local_path.exists() else None

    try:
        request = Request(illustration_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "")
            if "png" in content_type:
                suffix = ".png"
            elif "webp" in content_type:
                suffix = ".webp"
            else:
                suffix = ".jpg"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="novel_cover_") as temporary:
                temporary.write(response.read())
                return Path(temporary.name)
    except URLError, OSError:
        return None


def cleanup_cover_image(cover_image: Path | None) -> None:
    """Remove a temporary cover using the workflow's existing path rule."""
    if cover_image is not None and str(cover_image).startswith(tempfile.gettempdir()):
        cover_image.unlink(missing_ok=True)


__all__ = ["cleanup_cover_image", "resolve_cover_image"]
