"""Translate endpoint."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter

from src.api.dependencies import AuthenticatedPrincipal, JobManagerDependency
from src.api.jobs import build_progress_emitter
from src.api.schemas import JobStartResponse, TranslationRequestPayload
from src.application import config as app_config
from src.application.novel import catalog, identity
from src.application.novel.localization import localize_metadata
from src.application.progress import ProgressEvent
from src.application.translate import (
    TranslationRequest,
    run_translation,
)
from src.services.notifier import send_run_notification

router = APIRouter(tags=["translate"])


@router.post("/translate", response_model=JobStartResponse, status_code=202)
async def post_translate(
    payload: TranslationRequestPayload,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    snapshot = app_config.get_config().clone(
        llm_provider=payload.provider or None,
        target_language=payload.target_language or None,
    )
    if payload.enable_review is not None:
        snapshot.enable_review = payload.enable_review
    if payload.enable_summary is not None:
        snapshot.enable_summary = payload.enable_summary

    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        started_at = time.time()
        progress_cb = build_progress_emitter(job, emit)
        metadata_result = None
        if payload.translate_metadata is not False:
            progress_cb(
                ProgressEvent(
                    kind="phase",
                    novel=payload.novel,
                    message=f"Translating title and summary to {payload.target_language or snapshot.target_language}...",
                )
            )
            metadata_result = localize_metadata(
                identity.resolve_root(snapshot.translated_dir),
                payload.novel,
                payload.target_language or snapshot.target_language,
                force=payload.force_metadata or False,
                cancel_event=cancel_event,
            )
        request = TranslationRequest(
            novel=payload.novel,
            source_language=payload.source_language or "",
            target_language=payload.target_language or snapshot.target_language,
            provider=payload.provider,
            enable_review=payload.enable_review or False,
            enable_summary=payload.enable_summary or False,
            start_chapter=payload.start_chapter or 0,
            end_chapter=payload.end_chapter or 0,
            force=payload.force or False,
            resume=payload.resume or False,
            failed_only=payload.failed_only or False,
            limit=payload.limit or 0,
            dry_run=False,
        )
        try:
            result = run_translation(
                request,
                progress_callback=progress_cb,
                cancel_event=cancel_event,
            )
        except Exception as error:
            interrupted = cancel_event.is_set()
            send_run_notification(
                status="Success" if interrupted else "Failed",
                task="Translation",
                novel=payload.novel,
                detail="Translation interrupted." if interrupted else (str(error) or type(error).__name__),
                started_at=started_at,
            )
            raise

        if result.cancelled:
            status = "Success"
            detail = "Translation interrupted."
        elif result.failed > 0:
            status = "Failed"
            detail = "Translation finished with errors."
        elif result.skipped:
            status = "Success"
            detail = "No chapters needed translation."
        else:
            status = "Success"
            detail = "Translation finished."
        stats = f"Translated: {result.success}/{result.total}"
        if result.failed > 0:
            stats += f" · Failed: {result.failed}"
        send_run_notification(
            status=status,
            task="Translation",
            novel=result.novel,
            detail=detail,
            stats=stats,
            started_at=result.started_at,
        )
        return {
            "novel": result.novel,
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "chapters_attempted": result.chapters_attempted,
            "failures": result.failures,
            "cancelled": result.cancelled,
            "metadata": asdict(metadata_result) if metadata_result is not None else None,
        }

    job = jobs.submit(
        kind="translate",
        novel=payload.novel,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.get("/novels/{name}/translation-progress")
def translation_progress(
    name: str,
    _: AuthenticatedPrincipal,
    target: Literal["vi", "en"] | None = None,
) -> dict:
    config = app_config.get_config()
    root = identity.resolve_root(config.translated_dir)
    if not identity.is_valid_slug(name):
        from src.api.errors import ResourceNotFoundError

        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    resolved_target: Literal["vi", "en"] = target or ("en" if config.target_language == "en" else "vi")
    saved = catalog.progress(root, name, resolved_target)
    return {
        "novel": name,
        "target": resolved_target,
        "completed": saved["completed"],
        "failed": saved["failed"],
    }
