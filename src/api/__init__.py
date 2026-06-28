"""FastAPI app exposing the novel-ai-trans pipeline over HTTP + SSE."""

from __future__ import annotations

__all__ = ["create_app", "app"]


def create_app(*args, **kwargs):  # pragma: no cover - thin wrapper
    from src.api.app_factory import create_app as _create_app

    return _create_app(*args, **kwargs)


def app(*args, **kwargs):  # pragma: no cover - thin wrapper
    return create_app(*args, **kwargs)
