"""Provider listing and runtime check helpers."""

from __future__ import annotations

import httpx

from src.api.application_config_context import config_context
from src.api.errors import ExternalServiceError
from src.api.schemas import ProviderCheckResponse, ProviderInfo, ProvidersResponse


def list_providers() -> ProvidersResponse:
    config = config_context.get_config()
    providers = [
        ProviderInfo(
            name="ollama",
            configured=True,
            default_model=config.ollama_model,
        ),
        ProviderInfo(
            name="gemini",
            configured=bool(config.gemini_api_key),
            default_model=config.gemini_model,
        ),
        ProviderInfo(
            name="openrouter",
            configured=bool(config.openrouter_api_key),
            default_model=config.openrouter_model,
        ),
    ]
    return ProvidersResponse(providers=providers, default_provider=config.llm_provider)


def check_provider_runtime(provider: str) -> ProviderCheckResponse:
    """Synchronously verify a provider is reachable."""
    config = config_context.get_config()
    provider = provider.lower().strip()
    if provider == "ollama":
        try:
            response = httpx.get(f"{config.ollama_base_url.rstrip('/')}/api/tags", timeout=5.0)
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"Ollama is unreachable: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    if provider == "gemini":
        if not config.gemini_api_key:
            raise ExternalServiceError("Gemini API key is not configured.")
        try:
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": config.gemini_api_key},
                timeout=10.0,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"Gemini check failed: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    if provider == "openrouter":
        if not config.openrouter_api_key:
            raise ExternalServiceError("OpenRouter API key is not configured.")
        try:
            response = httpx.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"OpenRouter check failed: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    raise ExternalServiceError(f"Unknown provider: {provider}")
