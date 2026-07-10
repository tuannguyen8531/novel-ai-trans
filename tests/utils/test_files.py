import json
from pathlib import Path

import pytest

from src.utils.files import (
    exclusive_file_lock,
    merge_json_locked,
    read_json_locked,
    write_bytes_atomic,
    write_json_atomic,
    write_text_atomic,
)


def test_atomic_writers_replace_file_content(tmp_path: Path) -> None:
    text_path = tmp_path / "nested" / "chapter.txt"
    bytes_path = tmp_path / "image.bin"
    json_path = tmp_path / "metadata.json"

    write_text_atomic(text_path, "updated")
    write_bytes_atomic(bytes_path, b"image")
    write_json_atomic(json_path, {"title": "Demo"})

    assert text_path.read_text(encoding="utf-8") == "updated"
    assert bytes_path.read_bytes() == b"image"
    assert json_path.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"title": "Demo"}
    assert not list(tmp_path.rglob("*.tmp"))


def test_merge_json_locked_recovers_invalid_content(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    path.write_text("invalid", encoding="utf-8")

    result = merge_json_locked(path, lambda data: {**data, "terms": {"source": "target"}})

    assert result == {"terms": {"source": "target"}}
    assert read_json_locked(path) == result


def test_read_json_locked_returns_empty_object_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.touch()

    assert read_json_locked(path) == {}


def test_exclusive_file_lock_rejects_second_nonblocking_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "novel.lock"

    with (
        exclusive_file_lock(lock_path),
        pytest.raises(BlockingIOError),
        exclusive_file_lock(lock_path, blocking=False),
    ):
        pytest.fail("second lock unexpectedly acquired")
