"""Default path roots shared by the application layer and CLI.

The application workflow uses these constants so the legacy default locations
(``runtime/input`` and ``runtime/output``) can be exercised in tests and
overridden by future deployments. Paths are anchored at the project root so
they stay valid regardless of the caller's current working directory.
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

RUNTIME_DIR = _PROJECT_ROOT / "runtime"
INPUT_DIR = _PROJECT_ROOT / "translated" / "input"
OUTPUT_DIR = _PROJECT_ROOT / "translated" / "output"
PROGRESS_DIR = _PROJECT_ROOT / "runtime" / "progress"
REPORT_DIR = _PROJECT_ROOT / "runtime" / "reports"
RUNTIME_OUTPUT_ROOT = _PROJECT_ROOT / "runtime" / "crawler"
CONFIG_DIR = _PROJECT_ROOT / "configs"
DEFAULT_TRANSLATED_ROOT = _PROJECT_ROOT / "translated"
GLOSSARY_DIR = _PROJECT_ROOT / "runtime" / "glossary"
CONFIG_DRAFTS_DIR = _PROJECT_ROOT / "runtime" / "config-drafts"
LOCK_DIR = RUNTIME_DIR / "locks"
GLOSSARY_BACKUP_DIR = RUNTIME_DIR / "glossary-backups"


__all__ = [
    "INPUT_DIR",
    "RUNTIME_DIR",
    "OUTPUT_DIR",
    "PROGRESS_DIR",
    "REPORT_DIR",
    "RUNTIME_OUTPUT_ROOT",
    "CONFIG_DIR",
    "DEFAULT_TRANSLATED_ROOT",
    "GLOSSARY_DIR",
    "CONFIG_DRAFTS_DIR",
    "LOCK_DIR",
    "GLOSSARY_BACKUP_DIR",
]
