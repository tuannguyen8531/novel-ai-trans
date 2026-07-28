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

    def save_manual_check(
        self,
        path: Path,
        *,
        chapter: int,
        target_language: str,
        issue_codes: list[str],
    ) -> None:
        """Update the current manual-edit check while preserving the translation report."""
        report: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError, OSError:
                loaded = {}
            if isinstance(loaded, dict):
                report = loaded
        report.update(
            {
                "chapter": chapter,
                "target_language": target_language,
                "manual_post_check_issues": issue_codes,
            }
        )
        self.save(path, report)
