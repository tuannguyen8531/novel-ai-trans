"""Local and remote cover acquisition and cleanup."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

_LOCAL_COVER_SUFFIXES = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})


def _local_cover_candidates(novel_root: Path, local_path: Path) -> tuple[Path, ...]:
    """Return allowed locations for a canonical local cover filename."""
    if (
        local_path.is_absolute()
        or local_path.stem.casefold() != "cover"
        or local_path.suffix.casefold() not in _LOCAL_COVER_SUFFIXES
    ):
        return ()
    parts = local_path.parts
    if len(parts) == 1:
        return novel_root / local_path, novel_root / "illustrations" / local_path
    if len(parts) == 2 and parts[0].casefold() == "illustrations":
        return (novel_root / local_path,)
    return ()


def resolve_cover_image(metadata: dict[str, Any], novel_root: Path | None = None) -> Path | None:
    """Resolve a local cover or download a remote cover to a temporary file."""
    illustration_url = metadata.get("illustration_url", "")
    if not illustration_url:
        return None

    if not illustration_url.startswith(("http://", "https://")):
        if novel_root is None:
            return None
        local_path = Path(illustration_url)
        resolved_root = novel_root.resolve()
        for candidate in _local_cover_candidates(resolved_root, local_path):
            resolved_candidate = candidate.resolve()
            if resolved_candidate.is_relative_to(resolved_root) and resolved_candidate.is_file():
                return resolved_candidate
        return None

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


def cleanup_cover_image(cover_image: Path | None, *, novel_root: Path | None = None) -> None:
    """Remove only cover files created by the remote-cover downloader."""
    if cover_image is None:
        return
    resolved_cover = cover_image.resolve()
    if novel_root is not None and resolved_cover.is_relative_to(novel_root.resolve()):
        return
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if resolved_cover.parent == temporary_root and resolved_cover.name.startswith("novel_cover_"):
        resolved_cover.unlink(missing_ok=True)


__all__ = ["cleanup_cover_image", "resolve_cover_image"]
