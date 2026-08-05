from __future__ import annotations

import os
import queue
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from src.api.translation.worker import (
    TranslationWorker,
    TranslationWorkerError,
    TranslationWorkerPayload,
    WorkerCompleted,
    WorkerLog,
    WorkerReady,
)
from src.application.locks import novel_lock
from src.application.translation.models import TranslationRequest, TranslationResult
from src.config import Config


def _cancel_entry(payload: TranslationWorkerPayload, control_queue: Any, log_queue: Any, cancel_event: Any) -> None:
    control_queue.put(WorkerReady(pid=os.getpid()))
    log_queue.put_nowait(WorkerLog(message="worker awaiting cancellation", level="info"))
    cancel_event.wait(timeout=5)
    control_queue.put(
        WorkerCompleted(
            result=TranslationResult(
                novel=payload.request.novel,
                total=1,
                success=0,
                failed=0,
                skipped=False,
                dry_run=False,
                chapters_attempted=[],
                failures=[],
                started_at=0.0,
                finished_at=1.0,
                cancelled=cancel_event.is_set(),
            ),
            metadata=None,
        )
    )


def _crash_entry(payload: TranslationWorkerPayload, control_queue: Any, log_queue: Any, cancel_event: Any) -> None:
    del payload, control_queue, log_queue, cancel_event
    os._exit(17)


def _blocking_entry(payload: TranslationWorkerPayload, control_queue: Any, log_queue: Any, cancel_event: Any) -> None:
    del control_queue, log_queue, cancel_event
    lock_dir = payload.runtime_root / "locks"
    with novel_lock(payload.request.novel, lock_dir=lock_dir):
        payload.runtime_root.mkdir(parents=True, exist_ok=True)
        (payload.runtime_root / "worker-ready").write_text("ready", encoding="utf-8")
        while True:
            time.sleep(0.1)


def _noisy_entry(payload: TranslationWorkerPayload, control_queue: Any, log_queue: Any, cancel_event: Any) -> None:
    del cancel_event
    for index in range(2_000):
        with suppress(queue.Full):
            log_queue.put_nowait(WorkerLog(message=f"log {index}", level="info"))
    control_queue.put(
        WorkerCompleted(
            result=TranslationResult(
                novel=payload.request.novel,
                total=0,
                success=0,
                failed=0,
                skipped=True,
                dry_run=False,
                chapters_attempted=[],
                failures=[],
                started_at=0.0,
                finished_at=1.0,
            ),
            metadata=None,
        )
    )


def _payload(
    tmp_path: Path,
    *,
    dry_run: bool = True,
    translate_metadata: bool = False,
) -> TranslationWorkerPayload:
    return TranslationWorkerPayload(
        job_id="test-job",
        snapshot=Config(translated_dir=str(tmp_path / "translated")),
        request=TranslationRequest(novel="demo", dry_run=dry_run),
        runtime_root=tmp_path / "runtime",
        translate_metadata=translate_metadata,
    )


def test_spawned_worker_runs_translation_and_bridges_progress(tmp_path: Path) -> None:
    input_dir = tmp_path / "translated" / "demo" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")
    (input_dir.parent / "metadata.json").write_text("{}", encoding="utf-8")
    progress = []
    logs: list[WorkerLog] = []
    worker = TranslationWorker(_payload(tmp_path, translate_metadata=True))

    completed = worker.run(
        progress_callback=progress.append,
        log_callback=logs.append,
        cancel_event=threading.Event(),
    )

    assert worker.pid is not None
    assert worker.pid != os.getpid()
    assert worker.exitcode == 0
    assert completed.result.dry_run is True
    assert completed.result.chapters_attempted == [1]
    assert completed.metadata is not None
    assert completed.metadata.skipped == ["title", "summary"]
    assert [event.kind for event in progress] == ["phase", "dry_run"]
    assert (tmp_path / "runtime" / "locks").is_dir()


def test_spawned_worker_serializes_application_failure(tmp_path: Path) -> None:
    worker = TranslationWorker(_payload(tmp_path))

    with pytest.raises(TranslationWorkerError) as caught:
        worker.run(
            progress_callback=lambda event: None,
            log_callback=lambda log: None,
            cancel_event=threading.Event(),
        )

    assert caught.value.code == "not_found"
    assert caught.value.details["type"] == "ResourceNotFoundError"


def test_spawned_worker_mirrors_parent_cancellation_and_logs(tmp_path: Path) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    logs: list[WorkerLog] = []
    worker = TranslationWorker(_payload(tmp_path, dry_run=False), entrypoint=_cancel_entry)

    completed = worker.run(
        progress_callback=lambda event: None,
        log_callback=logs.append,
        cancel_event=cancel_event,
    )

    assert completed.result.cancelled is True
    assert [log.message for log in logs] == ["worker awaiting cancellation"]


def test_spawned_worker_reports_abnormal_exit(tmp_path: Path) -> None:
    worker = TranslationWorker(_payload(tmp_path), entrypoint=_crash_entry)

    with pytest.raises(TranslationWorkerError) as caught:
        worker.run(
            progress_callback=lambda event: None,
            log_callback=lambda log: None,
            cancel_event=threading.Event(),
        )

    assert caught.value.code == "worker_exit"
    assert caught.value.details == {"exit_code": 17}


def test_force_stop_terminates_blocking_worker_and_releases_novel_lock(tmp_path: Path) -> None:
    worker = TranslationWorker(_payload(tmp_path, dry_run=False), entrypoint=_blocking_entry)
    caught: list[BaseException] = []

    def run() -> None:
        try:
            worker.run(
                progress_callback=lambda event: None,
                log_callback=lambda log: None,
                cancel_event=threading.Event(),
            )
        except BaseException as error:  # noqa: BLE001 - asserted after the worker thread joins
            caught.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    ready = tmp_path / "runtime" / "worker-ready"
    deadline = time.monotonic() + 5
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()

    started = time.monotonic()
    worker.force_stop(grace_period=0.1)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert time.monotonic() - started < 2
    assert not worker.is_alive
    assert len(caught) == 1
    assert isinstance(caught[0], TranslationWorkerError)
    assert caught[0].code == "worker_exit"
    with novel_lock("demo", lock_dir=tmp_path / "runtime" / "locks"):
        pass


def test_force_stop_before_start_prevents_child_creation(tmp_path: Path) -> None:
    worker = TranslationWorker(_payload(tmp_path))
    worker.force_stop(grace_period=0)

    with pytest.raises(TranslationWorkerError) as caught:
        worker.run(
            progress_callback=lambda event: None,
            log_callback=lambda log: None,
            cancel_event=threading.Event(),
        )

    assert caught.value.code == "forced_stop"
    assert worker.pid is None


def test_lossy_log_pressure_does_not_block_reliable_result(tmp_path: Path) -> None:
    worker = TranslationWorker(_payload(tmp_path), entrypoint=_noisy_entry)
    logs: list[WorkerLog] = []

    completed = worker.run(
        progress_callback=lambda event: None,
        log_callback=logs.append,
        cancel_event=threading.Event(),
    )

    assert completed.result.skipped is True
    assert not worker.is_alive
    assert 0 < len(logs) <= 2_000
