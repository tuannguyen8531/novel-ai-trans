"""Preview, apply, dismiss, and rollback rendered glossary replacements."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from src import paths as _paths
from src.application import config as app_config
from src.application.errors import (
    OperationCancelledError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.application.progress import ProgressEvent
from src.config import active_config_scope, config
from src.domain.characters import count_name_occurrences
from src.domain.glossary import (
    PENDING_REPLACEMENTS_KEY,
    audit_term_usage,
    find_glossary_replacement_conflicts,
    merge_pending_replacements,
    replace_glossary_values,
    uppercase_first_cased,
    validate_glossary_data,
)
from src.domain.language import normalize_target_language
from src.services import glossary as glossary_service
from src.utils import files as file_utils

GLOSSARY_BACKUP_DIR = _paths.GLOSSARY_BACKUP_DIR
_BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{6}_\d{6}Z_[0-9a-f]{8}$")


def _empty_glossary() -> dict:
    return {"terms": {}, "entities": {}, "edges": []}


def _emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if callback is not None:
        with suppress(Exception):
            callback(event)


def _check_cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise OperationCancelledError("Glossary operation cancelled.")


def load_glossary(novel_name: str) -> dict:
    """Load the active glossary document for a novel."""
    path = glossary_service.resolve_glossary_path(novel_name)
    try:
        if not path.exists() or path.stat().st_size == 0:
            return _empty_glossary()
        return glossary_service.load_glossary_data(novel_name)
    except (OSError, json.JSONDecodeError, ValueError):
        return _empty_glossary()


def save_terms(novel_name: str, terms: dict[str, str]) -> dict:
    glossary_service.save_glossary(novel_name, terms, is_user_edit=True)
    return load_glossary(novel_name)


def save_term(novel_name: str, original: str, translated: str) -> dict:
    return save_terms(novel_name, {original: translated})


def remove_term(novel_name: str, original: str) -> dict:
    glossary_service.remove_glossary_term(novel_name, original)
    return load_glossary(novel_name)


def update_term(
    novel_name: str,
    old_original: str,
    new_original: str,
    translated: str,
    *,
    overwrite: bool,
) -> dict:
    try:
        glossary_service.update_glossary_term(
            novel_name,
            old_original,
            new_original,
            translated,
            overwrite=overwrite,
            is_user_edit=True,
        )
    except KeyError as error:
        raise ResourceNotFoundError(f"Glossary term not found: {old_original}") from error
    except FileExistsError as error:
        raise ResourceConflictError(f"Glossary term already exists: {new_original}") from error
    return load_glossary(novel_name)


def remove_character(novel_name: str, original: str) -> dict:
    glossary_service.remove_character(novel_name, original)
    return load_glossary(novel_name)


def remove_relationship(novel_name: str, from_char: str, to_char: str) -> dict:
    glossary_service.remove_relationship(novel_name, from_char, to_char)
    return load_glossary(novel_name)


def save_character(
    novel_name: str,
    original: str,
    *,
    translated_name: str,
    role: str,
) -> dict:
    glossary_service.save_character(
        novel_name,
        original,
        translated_name=translated_name,
        role=role,
        is_user_edit=True,
    )
    return load_glossary(novel_name)


def save_character_pronoun(novel_name: str, original: str, pronoun: str) -> bool:
    return glossary_service.save_character_pronoun(novel_name, original, pronoun)


def save_relationship(
    novel_name: str,
    *,
    from_char: str,
    to_char: str,
    relationship: str,
    since: int | None = None,
    update_since: bool = False,
) -> dict:
    glossary_service.save_relationship(
        novel_name,
        from_char,
        to_char,
        relationship,
        since_chapter=since,
        update_since=update_since,
    )
    return load_glossary(novel_name)


def clean_glossary(novel_name: str) -> dict:
    return glossary_service.clean_glossary(novel_name)


def validate_glossary(
    novel_name: str,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[str]:
    _check_cancel(cancel_event)
    _emit(progress_callback, ProgressEvent(kind="phase", novel=novel_name, message="Validating glossary"))
    issues = validate_glossary_data(load_glossary(novel_name))
    _check_cancel(cancel_event)
    return issues


def audit_glossary(
    novel_name: str,
    *,
    target: str | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[dict]:
    terms = load_glossary(novel_name).get("terms", {})
    return audit_terms(
        novel_name,
        terms,
        target=target,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )


def audit_terms(
    novel_name: str,
    terms: dict[str, str],
    *,
    target: str | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> list[dict]:
    """Audit translated chapters against an explicit set of terms."""
    novel_root = _paths.novel_root_dir(app_config.get_config(), novel_name)
    chapters = sorted(_paths.novel_input_dir_from_root(novel_root).glob("chapter_*.txt"))
    output_dir = _paths.novel_output_dir_from_root(novel_root, target or "vi")
    if not output_dir.exists():
        return []

    issues: list[dict] = []
    total = len(chapters)
    for index, source_path in enumerate(chapters, 1):
        _check_cancel(cancel_event)
        try:
            chapter_number = int(source_path.stem.split("_")[-1])
        except ValueError:
            continue
        output_path = output_dir / f"chapter_{chapter_number:03d}.txt"
        if not output_path.exists():
            output_path = output_dir / source_path.name
        if not output_path.exists():
            continue
        try:
            source_text = source_path.read_text(encoding="utf-8")
            translated_text = output_path.read_text(encoding="utf-8")
        except OSError:
            continue
        issues.extend({"chapter": chapter_number, **issue} for issue in audit_term_usage(terms, source_text, translated_text))
        _emit(
            progress_callback,
            ProgressEvent(
                kind="progress",
                novel=novel_name,
                current=index,
                total=total,
                chapter=chapter_number,
                pct=round(index / total * 100, 2) if total else None,
            ),
        )
    return issues


@contextmanager
def novel_lock(novel_name: str):
    """Map a service lock failure to the application error contract."""
    try:
        with glossary_service.novel_lock(novel_name):
            yield
    except glossary_service.GlossaryLockError as error:
        raise ResourceConflictError(str(error)) from error


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
        pending_total_occurrences = [0] * len(pending)
        pending_has_issues = [False] * len(pending)
        files_to_write: dict[Path, str] = {}

        if input_dir.exists():
            for source_path in sorted(input_dir.glob("chapter_*.txt")):
                try:
                    chapter_number = int(source_path.stem.split("_")[-1])
                    source_text = source_path.read_text(encoding="utf-8")
                except (OSError, ValueError):
                    continue

                source_counts = [
                    sum(count_name_occurrences(source, source_text) for source in item.get("sources", [])) for item in pending
                ]
                applicable_indexes = [index for index, count in enumerate(source_counts) if count > 0]
                if not applicable_indexes:
                    continue

                output_path = output_dir / f"chapter_{chapter_number:03d}.txt"
                if not output_path.exists():
                    output_path = output_dir / source_path.name
                if not output_path.exists():
                    for index in applicable_indexes:
                        pending_has_issues[index] = True
                        item = pending[index]
                        reports.append(
                            {
                                "chapter": chapter_number,
                                "kind": item.get("kind", "term"),
                                "sources": item.get("sources", []),
                                "old": item.get("old", ""),
                                "new": item.get("new", ""),
                                "status": "missing_output",
                                "source_count": source_counts[index],
                                "output_count": 0,
                                "occurrences": 0,
                                "conflict_news": [],
                            }
                        )
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
                    for index in safe_indexes:
                        pending_total_occurrences[index] += actual_counts.get(str(pending[index].get("old", "")), 0)

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
        new_pending = [
            item
            for index, item in enumerate(pending)
            if not (pending_total_occurrences[index] > 0 and not pending_has_issues[index])
        ]

        changed_files = 0
        backup_id: str | None = None
        if effective_write and files_to_write:
            backup_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S_%fZ')}_{secrets.token_hex(4)}"
            backup_dir = GLOSSARY_BACKUP_DIR / glossary_service.novel_runtime_key(novel_name) / backup_id
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

            glossary_path = glossary_service.resolve_glossary_path(novel_name)
            file_utils.merge_json_locked(
                glossary_path,
                lambda current: {**current, PENDING_REPLACEMENTS_KEY: new_pending},
            )
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
    backup_dir = GLOSSARY_BACKUP_DIR / glossary_service.novel_runtime_key(novel_name) / backup_id
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
