"""Entry point for ``uv run serve``."""

from __future__ import annotations

import logging
import os

import uvicorn

_logger = logging.getLogger(__name__)


def main() -> int:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    log_level = os.getenv("API_LOG_LEVEL", "info")
    _logger.info("Starting uvicorn on %s:%s", host, port)
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
