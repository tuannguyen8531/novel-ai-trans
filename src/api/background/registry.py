"""In-memory background job state and conflict rules."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import UTC, datetime

from src.api.background.models import ACTIVE_STATUSES, Job, JobStatus


class JobConflictError(RuntimeError):
    """Raised when a submitted job conflicts with an active job."""


class JobNotFoundError(LookupError):
    """Raised when a job id is unknown."""


class JobRegistry:
    """Own active and historical jobs plus their conflict semantics."""

    def __init__(self, *, history_limit: int = 50) -> None:
        self._active: dict[str, Job] = {}
        self._history: deque[Job] = deque(maxlen=history_limit)
        self._lock = threading.Lock()

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

    def get(self, job_id: str) -> Job:
        with self._lock:
            if job_id in self._active:
                return self._active[job_id]
            for job in self._history:
                if job.id == job_id:
                    return job
        raise JobNotFoundError(job_id)

    def create(self, *, kind: str, novel: str | None) -> Job:
        with self._lock:
            for active in self._active.values():
                if jobs_conflict(active, novel=novel):
                    raise JobConflictError(active.id)
            job = Job(
                id=str(uuid.uuid4()),
                kind=kind,
                novel=novel,
                status=JobStatus.QUEUED,
                created_at=datetime.now(UTC),
            )
            self._active[job.id] = job
            return job

    def add_history(self, job: Job, *, newest: bool = False) -> None:
        with self._lock:
            if newest:
                self._history.appendleft(job)
            else:
                self._history.append(job)

    def mark_running(self, job: Job) -> bool:
        with self._lock:
            if job.status == JobStatus.CANCELLED:
                return False
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            return True

    def finish(self, job: Job) -> None:
        with self._lock:
            self._active.pop(job.id, None)
            self._history.appendleft(job)

    def request_cancel(self, job: Job) -> JobStatus | None:
        with self._lock:
            if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
                return None
            job.cancel_event.set()
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.now(UTC)
                self._active.pop(job.id, None)
                self._history.appendleft(job)
            else:
                job.status = JobStatus.CANCELLING
            return job.status

    def request_force_stop(self, job: Job) -> JobStatus | None:
        with self._lock:
            if job.status not in ACTIVE_STATUSES:
                return None
            job.force_requested = True
            job.cancel_event.set()
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.result = {"forced": True}
                job.finished_at = datetime.now(UTC)
                self._active.pop(job.id, None)
                self._history.appendleft(job)
            else:
                job.status = JobStatus.CANCELLING
            return job.status

    def delete(self, job_id: str) -> bool:
        with self._lock:
            active = self._active.get(job_id)
            if active is not None:
                if active.status in ACTIVE_STATUSES:
                    raise ValueError("Cannot delete an active job.")
                self._active.pop(job_id, None)
                return True

            for job in self._history:
                if job.id != job_id:
                    continue
                if job.status in ACTIVE_STATUSES:
                    raise ValueError("Cannot delete an active job.")
                self._history.remove(job)
                return True
            return False

    def clear_inactive(self) -> list[str]:
        """Clear terminal memory state and return stale active ids removed."""
        with self._lock:
            self._history = deque(
                [job for job in self._history if job.status in ACTIVE_STATUSES],
                maxlen=self._history.maxlen,
            )
            stale_ids: list[str] = []
            for job_id, job in list(self._active.items()):
                if job.status not in ACTIVE_STATUSES:
                    self._active.pop(job_id, None)
                    stale_ids.append(job_id)
            return stale_ids


def jobs_conflict(active: Job, *, novel: str | None) -> bool:
    """Return whether an active job conflicts with a requested novel scope."""
    if active.status not in ACTIVE_STATUSES:
        return False
    if active.novel is None or novel is None:
        return True
    return active.novel == novel


__all__ = ["JobConflictError", "JobNotFoundError", "JobRegistry", "jobs_conflict"]
