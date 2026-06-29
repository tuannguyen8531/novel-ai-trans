"""Crawl and EPUB import endpoints."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager, get_state
from src.api.jobs import JobManager, build_progress_emitter
from src.api.schemas import CrawlRequestPayload, JobStartResponse
from src.application.crawl import (
    CrawlRequest,
    ImportRequest,
    import_epub_workflow,
    run_crawl,
)
from src.services.notifier import send_run_notification

router = APIRouter(tags=["crawl"])


@router.post("/crawl", response_model=JobStartResponse, status_code=202)
async def post_crawl(
    payload: CrawlRequestPayload,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    snapshot = config_context.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        started_at = time.time()
        progress_cb = build_progress_emitter(job, emit)
        request = CrawlRequest(
            target=payload.target,
            translated_output=Path(payload.translated_output) if payload.translated_output else None,
            max_chapters=payload.max_chapters,
            fail_fast=payload.fail_fast or False,
            ignore_robots=payload.ignore_robots or False,
            overwrite=payload.overwrite or False,
            use_browser=payload.browser,
            headed=payload.headed or False,
            workers=payload.workers or 1,
        )
        try:
            result = run_crawl(request, progress_callback=progress_cb, cancel_event=cancel_event)
        except Exception as error:
            interrupted = cancel_event.is_set()
            send_run_notification(
                status="Success" if interrupted else "Failed",
                task="Crawl",
                novel=payload.target,
                detail="Crawl interrupted." if interrupted else (str(error) or type(error).__name__),
                started_at=started_at,
            )
            raise

        if result.cancelled:
            status = "Success"
            detail = "Crawl interrupted."
        elif result.failed > 0:
            status = "Failed"
            detail = "Crawl finished with chapter errors."
        else:
            status = "Success"
            detail = "Crawl finished."
        send_run_notification(
            status=status,
            task="Crawl",
            novel=result.novel,
            detail=detail,
            stats=(
                f"New: {result.fetched}/{result.total} · "
                f"Skipped: {result.skipped}/{result.total} · "
                f"Failed: {result.failed}/{result.total}"
            ),
            started_at=result.started_at,
        )
        return {
            "novel": result.novel,
            "title": result.title,
            "fetched": result.fetched,
            "skipped": result.skipped,
            "failed": result.failed,
            "output_dir": result.output_dir,
        }

    job = jobs.submit(
        kind="crawl",
        novel=payload.target,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.post("/import", response_model=JobStartResponse, status_code=202)
async def post_import(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    keep_existing: bool = Form(False),
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    state = get_state()
    snapshot = config_context.get_config().clone()
    loop = asyncio.get_running_loop()
    max_bytes = state.max_upload_bytes

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        total = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "upload_too_large",
                        "message": f"Upload exceeds {max_bytes} bytes.",
                    },
                )
            tmp.write(chunk)

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        try:
            request = ImportRequest(
                epub_path=tmp_path,
                name=name,
                keep_existing=keep_existing,
            )
            result = import_epub_workflow(
                request,
                progress_callback=progress_cb,
                cancel_event=cancel_event,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        return {
            "novel": result.novel,
            "title": result.title,
            "chapters": result.chapters,
            "illustrations": result.illustrations,
            "output_dir": result.output_dir,
            "warnings": result.warnings,
        }

    try:
        job = jobs.submit(
            kind="import",
            novel=name or file.filename,
            snapshot=snapshot,
            loop=loop,
            run=_run,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return JobStartResponse(job_id=job.id)
