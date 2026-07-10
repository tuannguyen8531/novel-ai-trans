"""Default path roots shared by the application layer and CLI.

The application workflow uses these constants so the legacy default locations
(``runtime/input`` and ``runtime/output``) can be exercised in tests and
overridden by future deployments. Paths are anchored at the project root so
they stay valid regardless of the caller's current working directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.target_language import normalize_target_language

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


def novel_root_dir(config: Any, novel_name: str) -> Path:
    return Path(config.translated_dir) / novel_name


def novel_input_dir(config: Any, novel_name: str) -> Path:
    return novel_root_dir(config, novel_name) / "input"


def novel_output_dir(config: Any, novel_name: str, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    base = novel_root_dir(config, novel_name) / "output"
    return base if target == "vi" else base / target


def novel_artifact_dir(config: Any, novel_name: str) -> Path:
    return novel_root_dir(config, novel_name) / "artifacts"


def translation_progress_path(
    config: Any,
    novel_name: str,
    target_language: str | None = None,
    *,
    progress_root: Path | None = None,
) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    root = progress_root or PROGRESS_DIR
    if target == "vi":
        return root / f"{novel_name}.json"
    return root / target / f"{novel_name}.json"


def translation_report_path(
    config: Any,
    novel_name: str,
    chapter_number: int,
    target_language: str | None = None,
    *,
    report_root: Path | None = None,
) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    root = report_root or REPORT_DIR
    if target == "vi":
        return root / novel_name / f"chapter_{chapter_number:03d}.json"
    return root / target / novel_name / f"chapter_{chapter_number:03d}.json"


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
    "novel_root_dir",
    "novel_input_dir",
    "novel_output_dir",
    "novel_artifact_dir",
    "translation_progress_path",
    "translation_report_path",
]
