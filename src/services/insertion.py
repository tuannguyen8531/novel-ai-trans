"""Filesystem persistence for chapter insertion workflows."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src import paths
from src.utils import files


@dataclass(frozen=True)
class FileGroup:
    label: str
    directory: Path
    suffix: str


@dataclass(frozen=True)
class StateFile:
    label: str
    path: Path
    data: dict[str, Any]
    updated: dict[str, Any]


def numbered_files(group: FileGroup, *, start: int) -> list[tuple[int, Path]]:
    if not group.directory.exists():
        return []
    found: list[tuple[int, Path]] = []
    for path in group.directory.iterdir():
        stem, dot, suffix = path.name.rpartition(".")
        prefix = "chapter_"
        number_text = stem.removeprefix(prefix)
        if not dot or suffix != group.suffix or not stem.startswith(prefix) or not number_text.isdigit() or not path.is_file():
            continue
        number = int(number_text)
        if number >= start:
            found.append((number, path))
    return sorted(found, key=lambda item: (item[0], item[1].name), reverse=True)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def _shifted_name(path: Path, old_number: int, new_number: int, suffix: str) -> str:
    canonical = f"chapter_{old_number:03d}.{suffix}"
    width = 3 if path.name == canonical else 0
    return f"chapter_{new_number:0{width}d}.{suffix}" if width else f"chapter_{new_number}.{suffix}"


def create_backup(
    *,
    novel: str,
    operation_id: str,
    number: int,
    previous_last: int,
    backup_root: Path,
    groups: list[FileGroup],
    state_files: list[StateFile],
) -> Path:
    backup_dir = paths.resolve_within(backup_root, novel, operation_id)
    if backup_dir.exists():
        raise FileExistsError(backup_dir)
    backup_dir.mkdir(parents=True)

    entries: list[dict[str, Any]] = []
    for group in groups:
        group_backup = backup_dir / "files" / group.label
        for old_number, source in numbered_files(group, start=number):
            group_backup.mkdir(parents=True, exist_ok=True)
            destination = group_backup / source.name
            shutil.copy2(source, destination)
            entries.append(
                {
                    "group": group.label,
                    "number": old_number,
                    "source": str(source),
                    "backup": str(destination.relative_to(backup_dir)),
                }
            )

    states: list[dict[str, str]] = []
    for state_file in state_files:
        destination = backup_dir / "state" / f"{state_file.label}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_file.path, destination)
        states.append(
            {
                "label": state_file.label,
                "source": str(state_file.path),
                "backup": str(destination.relative_to(backup_dir)),
            }
        )

    files.write_json_atomic(
        backup_dir / "manifest.json",
        {
            "status": "prepared",
            "novel": novel,
            "chapter": number,
            "previous_last_chapter": previous_last,
            "groups": [
                {
                    "label": group.label,
                    "directory": str(group.directory),
                    "suffix": group.suffix,
                }
                for group in groups
            ],
            "files": entries,
            "state_files": states,
        },
    )
    return backup_dir


def restore(backup_dir: Path) -> None:
    _restore_from_manifest(backup_dir, status="rolled_back")


def _restore_from_manifest(backup_dir: Path, *, status: str) -> None:
    manifest = load_json(backup_dir / "manifest.json")
    number = manifest.get("chapter")
    group_entries = manifest.get("groups")
    state_entries = manifest.get("state_files")
    if not isinstance(number, int) or not isinstance(group_entries, list) or not isinstance(state_entries, list):
        raise ValueError(f"Invalid insert backup manifest: {backup_dir}")

    groups: list[FileGroup] = []
    for entry in group_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid insert backup group: {backup_dir}")
        label = entry.get("label")
        directory = entry.get("directory")
        suffix = entry.get("suffix")
        if (
            not isinstance(label, str)
            or not label
            or not isinstance(directory, str)
            or not directory
            or not isinstance(suffix, str)
            or not suffix
        ):
            raise ValueError(f"Invalid insert backup group: {backup_dir}")
        groups.append(FileGroup(label, Path(directory), suffix))

    for group in groups:
        for _, path in numbered_files(group, start=number):
            path.unlink()
        group_backup = backup_dir / "files" / group.label
        if group_backup.exists():
            group.directory.mkdir(parents=True, exist_ok=True)
            for source in group_backup.iterdir():
                if source.is_file():
                    shutil.copy2(source, group.directory / source.name)

    for entry in state_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid insert backup state file: {backup_dir}")
        source = entry.get("source")
        backup = entry.get("backup")
        if not isinstance(source, str) or not isinstance(backup, str):
            raise ValueError(f"Invalid insert backup state file: {backup_dir}")
        backup_path = backup_dir / backup
        if backup_path.exists():
            files.write_bytes_atomic(Path(source), backup_path.read_bytes())

    manifest["status"] = status
    files.write_json_atomic(backup_dir / "manifest.json", manifest)


def recover_prepared_backups(backup_root: Path) -> list[str]:
    """Restore interrupted insert operations before the API accepts work."""
    if not backup_root.exists():
        return []
    recovered: list[str] = []
    for novel_dir in backup_root.iterdir():
        if not novel_dir.is_dir():
            continue
        for operation_dir in novel_dir.iterdir():
            manifest_path = operation_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            manifest = load_json(manifest_path)
            if manifest.get("status") != "prepared":
                continue
            _restore_from_manifest(operation_dir, status="recovered")
            recovered.append(operation_dir.name)
    return recovered


def shift_group(group: FileGroup, number: int) -> list[tuple[int, Path]]:
    shifted: list[tuple[int, Path]] = []
    for old_number, source in numbered_files(group, start=number):
        destination = source.with_name(_shifted_name(source, old_number, old_number + 1, group.suffix))
        source.replace(destination)
        shifted.append((old_number + 1, destination))
    return shifted


def write_state_files(state_files: list[StateFile]) -> None:
    for state_file in state_files:
        files.write_json_atomic(state_file.path, state_file.updated)


def update_backup_status(backup_dir: Path, status: str) -> None:
    manifest_path = backup_dir / "manifest.json"
    manifest = load_json(manifest_path)
    manifest["status"] = status
    files.write_json_atomic(manifest_path, manifest)


__all__ = [
    "FileGroup",
    "StateFile",
    "create_backup",
    "load_json",
    "numbered_files",
    "recover_prepared_backups",
    "restore",
    "shift_group",
    "update_backup_status",
    "write_state_files",
]
