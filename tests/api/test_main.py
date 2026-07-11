from __future__ import annotations

import os
from unittest.mock import patch

from src.api import __main__ as api_main


def test_serve_only_starts_uvicorn():
    with patch.dict(os.environ, {}, clear=True), patch.object(api_main.uvicorn, "run") as mocked_run:
        result = api_main.main()

    assert result == 0
    mocked_run.assert_called_once_with(
        "src.api.factory:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=False,
    )
