"""Novel metadata persistence and updates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.application.errors import ApplicationValidationError, PersistenceError
from src.application.novel.identity import require_path
from src.utils import files as file_utils


def load(novel_root: Path) -> dict[str, Any]:
    metadata_path = novel_root / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}


def write(novel_root: Path, metadata: dict[str, Any], *, trailing_newline: bool = True) -> None:
    content = json.dumps(metadata, ensure_ascii=False, indent=2)
    (novel_root / "metadata.json").write_text(
        content + ("\n" if trailing_newline else ""),
        encoding="utf-8",
    )


def metadata(root: Path, name: str) -> dict[str, Any]:
    return load(require_path(root, name))


def _source_hash(value: object) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def update_metadata(
    root: Path,
    name: str,
    updates: dict[str, Any],
    *,
    localized_origin: str | None = None,
) -> dict[str, Any]:
    novel_root = require_path(root, name)
    if not updates:
        raise ApplicationValidationError("At least one metadata field must be provided.")

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        next_data = dict(current)
        shallow_updates = {key: value for key, value in updates.items() if key != "localized"}
        next_data.update(shallow_updates)

        localized_updates = updates.get("localized")
        if isinstance(localized_updates, dict):
            localized = dict(current.get("localized", {})) if isinstance(current.get("localized"), dict) else {}
            localization_meta = (
                dict(current.get("localization_meta", {})) if isinstance(current.get("localization_meta"), dict) else {}
            )
            for target, target_updates in localized_updates.items():
                if not isinstance(target_updates, dict):
                    continue
                target_values = dict(localized.get(target, {})) if isinstance(localized.get(target), dict) else {}
                target_meta = dict(localization_meta.get(target, {})) if isinstance(localization_meta.get(target), dict) else {}
                for field, value in target_updates.items():
                    if field not in {"title", "summary"}:
                        continue
                    if value is None:
                        target_values.pop(field, None)
                        target_meta.pop(field, None)
                        continue
                    target_values[field] = value
                    if localized_origin:
                        target_meta[field] = {
                            "source_hash": _source_hash(next_data.get(field)),
                            "origin": localized_origin,
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                if target_values:
                    localized[target] = target_values
                else:
                    localized.pop(target, None)
                if target_meta:
                    localization_meta[target] = target_meta
                else:
                    localization_meta.pop(target, None)
            next_data["localized"] = localized
            next_data["localization_meta"] = localization_meta
        return next_data

    try:
        return file_utils.merge_json_locked(novel_root / "metadata.json", updater)
    except OSError as error:
        raise PersistenceError(f"Failed to update novel metadata: {error}") from error


__all__ = ["load", "metadata", "update_metadata", "write"]
