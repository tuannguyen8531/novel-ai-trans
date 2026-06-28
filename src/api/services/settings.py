"""Settings read/write for the API layer."""

from __future__ import annotations

from src.api.application_config_context import config_context
from src.api.schemas import SettingsResponse
from src.application.config_context import apply_settings_patch as _apply
from src.application.errors import ApplicationValidationError


def build_settings_response() -> SettingsResponse:
    config = config_context.get_config()
    return SettingsResponse(
        translated_dir=config.translated_dir,
        target_language=config.target_language,
        llm_provider=config.llm_provider,
        fallback_provider=config.fallback_provider,
        use_browser=config.use_browser,
        max_chapters=config.max_chapters,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        review_threshold=config.review_threshold,
        max_retries=config.max_retries,
        enable_review=config.enable_review,
        enable_summary=config.enable_summary,
        translation_temperature=config.translation_temperature,
        translation_max_tokens=config.translation_max_tokens,
        gemini_api_key_configured=bool(config.gemini_api_key),
        openrouter_api_key_configured=bool(config.openrouter_api_key),
        telegram_configured=bool(config.telegram_bot_token and config.telegram_chat_id),
        ollama_base_url=config.ollama_base_url,
        ollama_model=config.ollama_model,
        gemini_model=config.gemini_model,
        openrouter_model=config.openrouter_model,
    )


def apply_settings_patch(patch: dict) -> SettingsResponse:
    try:
        _apply(patch)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error
    return build_settings_response()
