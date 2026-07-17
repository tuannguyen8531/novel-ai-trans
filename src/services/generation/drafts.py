"""Persistence for generated crawler-config drafts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class DraftRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    @staticmethod
    def validate_id(draft_id: str) -> None:
        if not _SLUG.fullmatch(draft_id) or draft_id in {".", ".."}:
            raise ValueError(f"Invalid draft id: {draft_id!r}")

    def save(self, draft: dict[str, Any]) -> Path:
        draft_id = str(draft["draft_id"])
        self.validate_id(draft_id)
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(draft_id)
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, draft_id: str) -> dict[str, Any]:
        path = self._path(draft_id)
        if not path.exists():
            raise FileNotFoundError(f"Draft not found: {draft_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid draft: {draft_id}")
        return data

    def list(self) -> list[dict[str, Any]]:
        if not self._root.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self._root.iterdir()):
            if path.suffix != ".json" or not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records

    def cleanup(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        for record in self.list():
            try:
                expires_at = datetime.fromisoformat(str(record["expires_at"]))
                draft_id = str(record["draft_id"])
            except KeyError, TypeError, ValueError:
                continue
            if expires_at <= current:
                self.delete(draft_id)

    def delete(self, draft_id: str) -> None:
        self._path(draft_id).unlink(missing_ok=True)

    def _path(self, draft_id: str) -> Path:
        self.validate_id(draft_id)
        return self._root / f"{draft_id}.json"


__all__ = ["DraftRepository"]
