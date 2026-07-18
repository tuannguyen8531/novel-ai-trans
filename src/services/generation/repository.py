"""Validation and persistence for generated crawler configs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import SiteConfig
from src.paths import resolve_novel_root

_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class ConfigRepository:
    """Validate and persist novel-owned crawler configurations."""

    def __init__(self, translated_root: Path) -> None:
        self._translated_root = translated_root

    @staticmethod
    def validate(config: dict[str, Any]) -> SiteConfig:
        return SiteConfig.from_dict(config)

    @staticmethod
    def validate_name(name: str) -> None:
        if not _SLUG.fullmatch(name) or name in {".", ".."}:
            raise ValueError(f"Invalid novel slug: {name!r}")

    def list(self) -> list[dict[str, Any]]:
        if not self._translated_root.exists():
            return []
        records: list[dict[str, Any]] = []
        for root in sorted(self._translated_root.iterdir()):
            path = root / "config.json"
            if not root.is_dir() or not _SLUG.fullmatch(root.name) or not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("name") == root.name:
                records.append(data)
        return records

    def load(self, name: str) -> dict[str, Any]:
        self.validate_name(name)
        path = resolve_novel_root(self._translated_root, name) / "config.json"
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid config: {name}")
        return data

    def save(self, config: dict[str, Any]) -> Path:
        name = str(config.get("name", "generated"))
        self.validate_name(name)
        path = resolve_novel_root(self._translated_root, name) / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path


__all__ = ["ConfigRepository"]
