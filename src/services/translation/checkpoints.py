"""Translation checkpoint persistence."""

from __future__ import annotations

import json
from pathlib import Path


class CheckpointStore:
    """Load and save normalized translation progress documents."""

    def load(self, path: Path) -> dict[str, list[int]]:
        if not path.exists():
            return {"completed": [], "failed": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return {"completed": [], "failed": []}
        if not isinstance(data, dict):
            return {"completed": [], "failed": []}
        return {
            "completed": list(data.get("completed", [])),
            "failed": list(data.get("failed", [])),
        }

    def save(self, path: Path, checkpoint: dict[str, list[int]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = {
            "completed": sorted(set(checkpoint.get("completed", []))),
            "failed": sorted(set(checkpoint.get("failed", []))),
        }
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
