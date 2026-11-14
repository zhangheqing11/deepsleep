"""Small cross-platform advisory file lock used by local demo tooling."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import time


def _windows_lock(stream, *, blocking: bool) -> None:
    """Acquire byte zero with Windows retry semantics.

    The Windows locking primitive gives up after a bounded number of retries.
    The public lock API promises a genuinely blocking mode, so use the
    non-blocking primitive in a small retry loop instead.
    """
    import msvcrt

    while True:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            held = (getattr(exc, "winerror", None) == 33
                    or getattr(exc, "errno", None) in (13, 36, 11))
            if not held or not blocking:
                if not blocking and held:
                    raise BlockingIOError from exc
                raise
            time.sleep(0.05)


@contextmanager
def file_lock(path: str | Path, *, blocking: bool = True):
    """Hold an advisory lock on *path* for the duration of the context.

    The lock file is deliberately kept on disk so Windows does not need to
    delete an open file.  The contents are never used.  ``blocking=False``
    raises ``BlockingIOError`` when another process owns the lock.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stream = target.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            # msvcrt.locking locks bytes from the current file position.
            # Keep one byte in the lock file so an empty newly-created file is
            # still lockable.
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            _windows_lock(stream, blocking=blocking)
            try:
                yield stream
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            mode = fcntl.LOCK_EX | (fcntl.LOCK_NB if not blocking else 0)
            fcntl.flock(stream.fileno(), mode)
            try:
                yield stream
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()
