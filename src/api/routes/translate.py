"""Translate endpoint."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager
from src.api.jobs import JobManager, build_progress_emitter
from src.api.schemas import JobStartResponse, TranslationRequestPayload
from src.application.translate import (
    TranslationRequest,
    run_translation,
)

router = APIRouter(tags=["translate"])


@router.post("/translate", response_model=JobStartResponse, status_code=202)
async def post_translate(
    payload: TranslationRequestPayload,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    snapshot = config_context.get_config().clone(
        llm_provider=payload.provider or None,
        target_language=payload.target_language or None,
    )
    if payload.enable_review is not None:
        snapshot.enable_review = payload.enable_review
    if payload.enable_summary is not None:
        snapshot.enable_summary = payload.enable_summary

    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
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
        result = run_translation(
            request,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )
        return {
            "novel": result.novel,
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "chapters_attempted": result.chapters_attempted,
            "failures": result.failures,
            "cancelled": result.cancelled,
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
    target: Literal["vi", "en"] | None = None,
    _: Principal = Depends(authenticate),
) -> dict:
    import json

    from src.api.services.novel_paths import is_valid_novel_slug, resolve_translated_root, safe_novel_path
    from src.application.paths import PROGRESS_DIR

    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        from src.api.errors import ResourceNotFoundError

        raise ResourceNotFoundError(f"Invalid novel name: {name!r}")
    novel_root = safe_novel_path(root, name)
    resolved_target: Literal["vi", "en"] = target or ("en" if config.target_language == "en" else "vi")
    progress_paths = [
        PROGRESS_DIR / f"{name}.json" if resolved_target == "vi" else PROGRESS_DIR / resolved_target / f"{name}.json",
        novel_root / ("progress.json" if resolved_target == "vi" else f"progress.{resolved_target}.json"),
    ]
    completed: set[int] = set()
    failed: set[int] = set()
    for progress_path in progress_paths:
        if not progress_path.exists():
            continue
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        completed.update(data.get("completed", []))
        failed.update(data.get("failed", []))
    return {"novel": name, "target": resolved_target, "completed": sorted(completed), "failed": sorted(failed)}
