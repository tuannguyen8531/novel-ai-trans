"""Validation and persistence for generated crawler configs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import SiteConfig

_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class ConfigRepository:
    """Validate and persist novel-owned crawler configurations."""

    def __init__(self, translated_root: Path) -> None:
        self._translated_root = translated_root

    @staticmethod
    def validate(config: dict[str, Any]) -> SiteConfig:
        return SiteConfig.from_dict(config)

    def save(self, config: dict[str, Any]) -> Path:
        name = str(config.get("name", "generated"))
        if not _SLUG.fullmatch(name) or name in {".", ".."}:
            raise ValueError(f"Invalid novel slug: {name!r}")
        path = self._translated_root / name / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path


__all__ = ["ConfigRepository"]
