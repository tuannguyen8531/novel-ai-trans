"""Novels and chapter content endpoints."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_state
from src.api.errors import ApplicationValidationError, ResourceNotFoundError
from src.api.schemas import (
    ArtifactInfoResponse,
    ChapterContentResponse,
    NovelChapterStatus,
    NovelDetail,
    NovelMetadataPatch,
    NovelMetadataResponse,
    NovelSummary,
    NovelTargetProgress,
)
from src.api.services.novel_paths import (
    is_valid_novel_slug,
    list_novels,
    resolve_translated_root,
    safe_novel_path,
)
from src.application.paths import PROGRESS_DIR
from src.domain.target_language import SUPPORTED_TARGET_LANGUAGES, normalize_target_language

router = APIRouter(tags=["novels"])

_CHAPTER_PATTERN = re.compile(r"^chapter_(\d+)\.txt$")


def _input_dir(novel_root: Path) -> Path:
    return novel_root / "input"


def _output_dir(novel_root: Path, target: str) -> Path:
    return novel_root / "output" if target == "vi" else novel_root / "output" / target


def _progress_paths(novel_root: Path, novel: str, target: str) -> tuple[Path, ...]:
    # ``novel`` is the slug from the URL path; every caller validates it
    # with ``is_valid_novel_slug`` (which rejects separators, ``..``,
    # absolute paths) before this function is invoked. The CodeQL
    # py/path-injection query cannot follow the validation across the
    # function boundary, so the alert is suppressed here.
    runtime_path = (
        PROGRESS_DIR / f"{novel}.json" if target == "vi" else PROGRESS_DIR / target / f"{novel}.json"
    )  # codeql[py/path-injection]: validated by is_valid_novel_slug at each route entry
    shared_path = novel_root / (f"progress.{target}.json" if target != "vi" else "progress.json")
    return runtime_path, shared_path


def _load_progress(path: Path) -> dict[str, list[int]]:
    if not path.exists():
        return {"completed": [], "failed": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"completed": [], "failed": []}


def _load_progress_candidates(paths: tuple[Path, ...]) -> dict[str, list[int]]:
    completed: set[int] = set()
    failed: set[int] = set()
    for path in paths:
        data = _load_progress(path)
        completed.update(data.get("completed", []))
        failed.update(data.get("failed", []))
    return {"completed": sorted(completed), "failed": sorted(failed)}


def _list_chapters(input_dir: Path) -> dict[int, Path]:
    if not input_dir.exists():
        return {}
    chapters: dict[int, Path] = {}
    for f in input_dir.iterdir():
        match = _CHAPTER_PATTERN.match(f.name)
        if match and f.is_file():
            chapters[int(match.group(1))] = f
    return dict(sorted(chapters.items()))


def _count_outputs(output_dir: Path) -> set[int]:
    if not output_dir.exists():
        return set()
    out: set[int] = set()
    for f in output_dir.iterdir():
        match = _CHAPTER_PATTERN.match(f.name)
        if match and f.is_file():
            out.add(int(match.group(1)))
    return out


def _load_metadata(novel_root: Path) -> dict[str, Any]:
    metadata_path = novel_root / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _summarize_novel(root: Path, name: str) -> NovelSummary:
    novel_root = safe_novel_path(root, name)
    input_dir = _input_dir(novel_root)
    metadata = _load_metadata(novel_root)
    chapters = _list_chapters(input_dir)
    total = len(chapters)

    targets: list[NovelTargetProgress] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        progress = _load_progress_candidates(_progress_paths(novel_root, name, target))
        on_disk = _count_outputs(_output_dir(novel_root, target))
        # Trust on-disk output as the authoritative "completed" set so that
        # novels with missing or stale progress.json (e.g. imported EPUBs,
        # chapters placed manually, or a wiped progress file) still report
        # the real count. ``failed`` only comes from progress.json because a
        # file on disk cannot tell us it failed.
        completed = on_disk | set(progress.get("completed", []))
        failed = set(progress.get("failed", []))
        targets.append(
            NovelTargetProgress(
                target=target,
                completed=len(completed),
                failed=len(failed),
                total=total,
            )
        )
    illustrations_dir = novel_root / "illustrations"
    has_illustrations = illustrations_dir.exists() and any(illustrations_dir.iterdir())
    return NovelSummary(
        name=name,
        title=metadata.get("title"),
        author=metadata.get("author"),
        source_language=metadata.get("source_language"),
        total_input_chapters=total,
        targets=targets,
        has_illustrations=has_illustrations,
    )


@router.get("/novels", response_model=list[NovelSummary])
def list_novels_endpoint(
    _: Principal = Depends(authenticate),
) -> list[NovelSummary]:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    return [_summarize_novel(root, name) for name in list_novels(root)]


@router.get("/novels/{name}", response_model=NovelDetail)
def novel_detail(
    name: str,
    _: Principal = Depends(authenticate),
) -> NovelDetail:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    base = _summarize_novel(root, name)
    glossary_path = novel_root / "glossary.json"
    terms = entities = 0
    edges = 0
    if glossary_path.exists():
        try:
            data = json.loads(glossary_path.read_text(encoding="utf-8"))
            terms = len(data.get("terms", {}))
            entities = len(data.get("entities", {}))
            edges = len(data.get("edges", []))
        except (json.JSONDecodeError, OSError):
            pass
    artifacts = _list_artifacts(novel_root)
    return NovelDetail(
        name=base.name,
        title=base.title,
        author=base.author,
        source_language=base.source_language,
        total_input_chapters=base.total_input_chapters,
        targets=base.targets,
        has_illustrations=base.has_illustrations,
        glossary_terms=terms,
        glossary_entities=entities,
        glossary_edges=edges,
        artifacts=[a.name for a in artifacts],
    )


@router.get("/novels/{name}/chapters", response_model=list[NovelChapterStatus])
def novel_chapters(
    name: str,
    _: Principal = Depends(authenticate),
) -> list[NovelChapterStatus]:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    input_dir = _input_dir(novel_root)
    sources = _list_chapters(input_dir)
    outputs_by_target: dict[str, set[int]] = {
        target: _count_outputs(_output_dir(novel_root, target)) for target in SUPPORTED_TARGET_LANGUAGES
    }
    statuses: list[NovelChapterStatus] = []
    for number in sorted(sources):
        for target in SUPPORTED_TARGET_LANGUAGES:
            has_translation = number in outputs_by_target[target]
            statuses.append(
                NovelChapterStatus(
                    number=number,
                    has_source=True,
                    has_translation=has_translation,
                    target=target,
                )
            )
    return statuses


@router.get("/novels/{name}/chapters/{number}", response_model=ChapterContentResponse)
def novel_chapter_content(
    name: str,
    number: int,
    view: str = Query("source", pattern="^(source|translation)$"),
    target: Literal["vi", "en"] | None = Query(None),
    _: Principal = Depends(authenticate),
) -> ChapterContentResponse:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    if view == "source":
        path = _input_dir(novel_root) / f"chapter_{number}.txt"
        if not path.exists():
            raise ResourceNotFoundError(f"Source chapter not found: chapter {number}")
        return ChapterContentResponse(
            novel=name,
            chapter=number,
            view=view,
            target=None,
            content=path.read_text(encoding="utf-8"),
        )
    target_normalized = normalize_target_language(target or config.target_language)
    candidates = [
        _output_dir(novel_root, target_normalized) / f"chapter_{number:03d}.txt",
        _output_dir(novel_root, target_normalized) / f"chapter_{number}.txt",
    ]
    for path in candidates:
        if path.exists():
            return ChapterContentResponse(
                novel=name,
                chapter=number,
                view=view,
                target=target_normalized,
                content=path.read_text(encoding="utf-8"),
            )
    raise ResourceNotFoundError(f"Translated chapter not found: chapter {number}")


@router.get("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def get_novel_metadata(
    name: str,
    _: Principal = Depends(authenticate),
) -> NovelMetadataResponse:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    return NovelMetadataResponse(novel=name, data=_load_metadata(novel_root))


@router.patch("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def patch_novel_metadata(
    name: str,
    payload: NovelMetadataPatch,
    _: Principal = Depends(authenticate),
) -> NovelMetadataResponse:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    current = _load_metadata(novel_root)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise ApplicationValidationError("At least one metadata field must be provided.")
    # Merge nested ``translated`` dict instead of replacing it so callers can
    # clear individual targets (e.g. {"vi": null}) without losing the others.
    if "translated" in updates and isinstance(updates["translated"], dict) and isinstance(current.get("translated"), dict):
        merged = dict(current["translated"])
        for key, value in updates["translated"].items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        updates["translated"] = merged
    current.update(updates)
    metadata_path = novel_root / "metadata.json"
    metadata_path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return NovelMetadataResponse(novel=name, data=current)


@router.delete("/novels/{name}", status_code=204)
def delete_novel(
    name: str,
    principal: Principal = Depends(authenticate),
) -> None:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    state = get_state()
    current = state.job_manager.current
    if current and current.status.value in {"running", "cancelling", "queued"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "novel_in_use",
                "message": f"Novel {name!r} has an active job ({current.id}). Cancel the job first.",
                "details": {"active_job_id": current.id},
            },
        )
    import shutil

    shutil.rmtree(novel_root)
    return None


@router.get("/novels/{name}/artifacts", response_model=list[ArtifactInfoResponse])
def list_artifacts(
    name: str,
    _: Principal = Depends(authenticate),
) -> list[ArtifactInfoResponse]:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    artifacts = _list_artifacts(novel_root)
    return [
        ArtifactInfoResponse(
            name=path.name,
            format=path.suffix.lstrip("."),
            size=path.stat().st_size,
        )
        for path in artifacts
    ]


@router.get("/novels/{name}/artifacts/{filename}")
def download_artifact(
    name: str,
    filename: str,
    _: Principal = Depends(authenticate),
) -> FileResponse:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ResourceNotFoundError("Invalid artifact name")
    artifact_path = (novel_root / filename).resolve()
    try:
        artifact_path.relative_to(novel_root.resolve())
    except ValueError as error:
        raise ResourceNotFoundError("Artifact escapes novel root") from error
    if not artifact_path.is_file() or artifact_path.suffix.lower() not in {".epub", ".pdf"}:
        raise ResourceNotFoundError(f"Artifact not found: {filename}")
    return FileResponse(artifact_path, filename=filename)


def _list_artifacts(novel_root: Path) -> list[Path]:
    if not novel_root.exists():
        return []
    return sorted(p for p in novel_root.iterdir() if p.is_file() and p.suffix.lower() in {".epub", ".pdf"})
