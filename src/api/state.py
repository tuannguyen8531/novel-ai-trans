"""FastAPI application state contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from src.api.background.manager import JobManager


@dataclass
class AppState:
    job_manager: JobManager
    history_root: Path
    dist_dir: Path
    drafts_dir: Path
    config_drafts_dir: Path
    jobs_dir: Path
    shutdown_event: asyncio.Event
    max_upload_bytes: int = 100 * 1024 * 1024


__all__ = ["AppState"]
