"""Entry point for ``uv run serve``."""

from __future__ import annotations

import os

import uvicorn

from scripts.build import main as build_main


def main() -> int:
    print("Building application...", flush=True)
    build_result = build_main(quiet=True)
    if build_result != 0:
        return build_result

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    log_level = os.getenv("API_LOG_LEVEL", "info")
    print(f"Starting service at http://{host}:{port}", flush=True)
    uvicorn.run(
        "src.api.app_factory:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
