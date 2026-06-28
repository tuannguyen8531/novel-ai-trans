"""Tests for the filesystem-backed job store."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.api.services.job_store import (
    JobStore,
    job_to_snapshot,
    snapshot_to_job,
)


def _make_snapshot(job_id: str = "abc123", status: str = "completed") -> dict:
    return {
        "id": job_id,
        "kind": "translate",
        "novel": "demo",
        "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:01+00:00",
        "finished_at": "2026-01-01T00:00:10+00:00",
        "progress": {"current": 1, "total": 1},
        "result": {"success": 1},
        "error": None,
        "logs": [],
    }


def test_write_creates_file_and_overwrites(tmp_path: Path):
    store = JobStore(tmp_path)
    snap = _make_snapshot()
    store.write(snap)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8")) == snap

    # Overwrite with new content; same file, no leftover temps.
    snap["result"] = {"success": 2}
    store.write(snap)
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert len(list(tmp_path.glob("*.tmp"))) == 0
    assert json.loads(files[0].read_text(encoding="utf-8"))["result"] == {"success": 2}


def test_write_is_atomic_under_concurrent_writes(tmp_path: Path):
    store = JobStore(tmp_path)
    snapshot = _make_snapshot()
    errors: list[Exception] = []

    def writer(start: int) -> None:
        try:
            for i in range(50):
                snap = dict(snapshot)
                snap["result"] = {"iteration": start * 100 + i}
                store.write(snap)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    final = json.loads((tmp_path / "abc123.json").read_text(encoding="utf-8"))
    assert final["id"] == "abc123"


def test_get_returns_none_for_missing(tmp_path: Path):
    store = JobStore(tmp_path)
    assert store.get("nope") is None


def test_iter_all_returns_all_persisted_jobs(tmp_path: Path):
    store = JobStore(tmp_path)
    for i in range(3):
        store.write(_make_snapshot(job_id=f"job-{i}"))
    ids = {snap["id"] for snap in store.iter_all()}
    assert ids == {"job-0", "job-1", "job-2"}


def test_cleanup_removes_files_older_than_retention(tmp_path: Path):
    store = JobStore(tmp_path, retention=timedelta(days=7))
    store.write(_make_snapshot(job_id="old"))
    store.write(_make_snapshot(job_id="new"))
    old_file = tmp_path / "old.json"
    new_file = tmp_path / "new.json"
    # Backdate the old file
    old_mtime = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    import os

    os.utime(old_file, (old_mtime, old_mtime))
    new_mtime = datetime.now(UTC).timestamp()
    os.utime(new_file, (new_mtime, new_mtime))

    removed = store.cleanup()
    assert removed == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_path_traversal_rejected(tmp_path: Path):
    store = JobStore(tmp_path)
    with pytest.raises(ValueError):
        store.write(_make_snapshot(job_id="../../etc/passwd"))


def test_snapshot_roundtrip():
    snap = _make_snapshot()
    snap["error"] = {"code": "boom", "message": "it broke", "details": {"x": 1}}
    job = snapshot_to_job(snap)
    out = job_to_snapshot(job)
    assert out["id"] == snap["id"]
    assert out["status"] == snap["status"]
    assert out["error"] == snap["error"]
    assert out["progress"] == snap["progress"]


def test_iter_all_skips_unreadable_files(tmp_path: Path, caplog):
    store = JobStore(tmp_path)
    store.write(_make_snapshot(job_id="good"))
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    ids = {snap["id"] for snap in store.iter_all()}
    assert ids == {"good"}
