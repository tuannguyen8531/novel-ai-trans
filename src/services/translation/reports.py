"""Translation quality-report persistence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.utils.files import write_text_atomic


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
        write_text_atomic(path, self.serialize(report))

    def serialize(self, report: dict[str, Any]) -> str:
        return json.dumps(report, ensure_ascii=False, indent=2)

    def load(self, path: Path) -> dict[str, Any]:
        """Load a report defensively."""
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def save_output_check(
        self,
        path: Path,
        *,
        issue_codes: list[str],
        content: str,
    ) -> None:
        """Record current-output warnings and clear any rejected candidate."""
        self.save(
            path,
            self.prepare_output_check(path, issue_codes=issue_codes, content=content),
        )

    def prepare_output_check(
        self,
        path: Path,
        *,
        issue_codes: list[str],
        content: str,
    ) -> dict[str, Any]:
        """Build current-output warning state without publishing it."""
        report = self.load(path)
        fingerprint = content_hash(content)
        ignored = report.get("ignored_post_checks")
        retained = (
            [item for item in ignored if isinstance(item, dict) and item.get("content_hash") == fingerprint]
            if isinstance(ignored, list)
            else []
        )
        return {
            "manual_post_check_issues": list(dict.fromkeys(issue_codes)),
            "ignored_post_checks": retained,
            "issues": [],
            "candidate_translation": None,
            "partial": False,
            "failed_chunk_index": None,
            "total_chunks": None,
        }

    def save_rejection(
        self,
        path: Path,
        *,
        issues: list[dict[str, str]],
        candidate_translation: str,
        partial: bool,
        failed_chunk_index: int,
        total_chunks: int,
    ) -> None:
        """Record a rejected attempt without replacing current-output state."""
        report = self.load(path)
        self.save(
            path,
            {
                "manual_post_check_issues": _string_list(report.get("manual_post_check_issues")),
                "ignored_post_checks": _dict_list(report.get("ignored_post_checks")),
                "issues": issues,
                "candidate_translation": candidate_translation,
                "partial": partial,
                "failed_chunk_index": failed_chunk_index,
                "total_chunks": total_chunks,
            },
        )

    def save_manual_check(
        self,
        path: Path,
        *,
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
                "manual_post_check_issues": issue_codes,
            }
        )
        self.save(path, report)

    def set_issue_ignored(
        self,
        path: Path,
        *,
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
                "ignored_post_checks": retained,
            }
        )
        self.save(path, report)

    def set_issues_ignored(
        self,
        path: Path,
        *,
        issue_codes: list[str],
        content: str,
    ) -> None:
        """Set code-level review decisions for all current issues."""
        codes = list(dict.fromkeys(code for code in issue_codes if isinstance(code, str)))
        if not codes:
            return
        report = self.load(path)
        decisions = _dict_list(report.get("ignored_post_checks"))
        retained = [item for item in decisions if item.get("code") not in codes]
        fingerprint = content_hash(content)
        retained.extend(
            {
                "code": code,
                "content_hash": fingerprint,
                "reason": "manual_review",
            }
            for code in codes
        )
        report["ignored_post_checks"] = retained
        self.save(path, report)

    def set_review_ignored(
        self,
        path: Path,
        *,
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
                "ignored_post_checks": retained,
            }
        )
        self.save(path, report)


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
