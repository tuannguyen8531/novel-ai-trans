from __future__ import annotations

import json
from pathlib import Path

from src.services import insertion
from src.utils import files


def test_recover_prepared_backup_restores_interrupted_insert(tmp_path: Path) -> None:
    input_dir = tmp_path / "translated" / "demo" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "chapter_001.txt").write_text("one", encoding="utf-8")
    (input_dir / "chapter_002.txt").write_text("two", encoding="utf-8")
    progress_path = tmp_path / "runtime" / "progress" / "demo.json"
    files.write_json_atomic(progress_path, {"completed": [1, 2], "failed": []})

    group = insertion.FileGroup("input", input_dir, "txt")
    state_file = insertion.StateFile(
        "progress-vi",
        progress_path,
        {"completed": [1, 2], "failed": []},
        {"completed": [2, 3], "failed": []},
    )
    backup_root = tmp_path / "runtime" / "insert-backups"
    backup_dir = insertion.create_backup(
        novel="demo",
        operation_id="interrupted-job",
        number=1,
        previous_last=2,
        backup_root=backup_root,
        groups=[group],
        state_files=[state_file],
    )

    insertion.shift_group(group, 1)
    (input_dir / "chapter_001.txt").write_text("new", encoding="utf-8")
    insertion.write_state_files([state_file])

    assert insertion.recover_prepared_backups(backup_root) == ["interrupted-job"]
    assert (input_dir / "chapter_001.txt").read_text(encoding="utf-8") == "one"
    assert (input_dir / "chapter_002.txt").read_text(encoding="utf-8") == "two"
    assert not (input_dir / "chapter_003.txt").exists()
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {"completed": [1, 2], "failed": []}
    assert json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))["status"] == "recovered"
