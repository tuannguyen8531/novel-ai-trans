"""Novel EPUB artifact and illustration access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src import paths
from src.application.errors import ResourceNotFoundError
from src.application.novel import require_path
from src.services import chapters as chapter_service

ARTIFACT_SUFFIXES = frozenset({".epub"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})


@dataclass(frozen=True)
class Artifact:
    name: str
    format: str
    size: int
    target_language: str
    created_at: datetime
    chapter_count: int


def resolve_artifact_path(novel_root: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ResourceNotFoundError("Invalid artifact name")
    artifact_path = (paths.novel_artifact_dir_from_root(novel_root) / filename).resolve()
    if not artifact_path.is_file():
        artifact_path = (novel_root / filename).resolve()
    try:
        artifact_path.relative_to(novel_root.resolve())
    except ValueError as error:
        raise ResourceNotFoundError("Artifact escapes novel root") from error
    if not artifact_path.is_file() or artifact_path.suffix.lower() not in ARTIFACT_SUFFIXES:
        raise ResourceNotFoundError(f"Artifact not found: {filename}")
    return artifact_path


def list_artifact_paths(novel_root: Path) -> list[Path]:
    if not novel_root.exists():
        return []
    seen: set[str] = set()
    artifacts: list[Path] = []
    artifact_dir = paths.novel_artifact_dir_from_root(novel_root)
    if artifact_dir.is_dir():
        for artifact_path in artifact_dir.iterdir():
            if artifact_path.is_file() and artifact_path.suffix.lower() in ARTIFACT_SUFFIXES:
                artifacts.append(artifact_path)
                seen.add(artifact_path.name)
    for artifact_path in novel_root.iterdir():
        if artifact_path.is_file() and artifact_path.suffix.lower() in ARTIFACT_SUFFIXES and artifact_path.name not in seen:
            artifacts.append(artifact_path)
    return sorted(artifacts, key=lambda artifact_path: artifact_path.name)


def _artifact_target(artifact_path: Path) -> str:
    parts = artifact_path.stem.rsplit(".", 1)
    return parts[1] if len(parts) == 2 else "vi"


def list_artifacts(root: Path, name: str) -> list[Artifact]:
    novel_root = require_path(root, name)
    result: list[Artifact] = []
    for artifact_path in list_artifact_paths(novel_root):
        target = _artifact_target(artifact_path)
        stat = artifact_path.stat()
        result.append(
            Artifact(
                name=artifact_path.name,
                format=artifact_path.suffix.lstrip("."),
                size=stat.st_size,
                target_language=target,
                created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),  # noqa: UP017
                chapter_count=len(chapter_service.numbers(paths.novel_output_dir_from_root(novel_root, target))),
            )
        )
    return result


def artifact(root: Path, name: str, filename: str) -> Path:
    return resolve_artifact_path(require_path(root, name), filename)


def delete_artifact(root: Path, name: str, filename: str) -> None:
    artifact(root, name, filename).unlink()


def illustration(root: Path, name: str, filename: str) -> Path:
    novel_root = require_path(root, name)
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ResourceNotFoundError("Invalid illustration filename")
    illustration_dir = novel_root / "illustrations"
    illustration_path = (illustration_dir / filename).resolve()
    try:
        illustration_path.relative_to(illustration_dir.resolve())
    except ValueError as error:
        raise ResourceNotFoundError("Illustration escapes illustrations directory") from error
    if not illustration_path.is_file() or illustration_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ResourceNotFoundError(f"Illustration not found: {filename}")
    return illustration_path


__all__ = [
    "Artifact",
    "artifact",
    "delete_artifact",
    "illustration",
    "list_artifact_paths",
    "list_artifacts",
    "resolve_artifact_path",
]
