"""FastAPI route registration."""

from __future__ import annotations

from fastapi import FastAPI

from src.api.dependencies import set_current_app


def register_routes(app: FastAPI) -> None:
    set_current_app(app)
    from src.api.routes import (
        configs,
        crawl,
        glossary,
        health,
        jobs,
        novels,
        pack,
        system,
        translate,
    )

    routers = [
        health.router,
        system.router,
        novels.router,
        configs.router,
        crawl.router,
        translate.router,
        pack.router,
        glossary.router,
        jobs.router,
    ]
    for router in routers:
        app.include_router(router, prefix="/api")
