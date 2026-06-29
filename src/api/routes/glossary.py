"""Glossary endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager
from src.api.jobs import JobManager, build_progress_emitter
from src.api.schemas import (
    GlossaryCharactersResponse,
    GlossaryCharacterSummary,
    GlossaryCharacterUpdate,
    GlossaryRelationshipAdd,
    GlossaryResponse,
    GlossaryTermAdd,
    GlossaryTermsPut,
    GlossaryTermUpdate,
    JobStartResponse,
)
from src.api.services.glossary_runtime import (
    audit_glossary,
    load_glossary,
    remove_term,
    save_term,
    save_terms,
    update_term,
    validate_glossary,
)
from src.api.services.glossary_runtime import (
    remove_character as remove_character_impl,
)
from src.api.services.glossary_runtime import (
    remove_relationship as remove_relationship_impl,
)
from src.api.services.glossary_runtime import (
    save_character as save_character_impl,
)
from src.api.services.glossary_runtime import (
    save_relationship as save_relationship_impl,
)
from src.api.services.novel_paths import (
    is_valid_novel_slug,
    resolve_translated_root,
    safe_novel_path,
)

router = APIRouter(tags=["glossary"])


def _validate_novel(name: str) -> Path:
    config = config_context.get_config()
    root = resolve_translated_root(config.translated_dir)
    if not is_valid_novel_slug(name):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Invalid novel name: {name!r}"},
        )
    novel_root = safe_novel_path(root, name)
    if not novel_root.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"Novel not found: {name}"},
        )
    return novel_root


@router.get("/novels/{name}/glossary", response_model=GlossaryResponse)
def get_glossary(
    name: str,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    return GlossaryResponse(novel=name, data=load_glossary(novel_root))


@router.put("/novels/{name}/glossary/terms", response_model=GlossaryResponse)
def put_terms(
    name: str,
    payload: GlossaryTermsPut,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = save_terms(novel_root, payload.terms)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/terms", response_model=GlossaryResponse)
def post_term(
    name: str,
    payload: GlossaryTermAdd,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = save_term(novel_root, payload.original, payload.translated)
    return GlossaryResponse(novel=name, data=data)


@router.delete("/novels/{name}/glossary/terms/{original}", response_model=GlossaryResponse)
def delete_term(
    name: str,
    original: str,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = remove_term(novel_root, original)
    return GlossaryResponse(novel=name, data=data)


@router.patch("/novels/{name}/glossary/terms/{original}", response_model=GlossaryResponse)
def patch_term(
    name: str,
    original: str,
    payload: GlossaryTermUpdate,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = update_term(
        novel_root,
        original,
        payload.original,
        payload.translated,
        overwrite=payload.overwrite,
    )
    return GlossaryResponse(novel=name, data=data)


@router.get("/novels/{name}/glossary/characters", response_model=GlossaryCharactersResponse)
def list_characters(
    name: str,
    _: Principal = Depends(authenticate),
) -> GlossaryCharactersResponse:
    novel_root = _validate_novel(name)
    data = load_glossary(novel_root)
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
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = save_character_impl(
        novel_root,
        original,
        translated_name=payload.translated_name or "",
        role=payload.role or "",
    )
    return GlossaryResponse(novel=name, data=data)


@router.delete("/novels/{name}/glossary/characters/{original}", response_model=GlossaryResponse)
def delete_character(
    name: str,
    original: str,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = remove_character_impl(novel_root, original)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/relationships", response_model=GlossaryResponse)
def add_relationship(
    name: str,
    payload: GlossaryRelationshipAdd,
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = save_relationship_impl(
        novel_root,
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
    _: Principal = Depends(authenticate),
) -> GlossaryResponse:
    novel_root = _validate_novel(name)
    data = remove_relationship_impl(novel_root, from_char, to_char)
    return GlossaryResponse(novel=name, data=data)


@router.post("/novels/{name}/glossary/validate", response_model=JobStartResponse, status_code=202)
async def post_validate_glossary(
    name: str,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    novel_root = _validate_novel(name)
    snapshot = config_context.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        issues = validate_glossary(novel_root, progress_callback=progress_cb, cancel_event=cancel_event)
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
    target: Literal["vi", "en"] | None = None,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    novel_root = _validate_novel(name)
    snapshot = config_context.get_config().clone(target_language=target)
    loop = asyncio.get_running_loop()
    resolved_target = target or snapshot.target_language

    def _run(job, emit, cancel_event):
        progress_cb = build_progress_emitter(job, emit)
        issues = audit_glossary(novel_root, target=resolved_target, progress_callback=progress_cb, cancel_event=cancel_event)
        return {"novel": name, "target": resolved_target, "issues": issues}

    job = jobs.submit(
        kind="audit",
        novel=name,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)
