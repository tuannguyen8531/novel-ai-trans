"""Tests for novel artifact path compatibility."""

from pathlib import Path

import pytest

from src.api.errors import ResourceNotFoundError
from src.api.routes.novels import _list_artifacts, _resolve_artifact_path


def test_artifact_helpers_prefer_artifacts_dir_and_support_legacy_root(tmp_path: Path) -> None:
    novel_root = tmp_path / "demo"
    artifacts_dir = novel_root / "artifacts"
    artifacts_dir.mkdir(parents=True)
    current = artifacts_dir / "demo.vi.epub"
    current.write_bytes(b"current")
    (novel_root / "demo.vi.epub").write_bytes(b"duplicate-legacy")
    legacy = novel_root / "demo.en.pdf"
    legacy.write_bytes(b"legacy")

    assert [path.name for path in _list_artifacts(novel_root)] == ["demo.en.pdf", "demo.vi.epub"]
    assert _resolve_artifact_path(novel_root, "demo.vi.epub") == current.resolve()
    assert _resolve_artifact_path(novel_root, "demo.en.pdf") == legacy.resolve()


@pytest.mark.parametrize("filename", ["../demo.epub", "subdir/demo.epub", ".hidden.epub"])
def test_resolve_artifact_rejects_unsafe_filename(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ResourceNotFoundError, match="Invalid artifact name"):
        _resolve_artifact_path(tmp_path / "demo", filename)
