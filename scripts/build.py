"""Build the web UI for production."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def main() -> int:
    """Run the frontend production build and return its exit code."""
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found on PATH; install Node.js to use 'uv run build'.", flush=True)
        return 1

    return subprocess.run([npm, "run", "build"], cwd=WEB_DIR).returncode


if __name__ == "__main__":
    raise SystemExit(main())
