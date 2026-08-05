"""Worker threads, configuration scope, and job log capture."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.api.background.models import Job, JobError, JobOutcome, JobStatus
from src.api.background.registry import JobRegistry
from src.api.background.streaming import EventBus
from src.api.events import JobEvent
from src.application.config import config_scope
from src.config import Config

_logger = logging.getLogger(__name__)
_active_log_job_id: ContextVar[str | None] = ContextVar("active_log_job_id", default=None)

JobCallback = Callable[[Job, Callable[[JobEvent], None], threading.Event], dict[str, Any] | JobOutcome]
PersistCallback = Callable[[Job], None]


@dataclass
class JobRequest:
    job: Job
    snapshot: Config
    run: JobCallback


class JobLogHandler(logging.Handler):
    def __init__(self, job: Job, emit: Callable[[JobEvent], None]) -> None:
        super().__init__()
        self._job = job
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if _active_log_job_id.get() != self._job.id:
                return
            self._emit(
                JobEvent(
                    kind="log",
                    job_id=self._job.id,
                    novel=self._job.novel,
                    payload={"message": self.format(record), "level": record.levelname.lower()},
                )
            )
        except Exception:
            self.handleError(record)


class JobRunner:
    """Execute jobs in worker threads and record their lifecycle outcome."""

    def __init__(
        self,
        registry: JobRegistry,
        bus: EventBus,
        persist: PersistCallback,
        lifecycle_lock: threading.RLock | None = None,
    ) -> None:
        self._registry = registry
        self._bus = bus
        self._persist = persist
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._lifecycle_lock = lifecycle_lock or threading.RLock()

    def start(self, request: JobRequest) -> None:
        def target() -> None:
            job = request.job
            if not self._registry.mark_running(job):
                return
            self._persist(job)
            assert job.started_at is not None
            self._bus.publish(
                JobEvent(
                    kind="started",
                    job_id=job.id,
                    novel=job.novel,
                    payload={"kind": job.kind, "started_at": job.started_at.isoformat()},
                )
            )
            try:
                copy_context().run(self._run, request)
            except Exception as error:  # noqa: BLE001 - top-level worker guard
                _logger.exception("Job %s crashed", job.id)
                self._finish_failed(job, code="internal_error", message=str(error))

        thread = threading.Thread(target=target, name=f"job-{request.job.id}", daemon=True)
        with self._lock:
            self._threads[request.job.id] = thread
        thread.start()

    def _run(self, request: JobRequest) -> None:
        job = request.job

        def emit(event: JobEvent) -> None:
            self._bus.publish(event)
            if event.kind == "log":
                message = event.payload.get("message") if event.payload else None
                if isinstance(message, str):
                    job.logs.append(message)
            payload = event.payload or {}
            if any(key in payload for key in {"current", "total", "pct", "chapter", "message"}):
                job.progress.update(payload)

        handler = JobLogHandler(job, emit)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        token = _active_log_job_id.set(job.id)
        with config_scope(request.snapshot):
            try:
                callback_result = request.run(job, emit, job.cancel_event)
            except Exception as error:  # noqa: BLE001 - callback errors become job failures
                raw_details = getattr(error, "details", None)
                self._finish_failed(
                    job,
                    code=getattr(error, "code", "internal_error") or "internal_error",
                    message=str(error) or type(error).__name__,
                    details=raw_details if isinstance(raw_details, dict) else None,
                )
                return
            finally:
                _active_log_job_id.reset(token)
                root_logger.removeHandler(handler)

        with self._lifecycle_lock:
            outcome = callback_result if isinstance(callback_result, JobOutcome) else JobOutcome(callback_result)
            if job.force_requested:
                job.status = JobStatus.CANCELLED
                job.result = {"forced": True}
            else:
                job.status = JobStatus.CANCELLED if job.status == JobStatus.CANCELLING else outcome.terminal_status
                job.result = outcome.result
            job.finished_at = datetime.now(UTC)
            self._bus.publish(
                JobEvent(
                    kind=job.status.value,
                    job_id=job.id,
                    novel=job.novel,
                    payload={"result": job.result},
                )
            )
            self._registry.finish(job)
            self.discard(job.id)
            self._persist(job)

    def _finish_failed(
        self,
        job: Job,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._lifecycle_lock:
            if job.force_requested:
                job.status = JobStatus.CANCELLED
                job.result = {"forced": True}
                job.error = None
                payload = {"result": job.result}
            else:
                job.status = JobStatus.CANCELLED if job.status == JobStatus.CANCELLING else JobStatus.FAILED
                job.error = JobError(code=code, message=message, details=details)
                payload = {"error": {"code": code, "message": message, "details": details}}
            job.finished_at = datetime.now(UTC)
            self._bus.publish(
                JobEvent(
                    kind=job.status.value,
                    job_id=job.id,
                    novel=job.novel,
                    payload=payload,
                )
            )
            self._registry.finish(job)
            self.discard(job.id)
            self._persist(job)

    def discard(self, job_id: str) -> None:
        with self._lock:
            self._threads.pop(job_id, None)

    def join_all(self, *, timeout: float) -> None:
        with self._lock:
            threads = list(self._threads.values())
        deadline = time.monotonic() + timeout
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if thread.is_alive():
                thread.join(timeout=remaining)


__all__ = ["JobCallback", "JobRequest", "JobRunner"]
