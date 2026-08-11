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
from src.paths import PROGRESS_DIR, REPORT_DIR
from src.services import catalog as catalog_repository
from src.services import chapters as chapter_service
from src.services.metadata import localized_value
from src.services.translation.reports import ReportStore


@dataclass(frozen=True)
class Progress:
    target: str
    completed: int
    failed: int
    warnings: int
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
            "genres": [],
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
    )
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


def _report_directory(name: str, target: str, report_root: Path) -> Path:
    paths.validate_novel_name(name)
    return paths.resolve_within(report_root, target, name)


def summarize(
    root: Path,
    name: str,
    *,
    progress_root: Path | None = None,
    report_root: Path | None = None,
    target_language: str | None = None,
) -> Summary:
    novel_root = resolve_path(root, name)
    metadata = load_metadata(novel_root)
    total = len(chapter_service.scan(paths.novel_input_dir_from_root(novel_root)))
    progress_dir = progress_root or PROGRESS_DIR
    reports_dir = report_root or REPORT_DIR

    targets: list[Progress] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        saved = _merge_progress(_progress_paths(novel_root, name, target, progress_dir))
        on_disk = chapter_service.numbers(paths.novel_output_dir_from_root(novel_root, target))
        completed = on_disk
        failed = set(saved.get("failed", []))
        output_dir = paths.novel_output_dir_from_root(novel_root, target)
        warnings = catalog_repository.load_warning_chapters(
            _report_directory(name, target, reports_dir),
            output_dir,
        )
        targets.append(
            Progress(
                target=target,
                completed=len(completed),
                failed=len(failed),
                warnings=len(warnings),
                total=total,
            )
        )

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
    report_root: Path | None = None,
    target_language: str | None = None,
) -> list[Summary]:
    return [
        summarize(
            root,
            name,
            progress_root=progress_root,
            report_root=report_root,
            target_language=target_language,
        )
        for name in list_names(root)
    ]


def progress(
    root: Path,
    name: str,
    target: str,
    *,
    progress_root: Path | None = None,
    report_root: Path | None = None,
) -> dict[str, list[int]]:
    novel_root = resolve_path(root, name)
    resolved_target = normalize_target_language(target)
    saved = _merge_progress(
        _progress_paths(
            novel_root,
            name,
            resolved_target,
            progress_root or PROGRESS_DIR,
        )
    )
    saved["completed"] = sorted(chapter_service.numbers(paths.novel_output_dir_from_root(novel_root, resolved_target)))
    report_directory = _report_directory(name, resolved_target, report_root or REPORT_DIR)
    output_directory = paths.novel_output_dir_from_root(novel_root, resolved_target)
    saved["warnings"] = catalog_repository.load_warning_chapters(
        report_directory,
        output_directory,
    )
    saved["source_warnings"] = catalog_repository.load_source_warning_chapters(
        report_directory,
        output_directory,
    )
    return saved


def ignore_warnings(
    root: Path,
    name: str,
    target: str,
    *,
    report_root: Path | None = None,
) -> int:
    """Ignore all currently unresolved warnings for one novel target."""
    novel_root = require_path(root, name)
    resolved_target = normalize_target_language(target)
    report_directory = _report_directory(name, resolved_target, report_root or REPORT_DIR)
    output_directory = paths.novel_output_dir_from_root(novel_root, resolved_target)
    report_store = ReportStore()
    ignored_chapters = 0

    for chapter in catalog_repository.load_warning_chapters(report_directory, output_directory):
        report_path = report_directory / f"chapter_{chapter:03d}.json"
        if not report_path.exists():
            report_path = report_directory / f"chapter_{chapter}.json"
        report = report_store.load(report_path)
        issue_codes = [code for code in report.get("manual_post_check_issues", []) if isinstance(code, str)]
        if not issue_codes:
            continue
        try:
            content = chapter_service.read(output_directory, chapter)
        except OSError:
            continue
        report_store.set_issues_ignored(
            report_path,
            issue_codes=issue_codes,
            content=content,
        )
        ignored_chapters += 1
    return ignored_chapters


def detail(
    root: Path,
    name: str,
    *,
    progress_root: Path | None = None,
    report_root: Path | None = None,
    target_language: str | None = None,
) -> Detail:
    novel_root = require_path(root, name)
    base = summarize(
        root,
        name,
        progress_root=progress_root,
        report_root=report_root,
        target_language=target_language,
    )
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
    "ignore_warnings",
    "list_names",
    "list_summaries",
    "progress",
    "summarize",
]
