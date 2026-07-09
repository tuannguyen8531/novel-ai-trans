"""Tests for the novel custom rules endpoints."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.api.app_factory import create_app
from src.application import config_context as _config_context
from src.config import Config


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        translated = tmp_path / "translated"
        translated.mkdir(parents=True, exist_ok=True)
        drafts = tmp_path / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        novel_dir = translated / "demo"
        novel_dir.mkdir(parents=True)
        (novel_dir / "rules.md").write_text(
            "- Custom rule 1\n- Custom rule 2",
            encoding="utf-8",
        )
        snapshot = Config(translated_dir=str(translated))
        original = _config_context.get_config()
        _config_context.set_default(snapshot)
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
                    yield test_client, novel_dir
        finally:
            _config_context.set_default(original)


def test_get_rules_returns_existing(client):
    test_client, _ = client
    response = test_client.get("/api/novels/demo/rules")
    assert response.status_code == 200
    body = response.json()
    assert body["rules"] == "- Custom rule 1\n- Custom rule 2"


def test_get_rules_returns_empty_when_missing(client):
    test_client, novel_dir = client
    # Remove existing rules file
    (novel_dir / "rules.md").unlink()
    response = test_client.get("/api/novels/demo/rules")
    assert response.status_code == 200
    body = response.json()
    assert body["rules"] == ""


def test_get_rules_missing_novel_returns_404(client):
    test_client, _ = client
    response = test_client.get("/api/novels/does-not-exist/rules")
    assert response.status_code == 404


def test_put_rules_updates_file(client):
    test_client, novel_dir = client
    response = test_client.put(
        "/api/novels/demo/rules",
        json={"rules": "New translation guidelines"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Rules updated successfully."

    # Verify on-disk file updated
    content = (novel_dir / "rules.md").read_text(encoding="utf-8")
    assert content == "New translation guidelines"


def test_put_rules_creates_file_if_missing(client):
    test_client, novel_dir = client
    (novel_dir / "rules.md").unlink()
    response = test_client.put(
        "/api/novels/demo/rules",
        json={"rules": "Brand new rules content"},
    )
    assert response.status_code == 200
    assert (novel_dir / "rules.md").exists()
    content = (novel_dir / "rules.md").read_text(encoding="utf-8")
    assert content == "Brand new rules content"
