"""Thin coordination for background job lifecycle collaborators."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.api.background.models import ACTIVE_STATUSES, TERMINAL_STATUSES, Job, JobError, JobStatus
from src.api.background.registry import JobNotFoundError, JobRegistry
from src.api.background.runner import JobCallback, JobRequest, JobRunner
from src.api.background.streaming import EventBus
from src.api.events import JobEvent
from src.api.services.jobs import JobStore, job_to_snapshot, snapshot_to_job
from src.config import Config

_logger = logging.getLogger(__name__)


class JobManager:
    """Coordinate job state, execution, streaming, and persistence."""

    HISTORY_LIMIT_DEFAULT = 50

    def __init__(
        self,
        *,
        history_limit: int = HISTORY_LIMIT_DEFAULT,
        store: JobStore | None = None,
    ) -> None:
        self._store = store
        self._registry = JobRegistry(history_limit=history_limit)
        self._bus = EventBus()
        self._runner = JobRunner(self._registry, self._bus, self._persist)
        if store is not None:
            self._restore_from_store()

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    @property
    def current(self) -> Job | None:
        return self._registry.current

    def list_active(self) -> list[Job]:
        return self._registry.list_active()

    def list_history(self) -> list[Job]:
        return self._registry.list_history()

    def get(self, job_id: str) -> Job:
        return self._registry.get(job_id)

    def submit(
        self,
        *,
        kind: str,
        novel: str | None,
        run: JobCallback,
        snapshot: Config,
        loop: Any,
    ) -> Job:
        del loop  # Retained in the adapter contract; streaming owns event-loop delivery.
        job = self._registry.create(kind=kind, novel=novel)
        self._persist(job)
        self._bus.publish(JobEvent(kind="queued", job_id=job.id, novel=novel, payload={"kind": kind}))
        self._runner.start(JobRequest(job=job, snapshot=snapshot, run=run))
        return job

    def request_cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        status = self._registry.request_cancel(job)
        if status is None:
            return job
        if status == JobStatus.CANCELLED:
            self._bus.publish(JobEvent(kind="cancelled", job_id=job.id, novel=job.novel))
            self._runner.discard(job.id)
        else:
            self._bus.publish(JobEvent(kind="cancelling", job_id=job.id, novel=job.novel))
        self._persist(job)
        return job

    def delete(self, job_id: str) -> None:
        if self._registry.delete(job_id):
            self._runner.discard(job_id)
            if self._store:
                self._store.delete(job_id)
            return

        if self._store:
            snapshot = self._store.get(job_id)
            if snapshot:
                if snapshot.get("status") in {status.value for status in ACTIVE_STATUSES}:
                    raise ValueError("Cannot delete an active job.")
                self._store.delete(job_id)
                return
        raise JobNotFoundError(job_id)

    def clear_inactive(self) -> None:
        for job_id in self._registry.clear_inactive():
            self._runner.discard(job_id)
        if self._store:
            for snapshot in list(self._store.iter_all()):
                if snapshot.get("status") in {status.value for status in TERMINAL_STATUSES}:
                    self._store.delete(snapshot["id"])

    def shutdown(self, timeout: float = 5.0) -> None:
        for job in self.list_active():
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                self.request_cancel(job.id)
        self._runner.join_all(timeout=timeout)

    def _persist(self, job: Job) -> None:
        if self._store is None:
            return
        try:
            self._store.write(job_to_snapshot(job))
        except Exception as error:  # noqa: BLE001 - persistence must never break a job
            _logger.warning("Failed to persist job %s: %s", job.id, error)

    def _restore_from_store(self) -> None:
        assert self._store is not None
        for snapshot in self._store.iter_all():
            try:
                job = snapshot_to_job(snapshot)
            except Exception as error:  # noqa: BLE001 - invalid history must not block startup
                _logger.warning("Skipping invalid job snapshot: %s", error)
                continue
            if job.status in TERMINAL_STATUSES:
                self._registry.add_history(job)
                continue
            job.status = JobStatus.FAILED
            job.error = JobError(code="interrupted", message="Server restarted while job was running.")
            job.finished_at = job.finished_at or datetime.now(UTC)
            self._registry.add_history(job, newest=True)
            self._store.write(job_to_snapshot(job))


__all__ = ["JobManager"]
