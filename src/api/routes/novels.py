"""Novels and chapter content endpoints."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_state
from src.api.errors import ApplicationValidationError, ResourceNotFoundError
from src.api.schemas import (
    ArtifactInfoResponse,
    ChapterContentPayload,
    ChapterContentResponse,
    CreateNovelPayload,
    NovelChapterStatus,
    NovelDetail,
    NovelMetadataPatch,
    NovelMetadataResponse,
    NovelRulesPayload,
    NovelSummary,
    NovelTargetProgress,
)
from src.api.services.novel_paths import (
    is_valid_novel_slug,
    list_novels,
    resolve_translated_root,
    safe_novel_path,
)
from src.application import paths as _paths
from src.application.paths import PROGRESS_DIR
from src.domain.target_language import SUPPORTED_TARGET_LANGUAGES, normalize_target_language

router = APIRouter(tags=["novels"])

_CHAPTER_PATTERN = re.compile(r"^chapter_(\d+)\.txt$")
_ARTIFACT_SUFFIXES = frozenset({".epub", ".pdf"})
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})


@router.post("/novels", status_code=status.HTTP_201_CREATED)
def create_novel(
    payload: CreateNovelPayload,
    _: Principal = Depends(authenticate),
) -> dict[str, str]:
    if not is_valid_novel_slug(payload.name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid novel name. Only alphanumeric characters, '.', '_', "
                "and '-' are allowed, and it must start with an alphanumeric character."
            ),
        )

    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    novel_root = safe_novel_path(root, payload.name)

    if novel_root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Novel directory '{payload.name}' already exists.",
        )

    try:
        novel_root.mkdir(parents=True, exist_ok=True)
        _paths.novel_input_dir_from_root(novel_root).mkdir(parents=True, exist_ok=True)
        _paths.novel_output_dir_from_root(novel_root, "vi").mkdir(parents=True, exist_ok=True)
        _paths.novel_artifact_dir_from_root(novel_root).mkdir(parents=True, exist_ok=True)

        from src.services.glossary import normalize_source_language

        metadata = {
            "title": payload.title or None,
            "author": payload.author or None,
            "source_language": normalize_source_language(payload.source_language) or None,
            "translated": {"en": None, "vi": None},
            "source_url": None,
            "illustration_url": payload.illustration_url or None,
            "site_name": None,
        }
        (novel_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as error:
        import shutil

        shutil.rmtree(novel_root, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to create novel: {error}") from error

    return {"name": payload.name, "message": "Novel created successfully."}


def _progress_paths(novel_root: Path, novel: str, target: str) -> tuple[Path, ...]:
    # ``novel`` is the slug from the URL path; every caller validates it
    # with ``is_valid_novel_slug`` (which rejects separators, ``..``,
    # absolute paths) before this function is invoked. The CodeQL
    # py/path-injection query cannot follow the validation across the
    # function boundary, so the alert is suppressed here.
    runtime_path = _paths.translation_progress_path_for_target(
        novel,
        target,
        progress_root=PROGRESS_DIR,
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
    input_dir = _paths.novel_input_dir_from_root(novel_root)
    metadata = _load_metadata(novel_root)
    chapters = _list_chapters(input_dir)
    total = len(chapters)

    targets: list[NovelTargetProgress] = []
    for target in SUPPORTED_TARGET_LANGUAGES:
        progress = _load_progress_candidates(_progress_paths(novel_root, name, target))
        on_disk = _count_outputs(_paths.novel_output_dir_from_root(novel_root, target))
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


def _get_chapter_title_on_fly(file_path: Path, fallback: str, keep_cjk: bool = True) -> str:
    if not file_path.exists():
        return fallback
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = []
            for line in f:
                stripped = line.strip()
                if stripped.startswith("\ufeff"):
                    stripped = stripped.lstrip("\ufeff")
                if stripped:
                    lines.append(stripped)
                    if len(lines) >= 5:
                        break
        if not lines:
            return fallback
        header_lines = []
        for idx, line in enumerate(lines[:5]):
            if line.startswith("Chương ") or "Chương" in line or line.lower().startswith("chapter"):
                header_lines.append((idx, line))
            else:
                break
        title = header_lines[-1][1] if header_lines else lines[0]
        if not title:
            return fallback
        replacements = {
            "『": '"',
            "』": '"',
            "「": '"',
            "」": '"',
            "【": "[",
            "】": "]",
            "〖": "[",
            "〗": "]",
            "—": "-",
            "–": "-",
            "﹏": "~",
        }
        for orig, rep in replacements.items():
            title = title.replace(orig, rep)
        if not keep_cjk:
            cjk_pattern = re.compile(
                r"[\u4e00-\u9fff"
                r"\u3040-\u309f"
                r"\u30a0-\u30ff"
                r"\uac00-\ud7af"
                r"\u1100-\u11ff"
                r"\u3130-\u318f"
                r"\ufe30-\ufe4f"
                r"]"
            )
            title = cjk_pattern.sub("", title)
        title = re.sub(r" +", " ", title)
        return title.strip()
    except Exception:
        return fallback


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
    input_dir = _paths.novel_input_dir_from_root(novel_root)
    sources = _list_chapters(input_dir)
    outputs_by_target: dict[str, set[int]] = {
        target: _count_outputs(_paths.novel_output_dir_from_root(novel_root, target)) for target in SUPPORTED_TARGET_LANGUAGES
    }
    statuses: list[NovelChapterStatus] = []
    for number in sorted(sources):
        source_path = input_dir / f"chapter_{number}.txt"
        source_title = _get_chapter_title_on_fly(source_path, f"Chapter {number}")
        for target in SUPPORTED_TARGET_LANGUAGES:
            has_translation = number in outputs_by_target[target]
            title = f"Chapter {number}"
            if has_translation:
                out_dir = _paths.novel_output_dir_from_root(novel_root, target)
                out_path = out_dir / f"chapter_{number:03d}.txt"
                title = _get_chapter_title_on_fly(out_path, f"Chapter {number}")
            statuses.append(
                NovelChapterStatus(
                    number=number,
                    has_source=True,
                    has_translation=has_translation,
                    target=target,
                    title=title,
                    source_title=source_title,
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
        path = _paths.novel_input_dir_from_root(novel_root) / f"chapter_{number}.txt"
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
        _paths.novel_output_dir_from_root(novel_root, target_normalized) / f"chapter_{number:03d}.txt",
        _paths.novel_output_dir_from_root(novel_root, target_normalized) / f"chapter_{number}.txt",
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


@router.put("/novels/{name}/chapters/{number}", response_model=ChapterContentResponse)
def put_chapter_content(
    name: str,
    number: int,
    payload: ChapterContentPayload,
    _: Principal = Depends(authenticate),
) -> ChapterContentResponse:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    input_dir = _paths.novel_input_dir_from_root(novel_root)
    input_dir.mkdir(parents=True, exist_ok=True)
    path = input_dir / f"chapter_{number}.txt"
    path.write_text(payload.content, encoding="utf-8")
    return ChapterContentResponse(
        novel=name,
        chapter=number,
        view="source",
        target=None,
        content=payload.content,
    )


@router.delete("/novels/{name}/chapters/{number}", status_code=204)
def delete_chapter(
    name: str,
    number: int,
    _: Principal = Depends(authenticate),
) -> None:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    input_dir = _paths.novel_input_dir_from_root(novel_root)
    path = input_dir / f"chapter_{number}.txt"
    if not path.exists():
        raise ResourceNotFoundError(f"Input chapter not found: chapter {number}")
    path.unlink()
    return None


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
    if "source_language" in payload.model_fields_set:
        from src.services.glossary import normalize_source_language

        updates["source_language"] = normalize_source_language(payload.source_language) or None
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
    results: list[ArtifactInfoResponse] = []
    for path in artifacts:
        stat = path.stat()
        target_language, chapter_count = _parse_artifact_info(novel_root, path)
        results.append(
            ArtifactInfoResponse(
                name=path.name,
                format=path.suffix.lstrip("."),
                size=stat.st_size,
                target_language=target_language,
                created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),  # noqa: UP017
                chapter_count=chapter_count,
            )
        )
    return results


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
    artifact_path = _resolve_artifact_path(novel_root, filename)
    return FileResponse(artifact_path, filename=filename)


@router.delete("/novels/{name}/artifacts/{filename}", status_code=204)
def delete_artifact(
    name: str,
    filename: str,
    _: Principal = Depends(authenticate),
) -> None:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")
    artifact_path = _resolve_artifact_path(novel_root, filename)
    artifact_path.unlink()
    return None


@router.get("/novels/{name}/illustrations/{filename}")
def get_illustration(
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
        raise ResourceNotFoundError("Invalid illustration filename")
    illustrations_dir = novel_root / "illustrations"
    illustration_path = (illustrations_dir / filename).resolve()
    try:
        illustration_path.relative_to(illustrations_dir.resolve())
    except ValueError as error:
        raise ResourceNotFoundError("Illustration escapes illustrations directory") from error
    if not illustration_path.is_file() or illustration_path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise ResourceNotFoundError(f"Illustration not found: {filename}")
    return FileResponse(illustration_path)


def _resolve_artifact_path(novel_root: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ResourceNotFoundError("Invalid artifact name")
    artifact_path = (_paths.novel_artifact_dir_from_root(novel_root) / filename).resolve()
    if not artifact_path.is_file():
        artifact_path = (novel_root / filename).resolve()
    try:
        artifact_path.relative_to(novel_root.resolve())
    except ValueError as error:
        raise ResourceNotFoundError("Artifact escapes novel root") from error
    if not artifact_path.is_file() or artifact_path.suffix.lower() not in _ARTIFACT_SUFFIXES:
        raise ResourceNotFoundError(f"Artifact not found: {filename}")
    return artifact_path


def _list_artifacts(novel_root: Path) -> list[Path]:
    if not novel_root.exists():
        return []
    seen_names = set()
    artifacts: list[Path] = []
    # 1. Scan the new "artifacts" subdirectory first
    artifacts_dir = _paths.novel_artifact_dir_from_root(novel_root)
    if artifacts_dir.is_dir():
        for p in artifacts_dir.iterdir():
            if p.is_file() and p.suffix.lower() in _ARTIFACT_SUFFIXES:
                artifacts.append(p)
                seen_names.add(p.name)
    # 2. Scan the novel root directory for backward compatibility
    for p in novel_root.iterdir():
        if p.is_file() and p.suffix.lower() in _ARTIFACT_SUFFIXES and p.name not in seen_names:
            artifacts.append(p)
    return sorted(artifacts, key=lambda p: p.name)


def _parse_artifact_info(novel_root: Path, artifact_path: Path) -> tuple[str, int]:
    """Parse artifact filename to extract target language and count chapters.

    Artifact filename format: {novel_name}.{target}.{format}
    Example: my-novel.vi.epub -> target=vi, count chapters in output/
    """
    stem = artifact_path.stem
    parts = stem.rsplit(".", 1)
    target_language = parts[1] if len(parts) == 2 else "vi"

    output_dir = _paths.novel_output_dir_from_root(novel_root, target_language)
    chapter_count = len(_count_outputs(output_dir))
    return target_language, chapter_count


@router.get("/novels/{name}/rules")
def get_novel_rules(
    name: str,
    _: Principal = Depends(authenticate),
) -> dict[str, str]:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")

    rules_path = novel_root / "rules.md"
    rules_content = ""
    if rules_path.exists():
        try:
            rules_content = rules_path.read_text(encoding="utf-8")
        except OSError as error:
            raise HTTPException(status_code=500, detail=f"Failed to read rules: {error}") from error
    return {"rules": rules_content}


@router.put("/novels/{name}/rules")
def put_novel_rules(
    name: str,
    payload: NovelRulesPayload,
    _: Principal = Depends(authenticate),
) -> dict[str, str]:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise ResourceNotFoundError(f"Novel not found: {name}")

    rules_path = novel_root / "rules.md"
    try:
        rules_path.write_text(payload.rules, encoding="utf-8")
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Failed to write rules: {error}") from error
    return {"message": "Rules updated successfully."}
