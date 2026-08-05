"""Contracts and errors for process-backed job controllers."""

from __future__ import annotations

from typing import Protocol


class ProcessController(Protocol):
    """Parent-owned handle for one process-backed job."""

    def force_stop(self, *, grace_period: float = 2.0) -> None: ...


class ForceStopConflictError(RuntimeError):
    """Raised when a job cannot be force-stopped in its current state."""


__all__ = ["ForceStopConflictError", "ProcessController"]
