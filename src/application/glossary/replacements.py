"""Apply, dismiss, and roll back glossary replacements."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

from src import paths as _paths
from src.application.errors import ResourceNotFoundError
from src.application.locks import novel_lock, novel_runtime_key
from src.config import active_config_scope, config
from src.domain.characters import count_name_occurrences
from src.domain.glossary import (
    PENDING_REPLACEMENTS_KEY,
    find_glossary_replacement_conflicts,
    merge_pending_replacements,
    replace_glossary_values,
    uppercase_first_cased,
)
from src.domain.language import normalize_target_language
from src.services import chapters as chapter_service
from src.services import glossary as glossary_service
from src.utils import files as file_utils

GLOSSARY_BACKUP_DIR = _paths.GLOSSARY_BACKUP_DIR
_BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{6}_\d{6}Z_[0-9a-f]{8}$")


def apply_pending_replacements(
    novel_name: str,
    *,
    target_language: str | None = None,
    write: bool = False,
) -> dict:
    """Preview or apply pending term/name changes to translated chapter files."""
    current_target = glossary_service.current_target_language()
    target = normalize_target_language(target_language or current_target)
    if target != current_target:
        with active_config_scope(config.clone(target_language=target)):
            return apply_pending_replacements(novel_name, write=write)

    with novel_lock(novel_name):
        data = glossary_service.load_glossary_data(novel_name)
        pending = [dict(item) for item in data.get(PENDING_REPLACEMENTS_KEY, []) if isinstance(item, dict)]
        if not pending:
            return {
                "novel": novel_name,
                "target": target,
                "write": write,
                "conflicted": False,
                "changed_files": 0,
                "replacements": [],
            }

        conflicts = find_glossary_replacement_conflicts(pending)
        has_global_conflicts = bool(conflicts)

        novel_root = glossary_service.translated_novel_root(novel_name)
        input_dir = _paths.novel_input_dir_from_root(novel_root)
        output_dir = _paths.novel_output_dir_from_root(novel_root, target)

        reports: list[dict] = []
        pending_has_issues = [False] * len(pending)
        files_to_write: dict[Path, str] = {}

        if input_dir.exists():
            for source_path in chapter_service.scan(input_dir).values():
                try:
                    chapter_number = int(source_path.stem.split("_")[-1])
                    source_text = source_path.read_text(encoding="utf-8")
                except OSError, ValueError:
                    continue

                source_counts = [
                    sum(count_name_occurrences(source, source_text) for source in item.get("sources", [])) for item in pending
                ]
                applicable_indexes = [index for index, count in enumerate(source_counts) if count > 0]
                if not applicable_indexes:
                    continue

                output_path = chapter_service.chapter_path(output_dir, chapter_number)
                if not output_path.exists():
                    continue

                translated_text = output_path.read_text(encoding="utf-8")
                nonconflicting_indexes = [index for index in applicable_indexes if index not in conflicts]
                planned_counts: dict[str, int] = {}
                if nonconflicting_indexes:
                    _, planned_counts = replace_glossary_values(
                        translated_text,
                        [pending[index] for index in nonconflicting_indexes],
                    )

                statuses: dict[int, tuple[str, int]] = {}
                safe_indexes: set[int] = set()
                for index in applicable_indexes:
                    item = pending[index]
                    source_count = source_counts[index]
                    if index in conflicts:
                        statuses[index] = ("conflict", 0)
                        pending_has_issues[index] = True
                        continue
                    old_count = planned_counts.get(str(item.get("old", "")), 0)
                    new_value = str(item.get("new", ""))
                    new_variants = {new_value, uppercase_first_cased(new_value)}
                    new_count = sum(count_name_occurrences(variant, translated_text) for variant in new_variants)
                    if old_count == 0 and new_count >= source_count:
                        statuses[index] = ("already_applied", new_count)
                    elif old_count == source_count:
                        statuses[index] = ("safe", old_count)
                        safe_indexes.add(index)
                    else:
                        statuses[index] = ("ambiguous", old_count)
                        pending_has_issues[index] = True

                while safe_indexes:
                    _, actual_counts = replace_glossary_values(
                        translated_text,
                        [pending[index] for index in sorted(safe_indexes)],
                    )
                    invalid = {
                        index
                        for index in safe_indexes
                        if actual_counts.get(str(pending[index].get("old", "")), 0) != source_counts[index]
                    }
                    if not invalid:
                        break
                    for index in invalid:
                        statuses[index] = (
                            "ambiguous",
                            actual_counts.get(str(pending[index].get("old", "")), 0),
                        )
                        pending_has_issues[index] = True
                    safe_indexes -= invalid

                actual_counts = {}
                if safe_indexes:
                    updated_text, actual_counts = replace_glossary_values(
                        translated_text,
                        [pending[index] for index in sorted(safe_indexes)],
                    )
                    if updated_text != translated_text:
                        files_to_write[output_path] = updated_text

                for index in applicable_indexes:
                    item = pending[index]
                    status, output_count = statuses[index]
                    occurrences = actual_counts.get(str(item.get("old", "")), 0) if status == "safe" else 0
                    reports.append(
                        {
                            "chapter": chapter_number,
                            "kind": item.get("kind", "term"),
                            "sources": item.get("sources", []),
                            "old": item.get("old", ""),
                            "new": item.get("new", ""),
                            "status": status,
                            "source_count": source_counts[index],
                            "output_count": output_count,
                            "occurrences": occurrences,
                            "conflict_news": conflicts.get(index, []),
                        }
                    )

        effective_write = write and not has_global_conflicts
        new_pending = [item for index, item in enumerate(pending) if pending_has_issues[index]]

        changed_files = 0
        backup_id: str | None = None
        manifest: dict | None = None
        manifest_path: Path | None = None
        if effective_write and files_to_write:
            backup_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S_%fZ')}_{secrets.token_hex(4)}"
            backup_dir = GLOSSARY_BACKUP_DIR / novel_runtime_key(novel_name) / backup_id
            backup_dir.mkdir(parents=True, exist_ok=False)

            backup_files: list[str] = []
            for path in files_to_write:
                rel_path = path.relative_to(novel_root)
                backup_file_path = backup_dir / rel_path
                backup_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_file_path)
                backup_files.append(str(rel_path))

            manifest = {
                "id": backup_id,
                "status": "prepared",
                "novel": novel_name,
                "target": target,
                "files": backup_files,
                "pending_before": pending,
            }
            manifest_path = backup_dir / "manifest.json"
            file_utils.write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

            for path, content in files_to_write.items():
                file_utils.write_text_atomic(path, content)
                changed_files += 1

        if effective_write and new_pending != pending:
            glossary_path = glossary_service.resolve_glossary_path(novel_name)
            file_utils.merge_json_locked(
                glossary_path,
                lambda current: {**current, PENDING_REPLACEMENTS_KEY: new_pending},
            )

        if effective_write and manifest is not None and manifest_path is not None:
            manifest["status"] = "completed"
            manifest["pending_after"] = new_pending
            file_utils.write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

        return {
            "novel": novel_name,
            "target": target,
            "write": effective_write,
            "conflicted": has_global_conflicts,
            "changed_files": len(files_to_write) if not effective_write else changed_files,
            "backup_id": backup_id,
            "replacements": reports,
        }


def rollback_glossary_replacement(novel_name: str, backup_id: str) -> None:
    """Rollback a previous glossary replacement using the backup manifest."""
    if not _BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise FileNotFoundError(f"Invalid glossary backup id: {backup_id!r}")
    backup_dir = GLOSSARY_BACKUP_DIR / novel_runtime_key(novel_name) / backup_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Glossary backup not found: {backup_id}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("novel") != novel_name:
        raise FileNotFoundError(f"Glossary backup does not belong to novel {novel_name!r}")
    target = normalize_target_language(manifest.get("target") or "vi")
    if target != glossary_service.current_target_language():
        with active_config_scope(config.clone(target_language=target)):
            rollback_glossary_replacement(novel_name, backup_id)
        return

    novel_root = glossary_service.translated_novel_root(novel_name).resolve()

    with novel_lock(novel_name):
        for rel_file_path in manifest.get("files", []):
            backup_file_path = (backup_dir / rel_file_path).resolve()
            target_file_path = (novel_root / rel_file_path).resolve()
            try:
                backup_file_path.relative_to(backup_dir.resolve())
                target_file_path.relative_to(novel_root)
            except ValueError as error:
                raise FileNotFoundError("Glossary backup contains an invalid file path") from error
            if backup_file_path.exists():
                file_utils.write_text_atomic(target_file_path, backup_file_path.read_text(encoding="utf-8"))

        pending_before = [item for item in manifest.get("pending_before", []) if isinstance(item, dict)]
        glossary_path = glossary_service.resolve_glossary_path(novel_name)

        def restore_pending(current_data: dict) -> dict:
            current_pending = [item for item in current_data.get(PENDING_REPLACEMENTS_KEY, []) if isinstance(item, dict)]
            return {
                **current_data,
                PENDING_REPLACEMENTS_KEY: merge_pending_replacements(pending_before, current_pending),
            }

        file_utils.merge_json_locked(glossary_path, restore_pending)


def rollback_replacements(novel_name: str, backup_id: str) -> None:
    """Rollback a replacement while exposing application-level errors."""
    try:
        rollback_glossary_replacement(novel_name, backup_id)
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error


def dismiss_pending_replacements(novel_name: str, *, target_language: str | None = None) -> None:
    """Manually dismiss all pending replacements."""
    current_target = glossary_service.current_target_language()
    target = normalize_target_language(target_language or current_target)
    if target != current_target:
        with active_config_scope(config.clone(target_language=target)):
            dismiss_pending_replacements(novel_name)
        return
    glossary_path = glossary_service.resolve_glossary_path(novel_name)
    with novel_lock(novel_name):
        file_utils.merge_json_locked(
            glossary_path,
            lambda current: {**current, PENDING_REPLACEMENTS_KEY: []},
        )
