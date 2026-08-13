"""No-follow, fsync-and-replace helpers shared by dumper and parser."""

from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Callable
from pathlib import Path


def ensure_directory(path: Path, mode: int = 0o750) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"Refusing symlink directory: {path}")
    path.mkdir(mode=mode, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
        raise RuntimeError(f"Unsafe output directory: {path}")
    try:
        path.chmod(mode)
    except OSError:
        pass


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o640, directory_mode: int = 0o750) -> None:
    ensure_directory(path.parent, directory_mode)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = os.open(temp, flags, 0o600)
    try:
        stream = os.fdopen(fd, "wb", closefd=True)
        fd = None
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        fsync_directory(path.parent)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def atomic_generate(
    path: Path,
    generator: Callable[[Path], None],
    *,
    mode: int = 0o640,
    directory_mode: int = 0o750,
) -> None:
    ensure_directory(path.parent, directory_mode)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    os.close(fd)
    try:
        generator(temp)
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        fsync_directory(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
