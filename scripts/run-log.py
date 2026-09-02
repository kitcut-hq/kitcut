#!/usr/bin/env python
"""Read the run log: what ran, how long, and how it ended.

    python scripts/run-log.py --project books-giveaway            # the last run
    python scripts/run-log.py --project books-giveaway --list     # every run
    python scripts/run-log.py --project books-giveaway --follow   # tail a live one
    python scripts/run-log.py --project books-giveaway --notes    # only the facts

`_runlog.py` writes the file; this reads it. Stdlib only and no `_env` import,
so it stays usable from a watch loop or a status line without a venv re-exec --
and, more to the point, usable when the venv is the thing that is broken.

Invoke as:  python scripts/run-log.py --project <id> [--list|--follow|--notes]
"""
import os
import sys
import time
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _runlog  # noqa: E402 -- stdlib-only sibling, no venv needed

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OUTCOME = {"ok": "OK", "failed": "FAILED", "stopped": "STOPPED",
           "interrupted": "INTERRUPTED", "running": "RUNNING"}


def fmt(t):
    t = float(t or 0)
    return f"{int(t) // 60}:{t % 60:04.1f}"


def project_dir(pid):
    # projects/ lives beside scripts/; _project.projects_dir() is the real
    # resolver, but importing it would pull in _env and its re-exec
    return os.path.join(ROOT, "projects", pid)


def show(path, notes_only=False):
    recs = _runlog.read(path)
    if not recs:
        print(f"{os.path.basename(path)}: empty or unreadable")
        return 1
    head = recs[0] if recs[0].get("ev") == "run" else {}
    outcome, secs, note = _runlog.summary(recs)
    print(f"{os.path.basename(path)}   {OUTCOME.get(outcome, outcome)}   {fmt(secs)}")
    if head.get("argv"):
        print(f"  $ {' '.join(head['argv'])}")
    print()
    for r in recs:
        ev = r.get("ev")
        if ev == "stage" and not notes_only:
            extra = "  ".join(f"{k}={v}" for k, v in r.items()
                              if k not in ("ev", "t", "utc", "stage", "state", "secs", "note"))
            print(f"  {fmt(r['t']):>8}  {r['stage']:<10} {r['state']:<9} "
                  f"{fmt(r['secs']):>8}  {r.get('note', '')}{('  ' + extra) if extra else ''}")
        elif ev == "note":
            print(f"  {fmt(r['t']):>8}  {r.get('stage', ''):<10} ·         "
                  f"{'':>8}  {r.get('text', '')}")
        elif ev == "end":
            print(f"\n  {fmt(r['t']):>8}  {OUTCOME.get(r.get('outcome'), '?')}"
                  f"{('  ' + r['note']) if r.get('note') else ''}")
    if outcome == "running":
        print(f"\n  (no end record: still running, or killed without one)")
    return 0 if outcome == "ok" else 1


def follow(path):
    """Print new lines as they are written; ends when the run does."""
    seen = 0
    while True:
        recs = _runlog.read(path)
        for r in recs[seen:]:
            ev = r.get("ev")
            if ev == "stage":
                print(f"  {fmt(r['t']):>8}  {r['stage']:<10} {r['state']:<9} "
                      f"{fmt(r['secs']):>8}  {r.get('note', '')}", flush=True)
            elif ev == "note":
                print(f"  {fmt(r['t']):>8}  {r.get('stage', ''):<10} ·  "
                      f"{r.get('text', '')}", flush=True)
            elif ev == "run":
                print(f"  {os.path.basename(path)}  $ {' '.join(r.get('argv') or [])}", flush=True)
            elif ev == "end":
                print(f"\n  {OUTCOME.get(r.get('outcome'), '?')} after {fmt(r['t'])}"
                      f"{('  ' + r['note']) if r.get('note') else ''}", flush=True)
                return 0 if r.get("outcome") == "ok" else 1
        seen = len(recs)
        time.sleep(2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--list", action="store_true", help="one line per run, newest first")
    ap.add_argument("--follow", action="store_true", help="tail the newest run until it ends")
    ap.add_argument("--notes", action="store_true", help="only the noted facts, no stage rows")
    ap.add_argument("--run", help="a run id (the filename stem) instead of the newest")
    ap.add_argument("-n", type=int, default=15, help="--list: how many")
    args = ap.parse_args()

    pdir = project_dir(args.project)
    if args.list:
        paths = _runlog.latest(pdir, args.n)
        if not paths:
            print(f"{args.project}: no runs recorded yet")
            return 0
        print(f"{'run':<22} {'outcome':<12} {'took':>8}  command")
        for p in paths:
            recs = _runlog.read(p)
            outcome, secs, _ = _runlog.summary(recs)
            head = recs[0] if recs and recs[0].get("ev") == "run" else {}
            cmd = " ".join(head.get("argv") or [])
            print(f"{os.path.basename(p)[:-6]:<22} {OUTCOME.get(outcome, outcome):<12} "
                  f"{fmt(secs):>8}  {cmd[:70]}")
        return 0

    if args.run:
        path = os.path.join(_runlog.runs_dir(pdir), args.run + ".jsonl")
    else:
        got = _runlog.latest(pdir, 1)
        if not got:
            print(f"{args.project}: no runs recorded yet")
            return 0
        path = got[0]
    return follow(path) if args.follow else show(path, notes_only=args.notes)


if __name__ == "__main__":
    sys.exit(main())
