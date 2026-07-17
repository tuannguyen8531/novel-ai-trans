"""Application-owned run notification delivery."""

from __future__ import annotations

from src.services.notifier import send_run_notification as _send_run_notification


def send_run_notification(
    *,
    status: str,
    task: str,
    novel: str,
    detail: str,
    started_at: float,
    stats: str | None = None,
) -> None:
    _send_run_notification(
        status=status,
        task=task,
        novel=novel,
        detail=detail,
        started_at=started_at,
        stats=stats,
    )


__all__ = ["send_run_notification"]
