from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.services.generation.drafts import DraftRepository


def test_draft_repository_round_trip_cleanup_and_validation(tmp_path: Path) -> None:
    repository = DraftRepository(tmp_path)
    now = datetime.now(UTC)
    repository.save(
        {
            "draft_id": "expired",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
        }
    )
    repository.save(
        {
            "draft_id": "active",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }
    )

    assert repository.load("active")["draft_id"] == "active"
    repository.cleanup(now)
    assert [record["draft_id"] for record in repository.list()] == ["active"]
    with pytest.raises(ValueError):
        repository.load("../escape")
