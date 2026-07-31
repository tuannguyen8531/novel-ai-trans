"""Tests for API logging format."""

import json
from datetime import datetime

from src import paths
from src.services import logger as logger_module


def test_pytest_logs_use_shared_cache_root():
    assert paths.RUNTIME_DIR.parent / ".cache" / "pytest" / "logs" == logger_module.LOG_DIR


def test_new_daily_folder_removes_old_logs_beyond_retention(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    for name in ("2026-05-01", "2026-05-02", "2026-05-03"):
        daily_dir = log_dir / name
        daily_dir.mkdir(parents=True)
        (daily_dir / "request.log").write_text(name, encoding="utf-8")
    unrelated_dir = log_dir / "archive"
    unrelated_dir.mkdir()

    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module.config, "log_retention_days", 3)

    path = logger_module._daily_log_path(datetime(2026, 5, 4), "request.log")

    assert path == log_dir / "2026-05-04" / "request.log"
    assert sorted(entry.name for entry in log_dir.iterdir()) == ["2026-05-02", "2026-05-03", "2026-05-04", "archive"]


def test_existing_daily_folder_does_not_run_rotation(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    for name in ("2026-05-01", "2026-05-02"):
        (log_dir / name).mkdir(parents=True)

    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module.config, "log_retention_days", 1)

    logger_module._daily_log_path(datetime(2026, 5, 2), "request.log")

    assert sorted(entry.name for entry in log_dir.iterdir()) == ["2026-05-01", "2026-05-02"]


def test_log_api_request_writes_separate_request_and_response_records(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logger_module, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger_module, "_redact_secrets", lambda data: data)
    fixed_time = "2026-05-07 15:00:00"

    def _strftime(fmt):
        return "2026-05-07" if fmt == "%Y-%m-%d" else fixed_time

    dummy_now = type("DummyNow", (), {"strftime": staticmethod(_strftime)})()
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

    daily_dir = log_dir / "2026-05-07"
    request_lines = (daily_dir / "request.log").read_text(encoding="utf-8").splitlines()
    response_lines = (daily_dir / "response.log").read_text(encoding="utf-8").splitlines()
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

    logger_module.log_api_request_sent(
        call_type="gen-config-toc-retry",
        provider="ollama",
        url="http://localhost/api/chat",
        request_body={},
    )

    request_files = list(log_dir.glob("*/request.log"))
    assert len(request_files) == 1
    line = request_files[0].read_text(encoding="utf-8").splitlines()[0]
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
