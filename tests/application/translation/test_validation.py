"""Tests for translation request and provider validation."""

import pytest

from src.application.errors import ApplicationValidationError
from src.application.translation.models import TranslationRequest
from src.application.translation.validation import apply_request_overrides, validate_provider
from src.config import Config


def test_request_overrides_update_active_workflow_config() -> None:
    config = Config(target_language="vi", llm_provider="ollama")
    request = TranslationRequest(
        novel="novel",
        target_language="en",
        provider="gemini",
        review=True,
        summary=True,
    )

    assert apply_request_overrides(config, request) == "en"
    assert config.target_language == "en"
    assert config.llm_provider == "gemini"
    assert request.review is True
    assert request.summary is True


def test_invalid_target_raises_application_validation_error() -> None:
    with pytest.raises(ApplicationValidationError, match="Unsupported target language"):
        apply_request_overrides(
            Config(),
            TranslationRequest(novel="novel", target_language="invalid"),
        )


@pytest.mark.parametrize(
    ("provider", "field"),
    [("gemini", "gemini_api_key"), ("openrouter", "openrouter_api_key")],
)
def test_remote_provider_requires_api_key(provider, field) -> None:
    config = Config(llm_provider=provider)
    setattr(config, field, "")

    with pytest.raises(ApplicationValidationError, match="API key is not configured"):
        validate_provider(config)
