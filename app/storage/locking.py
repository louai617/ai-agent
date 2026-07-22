"""Cross-process + cross-thread file locking.

Excel workbooks are read/modified/written in full by ``openpyxl``. To make
concurrent writes safe we serialise every read-modify-write behind a lock that
is held both:

* **within the process** - a per-path ``threading.RLock`` (multiple worker
  threads), and
* **across processes** - an exclusive lock file created atomically with
  ``O_CREAT | O_EXCL`` (a second process running the app, or a headless run
  alongside the desktop app).

The implementation is dependency-free (no ``fcntl``/``msvcrt``/``filelock``) so
it behaves identically on Windows, macOS and Linux. Stale locks left behind by
a crashed process are reclaimed after ``stale_after`` seconds.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path
from types import TracebackType

from app.core.logging import get_logger

logger = get_logger(__name__)

# One in-process lock per absolute file path, shared across FileLock instances.
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_REGISTRY_GUARD = threading.Lock()


def _process_lock_for(path: str) -> threading.RLock:
    with _REGISTRY_GUARD:
        lock = _PROCESS_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[path] = lock
        return lock


class LockTimeout(RuntimeError):
    """Raised when a lock could not be acquired within ``timeout`` seconds."""


class FileLock:
    """Reentrant, cross-process lock guarding a single file.

    Use as a context manager::

        with FileLock("data/properties.xlsx"):
            ...  # exclusive read-modify-write

    The lock file lives next to the target as ``<name>.lock``.
    """

    def __init__(
        self,
        target: str | Path,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
        stale_after: float = 120.0,
    ) -> None:
        self._target = Path(target).resolve()
        self._lock_path = self._target.with_name(self._target.name + ".lock")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._stale_after = stale_after
        self._process_lock = _process_lock_for(str(self._target))
        self._fd: int | None = None
        self._depth = 0

    # ------------------------------------------------------------------ acquire

    def acquire(self) -> None:
        # Serialise threads in this process first (reentrant).
        self._process_lock.acquire()
        self._depth += 1
        if self._depth > 1:
            return  # already hold the cross-process lock on this thread stack
        try:
            self._acquire_file_lock()
        except BaseException:
            self._depth -= 1
            self._process_lock.release()
            raise

    def _acquire_file_lock(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                self._fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode("ascii"))
                return
            except FileExistsError:
                if self._reclaim_if_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"Timed out after {self._timeout:g}s waiting for {self._lock_path}"
                    ) from None
                time.sleep(self._poll_interval)

    def _reclaim_if_stale(self) -> bool:
        """Delete an abandoned lock file older than ``stale_after`` seconds."""
        try:
            age = time.time() - self._lock_path.stat().st_mtime
        except FileNotFoundError:
            return True  # vanished - retry immediately
        if age > self._stale_after:
            logger.warning("Reclaiming stale lock %s (age %.0fs)", self._lock_path, age)
            with contextlib.suppress(FileNotFoundError):
                self._lock_path.unlink()
            return True
        return False

    # ------------------------------------------------------------------ release

    def release(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        try:
            if self._depth == 0:
                self._release_file_lock()
        finally:
            self._process_lock.release()

    def _release_file_lock(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        with contextlib.suppress(FileNotFoundError):
            self._lock_path.unlink()

    # --------------------------------------------------------------- protocol

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
