"""Tests for pure translation chapter selection."""

import pytest

from src.application.translation.models import TranslationRequest
from src.application.translation.selection import select_chapters


@pytest.mark.parametrize(
    ("options", "translated", "checkpoint", "expected"),
    [
        ({}, {1}, {"completed": [], "failed": []}, [2, 3]),
        ({"force": True}, {1, 2, 3}, {"completed": [], "failed": []}, [1, 2, 3]),
        (
            {"start_chapter": 2, "end_chapter": 3},
            set(),
            {"completed": [], "failed": []},
            [2, 3],
        ),
        ({"resume": True}, set(), {"completed": [1, 3], "failed": []}, [2]),
        ({"failed_only": True}, set(), {"completed": [2], "failed": [1, 3]}, [1, 3]),
        ({"limit": 2}, set(), {"completed": [], "failed": []}, [1, 2]),
    ],
)
def test_select_chapters(options, translated, checkpoint, expected) -> None:
    request = TranslationRequest(novel="novel", **options)

    assert select_chapters(request, [3, 1, 2], translated, checkpoint) == expected


def test_failed_only_takes_precedence_over_resume() -> None:
    request = TranslationRequest(novel="novel", failed_only=True, resume=True)

    selected = select_chapters(
        request,
        [1, 2, 3],
        set(),
        {"completed": [1], "failed": [1, 3]},
    )

    assert selected == [1, 3]
