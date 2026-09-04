#!/usr/bin/env python
"""Publish an ffmpeg render's progress where another process can read it.

A render here is minutes of NVENC with `capture_output=True` on the far side,
so from outside the process it is a silent wait on a growing `.part.mp4`. That
is fine for the script -- it prints when it is done -- and useless for anything
watching, which is why the Claude Code status line had nothing to show.

The fix is ffmpeg's own `-progress` writer: point it at a file and it appends a
block of `key=value` lines every half second, including `out_time` and `speed`.
That file says how far along the encode is but not how far it has to go, so
`begin()` writes a small sidecar next to it carrying the runtime the caller
already computed. `render-status.py` reads the pair.

Stdlib only, and deliberately so: the reader runs on every status-line refresh,
where a `_env` re-exec would cost a subprocess spawn each time. Nothing here
needs the venv.
"""

import os
import json
import time
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "temp", "render-progress")

# A job whose progress file has not been touched in this long is assumed dead --
# killed, crashed, or the machine went to sleep. Without it a interrupted render
# would sit at 61% in the status line forever.
STALE_S = 90.0


def _paths(job):
    return (os.path.join(DIR, job + ".json"), os.path.join(DIR, job + ".progress"))


def begin(job, total_s, out_path, kind="render"):
    """Declare a job and return the path to give ffmpeg's -progress.

    Any earlier run's files are removed first, so a stale block from a previous
    attempt cannot be read as this one's position.
    """
    os.makedirs(DIR, exist_ok=True)
    meta, prog = _paths(job)
    for p in (meta, prog):
        try:
            os.remove(p)
        except OSError:
            pass
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(
            {
                "job": job,
                "kind": kind,
                "total": float(total_s),
                "out": out_path,
                "started": time.time(),
            },
            f,
        )
    return prog


def end(job):
    """Drop the job. Safe to call twice, and safe to call on a failed render."""
    for p in _paths(job):
        try:
            os.remove(p)
        except OSError:
            pass


def _tail(path, n=4096):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - n))
        return f.read().decode("utf-8", "replace")


def _hhmmss(s):
    s = int(max(0, s))
    return (
        ("%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60))
        if s >= 3600
        else ("%d:%02d" % (s // 60, s % 60))
    )


def read():
    """The live jobs, newest first. Never raises -- a reader must not crash."""
    out = []
    try:
        metas = glob.glob(os.path.join(DIR, "*.json"))
    except OSError:
        return out
    now = time.time()
    for meta in metas:
        try:
            with open(meta, encoding="utf-8") as f:
                job = json.load(f)
            prog = meta[:-5] + ".progress"
            done = 0.0
            speed = None
            finished = False
            touched = os.path.getmtime(meta)
            if os.path.exists(prog):
                touched = max(touched, os.path.getmtime(prog))
                for line in _tail(prog).splitlines():
                    k, _, v = line.partition("=")
                    v = v.strip()
                    if k == "out_time" and ":" in v:
                        try:
                            h, m, s = v.split(":")
                            done = int(h) * 3600 + int(m) * 60 + float(s)
                        except ValueError:
                            pass
                    elif k == "speed" and v.endswith("x"):
                        try:
                            speed = float(v[:-1])
                        except ValueError:
                            pass
                    elif k == "progress":
                        finished = v == "end"
            job["done"] = done
            job["speed"] = speed
            job["finished"] = finished
            job["age"] = now - touched
            job["stale"] = (now - touched) > STALE_S
            out.append(job)
        except (OSError, ValueError):
            continue
    out.sort(key=lambda j: j.get("started", 0), reverse=True)
    return out


def describe(job, width=10):
    """One line: name, bar, percent, position, speed, eta."""
    total = float(job.get("total") or 0)
    done = float(job.get("done") or 0)
    frac = min(1.0, done / total) if total > 0 else 0.0
    filled = int(round(frac * width))
    bar = "█" * filled + "░" * (width - filled)

    bits = ["%s %s %3d%%" % (job.get("job", "?"), bar, int(frac * 100))]
    if total > 0:
        bits.append("%s/%s" % (_hhmmss(done), _hhmmss(total)))
    speed = job.get("speed")
    if speed:
        bits.append("%.2gx" % speed)
        left = total - done
        if left > 0 and speed > 0:
            bits.append("eta %s" % _hhmmss(left / speed))
    if job.get("stale"):
        bits.append("(stalled %s)" % _hhmmss(job.get("age", 0)))
    return "  ".join(bits)
