"""Provider listing and runtime check helpers."""

from __future__ import annotations

import httpx2 as httpx

from src.api.application_config_context import config_context
from src.api.errors import ExternalServiceError
from src.api.schemas import (
    ProviderCheckResponse,
    ProviderInfo,
    ProviderModelsResponse,
    ProvidersResponse,
)


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


def list_provider_models(provider: str) -> ProviderModelsResponse:
    """Return the list of available model ids for *provider*.

    Ollama: pulled from ``/api/tags`` on the configured base URL.
    Gemini: ``GET /v1beta/models`` (requires the API key).
    OpenRouter: ``GET /api/v1/models`` (requires the API key).

    On any network/parse failure we return an empty list rather than
    raising — the GUI can still let the user type a model name manually.
    """
    config = config_context.get_config()
    provider = provider.lower().strip()
    try:
        if provider == "ollama":
            response = httpx.get(
                f"{config.ollama_base_url.rstrip('/')}/api/tags",
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
            return ProviderModelsResponse(
                provider="ollama",
                models=sorted(
                    {
                        str(item.get("name", "")).strip()
                        for item in payload.get("models", [])
                        if isinstance(item, dict) and item.get("name")
                    }
                ),
            )
        if provider == "gemini":
            if not config.gemini_api_key:
                return ProviderModelsResponse(provider="gemini", models=[])
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": config.gemini_api_key},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            return ProviderModelsResponse(
                provider="gemini",
                models=sorted(
                    {
                        str(item.get("name", "")).replace("models/", "").strip()
                        for item in payload.get("models", [])
                        if isinstance(item, dict) and item.get("name")
                    }
                ),
            )
        if provider == "openrouter":
            if not config.openrouter_api_key:
                return ProviderModelsResponse(provider="openrouter", models=[])
            response = httpx.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            return ProviderModelsResponse(
                provider="openrouter",
                models=sorted(
                    {
                        str(item.get("id", "")).strip()
                        for item in payload.get("data", [])
                        if isinstance(item, dict) and item.get("id")
                    }
                ),
            )
    except (httpx.HTTPError, OSError, ValueError):
        return ProviderModelsResponse(provider=provider, models=[])
    return ProviderModelsResponse(provider=provider, models=[])


def check_provider_runtime(
    provider: str,
    *,
    ollama_base_url: str | None = None,
    gemini_api_key: str | None = None,
    openrouter_api_key: str | None = None,
) -> ProviderCheckResponse:
    """Synchronously verify a provider is reachable."""
    config = config_context.get_config()
    provider = provider.lower().strip()
    if provider == "ollama":
        base_url = (ollama_base_url or config.ollama_base_url).rstrip("/")
        try:
            response = httpx.get(f"{base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"Ollama is unreachable: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    if provider == "gemini":
        api_key = gemini_api_key or config.gemini_api_key
        if not api_key:
            raise ExternalServiceError("Gemini API key is not configured.")
        try:
            response = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=10.0,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"Gemini check failed: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    if provider == "openrouter":
        api_key = openrouter_api_key or config.openrouter_api_key
        if not api_key:
            raise ExternalServiceError("OpenRouter API key is not configured.")
        try:
            response = httpx.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"OpenRouter check failed: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    raise ExternalServiceError(f"Unknown provider: {provider}")
