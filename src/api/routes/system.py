"""Settings and provider check endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter

from src import paths
from src.api.dependencies import AuthenticatedPrincipal, get_state
from src.api.errors import ExternalServiceError
from src.api.schemas import (
    OllamaAccountResponse,
    ProviderCheckRequest,
    ProviderCheckResponse,
    ProviderModelsResponse,
    ProviderSettingsPatch,
    ProvidersResponse,
    SettingsPatch,
    SettingsPersistResponse,
    SettingsResponse,
    TelegramSettingsPatch,
)
from src.api.services.env import (
    persist_config_to_env,
)
from src.api.services.providers import (
    check_provider_runtime,
    get_ollama_account,
    list_provider_models,
    list_providers,
)
from src.api.services.settings import apply_settings_patch, build_settings_response, persist_config_to_settings
from src.application import config as app_config

router = APIRouter(tags=["settings"])
_logger = logging.getLogger(__name__)

# Project root sits three directories up from this file:
#   src/api/routes/system.py -> src/api/routes/ -> src/api/ -> src/ -> project/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = _PROJECT_ROOT / ".env"
DEFAULT_SETTINGS_PATH = paths.SETTINGS_PATH


@router.get("/settings", response_model=SettingsResponse)
def get_settings(_: AuthenticatedPrincipal) -> SettingsResponse:
    return build_settings_response()


@router.patch("/settings", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsPatch,
    _: AuthenticatedPrincipal,
) -> SettingsResponse:
    apply_settings_patch(payload.model_dump(exclude_none=True))
    return build_settings_response()


@router.post("/settings/persist", response_model=SettingsPersistResponse)
def persist_settings(
    _: AuthenticatedPrincipal,
) -> SettingsPersistResponse:
    """Write the current non-secret settings to ``settings.json``."""
    config = app_config.get_config()
    written = persist_config_to_settings(
        config,
        DEFAULT_SETTINGS_PATH,
        field_names={
            field_name
            for field_name in config.__dataclass_fields__
            if not field_name.startswith("telegram_")
            and field_name
            not in {
                "llm_provider",
                "fallback_provider",
                "ollama_base_url",
                "ollama_model",
                "gemini_api_key",
                "gemini_model",
                "openrouter_api_key",
                "openrouter_model",
            }
        },
    )
    _logger.info(
        "Persisted %d setting(s) to %s: %s",
        len(written),
        DEFAULT_SETTINGS_PATH,
        ", ".join(written) or "(none)",
    )
    return SettingsPersistResponse(
        path=str(DEFAULT_SETTINGS_PATH),
        changed_keys=sorted(written),
    )


@router.post("/settings/telegram/persist", response_model=SettingsPersistResponse)
def persist_telegram_settings(
    payload: TelegramSettingsPatch,
    _: AuthenticatedPrincipal,
) -> SettingsPersistResponse:
    """Update Telegram runtime settings and persist only Telegram fields."""
    apply_settings_patch(payload.model_dump())
    config = app_config.get_config()
    written = persist_config_to_settings(
        config,
        DEFAULT_SETTINGS_PATH,
        field_names={
            "telegram_enabled",
            "telegram_api_base",
            "telegram_parse_mode",
            "telegram_silent",
            "telegram_timeout_seconds",
        },
    )
    _logger.info("Persisted Telegram settings to %s: %s", DEFAULT_SETTINGS_PATH, ", ".join(written) or "(none)")
    return SettingsPersistResponse(path=str(DEFAULT_SETTINGS_PATH), changed_keys=sorted(written))


@router.post("/settings/providers/persist", response_model=SettingsPersistResponse)
def persist_provider_settings(
    payload: ProviderSettingsPatch,
    _: AuthenticatedPrincipal,
) -> SettingsPersistResponse:
    """Update provider settings; keep API keys in ``.env``."""
    patch = payload.model_dump()
    if not patch.get("gemini_api_key"):
        patch.pop("gemini_api_key", None)
    if not patch.get("openrouter_api_key"):
        patch.pop("openrouter_api_key", None)
    apply_settings_patch(patch)
    config = app_config.get_config()
    written = persist_config_to_settings(
        config,
        DEFAULT_SETTINGS_PATH,
        field_names={
            "llm_provider",
            "fallback_provider",
            "ollama_base_url",
            "ollama_model",
            "gemini_model",
            "openrouter_model",
        },
    )
    secret_written = persist_config_to_env(
        config,
        DEFAULT_ENV_PATH,
        field_names={"gemini_api_key", "openrouter_api_key"},
    )
    _logger.info("Persisted provider settings to %s and keys to %s", DEFAULT_SETTINGS_PATH, DEFAULT_ENV_PATH)
    return SettingsPersistResponse(
        path=str(DEFAULT_SETTINGS_PATH),
        changed_keys=sorted(set(written).union(secret_written)),
    )


@router.get("/providers", response_model=ProvidersResponse)
def get_providers(_: AuthenticatedPrincipal) -> ProvidersResponse:
    return list_providers()


@router.get("/providers/ollama/account", response_model=OllamaAccountResponse)
def get_ollama_account_status(_: AuthenticatedPrincipal) -> OllamaAccountResponse:
    return get_ollama_account()


@router.get("/providers/{provider}/models", response_model=ProviderModelsResponse)
def get_provider_models(
    provider: str,
    _: AuthenticatedPrincipal,
) -> ProviderModelsResponse:
    return list_provider_models(provider)


@router.post("/providers/check", response_model=ProviderCheckResponse)
async def post_provider_check(
    payload: ProviderCheckRequest,
    _: AuthenticatedPrincipal,
) -> ProviderCheckResponse:
    get_state()

    def _run() -> ProviderCheckResponse:
        try:
            return check_provider_runtime(
                payload.provider,
                ollama_base_url=payload.ollama_base_url,
                gemini_api_key=payload.gemini_api_key,
                openrouter_api_key=payload.openrouter_api_key,
            )
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
