#!/usr/bin/env python
"""One heavy run at a time, machine-wide: the GPU is a single 4 GB resource.

Three `transcribe-words.py` runs were once launched inside two minutes by
different sessions working in this repo at once. Each loaded its own `large-v3`
(~2-3 GB) into a 4 GB card, so all three thrashed and *none* finished: the card
read 100% busy and 3.9/4.0 GB used for twenty minutes while no transcript was
written. Nothing failed, which is what made it expensive -- there was no error
to read, only three jobs that were each nearly done forever. Diagnosing it took
a CIM sweep of every python process's command line.

So a run that wants the GPU takes this lock first and the others queue behind
it. Serialising is strictly better than failing here: the same work still gets
done, just one at a time, which is the only way any of it finishes at all.

    with _gpulock.hold("gpu", tool="transcribe-words", project="abc"):
        ...                      # the card is ours for this block

The lock is a file under `temp/locks/`, created O_EXCL so two racing acquirers
cannot both win, holding JSON that names the holder. Two things make it safe to
leave lying around:

  * **A dead holder does not block anyone.** The pid is checked for liveness on
    every contended acquire and a dead one is stolen. This matters because the
    way these runs end is often a forced kill, which runs no cleanup -- the
    incident above was resolved by killing two of the three.
  * **A holder only ever releases its own lock.** If ours went stale and was
    stolen while we ran, we must not delete the new owner's file on the way out.

Pid reuse is the residual hole: a recycled pid reads as alive and would keep a
dead lock standing. MAX_AGE_S is the backstop -- a lock older than that is
stale regardless of what its pid says.

Stdlib only, and no `_env` import, for the same reason as `_runlog.py`: this is
what you read when a run is wedged, and a broken venv is one of the things that
can wedge it. `gpu-lock.py` is the reader.
"""
import os
import io
import json
import time
import errno

SCHEMA = 1
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A run that outlives this is treated as abandoned no matter what its pid says,
# which is the only defence against a reused pid. Well clear of a real job: the
# longest thing that takes the card is a full-length transcribe, ~30 minutes on
# this machine when it is not being fought over.
MAX_AGE_S = 6 * 3600


def locks_dir():
    return os.path.join(ROOT, "temp", "locks")


def lock_path(name="gpu"):
    return os.path.join(locks_dir(), name + ".lock")


def alive(pid):
    """Is this pid a live process? False for a dead-but-unreaped one too."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        # QUERY_LIMITED_INFORMATION works without full rights to the process.
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if k.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == 259          # STILL_ACTIVE
            return True
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM             # alive, just not ours
    return True


def read(name="gpu"):
    """The current holder as a dict, or None. Never raises."""
    try:
        with io.open(lock_path(name), "r", encoding="utf-8") as f:
            rec = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def stale(rec):
    """Why this lock is dead, or None if it is genuinely held."""
    if not rec:
        return "unreadable"
    if not alive(rec.get("pid")):
        return "holder pid %s is gone" % rec.get("pid")
    age = time.time() - float(rec.get("started_epoch") or 0)
    if age > MAX_AGE_S:
        return "held %.1f h, over the %.0f h cap" % (age / 3600.0,
                                                     MAX_AGE_S / 3600.0)
    return None


def _write_new(path, rec):
    """Create the lock, or report that someone else holds it. Atomic."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as e:
        if e.errno == errno.EEXIST:
            return False
        raise
    with io.open(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f)
    return True


def acquire(name="gpu", tool="?", project=None, wait=0, poll=5.0, on_wait=None):
    """Take the lock, waiting up to `wait` seconds. Returns a token or None.

    `on_wait(rec, waited)` is called once while blocked, so the caller can say
    who it is queued behind rather than sitting there looking hung.
    """
    os.makedirs(locks_dir(), exist_ok=True)
    path = lock_path(name)
    rec = {"schema": SCHEMA, "pid": os.getpid(), "tool": tool,
           "project": project, "host": _host(),
           "started_epoch": time.time(),
           "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    t0 = time.time()
    told = False
    while True:
        if _write_new(path, rec):
            return rec
        held = read(name)
        why = stale(held)
        if why:
            # Steal it -- but only the exact file we just judged dead: another
            # acquirer may be stealing at the same moment and win the race.
            _steal(path, name, held)
            continue
        waited = time.time() - t0
        if waited >= wait:
            return None
        if on_wait and not told:
            on_wait(held, waited)
            told = True
        time.sleep(min(poll, max(0.1, wait - waited)))


def _steal(path, name, held):
    try:
        cur = read(name)
        if cur and held and cur.get("pid") != held.get("pid"):
            return                                # someone already replaced it
        os.remove(path)
    except OSError:
        pass                                      # lost the race; loop retries


def release(token, name="gpu"):
    """Drop the lock -- but only if it is still ours."""
    if not token:
        return
    cur = read(name)
    if cur and cur.get("pid") == token.get("pid") \
            and cur.get("started_epoch") == token.get("started_epoch"):
        try:
            os.remove(lock_path(name))
        except OSError:
            pass


def _host():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "?"


class hold(object):
    """Context manager. `blocked` is set when the wait timed out."""

    def __init__(self, name="gpu", tool="?", project=None, wait=0, poll=5.0,
                 on_wait=None, required=True):
        self.name, self.tool, self.project = name, tool, project
        self.wait, self.poll, self.on_wait = wait, poll, on_wait
        self.required = required
        self.token = None
        self.blocked = None

    def __enter__(self):
        self.token = acquire(self.name, self.tool, self.project,
                             self.wait, self.poll, self.on_wait)
        if self.token is None:
            self.blocked = read(self.name)
            if self.required:
                raise Busy(self.name, self.blocked)
        return self

    def __exit__(self, *exc):
        release(self.token, self.name)
        self.token = None
        return False


class Busy(RuntimeError):
    def __init__(self, name, held):
        self.held = held
        RuntimeError.__init__(self, describe(held, name))


def describe(rec, name="gpu"):
    if not rec:
        return "%s: free" % name
    age = time.time() - float(rec.get("started_epoch") or 0)
    return ("%s: held by pid %s (%s%s) since %s, %s"
            % (name, rec.get("pid"), rec.get("tool"),
               "/" + rec["project"] if rec.get("project") else "",
               rec.get("started_utc"), _dur(age)))


def _dur(s):
    s = int(max(0, s))
    return "%dh%02dm" % (s // 3600, (s % 3600) // 60) if s >= 3600 \
        else "%dm%02ds" % (s // 60, s % 60)
