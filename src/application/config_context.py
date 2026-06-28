"""Per-job configuration snapshot and context management.

Worker-reachable services and graph nodes resolve configuration at execution
time through :func:`get_config` instead of capturing the module-level
``config`` global. The default value of the context variable is the
``config`` global from :mod:`src.config`.

Application workflows use :func:`config_scope` to enter a per-job snapshot.
Worker dispatch across :class:`concurrent.futures.ThreadPoolExecutor` must
copy the context with :func:`contextvars.copy_context` and run work through
``ctx.run`` so the snapshot is visible inside the worker thread.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.config import (
    Config,
    active_config_scope,
    get_active_config,
    reset_default_config,
    set_default_config,
)


def get_config() -> Config:
    """Return the current job's :class:`Config` snapshot, or the global default."""
    return get_active_config()


def set_default(config: Config) -> None:
    """Replace the process-wide default configuration.

    Used by the API layer when ``PATCH /api/settings`` updates the defaults.
    """
    set_default_config(config)


def apply_settings_patch(patch: dict[str, Any]) -> Config:
    """Apply a partial settings patch to the current default configuration.

    Returns the new configuration. This does not mutate the .env file; it
    only updates the in-process defaults used by future jobs.
    """
    current = get_config()
    updated = current.clone(**patch)
    set_default(updated)
    return updated


def reset_default() -> None:
    """Restore the original global default captured at import time."""
    reset_default_config()


@contextmanager
def config_scope(snapshot: Config) -> Iterator[Config]:
    """Enter a scope where :func:`get_config` returns *snapshot*."""
    with active_config_scope(snapshot):
        yield snapshot
