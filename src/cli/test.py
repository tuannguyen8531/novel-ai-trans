"""Unified validation entry point: ruff check + ruff format + pytest."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def test_main(argv: list[str] | None = None) -> int:
    """Run ruff lint, ruff format check, and the pytest suite."""
    parser = argparse.ArgumentParser(
        prog="novel-ai-trans test",
        description="Run ruff lint, ruff format check, and the pytest suite.",
    )
    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="Skip ruff lint step.",
    )
    parser.add_argument(
        "--no-format",
        action="store_true",
        help="Skip ruff format check step.",
    )
    parser.add_argument(
        "--no-pytest",
        action="store_true",
        help="Skip pytest step.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to pytest (after `--`).",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    failed = False

    def _run(label: str, cmd: list[str]) -> bool:
        print(f"\n=== {label} ===")
        print(f"$ {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=project_root)
        if result.returncode != 0:
            print(f"✗ {label} FAILED (exit {result.returncode})")
            return False
        print(f"✓ {label} passed")
        return True

    if not args.no_lint:
        ok = _run("ruff check", ["uv", "run", "ruff", "check", "."])
        failed = failed or not ok

    if not args.no_format:
        ok = _run("ruff format --check", ["uv", "run", "ruff", "format", "--check", "."])
        failed = failed or not ok

    if not args.no_pytest:
        pytest_cmd = ["uv", "run", "pytest", "tests/"]
        if args.pytest_args:
            idx = args.pytest_args.index("--") if "--" in args.pytest_args else -1
            extra = args.pytest_args[idx + 1 :] if idx >= 0 else args.pytest_args
            if extra:
                pytest_cmd.extend(extra)
        ok = _run("pytest", pytest_cmd)
        failed = failed or not ok

    if failed:
        print("\n✗ One or more test steps failed.")
        return 1
    print("\n✓ All test steps passed.")
    return 0
