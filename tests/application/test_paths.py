"""Tests for shared novel path resolution."""

from pathlib import Path

from src.application import paths


def test_novel_directories_from_root() -> None:
    novel_root = Path("translated") / "demo"

    assert paths.novel_input_dir_from_root(novel_root) == novel_root / "input"
    assert paths.novel_output_dir_from_root(novel_root, "vi") == novel_root / "output"
    assert paths.novel_output_dir_from_root(novel_root, "en") == novel_root / "output" / "en"
    assert paths.novel_artifact_dir_from_root(novel_root) == novel_root / "artifacts"


def test_translation_progress_path_for_target(tmp_path: Path) -> None:
    assert paths.translation_progress_path_for_target("demo", "vi", progress_root=tmp_path) == tmp_path / "demo.json"
    assert paths.translation_progress_path_for_target("demo", "en", progress_root=tmp_path) == (tmp_path / "en" / "demo.json")
