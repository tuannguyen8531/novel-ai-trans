"""Tests for the novel metadata endpoints."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
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
        novel_dir = translated / "demo"
        novel_dir.mkdir(parents=True)
        (novel_dir / "metadata.json").write_text(
            json.dumps({"title": "Old", "author": "Old Author"}),
            encoding="utf-8",
        )
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
                    yield test_client, novel_dir
        finally:
            _config.set_default(original)


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


def test_patch_metadata_rejects_legacy_translated_field(client):
    test_client, _ = client
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"translated": {"vi": "Tiêu đề", "en": "English Title"}},
    )
    assert response.status_code == 422


def test_patch_metadata_source_language_set_and_clear(client):
    test_client, novel_dir = client
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"source_language": "zh"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["source_language"] == "chinese"

    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"source_language": None},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["source_language"] is None

    on_disk = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk["source_language"] is None


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


def test_patch_metadata_deep_merges_localized_values_and_marks_manual(client):
    test_client, novel_dir = client
    response = test_client.patch(
        "/api/novels/demo/metadata",
        json={"localized": {"vi": {"title": "Tên truyện", "summary": "Tóm tắt"}}},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["localized"]["vi"] == {"title": "Tên truyện", "summary": "Tóm tắt"}
    assert data["localization_meta"]["vi"]["title"]["origin"] == "manual"
    assert json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8")) == data


def test_localize_metadata_endpoint_runs_as_job_with_mocked_llm(client):
    test_client, novel_dir = client
    (novel_dir / "metadata.json").write_text(
        json.dumps({"title": "Original", "summary": "Original summary", "source_language": "english"}),
        encoding="utf-8",
    )
    llm = type("FakeLlm", (), {"generate": lambda self, *_: '{"title":"Tên","summary":"Tóm tắt"}'})()

    with patch("src.application.localization.get_llm", return_value=llm):
        response = test_client.post(
            "/api/novels/demo/metadata/localize",
            json={"target_language": "vi"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        job: dict = {"status": "queued"}
        deadline = time.time() + 2
        while time.time() < deadline:
            job = test_client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in {"queued", "running", "cancelling"}:
                break
            time.sleep(0.01)

    assert job["status"] == "completed", job
    data = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))
    assert data["localized"]["vi"] == {"title": "Tên", "summary": "Tóm tắt"}
