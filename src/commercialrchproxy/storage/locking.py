"""Small cross-process advisory locks for spool metadata.

The protected data is always published with atomic replace as well.  The lock
only serializes competing allocators/parser workers; it is not used as a data
durability mechanism.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from types import TracebackType


class FileLockTimeout(TimeoutError):
    """Raised when an advisory lock cannot be acquired within its deadline."""


class FileLock:
    def __init__(self, path: Path, *, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> FileLock:
        if self.path.is_symlink():
            raise RuntimeError(f"Refusing symlink lock file: {self.path}")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError(f"Lock is not a regular file: {self.path}")
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            else:
                self.path.chmod(0o600)
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    self._try_lock(fd)
                    break
                except (BlockingIOError, OSError) as exc:
                    if time.monotonic() >= deadline:
                        raise FileLockTimeout(f"Timed out acquiring lock: {self.path}") from exc
                    time.sleep(0.05)
            self._fd = fd
            return self
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _try_lock(fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._fd is None:
            return
        try:
            self._unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None
