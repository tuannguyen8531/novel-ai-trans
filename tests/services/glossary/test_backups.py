from __future__ import annotations

from pathlib import Path

from src.services.glossary import backups


def test_glossary_backup_prepare_write_complete_and_restore(tmp_path: Path) -> None:
    novel_root = tmp_path / "novel"
    output = novel_root / "output"
    output.mkdir(parents=True)
    chapter = output / "chapter_001.txt"
    chapter.write_text("before", encoding="utf-8")
    backup_root = tmp_path / "backups"

    manifest, manifest_path = backups.prepare(
        backup_root,
        "backup-id",
        novel="novel",
        target="vi",
        novel_root=novel_root,
        files=[chapter],
        pending=[{"old": "a", "new": "b"}],
    )
    assert backups.write_chapters({chapter: "after"}) == 1
    backups.complete(manifest_path, manifest, [])

    loaded, backup_dir = backups.load(backup_root, "backup-id")
    assert loaded["status"] == "completed"
    backups.restore_files(backup_dir, novel_root, loaded["files"])
    assert chapter.read_text(encoding="utf-8") == "before"
