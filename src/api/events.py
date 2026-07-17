"""SSE event types and conversion from the application progress events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from src.api.background.models import Job


@dataclass
class JobEvent:
    kind: str
    job_id: str
    novel: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {"job_id": self.job_id}
        if self.novel is not None:
            data["novel"] = self.novel
        if self.payload:
            data.update(self.payload)
        return data

    def sse(self) -> dict[str, str]:
        import json

        return {
            "event": self.kind,
            "data": json.dumps(self.to_payload(), default=str, ensure_ascii=False),
        }


def event_from_application(job_id: str, application_event: Any) -> JobEvent:
    """Map an :class:`src.application.progress.ProgressEvent` to a :class:`JobEvent`."""
    payload: dict[str, Any] = {
        "current": getattr(application_event, "current", 0),
        "total": getattr(application_event, "total", 0),
    }
    if getattr(application_event, "chapter", None) is not None:
        payload["chapter"] = application_event.chapter
    if getattr(application_event, "pct", None) is not None:
        payload["pct"] = application_event.pct
    if getattr(application_event, "message", None):
        payload["message"] = application_event.message
    extras = getattr(application_event, "extra", None)
    if extras:
        for key, value in extras.items():
            payload[key] = value
    return JobEvent(kind=application_event.kind, job_id=job_id, novel=application_event.novel, payload=payload)


def public_dict(event: JobEvent) -> dict[str, Any]:
    return asdict(event)


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
    if kind in {"started", "dry_run", "phase"}:
        return str(message) if message else None
    if kind == "skipped":
        return "No chapters to translate."
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
        terms_message = f" [+ {new_terms} terms]" if new_terms > 0 else ""
        return f"OK Ch.{chapter} -> {int(output_size):,} {size_unit} - {elapsed:.1f}s{terms_message}"
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

    def callback(application_event: Any) -> None:
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

    return callback


__all__ = ["JobEvent", "build_progress_emitter", "event_from_application", "public_dict"]
