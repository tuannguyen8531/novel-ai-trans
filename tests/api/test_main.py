from __future__ import annotations

from unittest.mock import patch

from src.api import __main__ as api_main


def test_serve_builds_before_starting_uvicorn():
    with (
        patch.object(api_main, "build_main", return_value=0) as mocked_build,
        patch.object(api_main.uvicorn, "run") as mocked_run,
    ):
        result = api_main.main()

    assert result == 0
    mocked_build.assert_called_once_with(quiet=True)
    mocked_run.assert_called_once()


def test_serve_does_not_start_when_build_fails():
    with (
        patch.object(api_main, "build_main", return_value=3),
        patch.object(api_main.uvicorn, "run") as mocked_run,
    ):
        result = api_main.main()

    assert result == 3
    mocked_run.assert_not_called()
