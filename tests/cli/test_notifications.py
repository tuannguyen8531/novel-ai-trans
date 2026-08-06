"""Tests for CLI translation notifications."""

from unittest.mock import patch

from src.application.translation.models import TranslationResult
from src.cli import notifications


class StubNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message: str, *, silent: bool | None = None) -> bool:
        self.messages.append(message)
        return True

    @staticmethod
    def escape(text: str) -> str:
        return text


def result(**overrides) -> TranslationResult:
    values = {
        "novel": "demo-novel",
        "total": 3,
        "success": 3,
        "failed": 0,
        "skipped": False,
        "dry_run": False,
        "chapters_attempted": [1, 2, 3],
        "failures": [],
        "started_at": 0.0,
        "finished_at": 1.0,
        "cancelled": False,
    }
    values.update(overrides)
    return TranslationResult(**values)


def notify(value: TranslationResult) -> list[str]:
    notifier = StubNotifier()
    with (
        patch.object(notifications, "get_notifier", return_value=notifier),
        patch.object(
            notifications,
            "format_run_footer",
            return_value="Start: 2026-01-01 00:00\nFinish: 2026-01-01 00:00\nRuntime: 0s",
        ),
    ):
        notifications.notify_translation_result(value)
    return notifier.messages


def test_notifies_success() -> None:
    assert notify(result()) == [
        "\n".join(
            [
                "Status: ✔️",
                "Task: Translate",
                "Novel: demo-novel",
                "Detail: Translation finished.",
                "Stats: Translated 3/3 · Failed 0/3",
                "Start: 2026-01-01 00:00",
                "Finish: 2026-01-01 00:00",
                "Runtime: 0s",
            ]
        )
    ]


def test_notifies_partial_failure() -> None:
    messages = notify(result(total=5, success=3, failed=2, failures=[4, 5]))

    assert "Status: ❌" in messages[0]
    assert "Detail: Translation finished with errors." in messages[0]
    assert "Stats: Translated 3/5 · Failed 2/5" in messages[0]


def test_notifies_interruption_as_success() -> None:
    messages = notify(result(total=5, success=2, cancelled=True))

    assert "Status: ✔️" in messages[0]
    assert "Detail: Translation interrupted." in messages[0]
    assert "Stats: Translated 2/5 · Failed 0/5" in messages[0]


def test_skipped_result_does_not_notify() -> None:
    assert notify(result(total=0, success=0, skipped=True)) == []


def test_notifies_failure_detail() -> None:
    notifier = StubNotifier()
    with (
        patch.object(notifications, "get_notifier", return_value=notifier),
        patch.object(
            notifications,
            "format_run_footer",
            return_value="Start: 2026-01-01 00:00\nFinish: 2026-01-01 00:00\nRuntime: 0s",
        ),
    ):
        notifications.notify_translation_failure(
            "demo-novel",
            "no input chapters",
            started_at=0.0,
        )

    assert notifier.messages == [
        "\n".join(
            [
                "Status: ❌",
                "Task: Translate",
                "Novel: demo-novel",
                "Detail: no input chapters",
                "Start: 2026-01-01 00:00",
                "Finish: 2026-01-01 00:00",
                "Runtime: 0s",
            ]
        )
    ]
