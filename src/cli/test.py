"""Unified Python validation entry point."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean_output(stdout: str, stderr: str) -> str:
    parts = [part.strip() for part in (stdout, stderr) if part.strip()]
    return ANSI_RE.sub("", "\n".join(parts))


def _summary(output: str) -> str:
    lines = [line.strip(" =") for line in output.splitlines() if line.strip() and not line.strip().startswith(">")]
    return lines[-1] if lines else "All checks passed!"


def _run(label: str, command: list[str], working_directory: Path) -> bool:
    result = subprocess.run(command, cwd=working_directory, capture_output=True, text=True)
    output = _clean_output(result.stdout, result.stderr)
    if result.returncode == 0:
        print(f"PASS {label}: {_summary(output)}", flush=True)
        return True

    print(f"FAIL {label} (exit {result.returncode})", flush=True)
    if output:
        print(output, flush=True)
    return False


def main(argv: list[str] | None = None) -> int:
    """Run Python checks, frontend lint, and unit tests."""
    parser = argparse.ArgumentParser(
        prog="novel-ai-trans test",
        description="Run ruff, pyright, pytest, frontend lint, and unit tests.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply safe Python and frontend lint fixes before validation.",
    )
    parser.add_argument("--no-lint", action="store_true", help="Skip ruff lint check.")
    parser.add_argument("--no-format", action="store_true", help="Skip ruff format check.")
    parser.add_argument("--no-pyright", action="store_true", help="Skip pyright check.")
    parser.add_argument("--no-pytest", action="store_true", help="Skip pytest.")
    parser.add_argument("--no-frontend", action="store_true", help="Skip frontend lint and unit tests.")
    parser.add_argument("--no-frontend-lint", action="store_true", help="Skip frontend ESLint check.")
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to pytest (after `--`).",
    )
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    commands: list[tuple[str, list[str], Path]] = []
    if not args.no_lint:
        lint_command = [sys.executable, "-m", "ruff", "check"]
        if args.fix:
            lint_command.append("--fix")
        commands.append(("ruff check", [*lint_command, "."], project_root))
    if not args.no_format:
        format_mode = ["--quiet"] if args.fix else ["--check"]
        commands.append(("ruff format", [sys.executable, "-m", "ruff", "format", *format_mode, "."], project_root))
    if not args.no_pyright:
        commands.append(("pyright", [sys.executable, "-m", "pyright"], project_root))
    if not args.no_pytest:
        extra = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
        commands.append(("pytest", [sys.executable, "-m", "pytest", "tests/", "-q", *extra], project_root))

    if not args.no_frontend:
        npm = shutil.which("npm")
        if npm is None:
            print("FAIL frontend: npm not found on PATH", flush=True)
            return 1
        if not args.no_frontend_lint:
            lint_command = [npm, "run", "lint"]
            if args.fix:
                lint_command.extend(["--", "--fix"])
            commands.append(("frontend lint", lint_command, project_root / "web"))
        commands.append(("frontend unit", [npm, "run", "test:unit"], project_root / "web"))

    passed = [_run(label, command, working_directory) for label, command, working_directory in commands]
    return 0 if all(passed) else 1
