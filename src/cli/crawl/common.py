"""Shared crawl CLI output and logging helpers."""

from __future__ import annotations

from typing import Any

from src.utils.logging import setup_logging

_quiet_output = False


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    global _quiet_output
    _quiet_output = quiet
    log_level = "debug" if verbose else ("error" if quiet else "info")
    setup_logging(log_level)


def print_output(*args: object, **kwargs: Any) -> None:
    if not _quiet_output:
        print(*args, **kwargs)
