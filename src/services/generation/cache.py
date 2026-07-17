"""File-backed HTML cache used during crawler config generation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from bs4 import BeautifulSoup

from src.utils.logging import get_logger


class HtmlCache:
    """Cache raw HTML and discard entries that are clearly unusable."""

    def __init__(self, cache_dir: Path, *, enabled: bool = True) -> None:
        self._dir = cache_dir
        self._enabled = enabled
        if enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16] + ".html"

    def get(self, url: str) -> str | None:
        if not self._enabled:
            return None
        path = self._dir / self._key(url)
        if not path.is_file():
            return None
        html = path.read_text(encoding="utf-8")
        if is_bad_html(html):
            get_logger().warning("Invalidating unusable generated-config HTML cache entry for %s", url)
            self.invalidate(url)
            return None
        return html

    def set(self, url: str, html: str) -> None:
        if self._enabled:
            (self._dir / self._key(url)).write_text(html, encoding="utf-8")

    def invalidate(self, url: str) -> None:
        if not self._enabled:
            return
        path = self._dir / self._key(url)
        if path.exists():
            path.unlink()


def is_bad_html(html: str) -> bool:
    """Return whether HTML is empty, an error page, or a challenge page."""
    if not html or len(html.strip()) < 200:
        return True
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").lower() if soup.title else ""
    body_text = soup.get_text(" ", strip=True)[:300].lower()
    bad_signals = (
        "just a moment",
        "checking your browser",
        "ddos protection",
        "attention required",
        "cloudflare",
        "404",
        "not found",
        "error",
        "access denied",
        "forbidden",
    )
    return any(signal in title or signal in body_text for signal in bad_signals)


__all__ = ["HtmlCache", "is_bad_html"]
