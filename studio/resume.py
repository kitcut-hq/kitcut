#!/usr/bin/env python
"""Pick up a film the studio stopped half-way: one more turn of Claude's own saved session, then
the soundtrack and the video as usual, into the same film (its page and link stay the same).

    python studio/resume.py <film-id> --plan      what is there, what is missing, what it may cost
    python studio/resume.py <film-id>             pick it up (make_film resume=True)
    python studio/resume.py <film-id> --minutes N  with N minutes of Claude's working time
    python studio/resume.py <film-id> --finish    Claude's part is whole: mix and render only

For a film the studio stopped under it -- a restart while Claude was still working records it
cancelled (before 2026-09-29) or interrupted -- not for one its person stopped. The Claude session
is the film's own (STUDIO_HOME/claude/<id>/ for a film on the key), so Claude remembers what it
drew and why; its working time is what the film's limit has left (--minutes to set it). What the
stopped attempt spent is carried into the record (studio.json and kitcut.studio_runs), not
replaced, and the events go on in the film's events.jsonl, so its page shows the rest of the run.

Runs beside the server, not inside it: the film is not in the server's list, so its page reads
it from disk until it is done. Run it where the film lives, with that studio's STUDIO_HOME -- on
the Azure VM: `bash studio/deploy/ops.sh resume <film-id> [--plan]`.
"""

import os
import sys
import json
import time
import asyncio
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent  # noqa: E402 -- imports _env first
from film import MADE, Film, limits  # noqa: E402
from sched import Sched  # noqa: E402

# a film in one of these the server is not making, and nobody chose to stop
STOPPED = ("cancelled", "interrupted", "error")


def session_file(film):
    """Claude's saved session for the film (the transcript Claude Code resumes), or None."""
    sid = film.record().get("claude_session")
    if not sid:
        return None
    for root in (film.claude_dir, os.path.expanduser("~/.claude")):
        for d, _, names in os.walk(os.path.join(root, "projects")):
            if sid + ".jsonl" in names:
                return os.path.join(d, sid + ".jsonl")
    return None


def plan(film, minutes=None):
    """What resuming would do, from the files alone: nothing is spent."""
    rec = film.record()
    lim = limits(film.length)
    used = (rec.get("stages") or {}).get("claude") or rec.get("seconds") or 0
    work = minutes * 60 if minutes else max(agent.RESUME_MIN_S, lim["claude_s"] - used)
    missing = [f for f in MADE if not os.path.exists(film.path(f))]
    if not os.path.exists(film.path("audio", "vo", "timeline.json")):
        missing.append("audio/vo/timeline.json (the narration)")
    spent = rec.get("claude_cost_usd") or 0
    return {
        "film": film.id,
        "state": film.state,
        "error": rec.get("error"),
        "length": film.length,
        "auth": rec.get("auth", "api"),
        "session": rec.get("claude_session"),
        "session_file": session_file(film),
        "missing": missing,
        "earlier_s": used,
        "working_minutes": round(work / 60, 1),
        "spent_usd": spent,
        "budget_left_usd": round(max(1.0, lim["budget_usd"] - spent), 2),
    }


def refuse(film, finish):
    """Why this film may not be picked up here, or None."""
    if film.state not in STOPPED:
        return "%s is %s, not stopped (only %s films are picked up)" % (
            film.id,
            film.state,
            "/".join(STOPPED),
        )
    if finish:
        missing = [f for f in MADE if not os.path.exists(film.path(f))]
        return "Claude's part is not whole (%s missing)" % ", ".join(missing) if missing else None
    if not session_file(film):
        return "no saved Claude session for %s (%s)" % (
            film.id,
            film.record().get("claude_session") or "none recorded",
        )
    return None


def logger(film):
    """emit(): the film's events.jsonl, its times going on from where the log stopped (as the
    server's own emit does for a film picked up after a restart), and the console."""
    log = film.path("events.jsonl")
    last = 0.0
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        last = rows[-1]["t"] if rows else 0.0
    t0 = time.time() - last

    def emit(ev):
        ev = {**ev, "t": round(time.time() - t0, 1)}
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        agent._print(ev)

    return emit


def main():
    agent._env.utf8_stdio()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("film", help="the film's id (studio-YYYYMMDD-HHMMSS-xxxxxx)")
    ap.add_argument("--plan", action="store_true", help="say what it would do; spend nothing")
    ap.add_argument(
        "--finish", action="store_true", help="no Claude: its part is whole, mix and render only"
    )
    ap.add_argument(
        "--minutes",
        type=int,
        help="Claude's working time (default: what the film's limit has left, at least 5)",
    )
    args = ap.parse_args()
    film = Film.open(args.film)
    if film is None:
        sys.exit("no film %s in %s" % (args.film, agent.HOME))
    p = plan(film, args.minutes)
    print(json.dumps(p, indent=2))
    why = refuse(film, args.finish)
    if why:
        sys.exit("not picking it up: " + why)
    if args.plan:
        return
    emit = logger(film)
    agent.procs.cgroup_root()  # the steps' cgroups, before Claude Code is started (server.main)
    if args.finish:
        film.update(state="finishing", ok=None, error=None, finished=None)
    r = asyncio.run(
        agent.make_film(
            film,
            emit,
            Sched(),
            auth=p["auth"],
            finish_only=args.finish,
            resume=not args.finish,
            resume_minutes=args.minutes,
        )
    )
    if r.get("ok"):
        print("  %s" % film.path("outputs", "film.mp4"))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
