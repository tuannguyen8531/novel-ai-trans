"""Application services for managing novels and their stored content."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src import paths
from src.application.errors import (
    ApplicationValidationError,
    PersistenceError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.domain.language import SUPPORTED_TARGET_LANGUAGES, normalize_source_language, normalize_target_language
from src.paths import DEFAULT_TRANSLATED_ROOT, PROGRESS_DIR
from src.services import chapters

SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ARTIFACT_SUFFIXES = frozenset({".epub", ".pdf"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})


@dataclass(frozen=True)
class Progress:
    target: str
    completed: int
    failed: int
    total: int


@dataclass(frozen=True)
class Summary:
    name: str
    title: str | None
    author: str | None
    source_language: str | None
    total_input_chapters: int
    targets: list[Progress]
    has_illustrations: bool


@dataclass(frozen=True)
class Detail(Summary):
    glossary_terms: int
    glossary_entities: int
    glossary_edges: int
    artifacts: list[str]


@dataclass(frozen=True)
class Chapter:
    number: int
    has_source: bool
    has_translation: bool
    target: str | None
    title: str | None
    source_title: str | None


@dataclass(frozen=True)
class Content:
    novel: str
    chapter: int
    view: str
    target: str | None
    content: str


@dataclass(frozen=True)
class Artifact:
    name: str
    format: str
    size: int
    target_language: str
    created_at: datetime
    chapter_count: int


def is_valid_slug(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    if name in {".", ".."} or "/" in name or "\\" in name or name.startswith("."):
        return False
    return bool(SLUG_PATTERN.match(name))


def resolve_root(translated_dir: str | None) -> Path:
    root = Path(translated_dir) if translated_dir else DEFAULT_TRANSLATED_ROOT
    return root.resolve()


def resolve_path(root: Path, name: str) -> Path:
    if not is_valid_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = (root / name).resolve()
    try:
        novel_root.relative_to(root.resolve())
    except ValueError as error:
        raise ResourceNotFoundError(f"Novel path escapes root: {name}") from error
    return novel_root


def require_path(root: Path, name: str) -> Path:
    novel_root = resolve_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    return novel_root


def list_names(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir() and is_valid_slug(entry.name))


def create(
    root: Path,
    name: str,
    *,
    title: str | None = None,
    author: str | None = None,
    source_language: str | None = None,
    illustration_url: str | None = None,
) -> Path:
    if not is_valid_slug(name):
        raise ApplicationValidationError(f"Invalid novel name: {name!r}")
    novel_root = resolve_path(root, name)
    if novel_root.exists():
        raise ResourceConflictError(f"Novel directory {name!r} already exists.")
    try:
        novel_root.mkdir(parents=True)
        paths.novel_input_dir_from_root(novel_root).mkdir(parents=True)
        paths.novel_output_dir_from_root(novel_root, "vi").mkdir(parents=True)
        paths.novel_artifact_dir_from_root(novel_root).mkdir(parents=True)
        metadata = {
            "title": title or None,
            "author": author or None,
            "source_language": normalize_source_language(source_language) or None,
            "translated": {"en": None, "vi": None},
            "source_url": None,
            "illustration_url": illustration_url or None,
            "summary": None,
            "site_name": None,
        }
        _write_metadata(novel_root, metadata, trailing_newline=False)
    except Exception as error:
        shutil.rmtree(novel_root, ignore_errors=True)
        raise PersistenceError(f"Failed to create novel: {error}") from error
    return novel_root


def _progress_paths(novel_root: Path, name: str, target: str, progress_root: Path) -> tuple[Path, ...]:
    runtime_path = paths.translation_progress_path_for_target(
        name,
        target,
        progress_root=progress_root,
    )  # codeql[py/path-injection]: name validated by resolve_path
    shared_path = novel_root / (f"progress.{target}.json" if target != "vi" else "progress.json")
    return runtime_path, shared_path


def _load_progress(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {"completed": [], "failed": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"completed": [], "failed": []}


def _merge_progress(progress_paths: tuple[Path, ...]) -> dict[str, list[int]]:
    completed: set[int] = set()
    failed: set[int] = set()
    for progress_path in progress_paths:
        data = _load_progress(progress_path)
        completed.update(data.get("completed", []))
        failed.update(data.get("failed", []))
    return {"completed": sorted(completed), "failed": sorted(failed)}


def _load_metadata(novel_root: Path) -> dict[str, Any]:
    metadata_path = novel_root / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_metadata(novel_root: Path, metadata: dict[str, Any], *, trailing_newline: bool = True) -> None:
    content = json.dumps(metadata, ensure_ascii=False, indent=2)
    (novel_root / "metadata.json").write_text(
        content + ("\n" if trailing_newline else ""),
        encoding="utf-8",
    )


def summarize(root: Path, name: str, *, progress_root: Path | None = None) -> Summary:
    novel_root = resolve_path(root, name)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    metadata = _load_metadata(novel_root)
    total = len(chapters.scan(input_dir))
    progress_dir = progress_root or PROGRESS_DIR

    targets: list[Progress] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        progress = _merge_progress(_progress_paths(novel_root, name, target, progress_dir))
        on_disk = chapters.numbers(paths.novel_output_dir_from_root(novel_root, target))
        completed = on_disk | set(progress.get("completed", []))
        failed = set(progress.get("failed", []))
        targets.append(Progress(target=target, completed=len(completed), failed=len(failed), total=total))

    illustrations_dir = novel_root / "illustrations"
    return Summary(
        name=name,
        title=metadata.get("title"),
        author=metadata.get("author"),
        source_language=metadata.get("source_language"),
        total_input_chapters=total,
        targets=targets,
        has_illustrations=illustrations_dir.exists() and any(illustrations_dir.iterdir()),
    )


def list_summaries(root: Path, *, progress_root: Path | None = None) -> list[Summary]:
    return [summarize(root, name, progress_root=progress_root) for name in list_names(root)]


def progress(
    root: Path,
    name: str,
    target: str,
    *,
    progress_root: Path | None = None,
) -> dict[str, list[int]]:
    novel_root = resolve_path(root, name)
    return _merge_progress(
        _progress_paths(
            novel_root,
            name,
            normalize_target_language(target),
            progress_root or PROGRESS_DIR,
        )
    )


def detail(root: Path, name: str, *, progress_root: Path | None = None) -> Detail:
    novel_root = require_path(root, name)
    base = summarize(root, name, progress_root=progress_root)
    terms = entities = edges = 0
    glossary_path = novel_root / "glossary.json"
    if glossary_path.exists():
        try:
            glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
            terms = len(glossary.get("terms", {}))
            entities = len(glossary.get("entities", {}))
            edges = len(glossary.get("edges", []))
        except (json.JSONDecodeError, OSError):
            pass
    return Detail(
        **base.__dict__,
        glossary_terms=terms,
        glossary_entities=entities,
        glossary_edges=edges,
        artifacts=[artifact.name for artifact in list_artifact_paths(novel_root)],
    )


def list_chapters(root: Path, name: str) -> list[Chapter]:
    novel_root = require_path(root, name)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    sources = chapters.scan(input_dir)
    outputs = {
        target: chapters.numbers(paths.novel_output_dir_from_root(novel_root, target)) for target in SUPPORTED_TARGET_LANGUAGES
    }
    result: list[Chapter] = []
    for number in sources:
        source_title = chapters.read_title(input_dir / f"chapter_{number}.txt", f"Chapter {number}")
        for target in SUPPORTED_TARGET_LANGUAGES:
            translated = number in outputs[target]
            title = f"Chapter {number}"
            if translated:
                output_path = paths.novel_output_dir_from_root(novel_root, target) / f"chapter_{number:03d}.txt"
                title = chapters.read_title(output_path, title)
            result.append(
                Chapter(
                    number=number,
                    has_source=True,
                    has_translation=translated,
                    target=target,
                    title=title,
                    source_title=source_title,
                )
            )
    return result


def read_chapter(
    root: Path,
    name: str,
    number: int,
    *,
    view: Literal["source", "translation"],
    target: str | None = None,
) -> Content:
    novel_root = require_path(root, name)
    if view == "source":
        chapter_path = paths.novel_input_dir_from_root(novel_root) / f"chapter_{number}.txt"
        if not chapter_path.exists():
            raise ResourceNotFoundError(f"Source chapter not found: chapter {number}")
        return Content(name, number, view, None, chapter_path.read_text(encoding="utf-8"))

    normalized_target = normalize_target_language(target)
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    for chapter_path in (output_dir / f"chapter_{number:03d}.txt", output_dir / f"chapter_{number}.txt"):
        if chapter_path.exists():
            return Content(name, number, view, normalized_target, chapter_path.read_text(encoding="utf-8"))
    raise ResourceNotFoundError(f"Translated chapter not found: chapter {number}")


def write_chapter(root: Path, name: str, number: int, content: str) -> Content:
    novel_root = require_path(root, name)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / f"chapter_{number}.txt").write_text(content, encoding="utf-8")
    return Content(name, number, "source", None, content)


def delete_chapter(root: Path, name: str, number: int) -> None:
    novel_root = require_path(root, name)
    chapter_path = paths.novel_input_dir_from_root(novel_root) / f"chapter_{number}.txt"
    if not chapter_path.exists():
        raise ResourceNotFoundError(f"Input chapter not found: chapter {number}")
    chapter_path.unlink()


def metadata(root: Path, name: str) -> dict[str, Any]:
    return _load_metadata(require_path(root, name))


def update_metadata(root: Path, name: str, updates: dict[str, Any]) -> dict[str, Any]:
    novel_root = require_path(root, name)
    if not updates:
        raise ApplicationValidationError("At least one metadata field must be provided.")
    current = _load_metadata(novel_root)
    translated = updates.get("translated")
    if isinstance(translated, dict) and isinstance(current.get("translated"), dict):
        merged = dict(current["translated"])
        for key, value in translated.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        updates = {**updates, "translated": merged}
    current.update(updates)
    _write_metadata(novel_root, current)
    return current


def delete(root: Path, name: str) -> None:
    shutil.rmtree(require_path(root, name))


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
                chapter_count=len(chapters.numbers(paths.novel_output_dir_from_root(novel_root, target))),
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


def rules(root: Path, name: str) -> str:
    rules_path = require_path(root, name) / "rules.md"
    if not rules_path.exists():
        return ""
    try:
        return rules_path.read_text(encoding="utf-8")
    except OSError as error:
        raise PersistenceError(f"Failed to read rules: {error}") from error


def save_rules(root: Path, name: str, content: str) -> None:
    rules_path = require_path(root, name) / "rules.md"
    try:
        rules_path.write_text(content, encoding="utf-8")
    except OSError as error:
        raise PersistenceError(f"Failed to write rules: {error}") from error
