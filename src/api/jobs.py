"""Job lifecycle model and bounded-concurrency JobManager.

The JobManager is responsible for:

- accepting multiple long jobs when their novel locks do not conflict;
- running the job in a dedicated background thread;
- emitting :class:`JobEvent` instances to subscribed SSE clients via an
  asyncio.Queue that lives in the FastAPI event loop;
- exposing active jobs plus a bounded recent-history list;
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
from contextvars import ContextVar, copy_context
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from src.api.events import JobEvent, event_from_application
from src.api.services.jobs import JobStore, job_to_snapshot
from src.api.services.jobs import snapshot_to_job as _snapshot_to_job
from src.application.config import config_scope
from src.config import Config

_logger = logging.getLogger(__name__)
_active_log_job_id: ContextVar[str | None] = ContextVar("active_log_job_id", default=None)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


_ACTIVE_STATUSES: Final = frozenset({JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING})


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
            if _active_log_job_id.get() != self._job.id:
                return
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

        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(_put)

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
    """Run non-conflicting jobs concurrently while keeping one active job per novel."""

    HISTORY_LIMIT_DEFAULT = 50

    def __init__(
        self,
        *,
        history_limit: int = HISTORY_LIMIT_DEFAULT,
        store: JobStore | None = None,
    ) -> None:
        self._active: dict[str, Job] = {}
        self._history: deque[Job] = deque(maxlen=history_limit)
        self._lock = threading.Lock()
        self._bus = EventBus()
        self._threads: dict[str, threading.Thread] = {}
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
            return min(self._active.values(), key=lambda job: (job.created_at, job.id), default=None)

    def list_active(self) -> list[Job]:
        with self._lock:
            return sorted(self._active.values(), key=lambda job: job.created_at)

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
            if job_id in self._active:
                return self._active[job_id]
            for job in self._history:
                if job.id == job_id:
                    return job
        raise JobNotFoundError(job_id)

    @staticmethod
    def _job_conflicts(active: Job, *, novel: str | None) -> bool:
        if active.status not in _ACTIVE_STATUSES:
            return False
        if active.novel is None or novel is None:
            return True
        return active.novel == novel

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
            for active in self._active.values():
                if self._job_conflicts(active, novel=novel):
                    raise JobConflictError(active.id)
            job = Job(
                id=str(uuid.uuid4()),
                kind=kind,
                novel=novel,
                status=JobStatus.QUEUED,
                created_at=datetime.now(UTC),
            )
            self._active[job.id] = job
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
        with self._lock:
            self._threads[request.job.id] = thread
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
        token = _active_log_job_id.set(job.id)
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
                _active_log_job_id.reset(token)
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
            self._active.pop(job.id, None)
            self._threads.pop(job.id, None)
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
            self._active.pop(job.id, None)
            self._threads.pop(job.id, None)
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
                self._active.pop(job.id, None)
                self._threads.pop(job.id, None)
                self._history.appendleft(job)
            self._persist(job)
            return job
        job.status = JobStatus.CANCELLING
        job.cancel_event.set()
        self._persist(job)
        self._bus.publish(JobEvent(kind="cancelling", job_id=job.id, novel=job.novel))
        return job

    def delete(self, job_id: str) -> None:
        with self._lock:
            # Check if it's an active/running job
            if job_id in self._active:
                if self._active[job_id].status in _ACTIVE_STATUSES:
                    raise ValueError("Cannot delete an active job.")
                self._active.pop(job_id, None)
                self._threads.pop(job_id, None)
                if self._store:
                    self._store.delete(job_id)
                return

            # Check history
            found_job = None
            for job in self._history:
                if job.id == job_id:
                    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING}:
                        raise ValueError("Cannot delete an active job.")
                    found_job = job
                    break

            if found_job:
                self._history.remove(found_job)
                if self._store:
                    self._store.delete(job_id)
                return

            # Try to find in store
            if self._store:
                snapshot = self._store.get(job_id)
                if snapshot:
                    if snapshot.get("status") in {JobStatus.QUEUED.value, JobStatus.RUNNING.value, JobStatus.CANCELLING.value}:
                        raise ValueError("Cannot delete an active job.")
                    self._store.delete(job_id)
                    return

            raise JobNotFoundError(job_id)

    def clear_inactive(self) -> None:
        with self._lock:
            # Filter memory history
            new_history = deque([job for job in self._history if job.status in _ACTIVE_STATUSES], maxlen=self._history.maxlen)
            self._history = new_history

            # Drop any stale non-active entries from the active map.
            for job_id, job in list(self._active.items()):
                if job.status not in _ACTIVE_STATUSES:
                    self._active.pop(job_id, None)
                    self._threads.pop(job_id, None)

            # Filter disk store
            if self._store:
                for snapshot in list(self._store.iter_all()):
                    status_val = snapshot.get("status")
                    if status_val in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                        self._store.delete(snapshot["id"])

    def shutdown(self, timeout: float = 5.0) -> None:
        active = self.list_active()
        for job in active:
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                self.request_cancel(job.id)
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Event conversion from the application layer
# ---------------------------------------------------------------------------


def _format_console_progress(application_event: Any) -> str | None:
    """Render progress events as terminal-like log lines for the web UI."""
    kind = getattr(application_event, "kind", "")
    message = getattr(application_event, "message", None)
    current = getattr(application_event, "current", 0) or 0
    total = getattr(application_event, "total", 0) or 0
    chapter = getattr(application_event, "chapter", None)
    extra = getattr(application_event, "extra", None) or {}

    if kind == "log":
        return None
    if kind == "started":
        return str(message) if message else None
    if kind == "dry_run":
        return str(message) if message else None
    if kind == "skipped":
        return "No chapters to translate."
    if kind == "phase":
        return str(message) if message else None
    if kind == "chapter_started" and chapter is not None:
        size = extra.get("source_size", extra.get("file_size", 0))
        size_unit = extra.get("size_unit", "chars")
        prefix = f"[{current}/{total}] " if total else ""
        return f"{prefix}Ch.{chapter} start ({int(size):,} {size_unit})"
    if kind == "chapter_completed" and chapter is not None:
        output_size = extra.get("output_size", extra.get("chars_out", 0))
        size_unit = extra.get("size_unit", "chars")
        elapsed = float(extra.get("elapsed", 0.0) or 0.0)
        new_terms = int(extra.get("new_terms", 0) or 0)
        terms_msg = f" [+ {new_terms} terms]" if new_terms > 0 else ""
        return f"OK Ch.{chapter} -> {int(output_size):,} {size_unit} - {elapsed:.1f}s{terms_msg}"
    if kind == "chapter_failed":
        error = extra.get("error")
        label = f"Ch.{chapter}" if chapter is not None else "Chapter"
        return f"FAIL {label}: {error or 'unknown error'}"
    if kind == "chapter":
        status = str(extra.get("status", "")).lower()
        if status in {"started", "skipped"}:
            return None
        title = extra.get("title") or message or "chapter"
        prefix = f"[{current}/{total}] " if total else ""
        if status == "failed":
            return f"{prefix}{title} (fail: {extra.get('error') or 'unknown error'})"
        if status == "fetched":
            return f"{prefix}{title}"
        return f"{prefix}{title} ({status or kind})"
    if kind == "chapter_loaded" and chapter is not None:
        return str(message) if message else f"Reading chapter {chapter}"
    if kind == "completed":
        return str(message) if message else f"Completed {current}/{total}" if total else "Completed"
    if kind == "completed_with_errors":
        return f"Completed with errors {current}/{total}" if total else "Completed with errors"
    if kind == "cancelled":
        return str(message) if message else f"Cancelled {current}/{total}" if total else "Cancelled"
    return str(message) if message else None


def build_progress_emitter(
    job: Job,
    emit: Callable[[JobEvent], None],
) -> Callable[[Any], None]:
    """Build a callback that updates job state and publishes progress."""

    def _callback(application_event: Any) -> None:
        emit(event_from_application(job.id, application_event))
        console_line = _format_console_progress(application_event)
        if console_line:
            emit(
                JobEvent(
                    kind="log",
                    job_id=job.id,
                    novel=getattr(application_event, "novel", None),
                    payload={"message": console_line, "level": "info", "source": "progress"},
                )
            )

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
