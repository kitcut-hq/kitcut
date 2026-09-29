"""Films made a scene at a time: a director, then one conversation per scene, then an editor.

A film longer than STUDIO_SCENES_OVER_S (film.py) is not written by one Claude conversation that
grows with it -- the 8-minute film llwtme reached 371k tokens and wrote its whole picture in one
57k-token reply, and past ~18 minutes that reply cannot be written at all, past ~25 the
conversation outgrows its window (docs/known-issues.md KI-034). Instead (agent.make_scenes):

    director   the brief -> the narration (recorded), film.js (the shared look: palette, helpers in
               SK.look, the camera; SK.film without a draw), scenes.json (the plan) and scene 1,
               the pilot that settles the look on real stills
    scene k    a fresh conversation that may write only scenes/<id>.js: the look, its own lines
               with their words' times, its neighbours' plans and summaries, the last frames of
               the scene before -- the same size whatever the film's length
    editor     the whole film at contact-sheet level: continuity fixes, score.json and sfx.json

Progress lives in studio.json (`scenes`: the director's, each scene's, the editor's), which Claude
cannot read, so no pass can mark itself done. A crash, a restart or a stall costs the pass in
progress; the next run (server.adopt, resume.py) starts from the first pass not done.

The plan's rules are validate._scenes; the engine side (SK.scene) is sketch/engine.js; the
design is docs/studio-scenes-plan.md.
"""

import os
import json

import validate
from film import limits

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "prompts")
DIRECTOR, EDITOR = "_director", "_editor"  # their entries in studio.json's `scenes`
LEAD = 0.3  # the engine's default: a scene starts this long before its first line is spoken
TRIES = 2  # fresh conversations one pass may take before the film fails
# how hard each pass thinks: "high", not the single conversation's xhigh (agent.EFFORT). At xhigh
# a pass writing a 40 s scene thought for over 10 minutes before its first word, twice, and the
# film failed (i4d52n, 2026-09-29); a pass has one scene to think about, not the whole film
EFFORT = "high"
PER_SHEET = 12  # stills on one sheet (tools.MAX_STILLS)


def _read(name):
    with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ the plan and its progress
def plan(film):
    """The scenes in order (scenes.json), or [] before the director has written a valid plan."""
    try:
        with open(film.path("scenes.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    if validate._scenes(d, film):
        return []
    return d["scenes"]


def progress(film):
    return film.record().get("scenes") or {}


def mark(film, key, **fields):
    """Record a pass's state in studio.json (never Claude's to write)."""
    sc = progress(film)
    sc.setdefault(key, {}).update(fields)
    film.update(scenes=sc)
    return sc[key]


def done(film, key):
    return progress(film).get(key, {}).get("state") == "done"


def tries(film, key):
    return progress(film).get(key, {}).get("tries", 0)


def timed(film):
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            return json.load(f).get("lines", [])
    except (OSError, ValueError, AttributeError):
        return []


def spans(film, scenes=None):
    """[(scene, start, end)] on the film clock, as the engine will draw them (SK.scene): the first
    scene opens the film, each other starts LEAD before its first line, each ends where the next
    starts, the last at the film's end."""
    scenes = plan(film) if scenes is None else scenes
    tl = timed(film)
    starts = []
    for i, s in enumerate(scenes):
        a = s["lines"][0]
        starts.append(0.0 if i == 0 else max(0.0, tl[a]["start"] - LEAD) if a < len(tl) else 0.0)
    return [
        (s, starts[i], starts[i + 1] if i + 1 < len(scenes) else float(film.length))
        for i, s in enumerate(scenes)
    ]


def scene_file(scene):
    return "scenes/%s.js" % scene["id"]


def spent(film):
    """What the passes already done have cost (each pass records its own)."""
    return round(sum(v.get("cost_usd") or 0 for v in progress(film).values()), 4)


# ------------------------------------------------------------------ each pass's allowance
def pass_limits(film, kind, span=None):
    """Claude's working time (s) and budget (USD) for one pass: bounded by what the pass is, not
    by the film's length -- that is the point. The film's own limit still caps the sum."""
    film_budget = limits(film.length)["budget_usd"]
    # raised 2026-09-29 after i4d52n (8 min, 12 scenes): its director needed a second try, having
    # spent its 28 minutes on narration retakes, and a scene pass got 10 minutes and used them all
    # thinking before it wrote a line
    if kind == "director":
        work, usd = 40 * 60 + 20 * min(film.length, 1800) // 60, max(4.0, 0.03 * film.length)
    elif kind == "scene":
        mins = (span[1] - span[0]) / 60 if span else 1.0
        work, usd = int(20 * 60 + 3 * 60 * mins), 1.5 + 1.5 * mins
    else:  # the editor
        n = len(plan(film))
        work, usd = min(40 * 60, 15 * 60 + 30 * n), 3.0 + 0.1 * n
    return {"claude_s": int(work), "budget_usd": round(min(usd, film_budget), 2)}


def film_claude_s(film):
    """Claude's working time for the whole film made in scenes: every pass's allowance, so the
    film's own limit (film.limits, sized for one conversation) does not starve the last scenes."""
    try:
        planned = [(a, b) for _, a, b in spans(film)]
    except (KeyError, IndexError, TypeError):
        planned = []
    # before the director has planned it: a scene about every 40 s, as i4d52n's 12 in 8 minutes
    guess = [(0, 40)] * max(1, round(film.length / 40))
    scenes = sum(pass_limits(film, "scene", s)["claude_s"] for s in planned or guess)
    return (
        pass_limits(film, "director")["claude_s"] + scenes + pass_limits(film, "editor")["claude_s"]
    )


# ------------------------------------------------------------------ what each pass is told
def _lines_text(film, scene):
    """A scene's own narration lines with their words' times (on the film clock)."""
    tl = timed(film)
    a, b = scene["lines"]
    out = []
    for L in tl[a : b + 1]:
        words = " | ".join("%s %.2f" % (w["text"], w["s"]) for w in L.get("words", []))
        out.append(
            "line %d  %.2f-%.2f s  %r\n  words: %s"
            % (L["i"], L["start"], L["end"], L["text"], words)
        )
    return "\n".join(out) or "(no narration in this scene)"


def _about(entry, summary=None):
    if not entry:
        return "(none -- this is the %s)" % ("first scene" if summary is None else "last scene")
    s = "%s -- %s. Shows: %s" % (entry["id"], entry.get("title", ""), entry.get("shows", ""))
    return s + ("\n  What it ended up as: %s" % summary if summary else "")


def director_message(film, ask_text):
    """The film's own brief (agent.ask: length, words, the prompt, attachments, the series) and
    the director's pass."""
    return (
        ask_text
        + "\n\n"
        + _read("director.md").format(
            LENGTH=film.length, MINUTES=pass_limits(film, "director")["claude_s"] // 60
        )
    )


def scene_message(film, k, sheet=None):
    """Scene k's first message: everything it needs, nothing it does not (bounded)."""
    rows = spans(film)
    scene, start, end = rows[k]
    prev = rows[k - 1][0] if k else None
    nxt = rows[k + 1][0] if k + 1 < len(rows) else None
    pr = progress(film)
    try:
        with open(film.path("film.js"), encoding="utf-8") as f:
            look = f.read()
    except OSError:
        look = "(missing)"
    existing = os.path.exists(film.path(*scene_file(scene).split("/")))
    return _read("scene.md").format(
        K=k + 1,
        N=len(rows),
        ID=scene["id"],
        FILE=scene_file(scene),
        TITLE=scene.get("title", ""),
        SHOWS=scene.get("shows", ""),
        NOTES=scene.get("notes", "") or "(none)",
        START="%.2f" % start,
        END="%.2f" % end,
        LOCAL_END="%.2f" % (end - start),
        LINES=_lines_text(film, scene),
        STYLE=pr.get(DIRECTOR, {}).get("summary") or "(see film.js)",
        BEFORE=_about(prev, pr.get(prev["id"], {}).get("summary") if prev else ""),
        AFTER=_about(nxt, "") if nxt else "(none -- this is the last scene)",
        SHEET=sheet or "(none: this is the first scene)",
        LOOK=look,
        MINUTES=pass_limits(film, "scene", (start, end))["claude_s"] // 60,
        EXISTING=(
            "A previous attempt at this scene left %s: Read it, then finish it or rewrite it."
            % scene_file(scene)
            if existing
            else "Write %s from scratch." % scene_file(scene)
        ),
    )


def editor_message(film, sheets):
    rows = spans(film)
    pr = progress(film)
    plan_text = "\n".join(
        "%s  %.1f-%.1f s  %s\n  shows: %s\n  as written: %s"
        % (
            s["id"],
            a,
            b,
            s.get("title", ""),
            s.get("shows", ""),
            pr.get(s["id"], {}).get("summary", ""),
        )
        for s, a, b in rows
    )
    return _read("editor.md").format(
        N=len(rows),
        PLAN=plan_text,
        SHEETS="\n".join("- " + p for p in sheets) or "(none)",
        MINUTES=pass_limits(film, "editor")["claude_s"] // 60,
    )


def contact_times(film):
    """For the editor: every boundary from both sides and each scene's middle."""
    ts = []
    for _, a, b in spans(film):
        ts += [a + 0.4, (a + b) / 2, max(a, b - 0.4)]
    ts = sorted({round(min(max(t, 0), film.length), 2) for t in ts})
    return [ts[i : i + PER_SHEET] for i in range(0, len(ts), PER_SHEET)]


def system_section():
    """Appended to the studio's system prompt (agent.system_prompt), after its references, so a
    film made in scenes shares the prompt cache with every other film up to this section."""
    return "\n\n" + _read("scenes.md")
