"""Filesystem-backed job persistence.

Each job is written to a single JSON file under ``runtime/jobs/{id}.json`` on
every state transition. Writes are atomic (write-to-tmp + replace) so a
crash mid-write can't leave a half-written file. On app startup the store
loads the most recent jobs into the in-memory deque and deletes anything
older than the retention window.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

DEFAULT_RETENTION = timedelta(days=7)


class JobStore:
    """Persists :class:`Job` snapshots as one JSON file per job id."""

    def __init__(self, root: Path, *, retention: timedelta = DEFAULT_RETENTION) -> None:
        self._root = Path(root)
        self._retention = retention
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, job_id: str) -> Path:
        # Job ids are UUID4 hex; still validate to keep the path inside root.
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError(f"Invalid job id: {job_id!r}")
        return self._root / f"{job_id}.json"

    def write(self, snapshot: dict[str, Any]) -> None:
        """Atomically write *snapshot* (a ``Job.public_dict()``) to disk."""
        path = self._path(snapshot["id"])
        data = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        with self._lock:
            fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(self._root))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data)
                os.replace(tmp_name, path)
            except Exception:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(tmp_name)
                raise

    def delete(self, job_id: str) -> None:
        path = self._path(job_id)
        with self._lock, contextlib.suppress(FileNotFoundError):
            path.unlink()

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _logger.warning("Failed to read job %s: %s", job_id, error)
            return None

    def iter_all(self) -> Iterator[dict[str, Any]]:
        if not self._root.exists():
            return
        for entry in sorted(self._root.glob("*.json"), key=_file_mtime, reverse=True):
            try:
                yield json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                _logger.warning("Skipping unreadable job file %s: %s", entry, error)

    def cleanup(self, *, now: datetime | None = None) -> int:
        """Delete files older than the retention window. Returns the count removed."""
        cutoff = (now or datetime.now(UTC)) - self._retention
        removed = 0
        for entry in list(self._root.glob("*.json")):
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def job_to_snapshot(job: Any) -> dict[str, Any]:
    """Convert a :class:`Job` to a JSON-serializable snapshot."""
    snapshot = job.public_dict()
    return snapshot


def snapshot_to_job(snapshot: dict[str, Any]) -> Any:
    """Reconstruct a :class:`Job` from a snapshot dict (without cancel_event)."""
    # Local import to avoid a cycle: jobs.py is the canonical owner of Job.
    from src.api.jobs import Job, JobError, JobStatus

    status = JobStatus(snapshot["status"])
    error_data = snapshot.get("error")
    error = (
        JobError(
            code=error_data["code"],
            message=error_data["message"],
            details=error_data.get("details"),
        )
        if error_data
        else None
    )
    from collections import deque

    return Job(
        id=snapshot["id"],
        kind=snapshot["kind"],
        novel=snapshot.get("novel"),
        status=status,
        created_at=datetime.fromisoformat(snapshot["created_at"]),
        started_at=(datetime.fromisoformat(snapshot["started_at"]) if snapshot.get("started_at") else None),
        finished_at=(datetime.fromisoformat(snapshot["finished_at"]) if snapshot.get("finished_at") else None),
        progress=dict(snapshot.get("progress") or {}),
        result=snapshot.get("result"),
        error=error,
        logs=deque(maxlen=500),  # empty; logs are not persisted to keep files small
    )


__all__ = ["JobStore", "job_to_snapshot", "snapshot_to_job", "DEFAULT_RETENTION"]
