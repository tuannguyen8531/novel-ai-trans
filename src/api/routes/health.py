"""Health and liveness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.auth import Principal, health_authenticate
from src.api.dependencies import get_job_manager
from src.api.jobs import JobManager
from src.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(
    _: Principal = Depends(health_authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> HealthResponse:
    current = jobs.current
    active_id = current.id if current is not None else None
    return HealthResponse(status="ok", active_job_id=active_id)
