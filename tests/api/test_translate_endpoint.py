"""Smoke tests for the translation endpoint payload handling."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.api.factory import create_app
from src.application import config as _config
from src.config import Config


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        translated = tmp_path / "translated"
        translated.mkdir(parents=True, exist_ok=True)
        drafts = tmp_path / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        snapshot = Config(translated_dir=str(translated))
        original = _config.get_config()
        _config.set_default(snapshot)
        try:
            with patch.dict(
                os.environ,
                {"API_HOST": "127.0.0.1", "CORS_ORIGINS": "http://localhost:5173"},
                clear=True,
            ):
                app = create_app(
                    dist_dir=tmp_path / "dist",
                    drafts_dir=drafts,
                    history_root=translated,
                    jobs_dir=tmp_path / "jobs",
                )
                with TestClient(app) as test_client:
                    yield test_client
        finally:
            _config.set_default(original)


def test_translate_accepts_empty_provider_and_target(client):
    """Empty strings from the GUI's 'use default' option must not be passed
    as unexpected kwargs to ``Config.__init__``."""
    response = client.post(
        "/api/translate",
        json={
            "novel": "demo",
            "provider": "",
            "target_language": "",
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert "job_id" in body
    # Wait briefly for the queued job to start, then cancel it so the
    # test fixture tears down cleanly.
    deadline = time.time() + 1.0
    while time.time() < deadline:
        current = client.app.state.app_state.job_manager.current
        if current and current.id == body["job_id"]:
            client.post(f"/api/jobs/{body['job_id']}/cancel")
            break
        time.sleep(0.05)


def test_translate_accepts_explicit_provider(client):
    response = client.post(
        "/api/translate",
        json={
            "novel": "demo",
            "provider": "ollama",
            "target_language": "vi",
        },
    )
    assert response.status_code == 202, response.text


def test_translate_accepts_missing_fields(client):
    """Frontend may POST only the novel name; all overrides are optional."""
    response = client.post("/api/translate", json={"novel": "demo"})
    assert response.status_code == 202, response.text


def test_translate_writes_reports_next_to_custom_jobs_directory(client):
    result = SimpleNamespace(
        novel="demo",
        total=1,
        success=1,
        failed=0,
        skipped=False,
        cancelled=False,
        chapters_attempted=[1],
        failures=[],
        started_at=time.time(),
    )
    with patch("src.api.routes.translate.run_translation", return_value=result) as translate:
        response = client.post(
            "/api/translate",
            json={"novel": "demo", "translate_metadata": False},
        )
        assert response.status_code == 202, response.text

        deadline = time.time() + 2
        while time.time() < deadline and not translate.called:
            time.sleep(0.01)

        assert translate.called
        runtime_root = client.app.state.app_state.jobs_dir.parent
        assert translate.call_args.kwargs["report_root"] == runtime_root / "reports"
        assert translate.call_args.kwargs["transaction_root"] == runtime_root / "transactions"
        assert "rejected_root" not in translate.call_args.kwargs


def test_translate_chapter_failures_finish_with_errors_and_notify_failed(client):
    result = SimpleNamespace(
        novel="demo",
        total=2,
        success=1,
        failed=1,
        skipped=False,
        cancelled=False,
        chapters_attempted=[1, 2],
        failures=[2],
        started_at=time.time(),
    )
    with (
        patch("src.api.routes.translate.run_translation", return_value=result),
        patch("src.api.routes.translate.send_run_notification") as notify,
    ):
        response = client.post(
            "/api/translate",
            json={"novel": "demo", "translate_metadata": False},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        deadline = time.time() + 5
        job = client.get(f"/api/jobs/{job_id}").json()
        while job["status"] in {"queued", "running", "cancelling"} and time.time() < deadline:
            time.sleep(0.01)
            job = client.get(f"/api/jobs/{job_id}").json()

    assert job["status"] == "degraded"
    assert job["result"]["failed"] == 1
    notify.assert_called_once()
    assert notify.call_args.kwargs["status"] == "Failed"
    assert notify.call_args.kwargs["stats"] == "Translated: 1/2 · Failed: 1"
