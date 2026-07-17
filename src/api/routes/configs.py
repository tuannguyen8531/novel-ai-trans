"""Per-novel crawler config endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from src.api.dependencies import AuthenticatedPrincipal, JobManagerDependency, get_state
from src.api.schemas import (
    ConfigGenerateRequest,
    ConfigSaveRequest,
    ConfigSummary,
    ConfigValidateRequest,
    DraftDetail,
    DraftSummary,
    JobStartResponse,
)
from src.application import config as app_config
from src.application.crawl import configs as config_workflow
from src.application.crawl import generator as generator_workflow
from src.application.crawl import validator as validator_workflow
from src.application.novel import identity

router = APIRouter(tags=["configs"])


def _translated_root() -> Path:
    return identity.resolve_root(app_config.get_config().translated_dir)


@router.get("/configs", response_model=list[ConfigSummary])
def get_configs(_: AuthenticatedPrincipal) -> list[ConfigSummary]:
    return [ConfigSummary(**vars(record), updated_at=None) for record in config_workflow.list_configs(_translated_root())]


@router.get("/configs/{name}")
def get_config_file(
    name: str,
    _: AuthenticatedPrincipal,
) -> dict[str, Any]:
    return config_workflow.load_config(_translated_root(), name)


@router.put("/configs/{name}")
def save_config(
    name: str,
    payload: ConfigSaveRequest,
    request: Request,
    _: AuthenticatedPrincipal,
) -> dict[str, Any]:
    config_workflow.save_config(
        _translated_root(),
        get_state(request).drafts_dir,
        name,
        payload.config,
        payload.draft_id,
    )
    return {"name": name, "saved": True}


@router.post("/configs/generate", response_model=JobStartResponse, status_code=202)
async def post_generate_config(
    payload: ConfigGenerateRequest,
    request: Request,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    snapshot = app_config.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        from src.api.events import build_progress_emitter as _bpe

        progress_cb = _bpe(job, emit)
        result: generator_workflow.ConfigGenerationResult = generator_workflow.generate_config(
            url=payload.url,
            name=payload.name,
            provider=payload.provider,
            use_browser=payload.browser or False,
            headed=payload.headed or False,
            no_cache=payload.no_cache or False,
            ignore_sample=payload.ignore_sample or False,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
            drafts_dir=get_state().drafts_dir,
        )
        # Update the job's novel label to the suggested config name so the
        # Jobs list and the JobMonitor don't show "—".
        job.novel = result.suggested_name
        emit_dict = {
            "draft_id": result.draft_id,
            "name": result.suggested_name,
            "config": result.config,
            "metadata": result.metadata,
        }
        return emit_dict

    job = jobs.submit(
        kind="generate",
        novel=None,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.post("/configs/{name}/validate", response_model=JobStartResponse, status_code=202)
async def post_validate_config(
    name: str,
    payload: ConfigValidateRequest,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    snapshot = app_config.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        from src.api.events import build_progress_emitter as _bpe

        progress_cb = _bpe(job, emit)
        result: validator_workflow.ConfigValidationResult = validator_workflow.validate_config(
            novel=name,
            use_browser=payload.browser,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )
        return {
            "novel": name,
            "ok": result.ok,
            "issues": [vars(issue) for issue in result.issues],
            "metadata": result.metadata,
        }

    job = jobs.submit(
        kind="validate",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.get("/config-drafts", response_model=list[DraftSummary])
def list_drafts(_: AuthenticatedPrincipal) -> list[DraftSummary]:
    return [
        DraftSummary(
            draft_id=record.draft_id,
            name=record.name,
            created_at=record.created_at,
            expires_at=record.expires_at,
            source_url=record.source_url,
        )
        for record in config_workflow.list_drafts(get_state().drafts_dir)
    ]


@router.get("/config-drafts/{draft_id}", response_model=DraftDetail)
def get_draft(
    draft_id: str,
    _: AuthenticatedPrincipal,
) -> DraftDetail:
    return DraftDetail(**vars(config_workflow.load_draft(get_state().drafts_dir, draft_id)))


@router.delete("/config-drafts/{draft_id}", status_code=204)
def delete_draft(
    draft_id: str,
    _: AuthenticatedPrincipal,
) -> None:
    config_workflow.delete_draft(get_state().drafts_dir, draft_id)
    return None
