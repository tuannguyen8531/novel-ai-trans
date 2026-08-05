import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Config, active_config_scope
from src.services.metadata import (
    load_genres,
    load_source_language,
    load_translation_profile,
    metadata_path,
    save_source_language,
)


def test_save_and_load_source_language_from_novel_metadata(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    snapshot = Config(translated_dir=str(translated_root))

    with active_config_scope(snapshot):
        save_source_language("demo", "zh")
        assert load_source_language("demo") == "chinese"
        path = metadata_path("demo")

    assert json.loads(path.read_text(encoding="utf-8"))["source_language"] == "chinese"


def test_load_source_language_migrates_legacy_glossary_field(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    novel_root.mkdir(parents=True)
    glossary_path = novel_root / "glossary.json"
    glossary_path.write_text(
        json.dumps({"terms": {"魔法": "ma thuật"}, "source_language": "zh"}),
        encoding="utf-8",
    )

    with active_config_scope(Config(translated_dir=str(translated_root))):
        assert load_source_language("demo") == "chinese"

    metadata = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
    assert metadata["source_language"] == "chinese"
    assert glossary == {"terms": {"魔法": "ma thuật"}}


def test_save_empty_source_language_does_not_create_metadata(tmp_path: Path) -> None:
    with active_config_scope(Config(translated_dir=str(tmp_path / "translated"))):
        save_source_language("demo", "")
        assert load_source_language("demo") == ""
        assert not metadata_path("demo").exists()


def test_load_genres_preserves_backward_compatibility(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"source_language": "chinese"}),
        encoding="utf-8",
    )

    with active_config_scope(Config(translated_dir=str(translated_root))):
        assert load_genres("demo") == []


def test_load_genres_rejects_malformed_metadata(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(
        json.dumps({"genres": "urban"}),
        encoding="utf-8",
    )

    with (
        active_config_scope(Config(translated_dir=str(translated_root))),
        pytest.raises(ValueError, match="list of strings"),
    ):
        load_genres("demo")


def test_load_translation_profile_reads_both_fields_from_one_snapshot(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    snapshot = Config(translated_dir=str(translated_root))
    profile_data = {"source_language": "zh", "genres": ["urban", "fantasy"]}

    with (
        active_config_scope(snapshot),
        patch("src.services.metadata.file_utils.read_json_locked", return_value=profile_data) as read,
    ):
        profile = load_translation_profile("demo")

    assert profile.source_language == "chinese"
    assert profile.genres == ("urban", "fantasy")
    read.assert_called_once_with(translated_root / "demo" / "metadata.json")


def test_save_source_language_does_not_overwrite_existing_profile(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    novel_root.mkdir(parents=True)
    metadata_file = novel_root / "metadata.json"
    metadata_file.write_text(
        json.dumps({"source_language": "korean", "genres": ["academy"]}),
        encoding="utf-8",
    )

    with active_config_scope(Config(translated_dir=str(translated_root))):
        save_source_language("demo", "chinese")

    assert json.loads(metadata_file.read_text(encoding="utf-8")) == {
        "source_language": "korean",
        "genres": ["academy"],
    }
