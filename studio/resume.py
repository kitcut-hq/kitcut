#!/usr/bin/env python
"""Pick up a film the studio stopped half-way: one more turn of Claude's own saved session, then
the soundtrack and the video as usual, into the same film (its page and link stay the same).

    python studio/resume.py <film-id> --plan      what is there, what is missing, what it may cost
    python studio/resume.py <film-id>             pick it up (make_film resume=True)
    python studio/resume.py <film-id> --minutes N  with N minutes of Claude's working time
    python studio/resume.py <film-id> --finish    Claude's part is whole: mix and render only
    python studio/resume.py <film-id> --finish --patched [--over N]
                                                  a FINISHED film MADE IN SCENES whose files were
                                                  changed by hand in its own folder: mixed, rendered
                                                  and put online again under new names, same page.
                                                  Any other film's hand changes are its next
                                                  version, made on a copy: ops.sh take / put
                                                  (rounds.py). --over N past version 1

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
import scenes  # noqa: E402
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


# Rendering in the film's own folder is how a hand's fix erased its maker's version (KI-061):
# nothing there can tell files that started from the film as it is from files that did not.
IN_PLACE = (
    "files changed by hand become the film's next version, made on a copy and swapped in as a "
    "round is: `ops.sh take <film-id> <dir>`, change them, `ops.sh put <film-id> <dir> --summary "
    '"..."`. --patched renders in the film\'s own folder and is left for a film made in scenes, '
    "which a round cannot change yet"
)


def stale(rec, over=None):
    """Why files changed by hand may not become this film, or None. A film its maker changed from
    notes (rounds.py) is at a version the hand's copy may never have seen: on 2026-10-07 a copy
    taken at version 1 was sent back an hour after version 2 was made, and the film stayed
    "version 2" without one change its maker had asked for (KI-061). So the hand says which
    version it started from, and it must be the one the film is at."""
    r = rec.get("round") or {}
    if r.get("state") in ("queued", "running", "finishing"):
        return (
            "version %s is being made from its maker's notes (%s): wait for it, then take the "
            "film's files again" % (r.get("n"), r.get("id"))
        )
    cur = int(rec.get("version") or 1)
    if cur > 1 and over != cur:
        made = next((v for v in rec.get("versions") or [] if v.get("n") == cur), {})
        return (
            "the film is at version %d, made from its maker's notes%s. Files changed by hand must "
            "start from that version's (take them again and compare film.js), then say so: --over %d"
            % (cur, " at %s" % made["at"] if made.get("at") else "", cur)
        )
    if over is not None and over != cur:
        return "--over %d, but the film is at version %d" % (over, cur)
    return None


def refuse(film, finish, patched=False, over=None):
    """Why this film may not be picked up here, or None."""
    if patched:
        if not finish:
            return (
                "--patched goes with --finish: a patched film is mixed and rendered, not re-asked"
            )
        if film.state != "done":
            return "%s is %s; --patched is for a finished film" % (film.id, film.state)
        if film.mode != "scenes":
            return IN_PLACE
        why = stale(film.record(), over)
        if why:
            return why
    elif film.state not in STOPPED:
        return "%s is %s, not stopped (only %s films are picked up)" % (
            film.id,
            film.state,
            "/".join(STOPPED),
        )
    if finish:
        missing = [f for f in MADE if not os.path.exists(film.path(f))]
        return "Claude's part is not whole (%s missing)" % ", ".join(missing) if missing else None
    if film.mode == "scenes":  # its finished passes are kept: nothing to replay (scenes.py)
        return None
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
        "--patched",
        action="store_true",
        help="with --finish: a finished film changed by hand, rendered and put online again",
    )
    ap.add_argument(
        "--over",
        type=int,
        metavar="N",
        help="with --patched: the version the changed files started from (needed past version 1)",
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
    why = refuse(film, args.finish, args.patched, args.over)
    if why:
        sys.exit("not picking it up: " + why)
    if args.plan:
        return
    emit = logger(film)
    agent.procs.cgroup_root()  # the steps' cgroups, before Claude Code is started (server.main)
    if args.patched:
        # its files online are immutable under their names (media.blob_of): the next revision
        # gets new ones; the link-preview card is made again from the new poster
        rev = (film.record().get("media_rev") or 0) + 1
        card = film.path("outputs", "card.jpg")
        if os.path.exists(card):
            os.makedirs(film.path("temp"), exist_ok=True)
            os.replace(card, film.path("temp", "card-before-r%d.jpg" % rev))
        film.update(media_rev=rev)
        emit(
            {"type": "stage", "name": "patch", "text": "Changed by hand: mixed and rendered again"}
        )
    if args.finish:
        film.update(state="finishing", ok=None, error=None, finished=None)
    elif film.mode == "scenes":
        # a film made in scenes goes on from its first pass not done (agent.make_scenes), each
        # of those with its tries counted afresh; the ones done stay done
        for key, v in scenes.progress(film).items():
            if v.get("state") != "done":
                scenes.mark(film, key, tries=0)
        film.update(ok=None, error=None, finished=None)
        r = asyncio.run(agent.make_film(film, emit, Sched(), auth=p["auth"]))
        if r.get("ok"):
            print("  %s" % film.path("outputs", "film.mp4"))
        sys.exit(0 if r.get("ok") else 1)
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
