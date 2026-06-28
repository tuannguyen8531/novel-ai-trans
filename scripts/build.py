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


def step(label: str, command: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {label} ===\n", flush=True)
    result = subprocess.run(command, cwd=cwd, capture_output=True)
    out = strip_ansi(result.stdout)
    err = strip_ansi(result.stderr) if result.stderr else ""
    print(summarise(out or err))
    if result.returncode != 0:
        if err and err != out:
            print("\n--- stderr ---")
            print(summarise(err))
        print(f"\n!!! {label} failed (exit {result.returncode})", flush=True)
        sys.exit(result.returncode)


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found on PATH; install Node.js to use 'uv run build'.", flush=True)
        return 1

    step("pytest", ["uv", "run", "pytest", "tests/"])
    step("pyright", ["uv", "run", "pyright"])
    step("vue-tsc + vite build", ["npm", "run", "build"], cwd=WEB_DIR)
    print("\nAll checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
