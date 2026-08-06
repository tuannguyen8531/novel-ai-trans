"""Default path roots shared across application, service, API, and CLI layers.

These constants preserve the default runtime locations while allowing callers
to override roots in tests and deployments. Paths are anchored at the project
root so they stay valid regardless of the caller's current working directory.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from src.domain.language import normalize_target_language

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NOVEL_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

RUNTIME_DIR = _PROJECT_ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
INPUT_DIR = _PROJECT_ROOT / "translated" / "input"
OUTPUT_DIR = _PROJECT_ROOT / "translated" / "output"
PROGRESS_DIR = RUNTIME_DIR / "progress"
REPORT_DIR = RUNTIME_DIR / "reports"
TRANSACTION_DIR = RUNTIME_DIR / "transactions"
MANIFEST_DIR = RUNTIME_DIR / "manifests"
BACKUP_DIR = RUNTIME_DIR / "backups"
CACHE_DIR = RUNTIME_DIR / "cache"
BROWSER_CACHE_DIR = CACHE_DIR / "browser"
DISCOVERY_CACHE_DIR = CACHE_DIR / "discovery"
DRAFT_DIR = RUNTIME_DIR / "drafts"
JOB_DIR = RUNTIME_DIR / "jobs"
CONFIG_DIR = _PROJECT_ROOT / "configs"
SETTINGS_PATH = RUNTIME_DIR / "settings.json"
DEFAULT_TRANSLATED_ROOT = _PROJECT_ROOT / "translated"
LOCK_DIR = RUNTIME_DIR / "locks"
GLOSSARY_BACKUP_DIR = BACKUP_DIR / "replacements"
INSERT_BACKUP_DIR = BACKUP_DIR / "insertions"


def is_valid_novel_name(novel_name: str) -> bool:
    """Return whether *novel_name* is safe as one filesystem component."""
    return isinstance(novel_name, str) and novel_name not in {".", ".."} and bool(_NOVEL_NAME_PATTERN.fullmatch(novel_name))


def validate_novel_name(novel_name: str) -> str:
    """Validate and return a filesystem-safe novel name."""
    if not is_valid_novel_name(novel_name):
        raise ValueError(f"Invalid novel name: {novel_name!r}")
    return novel_name


def resolve_within(root: Path, *parts: str) -> Path:
    """Resolve a path and require it to remain below *root*.

    Resolving both sides also prevents an existing symlink inside the root
    from redirecting filesystem operations outside the configured boundary.
    """
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"Path escapes configured root: {candidate}")
    return candidate


def resolve_novel_root(root: Path, novel_name: str) -> Path:
    """Return a validated novel directory contained by *root*."""
    return resolve_within(root, validate_novel_name(novel_name))


def novel_root_dir(config: Any, novel_name: str) -> Path:
    return resolve_novel_root(Path(config.translated_dir), novel_name)


def novel_input_dir_from_root(novel_root: Path) -> Path:
    return novel_root / "input"


def novel_output_dir_from_root(novel_root: Path, target_language: str) -> Path:
    target = normalize_target_language(target_language)
    base = novel_root / "output"
    return base if target == "vi" else base / target


def novel_artifact_dir_from_root(novel_root: Path) -> Path:
    return novel_root / "artifacts"


def novel_artifact_manifest_path_from_root(novel_root: Path) -> Path:
    return novel_artifact_dir_from_root(novel_root) / "manifest.json"


def novel_runtime_key(novel_name: str) -> str:
    return hashlib.sha256(novel_name.encode("utf-8")).hexdigest()


def novel_lock_path(novel_name: str, *, lock_dir: Path | None = None) -> Path:
    return (lock_dir or LOCK_DIR) / f"{novel_runtime_key(novel_name)}.lock"


def novel_config_path_from_root(novel_root: Path) -> Path:
    return novel_root / "config.json"


def novel_glossary_path(
    config: Any,
    novel_name: str,
    target_language: str | None = None,
) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    novel_root = novel_root_dir(config, novel_name)
    return novel_root / ("glossary.json" if target == "vi" else f"glossary.{target}.json")


def novel_input_dir(config: Any, novel_name: str) -> Path:
    return novel_input_dir_from_root(novel_root_dir(config, novel_name))


def novel_output_dir(config: Any, novel_name: str, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    return novel_output_dir_from_root(novel_root_dir(config, novel_name), target)


def novel_artifact_dir(config: Any, novel_name: str) -> Path:
    return novel_artifact_dir_from_root(novel_root_dir(config, novel_name))


def novel_artifact_manifest_path(config: Any, novel_name: str) -> Path:
    return novel_artifact_manifest_path_from_root(novel_root_dir(config, novel_name))


def novel_config_path(config: Any, novel_name: str) -> Path:
    return novel_config_path_from_root(novel_root_dir(config, novel_name))


def translation_progress_path_for_target(
    novel_name: str,
    target_language: str,
    *,
    progress_root: Path | None = None,
) -> Path:
    target = normalize_target_language(target_language)
    root = progress_root or PROGRESS_DIR
    validate_novel_name(novel_name)
    if target == "vi":
        return resolve_within(root, f"{novel_name}.json")
    return resolve_within(root, target, f"{novel_name}.json")


def translation_progress_path(
    config: Any,
    novel_name: str,
    target_language: str | None = None,
    *,
    progress_root: Path | None = None,
) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    return translation_progress_path_for_target(novel_name, target, progress_root=progress_root)


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
    validate_novel_name(novel_name)
    return resolve_within(root, target, novel_name, f"chapter_{chapter_number:03d}.json")


def translation_transaction_dir(
    novel_name: str,
    target_language: str,
    *,
    transaction_root: Path | None = None,
) -> Path:
    """Return the recoverable-publication journal directory for a novel target."""
    target = normalize_target_language(target_language)
    root = transaction_root or TRANSACTION_DIR
    validate_novel_name(novel_name)
    return resolve_within(root, target, novel_name)


__all__ = [
    "INPUT_DIR",
    "LOG_DIR",
    "RUNTIME_DIR",
    "OUTPUT_DIR",
    "PROGRESS_DIR",
    "REPORT_DIR",
    "TRANSACTION_DIR",
    "MANIFEST_DIR",
    "BACKUP_DIR",
    "CACHE_DIR",
    "BROWSER_CACHE_DIR",
    "DISCOVERY_CACHE_DIR",
    "DRAFT_DIR",
    "JOB_DIR",
    "CONFIG_DIR",
    "SETTINGS_PATH",
    "DEFAULT_TRANSLATED_ROOT",
    "LOCK_DIR",
    "GLOSSARY_BACKUP_DIR",
    "INSERT_BACKUP_DIR",
    "is_valid_novel_name",
    "validate_novel_name",
    "resolve_within",
    "resolve_novel_root",
    "novel_root_dir",
    "novel_input_dir_from_root",
    "novel_output_dir_from_root",
    "novel_artifact_dir_from_root",
    "novel_artifact_manifest_path_from_root",
    "novel_runtime_key",
    "novel_lock_path",
    "novel_config_path_from_root",
    "novel_glossary_path",
    "novel_input_dir",
    "novel_output_dir",
    "novel_artifact_dir",
    "novel_artifact_manifest_path",
    "novel_config_path",
    "translation_progress_path_for_target",
    "translation_progress_path",
    "translation_report_path",
    "translation_transaction_dir",
]
