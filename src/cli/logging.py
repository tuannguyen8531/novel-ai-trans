"""CLI-owned verbose logging configuration."""

from src.services.logger import set_verbose


def enable_verbose() -> None:
    set_verbose(True)


__all__ = ["enable_verbose"]
