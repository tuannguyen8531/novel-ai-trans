"""Tests for provider metadata helpers."""

from unittest.mock import Mock, patch

import httpx2 as httpx
import pytest

from src.api.errors import ExternalServiceError
from src.api.services.providers import check_provider_runtime, get_ollama_account, list_provider_models, list_providers
from src.application.config import config_scope
from src.config import Config


def test_get_ollama_account_returns_signed_in_username() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"name": "firedragon8531"}

    with patch("src.api.services.providers.httpx.post", return_value=response) as post:
        result = get_ollama_account()

    assert result.signed_in is True
    assert result.username == "firedragon8531"
    assert result.detail is None
    assert post.call_args.args[0].endswith("/api/me")


def test_get_ollama_account_handles_signed_out_daemon() -> None:
    response = Mock(status_code=401)

    with patch("src.api.services.providers.httpx.post", return_value=response):
        result = get_ollama_account()

    assert result.signed_in is False
    assert result.username is None
    assert result.detail == "Not signed in"


def test_check_ollama_confirms_signed_in_account() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"name": "firedragon8531"}

    with patch("src.api.services.providers.httpx.post", return_value=response):
        result = check_provider_runtime("ollama")

    assert result.ok is True
    assert result.detail is None


def test_check_ollama_rejects_signed_out_daemon() -> None:
    response = Mock(status_code=401)

    with (
        patch("src.api.services.providers.httpx.post", return_value=response),
        pytest.raises(ExternalServiceError, match="not signed in"),
    ):
        check_provider_runtime("ollama")


def test_check_ollama_reports_unreachable_daemon() -> None:
    with (
        patch("src.api.services.providers.httpx.post", side_effect=OSError("connection refused")),
        pytest.raises(ExternalServiceError, match="Ollama is unreachable: connection refused"),
    ):
        check_provider_runtime("ollama")


def test_nvidia_discovery_uses_saved_key_and_deduplicates_models():
    response = Mock()
    response.json.return_value = {"data": [{"id": "z/model"}, {"id": "google/gemma-4-31b-it"}, {"id": "z/model"}, {}]}
    with (
        config_scope(Config(nvidia_api_key="saved-key")),
        patch("src.api.services.providers.httpx.get", return_value=response) as get,
    ):
        info = next(item for item in list_providers().providers if item.name == "nvidia")
        assert info.configured is True
        assert info.default_model == "google/gemma-4-31b-it"
        assert list_provider_models("nvidia").models == ["google/gemma-4-31b-it", "z/model"]
    get.assert_called_once_with(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": "Bearer saved-key"},
        timeout=10.0,
    )


def test_nvidia_discovery_returns_empty_on_network_failure():
    with config_scope(Config(nvidia_api_key="key")), patch("src.api.services.providers.httpx.get", side_effect=OSError):
        assert list_provider_models("nvidia").models == []


def test_nvidia_check_verifies_unsaved_key_and_model_with_inference():
    with (
        config_scope(Config(nvidia_api_key="saved-key")),
        patch("src.api.services.providers.httpx.post", return_value=Mock()) as post,
    ):
        assert check_provider_runtime("nvidia", nvidia_api_key="new-key", nvidia_model="custom/model").ok is True
    assert post.call_args.args[0] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer new-key"}
    assert post.call_args.kwargs["json"]["model"] == "custom/model"
    assert post.call_args.kwargs["json"]["max_tokens"] == 1


def test_nvidia_check_rejects_missing_and_invalid_keys():
    with config_scope(Config()), pytest.raises(ExternalServiceError, match="API key is not configured"):
        check_provider_runtime("nvidia")
    response = httpx.Response(401, request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions"))
    with (
        config_scope(Config(nvidia_api_key="invalid")),
        patch("src.api.services.providers.httpx.post", return_value=response),
        pytest.raises(ExternalServiceError, match="NVIDIA check failed"),
    ):
        check_provider_runtime("nvidia")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"status": 400, "detail": "Function id 'example': DEGRADED function cannot be invoked"},
            "temporarily unavailable (DEGRADED)",
        ),
        ({"status": 400, "detail": "max_tokens is invalid"}, "max_tokens is invalid"),
        ({"error": {"message": "Invalid API key"}}, "Invalid API key"),
        ({"message": "Request rejected"}, "Request rejected"),
        ({"detail": "Invalid API key: nvapi-test-key"}, "Invalid API key: [redacted]"),
    ],
)
def test_nvidia_check_shows_upstream_error_details(payload, expected):
    response = httpx.Response(
        400,
        json=payload,
        request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions"),
    )
    with (
        config_scope(Config(nvidia_api_key="nvapi-test-key")),
        patch("src.api.services.providers.httpx.post", return_value=response),
        pytest.raises(ExternalServiceError) as caught,
    ):
        check_provider_runtime("nvidia")
    assert "HTTP 400" in caught.value.message
    assert expected in caught.value.message
