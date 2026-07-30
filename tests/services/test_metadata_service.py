import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Config, active_config_scope
from src.services.metadata import (
    load_genres,
    load_source_language,
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


def test_source_language_falls_back_when_translated_dir_is_unavailable(tmp_path: Path) -> None:
    with (
        patch("src.services.metadata.config") as mock_config,
        patch("src.services.metadata.METADATA_FALLBACK_DIR", tmp_path),
        patch("src.services.metadata.LEGACY_GLOSSARY_FALLBACK_DIR", tmp_path),
    ):
        mock_config.translated_dir = ""
        save_source_language("demo", "korean")
        assert load_source_language("demo") == "korean"
        assert metadata_path("demo") == tmp_path / "demo.metadata.json"


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
