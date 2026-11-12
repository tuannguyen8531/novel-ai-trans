"""Provider listing and runtime check helpers."""

from __future__ import annotations

import httpx2 as httpx

from src.api.errors import ExternalServiceError
from src.api.schemas import (
    OllamaAccountResponse,
    ProviderCheckResponse,
    ProviderInfo,
    ProviderModelsResponse,
    ProvidersResponse,
)
from src.application import config as app_config
from src.services.llm.base import response_error_message


def list_providers() -> ProvidersResponse:
    config = app_config.get_config()
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
        ProviderInfo(
            name="nvidia",
            configured=bool(config.nvidia_api_key),
            default_model=config.nvidia_model,
        ),
    ]
    return ProvidersResponse(providers=providers, default_provider=config.llm_provider)


def get_ollama_account() -> OllamaAccountResponse:
    """Return the account authenticated by the configured Ollama daemon."""
    config = app_config.get_config()
    try:
        response = httpx.post(
            f"{config.ollama_base_url.rstrip('/')}/api/me",
            timeout=5.0,
        )
        if response.status_code == 401:
            return OllamaAccountResponse(
                signed_in=False,
                detail="Not signed in",
            )
        response.raise_for_status()
        payload = response.json()
        username = str(payload.get("name", "")).strip() if isinstance(payload, dict) else ""
        if not username:
            return OllamaAccountResponse(
                signed_in=False,
                detail="Ollama did not return an account name",
            )
        return OllamaAccountResponse(signed_in=True, username=username)
    except (httpx.HTTPError, OSError, ValueError) as error:
        return OllamaAccountResponse(
            signed_in=False,
            detail=f"Account unavailable: {error}",
        )


def list_provider_models(provider: str) -> ProviderModelsResponse:
    """Return the list of available model ids for *provider*.

    Ollama: pulled from ``/api/tags`` on the configured base URL.
    Gemini: ``GET /v1beta/models`` (requires the API key).
    OpenRouter: ``GET /api/v1/models`` (requires the API key).
    NVIDIA: ``GET /v1/models``.

    On any network/parse failure we return an empty list rather than
    raising — the GUI can still let the user type a model name manually.
    """
    config = app_config.get_config()
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
        if provider in {"openrouter", "nvidia"}:
            api_key = getattr(config, f"{provider}_api_key")
            if not api_key:
                return ProviderModelsResponse(provider=provider, models=[])
            response = httpx.get(
                "https://openrouter.ai/api/v1/models"
                if provider == "openrouter"
                else "https://integrate.api.nvidia.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            return ProviderModelsResponse(
                provider=provider,
                models=sorted(
                    {
                        str(item.get("id", "")).strip()
                        for item in payload.get("data", [])
                        if isinstance(item, dict) and item.get("id")
                    }
                ),
            )
    except httpx.HTTPError, OSError, ValueError:
        return ProviderModelsResponse(provider=provider, models=[])
    return ProviderModelsResponse(provider=provider, models=[])


def check_provider_runtime(
    provider: str,
    *,
    ollama_base_url: str | None = None,
    gemini_api_key: str | None = None,
    openrouter_api_key: str | None = None,
    nvidia_api_key: str | None = None,
    nvidia_model: str | None = None,
) -> ProviderCheckResponse:
    """Synchronously verify a provider is reachable."""
    config = app_config.get_config()
    provider = provider.lower().strip()
    if provider == "ollama":
        base_url = (ollama_base_url or config.ollama_base_url).rstrip("/")
        try:
            response = httpx.post(f"{base_url}/api/me", timeout=5.0)
            if response.status_code == 401:
                raise ExternalServiceError("Ollama is not signed in.")
            response.raise_for_status()
            payload = response.json()
            username = str(payload.get("name", "")).strip() if isinstance(payload, dict) else ""
            if not username:
                raise ExternalServiceError("Ollama did not return an account name.")
        except ExternalServiceError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
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
    if provider == "nvidia":
        api_key = nvidia_api_key or config.nvidia_api_key
        model = nvidia_model or config.nvidia_model
        if not api_key:
            raise ExternalServiceError("NVIDIA API key is not configured.")
        try:
            # The model catalog is public; use inference to actually verify the key.
            response = httpx.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 1,
                    "stream": False,
                },
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = response_error_message(error.response).replace(api_key, "[redacted]")
            if "degraded" in detail.lower():
                detail = f"Model '{model}' is temporarily unavailable (DEGRADED). Choose another model or try again later."
            raise ExternalServiceError(f"NVIDIA check failed (HTTP {error.response.status_code}): {detail}") from error
        except (httpx.HTTPError, OSError) as error:
            raise ExternalServiceError(f"NVIDIA check failed: {error}") from error
        return ProviderCheckResponse(provider=provider, ok=True)
    raise ExternalServiceError(f"Unknown provider: {provider}")
