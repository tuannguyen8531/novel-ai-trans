"""Novels and chapter content endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from src.api.dependencies import AuthenticatedPrincipal, JobManagerDependency, get_state
from src.api.events import build_progress_emitter
from src.api.schemas import (
    ArtifactInfoResponse,
    ChapterContentPayload,
    ChapterContentResponse,
    ChapterPostCheckResponse,
    ChapterPostCheckReviewPayload,
    ChapterSourceWarningResponse,
    ChapterWarningReviewPayload,
    CreateNovelPayload,
    InsertChapterPayload,
    JobStartResponse,
    MetadataLocalizationPayload,
    NovelChapterStatus,
    NovelDetail,
    NovelMetadataPatch,
    NovelMetadataResponse,
    NovelRulesPayload,
    NovelSummary,
)
from src.application import config as app_config
from src.application import genres as genre_profiles
from src.application.errors import ApplicationValidationError, PersistenceError
from src.application.languages import normalize_source_language
from src.application.novel import artifacts, catalog, chapters, covers, identity, metadata, rules
from src.application.novel.insertion import InsertRequest, insert_chapter
from src.application.novel.localization import localize_metadata

router = APIRouter(tags=["novels"])


@router.get("/genres", response_model=dict[str, list[str]])
def list_genres(
    _: AuthenticatedPrincipal,
) -> dict[str, list[str]]:
    return genre_profiles.genre_catalog()


@router.post("/novels", status_code=status.HTTP_201_CREATED)
def create_novel(
    payload: CreateNovelPayload,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    if not identity.is_valid_slug(payload.name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid novel name. Only alphanumeric characters, '.', '_', "
                "and '-' are allowed, and it must start with an alphanumeric character."
            ),
        )

    root = identity.resolve_root(app_config.get_config().translated_dir)
    if identity.resolve_path(root, payload.name).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Novel directory '{payload.name}' already exists.",
        )
    try:
        catalog.create(
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
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    report_root = get_state().jobs_dir.parent / "reports"
    return [
        NovelSummary(**asdict(summary))
        for summary in catalog.list_summaries(
            root,
            report_root=report_root,
            target_language=config.target_language,
        )
    ]


@router.get("/novels/{name}", response_model=NovelDetail)
def novel_detail(
    name: str,
    _: AuthenticatedPrincipal,
) -> NovelDetail:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    return NovelDetail(
        **asdict(
            catalog.detail(
                root,
                name,
                report_root=get_state().jobs_dir.parent / "reports",
                target_language=config.target_language,
            )
        )
    )


@router.get("/novels/{name}/chapters", response_model=list[NovelChapterStatus])
def novel_chapters(
    name: str,
    _: AuthenticatedPrincipal,
) -> list[NovelChapterStatus]:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return [NovelChapterStatus(**asdict(chapter)) for chapter in chapters.list_chapters(root, name)]


@router.post(
    "/novels/{name}/chapters/insert",
    response_model=JobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def insert_novel_chapter(
    name: str,
    payload: InsertChapterPayload,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    identity.require_path(root, name)
    snapshot = config.clone()
    loop = asyncio.get_running_loop()
    runtime_root = get_state().jobs_dir.parent

    def _run(job, emit, cancel_event):
        result = insert_chapter(
            InsertRequest(
                novel=name,
                number=payload.number,
                content=payload.content,
                operation_id=job.id,
            ),
            progress_callback=build_progress_emitter(job, emit),
            cancel_event=cancel_event,
            progress_root=runtime_root / "progress",
            report_root=runtime_root / "reports",
            rejected_root=runtime_root / "rejected",
            backup_root=runtime_root / "insert-backups",
            lock_dir=runtime_root / "locks",
        )
        return asdict(result)

    job = jobs.submit(
        kind="insert",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.get("/novels/{name}/chapters/{number}", response_model=ChapterContentResponse)
def novel_chapter_content(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
    view: Annotated[Literal["source", "translation"], Query()] = "source",
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterContentResponse:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    content = chapters.read_chapter(
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
    view: Annotated[Literal["source", "translation"], Query()] = "source",
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterContentResponse:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    content = chapters.write_chapter(
        root,
        name,
        number,
        payload.content,
        view=view,
        target=target or config.target_language,
        report_root=get_state().jobs_dir.parent / "reports",
    )
    return ChapterContentResponse(**asdict(content))


@router.get(
    "/novels/{name}/chapters/{number}/warnings/source",
    response_model=ChapterSourceWarningResponse,
)
def get_chapter_source_warning(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterSourceWarningResponse:
    config = app_config.get_config()
    status = chapters.source_warning_status(
        identity.resolve_root(config.translated_dir),
        name,
        number,
        target or config.target_language,
        report_root=get_state().jobs_dir.parent / "reports",
    )
    return ChapterSourceWarningResponse(**asdict(status))


@router.put(
    "/novels/{name}/chapters/{number}/warnings/source",
    response_model=ChapterSourceWarningResponse,
)
def review_chapter_source_warning(
    name: str,
    number: int,
    payload: ChapterWarningReviewPayload,
    _: AuthenticatedPrincipal,
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterSourceWarningResponse:
    config = app_config.get_config()
    status = chapters.review_source_warning(
        identity.resolve_root(config.translated_dir),
        name,
        number,
        target or config.target_language,
        ignored=payload.ignored,
        report_root=get_state().jobs_dir.parent / "reports",
    )
    return ChapterSourceWarningResponse(**asdict(status))


@router.get(
    "/novels/{name}/chapters/{number}/post-check",
    response_model=ChapterPostCheckResponse,
)
def get_chapter_post_check(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterPostCheckResponse:
    config = app_config.get_config()
    runtime_root = get_state().jobs_dir.parent
    review = chapters.chapter_post_check(
        identity.resolve_root(config.translated_dir),
        name,
        number,
        target or config.target_language,
        report_root=runtime_root / "reports",
        rejected_root=runtime_root / "rejected",
    )
    return ChapterPostCheckResponse(**asdict(review))


@router.put(
    "/novels/{name}/chapters/{number}/post-check",
    response_model=ChapterPostCheckResponse,
)
def review_chapter_post_check(
    name: str,
    number: int,
    payload: ChapterPostCheckReviewPayload,
    _: AuthenticatedPrincipal,
    target: Annotated[Literal["vi", "en"] | None, Query()] = None,
) -> ChapterPostCheckResponse:
    config = app_config.get_config()
    runtime_root = get_state().jobs_dir.parent
    review = chapters.review_post_check_item(
        identity.resolve_root(config.translated_dir),
        name,
        number,
        target or config.target_language,
        payload.key,
        ignored=payload.ignored,
        report_root=runtime_root / "reports",
        rejected_root=runtime_root / "rejected",
    )
    return ChapterPostCheckResponse(**asdict(review))


@router.delete("/novels/{name}/chapters/{number}", status_code=204)
def delete_chapter(
    name: str,
    number: int,
    _: AuthenticatedPrincipal,
) -> None:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    chapters.delete_chapter(root, name, number)


@router.get("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def get_novel_metadata(
    name: str,
    _: AuthenticatedPrincipal,
) -> NovelMetadataResponse:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return NovelMetadataResponse(novel=name, data=metadata.metadata(root, name))


@router.patch("/novels/{name}/metadata", response_model=NovelMetadataResponse)
def patch_novel_metadata(
    name: str,
    payload: NovelMetadataPatch,
    _: AuthenticatedPrincipal,
) -> NovelMetadataResponse:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    current = metadata.metadata(root, name)
    updates = payload.model_dump(exclude_unset=True)
    if "source_language" in payload.model_fields_set:
        updates["source_language"] = normalize_source_language(payload.source_language) or None
    if {"source_language", "genres"}.intersection(payload.model_fields_set):
        source_language = updates.get("source_language", current.get("source_language"))
        selected_genres = updates.get("genres", current.get("genres", []))
        updates["genres"] = genre_profiles.normalize_genres(source_language, selected_genres)
    return NovelMetadataResponse(
        novel=name,
        data=metadata.update_metadata(root, name, updates, localized_origin="manual"),
    )


@router.put("/novels/{name}/cover", response_model=NovelMetadataResponse)
async def put_novel_cover(
    name: str,
    _: AuthenticatedPrincipal,
    file: Annotated[UploadFile, File(...)],
) -> NovelMetadataResponse:
    limit = get_state().max_cover_bytes
    chunks: list[bytes] = []
    received = 0
    try:
        while chunk := await file.read(min(1024 * 1024, limit + 1)):
            received += len(chunk)
            if received > limit:
                raise ApplicationValidationError(f"Cover image must not exceed {limit // (1024 * 1024)} MiB.")
            chunks.append(chunk)
    finally:
        await file.close()

    root = identity.resolve_root(app_config.get_config().translated_dir)
    return NovelMetadataResponse(novel=name, data=covers.save(root, name, b"".join(chunks)))


@router.get("/novels/{name}/cover")
def get_novel_cover(
    name: str,
    _: AuthenticatedPrincipal,
) -> FileResponse:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return FileResponse(covers.cover(root, name))


@router.post(
    "/novels/{name}/metadata/localize",
    response_model=JobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def localize_novel_metadata(
    name: str,
    payload: MetadataLocalizationPayload,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    identity.require_path(root, name)
    snapshot = config.clone(
        llm_provider=payload.provider or None,
        target_language=payload.target_language,
    )
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        result = localize_metadata(
            root,
            name,
            payload.target_language,
            fields=tuple(payload.fields),
            force=payload.force,
            cancel_event=cancel_event,
        )
        return asdict(result)

    job = jobs.submit(
        kind="localize",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.delete("/novels/{name}", status_code=204)
def delete_novel(
    name: str,
    _: AuthenticatedPrincipal,
) -> None:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    identity.require_path(root, name)
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
    catalog.delete(root, name)


@router.get("/novels/{name}/artifacts", response_model=list[ArtifactInfoResponse])
def list_artifacts(
    name: str,
    _: AuthenticatedPrincipal,
) -> list[ArtifactInfoResponse]:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return [ArtifactInfoResponse(**asdict(artifact)) for artifact in artifacts.list_artifacts(root, name)]


@router.get("/novels/{name}/artifacts/{filename}")
def download_artifact(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> FileResponse:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return FileResponse(artifacts.artifact(root, name, filename), filename=filename)


@router.delete("/novels/{name}/artifacts/{filename}", status_code=204)
def delete_artifact(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> None:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    artifacts.delete_artifact(root, name, filename)


@router.get("/novels/{name}/illustrations/{filename}")
def get_illustration(
    name: str,
    filename: str,
    _: AuthenticatedPrincipal,
) -> FileResponse:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    return FileResponse(artifacts.illustration(root, name, filename))


@router.get("/novels/{name}/rules")
def get_novel_rules(
    name: str,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    try:
        return {"rules": rules.rules(root, name)}
    except PersistenceError as error:
        raise HTTPException(status_code=500, detail=error.message) from error


@router.put("/novels/{name}/rules")
def put_novel_rules(
    name: str,
    payload: NovelRulesPayload,
    _: AuthenticatedPrincipal,
) -> dict[str, str]:
    root = identity.resolve_root(app_config.get_config().translated_dir)
    try:
        rules.save_rules(root, name, payload.rules)
    except PersistenceError as error:
        raise HTTPException(status_code=500, detail=error.message) from error
    return {"message": "Rules updated successfully."}
