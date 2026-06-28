"""SSE event types and conversion from the application progress events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
