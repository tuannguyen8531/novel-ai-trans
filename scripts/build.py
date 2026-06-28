"""Full verification chain: tests + type-check + GUI build.

Each step prints only a short summary so the console stays quiet.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"

ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(stream: bytes) -> str:
    return ANSI_RE.sub(b"", stream).decode("utf-8", errors="replace")


def summarise(text: str, lines: int = 15) -> str:
    kept = [line for line in text.splitlines() if line.strip()]
    return "\n".join(kept[-lines:]) if kept else "(no output)"


def step(label: str, command: list[str], cwd: Path | None = None, *, quiet: bool = False) -> int:
    if not quiet:
        print(f"\n=== {label} ===\n", flush=True)
    result = subprocess.run(command, cwd=cwd, capture_output=True)
    out = strip_ansi(result.stdout)
    err = strip_ansi(result.stderr) if result.stderr else ""
    if not quiet:
        print(summarise(out or err))
    if result.returncode != 0:
        if quiet:
            print(f"\n=== {label} ===\n", flush=True)
            print(summarise(out or err))
        if err and err != out:
            print("\n--- stderr ---")
            print(summarise(err))
        print(f"\n!!! {label} failed (exit {result.returncode})", flush=True)
    return result.returncode


def main(*, quiet: bool = False) -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found on PATH; install Node.js to use 'uv run build'.", flush=True)
        return 1
    pyright = shutil.which("pyright")
    if pyright is None:
        print("pyright not found on PATH; run this command through 'uv run build'.", flush=True)
        return 1

    steps = (
        ("pytest", [sys.executable, "-m", "pytest", "tests/"], None),
        ("pyright", [pyright], None),
        ("vue-tsc + vite build", ["npm", "run", "build"], WEB_DIR),
    )
    for label, command, cwd in steps:
        returncode = step(label, command, cwd=cwd, quiet=quiet)
        if returncode != 0:
            return returncode
    print("Build passed." if quiet else "\nAll checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
