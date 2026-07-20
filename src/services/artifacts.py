"""Filesystem access for generated EPUB artifacts and illustrations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src import paths
from src.utils import files

ARTIFACT_SUFFIXES = frozenset({".epub"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArtifactMetadata:
    format: str
    size: int
    target_language: str
    created_at: datetime
    chapter_count: int


def _manifest_data(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        _logger.warning("Ignoring invalid artifact manifest %s: %s", path, error)
        return {}
    return data if isinstance(data, dict) else {}


def _manifest_entries(path: Path) -> dict[str, Any]:
    entries = _manifest_data(path).get("artifacts")
    return dict(entries) if isinstance(entries, dict) else {}


def read_metadata(root: Path, filename: str) -> ArtifactMetadata | None:
    entry = _manifest_entries(paths.novel_artifact_manifest_path_from_root(root)).get(filename)
    if not isinstance(entry, dict):
        return None
    try:
        metadata = ArtifactMetadata(
            format=str(entry["format"]),
            size=int(entry["size"]),
            target_language=str(entry["target_language"]),
            created_at=datetime.fromisoformat(str(entry["created_at"])),
            chapter_count=int(entry["chapter_count"]),
        )
    except KeyError, TypeError, ValueError:
        return None
    if metadata.size < 0 or metadata.chapter_count < 0:
        return None
    return metadata


def record_metadata(
    root: Path,
    filename: str,
    *,
    artifact_format: str,
    size: int,
    target_language: str,
    created_at: datetime,
    chapter_count: int,
) -> None:
    manifest_path = paths.novel_artifact_manifest_path_from_root(root)
    entries = _manifest_entries(manifest_path)
    entries[filename] = {
        "format": artifact_format,
        "target_language": target_language,
        "created_at": created_at.isoformat(),
        "chapter_count": chapter_count,
        "size": size,
    }
    files.write_json_atomic(manifest_path, {"artifacts": entries})


def remove_metadata(root: Path, filename: str) -> None:
    manifest_path = paths.novel_artifact_manifest_path_from_root(root)
    if not manifest_path.is_file():
        return
    entries = _manifest_entries(manifest_path)
    if filename not in entries:
        return
    del entries[filename]
    files.write_json_atomic(manifest_path, {"artifacts": entries})


def resolve(root: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise FileNotFoundError("Invalid artifact name")
    artifact_path = (paths.novel_artifact_dir_from_root(root) / filename).resolve()
    if not artifact_path.is_file():
        artifact_path = (root / filename).resolve()
    try:
        artifact_path.relative_to(root.resolve())
    except ValueError as error:
        raise FileNotFoundError("Artifact escapes novel root") from error
    if not artifact_path.is_file() or artifact_path.suffix.lower() not in ARTIFACT_SUFFIXES:
        raise FileNotFoundError(f"Artifact not found: {filename}")
    return artifact_path


def list_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    seen: set[str] = set()
    artifacts: list[Path] = []
    artifact_dir = paths.novel_artifact_dir_from_root(root)
    if artifact_dir.is_dir():
        for artifact_path in artifact_dir.iterdir():
            if artifact_path.is_file() and artifact_path.suffix.lower() in ARTIFACT_SUFFIXES:
                artifacts.append(artifact_path)
                seen.add(artifact_path.name)
    for artifact_path in root.iterdir():
        if artifact_path.is_file() and artifact_path.suffix.lower() in ARTIFACT_SUFFIXES and artifact_path.name not in seen:
            artifacts.append(artifact_path)
    return sorted(artifacts, key=lambda artifact_path: artifact_path.name)


def delete(root: Path, filename: str) -> None:
    resolve(root, filename).unlink()
    remove_metadata(root, filename)


def illustration(root: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise FileNotFoundError("Invalid illustration filename")
    illustration_dir = root / "illustrations"
    illustration_path = (illustration_dir / filename).resolve()
    try:
        illustration_path.relative_to(illustration_dir.resolve())
    except ValueError as error:
        raise FileNotFoundError("Illustration escapes illustrations directory") from error
    if not illustration_path.is_file() or illustration_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise FileNotFoundError(f"Illustration not found: {filename}")
    return illustration_path


__all__ = [
    "ArtifactMetadata",
    "delete",
    "illustration",
    "list_paths",
    "read_metadata",
    "record_metadata",
    "remove_metadata",
    "resolve",
]
