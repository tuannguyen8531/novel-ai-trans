"""Translation quality-report persistence."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from pathlib import Path
from typing import Any


def content_hash(content: str | bytes) -> str:
    """Return a stable fingerprint for report decisions tied to exact content."""
    payload = content if isinstance(content, bytes) else content.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def issue_is_ignored(report: dict[str, Any], code: str, fingerprint: str) -> bool:
    """Return whether an issue was reviewed for the exact current content."""
    ignored = report.get("ignored_post_checks")
    if not isinstance(ignored, list):
        return False
    return any(
        isinstance(item, dict) and "key" not in item and item.get("code") == code and item.get("content_hash") == fingerprint
        for item in ignored
    )


def review_key_is_ignored(report: dict[str, Any], key: str, fingerprint: str) -> bool:
    """Return whether one granular post-check item was reviewed."""
    ignored = report.get("ignored_post_checks")
    if not isinstance(ignored, list):
        return False
    return any(isinstance(item, dict) and item.get("key") == key and item.get("content_hash") == fingerprint for item in ignored)


def post_check_review_key(code: str, detail: str) -> str:
    """Build a stable key for one granular post-check item."""
    return f"{code}:{content_hash(detail)[:16]}"


class ReportStore:
    """Persist per-chapter translation quality reports."""

    def save(self, path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete(self, path: Path) -> None:
        """Delete one report when it exists."""
        with suppress(OSError):
            path.unlink(missing_ok=True)

    def load(self, path: Path) -> dict[str, Any]:
        """Load a report defensively."""
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def save_manual_check(
        self,
        path: Path,
        *,
        chapter: int,
        target_language: str,
        issue_codes: list[str],
        content: str,
    ) -> None:
        """Update the current manual-edit check while preserving the translation report."""
        report = self.load(path)
        fingerprint = content_hash(content)
        ignored = report.get("ignored_post_checks")
        if isinstance(ignored, list):
            report["ignored_post_checks"] = [
                item for item in ignored if isinstance(item, dict) and item.get("content_hash") == fingerprint
            ]
        report.update(
            {
                "chapter": chapter,
                "target_language": target_language,
                "manual_post_check_issues": issue_codes,
            }
        )
        self.save(path, report)

    def set_issue_ignored(
        self,
        path: Path,
        *,
        chapter: int,
        target_language: str,
        code: str,
        fragments: list[str],
        content: str,
        ignored: bool,
    ) -> None:
        """Set or clear a review decision for one issue on exact content."""
        report = self.load(path)
        decisions = report.get("ignored_post_checks")
        retained = (
            [item for item in decisions if isinstance(item, dict) and item.get("code") != code]
            if isinstance(decisions, list)
            else []
        )
        if ignored:
            retained.append(
                {
                    "code": code,
                    "fragments": fragments,
                    "content_hash": content_hash(content),
                    "reason": "manual_review",
                }
            )
        report.update(
            {
                "chapter": chapter,
                "target_language": target_language,
                "ignored_post_checks": retained,
            }
        )
        self.save(path, report)

    def set_review_ignored(
        self,
        path: Path,
        *,
        chapter: int,
        target_language: str,
        key: str,
        code: str,
        detail: str,
        content: str,
        ignored: bool,
    ) -> None:
        """Set or clear a granular review decision for exact content."""
        report = self.load(path)
        decisions = report.get("ignored_post_checks")
        retained = (
            [item for item in decisions if isinstance(item, dict) and item.get("key") != key]
            if isinstance(decisions, list)
            else []
        )
        if ignored:
            retained.append(
                {
                    "key": key,
                    "code": code,
                    "detail": detail,
                    "content_hash": content_hash(content),
                    "reason": "manual_review",
                }
            )
        report.update(
            {
                "chapter": chapter,
                "target_language": target_language,
                "ignored_post_checks": retained,
            }
        )
        self.save(path, report)
