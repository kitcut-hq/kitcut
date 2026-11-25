"""Who is on screen, and who is speaking, all through one version of a film: for its notes page
(Edit film), which shows its maker the cast at the moment they are watching -- the ones in the
picture lit, the one speaking marked as speaking -- instead of a list that never changes.

    on     sketch/probe.js plays the film's drawing code without painting it, a few times a
           second, and says which cast member's functions drew, where and how opaque. A member
           whose drawing is on the frame (not faded out, not in the overlay) is on screen. A
           scene (kind "place") is not somebody, and is left out. Painted and collage films draw
           pictures, not cast functions: they have no `on`.
    says   each narration line as recorded (audio/vo/timeline.json) and who says it (vo.json's
           `who`; none: the narrator).

-> {"step", "on": {name: [[t0, t1], ...]}, "says": [[t0, t1, name or null], ...]}, kept on the
version's entry in the film's record (`who`), and so on the film's document the site reads.

Worked out once a version exists, in the background (ensure): the notes page shows the static
list until it is there.
"""

import os
import sys
import json
import asyncio
import contextlib

import tools as toolbox

STEP = 0.25  # seconds between the probe's frames (it falls back coarser on a heavy film)
SEEN = 0.3  # fainter than this, a drawing is fading in or out and is not counted
GAP = 0.6  # seconds: two stretches on screen this close are one
LEAST = 0.3  # seconds: a stretch shorter than this is a flicker, not somebody on screen
INTO = ("temp", "who")
MAX_RUNS = 400  # stretches kept a member, more than any film needs
JOBS = {}  # film id -> the task working its track out


def _cast(film):
    """The cast members this film draws, and which of them are scenes."""
    names = set()
    with contextlib.suppress(OSError):
        names = {n[:-3] for n in os.listdir(film.path("cast")) if n.endswith(".js")}
    places = {
        c.get("name")
        for c in ((film.record().get("library") or {}).get("cast") or [])
        if c.get("kind") == "place"
    }
    return names, places


def runs(times, step):
    """Sorted moments -> [[t0, t1]]: the stretches they make, joined across short gaps, without
    the flickers."""
    out = []
    for t in times:
        if out and t - out[-1][1] <= max(GAP, 1.5 * step):
            out[-1][1] = t
        else:
            out.append([t, t])
    return [[round(a, 2), round(b + step, 2)] for a, b in out if b + step - a >= LEAST][:MAX_RUNS]


def on_screen(report, names, places):
    """{name: [[t0, t1], ...]} from the probe's report (sketch/probe.js)."""
    keys = report.get("keys") or []
    step = float(report.get("step") or STEP)
    seen = {}
    for fr in report.get("frames") or []:
        t = float(fr.get("t") or 0)
        here = set()
        for s in fr.get("s") or []:
            try:
                k, x0, y0, x1, y1 = s[0], s[1], s[2], s[3], s[4]
                alpha, overlay = float(s[10]), int(s[11])
            except (IndexError, TypeError, ValueError):
                continue
            name = str(keys[k]).split(".")[0] if 0 <= k < len(keys) else ""
            if name not in names or name in places or overlay or alpha < SEEN:
                continue
            # what of it lies on the frame (thousandths): a sliver at the edge is not on screen
            w, h = min(x1, 1000) - max(x0, 0), min(y1, 1000) - max(y0, 0)
            if w > 8 and h > 8:
                here.add(name)
        for n in here:
            seen.setdefault(n, []).append(t)
    return {n: runs(sorted(ts), step) for n, ts in sorted(seen.items())}


def speakers(film):
    """[[t0, t1, who or None], ...]: each line as recorded, and who says it."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            said = [x for x in json.load(f).get("lines") or [] if isinstance(x, dict)]
    except (OSError, ValueError):
        return []
    try:
        with open(film.path("vo.json"), encoding="utf-8") as f:
            lines = json.load(f).get("lines") or []
    except (OSError, ValueError):
        lines = []
    out = []
    for i, x in enumerate(said):
        j = x.get("i", i)
        who = (
            lines[j].get("who")
            if isinstance(j, int) and 0 <= j < len(lines) and isinstance(lines[j], dict)
            else None
        )
        out.append(
            [
                round(float(x.get("start") or 0), 2),
                round(float(x.get("end") or 0), 2),
                str(who) if who else None,
            ]
        )
    return out


async def track(film, sched):
    """The version the film shows, worked out: {"step", "on", "says"}."""
    names, places = _cast(film)
    on, step = {}, None
    if names - places and film.look == "drawn":
        t = toolbox.Tools(film, sched, lambda ev: None)
        into = film.path(*INTO)
        with contextlib.suppress(OSError):
            for n in os.listdir(into):
                os.remove(os.path.join(into, n))
        await t._script(
            "stills",
            "sketch-render.py",
            ["--stills", "0", "--into", "/".join(INTO), "--probe", "%g" % STEP],
            pools=[("browser", 1)],
            timeout=120 + toolbox.PROBE_S,
        )
        with open(os.path.join(into, "report.json"), encoding="utf-8") as f:
            rep = json.load(f).get("probe") or {}
        on, step = on_screen(rep, names, places), rep.get("step")
    return {"step": step or STEP, "on": on, "says": speakers(film)}


def _keep(film, n, got):
    """The track on version n's entry, while the film still shows version n. -> whether kept."""
    import rounds

    rec = film.record()
    if rounds.version_of(rec) != n:
        return False
    vs = [dict(v) for v in rec.get("versions") or []]
    for v in vs:
        if v.get("n") == n:
            v["who"] = got
            break
    else:
        return False
    film.update(versions=vs)
    return vs


async def _work(film, sched):
    import agent
    import rounds

    n = rounds.version_of(film.record())
    try:
        got = await track(film, sched)
    except Exception as e:  # noqa: BLE001 -- the page keeps its plain list
        print(
            "film %s: who is on screen not worked out: %s" % (film.id, e),
            file=sys.stderr,
            flush=True,
        )
        got = {"step": STEP, "on": {}, "says": speakers(film), "error": str(e)[:200]}
    vs = await asyncio.to_thread(_keep, film, n, got)
    if vs:
        await agent.save(film.id, {"versions": vs})


def ensure(film, sched):
    """Work out the track of the version the film shows, in the background, unless its entry has
    one or it is being worked out. Never raises; returns at once."""
    import rounds

    try:
        rec = film.record()
        if rec.get("state") != "done" or film.id in JOBS:
            return
        n = rounds.version_of(rec)
        cur = next((v for v in rec.get("versions") or [] if v.get("n") == n), None)
        if cur is None or cur.get("who") is not None:
            return
        task = asyncio.get_running_loop().create_task(_work(film, sched))
        JOBS[film.id] = task
        task.add_done_callback(lambda _t: JOBS.pop(film.id, None))
    except Exception as e:  # noqa: BLE001
        print(
            "film %s: who is on screen not asked for: %s" % (film.id, e),
            file=sys.stderr,
            flush=True,
        )
