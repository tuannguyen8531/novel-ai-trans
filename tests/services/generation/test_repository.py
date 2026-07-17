from pathlib import Path

import pytest

from src.services.generation.repository import ConfigRepository


def test_save_writes_config_inside_novel_directory(tmp_path: Path) -> None:
    path = ConfigRepository(tmp_path).save({"name": "demo"})

    assert path == tmp_path / "demo" / "config.json"
    assert path.is_file()


def test_save_rejects_non_slug_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid novel slug"):
        ConfigRepository(tmp_path).save({"name": "../demo"})
