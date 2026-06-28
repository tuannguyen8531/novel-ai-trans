"""Pack endpoint."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager
from src.api.jobs import JobManager, build_progress_emitter
from src.api.schemas import JobStartResponse, PackRequestPayload
from src.application.pack import PackRequest, run_pack

router = APIRouter(tags=["pack"])


@router.post("/pack", response_model=JobStartResponse, status_code=202)
async def post_pack(
    payload: PackRequestPayload,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    snapshot = config_context.get_config().clone(
        target_language=payload.target_language,
    )
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        formats = tuple(payload.formats) if payload.formats else ("epub", "pdf")
        request = PackRequest(
            novel=payload.novel,
            target_language=payload.target_language or snapshot.target_language,
            formats=formats,
            title=payload.title or "",
            author=payload.author or "AI Translator",
            dark_mode=payload.dark_mode or False,
        )
        result = run_pack(
            request,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )
        return {
            "novel": result.novel,
            "title": result.title,
            "author": result.author,
            "artifacts": [{"format": a.format, "path": a.path, "size": a.size} for a in result.artifacts],
        }

    job = jobs.submit(
        kind="pack",
        novel=payload.novel,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)
