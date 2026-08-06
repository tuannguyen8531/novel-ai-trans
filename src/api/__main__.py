"""Entry point for ``uv run serve``."""

from __future__ import annotations

import os

import uvicorn

from src.config import Config


def main() -> int:
    Config.ensure_settings_file()
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    log_level = os.getenv("API_LOG_LEVEL", "info")
    print(f"Starting service at http://{host}:{port}", flush=True)
    uvicorn.run(
        "src.api.factory:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
