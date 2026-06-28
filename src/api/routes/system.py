"""Settings and provider check endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.application_config_context import config_context
from src.api.auth import Principal, authenticate
from src.api.dependencies import get_state
from src.api.errors import ExternalServiceError
from src.api.schemas import (
    ProviderCheckRequest,
    ProviderCheckResponse,
    ProviderModelsResponse,
    ProvidersResponse,
    SettingsPatch,
    SettingsPersistResponse,
    SettingsResponse,
)
from src.api.services.env_persistence import (
    persist_config_to_env,
)
from src.api.services.providers import (
    check_provider_runtime,
    list_provider_models,
    list_providers,
)
from src.api.services.settings import apply_settings_patch, build_settings_response

router = APIRouter(tags=["settings"])
_logger = logging.getLogger(__name__)

# Project root sits three directories up from this file:
#   src/api/routes/system.py -> src/api/routes/ -> src/api/ -> src/ -> project/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = _PROJECT_ROOT / ".env"


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


@router.post("/settings/persist", response_model=SettingsPersistResponse)
def persist_settings(
    _: Principal = Depends(authenticate),
) -> SettingsPersistResponse:
    """Write the current in-process settings back to ``.env``.

    Non-secret fields are always written. Secret fields (provider API keys,
    Telegram tokens) are only written when the in-memory value is non-empty,
    so a freshly-cleared field is not written as an empty line.
    """
    config = config_context.get_config()
    env_path = DEFAULT_ENV_PATH
    written = persist_config_to_env(config, env_path)
    _logger.info(
        "Persisted %d setting(s) to %s: %s",
        len(written),
        env_path,
        ", ".join(written) or "(none)",
    )
    return SettingsPersistResponse(
        path=str(env_path),
        changed_keys=sorted(written),
    )


@router.get("/providers", response_model=ProvidersResponse)
def get_providers(_: Principal = Depends(authenticate)) -> ProvidersResponse:
    return list_providers()


@router.get("/providers/{provider}/models", response_model=ProviderModelsResponse)
def get_provider_models(
    provider: str,
    _: Principal = Depends(authenticate),
) -> ProviderModelsResponse:
    return list_provider_models(provider)


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
