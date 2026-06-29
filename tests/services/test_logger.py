"""Tests for API logging format."""

import json

from src.services import logger as logger_module


def test_log_api_request_writes_separate_request_and_response_records(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module, "LOG_REQUEST_FILE", log_dir / "request.log")
    monkeypatch.setattr(logger_module, "LOG_RESPONSE_FILE", log_dir / "response.log")
    monkeypatch.setattr(logger_module, "_redact_secrets", lambda data: data)
    fixed_time = "2026-05-07 15:00:00"
    dummy_now = type("DummyNow", (), {"strftime": staticmethod(lambda _fmt: fixed_time)})()
    dummy_datetime = type("DummyDateTime", (), {"now": staticmethod(lambda: dummy_now)})()
    monkeypatch.setattr(logger_module, "datetime", dummy_datetime)
    monkeypatch.setattr(logger_module, "uuid4", type("DummyUUID4", (), {"hex": "abc123"}))

    call_id = logger_module.log_api_request_sent(
        call_type="translate",
        provider="gemini",
        url="https://example.test/api",
        request_body={"foo": "bar"},
        chunk_index=0,
    )

    logger_module.log_api_request_received(
        call_id=call_id,
        call_type="translate",
        provider="gemini",
        url="https://example.test/api",
        response_body={"ok": True},
        status_code=200,
        duration_ms=12.34,
        chunk_index=0,
    )

    request_lines = (log_dir / "request.log").read_text(encoding="utf-8").splitlines()
    response_lines = (log_dir / "response.log").read_text(encoding="utf-8").splitlines()
    assert len(request_lines) == 1
    assert len(response_lines) == 1

    first = json.loads(request_lines[0].split(" ", 2)[2])
    second = json.loads(response_lines[0].split(" ", 2)[2])

    assert first["type"] == "translate"
    assert second["type"] == "translate"
    assert first["provider"] == "gemini"
    assert second["provider"] == "gemini"
    assert "call_type" not in first
    assert "call_type" not in second
    assert first["call_id"] == "abc123"
    assert second["call_id"] == "abc123"
    assert first["request"] == {"foo": "bar"}
    assert second["response"] == {"ok": True}
    assert "response" not in first
    assert "request" not in second


def test_log_type_is_normalized_to_snake_case(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module, "LOG_REQUEST_FILE", log_dir / "request.log")

    logger_module.log_api_request_sent(
        call_type="gen-config-toc-retry",
        provider="ollama",
        url="http://localhost/api/chat",
        request_body={},
    )

    line = (log_dir / "request.log").read_text(encoding="utf-8").splitlines()[0]
    entry = json.loads(line.split(" ", 2)[2])
    assert entry["type"] == "gen_config_toc_retry"
    assert "call_type" not in entry


def test_log_ai_call_does_not_write_translation_log(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module, "_verbose", False)

    logger_module.log_ai_call(
        "translate",
        system_prompt="system",
        user_prompt="user",
        response="response",
    )

    assert not log_dir.exists()
