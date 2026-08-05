"""Background job lifecycle models."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


ACTIVE_STATUSES: Final = frozenset({JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING})
TERMINAL_STATUSES: Final = frozenset({JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.FAILED, JobStatus.CANCELLED})


@dataclass(frozen=True)
class JobOutcome:
    """Public callback result with an explicit non-failure terminal status."""

    result: dict[str, Any]
    terminal_status: JobStatus = JobStatus.COMPLETED

    def __post_init__(self) -> None:
        allowed = {JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.CANCELLED}
        if self.terminal_status not in allowed:
            raise ValueError(f"Callbacks cannot finish with status {self.terminal_status.value!r}.")


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
    process_backed: bool = False
    force_requested: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
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


__all__ = ["ACTIVE_STATUSES", "TERMINAL_STATUSES", "Job", "JobError", "JobOutcome", "JobStatus"]
