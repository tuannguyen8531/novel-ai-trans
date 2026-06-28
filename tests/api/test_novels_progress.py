"""Tests for novel listing and progress computation."""

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
        snapshot = _global_config.clone(translated_dir=str(translated))
        original = _config_context.get_config()
        _config_context.set_default(snapshot)
        try:
            with patch.dict(os.environ, {"API_HOST": "127.0.0.1", "CORS_ORIGINS": "http://localhost:5173"}):
                app = create_app(
                    dist_dir=tmp_path / "dist",
                    drafts_dir=drafts,
                    history_root=translated,
                )
            with TestClient(app) as test_client:
                yield test_client, translated
        finally:
            _config_context.set_default(original)


def _write_chapter(parent: Path, number: int) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    (parent / f"chapter_{number:03d}.txt").write_text(f"chapter {number}", encoding="utf-8")


def test_progress_reflects_on_disk_output_when_progress_file_missing(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 4):
        _write_chapter(output_dir, i)
    # No progress.json file exists.

    response = test_client.get("/api/novels")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    targets = {t["target"]: t for t in body[0]["targets"]}
    assert targets["vi"]["completed"] == 3
    assert targets["vi"]["total"] == 5
    assert targets["en"]["completed"] == 0


def test_progress_unions_progress_file_with_on_disk_output(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 3):
        _write_chapter(output_dir, i)
    # Progress.json says chapters 3-5 are completed but only 1-2 are on disk.
    (novel / "progress.json").write_text(
        json.dumps({"completed": [3, 4, 5], "failed": []}),
        encoding="utf-8",
    )

    response = test_client.get("/api/novels")
    assert response.status_code == 200
    body = response.json()
    targets = {t["target"]: t for t in body[0]["targets"]}
    # Union of on-disk and progress file: {1, 2, 3, 4, 5}
    assert targets["vi"]["completed"] == 5


def test_failed_count_only_from_progress_file(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 4):
        _write_chapter(output_dir, i)
    (novel / "progress.json").write_text(
        json.dumps({"completed": [1, 2, 3], "failed": [4, 5]}),
        encoding="utf-8",
    )

    response = test_client.get("/api/novels")
    body = response.json()
    targets = {t["target"]: t for t in body[0]["targets"]}
    assert targets["vi"]["completed"] == 3
    assert targets["vi"]["failed"] == 2


def test_failed_count_reads_runtime_progress_written_by_translation(client, tmp_path):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    progress_dir = tmp_path / "progress"
    progress_dir.mkdir()
    (progress_dir / "demo.json").write_text(
        json.dumps({"completed": [], "failed": [1]}),
        encoding="utf-8",
    )

    with patch("src.api.routes.novels.PROGRESS_DIR", progress_dir):
        response = test_client.get("/api/novels")

    targets = {item["target"]: item for item in response.json()[0]["targets"]}
    assert targets["vi"]["failed"] == 1
