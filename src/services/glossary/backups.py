"""Persistence for glossary replacement backups."""

from __future__ import annotations

import json
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

from src.utils import files as file_utils


def generate_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S_%fZ')}_{secrets.token_hex(4)}"


def prepare(
    root: Path,
    backup_id: str,
    *,
    novel: str,
    target: str,
    novel_root: Path,
    files: list[Path],
    pending: list[dict],
) -> tuple[dict, Path]:
    backup_dir = root / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    relative_files: list[str] = []
    for path in files:
        relative = path.relative_to(novel_root)
        backup_path = backup_dir / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        relative_files.append(str(relative))
    manifest = {
        "id": backup_id,
        "status": "prepared",
        "novel": novel,
        "target": target,
        "files": relative_files,
        "pending_before": pending,
    }
    manifest_path = backup_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)
    return manifest, manifest_path


def complete(manifest_path: Path, manifest: dict, pending: list[dict]) -> None:
    manifest["status"] = "completed"
    manifest["pending_after"] = pending
    _write_manifest(manifest_path, manifest)


def load(root: Path, backup_id: str) -> tuple[dict, Path]:
    backup_dir = root / backup_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Glossary backup not found: {backup_id}")
    return json.loads(manifest_path.read_text(encoding="utf-8")), backup_dir


def restore_files(backup_dir: Path, novel_root: Path, relative_paths: list[str]) -> None:
    resolved_backup = backup_dir.resolve()
    resolved_novel = novel_root.resolve()
    for relative_path in relative_paths:
        backup_path = (resolved_backup / relative_path).resolve()
        target_path = (resolved_novel / relative_path).resolve()
        try:
            backup_path.relative_to(resolved_backup)
            target_path.relative_to(resolved_novel)
        except ValueError as error:
            raise FileNotFoundError("Glossary backup contains an invalid file path") from error
        if backup_path.exists():
            file_utils.write_text_atomic(target_path, backup_path.read_text(encoding="utf-8"))


def write_chapters(files: dict[Path, str]) -> int:
    for path, content in files.items():
        file_utils.write_text_atomic(path, content)
    return len(files)


def _write_manifest(path: Path, manifest: dict) -> None:
    file_utils.write_text_atomic(path, json.dumps(manifest, ensure_ascii=False, indent=2))


__all__ = ["complete", "generate_id", "load", "prepare", "restore_files", "write_chapters"]
