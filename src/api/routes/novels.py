"""Novels and chapter content endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from src.api.dependencies import AuthenticatedPrincipal, get_state
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
)
from src.application import config as app_config
from src.application import novels
from src.application.errors import PersistenceError
from src.domain.language import normalize_source_language

router = APIRouter(tags=["novels"])


@router.post("/novels", status_code=status.HTTP_201_CREATED)
def create_novel(
    payload: CreateNovelPayload,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    if not novels.is_valid_slug(payload.name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid novel name. Only alphanumeric characters, '.', '_', "
                "and '-' are allowed, and it must start with an alphanumeric character."
            ),
        )

    root = novels.resolve_root(app_config.get_config().translated_dir)
    if novels.resolve_path(root, payload.name).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Novel directory '{payload.name}' already exists.",
        )
    try:
        novels.create(
            root,
            payload.name,
            title=payload.title,
            author=payload.author,
            source_language=payload.source_language,
            illustration_url=payload.illustration_url,
        )
    except PersistenceError as error:
        raise HTTPException(status_code=500, detail=error.message) from error
    return {"name": payload.name, "message": "Novel created successfully."}


@router.get("/novels", response_model=list[NovelSummary])
def list_novels_endpoint(
    _: AuthenticatedPrincipal,
) -> list[NovelSummary]:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return [NovelSummary(**asdict(summary)) for summary in novels.list_summaries(root)]


@router.get("/novels/{name}", response_model=NovelDetail)
def novel_detail(
    name: str,
    _: AuthenticatedPrincipal,
) -> NovelDetail:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return NovelDetail(**asdict(novels.detail(root, name)))


@router.get("/novels/{name}/chapters", response_model=list[NovelChapterStatus])
def novel_chapters(
    name: str,
    _: AuthenticatedPrincipal,
) -> list[NovelChapterStatus]:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return [NovelChapterStatus(**asdict(chapter)) for chapter in novels.list_chapters(root, name)]


@router.get("/novels/{name}/chapters/{number}", response_model=ChapterContentResponse)
def novel_chapter_content(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
    view: Annotated[Literal["source", "translation"], Query()] = "source",
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterContentResponse:
    config = app_config.get_config()
    root = novels.resolve_root(config.translated_dir)
    content = novels.read_chapter(
        root,
        name,
        number,
        view=view,
        target=target or config.target_language,
    )
    return ChapterContentResponse(**asdict(content))


@router.put("/novels/{name}/chapters/{number}", response_model=ChapterContentResponse)
def put_chapter_content(
    name: str,
    number: int,
    payload: ChapterContentPayload,
    _: AuthenticatedPrincipal,
) -> ChapterContentResponse:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return ChapterContentResponse(**asdict(novels.write_chapter(root, name, number, payload.content)))


@router.delete("/novels/{name}/chapters/{number}", status_code=204)
def delete_chapter(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
) -> None:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    novels.delete_chapter(root, name, number)


@router.get("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def get_novel_metadata(
    name: str,
    _: AuthenticatedPrincipal,
) -> NovelMetadataResponse:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return NovelMetadataResponse(novel=name, data=novels.metadata(root, name))


@router.patch("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def patch_novel_metadata(
    name: str,
    payload: NovelMetadataPatch,
    _: AuthenticatedPrincipal,
) -> NovelMetadataResponse:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    updates = payload.model_dump(exclude_none=True)
    if "source_language" in payload.model_fields_set:
        updates["source_language"] = normalize_source_language(payload.source_language) or None
    return NovelMetadataResponse(novel=name, data=novels.update_metadata(root, name, updates))


@router.delete("/novels/{name}", status_code=204)
def delete_novel(
    name: str,
    _: AuthenticatedPrincipal,
) -> None:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    novels.require_path(root, name)
    state = get_state()
    active_job = next(
        (
            job
            for job in state.job_manager.list_active()
            if job.novel == name and job.status.value in {"running", "cancelling", "queued"}
        ),
        None,
    )
    if active_job:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "novel_in_use",
                "message": f"Novel {name!r} has an active job ({active_job.id}). Cancel the job first.",
                "details": {"active_job_id": active_job.id},
            },
        )
    novels.delete(root, name)


@router.get("/novels/{name}/artifacts", response_model=list[ArtifactInfoResponse])
def list_artifacts(
    name: str,
    _: AuthenticatedPrincipal,
) -> list[ArtifactInfoResponse]:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return [ArtifactInfoResponse(**asdict(artifact)) for artifact in novels.list_artifacts(root, name)]


@router.get("/novels/{name}/artifacts/{filename}")
def download_artifact(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> FileResponse:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return FileResponse(novels.artifact(root, name, filename), filename=filename)


@router.delete("/novels/{name}/artifacts/{filename}", status_code=204)
def delete_artifact(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> None:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    novels.delete_artifact(root, name, filename)


@router.get("/novels/{name}/illustrations/{filename}")
def get_illustration(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> FileResponse:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    return FileResponse(novels.illustration(root, name, filename))


@router.get("/novels/{name}/rules")
def get_novel_rules(
    name: str,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    try:
        return {"rules": novels.rules(root, name)}
    except PersistenceError as error:
        raise HTTPException(status_code=500, detail=error.message) from error


@router.put("/novels/{name}/rules")
def put_novel_rules(
    name: str,
    payload: NovelRulesPayload,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    root = novels.resolve_root(app_config.get_config().translated_dir)
    try:
        novels.save_rules(root, name, payload.rules)
    except PersistenceError as error:
        raise HTTPException(status_code=500, detail=error.message) from error
    return {"message": "Rules updated successfully."}
