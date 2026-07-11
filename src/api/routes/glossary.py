"""Glossary endpoints."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException

from src.api.dependencies import AuthenticatedPrincipal, JobManagerDependency
from src.api.jobs import build_progress_emitter
from src.api.schemas import (
    GlossaryApplyRequest,
    GlossaryCharactersResponse,
    GlossaryCharacterSummary,
    GlossaryCharacterUpdate,
    GlossaryDismissRequest,
    GlossaryRelationshipAdd,
    GlossaryResponse,
    GlossaryRollbackRequest,
    GlossaryTermAdd,
    GlossaryTermsPut,
    GlossaryTermUpdate,
    JobStartResponse,
)
from src.application import config as app_config
from src.application import glossary, novels

router = APIRouter(tags=["glossary"])


def _validate_novel(name: str) -> None:
    config = app_config.get_config()
    root = novels.resolve_root(config.translated_dir)
    if not novels.is_valid_slug(name):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Invalid novel name: {name!r}"},
        )
    novel_root = novels.resolve_path(root, name)
    if not novel_root.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Novel not found: {name}"},
        )


@router.get("/novels/{name}/glossary", response_model=GlossaryResponse)
def get_glossary(
    name: str,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    return GlossaryResponse(novel=name, data=glossary.load_glossary(name))


@router.put("/novels/{name}/glossary/terms", response_model=GlossaryResponse)
def put_terms(
    name: str,
    payload: GlossaryTermsPut,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.save_terms(name, payload.terms)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/terms", response_model=GlossaryResponse)
def post_term(
    name: str,
    payload: GlossaryTermAdd,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.save_term(name, payload.original, payload.translated)
    return GlossaryResponse(novel=name, data=data)


@router.delete("/novels/{name}/glossary/terms/{original}", response_model=GlossaryResponse)
def delete_term(
    name: str,
    original: str,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.remove_term(name, original)
    return GlossaryResponse(novel=name, data=data)


@router.patch("/novels/{name}/glossary/terms/{original}", response_model=GlossaryResponse)
def patch_term(
    name: str,
    original: str,
    payload: GlossaryTermUpdate,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.update_term(
        name,
        original,
        payload.original,
        payload.translated,
        overwrite=payload.overwrite,
    )
    return GlossaryResponse(novel=name, data=data)


@router.get("/novels/{name}/glossary/characters", response_model=GlossaryCharactersResponse)
def list_characters(
    name: str,
    _: AuthenticatedPrincipal,
) -> GlossaryCharactersResponse:
    _validate_novel(name)
    data = glossary.load_glossary(name)
    entities = data.get("entities", {}) if isinstance(data, dict) else {}
    characters = [
        GlossaryCharacterSummary(
            original=original,
            translated_name=info.get("translated_name") if isinstance(info, dict) else None,
            role=info.get("role") if isinstance(info, dict) else None,
            pronoun=info.get("pronoun") if isinstance(info, dict) else None,
        )
        for original, info in sorted(entities.items())
    ]
    return GlossaryCharactersResponse(novel=name, characters=characters)


@router.put("/novels/{name}/glossary/characters/{original}", response_model=GlossaryResponse)
def update_character(
    name: str,
    original: str,
    payload: GlossaryCharacterUpdate,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.save_character(
        name,
        original,
        translated_name=payload.translated_name or "",
        role=payload.role or "",
    )
    return GlossaryResponse(novel=name, data=data)


@router.delete("/novels/{name}/glossary/characters/{original}", response_model=GlossaryResponse)
def delete_character(
    name: str,
    original: str,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.remove_character(name, original)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/relationships", response_model=GlossaryResponse)
def add_relationship(
    name: str,
    payload: GlossaryRelationshipAdd,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.save_relationship(
        name,
        from_char=payload.from_char,
        to_char=payload.to_char,
        relationship=payload.relationship,
        since=payload.since,
        update_since="since" in payload.model_fields_set,
    )
    return GlossaryResponse(novel=name, data=data)


@router.delete("/novels/{name}/glossary/relationships", response_model=GlossaryResponse)
def delete_relationship(
    name: str,
    from_char: str,
    to_char: str,
    _: AuthenticatedPrincipal,
) -> GlossaryResponse:
    _validate_novel(name)
    data = glossary.remove_relationship(name, from_char, to_char)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/validate", response_model=JobStartResponse, status_code=202)
async def post_validate_glossary(
    name: str,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
) -> JobStartResponse:
    _validate_novel(name)
    snapshot = app_config.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        issues = glossary.validate_glossary(name, progress_callback=progress_cb, cancel_event=cancel_event)
        return {"novel": name, "issues": issues}

    job = jobs.submit(
        kind="glossary",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.post("/novels/{name}/glossary/audit", response_model=JobStartResponse, status_code=202)
async def post_audit_glossary(
    name: str,
    _: AuthenticatedPrincipal,
    jobs: JobManagerDependency,
    target: Literal["vi", "en"] | None = None,
) -> JobStartResponse:
    _validate_novel(name)
    snapshot = app_config.get_config().clone(target_language=target)
    loop = asyncio.get_running_loop()
    resolved_target = target or snapshot.target_language

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        issues = glossary.audit_glossary(
            name,
            target=resolved_target,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )
        return {"novel": name, "target": resolved_target, "issues": issues}

    job = jobs.submit(
        kind="audit",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


@router.post("/novels/{name}/glossary/apply")
def post_apply_glossary(
    name: str,
    payload: GlossaryApplyRequest,
    _: AuthenticatedPrincipal,
) -> dict:
    _validate_novel(name)
    return glossary.apply_pending_replacements(
        name,
        target_language=payload.target,
        write=payload.write,
    )


@router.post("/novels/{name}/glossary/dismiss")
def post_dismiss_glossary(
    name: str,
    payload: GlossaryDismissRequest,
    _: AuthenticatedPrincipal,
) -> dict:
    _validate_novel(name)
    glossary.dismiss_pending_replacements(name, target_language=payload.target)
    return {"status": "ok"}


@router.post("/novels/{name}/glossary/rollback")
def post_rollback_glossary(
    name: str,
    payload: GlossaryRollbackRequest,
    _: AuthenticatedPrincipal,
) -> dict:
    _validate_novel(name)
    glossary.rollback_replacements(name, payload.backup_id)
    return {"status": "ok"}
