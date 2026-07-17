"""HTML text and image extraction for EPUB imports."""

from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag

EPUB_IMAGE_PLACEHOLDER = "[[EPUB_IMAGE:{index}]]"


@dataclass(frozen=True)
class EpubSection:
    index: int
    source_path: str
    title: str
    text: str
    image_paths: tuple[str, ...] = ()


class TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    SKIP_TAGS = {"head", "script", "style", "svg"}
    TITLE_TAGS = {"h1", "h2", "h3", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._capture_title: str | None = None
        self._title_parts: list[str] = []
        self.image_sources: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_name = {name.casefold(): value for name, value in attrs if value}
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in {"img", "image"}:
            src = attrs_by_name.get("src") or attrs_by_name.get("href") or attrs_by_name.get("xlink:href")
            if src:
                self.image_sources.append(html.unescape(src))
                self._add_break()
                self._parts.append(EPUB_IMAGE_PLACEHOLDER.format(index=len(self.image_sources)))
                self._add_break()
        if tag in self.BLOCK_TAGS:
            self._add_break()
        if not self.title and tag in self.TITLE_TAGS:
            self._capture_title = tag
            self._title_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if self._capture_title == tag:
            self.title = normalize_whitespace(" ".join(self._title_parts))
            self._capture_title = None
            self._title_parts = []
        if tag in self.BLOCK_TAGS:
            self._add_break()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = normalize_inline_markup(html.unescape(data))
        if not text.strip():
            return
        self._parts.append(text)
        if self._capture_title:
            self._title_parts.append(text)

    def get_text(self) -> str:
        text = "".join(self._parts)
        lines = [normalize_whitespace(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n\n".join(lines)

    def _add_break(self) -> None:
        if self._parts and not self._parts[-1].endswith("\n"):
            self._parts.append("\n")


def read_section(epub: zipfile.ZipFile, source_path: str, index: int) -> EpubSection:
    raw = epub.read(source_path)
    markup = decode_bytes(raw)
    extractor = TextExtractor()
    extractor.feed(markup)
    extractor.close()
    text = extractor.get_text()
    title = extractor.title or Path(source_path).stem
    image_paths: list[str] = []
    for source_index, image_source in enumerate(extractor.image_sources, start=1):
        source_placeholder = EPUB_IMAGE_PLACEHOLDER.format(index=source_index)
        resolved_path = resolve_resource_path(source_path, image_source)
        if not resolved_path or resolved_path not in epub.namelist():
            text = text.replace(source_placeholder, "")
            continue
        image_paths.append(resolved_path)
        target_placeholder = EPUB_IMAGE_PLACEHOLDER.format(index=len(image_paths))
        text = text.replace(source_placeholder, target_placeholder)
    return EpubSection(
        index=index,
        source_path=source_path,
        title=title,
        text=text,
        image_paths=tuple(image_paths),
    )


def resolve_resource_path(section_path: str, resource_ref: str) -> str | None:
    clean_ref = unquote(urldefrag(resource_ref)[0]).strip()
    if not clean_ref:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*:", clean_ref, re.IGNORECASE):
        return None
    if clean_ref.startswith("/"):
        return posixpath.normpath(clean_ref.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(section_path), clean_ref))


def normalize_epub_summary(value: str | None) -> str | None:
    """Normalize plain-text or escaped-HTML descriptions while preserving paragraphs."""
    if not value:
        return None
    decoded = html.unescape(value).strip()
    if re.search(r"<\s*[a-z][^>]*>", decoded, re.IGNORECASE):
        extractor = TextExtractor()
        extractor.feed(decoded)
        extractor.close()
        decoded = extractor.get_text()
    paragraphs = [normalize_whitespace(part) for part in re.split(r"\n\s*\n", decoded) if part.strip()]
    return "\n\n".join(paragraphs) or None


def decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_whitespace(value: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()


def normalize_inline_markup(value: str) -> str:
    return re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)


__all__ = [
    "EPUB_IMAGE_PLACEHOLDER",
    "EpubSection",
    "TextExtractor",
    "decode_bytes",
    "normalize_epub_summary",
    "normalize_inline_markup",
    "normalize_whitespace",
    "read_section",
    "resolve_resource_path",
]
