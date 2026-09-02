#!/usr/bin/env python
"""One durable record per pipeline run: what ran, how long, how it ended.

A long run here is stages of minutes each, launched in the background and read
back hours later. Until now that history lived in whatever file the shell
redirection happened to point at -- so a run that ended at 3 a.m. left the
question "did the gate pass?" answerable only by re-reading a scrollback that
had already gone. Worse, two of them: a `| tail` in one launch kept only the
tail (KI-016), and a converge loop that stopped after four rounds recorded its
verdict nowhere a later session would look.

So every run appends to `<project>/temp/pipeline/runs/<utc>.jsonl`, one JSON
object per line, flushed as it happens:

    {"ev": "run",   "run": "...", "argv": [...], "stages": [...]}   first line
    {"ev": "stage", "stage": "track", "state": "ran", "secs": 604.1, ...}
    {"ev": "note",  "stage": "gate", "text": "round 2: 9 hit(s)"}
    {"ev": "end",   "outcome": "ok"|"failed"|"stopped", "secs": ..., ...}

JSONL rather than one JSON document precisely because a run can be killed: a
half-written array is unreadable, a half-written JSONL file is every line that
made it. `run-log.py` is the reader.

Stdlib only, and no `_env` import: the reader must stay cheap enough to run
from a status line or a watch loop without a venv re-exec.
"""
import os
import io
import json
import time
import glob

SCHEMA = 1


def runs_dir(project_dir):
    return os.path.join(project_dir, "temp", "pipeline", "runs")


class RunLog:
    """Append-only. Every write is flushed, because the point is the crash."""

    def __init__(self, project_dir, argv=None, stages=None, tool="pipeline"):
        self.dir = runs_dir(project_dir)
        os.makedirs(self.dir, exist_ok=True)
        # A UTC second is not unique: the gate loop can start two runs inside
        # one, and sharing a filename would interleave their records into a
        # file that reads as one run ending twice. The pid disambiguates, and
        # a counter covers the same pid opening two logs in the same second.
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        for n in range(100):
            run = f"{stamp}-{os.getpid()}" + (f"-{n}" if n else "")
            path = os.path.join(self.dir, run + ".jsonl")
            if not os.path.exists(path):
                break
        self.run, self.path = run, path
        self.t0 = time.time()
        self.ended = False
        self._f = io.open(self.path, "a", encoding="utf-8", newline="\n")
        self.write("run", schema=SCHEMA, run=self.run, tool=tool,
                   argv=list(argv or []), stages=list(stages or []),
                   pid=os.getpid())

    def write(self, ev, **kw):
        kw["ev"] = ev
        kw["t"] = round(time.time() - self.t0, 1)
        kw["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._f.write(json.dumps(kw, ensure_ascii=False, sort_keys=False) + "\n")
        self._f.flush()
        try:
            os.fsync(self._f.fileno())
        except OSError:
            # a fsync failure must never take down a render that is working
            pass

    def stage(self, stage, state, secs, note="", **kw):
        self.write("stage", stage=stage, state=state,
                   secs=round(secs, 1), note=note, **kw)

    def note(self, stage, text, **kw):
        """A fact worth keeping that is not a stage boundary -- a gate round's
        hit count, a recall table, the piece cache's reuse. This is what makes
        the file answer "how did it end" instead of only "how long did it take".
        """
        self.write("note", stage=stage, text=text, **kw)

    def end(self, outcome, note="", **kw):
        if self.ended:
            return
        self.ended = True
        self.write("end", outcome=outcome, note=note,
                   secs=round(time.time() - self.t0, 1), **kw)
        try:
            self._f.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # An unhandled exception, a SystemExit from a failed stage, and a
        # Ctrl-C all land here; each gets its own outcome rather than a
        # missing `end` line that reads the same as "still running".
        if exc_type is None:
            self.end("ok")
        elif exc_type is KeyboardInterrupt:
            self.end("interrupted")
        elif exc_type is SystemExit:
            self.end("stopped", note=str(exc) if str(exc) else "")
        else:
            self.end("failed", note=f"{exc_type.__name__}: {exc}")
        return False


def read(path):
    """Every parseable line. A truncated last line is skipped, not fatal."""
    out = []
    try:
        with io.open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def latest(project_dir, n=1):
    """The n most recent run files, newest first.

    By mtime, not by name: the names carry a pid and a counter to stay unique
    within a second, and `X-1234.jsonl` sorts AFTER `X-1234-1.jsonl` as a
    string ('.' > '-'), which would hand back the older of two runs started
    together.
    """
    paths = glob.glob(os.path.join(runs_dir(project_dir), "*.jsonl"))
    return sorted(paths, key=lambda p: (os.path.getmtime(p), p), reverse=True)[:n]


def summary(recs):
    """(outcome, seconds, note) for a run's records; 'running' if no end line."""
    end = next((r for r in reversed(recs) if r.get("ev") == "end"), None)
    if end:
        return end.get("outcome", "?"), end.get("secs", 0.0), end.get("note", "")
    last = recs[-1] if recs else {}
    return "running", last.get("t", 0.0), ""
