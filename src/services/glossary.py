"""
Glossary Service — JSON-based per-novel glossary management.

Each novel gets its own glossary file at glossary/{novel_name}.json.
Structure:
{
    "terms": {
        "原始术语": "Target-language translation",
        "李明": "Lý Minh"
    },
    "source_language": "chinese",
    "entities": {
        "李明": {"translated_name": "Lý Minh", "role": "protagonist"}
    },
    "edges": [
        ["李明", "张伟", "friend", 3]
    ],
    "chapter_summaries": {
        "1": "Summary of chapter 1...",
        "2": "Summary of chapter 2..."
    }
}

If TRANSLATED_DIR is set, also checks {translated_dir}/{novel}/glossary.json
or glossary.{target}.json as a fallback source. If found in the translated
directory, copies to project glossary.

Character schema:
- entities: dict of original_name -> {translated_name, role, pronoun, aliases?}
  role: protagonist | antagonist | supporting | minor
  pronoun: target-language pronoun/reference style assigned on first appearance (immutable)
  aliases: source-language short/full-name variants resolved to the canonical entity
- edges: list of [from_orig, to_orig, relationship_type, since_chapter]
  Each relationship stored ONCE (no bidirectional duplication).
  Relationship types: mother, father, sibling, friend, enemy, master,
  disciple, rival, classmate, teacher, romantic interest, etc.
- address_rules: list of {speaker, listener, self, other, since, until?, notes?}
  Non-overlapping per-pair direct address/reference timelines in the target language.
"""

import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

try:
    import fcntl

    msvcrt = None
except ImportError:
    fcntl = None
    import msvcrt

from src.application.errors import ResourceConflictError
from src.application.paths import GLOSSARY_BACKUP_DIR, LOCK_DIR
from src.config import active_config_scope, config
from src.domain.glossary import (
    count_name_occurrences,
    find_glossary_replacement_conflicts,
    format_recent_summaries,
    get_character_translated_name,
    merge_character_context,
    normalize_character_info,
    normalize_glossary_data,
    replace_glossary_values,
    select_active_address_rules,
    select_active_character_context,
    uppercase_first_cased,
    upsert_relationship,
    validate_glossary_data,
)
from src.domain.target_language import normalize_target_language

_LOCK_SH = getattr(fcntl, "LOCK_SH", 0)
_LOCK_EX = getattr(fcntl, "LOCK_EX", 0)
_LOCK_NB = getattr(fcntl, "LOCK_NB", 0)
_LOCK_UN = getattr(fcntl, "LOCK_UN", 0)


def _flock(fd: int, op: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, op)  # type: ignore
    elif msvcrt is not None:
        # Only enforce non-blocking locks (like novel_lock) on Windows to prevent deadlocks
        # on read/write of glossary JSON files which use blocking locks.
        if op & 4:  # LOCK_NB
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore
            except OSError as err:
                raise BlockingIOError(err.strerror) from err
        elif op & 8:  # LOCK_UN
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore
            except OSError:
                pass


GLOSSARY_DIR = Path("runtime/glossary")
PENDING_REPLACEMENTS_KEY = "_pending_replacements"


def _current_target_language() -> str:
    target = getattr(config, "target_language", "vi")
    if not isinstance(target, str):
        return "vi"
    return normalize_target_language(target)


def _glossary_path(novel_name: str) -> Path:
    """Get path to glossary file for a novel (always in project glossary/)."""
    target = _current_target_language()
    if target == "vi":
        return GLOSSARY_DIR / f"{novel_name}.json"
    return GLOSSARY_DIR / f"{novel_name}.{target}.json"


def _share_glossary_path(novel_name: str) -> Path | None:
    """Get path to glossary file in translated dir, if configured."""
    if not config.translated_dir:
        return None
    target = _current_target_language()
    if target == "vi":
        return Path(config.translated_dir) / novel_name / "glossary.json"
    return Path(config.translated_dir) / novel_name / f"glossary.{target}.json"


def _resolve_glossary(novel_name: str) -> Path:
    """Resolve glossary path with translated dir fallback.

    Priority:
    1. Project glossary/{novel_name}.json or glossary/{novel_name}.{target}.json
    2. Translated dir {TRANSLATED_DIR}/{novel}/glossary*.json (copies to project if found)
    3. Returns project path (will be created on first save)
    """
    project_path = _glossary_path(novel_name)
    if project_path.exists():
        return project_path

    share_path = _share_glossary_path(novel_name)
    if share_path and share_path.exists():
        project_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(share_path, project_path)
        return project_path

    return project_path


def _ensure_dir(path: Path | None = None):
    """Create glossary directory if it doesn't exist."""
    if path is None:
        GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)


def _read_json_locked(path: Path) -> dict:
    """Read JSON file with shared lock."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        _flock(f.fileno(), _LOCK_SH)
        try:
            return json.load(f)
        finally:
            _flock(f.fileno(), _LOCK_UN)


def _write_json_locked(path: Path, data: dict):
    """Write JSON file with exclusive lock."""
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        _flock(f.fileno(), _LOCK_EX)
        try:
            json.dump(data, f, ensure_ascii=False, indent=2)
        finally:
            _flock(f.fileno(), _LOCK_UN)


def load_glossary_data(novel_name: str) -> dict:
    """Load the full glossary JSON data for a novel."""
    return _read_json_locked(_resolve_glossary(novel_name))


def _merge_json_locked(path: Path, updater: Callable[[dict], dict]) -> dict:
    """Atomically read-modify-write JSON with exclusive lock.

    After writing to the project path, copies to share dir if configured.

    Args:
        path: File path
        updater: Function that takes existing data dict and returns updated dict
    """
    _ensure_dir(path)
    with open(path, "a+", encoding="utf-8") as f:
        _flock(f.fileno(), _LOCK_EX)
        try:
            f.seek(0)
            try:
                existing_data = json.load(f)
            except (json.JSONDecodeError, ValueError):
                existing_data = {}
            new_data = updater(existing_data)
            f.seek(0)
            f.truncate()
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        finally:
            _flock(f.fileno(), _LOCK_UN)

    # Sync to share dir after successful write
    _sync_to_share(path, new_data)

    return new_data


def _sync_to_share(project_path: Path, data: dict) -> None:
    """Copy glossary data to translated dir if configured."""
    if not config.translated_dir:
        return

    # Extract novel name from filename: "my-novel.json" or "my-novel.en.json".
    target = _current_target_language()
    suffix = f".{target}.json"
    novel_name = project_path.name[: -len(suffix)] if target != "vi" and project_path.name.endswith(suffix) else project_path.stem
    share_dir = Path(config.translated_dir) / novel_name
    share_path = share_dir / "glossary.json" if target == "vi" else share_dir / f"glossary.{target}.json"

    if not share_path.exists() or share_path.resolve() != project_path.resolve():
        share_dir.mkdir(parents=True, exist_ok=True)
        share_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _queue_replacement(
    data: dict,
    *,
    kind: str,
    sources: list[str],
    old_value: str,
    new_value: str,
) -> dict:
    """Queue or collapse a pending rendered-value replacement."""
    sources = list(dict.fromkeys(source for source in sources if source))
    if not sources or not old_value or not new_value or old_value == new_value:
        return data

    pending = [dict(item) for item in data.get(PENDING_REPLACEMENTS_KEY, []) if isinstance(item, dict)]
    for index, item in enumerate(pending):
        if item.get("kind") == kind and item.get("sources") == sources and item.get("new") == old_value:
            if item.get("old") == new_value:
                pending.pop(index)
            else:
                item["new"] = new_value
            return {**data, PENDING_REPLACEMENTS_KEY: pending}
    pending.append({"kind": kind, "sources": sources, "old": old_value, "new": new_value})
    return {**data, PENDING_REPLACEMENTS_KEY: pending}


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        if path.exists() and hasattr(os, "fchmod"):
            with contextlib.suppress(AttributeError):
                os.fchmod(fd, stat.S_IMODE(path.stat().st_mode))  # type: ignore
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        Path(temp_name).unlink(missing_ok=True)
        raise


_ACTIVE_LOCKS: set[str] = set()


@contextlib.contextmanager
def novel_lock(novel_name: str):
    """Acquire an exclusive lock on a novel to prevent concurrent modifications."""
    if novel_name in _ACTIVE_LOCKS:
        raise ResourceConflictError(
            f"Novel {novel_name!r} is currently locked by another translation or glossary apply operation."
        )
    _ACTIVE_LOCKS.add(novel_name)
    try:
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = LOCK_DIR / f"{_novel_runtime_key(novel_name)}.lock"
        with open(lock_path, "a") as f:
            try:
                _flock(f.fileno(), _LOCK_EX | _LOCK_NB)
            except BlockingIOError as err:
                raise ResourceConflictError(
                    f"Novel {novel_name!r} is currently locked by another translation or glossary apply operation."
                ) from err
            try:
                yield
            finally:
                _flock(f.fileno(), _LOCK_UN)
    finally:
        _ACTIVE_LOCKS.discard(novel_name)


def _novel_runtime_key(novel_name: str) -> str:
    return hashlib.sha256(novel_name.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def load_glossary(novel_name: str) -> dict[str, str]:
    """Load term glossary for a novel. Returns empty dict if not found."""
    path = _resolve_glossary(novel_name)
    data = _read_json_locked(path)
    return data.get("terms", {})


def save_glossary(novel_name: str, terms: dict[str, str], *, is_user_edit: bool = False):
    """Save/merge terms into the novel's glossary (thread-safe)."""
    path = _resolve_glossary(novel_name)

    def updater(data: dict) -> dict:
        old_terms = dict(data.get("terms", {}))
        updated = {**data, "terms": {**old_terms, **terms}}
        if is_user_edit:
            for original, translated in terms.items():
                old_value = old_terms.get(original, "")
                updated = _queue_replacement(
                    updated,
                    kind="term",
                    sources=[original],
                    old_value=old_value,
                    new_value=translated,
                )
        return updated

    _merge_json_locked(path, updater)


def remove_glossary_term(novel_name: str, original: str) -> bool:
    """Remove a glossary term. Returns True if the term existed."""
    path = _resolve_glossary(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        terms = dict(data.get("terms", {}))
        removed = original in terms
        terms.pop(original, None)
        return {**data, "terms": terms}

    _merge_json_locked(path, updater)
    return removed


def update_glossary_term(
    novel_name: str,
    old_original: str,
    new_original: str,
    translated: str,
    *,
    overwrite: bool = False,
    is_user_edit: bool = False,
) -> None:
    """Atomically update or rename a term without exposing partial state."""
    path = _resolve_glossary(novel_name)

    def updater(data: dict) -> dict:
        terms = dict(data.get("terms", {}))
        if old_original not in terms:
            raise KeyError(old_original)
        old_translated = terms[old_original]
        if new_original != old_original and new_original in terms and not overwrite:
            raise FileExistsError(new_original)
        terms[new_original] = translated
        if new_original != old_original:
            terms.pop(old_original)
        updated = {**data, "terms": terms}
        if is_user_edit:
            updated = _queue_replacement(
                updated,
                kind="term",
                sources=list(dict.fromkeys([new_original, old_original])),
                old_value=old_translated,
                new_value=translated,
            )
        return updated

    _merge_json_locked(path, updater)


def remove_character(novel_name: str, original_name: str) -> bool:
    """Remove a character entity. Returns True if the character existed."""
    path = _resolve_glossary(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        entities = dict(data.get("entities", {}))
        removed = original_name in entities
        entities.pop(original_name, None)
        # Also clean up any edges or address rules referencing this character!
        edges = [
            edge for edge in data.get("edges", []) if len(edge) >= 2 and edge[0] != original_name and edge[1] != original_name
        ]
        address_rules = [
            rule
            for rule in data.get("address_rules", [])
            if rule.get("speaker") != original_name and rule.get("listener") != original_name
        ]
        return {**data, "entities": entities, "edges": edges, "address_rules": address_rules}

    _merge_json_locked(path, updater)
    return removed


def remove_relationship(novel_name: str, from_char: str, to_char: str) -> bool:
    """Remove a relationship edge between characters. Returns True if existed."""
    path = _resolve_glossary(novel_name)
    removed = False

    def updater(data: dict) -> dict:
        nonlocal removed
        edges = []
        for edge in data.get("edges", []):
            if len(edge) >= 2 and {edge[0], edge[1]} == {from_char, to_char}:
                removed = True
                continue
            edges.append(edge)
        return {**data, "edges": edges}

    _merge_json_locked(path, updater)
    return removed


def save_character_pronoun(novel_name: str, original_name: str, pronoun: str) -> bool:
    """Set a character pronoun. Returns True if the character existed."""
    path = _resolve_glossary(novel_name)
    found = False

    def updater(data: dict) -> dict:
        nonlocal found
        entities = dict(data.get("entities", {}))
        if original_name not in entities:
            return data
        info = normalize_character_info(dict(entities[original_name]))
        info["pronoun"] = pronoun
        entities[original_name] = info
        found = True
        return {**data, "entities": entities}

    _merge_json_locked(path, updater)
    return found


def save_character(
    novel_name: str,
    original_name: str,
    translated_name: str = "",
    role: str = "",
    name_vi: str = "",
    *,
    is_user_edit: bool = False,
) -> bool:
    """Update a character's translated name and/or role. Returns True if found."""
    path = _resolve_glossary(novel_name)
    found = False
    name_value = translated_name or name_vi

    def updater(data: dict) -> dict:
        nonlocal found
        entities = dict(data.get("entities", {}))
        if original_name not in entities:
            return data
        old_info = normalize_character_info(dict(entities[original_name]))
        old_name = get_character_translated_name(old_info)
        info = dict(old_info)
        if name_value:
            info["translated_name"] = name_value
        if role:
            info["role"] = role
        entities[original_name] = info
        found = True
        updated = {**data, "entities": entities}
        if is_user_edit:
            updated = _queue_replacement(
                updated,
                kind="character",
                sources=[original_name, *info.get("aliases", [])],
                old_value=old_name,
                new_value=info.get("translated_name", ""),
            )
        return updated

    _merge_json_locked(path, updater)
    return found


def save_relationship(
    novel_name: str,
    from_char: str,
    to_char: str,
    relationship: str,
    since_chapter: int | None = None,
    *,
    update_since: bool = False,
) -> bool:
    """Add or update a relationship. Returns True when both characters exist."""
    path = _resolve_glossary(novel_name)
    updated = False

    def updater(data: dict) -> dict:
        nonlocal updated
        entities = data.get("entities", {})
        if from_char not in entities or to_char not in entities:
            return data
        updated = True
        return upsert_relationship(
            data,
            from_char,
            to_char,
            relationship,
            since_chapter=since_chapter,
            update_since=update_since,
        )

    _merge_json_locked(path, updater)
    return updated


def validate_glossary(novel_name: str) -> list[str]:
    """Validate a novel glossary file and return issues."""
    return validate_glossary_data(load_glossary_data(novel_name))


def apply_pending_replacements(
    novel_name: str,
    *,
    target_language: str | None = None,
    write: bool = False,
) -> dict:
    """Preview or apply pending term/name changes to translated chapter files."""
    target = normalize_target_language(target_language or _current_target_language())
    if target != _current_target_language():
        with active_config_scope(config.clone(target_language=target)):
            return apply_pending_replacements(novel_name, write=write)

    with novel_lock(novel_name):
        data = load_glossary_data(novel_name)
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

        translated_root = Path(config.translated_dir) if config.translated_dir else Path("translated")
        novel_root = translated_root / novel_name
        input_dir = novel_root / "input"
        output_dir = novel_root / "output" if target == "vi" else novel_root / "output" / target

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

                # Removing an ambiguous longer match can expose a shorter one.
                # Recompute until every remaining safe item has the same count
                # that preview and write will actually use.
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
            backup_dir = GLOSSARY_BACKUP_DIR / _novel_runtime_key(novel_name) / backup_id
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
            _write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

            for path, content in files_to_write.items():
                _write_text_atomic(path, content)
                changed_files += 1

            path = _resolve_glossary(novel_name)
            _merge_json_locked(path, lambda current: {**current, PENDING_REPLACEMENTS_KEY: new_pending})
            manifest["status"] = "completed"
            manifest["pending_after"] = new_pending
            _write_text_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

        return {
            "novel": novel_name,
            "target": target,
            "write": effective_write,
            "conflicted": has_global_conflicts,
            "changed_files": len(files_to_write) if not effective_write else changed_files,
            "backup_id": backup_id,
            "replacements": reports,
        }


def clean_glossary(novel_name: str) -> dict:
    """Normalize a glossary file and return before/after counts."""
    path = _resolve_glossary(novel_name)

    stats: dict = {}

    def updater(data: dict) -> dict:
        nonlocal stats
        before_edges = len(data.get("edges", []))
        before_address_rules = len(data.get("address_rules", []))
        before_pronoun_examples = len(data.get("pronoun_examples", {}))
        cleaned = normalize_glossary_data(data)
        stats = {
            "entities": len(cleaned.get("entities", {})),
            "edges_before": before_edges,
            "edges_after": len(cleaned.get("edges", [])),
            "address_rules_before": before_address_rules,
            "address_rules_after": len(cleaned.get("address_rules", [])),
            "pronoun_examples_removed": before_pronoun_examples,
        }
        return cleaned

    _merge_json_locked(path, updater)
    return stats


# ---------------------------------------------------------------------------
# Source language
# ---------------------------------------------------------------------------


def load_source_language(novel_name: str) -> str:
    """Load detected source language for a novel. Returns empty string if not found."""
    path = _resolve_glossary(novel_name)
    data = _read_json_locked(path)
    return data.get("source_language", "")


def save_source_language(novel_name: str, language: str):
    """Save detected source language for a novel (thread-safe)."""
    if not language:
        return
    path = _resolve_glossary(novel_name)
    _merge_json_locked(
        path,
        lambda data: {
            **data,
            "source_language": language,
        },
    )


# ---------------------------------------------------------------------------
# Chapter summaries
# ---------------------------------------------------------------------------


def load_chapter_summary(novel_name: str, chapter_number: int) -> str:
    """Load summary for a specific chapter. Returns empty string if not found."""
    path = _resolve_glossary(novel_name)
    data = _read_json_locked(path)
    summaries = data.get("chapter_summaries", {})
    return summaries.get(str(chapter_number), "")


def load_chapter_summaries_recent(
    novel_name: str,
    current_chapter: int,
    max_count: int = 3,
) -> str:
    """
    Load the most recent chapter summaries (up to max_count).

    For chapter 10 with max_count=3, loads summaries for chapters 9, 8, 7.
    Returns a formatted string ready for inclusion in prompts.
    """
    path = _resolve_glossary(novel_name)
    data = _read_json_locked(path)
    summaries = data.get("chapter_summaries", {})

    return format_recent_summaries(summaries, current_chapter, max_count=max_count)


def save_chapter_summary(novel_name: str, chapter_number: int, summary: str):
    """Save a chapter summary (thread-safe)."""
    path = _resolve_glossary(novel_name)
    _merge_json_locked(
        path,
        lambda data: {
            **data,
            "chapter_summaries": {**data.get("chapter_summaries", {}), str(chapter_number): summary},
        },
    )


# ---------------------------------------------------------------------------
# Characters — Entity + Edge graph
# ---------------------------------------------------------------------------


def get_active_context(novel_name: str, source_text: str, chapter_number: int = 0) -> tuple[dict, list, list]:
    """Load only characters and relationships relevant to the current source text.

    Algorithm:
        1. Scan source_text for known character names (active set) using boundary-aware matching.
        2. Collect only pair edges where both endpoints are in the active set.
        3. Build entity dict for directly active characters.

    Returns:
        (entities, edges, address_rules) — filtered to active context only.
        entities: {orig_name: {"translated_name": str, "role": str}}
        edges:    [[from, to, rel_type, since_chapter], ...]
        address_rules: [{speaker, listener, self, other, since, until?, notes?}, ...]
    """
    data = normalize_glossary_data(_read_json_locked(_resolve_glossary(novel_name)))
    all_entities: dict = data.get("entities", {})
    all_edges: list = data.get("edges", [])
    all_address_rules: list = data.get("address_rules", [])

    if not all_entities:
        return {}, [], []

    entities, edges = select_active_character_context(all_entities, all_edges, source_text)
    address_rules = select_active_address_rules(all_address_rules, entities, chapter_number)
    return entities, edges, address_rules


def save_characters_batch(
    novel_name: str,
    entities: dict,
    edges: list,
    address_rules: list | None = None,
    chapter: int = 0,
):
    """Save character entities and relationship edges (thread-safe).

    Args:
        entities: {orig_name: {"translated_name": str, "role": str}}
        edges:    [[from, to, rel_type]] or [[from, to, rel_type, since_chapter]]
                  Each relationship should be stored ONCE (no bidirectional duplicates).
        address_rules: Direct address/reference rules for character pairs.
        chapter:  Current chapter number (used as since_chapter fallback).
    """
    if not entities and not edges and not address_rules:
        return

    path = _resolve_glossary(novel_name)

    def updater(data: dict) -> dict:
        return merge_character_context(data, entities, edges, address_rules=address_rules, chapter=chapter)

    _merge_json_locked(path, updater)


_BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{6}_\d{6}Z_[0-9a-f]{8}$")


def _merge_pending_replacements(restored: list[dict], current: list[dict]) -> list[dict]:
    merged = [dict(item) for item in restored]
    for current_item in current:
        item = dict(current_item)
        collapsed = False
        for previous in merged:
            if (
                previous.get("kind") == item.get("kind")
                and previous.get("sources") == item.get("sources")
                and previous.get("new") == item.get("old")
            ):
                previous["new"] = item.get("new")
                collapsed = True
                break
        if not collapsed and item not in merged:
            merged.append(item)
    return merged


def rollback_glossary_replacement(novel_name: str, backup_id: str) -> None:
    """Rollback a previous glossary replacement using the backup manifest."""
    if not _BACKUP_ID_PATTERN.fullmatch(backup_id):
        raise FileNotFoundError(f"Invalid glossary backup id: {backup_id!r}")
    backup_dir = GLOSSARY_BACKUP_DIR / _novel_runtime_key(novel_name) / backup_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Glossary backup not found: {backup_id}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("novel") != novel_name:
        raise FileNotFoundError(f"Glossary backup does not belong to novel {novel_name!r}")
    target = normalize_target_language(manifest.get("target") or "vi")
    if target != _current_target_language():
        with active_config_scope(config.clone(target_language=target)):
            rollback_glossary_replacement(novel_name, backup_id)
        return

    translated_root = Path(config.translated_dir) if config.translated_dir else Path("translated")
    novel_root = (translated_root / novel_name).resolve()

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
                _write_text_atomic(target_file_path, backup_file_path.read_text(encoding="utf-8"))

        pending_before = [item for item in manifest.get("pending_before", []) if isinstance(item, dict)]
        path = _resolve_glossary(novel_name)

        def restore_pending(current_data: dict) -> dict:
            current_pending = [item for item in current_data.get(PENDING_REPLACEMENTS_KEY, []) if isinstance(item, dict)]
            return {
                **current_data,
                PENDING_REPLACEMENTS_KEY: _merge_pending_replacements(pending_before, current_pending),
            }

        _merge_json_locked(path, restore_pending)


def dismiss_pending_replacements(novel_name: str, *, target_language: str | None = None) -> None:
    """Manually dismiss all pending replacements."""
    target = normalize_target_language(target_language or _current_target_language())
    if target != _current_target_language():
        with active_config_scope(config.clone(target_language=target)):
            dismiss_pending_replacements(novel_name)
        return
    path = _resolve_glossary(novel_name)
    with novel_lock(novel_name):
        _merge_json_locked(path, lambda current: {**current, PENDING_REPLACEMENTS_KEY: []})
