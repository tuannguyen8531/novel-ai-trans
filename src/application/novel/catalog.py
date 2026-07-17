"""Novel catalog queries and lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src import paths
from src.application.errors import ApplicationValidationError, PersistenceError, ResourceConflictError
from src.application.novel.artifacts import list_artifact_paths
from src.application.novel.identity import is_valid_slug, require_path, resolve_path
from src.application.novel.metadata import load as load_metadata
from src.application.novel.metadata import write as write_metadata
from src.domain.language import SUPPORTED_TARGET_LANGUAGES, normalize_source_language, normalize_target_language
from src.paths import PROGRESS_DIR
from src.services import catalog as catalog_repository
from src.services import chapters as chapter_service
from src.services.metadata import localized_value


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


def list_names(root: Path) -> list[str]:
    return [entry.name for entry in catalog_repository.list_directories(root) if is_valid_slug(entry.name)]


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
        catalog_repository.create_directories(novel_root)
        metadata = {
            "title": title or None,
            "author": author or None,
            "source_language": normalize_source_language(source_language) or None,
            "localized": {},
            "localization_meta": {},
            "source_url": None,
            "illustration_url": illustration_url or None,
            "summary": None,
            "site_name": None,
        }
        write_metadata(novel_root, metadata, trailing_newline=False)
    except Exception as error:
        catalog_repository.delete_directory(novel_root, ignore_errors=True)
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
    return catalog_repository.load_progress(path)


def _merge_progress(progress_paths: tuple[Path, ...]) -> dict[str, list[int]]:
    completed: set[int] = set()
    failed: set[int] = set()
    for progress_path in progress_paths:
        data = _load_progress(progress_path)
        completed.update(data.get("completed", []))
        failed.update(data.get("failed", []))
    return {"completed": sorted(completed), "failed": sorted(failed)}


def summarize(
    root: Path,
    name: str,
    *,
    progress_root: Path | None = None,
    target_language: str | None = None,
) -> Summary:
    novel_root = resolve_path(root, name)
    metadata = load_metadata(novel_root)
    total = len(chapter_service.scan(paths.novel_input_dir_from_root(novel_root)))
    progress_dir = progress_root or PROGRESS_DIR

    targets: list[Progress] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        saved = _merge_progress(_progress_paths(novel_root, name, target, progress_dir))
        on_disk = chapter_service.numbers(paths.novel_output_dir_from_root(novel_root, target))
        completed = on_disk | set(saved.get("completed", []))
        failed = set(saved.get("failed", []))
        targets.append(Progress(target=target, completed=len(completed), failed=len(failed), total=total))

    illustrations_dir = novel_root / "illustrations"
    display_title = metadata.get("title")
    if target_language:
        display_title = localized_value(metadata, normalize_target_language(target_language), "title") or None
    return Summary(
        name=name,
        title=display_title,
        author=metadata.get("author"),
        source_language=metadata.get("source_language"),
        total_input_chapters=total,
        targets=targets,
        has_illustrations=catalog_repository.has_files(illustrations_dir),
    )


def list_summaries(
    root: Path,
    *,
    progress_root: Path | None = None,
    target_language: str | None = None,
) -> list[Summary]:
    return [summarize(root, name, progress_root=progress_root, target_language=target_language) for name in list_names(root)]


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


def detail(
    root: Path,
    name: str,
    *,
    progress_root: Path | None = None,
    target_language: str | None = None,
) -> Detail:
    novel_root = require_path(root, name)
    base = summarize(root, name, progress_root=progress_root, target_language=target_language)
    terms, entities, edges = catalog_repository.glossary_counts(novel_root / "glossary.json")
    return Detail(
        **base.__dict__,
        glossary_terms=terms,
        glossary_entities=entities,
        glossary_edges=edges,
        artifacts=[artifact.name for artifact in list_artifact_paths(novel_root)],
    )


def delete(root: Path, name: str) -> None:
    catalog_repository.delete_directory(require_path(root, name))


__all__ = [
    "Detail",
    "Progress",
    "Summary",
    "create",
    "delete",
    "detail",
    "list_names",
    "list_summaries",
    "progress",
    "summarize",
]
