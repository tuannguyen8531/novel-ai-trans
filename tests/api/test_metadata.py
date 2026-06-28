"""Tests for the novel metadata endpoints."""

from __future__ import annotations

import json
import os
import tempfile
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
        novel_dir = translated / "demo"
        novel_dir.mkdir(parents=True)
        (novel_dir / "metadata.json").write_text(
            json.dumps({"title": "Old", "author": "Old Author"}),
            encoding="utf-8",
        )
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
                yield test_client, novel_dir
        finally:
            _config_context.set_default(original)


def test_get_metadata_returns_existing(client):
    test_client, _ = client
    response = test_client.get("/api/novels/demo/metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["novel"] == "demo"
    assert body["data"]["title"] == "Old"
    assert body["data"]["author"] == "Old Author"


def test_get_metadata_missing_novel_returns_404(client):
    test_client, _ = client
    response = test_client.get("/api/novels/does-not-exist/metadata")
    assert response.status_code == 404


def test_get_metadata_rejects_path_traversal(client):
    test_client, _ = client
    response = test_client.get("/api/novels/..%2F..%2Fetc/metadata")
    assert response.status_code == 404


def test_patch_metadata_merges_existing(client):
    test_client, novel_dir = client
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"title": "New Title", "illustration_url": "https://example.com/cover.jpg"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["title"] == "New Title"
    assert body["data"]["illustration_url"] == "https://example.com/cover.jpg"
    # Author preserved from existing metadata.
    assert body["data"]["author"] == "Old Author"
    # File on disk updated.
    on_disk = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["title"] == "New Title"
    assert on_disk["author"] == "Old Author"


def test_patch_metadata_empty_body_returns_422(client):
    test_client, _ = client
    response = test_client.patch("/api/novels/demo/metadata", json={})
    assert response.status_code == 422


def test_patch_metadata_translated_set_and_clear(client):
    test_client, novel_dir = client
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"translated": {"vi": "Tiêu đề", "en": "English Title"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["translated"] == {"vi": "Tiêu đề", "en": "English Title"}
    # Clearing one target keeps the other.
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"translated": {"vi": None}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["translated"] == {"en": "English Title"}


def test_patch_metadata_creates_file_if_missing(client):
    test_client, novel_dir = client
    (novel_dir / "metadata.json").unlink()
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"title": "Brand New"},
    )
    assert response.status_code == 200
    assert (novel_dir / "metadata.json").exists()
    on_disk = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["title"] == "Brand New"
