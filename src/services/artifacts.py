"""Filesystem access for generated EPUB artifacts and illustrations."""

from __future__ import annotations

from pathlib import Path

from src import paths

ARTIFACT_SUFFIXES = frozenset({".epub"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})


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


__all__ = ["delete", "illustration", "list_paths", "resolve"]
