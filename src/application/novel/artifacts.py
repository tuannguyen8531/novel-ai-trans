"""Novel EPUB artifact and illustration access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src import paths
from src.application.errors import ResourceNotFoundError
from src.application.novel.identity import require_path
from src.services import artifacts as artifact_repository
from src.services import chapters as chapter_service


@dataclass(frozen=True)
class Artifact:
    name: str
    format: str
    size: int
    target_language: str
    created_at: datetime
    chapter_count: int


def resolve_artifact_path(novel_root: Path, filename: str) -> Path:
    try:
        return artifact_repository.resolve(novel_root, filename)
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error


def list_artifact_paths(novel_root: Path) -> list[Path]:
    return artifact_repository.list_paths(novel_root)


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
    try:
        artifact_repository.delete(require_path(root, name), filename)
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error


def illustration(root: Path, name: str, filename: str) -> Path:
    try:
        return artifact_repository.illustration(require_path(root, name), filename)
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error


__all__ = [
    "Artifact",
    "artifact",
    "delete_artifact",
    "illustration",
    "list_artifact_paths",
    "list_artifacts",
    "resolve_artifact_path",
]
