from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src import paths
from src.application import config as app_config
from src.cli.insertion import main
from src.config import Config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_insert_cli_creates_empty_chapter_and_shifts_later_data(tmp_path: Path, capsys) -> None:
    translated_root = tmp_path / "translated"
    novel_root = translated_root / "demo"
    _write(novel_root / "input" / "chapter_001.txt", "one")
    _write(novel_root / "input" / "chapter_002.txt", "two")
    _write(novel_root / "output" / "chapter_002.txt", "translated two")

    runtime_root = tmp_path / "runtime"
    progress_path = runtime_root / "progress" / "demo.json"
    _write(progress_path, json.dumps({"completed": [1, 2], "failed": []}))

    config = Config(translated_dir=str(translated_root), target_language="vi")
    with (
        patch.object(app_config, "get_config", return_value=config),
        patch.multiple(
            paths,
            PROGRESS_DIR=runtime_root / "progress",
            REPORT_DIR=runtime_root / "reports",
            INSERT_BACKUP_DIR=runtime_root / "insert-backups",
            LOCK_DIR=runtime_root / "locks",
        ),
    ):
        exit_code = main(["demo", "2"])

    assert exit_code == 0
    assert (novel_root / "input" / "chapter_002.txt").read_text(encoding="utf-8") == ""
    assert (novel_root / "input" / "chapter_003.txt").read_text(encoding="utf-8") == "two"
    assert not (novel_root / "output" / "chapter_002.txt").exists()
    assert (novel_root / "output" / "chapter_003.txt").read_text(encoding="utf-8") == "translated two"
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {"completed": [1, 3], "failed": []}
    assert len(list((runtime_root / "insert-backups" / "demo").glob("*/manifest.json"))) == 1
    assert "Inserted empty chapter 2 into demo" in capsys.readouterr().out


def test_insert_cli_reports_invalid_gap(tmp_path: Path, capsys) -> None:
    translated_root = tmp_path / "translated"
    _write(translated_root / "demo" / "input" / "chapter_001.txt", "one")
    config = Config(translated_dir=str(translated_root))

    with patch.object(app_config, "get_config", return_value=config):
        exit_code = main(["demo", "3"])

    assert exit_code == 1
    assert "next available chapter is 2" in capsys.readouterr().err
