from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.services import artifacts, backups, catalog, documents, rules
from src.services.drafts import DraftRepository


def test_metadata_documents_round_trip_and_update(tmp_path: Path) -> None:
    documents.write(tmp_path, {"title": "Source"}, trailing_newline=False)
    assert (tmp_path / "metadata.json").read_text(encoding="utf-8").endswith('"Source"\n}')
    assert documents.load(tmp_path) == {"title": "Source"}

    updated = documents.update(tmp_path, lambda data: {**data, "author": "Author"})
    assert updated == {"title": "Source", "author": "Author"}


def test_catalog_repository_owns_directories_progress_and_glossary(tmp_path: Path) -> None:
    novel_root = tmp_path / "demo"
    catalog.create_directories(novel_root)
    assert [path.name for path in catalog.list_directories(tmp_path)] == ["demo"]

    progress_path = novel_root / "progress.json"
    progress_path.write_text(json.dumps({"completed": [1], "failed": [2]}), encoding="utf-8")
    assert catalog.load_progress(progress_path) == {"completed": [1], "failed": [2]}

    progress_path.write_text(json.dumps({"completed": ["3"], "failed": []}), encoding="utf-8")
    assert catalog.load_progress(progress_path) == {"completed": [3], "failed": []}

    progress_path.write_text(json.dumps({"completed": ["invalid"], "failed": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        catalog.load_progress(progress_path)

    glossary_path = novel_root / "glossary.json"
    glossary_path.write_text(
        json.dumps({"terms": {"a": "b"}, "entities": {"c": {}}, "edges": [["c", "d", "friend"]]}),
        encoding="utf-8",
    )
    assert catalog.glossary_counts(glossary_path) == (1, 1, 1)

    catalog.delete_directory(novel_root)
    assert not novel_root.exists()


def test_rules_repository_round_trip(tmp_path: Path) -> None:
    assert rules.read(tmp_path) == ""
    rules.write(tmp_path, "Keep honorifics.")
    assert rules.read(tmp_path) == "Keep honorifics."


def test_artifact_repository_lists_resolves_and_deletes_files(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    epub = artifact_dir / "demo.vi.epub"
    epub.write_bytes(b"epub")
    legacy = tmp_path / "legacy.epub"
    legacy.write_bytes(b"legacy")
    illustrations = tmp_path / "illustrations"
    illustrations.mkdir()
    image = illustrations / "cover.png"
    image.write_bytes(b"png")

    assert artifacts.list_paths(tmp_path) == [epub, legacy]
    assert artifacts.resolve(tmp_path, epub.name) == epub
    assert artifacts.illustration(tmp_path, image.name) == image
    with pytest.raises(FileNotFoundError):
        artifacts.resolve(tmp_path, "../escape.epub")

    artifacts.delete(tmp_path, epub.name)
    assert not epub.exists()


def test_draft_repository_round_trip_cleanup_and_validation(tmp_path: Path) -> None:
    repository = DraftRepository(tmp_path)
    now = datetime.now(UTC)
    repository.save(
        {
            "draft_id": "expired",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
        }
    )
    repository.save(
        {
            "draft_id": "active",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }
    )

    assert repository.load("active")["draft_id"] == "active"
    repository.cleanup(now)
    assert [record["draft_id"] for record in repository.list()] == ["active"]
    with pytest.raises(ValueError):
        repository.load("../escape")


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
