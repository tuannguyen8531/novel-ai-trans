"""Job lifecycle model and single-executor JobManager.

The JobManager is responsible for:

- accepting at most one top-level long job at a time (409 otherwise);
- running the job in a dedicated background thread;
- emitting :class:`JobEvent` instances to subscribed SSE clients via an
  asyncio.Queue that lives in the FastAPI event loop;
- exposing the current job plus a bounded recent-history list;
- supporting cooperative cancellation through ``threading.Event``.

Job worker callbacks run outside the API event-loop thread. Events are
delivered with ``loop.call_soon_threadsafe(queue.put_nowait, event)`` so
the asyncio queue is only touched from the loop thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextvars import copy_context
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.api.events import JobEvent, event_from_application
from src.api.services.job_store import JobStore, job_to_snapshot
from src.api.services.job_store import snapshot_to_job as _snapshot_to_job
from src.application.config_context import config_scope
from src.config import Config

_logger = logging.getLogger(__name__)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


@dataclass
class JobError:
    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class Job:
    id: str
    kind: str
    novel: str | None
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: JobError | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=500))
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def public_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "kind": self.kind,
            "novel": self.novel,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "progress": dict(self.progress),
            "result": self.result,
            "error": asdict(self.error) if self.error else None,
            "logs": list(self.logs) if self.logs is not None else [],
        }
        return data


class JobConflictError(RuntimeError):
    """Raised when a new job is submitted while another is active."""


class JobNotFoundError(LookupError):
    """Raised when a job id is unknown."""


class _JobLogHandler(logging.Handler):
    def __init__(self, job: Job, emit: Callable[[JobEvent], None]) -> None:
        super().__init__()
        self._job = job
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self._emit(
                JobEvent(
                    kind="log",
                    job_id=self._job.id,
                    novel=self._job.novel,
                    payload={"message": message, "level": record.levelname.lower()},
                )
            )
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Event subscriber queue
# ---------------------------------------------------------------------------


class EventBus:
    """Thread-safe event bus that fans out to per-subscriber queues.

    Worker callbacks call :meth:`publish` from any thread. Each subscriber
    owns a :class:`queue.Queue` and a reference to the running asyncio
    loop. Subscribers consume events from their queue in the loop thread.
    """

    def __init__(self) -> None:
        self._subscribers: list[_Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, loop) -> _Subscriber:
        sub = _Subscriber(loop)
        with self._lock:
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)
        sub.close()

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            sub.deliver(event)


class _Subscriber:
    def __init__(self, loop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[JobEvent | None] = asyncio.Queue(maxsize=1024)
        self._closed = False

    def deliver(self, event: JobEvent) -> None:
        if self._closed:
            return

        def _put() -> None:
            if self._closed:
                return
            try:
                self.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Keep live state moving for slow subscribers. REST remains
                # authoritative and reconciles any dropped intermediate event.
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    self.queue.put_nowait(event)

        try:
            self.loop.call_soon_threadsafe(_put)
        except RuntimeError:
            # Loop is closed; drop the event.
            pass

    def close(self) -> None:
        self._closed = True

        def _close() -> None:
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(None)

        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(_close)


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------


@dataclass
class _JobRequest:
    job: Job
    snapshot: Config
    run: Callable[[Job, Callable[[JobEvent], None], threading.Event], dict[str, Any]]
    progress_factory: Callable[[], Callable[[Any], None]] | None = None
    loop: Any = None  # running asyncio loop captured at submit time


class JobManager:
    """Single-executor job manager."""

    HISTORY_LIMIT_DEFAULT = 50

    def __init__(
        self,
        *,
        history_limit: int = HISTORY_LIMIT_DEFAULT,
        store: JobStore | None = None,
    ) -> None:
        self._current: Job | None = None
        self._history: deque[Job] = deque(maxlen=history_limit)
        self._lock = threading.Lock()
        self._bus = EventBus()
        self._thread: threading.Thread | None = None
        self._wake_event = threading.Event()
        self._store = store
        if store is not None:
            self._restore_from_store()

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    @property
    def current(self) -> Job | None:
        with self._lock:
            return self._current

    def list_history(self) -> list[Job]:
        with self._lock:
            return list(self._history)

    def _persist(self, job: Job) -> None:
        if self._store is None:
            return
        try:
            self._store.write(job_to_snapshot(job))
        except Exception as error:  # noqa: BLE001 - persistence must never break a job
            _logger.warning("Failed to persist job %s: %s", job.id, error)

    def _restore_from_store(self) -> None:
        """Repopulate the in-memory deque from disk on startup.

        Active jobs found on disk are left as-is (they died with the previous
        process); only terminal jobs go into history.
        """
        assert self._store is not None
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        for snapshot in self._store.iter_all():
            try:
                job = _snapshot_to_job(snapshot)
            except Exception as error:  # noqa: BLE001
                _logger.warning("Skipping invalid job snapshot: %s", error)
                continue
            if job.status in terminal:
                with self._lock:
                    self._history.append(job)
            else:
                # Active jobs from a previous run cannot be safely resumed.
                # Persist them as failed so the user sees the interruption.
                job.status = JobStatus.FAILED
                job.error = JobError(code="interrupted", message="Server restarted while job was running.")
                job.finished_at = job.finished_at or datetime.now(UTC)
                with self._lock:
                    self._history.appendleft(job)
                self._store.write(job_to_snapshot(job))

    def get(self, job_id: str) -> Job:
        with self._lock:
            if self._current and self._current.id == job_id:
                return self._current
            for job in self._history:
                if job.id == job_id:
                    return job
        raise JobNotFoundError(job_id)

    # ------------------------------------------------------------------ submit

    def submit(
        self,
        *,
        kind: str,
        novel: str | None,
        run: Callable[[Job, Callable[[JobEvent], None], threading.Event], dict[str, Any]],
        snapshot: Config,
        loop: Any,
    ) -> Job:
        with self._lock:
            current = self._current
            if current and current.status in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.CANCELLING,
            }:
                raise JobConflictError(current.id)
            job = Job(
                id=str(uuid.uuid4()),
                kind=kind,
                novel=novel,
                status=JobStatus.QUEUED,
                created_at=datetime.now(UTC),
            )
            self._current = job
        self._persist(job)
        self._bus.publish(JobEvent(kind="queued", job_id=job.id, novel=novel, payload={"kind": kind}))
        request = _JobRequest(job=job, snapshot=snapshot, run=run, loop=loop)
        self._start_worker(request)
        return job

    def _start_worker(self, request: _JobRequest) -> None:
        def _target() -> None:
            job = request.job
            with self._lock:
                if job.status == JobStatus.CANCELLED:
                    return
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(UTC)
            self._persist(job)
            self._bus.publish(
                JobEvent(
                    kind="started",
                    job_id=job.id,
                    novel=job.novel,
                    payload={"kind": job.kind, "started_at": job.started_at.isoformat()},
                )
            )
            try:
                ctx = copy_context()
                ctx.run(self._run_job, request)
            except Exception as error:  # noqa: BLE001 - top-level guard
                _logger.exception("Job %s crashed", job.id)
                self._finish_failed(job, code="internal_error", message=str(error))

        thread = threading.Thread(target=_target, name=f"job-{request.job.id}", daemon=True)
        self._thread = thread
        thread.start()

    def _run_job(self, request: _JobRequest) -> None:
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

        handler = _JobLogHandler(job, emit)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        with config_scope(request.snapshot):
            try:
                result = request.run(job, emit, job.cancel_event)
            except Exception as error:  # noqa: BLE001
                self._finish_failed(
                    job,
                    code=getattr(error, "code", "internal_error") or "internal_error",
                    message=str(error) or type(error).__name__,
                )
                return
            finally:
                root_logger.removeHandler(handler)

        if job.status == JobStatus.CANCELLING:
            job.status = JobStatus.CANCELLED
        else:
            job.status = JobStatus.COMPLETED
        job.result = result
        job.finished_at = datetime.now(UTC)
        self._bus.publish(
            JobEvent(
                kind=job.status.value,
                job_id=job.id,
                novel=job.novel,
                payload={"result": result},
            )
        )
        with self._lock:
            if self._current and self._current.id == job.id:
                self._current = None
            self._history.appendleft(job)
        self._persist(job)

    def _finish_failed(self, job: Job, *, code: str, message: str) -> None:
        if job.status == JobStatus.CANCELLING:
            job.status = JobStatus.CANCELLED
        else:
            job.status = JobStatus.FAILED
        job.error = JobError(code=code, message=message)
        job.finished_at = datetime.now(UTC)
        self._bus.publish(
            JobEvent(
                kind=job.status.value,
                job_id=job.id,
                novel=job.novel,
                payload={"error": {"code": code, "message": message}},
            )
        )
        with self._lock:
            if self._current and self._current.id == job.id:
                self._current = None
            self._history.appendleft(job)
        self._persist(job)

    # ----------------------------------------------------------------- cancel

    def request_cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            return job
        if job.status == JobStatus.QUEUED:
            job.cancel_event.set()
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            self._bus.publish(JobEvent(kind="cancelled", job_id=job.id, novel=job.novel))
            with self._lock:
                if self._current and self._current.id == job.id:
                    self._current = None
                self._history.appendleft(job)
            self._persist(job)
            return job
        job.status = JobStatus.CANCELLING
        job.cancel_event.set()
        self._persist(job)
        self._bus.publish(JobEvent(kind="cancelling", job_id=job.id, novel=job.novel))
        return job

    def shutdown(self, timeout: float = 5.0) -> None:
        current = self.current
        if current and current.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            self.request_cancel(current.id)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Event conversion from the application layer
# ---------------------------------------------------------------------------


def build_progress_emitter(
    job: Job,
    emit: Callable[[JobEvent], None],
) -> Callable[[Any], None]:
    """Build a callback that updates job state and publishes progress."""

    def _callback(application_event: Any) -> None:
        emit(event_from_application(job.id, application_event))

    return _callback


__all__ = [
    "Job",
    "JobError",
    "JobStatus",
    "JobManager",
    "JobConflictError",
    "JobNotFoundError",
    "EventBus",
]


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_dict(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def iter_history(manager: JobManager) -> Iterator[Job]:
    return iter(manager.list_history())
