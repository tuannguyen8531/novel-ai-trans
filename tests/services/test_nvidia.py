"""NVIDIA request contract and configuration snapshot coverage."""

import json
from unittest.mock import Mock

import httpx2 as httpx
import pytest

from src.application.config import config_scope
from src.config import Config
from src.services.llm import get_llm, reset_llm
from src.services.llm.fallback import FallbackProvider
from src.services.llm.nvidia import NvidiaProvider


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr("src.services.llm.base.log_api_request_sent", Mock(return_value="call"))
    monkeypatch.setattr("src.services.llm.base.log_api_request_received", Mock())
    monkeypatch.setattr("src.services.llm.base.log_error", Mock())
    with NvidiaProvider() as service:
        yield service


@pytest.mark.parametrize(("call_type", "temperature", "max_tokens"), [("translate", 0.3, 8192), ("learn", 0.0, 4096)])
def test_nvidia_uses_active_snapshot_and_generation_profile(provider, call_type, temperature, max_tokens):
    def respond(request):
        assert str(request.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer snapshot-key"
        assert json.loads(request.content) == {
            "model": "google/gemma-4-31b-it",
            "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "user"}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": " translated "}}]})

    provider._client = httpx.Client(transport=httpx.MockTransport(respond))
    with config_scope(Config(llm_provider="nvidia", nvidia_api_key="snapshot-key")):
        assert provider.generate("system", "user", call_type) == "translated"


@pytest.mark.parametrize(
    "content", ["<|channel>thought\n<channel|>translated", "<|channel>thought\nreasoning<channel|>translated"]
)
def test_nvidia_removes_gemma_thought_channel(provider, content):
    provider._client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"message": {"content": content}}]}))
    )
    with config_scope(Config(nvidia_api_key="key")):
        assert provider.generate("system", "user", "translate") == "translated"


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "<|channel>thought\n<channel|>"}}]},
    ],
)
def test_nvidia_rejects_missing_final_content(provider, payload):
    provider._client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with config_scope(Config(nvidia_api_key="key", max_retries=0)), pytest.raises(RuntimeError, match="no content"):
        provider.generate("system", "user", "translate")


def test_nvidia_missing_key_fails_before_http_request(provider):
    with config_scope(Config()), pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        provider.generate("system", "user", "translate")
    assert provider._client is None


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (429, {"error": {"message": "rate limited"}}),
        (400, {"status": 400, "title": "Bad Request", "detail": "Function id 'example': DEGRADED function cannot be invoked"}),
    ],
)
def test_nvidia_service_failure_retries_then_falls_back(provider, monkeypatch, status, payload):
    request = Mock(return_value=httpx.Response(status, json=payload))
    provider._client = httpx.Client(transport=httpx.MockTransport(request))
    wait = Mock()
    monkeypatch.setattr("src.services.llm.base.wait_for_retry", wait)
    fallback = Mock()
    fallback.provider_name = "ollama"
    fallback.generate.return_value = "fallback text"
    with config_scope(Config(nvidia_api_key="key", max_retries=1)):
        assert FallbackProvider(provider, fallback).generate("system", "user", "translate") == "fallback text"
    assert request.call_count == 2
    wait.assert_called_once_with(5)
    fallback.generate.assert_called_once_with("system", "user", "translate")


@pytest.mark.parametrize(("primary", "fallback"), [("nvidia", ""), ("nvidia", "ollama"), ("ollama", "nvidia")])
def test_factory_accepts_nvidia_as_primary_and_fallback(primary, fallback):
    reset_llm()
    try:
        with config_scope(Config(llm_provider=primary, fallback_provider=fallback)):
            service = get_llm()
            assert service.provider_name == (f"{primary}+{fallback}" if fallback else primary)
    finally:
        reset_llm()
