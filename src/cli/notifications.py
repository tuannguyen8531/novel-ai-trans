"""CLI translation notification formatting and delivery."""

from __future__ import annotations

from src.application.translation.models import TranslationResult
from src.services.notifier import format_run_footer, format_status, get_notifier


def escape_notification(value: str) -> str:
    return get_notifier().escape(value)


def notify_crawl_failure(novel: str, detail: str, *, started_at: float) -> None:
    notifier = get_notifier()
    notifier.send(
        f"Status: {format_status('Failed')}\n"
        "Task: Crawl\n"
        f"Novel: {notifier.escape(novel)}\n"
        f"Detail: {notifier.escape(detail)}\n"
        f"{format_run_footer(started_at)}"
    )


def notify_crawl_result(
    novel: str,
    *,
    failed: int,
    fetched: int,
    total: int,
    started_at: float,
) -> None:
    notifier = get_notifier()
    status = "Success" if failed == 0 else "Failed"
    detail = "Crawl finished." if failed == 0 else "Crawl finished with chapter errors."
    notifier.send(
        f"Status: {format_status(status)}\n"
        "Task: Crawl\n"
        f"Novel: {notifier.escape(novel)}\n"
        f"Detail: {detail}\n"
        f"Stats: New {fetched}/{total} · Failed {failed}/{total}\n"
        f"{format_run_footer(started_at)}"
    )


def notify_translation_result(result: TranslationResult, *, started_at: float | None = None) -> None:
    """Notify the configured chat about a completed translation result."""
    if result.skipped:
        return

    notifier = get_notifier()
    title = notifier.escape(result.novel) if result.novel else "novel"
    started = started_at if started_at is not None else result.started_at
    if result.cancelled:
        message = (
            f"Status: {format_status('Success')}\n"
            "Task: Translate\n"
            f"Novel: {title}\n"
            "Detail: Translation interrupted.\n"
            f"Stats: Translated {result.success}/{result.total} · Failed {result.failed}/{result.total}"
        )
    elif result.failed > 0:
        message = (
            f"Status: {format_status('Failed')}\n"
            "Task: Translate\n"
            f"Novel: {title}\n"
            "Detail: Translation finished with errors.\n"
            f"Stats: Translated {result.success}/{result.total} · Failed {result.failed}/{result.total}"
        )
    else:
        message = (
            f"Status: {format_status('Success')}\n"
            "Task: Translate\n"
            f"Novel: {title}\n"
            "Detail: Translation finished.\n"
            f"Stats: Translated {result.success}/{result.total} · Failed {result.failed}/{result.total}"
        )
    notifier.send(message + "\n" + format_run_footer(started))


def notify_translation_failure(novel: str, detail: str, *, started_at: float) -> None:
    """Notify the configured chat about a CLI translation failure."""
    notifier = get_notifier()
    title = notifier.escape(novel) if novel else "novel"
    message = (
        f"Status: {format_status('Failed')}\n"
        "Task: Translate\n"
        f"Novel: {title}\n"
        f"Detail: {notifier.escape(detail) if detail else 'Translation failed.'}"
    )
    notifier.send(message + "\n" + format_run_footer(started_at))


__all__ = [
    "escape_notification",
    "notify_crawl_failure",
    "notify_crawl_result",
    "notify_translation_failure",
    "notify_translation_result",
]
