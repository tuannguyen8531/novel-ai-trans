"""Translation quality-report persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReportStore:
    """Persist per-chapter translation quality reports."""

    def save(self, path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
