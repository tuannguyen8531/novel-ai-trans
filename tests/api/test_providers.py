"""Tests for provider metadata helpers."""

from unittest.mock import Mock, patch

import pytest

from src.api.errors import ExternalServiceError
from src.api.services.providers import check_provider_runtime, get_ollama_account


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
