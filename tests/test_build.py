from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from scripts import build


def test_build_only_runs_frontend_build():
    completed = CompletedProcess(args=[], returncode=0)
    with (
        patch.object(build.shutil, "which", return_value="/bin/npm"),
        patch.object(build.subprocess, "run", return_value=completed) as mocked_run,
    ):
        result = build.main()

    assert result == 0
    mocked_run.assert_called_once_with(["/bin/npm", "run", "build"], cwd=build.WEB_DIR)


def test_build_returns_frontend_failure():
    completed = CompletedProcess(args=[], returncode=7)
    with (
        patch.object(build.shutil, "which", return_value="/bin/npm"),
        patch.object(build.subprocess, "run", return_value=completed),
    ):
        assert build.main() == 7
