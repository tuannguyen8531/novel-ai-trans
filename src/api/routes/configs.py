"""Crawler config endpoints."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_job_manager, get_state
from src.api.errors import ApplicationValidationError as _ApiValidationError
from src.api.errors import ResourceNotFoundError
from src.api.jobs import JobManager
from src.api.schemas import (
    ConfigGenerateRequest,
    ConfigSaveRequest,
    ConfigSummary,
    ConfigValidateRequest,
    DraftDetail,
    DraftSummary,
    JobStartResponse,
)
from src.application.crawl import (
    ConfigGenerationResult,
    ConfigValidationResult,
)
from src.application.crawl import (
    generate_config as application_generate_config,
)
from src.application.crawl import (
    validate_config as application_validate_config,
)
from src.application.paths import CONFIG_DIR as _CONFIG_DIR
from src.config import SiteConfig

_current_app = None  # type: ignore[var-annotated]

router = APIRouter(tags=["configs"])

_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DRAFT_TTL = timedelta(days=7)


def _is_valid_slug(name: str) -> bool:
    return bool(name) and bool(_SLUG_PATTERN.match(name)) and name not in {".", ".."}


def _config_path(name: str) -> Path:
    if not _is_valid_slug(name):
        raise _ApiValidationError(f"Invalid config name: {name!r}")
    return _CONFIG_DIR / f"{name}.json"


def _list_configs() -> list[ConfigSummary]:
    if not _CONFIG_DIR.exists():
        return []
    out: list[ConfigSummary] = []
    for entry in sorted(_CONFIG_DIR.iterdir()):
        if entry.suffix == ".json" and entry.is_file():
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                out.append(
                    ConfigSummary(
                        name=entry.stem,
                        version=int(data.get("version", 1)),
                        start_url=str(data.get("start_url", "")),
                        updated_at=None,
                    )
                )
            except (OSError, json.JSONDecodeError):
                continue
    return out


@router.get("/configs", response_model=list[ConfigSummary])
def get_configs(_: Principal = Depends(authenticate)) -> list[ConfigSummary]:
    return _list_configs()


@router.get("/configs/{name}")
def get_config_file(
    name: str,
    _: Principal = Depends(authenticate),
) -> dict[str, Any]:
    path = _config_path(name)
    if not path.exists():
        raise ResourceNotFoundError(f"Config not found: {name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail={"code": "invalid_config", "message": str(error)}) from error


@router.put("/configs/{name}")
def save_config(
    name: str,
    payload: ConfigSaveRequest,
    request: Request,
    _: Principal = Depends(authenticate),
) -> dict[str, Any]:
    if not _is_valid_slug(name):
        raise _ApiValidationError(f"Invalid config name: {name!r}")
    if payload.draft_id and not _is_valid_slug(payload.draft_id):
        raise _ApiValidationError(f"Invalid draft id: {payload.draft_id!r}")
    try:
        SiteConfig.from_dict(payload.config)
    except (ValueError, KeyError) as error:
        raise _ApiValidationError(f"Invalid config: {error}") from error

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    target = _config_path(name)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload.config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)

    if payload.draft_id:
        draft_path = get_state(request).drafts_dir / f"{payload.draft_id}.json"
        if draft_path.exists():
            draft_path.unlink()
    return {"name": name, "saved": True}


@router.post("/configs/generate", response_model=JobStartResponse, status_code=202)
async def post_generate_config(
    payload: ConfigGenerateRequest,
    request: Request,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    snapshot = config_context.get_config().clone()
    loop = asyncio.get_running_loop()

    def _run(job, emit, cancel_event):
        from src.api.jobs import build_progress_emitter as _bpe

        progress_cb = _bpe(job, emit)
        result: ConfigGenerationResult = application_generate_config(
            url=payload.url,
            name=payload.name,
            provider=payload.provider,
            use_browser=payload.browser or False,
            no_cache=payload.no_cache or False,
            ignore_sample=payload.ignore_sample or False,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
            drafts_dir=get_state().drafts_dir,
        )
        emit_dict = {
            "draft_id": result.draft_id,
            "name": result.suggested_name,
            "config": result.config,
        }
        return emit_dict

    job = jobs.submit(
        kind="config_generate",
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
    request: Request,
    _: Principal = Depends(authenticate),
    jobs: JobManager = Depends(get_job_manager),
) -> JobStartResponse:
    snapshot = config_context.get_config().clone()
    import asyncio

    loop = asyncio.get_running_loop()
    target = payload.target or name

    def _run(job, emit, cancel_event):
        from src.api.jobs import build_progress_emitter as _bpe

        progress_cb = _bpe(job, emit)
        result: ConfigValidationResult = application_validate_config(
            target=target,
            use_browser=payload.browser,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )
        return {
            "target": target,
            "ok": result.ok,
            "issues": [vars(issue) for issue in result.issues],
            "metadata": result.metadata,
        }

    job = jobs.submit(
        kind="config_validate",
        novel=None,
        snapshot=snapshot,
        loop=loop,
        run=_run,
    )
    return JobStartResponse(job_id=job.id)


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def _draft_path(draft_id: str) -> Path:
    if not _is_valid_slug(draft_id):
        raise _ApiValidationError(f"Invalid draft id: {draft_id!r}")
    return get_state().drafts_dir / f"{draft_id}.json"


def _load_draft(draft_id: str) -> DraftDetail:
    path = _draft_path(draft_id)
    if not path.exists():
        raise ResourceNotFoundError(f"Draft not found: {draft_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail={"code": "invalid_draft", "message": str(error)}) from error
    return DraftDetail(
        draft_id=data["draft_id"],
        name=data.get("name", ""),
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        source_url=data.get("source_url"),
        config=data.get("config", {}),
    )


def _cleanup_expired_drafts(now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    drafts_dir = get_state().drafts_dir
    if not drafts_dir.exists():
        return
    for entry in drafts_dir.iterdir():
        if entry.suffix != ".json" or not entry.is_file():
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        expires = datetime.fromisoformat(data.get("expires_at"))
        if expires <= now:
            entry.unlink(missing_ok=True)


@router.get("/config-drafts", response_model=list[DraftSummary])
def list_drafts(_: Principal = Depends(authenticate)) -> list[DraftSummary]:
    _cleanup_expired_drafts()
    drafts_dir = get_state().drafts_dir
    if not drafts_dir.exists():
        return []
    out: list[DraftSummary] = []
    for entry in sorted(drafts_dir.iterdir()):
        if entry.suffix != ".json" or not entry.is_file():
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            DraftSummary(
                draft_id=data["draft_id"],
                name=data.get("name", ""),
                created_at=datetime.fromisoformat(data["created_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"]),
                source_url=data.get("source_url"),
            )
        )
    return out


@router.get("/config-drafts/{draft_id}", response_model=DraftDetail)
def get_draft(
    draft_id: str,
    _: Principal = Depends(authenticate),
) -> DraftDetail:
    return _load_draft(draft_id)


@router.delete("/config-drafts/{draft_id}", status_code=204)
def delete_draft(
    draft_id: str,
    _: Principal = Depends(authenticate),
) -> None:
    path = _draft_path(draft_id)
    if not path.exists():
        return None
    path.unlink()
    return None
