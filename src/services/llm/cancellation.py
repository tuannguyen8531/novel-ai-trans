"""Context-local cooperative cancellation for LLM calls and retry waits."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event

_CANCEL_EVENT: ContextVar[Event | None] = ContextVar("llm_cancel_event", default=None)


class GenerationCancelledError(RuntimeError):
    """Raised at an LLM safe point after cooperative cancellation."""


@contextmanager
def cancellation_scope(cancel_event: Event | None) -> Iterator[None]:
    token = _CANCEL_EVENT.set(cancel_event)
    try:
        yield
    finally:
        _CANCEL_EVENT.reset(token)


def check_cancelled() -> None:
    cancel_event = _CANCEL_EVENT.get()
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelledError("LLM generation cancelled.")


def wait_for_retry(delay: float) -> None:
    cancel_event = _CANCEL_EVENT.get()
    if cancel_event is None:
        time.sleep(delay)
        return
    if cancel_event.wait(timeout=delay):
        raise GenerationCancelledError("LLM retry cancelled.")


__all__ = ["GenerationCancelledError", "cancellation_scope", "check_cancelled", "wait_for_retry"]
