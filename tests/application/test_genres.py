"""Tests for filesystem-backed genre profile discovery."""

from pathlib import Path

import pytest

from src.application.errors import ApplicationValidationError
from src.application.genres import available_genres, normalize_genres


def _write_genres(root: Path, source: str, genres: tuple[str, ...], *, target: str) -> None:
    directory = root / target / source
    directory.mkdir(parents=True)
    for genre in genres:
        (directory / f"{genre}.md").write_text("## Style\n- Preserve style", encoding="utf-8")


def test_available_genres_discovers_matching_target_files(tmp_path):
    for target in ("vi", "en"):
        _write_genres(tmp_path, "chinese", ("urban", "school-life"), target=target)

    assert available_genres("zh", rules_dir=tmp_path) == ["school-life", "urban"]


def test_available_genres_rejects_target_mismatch(tmp_path):
    _write_genres(tmp_path, "chinese", ("urban",), target="vi")
    _write_genres(tmp_path, "chinese", ("urban", "fantasy"), target="en")

    with pytest.raises(ApplicationValidationError, match="differ across targets"):
        available_genres("chinese", rules_dir=tmp_path)


def test_available_genres_rejects_unsafe_filename(tmp_path):
    for target in ("vi", "en"):
        _write_genres(tmp_path, "chinese", ("school_life",), target=target)

    with pytest.raises(ApplicationValidationError, match="Invalid genre rule filename"):
        available_genres("chinese", rules_dir=tmp_path)


def test_normalize_genres_deduplicates_and_uses_discovered_order(tmp_path):
    for target in ("vi", "en"):
        _write_genres(tmp_path, "korean", ("school-life", "academy", "fantasy"), target=target)

    assert normalize_genres(
        "ko",
        ["fantasy", "academy", "fantasy"],
        rules_dir=tmp_path,
    ) == ["academy", "fantasy"]


def test_normalize_genres_requires_source_language(tmp_path):
    with pytest.raises(ApplicationValidationError, match="Select a source language"):
        normalize_genres("", ["fantasy"], rules_dir=tmp_path)


def test_normalize_genres_rejects_unknown_profile(tmp_path):
    for target in ("vi", "en"):
        _write_genres(tmp_path, "japanese", ("isekai",), target=target)

    with pytest.raises(ApplicationValidationError, match="Unsupported genre"):
        normalize_genres("japanese", ["urban"], rules_dir=tmp_path)
