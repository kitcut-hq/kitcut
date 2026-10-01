"""File locks that hold across processes: flock on Linux (the VM), msvcrt on Windows (the laptop).

    h = try_lock(path)            a handle, or None when another process holds it (never waits)
    unlock(h)                     let it go (a process that dies lets go of all its locks)
    with locked(path): ...        wait for it (a short critical section: read, change, write)

Two studio servers run side by side during a ship (peers.py), on one STUDIO_HOME. Anything both
may write -- a film's studio.json, a person's library index, the cost outbox -- is read, changed
and written under locked(). The kernel owns the lock, so a crash never leaves one behind; the
file itself is only a name and may stay. stdlib only.
"""

import os
import sys
import time
import contextlib

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


def try_lock(path):
    """An exclusive lock on `path` (created if missing), without waiting: its handle, or None
    when another holder has it -- another process, or another handle in this one."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if sys.platform == "win32":
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def unlock(fd):
    if fd is None:
        return
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        os.close(fd)


class LockTimeout(TimeoutError):
    pass


@contextlib.contextmanager
def locked(path, timeout=30.0, poll=0.02):
    """Hold `path`'s lock for the block, waiting up to `timeout` s for it (LockTimeout after).
    Not reentrant: a block must not take the same lock again."""
    t0 = time.monotonic()
    while True:
        fd = try_lock(path)
        if fd is not None:
            break
        if time.monotonic() - t0 > timeout:
            raise LockTimeout("%s still held after %.0f s" % (path, timeout))
        time.sleep(poll)
    try:
        yield
    finally:
        unlock(fd)
