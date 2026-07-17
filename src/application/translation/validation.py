"""Translation provider and request validation."""

from __future__ import annotations

from src.application.errors import ApplicationValidationError
from src.application.translation.models import TranslationRequest
from src.config import Config
from src.domain.language import normalize_target_language


def validate_request(config: Config, request: TranslationRequest) -> str:
    """Validate request-level values and return the normalized target language."""
    try:
        return normalize_target_language(request.target_language or config.target_language)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error


def apply_request_overrides(config: Config, request: TranslationRequest) -> str:
    """Apply supported request overrides and return the normalized target."""
    target = validate_request(config, request)
    if request.target_language and request.target_language != config.target_language:
        config.target_language = request.target_language
    if request.provider:
        config.llm_provider = request.provider
    if request.enable_review:
        config.enable_review = True
    if request.enable_summary:
        config.enable_summary = True
    return target


def validate_provider(config: Config) -> None:
    """Validate that the selected LLM provider has required credentials."""
    provider = config.llm_provider.lower()
    if provider == "ollama":
        return
    if provider == "gemini" and not config.gemini_api_key:
        raise ApplicationValidationError("Gemini API key is not configured.")
    if provider == "openrouter" and not config.openrouter_api_key:
        raise ApplicationValidationError("OpenRouter API key is not configured.")
