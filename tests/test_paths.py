"""Tests for shared novel path resolution."""

from pathlib import Path

from src import paths


def test_default_roots_are_anchored_at_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]

    assert project_root / "translated" == paths.DEFAULT_TRANSLATED_ROOT
    assert project_root / "runtime" == paths.RUNTIME_DIR
    assert project_root / "configs" == paths.CONFIG_DIR


def test_novel_directories_from_root() -> None:
    novel_root = Path("translated") / "demo"

    assert paths.novel_input_dir_from_root(novel_root) == novel_root / "input"
    assert paths.novel_output_dir_from_root(novel_root, "vi") == novel_root / "output"
    assert paths.novel_output_dir_from_root(novel_root, "en") == novel_root / "output" / "en"
    assert paths.novel_artifact_dir_from_root(novel_root) == novel_root / "artifacts"
    assert paths.novel_config_path_from_root(novel_root) == novel_root / "config.json"


def test_novel_config_path_uses_translated_root(tmp_path: Path) -> None:
    class Config:
        translated_dir = str(tmp_path / "translated")

    assert paths.novel_config_path(Config(), "demo") == tmp_path / "translated" / "demo" / "config.json"


def test_translation_progress_path_for_target(tmp_path: Path) -> None:
    assert paths.translation_progress_path_for_target("demo", "vi", progress_root=tmp_path) == tmp_path / "demo.json"
    assert paths.translation_progress_path_for_target("demo", "en", progress_root=tmp_path) == (tmp_path / "en" / "demo.json")


def test_novel_glossary_path_uses_target_and_fallback_root(tmp_path: Path) -> None:
    class Config:
        translated_dir = str(tmp_path / "translated")
        target_language = "vi"

    config = Config()
    assert paths.novel_glossary_path(config, "demo") == tmp_path / "translated" / "demo" / "glossary.json"
    assert paths.novel_glossary_path(config, "demo", "en") == tmp_path / "translated" / "demo" / "glossary.en.json"

    config.translated_dir = ""
    assert paths.novel_glossary_path(config, "demo", fallback_root=tmp_path) == tmp_path / "demo.json"
