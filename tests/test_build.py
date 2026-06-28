from __future__ import annotations

import sys
from unittest.mock import call, patch

from scripts import build


def test_quiet_build_runs_every_step(capsys):
    with (
        patch.object(build.shutil, "which", side_effect=lambda command: f"/bin/{command}"),
        patch.object(build, "step", return_value=0) as mocked_step,
    ):
        result = build.main(quiet=True)

    assert result == 0
    assert mocked_step.call_args_list == [
        call("pytest", [sys.executable, "-m", "pytest", "tests/"], cwd=None, quiet=True),
        call("pyright", ["/bin/pyright"], cwd=None, quiet=True),
        call("vue-tsc + vite build", ["npm", "run", "build"], cwd=build.WEB_DIR, quiet=True),
    ]
    assert capsys.readouterr().out == "Build passed.\n"


def test_build_stops_after_failed_step():
    with (
        patch.object(build.shutil, "which", side_effect=lambda command: f"/bin/{command}"),
        patch.object(build, "step", side_effect=[0, 7]) as mocked_step,
    ):
        result = build.main(quiet=True)

    assert result == 7
    assert mocked_step.call_count == 2
