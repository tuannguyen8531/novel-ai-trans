"""FastAPI application factory and lifespan management."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from src.api.auth import is_remote_mode, require_secret_key_configured
from src.api.jobs import JobConflictError, JobManager

_logger = logging.getLogger(__name__)


@dataclass
class AppState:
    job_manager: JobManager
    history_root: Path
    dist_dir: Path
    drafts_dir: Path
    config_drafts_dir: Path
    jobs_dir: Path
    shutdown_event: asyncio.Event
    max_upload_bytes: int = 100 * 1024 * 1024


@asynccontextmanager
async def _lifespan(app: FastAPI):
    state: AppState = app.state.app_state
    require_secret_key_configured()
    state.shutdown_event.clear()
    try:
        yield
    finally:
        state.shutdown_event.set()
        await asyncio.to_thread(state.job_manager.shutdown)


def _build_cors_origins() -> list[str]:
    origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    if is_remote_mode() and "*" in origins:
        raise RuntimeError("CORS_ORIGINS must not contain '*' in remote mode.")
    return origins


def create_app(
    *,
    dist_dir: Path | None = None,
    drafts_dir: Path | None = None,
    history_root: Path | None = None,
    jobs_dir: Path | None = None,
    max_upload_bytes: int = 100 * 1024 * 1024,
) -> FastAPI:
    """Construct the FastAPI application."""
    from src.api.routes import register_routes

    base = Path(__file__).resolve().parent.parent.parent
    _ = base / "runtime"
    jobs_dir = jobs_dir or base / "runtime" / "jobs"
    from src.api.services.job_store import JobStore

    job_store = JobStore(jobs_dir)
    # Drop expired job files so the on-disk history mirrors the in-memory
    # retention window. Run synchronously: it's a few mtime checks at most.
    removed = job_store.cleanup()
    if removed:
        import logging as _logging

        _logging.getLogger(__name__).info("Cleaned up %d expired job file(s)", removed)

    state = AppState(
        job_manager=JobManager(store=job_store),
        history_root=history_root or base / "translated",
        dist_dir=dist_dir or base / "web" / "dist",
        drafts_dir=drafts_dir or base / "runtime" / "config-drafts",
        config_drafts_dir=drafts_dir or base / "runtime" / "config-drafts",
        jobs_dir=jobs_dir,
        shutdown_event=asyncio.Event(),
        max_upload_bytes=max_upload_bytes,
    )
    state.drafts_dir.mkdir(parents=True, exist_ok=True)
    state.config_drafts_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="novel-ai-trans",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.app_state = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_build_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[],
    )

    register_routes(app)

    from src.api.errors import application_error_to_http
    from src.application.errors import ApplicationError

    @app.exception_handler(ApplicationError)
    async def _app_error(_: Request, error: ApplicationError):
        http_exc = application_error_to_http(error)
        return JSONResponse(
            status_code=http_exc.status_code,
            content={"error": http_exc.detail},
        )

    @app.exception_handler(JobConflictError)
    async def _job_conflict(_: Request, error: JobConflictError):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "job_conflict",
                    "message": "Another long-running job is already active.",
                    "details": {"active_job_id": str(error)},
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, error: HTTPException):
        detail = error.detail
        payload = detail if isinstance(detail, dict) and "code" in detail else {"code": "http_error", "message": str(detail)}
        return JSONResponse(status_code=error.status_code, content={"error": payload}, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": {"errors": error.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, error: Exception):  # noqa: ARG001
        _logger.exception("Unhandled API exception")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error.",
                }
            },
        )

    _mount_frontend(app, state)
    return app


def _mount_frontend(app: FastAPI, state: AppState) -> None:
    """Serve the built SPA from ``web/dist`` when available.

    The SPA fallback never shadows ``/api`` or ``/docs`` routes.
    """
    dist = state.dist_dir
    if not dist.exists() or not dist.is_dir():
        _logger.info("web/dist not present; API will run without the SPA bundle.")
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="spa-assets")
    spa_index = dist / "index.html"

    @app.get("/", include_in_schema=False)
    async def _index() -> Any:
        if spa_index.exists():
            return FileResponse(spa_index)
        return JSONResponse(
            {
                "name": "novel-ai-trans API",
                "frontend": "missing",
                "message": "Build the frontend (cd web && npm run build) to enable the GUI.",
            }
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> Any:
        if full_path.startswith(("api", "docs", "openapi.json", "redoc")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not spa_index.exists():
            return JSONResponse(
                {"name": "novel-ai-trans API", "frontend": "missing"},
                status_code=404,
            )
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(spa_index)
