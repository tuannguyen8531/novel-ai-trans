"""Tests for translation checkpoint persistence."""

from src import paths
from src.services.translation.checkpoints import CheckpointStore


def test_save_and_load_normalizes_chapter_lists(tmp_path) -> None:
    path = tmp_path / "progress" / "novel.json"
    store = CheckpointStore()

    store.save(path, {"completed": [2, 1, 2], "failed": [3, 3]})

    assert store.load(path) == {"completed": [1, 2], "failed": [3]}


def test_save_formats_several_chapters_per_line(tmp_path) -> None:
    path = tmp_path / "progress" / "novel.json"

    CheckpointStore().save(path, {"completed": list(range(1, 15)), "failed": []})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[2] == "    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,"
    assert lines[3] == "    13, 14"


def test_target_languages_use_separate_checkpoint_paths(tmp_path) -> None:
    store = CheckpointStore()
    vi_path = paths.translation_progress_path_for_target("novel", "vi", progress_root=tmp_path)
    en_path = paths.translation_progress_path_for_target("novel", "en", progress_root=tmp_path)
    store.save(vi_path, {"completed": [1], "failed": []})
    store.save(en_path, {"completed": [2], "failed": []})

    assert store.load(vi_path)["completed"] == [1]
    assert store.load(en_path)["completed"] == [2]


def test_missing_or_invalid_checkpoint_returns_default(tmp_path) -> None:
    store = CheckpointStore()
    path = tmp_path / "progress.json"
    assert store.load(path) == {"completed": [], "failed": []}

    path.write_text("not json", encoding="utf-8")
    assert store.load(path) == {"completed": [], "failed": []}
