"""Health and liveness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import HealthPrincipal, JobManagerDependency
from src.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(
    _: HealthPrincipal,
    jobs: JobManagerDependency,
) -> HealthResponse:
    current = jobs.current
    active_id = current.id if current is not None else None
    return HealthResponse(status="ok", active_job_id=active_id)
