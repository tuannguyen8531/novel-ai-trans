"""Shared helpers for locked and atomic file writes."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Protocol, cast

try:
    import fcntl

    msvcrt = None
except ImportError:
    fcntl = None
    import msvcrt


class FcntlModule(Protocol):
    LOCK_EX: int
    LOCK_SH: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int, /) -> None: ...


class MsvcrtModule(Protocol):
    LK_NBLCK: int
    LK_LOCK: int
    LK_UNLCK: int

    def locking(self, fd: int, mode: int, nbytes: int, /) -> None: ...


fchmod: Callable[[int, int], None] | None = getattr(os, "fchmod", None)

JsonObject = dict[str, Any]


def _lock_file(fd: int, *, exclusive: bool, nonblocking: bool = False) -> None:
    if fcntl is not None:
        _fcntl = cast(FcntlModule, fcntl)
        operation = _fcntl.LOCK_EX if exclusive else _fcntl.LOCK_SH
        if nonblocking:
            operation |= _fcntl.LOCK_NB
        _fcntl.flock(fd, operation)
        return
    if msvcrt is None:
        return

    _msvcrt = cast(MsvcrtModule, msvcrt)
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)
    mode = _msvcrt.LK_NBLCK if nonblocking else _msvcrt.LK_LOCK
    try:
        _msvcrt.locking(fd, mode, 1)
    except OSError as error:
        if nonblocking:
            raise BlockingIOError(error.strerror) from error
        raise


def _unlock_file(fd: int) -> None:
    if fcntl is not None:
        _fcntl = cast(FcntlModule, fcntl)
        _fcntl.flock(fd, _fcntl.LOCK_UN)
        return
    if msvcrt is None:
        return

    _msvcrt = cast(MsvcrtModule, msvcrt)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextmanager
def exclusive_file_lock(path: Path, *, blocking: bool = True) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as lock_file:
        _lock_file(lock_file.fileno(), exclusive=True, nonblocking=not blocking)
        try:
            yield
        finally:
            _unlock_file(lock_file.fileno())


def read_json_locked(path: Path) -> JsonObject:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with open(path, encoding="utf-8") as source:
        _lock_file(source.fileno(), exclusive=False)
        try:
            data = json.load(source)
        finally:
            _unlock_file(source.fileno())
    return data if isinstance(data, dict) else {}


def merge_json_locked(path: Path, updater: Callable[[JsonObject], JsonObject]) -> JsonObject:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as target:
        _lock_file(target.fileno(), exclusive=True)
        try:
            target.seek(0)
            try:
                existing_data = json.load(target)
            except json.JSONDecodeError, ValueError:
                existing_data = {}
            if not isinstance(existing_data, dict):
                existing_data = {}
            new_data = updater(existing_data)
            target.seek(0)
            target.truncate()
            json.dump(new_data, target, ensure_ascii=False, indent=2)
        finally:
            _unlock_file(target.fileno())
    return new_data


def _temporary_file(path: Path) -> tuple[int, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    if path.exists() and fchmod is not None:
        with suppress(AttributeError):
            fchmod(fd, stat.S_IMODE(path.stat().st_mode))
    return fd, Path(temp_name)


def write_text_atomic(path: Path, text: str) -> None:
    fd, temp_path = _temporary_file(path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, path)
    except Exception:
        with suppress(OSError):
            os.close(fd)
        temp_path.unlink(missing_ok=True)
        raise


def write_bytes_atomic(path: Path, data: bytes) -> None:
    fd, temp_path = _temporary_file(path)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, path)
    except Exception:
        with suppress(OSError):
            os.close(fd)
        temp_path.unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, data: object) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
