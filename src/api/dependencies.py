"""FastAPI dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from src.api.auth import Principal, authenticate
from src.api.jobs import JobManager

if TYPE_CHECKING:
    from src.api.app_factory import AppState

# Module-level reference to the current app, set by ``register_routes`` so
# module-level helpers (e.g. background job runners) can reach the app state
# without threading the ``Request`` object through every layer.
_current_app = None  # type: ignore[var-annotated]


def set_current_app(app) -> None:
    global _current_app
    _current_app = app


def get_state(request: Request | None = None) -> AppState:
    if request is not None:
        return request.app.state.app_state  # type: ignore[no-any-return]
    if _current_app is None:
        raise RuntimeError("App state is not available outside of a request context.")
    return _current_app.state.app_state  # type: ignore[no-any-return]


def get_job_manager(request: Request) -> JobManager:
    return get_state(request).job_manager


def get_principal(principal: Principal = Depends(authenticate)) -> Principal:
    return principal
