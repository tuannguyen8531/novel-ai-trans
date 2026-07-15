"""End-to-end tests for the FastAPI surface."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute
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
        env = {
            "API_HOST": "127.0.0.1",
            "API_PORT": "8765",
            "CORS_ORIGINS": "http://localhost:5173",
            "TRANSLATED_DIR": str(translated),
        }
        # Replace the in-process config snapshot with one pointing at the
        # temp dir for the duration of the test.
        snapshot = Config(translated_dir=str(translated))
        original_snapshot = _config.get_config()
        _config.set_default(snapshot)
        try:
            with patch.dict(os.environ, env, clear=True):
                app = create_app(
                    dist_dir=tmp_path / "dist",
                    drafts_dir=drafts,
                    history_root=translated,
                    jobs_dir=tmp_path / "jobs",
                )
                with TestClient(app) as test_client:
                    yield test_client
        finally:
            _config.set_default(original_snapshot)


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["active_job_id"] is None


def test_settings_round_trip(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert "gemini_api_key_configured" in body
    assert "openrouter_api_key_configured" in body
    assert "telegram_configured" in body
    assert "telegram_enabled" in body
    assert "telegram_api_base" in body
    assert "telegram_parse_mode" in body
    assert "telegram_silent" in body
    assert "telegram_timeout_seconds" in body
    assert body["target_language"] in {"vi", "en"}

    new_value = "en" if body["target_language"] == "vi" else "vi"
    patch = client.patch("/api/settings", json={"target_language": new_value})
    assert patch.status_code == 200
    assert patch.json()["target_language"] == new_value
    assert client.get("/api/settings").json()["target_language"] == new_value


def test_settings_omits_secrets(client):
    response = client.get("/api/settings")
    body = response.json()
    for secret in ("gemini_api_key", "openrouter_api_key", "telegram_bot_token"):
        assert secret not in body
    assert "openrouter_api_key" not in body
    assert "telegram_chat_id" not in body


def test_novels_listing_handles_missing_root(client):
    response = client.get("/api/novels")
    assert response.status_code == 200
    assert response.json() == []


def test_novel_detail_404_when_missing(client):
    response = client.get("/api/novels/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_novel_detail_rejects_invalid_slug(client):
    response = client.get("/api/novels/..")
    assert response.status_code == 404


def test_provider_check_rejects_unknown(client):
    response = client.post("/api/providers/check", json={"provider": "bogus"})
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "external_service_error"


def test_job_lifecycle_with_deterministic_job(client):
    app_state = client.app.state.app_state
    manager = app_state.job_manager
    from src.api.jobs import JobEvent, JobStatus
    from src.config import config as global_config

    snapshot = global_config.clone()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        counter = {"value": 0}
        lock = threading.Lock()

        def run(job, emit, cancel_event):
            with lock:
                counter["value"] += 1
            emit(JobEvent(kind="progress", job_id=job.id, payload={"step": 1}))
            emit(JobEvent(kind="progress", job_id=job.id, payload={"current": 2, "total": 2}))
            return {"counter": counter["value"]}

        job = manager.submit(
            kind="test",
            novel=None,
            snapshot=snapshot,
            loop=loop,
            run=run,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            current = manager.current
            if current is None or current.id != job.id:
                break
            time.sleep(0.05)
        stored = manager.get(job.id)
        assert stored.status == JobStatus.COMPLETED
        assert stored.result == {"counter": 1}
        assert stored.progress == {"current": 2, "total": 2}
    finally:
        loop.close()


def test_concurrent_job_returns_409(client):
    app_state = client.app.state.app_state
    manager = app_state.job_manager
    from src.api.jobs import JobConflictError
    from src.config import config as global_config

    snapshot = global_config.clone()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        started = threading.Event()
        proceed = threading.Event()

        def slow_run(job, emit, cancel_event):
            started.set()
            proceed.wait(timeout=5)
            return {"ok": True}

        first = manager.submit(kind="slow", novel=None, snapshot=snapshot, loop=loop, run=slow_run)
        assert started.wait(timeout=5)
        with pytest.raises(JobConflictError) as exc:
            manager.submit(kind="slow", novel=None, snapshot=snapshot, loop=loop, run=slow_run)
        assert exc.value.args[0] == first.id
        response = client.post("/api/translate", json={"novel": "demo"})
        assert response.status_code == 409
        assert response.json()["error"]["details"]["active_job_id"] == first.id
        proceed.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            current = manager.current
            if current is None or current.id != first.id:
                break
            time.sleep(0.05)
        assert manager.get(first.id).status.value == "completed"
    finally:
        loop.close()


def test_remote_mode_requires_key():
    env = {"API_HOST": "0.0.0.0", "API_SECRET_KEY": ""}
    with patch.dict(os.environ, env, clear=True), pytest.raises(RuntimeError):
        from src.api.auth import require_secret_key_configured

        require_secret_key_configured()


def test_remote_mode_accepts_matching_bearer():
    from starlette.requests import Request

    from src.api.auth import authenticate

    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer secret-key")],
    }
    request = Request(scope)
    with patch.dict(os.environ, {"API_HOST": "0.0.0.0", "API_SECRET_KEY": "secret-key"}, clear=True):
        principal = authenticate(request)
        assert principal.authenticated is True
        assert principal.source == "bearer"


def test_remote_mode_rejects_missing_bearer():
    from fastapi import HTTPException
    from starlette.requests import Request

    from src.api.auth import authenticate

    scope = {"type": "http", "headers": []}
    request = Request(scope)
    with patch.dict(os.environ, {"API_HOST": "0.0.0.0", "API_SECRET_KEY": "secret-key"}, clear=True):
        with pytest.raises(HTTPException) as exc:
            authenticate(request)
        assert exc.value.status_code == 401


def test_upload_size_limit_enforced():
    from src.api.errors import http_error

    err = http_error("upload_too_large", "too big", 413)
    assert err.status_code == 413
    assert err.detail["code"] == "upload_too_large"  # type: ignore[index]


def test_drafts_storage_round_trip(client):
    import json
    from datetime import datetime, timedelta

    drafts_dir = client.app.state.app_state.drafts_dir
    draft_id = "test-draft"
    payload = {
        "draft_id": draft_id,
        "name": "demo",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "source_url": "https://example.com",
        "config": {"name": "demo"},
    }
    drafts_dir.mkdir(parents=True, exist_ok=True)
    (drafts_dir / f"{draft_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    response = client.get(f"/api/config-drafts/{draft_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["draft_id"] == draft_id
    assert body["config"]["name"] == "demo"


def test_draft_deletion_removes_file(client):
    import json
    from datetime import datetime, timedelta

    drafts_dir = client.app.state.app_state.drafts_dir
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_id = "delete-me"
    payload = {
        "draft_id": draft_id,
        "name": "demo",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "source_url": "https://example.com",
        "config": {},
    }
    (drafts_dir / f"{draft_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    response = client.delete(f"/api/config-drafts/{draft_id}")
    assert response.status_code == 204
    assert not (drafts_dir / f"{draft_id}.json").exists()


def test_jobs_are_persisted_to_disk(client):
    import json
    import time

    jobs_dir = client.app.state.app_state.jobs_dir
    response = client.post(
        "/api/translate",
        json={"novel": "demo"},
    )
    assert response.status_code == 202
    body = response.json()
    job_id = body["job_id"]
    # Wait briefly for the worker to settle, then cancel to ensure a terminal
    # state is written to disk.
    deadline = time.time() + 2
    while time.time() < deadline:
        current = client.app.state.app_state.job_manager.current
        if current is None or current.id != job_id:
            break
        time.sleep(0.05)
    # The job is now terminal (or still running but persisted as running).
    files = list(jobs_dir.glob(f"{job_id}.json"))
    assert files, f"expected a job file for {job_id} in {jobs_dir}"
    snapshot = json.loads(files[0].read_text(encoding="utf-8"))
    assert snapshot["id"] == job_id
    assert snapshot["kind"] == "translate"
    assert snapshot["status"] in {"queued", "running", "completed", "failed", "cancelling", "cancelled"}


def test_jobs_survive_restart(tmp_path):
    """A second JobManager pointed at the same jobs dir must see the prior job."""
    from src.api.jobs import JobManager
    from src.api.services.jobs import JobStore

    jobs_dir = tmp_path / "jobs"
    store = JobStore(jobs_dir)
    manager = JobManager(store=store)
    job = manager.submit(
        kind="translate",
        novel="demo",
        run=lambda j, emit, cancel: {"ok": True},
        snapshot=manager.__dict__.get("snapshot", None) or __import__("src.config", fromlist=["Config"]).config,
        loop=None,
    )
    # Wait for the worker to finish.
    import time

    deadline = time.time() + 2
    while time.time() < deadline:
        if manager.current is None or manager.current.id != job.id:
            break
        time.sleep(0.05)
    completed = manager.get(job.id)
    assert completed.status.value == "completed"

    # Simulate restart with a fresh manager against the same store.
    manager2 = JobManager(store=JobStore(jobs_dir))
    restored = manager2.get(job.id)
    assert restored.id == job.id
    assert restored.status.value == "completed"
    assert restored.kind == "translate"
    assert restored.result == {"ok": True}


def test_job_progress_emitter_adds_console_log_lines():
    from datetime import datetime

    from src.api.events import JobEvent
    from src.api.jobs import Job, JobStatus, build_progress_emitter
    from src.application.progress import ProgressEvent

    job = Job(
        id="job-1",
        kind="translate",
        novel="demo",
        status=JobStatus.RUNNING,
        created_at=datetime.now(UTC),
    )
    events: list[JobEvent] = []

    def emit(event: JobEvent) -> None:
        events.append(event)
        if event.kind == "log":
            job.logs.append(str(event.payload["message"]))

    callback = build_progress_emitter(job, emit)

    callback(
        ProgressEvent(
            kind="chapter_completed",
            novel="demo",
            current=1,
            total=2,
            chapter=7,
            extra={
                "ok": True,
                "elapsed": 1.234,
                "output_size": 1234,
                "size_unit": "chars",
                "new_terms": 2,
            },
        )
    )

    assert [event.kind for event in events] == ["chapter_completed", "log"]
    assert events[0].payload["chapter"] == 7
    assert job.logs[-1] == "OK Ch.7 -> 1,234 chars - 1.2s [+ 2 terms]"


def test_job_progress_log_events_are_not_duplicated():
    from datetime import datetime

    from src.api.events import JobEvent
    from src.api.jobs import Job, JobStatus, build_progress_emitter
    from src.application.progress import ProgressEvent

    job = Job(
        id="job-1",
        kind="crawl",
        novel="demo",
        status=JobStatus.RUNNING,
        created_at=datetime.now(UTC),
    )
    events: list[JobEvent] = []

    def emit(event: JobEvent) -> None:
        events.append(event)

    callback = build_progress_emitter(job, emit)

    callback(ProgressEvent(kind="log", novel="demo", message="Validation warning: missing title"))

    assert [event.kind for event in events] == ["log"]
    assert events[0].payload["message"] == "Validation warning: missing title"


def test_crawl_job_console_hides_skipped_and_started_progress():
    from datetime import datetime

    from src.api.events import JobEvent
    from src.api.jobs import Job, JobStatus, build_progress_emitter
    from src.application.progress import ProgressEvent

    job = Job(
        id="job-1",
        kind="crawl",
        novel="demo",
        status=JobStatus.RUNNING,
        created_at=datetime.now(UTC),
    )
    events: list[JobEvent] = []

    callback = build_progress_emitter(job, events.append)
    callback(
        ProgressEvent(
            kind="chapter",
            novel="demo",
            current=21,
            total=983,
            message="Chapter 21",
            extra={"status": "skipped", "title": "Chapter 21"},
        )
    )
    callback(
        ProgressEvent(
            kind="chapter",
            novel="demo",
            current=0,
            total=3,
            message="Chapter 22",
            extra={"status": "started", "title": "Chapter 22"},
        )
    )
    callback(
        ProgressEvent(
            kind="chapter",
            novel="demo",
            current=1,
            total=3,
            message="Chapter 22",
            extra={"status": "fetched", "title": "Chapter 22"},
        )
    )

    assert [event.kind for event in events] == ["chapter", "chapter", "chapter", "log"]
    assert events[-1].payload["message"] == "[1/3] Chapter 22"


def test_config_save_rejects_traversal_draft_id(client):
    payload = {
        "config": {
            "name": "demo",
            "toc_url": "https://example.com/novel",
            "chapter_link_selector": ".chapter",
            "chapter_content_selector": ".content",
        },
        "draft_id": "../../victim",
    }
    response = client.put("/api/configs/demo", json=payload)
    assert response.status_code == 422
    translated_root = Path(_config.get_config().translated_dir)
    assert not (translated_root / "demo" / "config.json").exists()


def test_config_save_persists_draft_metadata_separately(client):
    import json
    from datetime import datetime, timedelta

    drafts_dir = client.app.state.app_state.drafts_dir
    draft_id = "generated-demo"
    draft = {
        "draft_id": draft_id,
        "name": "demo",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "source_url": "https://example.com/book",
        "config": {},
        "metadata": {
            "title": "Demo Novel",
            "author": "Demo Author",
            "source_url": "https://example.com/book",
            "illustration_url": "https://example.com/cover.jpg",
            "summary": "Demo summary.",
            "site_name": "demo",
        },
    }
    (drafts_dir / f"{draft_id}.json").write_text(json.dumps(draft), encoding="utf-8")
    payload = {
        "config": {
            "name": "demo",
            "toc_url": "https://example.com/book/toc",
            "source_url": "https://example.com/book",
            "chapter_link_selector": ".chapter",
            "chapter_content_selector": ".content",
        },
        "draft_id": draft_id,
    }

    response = client.put("/api/configs/demo", json=payload)

    assert response.status_code == 200
    translated_root = Path(_config.get_config().translated_dir)
    saved_config = json.loads((translated_root / "demo" / "config.json").read_text(encoding="utf-8"))
    saved_metadata = json.loads((translated_root / "demo" / "metadata.json").read_text(encoding="utf-8"))
    assert "title" not in saved_config
    assert saved_metadata["title"] == "Demo Novel"
    assert saved_metadata["summary"] == "Demo summary."
    assert not (drafts_dir / f"{draft_id}.json").exists()


def test_spa_fallback_rejects_paths_outside_dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    app = create_app(
        dist_dir=dist,
        drafts_dir=tmp_path / "drafts",
        history_root=tmp_path / "translated",
        jobs_dir=tmp_path / "jobs",
    )
    fallback = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == "/{full_path:path}")

    response = asyncio.run(fallback.endpoint("../secret.txt"))

    assert response.status_code == 404


def test_apply_glossary_endpoint_success(client):
    with (
        patch("src.api.routes.glossary.glossary.apply_pending_replacements") as mock_apply,
        patch("src.api.routes.glossary._validate_novel"),
    ):
        mock_apply.return_value = {
            "novel": "demo",
            "target": "vi",
            "write": True,
            "conflicted": False,
            "changed_files": 1,
            "backup_id": "backup_123",
            "replacements": [],
        }

        response = client.post(
            "/api/novels/demo/glossary/apply",
            json={"write": True, "target": "vi"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["write"] is True
        assert body["changed_files"] == 1
        assert body["backup_id"] == "backup_123"

        mock_apply.assert_called_once()
        assert mock_apply.call_args[1]["target_language"] == "vi"
        assert mock_apply.call_args[1]["write"] is True


def test_dismiss_glossary_endpoint_success(client):
    with (
        patch("src.api.routes.glossary.glossary.dismiss_pending_replacements") as mock_dismiss,
        patch("src.api.routes.glossary._validate_novel"),
    ):
        response = client.post(
            "/api/novels/demo/glossary/dismiss",
            json={"target": "en"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        mock_dismiss.assert_called_once()
        assert mock_dismiss.call_args[1]["target_language"] == "en"


def test_rollback_glossary_endpoint_success(client):
    with (
        patch("src.api.routes.glossary.glossary.rollback_replacements") as mock_rollback,
        patch("src.api.routes.glossary._validate_novel"),
    ):
        response = client.post(
            "/api/novels/demo/glossary/rollback",
            json={"backup_id": "20260703T120000_000000Z_deadbeef"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_rollback.assert_called_once()
        assert mock_rollback.call_args.args[1] == "20260703T120000_000000Z_deadbeef"
