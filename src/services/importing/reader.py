"""EPUB ZIP, OPF, spine, and metadata reading."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urldefrag
from xml.etree import ElementTree

from src.services.importing.extractor import EpubSection, normalize_epub_summary, normalize_whitespace, read_section

CONTAINER_PATH = "META-INF/container.xml"


class EpubImportError(Exception):
    pass


@dataclass(frozen=True)
class EpubBookMetadata:
    title: str | None
    author: str | None
    description: str | None


@dataclass(frozen=True)
class EpubBook:
    metadata: EpubBookMetadata
    sections: list[EpubSection]


def resolve_epub_path(epub_path: Path) -> Path:
    if epub_path.suffix.lower() != ".epub":
        raise EpubImportError(f"{epub_path} is not an .epub file")
    if not epub_path.is_file():
        raise EpubImportError(f"EPUB file not found: {epub_path}")
    return epub_path


def read_epub_book(epub_path: Path) -> EpubBook:
    try:
        with zipfile.ZipFile(epub_path) as epub:
            opf_path = get_opf_path(epub)
            metadata = read_epub_metadata(epub, opf_path)
            section_paths = get_spine_document_paths(epub, opf_path)
            sections = []
            for path in section_paths:
                section = read_section(epub, path, len(sections) + 1)
                if section.text or section.image_paths:
                    sections.append(section)
    except zipfile.BadZipFile as error:
        raise EpubImportError(f"invalid EPUB zip: {epub_path}") from error
    except KeyError as error:
        raise EpubImportError(f"missing EPUB member: {error}") from error
    except ElementTree.ParseError as error:
        raise EpubImportError(f"invalid EPUB XML: {error}") from error

    if not sections:
        raise EpubImportError(f"no readable text sections found in {epub_path}")
    return EpubBook(metadata=metadata, sections=sections)


def get_opf_path(epub: zipfile.ZipFile) -> str:
    root = ElementTree.fromstring(epub.read(CONTAINER_PATH))
    rootfile = root.find(".//{*}rootfile")
    if rootfile is None:
        raise EpubImportError(f"{CONTAINER_PATH} does not declare an OPF rootfile")
    opf_path = rootfile.attrib.get("full-path")
    if not opf_path:
        raise EpubImportError(f"{CONTAINER_PATH} rootfile is missing full-path")
    return opf_path


def read_epub_metadata(epub: zipfile.ZipFile, opf_path: str) -> EpubBookMetadata:
    opf_root = ElementTree.fromstring(epub.read(opf_path))
    metadata_node = opf_root.find(".//{*}metadata")
    if metadata_node is None:
        return EpubBookMetadata(title=None, author=None, description=None)
    return EpubBookMetadata(
        title=find_child_text(metadata_node, "title"),
        author=find_child_text(metadata_node, "creator"),
        description=normalize_epub_summary(find_child_raw_text(metadata_node, "description")),
    )


def find_child_text(element: ElementTree.Element, local_name: str) -> str | None:
    text = find_child_raw_text(element, local_name)
    return normalize_whitespace(text or "") or None


def find_child_raw_text(element: ElementTree.Element, local_name: str) -> str | None:
    for child in element.iter():
        if child is element:
            continue
        if xml_local_name(child.tag) != local_name:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return None


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def get_spine_document_paths(epub: zipfile.ZipFile, opf_path: str) -> list[str]:
    opf_root = ElementTree.fromstring(epub.read(opf_path))
    manifest = {
        item.attrib["id"]: item.attrib["href"]
        for item in opf_root.findall(".//{*}manifest/{*}item")
        if "id" in item.attrib and "href" in item.attrib
    }

    opf_dir = posixpath.dirname(opf_path)
    paths: list[str] = []
    for itemref in opf_root.findall(".//{*}spine/{*}itemref"):
        idref = itemref.attrib.get("idref")
        href = manifest.get(idref or "")
        if not href:
            continue
        clean_href = unquote(urldefrag(href)[0])
        normalized_path = posixpath.normpath(posixpath.join(opf_dir, clean_href))
        if normalized_path in epub.namelist():
            paths.append(normalized_path)

    if not paths:
        raise EpubImportError("EPUB spine does not contain readable document paths")
    return paths


__all__ = [
    "EpubBook",
    "EpubBookMetadata",
    "EpubImportError",
    "find_child_raw_text",
    "find_child_text",
    "get_opf_path",
    "get_spine_document_paths",
    "read_epub_book",
    "read_epub_metadata",
    "resolve_epub_path",
    "xml_local_name",
]
