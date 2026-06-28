"""Smoke tests for the translation endpoint payload handling."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.api.app_factory import create_app
from src.application import config_context as _config_context
from src.config import config as _global_config


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        translated = tmp_path / "translated"
        translated.mkdir(parents=True, exist_ok=True)
        drafts = tmp_path / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        snapshot = _global_config.clone(translated_dir=str(translated))
        original = _config_context.get_config()
        _config_context.set_default(snapshot)
        try:
            with patch.dict(os.environ, {"API_HOST": "127.0.0.1", "CORS_ORIGINS": "http://localhost:5173"}):
                app = create_app(
                    dist_dir=tmp_path / "dist",
                    drafts_dir=drafts,
                    history_root=translated,
                    jobs_dir=tmp_path / "jobs",
                )
            with TestClient(app) as test_client:
                yield test_client
        finally:
            _config_context.set_default(original)


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
