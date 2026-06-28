"""Typed progress event for long-running workflows.

Both translation and pack workflows emit :class:`ProgressEvent` instances to
the optional progress callback supplied by the caller. Adapters translate
this into SSE for the API or colored output for the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProgressEvent:
    """Single progress update from a long-running workflow."""

    kind: str
    novel: str | None = None
    current: int = 0
    total: int = 0
    chapter: int | None = None
    pct: float | None = None
    message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
