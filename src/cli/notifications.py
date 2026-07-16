"""CLI translation notification formatting and delivery."""

from __future__ import annotations

from src.application.translation.models import TranslationResult
from src.services.notifier import format_run_footer, get_notifier


def notify_translation_result(result: TranslationResult, *, started_at: float | None = None) -> None:
    """Notify the configured chat about a completed translation result."""
    if result.skipped:
        return

    notifier = get_notifier()
    title = notifier.escape(result.novel) if result.novel else "novel"
    started = started_at if started_at is not None else result.started_at
    if result.cancelled:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation interrupted.\n"
            f"Stats: Translated: {result.success}/{result.total}"
        )
    elif result.failed > 0:
        message = (
            "Status: Failed\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished with errors.\n"
            f"Stats: Translated: {result.success}/{result.total} · Failed: {result.failed}"
        )
    else:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished.\n"
            f"Stats: Translated: {result.success}/{result.total}"
        )
    notifier.send(message + "\n" + format_run_footer(started))


def notify_translation_failure(novel: str, detail: str, *, started_at: float) -> None:
    """Notify the configured chat about a CLI translation failure."""
    notifier = get_notifier()
    title = notifier.escape(novel) if novel else "novel"
    message = (
        "Status: Failed\n"
        "Task: Translation\n"
        f"Novel: {title}\n"
        f"Detail: {notifier.escape(detail) if detail else 'Translation failed.'}"
    )
    notifier.send(message + "\n" + format_run_footer(started_at))
