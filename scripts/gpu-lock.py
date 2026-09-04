#!/usr/bin/env python
"""Who has the GPU, and is that holder actually alive?

The question this answers used to cost a CIM sweep of every python process's
command line, which is how a three-way deadlock over one 4 GB card went twenty
minutes undiagnosed: nothing had failed, so there was no error to read.

    python scripts/gpu-lock.py                 # who holds it (free; the default)
    python scripts/gpu-lock.py --list          # the same, plus every other lock
    python scripts/gpu-lock.py --clear         # drop it, but only if it is dead
    python scripts/gpu-lock.py --clear --force # drop it regardless

`--clear` refuses a live holder on purpose. A lock whose process is still
running is not stale, and breaking it would put a second job back on the card --
which is the exact failure this whole mechanism exists to prevent. `--force` is
there for the case where you have already killed the holder yourself and the
liveness check disagrees; it names what it is about to break before doing it.

`_gpulock.py` writes the file; this reads it. Stdlib only and no `_env` import,
like `run-log.py`: this is what you reach for when a run is wedged, and a broken
venv is one of the things that can wedge it.

Invoke as:  python scripts/gpu-lock.py [--list] [--clear [--force]] [--name gpu]
"""

import os
import sys
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gpulock  # noqa: E402 -- stdlib-only sibling, no venv needed

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def show(name):
    rec = _gpulock.read(name)
    print(_gpulock.describe(rec, name))
    if not rec:
        return 0
    why = _gpulock.stale(rec)
    if why:
        print("  STALE: %s" % why)
        print(
            "  -- clear it with: python scripts/gpu-lock.py --clear"
            + ("" if name == "gpu" else " --name %s" % name)
        )
    else:
        print("  holder is alive; a second run would queue behind it")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="gpu", help="which lock (default: gpu)")
    ap.add_argument("--list", action="store_true", help="show every lock file, not just --name")
    ap.add_argument("--clear", action="store_true", help="remove the lock if its holder is dead")
    ap.add_argument(
        "--force", action="store_true", help="with --clear, remove it even if the holder is alive"
    )
    args = ap.parse_args()

    if args.clear:
        rec = _gpulock.read(args.name)
        if not rec:
            print("%s: free -- nothing to clear" % args.name)
            return 0
        why = _gpulock.stale(rec)
        if not why and not args.force:
            print(_gpulock.describe(rec, args.name))
            print(
                "REFUSED: that holder is alive. Clearing would put a second "
                "job on the card, which is what this lock prevents."
            )
            print("If you have already killed pid %s, re-run with --force." % rec.get("pid"))
            return 1
        print("clearing: %s" % _gpulock.describe(rec, args.name))
        print("  reason: %s" % (why or "forced by --force"))
        try:
            os.remove(_gpulock.lock_path(args.name))
        except OSError as e:
            print("could not remove: %s" % e)
            return 1
        print("%s: free" % args.name)
        return 0

    rc = show(args.name)
    if args.list:
        others = sorted(glob.glob(os.path.join(_gpulock.locks_dir(), "*.lock")))
        others = [os.path.splitext(os.path.basename(p))[0] for p in others]
        for other in others:
            if other != args.name:
                print()
                show(other)
        if not others:
            print("\nno lock files under temp/locks/")
    return rc


if __name__ == "__main__":
    sys.exit(main())
