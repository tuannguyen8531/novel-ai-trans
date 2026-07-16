"""Tests for application-level novel operation locks."""

import pytest

from src.application.errors import ResourceConflictError
from src.application.locks import novel_lock


def test_same_novel_cannot_be_locked_twice(tmp_path) -> None:
    with (
        novel_lock("novel", lock_dir=tmp_path),
        pytest.raises(ResourceConflictError, match="currently locked"),
        novel_lock("novel", lock_dir=tmp_path),
    ):
        pass


def test_different_novels_can_be_locked_concurrently(tmp_path) -> None:
    with novel_lock("first", lock_dir=tmp_path), novel_lock("second", lock_dir=tmp_path):
        pass
