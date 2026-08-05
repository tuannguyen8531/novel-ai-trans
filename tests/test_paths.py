"""Tests for shared novel path resolution."""

from pathlib import Path

import pytest

from src import paths


def test_default_roots_are_anchored_at_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]

    assert project_root / "translated" == paths.DEFAULT_TRANSLATED_ROOT
    assert project_root / "runtime" == paths.RUNTIME_DIR
    assert project_root / "runtime" / "logs" == paths.LOG_DIR
    assert project_root / "runtime" / "jobs" == paths.JOB_DIR
    assert project_root / "runtime" / "manifests" == paths.MANIFEST_DIR
    assert project_root / "runtime" / "transactions" == paths.TRANSACTION_DIR
    assert project_root / "runtime" / "backups" / "insertions" == paths.INSERT_BACKUP_DIR
    assert project_root / "runtime" / "backups" / "replacements" == paths.GLOSSARY_BACKUP_DIR
    assert project_root / "runtime" / "cache" / "browser" == paths.BROWSER_CACHE_DIR
    assert project_root / "runtime" / "cache" / "discovery" == paths.DISCOVERY_CACHE_DIR
    assert project_root / "runtime" / "drafts" == paths.DRAFT_DIR
    assert project_root / "configs" == paths.CONFIG_DIR


def test_novel_directories_from_root() -> None:
    novel_root = Path("translated") / "demo"

    assert paths.novel_input_dir_from_root(novel_root) == novel_root / "input"
    assert paths.novel_output_dir_from_root(novel_root, "vi") == novel_root / "output"
    assert paths.novel_output_dir_from_root(novel_root, "en") == novel_root / "output" / "en"
    assert paths.novel_artifact_dir_from_root(novel_root) == novel_root / "artifacts"
    assert paths.novel_artifact_manifest_path_from_root(novel_root) == novel_root / "artifacts" / "manifest.json"
    novel_lock = paths.novel_lock_path("demo", lock_dir=Path("runtime/locks"))
    assert novel_lock == Path("runtime/locks") / f"{paths.novel_runtime_key('demo')}.lock"
    assert paths.novel_config_path_from_root(novel_root) == novel_root / "config.json"


def test_novel_config_path_uses_translated_root(tmp_path: Path) -> None:
    class Config:
        translated_dir = str(tmp_path / "translated")

    assert paths.novel_config_path(Config(), "demo") == tmp_path / "translated" / "demo" / "config.json"


def test_translation_progress_path_for_target(tmp_path: Path) -> None:
    assert paths.translation_progress_path_for_target("demo", "vi", progress_root=tmp_path) == tmp_path / "demo.json"
    assert paths.translation_progress_path_for_target("demo", "en", progress_root=tmp_path) == (tmp_path / "en" / "demo.json")


def test_translation_transaction_directory_uses_target_and_novel(tmp_path: Path) -> None:
    assert paths.translation_transaction_dir("demo", "vi", transaction_root=tmp_path) == tmp_path / "vi" / "demo"


def test_novel_glossary_path_uses_novel_root_and_target(tmp_path: Path) -> None:
    class Config:
        translated_dir = str(tmp_path / "translated")
        target_language = "vi"

    config = Config()
    assert paths.novel_glossary_path(config, "demo") == tmp_path / "translated" / "demo" / "glossary.json"
    assert paths.novel_glossary_path(config, "demo", "en") == tmp_path / "translated" / "demo" / "glossary.en.json"


@pytest.mark.parametrize("novel_name", ["../secret", "..\\secret", "/absolute", "C:\\absolute", ".hidden"])
def test_novel_paths_reject_unsafe_names(tmp_path: Path, novel_name: str) -> None:
    class Config:
        translated_dir = str(tmp_path / "translated")
        target_language = "vi"

    with pytest.raises(ValueError, match="Invalid novel name"):
        paths.novel_root_dir(Config(), novel_name)
    with pytest.raises(ValueError, match="Invalid novel name"):
        paths.translation_progress_path_for_target(novel_name, "vi", progress_root=tmp_path)
