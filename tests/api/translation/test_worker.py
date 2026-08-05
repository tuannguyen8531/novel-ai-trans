from __future__ import annotations

import os
import threading
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
