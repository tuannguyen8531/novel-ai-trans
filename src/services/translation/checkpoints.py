"""Translation checkpoint persistence."""

from __future__ import annotations

import json
from pathlib import Path

from src.utils.files import write_text_atomic


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
        normalized = {
            "completed": sorted(set(checkpoint.get("completed", []))),
            "failed": sorted(set(checkpoint.get("failed", []))),
        }
        write_text_atomic(path, _format_progress(normalized))


def _format_progress(progress: dict[str, list[int]], *, values_per_line: int = 12) -> str:
    """Format compact, readable progress JSON while preserving integer arrays."""
    lines = ["{"]
    keys = ("completed", "failed")
    for key_index, key in enumerate(keys):
        values = progress[key]
        suffix = "," if key_index < len(keys) - 1 else ""
        if not values:
            lines.append(f'  "{key}": []{suffix}')
            continue
        lines.append(f'  "{key}": [')
        for offset in range(0, len(values), values_per_line):
            chunk = ", ".join(str(value) for value in values[offset : offset + values_per_line])
            chunk_suffix = "," if offset + values_per_line < len(values) else ""
            lines.append(f"    {chunk}{chunk_suffix}")
        lines.append(f"  ]{suffix}")
    lines.append("}")
    return "\n".join(lines) + "\n"
