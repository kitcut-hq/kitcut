#!/usr/bin/env python
"""Exercise the single-run GPU lock -- above all, the killed-holder case.

A lock is only as good as its worst exit. These runs are routinely ended by a
forced kill (that is how the original three-way pile-up on the 4 GB card was
resolved), and a kill runs no `atexit`, no `finally`, no cleanup of any kind.
So the lock file outlives its owner, and if nothing noticed, the card would be
fenced off forever by a process that no longer exists -- swapping a deadlock
for a permanent block, which is worse.

The defence is that liveness is checked on every contended acquire rather than
trusted to the holder's cooperation. This proves it, including by really
spawning a child, really killing it, and checking the next acquirer gets in.

No GPU, no model, no files outside a temp dir: the real `temp/locks/gpu.lock`
is never touched, so this is safe to run while a transcription is in flight.

Invoke as:  python scripts/check-gpulock.py [-v]
"""

import sys
import os
import json
import time
import shutil
import tempfile
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _gpulock  # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
FAILED = []
VERBOSE = False


def ok(name, cond, detail=""):
    print(
        ("  PASS  " if cond else "  FAIL  ")
        + name
        + (" -- " + detail if detail and (VERBOSE or not cond) else "")
    )
    if not cond:
        FAILED.append(name)
    return cond


def sandbox():
    """Point the lock at a throwaway root so the live gpu.lock is untouched."""
    d = tempfile.mkdtemp(prefix="gpulock-check-")
    _gpulock.ROOT = d
    return d


# --------------------------------------------------------------- basic cycle


def test_cycle():
    print("acquire / release")
    tok = _gpulock.acquire("t", tool="a")
    ok("acquire on a free lock succeeds", tok is not None)
    ok("the lock file exists", os.path.exists(_gpulock.lock_path("t")))
    ok("a second acquire is refused", _gpulock.acquire("t", tool="b", wait=0) is None)
    _gpulock.release(tok, "t")
    ok("release frees it", not os.path.exists(_gpulock.lock_path("t")))
    ok("acquire works again after release", _gpulock.acquire("t", tool="c") is not None)
    _gpulock.release(_gpulock.read("t"), "t")


# ------------------------------------------------- the case the user asked for


def test_dead_pid_is_stolen():
    print("killed holder (synthetic: a pid that cannot exist)")
    path = _gpulock.lock_path("t")
    os.makedirs(_gpulock.locks_dir(), exist_ok=True)
    # A pid that is not running. High and odd-numbered; verified dead below.
    dead = 999_999
    while _gpulock.alive(dead):
        dead -= 2
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema": 1,
                "pid": dead,
                "tool": "killed",
                "started_epoch": time.time(),
                "started_utc": "2026-01-01T00:00:00Z",
            },
            f,
        )
    ok(
        "a dead holder reads as stale",
        _gpulock.stale(_gpulock.read("t")) is not None,
        str(_gpulock.stale(_gpulock.read("t"))),
    )
    tok = _gpulock.acquire("t", tool="next", wait=0)
    ok("the next run steals it without waiting", tok is not None)
    ok("the stealer now owns it", (_gpulock.read("t") or {}).get("pid") == os.getpid())
    _gpulock.release(tok, "t")


def test_real_kill():
    """Spawn a real holder, kill it hard, and confirm the lock is recoverable."""
    print("killed holder (real: spawn, hard-kill, re-acquire)")
    root = _gpulock.ROOT
    child = (
        "import sys,time,os;"
        "sys.path.insert(0,%r);"
        "import _gpulock;"
        "_gpulock.ROOT=%r;"
        "t=_gpulock.acquire('t',tool='victim');"
        "open(os.path.join(%r,'held'),'w').write(str(os.getpid()));"
        "time.sleep(600)" % (SCRIPTS, root, root)
    )
    p = subprocess.Popen([sys.executable, "-c", child])
    marker = os.path.join(root, "held")
    for _ in range(100):
        if os.path.exists(marker):
            break
        time.sleep(0.1)
    held = ok("the child took the lock", os.path.exists(marker))
    if not held:
        p.kill()
        return
    # NOT p.pid: under _env this process is the venv python, and on Windows
    # that .exe can be a shim which launches the real interpreter under a
    # different pid -- so Popen's pid is the shim's. The pid that matters is
    # the one the worker reports for itself, because that is the process
    # acquire() recorded and the process actually holding VRAM.
    worker = None
    for _ in range(100):  # the file can exist a moment before it fills
        try:
            worker = int(open(marker, encoding="utf-8").read().strip())
            break
        except ValueError:
            time.sleep(0.05)
    rec = _gpulock.read("t")
    ok(
        "the lock names the worker's own pid",
        rec and rec.get("pid") == worker,
        "lock=%s worker=%s popen=%s" % (rec and rec.get("pid"), worker, p.pid),
    )
    ok("while it lives, we are refused", _gpulock.acquire("t", tool="me", wait=0) is None)

    p.kill()  # no atexit, no finally -- the real failure
    p.wait(timeout=30)
    ok(
        "the lock file survives the kill (nobody released it)",
        os.path.exists(_gpulock.lock_path("t")),
    )
    for _ in range(150):  # the OS can take a moment to reap the pid
        if not _gpulock.alive(worker):
            break
        time.sleep(0.1)
    ok("the killed worker no longer reads as alive", not _gpulock.alive(worker))
    tok = _gpulock.acquire("t", tool="me", wait=0)
    ok("the next run recovers the lock with no manual clear", tok is not None)
    _gpulock.release(tok, "t")


def test_age_backstop():
    print("pid reuse backstop")
    path = _gpulock.lock_path("t")
    os.makedirs(_gpulock.locks_dir(), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:  # our own live pid ...
        json.dump(
            {
                "schema": 1,
                "pid": os.getpid(),
                "tool": "ancient",
                "started_epoch": time.time() - (_gpulock.MAX_AGE_S + 60),
                "started_utc": "2026-01-01T00:00:00Z",
            },
            f,
        )
    ok(
        "a live pid holding it past the age cap is still stale",
        _gpulock.stale(_gpulock.read("t")) is not None,
        str(_gpulock.stale(_gpulock.read("t"))),
    )
    ok("and it is stealable", _gpulock.acquire("t", tool="x", wait=0) is not None)
    _gpulock.release(_gpulock.read("t"), "t")


def test_release_is_owned():
    print("a holder only releases its own lock")
    tok = _gpulock.acquire("t", tool="first")
    _gpulock.release(tok, "t")
    other = _gpulock.acquire("t", tool="second")  # someone else now owns it
    _gpulock.release(tok, "t")  # the old token tries again
    ok("a stale token cannot delete the new owner's lock", os.path.exists(_gpulock.lock_path("t")))
    ok("the new owner is intact", (_gpulock.read("t") or {}).get("tool") == "second")
    _gpulock.release(other, "t")


def test_queue_then_proceed():
    print("waiting behind a holder that goes away")
    dead = 999_999
    while _gpulock.alive(dead):
        dead -= 2
    os.makedirs(_gpulock.locks_dir(), exist_ok=True)
    with open(_gpulock.lock_path("t"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema": 1,
                "pid": dead,
                "tool": "gone",
                "started_epoch": time.time(),
                "started_utc": "x",
            },
            f,
        )
    t0 = time.time()
    tok = _gpulock.acquire("t", tool="waiter", wait=30, poll=0.2)
    ok(
        "a dead holder is stolen immediately, not waited out",
        tok is not None and time.time() - t0 < 5,
        "%.2fs" % (time.time() - t0),
    )
    _gpulock.release(tok, "t")


def test_describe():
    print("the diagnostic string")
    ok("free reads as free", "free" in _gpulock.describe(None, "t"))
    tok = _gpulock.acquire("t", tool="tr", project="abc")
    d = _gpulock.describe(_gpulock.read("t"), "t")
    ok("a held lock names tool and project", "tr" in d and "abc" in d, d)
    _gpulock.release(tok, "t")


def main():
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    VERBOSE = ap.parse_args().verbose

    real = _gpulock.lock_path("gpu")
    before = os.path.exists(real)
    d = sandbox()
    print("sandbox: %s\n" % d)
    try:
        for t in (
            test_cycle,
            test_dead_pid_is_stolen,
            test_real_kill,
            test_age_backstop,
            test_release_is_owned,
            test_queue_then_proceed,
            test_describe,
        ):
            t()
            print()
    finally:
        _gpulock.ROOT = os.path.dirname(SCRIPTS)
        shutil.rmtree(d, ignore_errors=True)

    ok("the real gpu.lock was not touched", os.path.exists(_gpulock.lock_path("gpu")) == before)

    print("\n%s" % ("FAILED: " + ", ".join(FAILED) if FAILED else "all checks passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
