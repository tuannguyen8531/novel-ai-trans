"""Tests for the filesystem-backed job store."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.api.background.controllers import ForceStopConflictError
from src.api.background.manager import JobManager
from src.api.background.models import TERMINAL_STATUSES, JobOutcome, JobStatus
from src.api.background.registry import JobNotFoundError
from src.api.events import JobEvent
from src.api.services.jobs import (
    JobStore,
    job_to_snapshot,
    snapshot_to_job,
)
from src.config import Config


class _ImmediateLoop:
    def call_soon_threadsafe(self, callback, *args) -> None:
        callback(*args)


class _ProcessController:
    def __init__(self) -> None:
        self.stopped = threading.Event()
        self.calls = 0

    def force_stop(self, *, grace_period: float = 2.0) -> None:
        del grace_period
        self.calls += 1
        self.stopped.set()


def _wait_for_terminal(manager: JobManager, job_id: str):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.status in TERMINAL_STATUSES:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not finish")


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


def test_manager_records_lifecycle_progress_logs_events_and_history(tmp_path: Path):
    store = JobStore(tmp_path)
    manager = JobManager(store=store)
    subscriber = manager.event_bus.subscribe(_ImmediateLoop())

    def run(job, emit, cancel_event):
        emit(
            JobEvent(
                kind="progress",
                job_id=job.id,
                novel=job.novel,
                payload={"current": 1, "total": 2, "message": "Halfway"},
            )
        )
        emit(JobEvent(kind="log", job_id=job.id, novel=job.novel, payload={"message": "explicit log"}))
        logging.getLogger("tests.phase0.jobs").warning("captured worker log")
        return {"ok": True}

    submitted = manager.submit(kind="translate", novel="demo", snapshot=Config(), loop=None, run=run)
    finished = _wait_for_terminal(manager, submitted.id)

    events = []
    while not subscriber.queue.empty():
        event = subscriber.queue.get_nowait()
        if event is not None:
            events.append(event)
    manager.event_bus.unsubscribe(subscriber)

    assert finished.status == JobStatus.COMPLETED
    assert finished.result == {"ok": True}
    assert finished.progress == {
        "current": 1,
        "total": 2,
        "message": "captured worker log",
        "level": "warning",
    }
    assert "explicit log" in finished.logs
    assert "captured worker log" in finished.logs
    assert manager.list_active() == []
    assert manager.list_history()[0].id == submitted.id
    assert [event.kind for event in events][0:2] == ["queued", "started"]
    assert {event.kind for event in events} >= {"queued", "started", "progress", "log", "completed"}
    persisted = store.get(submitted.id)
    assert persisted is not None
    assert persisted["status"] == "completed"
    assert persisted["result"] == {"ok": True}


def test_manager_restores_terminal_jobs_and_marks_interrupted_jobs_failed(tmp_path: Path):
    store = JobStore(tmp_path)
    store.write(_make_snapshot(job_id="completed", status="completed"))
    store.write(_make_snapshot(job_id="partial", status="degraded"))
    interrupted = _make_snapshot(job_id="interrupted", status="running")
    interrupted["finished_at"] = None
    store.write(interrupted)

    manager = JobManager(store=store)

    completed = manager.get("completed")
    partial = manager.get("partial")
    failed = manager.get("interrupted")
    assert completed.status == JobStatus.COMPLETED
    assert partial.status == JobStatus.DEGRADED
    assert failed.status == JobStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "interrupted"
    assert {job.id for job in manager.list_history()} == {"completed", "partial", "interrupted"}
    persisted = store.get("interrupted")
    assert persisted is not None
    assert persisted["status"] == "failed"


def test_manager_persists_and_streams_degraded(tmp_path: Path):
    store = JobStore(tmp_path)
    manager = JobManager(store=store)
    subscriber = manager.event_bus.subscribe(_ImmediateLoop())

    def run(job, emit, cancel_event):
        return JobOutcome(
            result={"success": 2, "failed": 1},
            terminal_status=JobStatus.DEGRADED,
        )

    submitted = manager.submit(kind="translate", novel="demo", snapshot=Config(), loop=None, run=run)
    finished = _wait_for_terminal(manager, submitted.id)
    events = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        while not subscriber.queue.empty():
            event = subscriber.queue.get_nowait()
            if event is not None:
                events.append(event)
        if any(event.kind == "degraded" for event in events):
            break
        time.sleep(0.01)
    while not subscriber.queue.empty():
        event = subscriber.queue.get_nowait()
        if event is not None:
            events.append(event)
    manager.event_bus.unsubscribe(subscriber)

    assert finished.status == JobStatus.DEGRADED
    assert events[-1].kind == "degraded"
    assert events[-1].payload == {"result": {"success": 2, "failed": 1}}
    persisted = store.get(submitted.id)
    assert persisted is not None
    assert persisted["status"] == "degraded"


def test_manager_records_worker_failure():
    manager = JobManager()

    def fail(job, emit, cancel_event):
        raise RuntimeError("provider failed")

    submitted = manager.submit(kind="translate", novel="demo", snapshot=Config(), loop=None, run=fail)
    failed = _wait_for_terminal(manager, submitted.id)

    assert failed.status == JobStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "internal_error"
    assert failed.error.message == "provider failed"
    assert manager.list_history()[0].id == submitted.id


def test_manager_shutdown_cancels_running_jobs_for_all_novels():
    manager = JobManager()
    started = {"a": threading.Event(), "b": threading.Event()}

    def wait_for_cancel(job, emit, cancel_event):
        assert job.novel is not None
        started[job.novel].set()
        assert cancel_event.wait(timeout=5)
        return {"cancel_seen": True}

    first = manager.submit(kind="crawl", novel="a", snapshot=Config(), loop=None, run=wait_for_cancel)
    second = manager.submit(kind="translate", novel="b", snapshot=Config(), loop=None, run=wait_for_cancel)
    assert started["a"].wait(timeout=5)
    assert started["b"].wait(timeout=5)

    manager.shutdown(timeout=5)

    assert manager.get(first.id).status == JobStatus.CANCELLED
    assert manager.get(second.id).status == JobStatus.CANCELLED
    assert first.cancel_event.is_set()
    assert second.cancel_event.is_set()


def test_manager_force_stops_queued_process_job_without_starting_worker(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    manager = JobManager(store=store)
    with patch.object(manager._runner, "start") as start:  # noqa: SLF001 - hold the job in its queued state
        submitted = manager.submit(
            kind="translate",
            novel="demo",
            snapshot=Config(),
            loop=None,
            run=lambda job, emit, cancel_event: {"ok": True},
            process_backed=True,
        )

    stopped = manager.force_stop(submitted.id)
    repeated = manager.force_stop(submitted.id)

    start.assert_called_once()
    assert stopped is repeated
    assert stopped.status == JobStatus.CANCELLED
    assert stopped.result == {"forced": True}
    assert stopped.cancel_event.is_set()
    persisted = store.get(stopped.id)
    assert persisted is not None
    assert persisted["status"] == "cancelled"
    assert persisted["result"] == {"forced": True}


def test_manager_force_stop_rejects_non_process_job() -> None:
    manager = JobManager()
    started = threading.Event()
    proceed = threading.Event()

    def run(job, emit, cancel_event):
        started.set()
        proceed.wait(timeout=5)
        return {"ok": True}

    submitted = manager.submit(kind="crawl", novel="demo", snapshot=Config(), loop=None, run=run)
    try:
        assert started.wait(timeout=5)
        with pytest.raises(ForceStopConflictError, match="process-backed"):
            manager.force_stop(submitted.id)
    finally:
        proceed.set()
    _wait_for_terminal(manager, submitted.id)


def test_manager_force_stops_registered_process_and_persists_forced_result(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    manager = JobManager(store=store)
    controller = _ProcessController()
    registered = threading.Event()

    def run(job, emit, cancel_event):
        manager.register_process(job.id, controller)
        registered.set()
        try:
            assert controller.stopped.wait(timeout=5)
            raise RuntimeError("worker exited after termination")
        finally:
            manager.unregister_process(job.id, controller)

    submitted = manager.submit(
        kind="translate",
        novel="demo",
        snapshot=Config(),
        loop=None,
        run=run,
        process_backed=True,
    )
    assert registered.wait(timeout=5)

    stopping = manager.force_stop(submitted.id, grace_period=0.01)
    finished = _wait_for_terminal(manager, submitted.id)
    repeated = manager.force_stop(submitted.id)

    assert stopping.status in {JobStatus.CANCELLING, JobStatus.CANCELLED}
    assert controller.calls == 1
    assert finished is repeated
    assert finished.status == JobStatus.CANCELLED
    assert finished.result == {"forced": True}
    assert finished.error is None
    persisted = store.get(finished.id)
    assert persisted is not None
    assert persisted["status"] == "cancelled"
    assert persisted["result"] == {"forced": True}


def test_manager_force_request_before_controller_registration_stops_on_registration() -> None:
    manager = JobManager()
    controller = _ProcessController()
    callback_started = threading.Event()
    register_now = threading.Event()

    def run(job, emit, cancel_event):
        callback_started.set()
        assert register_now.wait(timeout=5)
        manager.register_process(job.id, controller)
        try:
            assert controller.stopped.wait(timeout=5)
            raise RuntimeError("stopped before process startup")
        finally:
            manager.unregister_process(job.id, controller)

    submitted = manager.submit(
        kind="translate",
        novel="demo",
        snapshot=Config(),
        loop=None,
        run=run,
        process_backed=True,
    )
    assert callback_started.wait(timeout=5)
    manager.force_stop(submitted.id, grace_period=0)
    register_now.set()
    finished = _wait_for_terminal(manager, submitted.id)

    assert controller.calls == 1
    assert finished.status == JobStatus.CANCELLED
    assert finished.result == {"forced": True}


def test_manager_force_stop_rejects_clean_terminal_job() -> None:
    manager = JobManager()
    submitted = manager.submit(
        kind="translate",
        novel="demo",
        snapshot=Config(),
        loop=None,
        run=lambda job, emit, cancel_event: {"ok": True},
        process_backed=True,
    )
    _wait_for_terminal(manager, submitted.id)

    with pytest.raises(ForceStopConflictError, match="already finished"):
        manager.force_stop(submitted.id)


def test_manager_shutdown_escalates_process_job_after_cooperative_timeout() -> None:
    manager = JobManager()
    controller = _ProcessController()
    registered = threading.Event()

    def run(job, emit, cancel_event):
        manager.register_process(job.id, controller)
        registered.set()
        try:
            assert controller.stopped.wait(timeout=5)
            raise RuntimeError("terminated during shutdown")
        finally:
            manager.unregister_process(job.id, controller)

    submitted = manager.submit(
        kind="translate",
        novel="demo",
        snapshot=Config(),
        loop=None,
        run=run,
        process_backed=True,
    )
    assert registered.wait(timeout=5)

    manager.shutdown(timeout=0.01)
    finished = _wait_for_terminal(manager, submitted.id)

    assert controller.calls == 1
    assert finished.status == JobStatus.CANCELLED
    assert finished.result == {"forced": True}


def test_manager_rejects_active_deletion_then_deletes_completed_job(tmp_path: Path):
    store = JobStore(tmp_path)
    manager = JobManager(store=store)
    started = threading.Event()
    proceed = threading.Event()

    def slow_run(job, emit, cancel_event):
        started.set()
        proceed.wait(timeout=5)
        return {"ok": True}

    submitted = manager.submit(kind="crawl", novel="demo", snapshot=Config(), loop=None, run=slow_run)
    try:
        assert started.wait(timeout=5)
        with pytest.raises(ValueError, match="Cannot delete an active job"):
            manager.delete(submitted.id)
    finally:
        proceed.set()

    _wait_for_terminal(manager, submitted.id)
    manager.delete(submitted.id)

    with pytest.raises(JobNotFoundError):
        manager.get(submitted.id)
    assert store.get(submitted.id) is None


def test_iter_all_skips_unreadable_files(tmp_path: Path, caplog):
    store = JobStore(tmp_path)
    store.write(_make_snapshot(job_id="good"))
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    ids = {snap["id"] for snap in store.iter_all()}
    assert ids == {"good"}
