"""Settings and provider check endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from src.api.auth import Principal, authenticate
from src.api.dependencies import get_state
from src.api.errors import ExternalServiceError
from src.api.schemas import (
    ProviderCheckRequest,
    ProviderCheckResponse,
    ProvidersResponse,
    SettingsPatch,
    SettingsResponse,
)
from src.api.services.providers import check_provider_runtime, list_providers
from src.api.services.settings import apply_settings_patch, build_settings_response

router = APIRouter(tags=["settings"])
_logger = logging.getLogger(__name__)


@router.get("/settings", response_model=SettingsResponse)
def get_settings(_: Principal = Depends(authenticate)) -> SettingsResponse:
    return build_settings_response()


@router.patch("/settings", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsPatch,
    _: Principal = Depends(authenticate),
) -> SettingsResponse:
    apply_settings_patch(payload.model_dump(exclude_none=True))
    return build_settings_response()


@router.get("/providers", response_model=ProvidersResponse)
def get_providers(_: Principal = Depends(authenticate)) -> ProvidersResponse:
    return list_providers()


@router.post("/providers/check", response_model=ProviderCheckResponse)
async def post_provider_check(
    payload: ProviderCheckRequest,
    _: Principal = Depends(authenticate),
) -> ProviderCheckResponse:
    get_state()

    def _run() -> ProviderCheckResponse:
        try:
            return check_provider_runtime(payload.provider)
        except ExternalServiceError as error:
            # Surface a non-OK response rather than raising so the caller sees
            # a 200 with ok=False; raise to map to 502 for unknown providers.
            if "Unknown provider" in (error.message or ""):
                raise
            return ProviderCheckResponse(
                provider=payload.provider,
                ok=False,
                detail=error.message,
            )

    return await asyncio.to_thread(_run)
