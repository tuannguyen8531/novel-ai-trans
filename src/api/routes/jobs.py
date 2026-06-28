"""Job listing, retrieval, cancellation, and SSE event stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager
from src.api.jobs import Job, JobManager, JobNotFoundError, JobStatus
from src.api.schemas import JobErrorModel, JobListResponse, JobModel

router = APIRouter(tags=["jobs"])


def _serialize_job(job: Job) -> JobModel:
    error = (
        JobErrorModel(
            code=job.error.code,
            message=job.error.message,
            details=job.error.details,
        )
        if job.error
        else None
    )
    return JobModel(
        id=job.id,
        kind=job.kind,
        novel=job.novel,
        status=job.status.value,  # type: ignore[arg-type]
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        progress=job.progress,
        result=job.result,
        error=error,
        logs=list(job.logs),
    )


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobListResponse:
    current = jobs.current
    return JobListResponse(
        current=_serialize_job(current) if current else None,
        history=[_serialize_job(job) for job in jobs.list_history()],
    )


@router.get("/jobs/{job_id}", response_model=JobModel)
def get_job(
    job_id: str,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobModel:
    try:
        return _serialize_job(jobs.get(job_id))
    except JobNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Job not found: {job_id}"},
        ) from error


@router.post("/jobs/{job_id}/cancel", response_model=JobModel)
def cancel_job(
    job_id: str,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobModel:
    try:
        job = jobs.request_cancel(job_id)
    except JobNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Job not found: {job_id}"},
        ) from error
    return _serialize_job(job)


@router.get("/jobs/{job_id}/events")
async def stream_events(
    job_id: str,
    request: Request,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> EventSourceResponse:
    try:
        job = jobs.get(job_id)
    except JobNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Job not found: {job_id}"},
        ) from error

    loop = asyncio.get_running_loop()
    subscriber = jobs.event_bus.subscribe(loop)
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    async def event_publisher():
        try:
            # Emit current authoritative state snapshot first.
            payload = {
                "id": job.id,
                "kind": job.kind,
                "novel": job.novel,
                "status": job.status.value,
                "progress": dict(job.progress),
                "result": job.result,
                "error": (
                    {
                        "code": job.error.code,
                        "message": job.error.message,
                    }
                    if job.error
                    else None
                ),
            }
            yield {"event": "snapshot", "data": json.dumps(payload, default=str, ensure_ascii=False)}
            if job.status in terminal:
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=15.0)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event is None:
                    break
                # Filter out events from other jobs; the EventBus is global
                # so every subscriber sees every event.
                if event.job_id != job.id:
                    continue
                yield event.sse()
                if event.kind in {s.value for s in terminal}:
                    break
        finally:
            jobs.event_bus.unsubscribe(subscriber)

    return EventSourceResponse(event_publisher(), ping=15, sep="\n")
