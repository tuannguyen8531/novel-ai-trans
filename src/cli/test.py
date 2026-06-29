"""Unified Python validation entry point."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean_output(stdout: str, stderr: str) -> str:
    parts = [part.strip() for part in (stdout, stderr) if part.strip()]
    return ANSI_RE.sub("", "\n".join(parts))


def _summary(output: str) -> str:
    lines = [line.strip(" =") for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "passed"


def _run(label: str, command: list[str], project_root: Path) -> bool:
    result = subprocess.run(command, cwd=project_root, capture_output=True, text=True)
    output = _clean_output(result.stdout, result.stderr)
    if result.returncode == 0:
        print(f"PASS {label}: {_summary(output)}", flush=True)
        return True

    print(f"FAIL {label} (exit {result.returncode})", flush=True)
    if output:
        print(output, flush=True)
    return False


def test_main(argv: list[str] | None = None) -> int:
    """Run all Python lint, formatting, type, and test checks."""
    parser = argparse.ArgumentParser(
        prog="novel-ai-trans test",
        description="Run ruff, pyright, and pytest checks.",
    )
    parser.add_argument("--no-lint", action="store_true", help="Skip ruff lint check.")
    parser.add_argument("--no-format", action="store_true", help="Skip ruff format check.")
    parser.add_argument("--no-pyright", action="store_true", help="Skip pyright check.")
    parser.add_argument("--no-pytest", action="store_true", help="Skip pytest.")
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to pytest (after `--`).",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    commands: list[tuple[str, list[str]]] = []
    if not args.no_lint:
        commands.append(("ruff check", [sys.executable, "-m", "ruff", "check", "."]))
    if not args.no_format:
        commands.append(("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]))
    if not args.no_pyright:
        commands.append(("pyright", [sys.executable, "-m", "pyright"]))
    if not args.no_pytest:
        extra = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
        commands.append(("pytest", [sys.executable, "-m", "pytest", "tests/", "-q", *extra]))

    passed = [_run(label, command, project_root) for label, command in commands]
    return 0 if all(passed) else 1
