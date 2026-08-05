"""Spawned translation worker protocol and parent-side bridge."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import queue
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from src.application.config import config_scope
from src.application.novel import identity
from src.application.novel.localization import LocalizationResult, localize_metadata
from src.application.progress import ProgressEvent
from src.application.translation.models import TranslationRequest, TranslationResult
from src.application.translation.workflow import run_translation
from src.config import Config

_POLL_SECONDS = 0.05
_LOG_QUEUE_SIZE = 256


@dataclass(frozen=True)
class TranslationWorkerPayload:
    """Serializable inputs required by a translation child process."""

    job_id: str
    snapshot: Config
    request: TranslationRequest
    runtime_root: Path
    translate_metadata: bool = True
    force_metadata: bool = False


@dataclass(frozen=True)
class WorkerReady:
    pid: int


@dataclass(frozen=True)
class WorkerProgress:
    event: ProgressEvent


@dataclass(frozen=True)
class WorkerCompleted:
    result: TranslationResult
    metadata: LocalizationResult | None


@dataclass(frozen=True)
class WorkerFailed:
    code: str
    message: str
    details: dict[str, Any]


@dataclass(frozen=True)
class WorkerLog:
    message: str
    level: str


WorkerMessage = WorkerReady | WorkerProgress | WorkerCompleted | WorkerFailed
ProgressCallback = Callable[[ProgressEvent], None]
LogCallback = Callable[[WorkerLog], None]


class WorkerEntrypoint(Protocol):
    def __call__(self, payload: TranslationWorkerPayload, control_queue: Any, log_queue: Any, cancel_event: Any) -> None: ...


class TranslationWorkerError(RuntimeError):
    """A serialized application failure or abnormal child exit."""

    def __init__(self, message: str, *, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class _QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: Any) -> None:
        super().__init__()
        self._queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(
                WorkerLog(
                    message=self.format(record),
                    level=record.levelname.lower(),
                )
            )
        except queue.Full:
            return
        except Exception:
            self.handleError(record)


def _serializable_details(error: Exception) -> dict[str, Any]:
    raw = getattr(error, "details", None)
    details = raw if isinstance(raw, dict) else {}
    details = json.loads(json.dumps(details, default=str))
    details.setdefault("type", type(error).__name__)
    return details


def translation_worker_entry(
    payload: TranslationWorkerPayload,
    control_queue: Any,
    log_queue: Any,
    cancel_event: Any,
) -> None:
    """Run metadata localization and translation inside a spawned process."""
    handler = _QueueLogHandler(log_queue)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        control_queue.put(WorkerReady(pid=os.getpid()))
        with config_scope(payload.snapshot):
            metadata_result = None
            if payload.translate_metadata:
                control_queue.put(
                    WorkerProgress(
                        ProgressEvent(
                            kind="phase",
                            novel=payload.request.novel,
                            message=(
                                "Translating title and summary to "
                                f"{payload.request.target_language or payload.snapshot.target_language}..."
                            ),
                        )
                    )
                )
                metadata_result = localize_metadata(
                    identity.resolve_root(payload.snapshot.translated_dir),
                    payload.request.novel,
                    payload.request.target_language or payload.snapshot.target_language,
                    force=payload.force_metadata,
                    cancel_event=cast(threading.Event, cancel_event),
                )
            result = run_translation(
                payload.request,
                progress_callback=lambda event: control_queue.put(WorkerProgress(event)),
                cancel_event=cast(threading.Event, cancel_event),
                progress_root=payload.runtime_root / "progress",
                report_root=payload.runtime_root / "reports",
                transaction_root=payload.runtime_root / "transactions",
                lock_dir=payload.runtime_root / "locks",
            )
        control_queue.put(WorkerCompleted(result=result, metadata=metadata_result))
    except Exception as error:  # noqa: BLE001 - exceptions cross the process boundary as data
        control_queue.put(
            WorkerFailed(
                code=getattr(error, "code", "internal_error") or "internal_error",
                message=str(error) or type(error).__name__,
                details=_serializable_details(error),
            )
        )
    finally:
        root_logger.removeHandler(handler)


class TranslationWorker:
    """Own one spawned process and bridge its messages into parent callbacks."""

    def __init__(
        self,
        payload: TranslationWorkerPayload,
        *,
        entrypoint: WorkerEntrypoint = translation_worker_entry,
    ) -> None:
        self._payload = payload
        self._entrypoint = entrypoint
        self._context = multiprocessing.get_context("spawn")
        self._control_queue = self._context.Queue()
        self._log_queue = self._context.Queue(maxsize=_LOG_QUEUE_SIZE)
        self._cancel_event = self._context.Event()
        self._process = self._context.Process(
            target=self._entrypoint,
            args=(self._payload, self._control_queue, self._log_queue, self._cancel_event),
            name=f"translation-{payload.job_id}",
        )
        self._started = False
        self._queues_closed = False
        self._force_requested = False
        self._lock = threading.RLock()

    @property
    def pid(self) -> int | None:
        with self._lock:
            return self._process.pid

    @property
    def exitcode(self) -> int | None:
        with self._lock:
            return self._process.exitcode

    @property
    def is_alive(self) -> bool:
        with self._lock:
            return self._started and self._process.is_alive()

    def force_stop(self, *, grace_period: float = 2.0) -> None:
        """Terminate the child now, escalating to kill after the grace period."""
        if grace_period < 0:
            raise ValueError("Force-stop grace period cannot be negative.")
        with self._lock:
            self._force_requested = True
            self._cancel_event.set()
            if not self._started or not self._process.is_alive():
                return
            self._process.terminate()
            self._process.join(timeout=grace_period)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=grace_period)

    def run(
        self,
        *,
        progress_callback: ProgressCallback,
        log_callback: LogCallback,
        cancel_event: threading.Event,
    ) -> WorkerCompleted:
        with self._lock:
            if self._started:
                raise RuntimeError("Translation worker can only be started once.")
            if self._force_requested:
                self._close_queues()
                raise TranslationWorkerError(
                    "Translation worker was force-stopped before startup.",
                    code="forced_stop",
                    details={"forced": True},
                )
            self._started = True
            self._process.start()
        completed: WorkerCompleted | None = None
        failure: WorkerFailed | None = None
        try:
            while completed is None and failure is None:
                self._mirror_cancellation(cancel_event)
                self._drain_logs(log_callback)
                try:
                    message = self._control_queue.get(timeout=_POLL_SECONDS)
                except queue.Empty:
                    if self.is_alive:
                        continue
                    self._join()
                    completed, failure = self._drain_control(progress_callback, completed, failure)
                    if completed is None and failure is None:
                        raise TranslationWorkerError(
                            f"Translation worker exited without a result (exit code {self.exitcode}).",
                            code="worker_exit",
                            details={"exit_code": self.exitcode},
                        ) from None
                    break
                completed, failure = self._handle_message(message, progress_callback, completed, failure)

            while self.is_alive:
                self._mirror_cancellation(cancel_event)
                self._drain_logs(log_callback)
                self._join(timeout=_POLL_SECONDS)
            self._drain_logs(log_callback)
            if failure is not None:
                raise TranslationWorkerError(failure.message, code=failure.code, details=failure.details)
            assert completed is not None
            return completed
        finally:
            if not self.is_alive:
                self._join()
                self._close_queues()

    def _mirror_cancellation(self, cancel_event: threading.Event) -> None:
        if cancel_event.is_set() and not self._cancel_event.is_set():
            self._cancel_event.set()

    def _join(self, timeout: float | None = None) -> None:
        with self._lock:
            if self._started:
                self._process.join(timeout=timeout)

    def _drain_control(
        self,
        progress_callback: ProgressCallback,
        completed: WorkerCompleted | None,
        failure: WorkerFailed | None,
    ) -> tuple[WorkerCompleted | None, WorkerFailed | None]:
        while True:
            try:
                message = self._control_queue.get_nowait()
            except queue.Empty:
                return completed, failure
            completed, failure = self._handle_message(message, progress_callback, completed, failure)

    @staticmethod
    def _handle_message(
        message: object,
        progress_callback: ProgressCallback,
        completed: WorkerCompleted | None,
        failure: WorkerFailed | None,
    ) -> tuple[WorkerCompleted | None, WorkerFailed | None]:
        if isinstance(message, WorkerReady):
            return completed, failure
        if isinstance(message, WorkerProgress):
            progress_callback(message.event)
            return completed, failure
        if isinstance(message, WorkerCompleted):
            return message, failure
        if isinstance(message, WorkerFailed):
            return completed, message
        raise TranslationWorkerError(
            f"Translation worker sent an unsupported message: {type(message).__name__}.",
            code="worker_protocol",
        )

    def _drain_logs(self, log_callback: LogCallback) -> None:
        while True:
            try:
                message = self._log_queue.get_nowait()
            except queue.Empty:
                return
            if isinstance(message, WorkerLog):
                log_callback(message)

    def _close_queues(self) -> None:
        if self._queues_closed:
            return
        self._queues_closed = True
        for worker_queue in (self._control_queue, self._log_queue):
            with suppress(Exception):
                worker_queue.close()
            with suppress(Exception):
                worker_queue.join_thread()


def run_translation_worker(
    payload: TranslationWorkerPayload,
    *,
    progress_callback: ProgressCallback,
    log_callback: LogCallback,
    cancel_event: threading.Event,
) -> WorkerCompleted:
    """Spawn and synchronously bridge one translation worker."""
    return TranslationWorker(payload).run(
        progress_callback=progress_callback,
        log_callback=log_callback,
        cancel_event=cancel_event,
    )


__all__ = [
    "TranslationWorker",
    "TranslationWorkerError",
    "TranslationWorkerPayload",
    "WorkerCompleted",
    "WorkerFailed",
    "WorkerLog",
    "WorkerProgress",
    "WorkerReady",
    "run_translation_worker",
    "translation_worker_entry",
]
