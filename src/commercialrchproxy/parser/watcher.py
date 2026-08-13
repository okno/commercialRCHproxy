"""Optional Linux inotify wake-ups with an unconditional polling fallback."""

from __future__ import annotations

import ctypes
import errno
import logging
import os
import select
import sys
import threading
import time
from pathlib import Path
from types import TracebackType

_IN_ATTRIB = 0x00000004
_IN_CLOSE_WRITE = 0x00000008
_IN_MOVED_FROM = 0x00000040
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_DELETE_SELF = 0x00000400
_IN_MOVE_SELF = 0x00000800
_WATCH_MASK = (
    _IN_ATTRIB
    | _IN_CLOSE_WRITE
    | _IN_MOVED_FROM
    | _IN_MOVED_TO
    | _IN_CREATE
    | _IN_DELETE
    | _IN_DELETE_SELF
    | _IN_MOVE_SELF
)
_MAX_WATCHED_DIRECTORIES = 100_000


class SpoolWatcher:
    """Wake a parser scan on filesystem activity, or at every poll deadline.

    inotify is an optimization only.  Missing libc support, watch exhaustion,
    permission errors and non-Linux platforms all retain correct behavior via
    periodic scans of the persistent spool.
    """

    def __init__(self, root: Path, *, enabled: bool, logger: logging.Logger | None = None) -> None:
        self.root = Path(root)
        self.enabled = enabled
        self.logger = logger or logging.getLogger("commercialrchproxy.parser.watcher")
        self._fd: int | None = None
        self._libc: ctypes.CDLL | None = None
        self._path_watches: dict[Path, int] = {}
        self._warning_keys: set[str] = set()
        self._activate_if_possible()

    @property
    def mode(self) -> str:
        return "inotify+polling" if self._fd is not None else "polling"

    @property
    def inotify_available(self) -> bool:
        return self._fd is not None

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warning_keys:
            self._warning_keys.add(key)
            self.logger.warning(message, extra={"event": "parser_watcher_fallback"})

    def _activate_if_possible(self) -> None:
        if self._fd is not None or not self.enabled or not sys.platform.startswith("linux"):
            return
        if self.root.is_symlink() or not self.root.is_dir():
            return
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            initialize = libc.inotify_init1
            add_watch = libc.inotify_add_watch
        except (AttributeError, OSError):
            self._warn_once("unsupported", "inotify is unavailable; parser will use polling")
            return
        initialize.argtypes = [ctypes.c_int]
        initialize.restype = ctypes.c_int
        add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        add_watch.restype = ctypes.c_int
        flags = getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = initialize(flags)
        if fd < 0:
            error = ctypes.get_errno()
            self._warn_once("init", f"inotify initialization failed ({error}); parser will use polling")
            return
        self._fd = fd
        self._libc = libc
        self._refresh_watches()
        if self.root not in self._path_watches:
            self._disable_inotify("inotify could not watch the spool root; parser will use polling")

    def _disable_inotify(self, message: str | None = None) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self._libc = None
        self._path_watches.clear()
        if message:
            self._warn_once("disabled", message)

    def _directories(self) -> list[Path]:
        if self.root.is_symlink() or not self.root.is_dir():
            return []
        result: list[Path] = []
        for base, names, _files in os.walk(self.root, followlinks=False):
            directory = Path(base)
            if directory.is_symlink():
                names[:] = []
                continue
            result.append(directory)
            if len(result) >= _MAX_WATCHED_DIRECTORIES:
                self._warn_once("limit", "inotify directory limit reached; periodic scans remain enabled")
                break
            names[:] = [name for name in names if not (directory / name).is_symlink()]
        return result

    def _refresh_watches(self) -> None:
        if self._fd is None or self._libc is None:
            return
        current: dict[Path, int] = {}
        add_watch = self._libc.inotify_add_watch
        for path in self._directories():
            encoded = os.fsencode(path)
            watch = add_watch(self._fd, encoded, _WATCH_MASK)
            if watch >= 0:
                current[path] = watch
                continue
            error = ctypes.get_errno()
            if path == self.root or error not in {errno.EACCES, errno.ENOENT, errno.ENOSPC}:
                self._warn_once(
                    f"watch-{error}",
                    f"inotify could not watch part of the spool ({error}); periodic scans remain enabled",
                )
        self._path_watches = current

    def _drain(self) -> None:
        if self._fd is None:
            return
        while True:
            try:
                if not os.read(self._fd, 64 * 1024):
                    return
            except BlockingIOError:
                return
            except OSError as exc:
                self._disable_inotify(f"inotify read failed ({exc.errno}); parser will use polling")
                return

    def wait(self, timeout: float, stop: threading.Event) -> bool:
        """Wait for a likely spool change; return false on timeout or stop."""

        if timeout <= 0:
            raise ValueError("watch timeout must be positive")
        self._activate_if_possible()
        if self._fd is None:
            stop.wait(timeout)
            return False
        self._refresh_watches()
        deadline = time.monotonic() + timeout
        while not stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                readable, _, _ = select.select([self._fd], [], [], min(1.0, remaining))
            except (OSError, ValueError) as exc:
                self._disable_inotify(f"inotify wait failed ({exc}); parser will use polling")
                stop.wait(max(0.0, remaining))
                return False
            if readable:
                self._drain()
                return True
        return False

    def close(self) -> None:
        self._disable_inotify()

    def __enter__(self) -> SpoolWatcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
