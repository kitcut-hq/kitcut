"""A second pair of eyes before a film is called finished.

The author of a film checks it against what it meant to draw, and misses what it did not mean:
three two-minute episodes shipped on 2026-10-07 with 4-8 glitches each that their author had not
seen (a cat through her carrier's wall, a body flipped through a sliver, a hand hanging in the
air ten seconds, a narrated beat nobody drew). Each was plain to a reader who had not written the
film, once the whole of it was laid out a frame a second. This is that reader, as a step:

    read(view, ask)   two Claude calls with no tools. The first reads the whole film (motion.sheets:
                      a frame a second, with the narration under each frame) with the narration's
                      times and what the drawing code says (motion.events), and answers with
                      findings and the moments it wants closer. The studio renders those moments,
                      and the machine's own, as strips a tenth of a second apart; the second call
                      reads them and gives the final findings.
    gate(...)         the studio's step after the author's last turn (agent.py): read, and if
                      something must be fixed, one bounded turn for the author to fix exactly that.

What it may report is a fixed list of kinds of glitch (prompts/review.md), never taste. It can be
wrong, so nothing here can fail a film: a reader that breaks or runs out of time leaves the film
as its author finished it.

Measured on the bench of known glitches (studio/defects.py --part review): see the README.

    python studio/review.py --film <id>          read a finished film and print what it finds
    python studio/review.py --folder <dir> --machine   only what the drawing code shows (free)
"""

import io
import os
import re
import sys
import json
import time
import shutil
import asyncio
import contextlib
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import motion  # noqa: E402

EFFORT = "high"
CALL_S = 300  # one call's time; past it the reader has failed and the film goes on
KINDS = (
    "through",
    "squash",
    "double",
    "poke",
    "idle",
    "untold",
    "wash",
    "stray",
    "text",
    "cutoff",
    "continuity",
)
# kinds that are never a must-fix, whatever the reader says: they are about how a shot is
# composed, and a fix turn spent on one moved a crown off a name plate (2 of the 2 musts the
# reader raised on a film with nothing broken, 2026-10-07). They are kept and shown.
SOFT = ("cutoff", "continuity")
MAX_FINDINGS = 14
MAX_CLOSER = 8  # close-ups the reader may ask for
MAX_STRIPS = 12  # ... and all the studio renders: its own moments first come first
SHEET_W = 1568  # what a sheet is sent at: the model sees no more of a wider one
# which of the machine's moments get a close-up, most telling first (a wash shows on the sheets;
# a pop is usually a thing meant: a character coming out from behind something)
STRIP_KINDS = ("double", "cut", "into", "sliver", "jump", "squash")


def system():
    with open(os.path.join(HERE, "prompts", "review.md"), encoding="utf-8") as f:
        return f.read()


def clock(t):
    return "%d:%04.1f" % (t // 60, t % 60)


def seconds(v):
    """A time as the reader gives it: "1:43.5" as printed on the frames (asked for, because a
    reader converting 1:43 to seconds in its head wrote 43), or a number of seconds."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).strip().split(":")
    t = 0.0
    for p in parts:
        t = t * 60 + float(p)
    return t


def jpeg(path, width=SHEET_W):
    """A sheet's bytes at the size it is sent."""
    from PIL import Image  # noqa: PLC0415

    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=82)
    return b.getvalue()


def abouts(cast_dir, limit=8):
    """Each cast member's own line about itself (SK.cast.x = {about: '...'}), for who is who."""
    out = []
    try:
        names = sorted(os.listdir(cast_dir))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".js"):
            continue
        try:
            with open(os.path.join(cast_dir, name), encoding="utf-8") as f:
                m = re.search(r"about:\s*(['\"])((?:\\.|(?!\1).)*)\1", f.read())
        except OSError:
            continue
        if m:
            out.append("%s: %s" % (name[:-3], m.group(2).replace("\\'", "'")[:240]))
    return out[:limit]


def purpose(film_js):
    """film.js's first line, who the film is for (the author writes it: // For: ...)."""
    try:
        with open(film_js, encoding="utf-8") as f:
            line = f.readline().strip()
    except OSError:
        return ""
    return line[2:].strip()[:300] if line.startswith("//") else ""


def material(folder, title="", length=None):
    """What the reader is told about a film, from its own files (a film's folder: film.js, cast/,
    sketch.json, audio/vo/timeline.json)."""
    try:
        with open(os.path.join(folder, "sketch.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        m = {}
    lines = []
    try:
        with open(os.path.join(folder, "audio", "vo", "timeline.json"), encoding="utf-8") as f:
            for L in json.load(f).get("lines") or []:
                lines.append(
                    (float(L.get("start") or 0), float(L.get("end") or 0), str(L.get("text") or ""))
                )
    except (OSError, ValueError, AttributeError):
        pass
    return {
        "title": title or str(m.get("title") or "")[:200],
        "purpose": purpose(os.path.join(folder, m.get("film") or "film.js")),
        "length": float(length or m.get("duration") or 0),
        "narration": lines,
        "cast": abouts(os.path.join(folder, "cast")),
    }


def first_text(mat, events, n_sheets):
    out = [
        "A film to check: %s" % (mat["title"] or "(untitled)"),
        "Length: %s." % clock(mat["length"]),
    ]
    if mat["purpose"]:
        out.append("Who it is for, in its author's words: %s" % mat["purpose"])
    if mat["cast"]:
        out.append(
            "\nWho is in it (the cast's own notes):\n" + "\n".join("- " + c for c in mat["cast"])
        )
    if mat["narration"]:
        out.append(
            "\nThe narration, with its times:\n"
            + "\n".join("%s-%s  %s" % (clock(a), clock(b), t) for a, b, t in mat["narration"])
        )
    else:
        out.append("\nThe film has no narration.")
    if events:
        out.append(
            "\nWhat the machine noted in the drawing code (moments to look at, not verdicts):\n"
            + "\n".join("- " + e["text"] for e in events[:16])
        )
    out.append(
        "\nThe %d image(s) above are the whole film in order, a frame a second. This is your "
        "first reading: give your findings so far and the moments you want close-ups of." % n_sheets
    )
    return "\n".join(out)


def second_text(mat, first, strips):
    out = [
        "The same film (%s, %s). Above are close-ups, each a row or two of frames a tenth of a "
        "second apart:" % (mat["title"] or "untitled", clock(mat["length"]))
    ]
    for n, (t, why) in enumerate(strips, 1):
        out.append("- image %d: around %s%s" % (n, clock(t), (" -- " + why) if why else ""))
    out.append(
        "\nYour first reading of the whole film found:\n%s"
        % (json.dumps(first, ensure_ascii=False, indent=1) if first else "[] (nothing)")
    )
    out.append(
        "\nNow give the final findings for the whole film: keep what stands, correct the times, "
        "drop what the close-ups show to be fine, add what they show to be broken. Leave "
        "look_closer empty."
    )
    return "\n".join(out)


def clean(d, length):
    """The reader's answer made safe to act on: known kinds, times inside the film, sentences."""
    found = []
    for f in (d or {}).get("findings") or []:
        if not isinstance(f, dict):
            continue
        try:
            t0, t1 = seconds(f.get("t0")), seconds(f.get("t1", f.get("t0")))
        except (TypeError, ValueError):
            continue
        t0, t1 = max(0.0, min(t0, t1)), min(float(length or 1e9), max(t0, t1))
        what = " ".join(str(f.get("what") or "").split())[:400]
        if not what or t0 > t1:
            continue
        kind = str(f.get("kind") or "").strip().lower()
        found.append(
            {
                "t0": round(t0, 1),
                "t1": round(t1, 1),
                "kind": kind if kind in KINDS else "other",
                "what": what,
                "fix": " ".join(str(f.get("fix") or "").split())[:400],
                "must": bool(f.get("must")) and kind in KINDS and kind not in SOFT,
            }
        )
    found.sort(key=lambda f: (not f["must"], f["t0"]))
    closer = []
    for t in (d or {}).get("look_closer") or []:
        try:
            t = seconds(t)
        except (TypeError, ValueError):
            continue
        if 0 <= t <= float(length or 1e9) and all(abs(t - x) > 0.6 for x in closer):
            closer.append(round(t, 1))
    return {"findings": found[:MAX_FINDINGS], "look_closer": closer[:MAX_CLOSER]}


def kept(first, final, looked):
    """The final findings, and with them what the first reading found and the second never
    looked at closer: a close-up can clear a finding, silence about it cannot."""
    out = list(final)
    for f in first:
        again = any(g["t0"] - 1 <= f["t1"] and g["t1"] + 1 >= f["t0"] for g in final)
        seen = any(f["t0"] <= t <= f["t1"] for t, _ in looked)
        if not again and not seen:
            out.append(f)
    out.sort(key=lambda f: (not f["must"], f["t0"]))
    return out[:MAX_FINDINGS]


def moments(events, closer):
    """[(t, why)] to render as strips: the machine's telling moments, then the reader's own, no
    two within 0.6 s of each other, MAX_STRIPS at most."""
    out = []

    def add(t, why):
        if len(out) < MAX_STRIPS and all(abs(t - x) > 0.6 for x, _ in out):
            out.append((round(t, 1), why))

    for kind in STRIP_KINDS:
        for e in events:
            if e["kind"] == kind:
                # a long one (a body cut for ten seconds): its start and its middle
                add(e["t0"] + min(0.3, (e["t1"] - e["t0"]) / 2), "the machine: " + e["text"])
                if e["t1"] - e["t0"] > 3:
                    add((e["t0"] + e["t1"]) / 2, "the machine: " + e["text"])
    for t in closer:
        add(t, "you asked")
    return sorted(out)


async def read(view, ask, log=None):
    """Read a film. view: {mat, sheets: async () -> [jpeg paths], events: [..], strips: async
    ([(t, why)]) -> [jpeg paths in that order]}; ask: async (text, [image bytes]) -> (dict, cost).
    -> {findings, events, closer, calls, seconds, cost_usd}. Raises what its calls raise."""
    t0, cost = time.time(), 0.0
    say = log or (lambda s: None)
    mat = view["mat"]
    sheets = await view["sheets"]()
    if not sheets:
        raise RuntimeError("no frames to read")
    ev = view.get("events")  # a list, or how to get one once the frames are there
    events = (await asyncio.to_thread(ev) if callable(ev) else ev) or []
    say("reading the whole film: %d sheet(s), %d machine note(s)" % (len(sheets), len(events)))
    d, c = await asyncio.wait_for(
        ask(first_text(mat, events, len(sheets)), [jpeg(p) for p in sheets]), CALL_S
    )
    cost += c
    first = clean(d, mat["length"])
    want = moments(events, first["look_closer"])
    final, calls = first, 1
    if want:
        strips = await view["strips"](want)
        if strips:
            say("looking closer at %d moment(s)" % len(strips))
            d, c = await asyncio.wait_for(
                ask(
                    second_text(mat, first["findings"], want[: len(strips)]),
                    [jpeg(p) for p in strips],
                ),
                CALL_S,
            )
            cost += c
            final, calls = clean(d, mat["length"]), 2
            final["findings"] = kept(first["findings"], final["findings"], want[: len(strips)])
    return {
        "findings": final["findings"],
        "first": first["findings"],
        "closer": [t for t, _ in want],
        "events": events,
        "calls": calls,
        "seconds": round(time.time() - t0, 1),
        "cost_usd": round(cost, 4),
    }


def words(findings, must_only=False):
    """Findings as lines a person (or the author) reads."""
    out = []
    for f in findings:
        if must_only and not f["must"]:
            continue
        out.append(
            "- %s to %s (%s%s): %s%s"
            % (
                clock(f["t0"]),
                clock(f["t1"]),
                f["kind"],
                "" if f["must"] else ", could be better",
                f["what"],
                (" Fix: " + f["fix"]) if f["fix"] else "",
            )
        )
    return "\n".join(out)


# ------------------------------------------------------------------ the studio's step
FIX_S = 360  # the author's working time to fix what must be fixed
FIX_BUDGET_USD = 2.0
MAX_MUST = 5  # more than a turn can fix: the first five, in the film's order
FIX_TOOLS = (
    "check",
    "stills",
    "strip",
)  # look and check; no voice (the words' times must not move)
PAD_S = 2.0  # a frame this near a finding may change when it is fixed
CHANGED = 0.02  # of a frame's pixels: more than this differs, and the frame has changed
GUARD_PAIRS = 8  # frames that changed away from every finding, shown before and after
FIX = (
    "The studio had the finished film read by someone who did not make it: the whole of it a "
    "frame a second, and the moments below a tenth of a second apart. They found %d thing(s) a "
    "viewer would take for a mistake:\n\n%s\n\n"
    "Fix exactly these, in film.js (and in a cast file when the fault is there), and nothing "
    "else: no new ideas and no restyling. The narration is recorded: its words and their times "
    "must not move, so leave vo.json alone and keep every cue on its word. For each: make the "
    "change, `check`, `strip` the moment and look at it. Prefer the fix that keeps the scene. You "
    "have about six minutes; when the last one is looked at, stop with one sentence saying what "
    "you changed."
)
GUARD = (
    "You asked for fixes to a film. Each row above is one moment of it that changed although it "
    "was not one of the moments to be fixed: on the left as it was, on the right as it is now. A "
    "fix often changes other frames harmlessly (a box made bigger is bigger everywhere). Did any "
    "of these changes BREAK something: a character gone, cut, squashed or in the wrong place, a "
    "scene emptied, words unreadable?\n\n"
    'Answer with one JSON object and nothing else: {"broken": false, "why": ""} -- or true, and '
    "one sentence saying what broke and when."
)
SAVED = ("film.js", "sfx.json", "score.json", "vo.json")
SAVED_DIRS = ("cast", "scenes")


def enabled():
    """Not when Claude is stood in for (the studio's tests make films with a stub: their reading
    would be a real call)."""
    import agent  # noqa: PLC0415

    rc = agent.run_claude
    return getattr(rc, "__module__", None) == "agent" and rc.__name__ == "run_claude"


def view_of(film, tools):
    """A film being made, as read() takes one: laid out by the film's own tools."""
    import ytdraft  # noqa: PLC0415

    box = {"events": []}

    async def sheets():
        _, _, names, box["events"] = await tools.film_sheets()
        return [film.path(*n.split("/")) for n in names]

    async def strips(want):
        return await tools.strips([t for t, _ in want], name="look")

    rec = film.record()
    mat = material(film.dir, title=str(rec.get("title") or ""), length=film.length)
    if not mat["narration"]:
        mat["narration"] = [
            (a or 0.0, b or 0.0, t) for a, b, t in ytdraft._narration(film) if a is not None
        ]
    return {"mat": mat, "sheets": sheets, "events": lambda: box["events"], "strips": strips}


def snapshot(film):
    """What a fix may change, kept beside the film until the fix is judged."""
    d = film.path("temp", "before-review")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for name in SAVED:
        if os.path.isfile(film.path(name)):
            shutil.copy2(film.path(name), os.path.join(d, name))
    for sub in SAVED_DIRS:
        if os.path.isdir(film.path(sub)):
            shutil.copytree(film.path(sub), os.path.join(d, sub))
    return d


def restore(film, d, only=None):
    """Put the film back as it was before the fix (or only the files named)."""
    for name in SAVED:
        if (only is None or name in only) and os.path.isfile(os.path.join(d, name)):
            shutil.copy2(os.path.join(d, name), film.path(name))
    if only is None:
        for sub in SAVED_DIRS:
            if os.path.isdir(os.path.join(d, sub)):
                shutil.rmtree(film.path(sub), ignore_errors=True)
                shutil.copytree(os.path.join(d, sub), film.path(sub))


def same_file(a, b):
    try:
        with open(a, "rb") as f, open(b, "rb") as g:
            return f.read() == g.read()
    except OSError:
        return False


def changed_frames(before_dir, after_dir, windows):
    """[(t, before png, after png)] of the whole seconds whose frame changed and that lie more than
    PAD_S from every window: what a fix touched besides what it was asked to. A frame is a pure
    function of the film's code and its time, so an untouched one comes back byte for byte."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    was = dict(motion._frames(before_dir))
    out = []
    for t, p in motion._frames(after_dir):
        q = was.get(t)
        if q is None or abs(t - round(t)) > 1e-6:
            continue
        if any(a - PAD_S <= t <= b + PAD_S for a, b in windows) or same_file(p, q):
            continue
        with Image.open(p) as x, Image.open(q) as y:
            xs = np.asarray(x.convert("L").resize((192, 108)), dtype=np.int16)
            ys = np.asarray(y.convert("L").resize((192, 108)), dtype=np.int16)
        if float(np.mean(np.abs(xs - ys) > motion.CHANGE)) > CHANGED:
            out.append((t, q, p))
    return out


def pairs_sheet(pairs, path):
    """Before and after, side by side, one moment a row."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    w = 760
    with Image.open(pairs[0][1]) as im:
        h = round(w * im.height / im.width)
    sheet = Image.new("RGB", (2 * w + 12, len(pairs) * (h + 40)), "white")
    draw, font = ImageDraw.Draw(sheet), motion._font(24)
    for r, (t, a, b) in enumerate(pairs):
        y = r * (h + 40)
        draw.text(
            (4, y + 4),
            "%s -- as it was (left), as it is now (right)" % clock(t),
            fill="black",
            font=font,
        )
        for c, p in enumerate((a, b)):
            with Image.open(p) as im:
                sheet.paste(im.convert("RGB").resize((w, h)), (c * (w + 12), y + 36))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path, quality=82)
    return path


async def fix(film, emit, meter, tools, auth, musts, ask):
    """One bounded turn for the author to fix what must be fixed, then the fix judged: the film
    must still be whole, and what it changed away from the findings must not have broken anything.
    -> ("fixed" | "kept as it was: <why>", what the author said)."""
    import agent  # noqa: PLC0415

    sid = film.record().get("claude_session")
    if not sid:
        return "kept as it was: no session to fix it in", ""
    before = snapshot(film)
    was_frames = film.path("temp", "motion-before")
    shutil.rmtree(was_frames, ignore_errors=True)
    shutil.copytree(film.path("temp", "motion"), was_frames)
    said, tools.only = "", FIX_TOOLS
    try:
        with contextlib.suppress(TimeoutError):
            res = await agent._within(
                agent.run_claude(
                    film,
                    emit,
                    meter,
                    tools,
                    auth,
                    prompt=FIX % (len(musts), words(musts)),
                    resume=sid,
                    budget_usd=FIX_BUDGET_USD,
                    effort="high",
                ),
                agent.Clock(),
                {"claude_s": FIX_S, "wall_s": FIX_S + 180},
            )
            said = (getattr(res, "result", "") or "")[:600]
    finally:
        tools.only = None
    if not same_file(film.path("vo.json"), os.path.join(before, "vo.json")):
        restore(film, before, only=("vo.json",))  # the recording is what it is: the words stay
    if not await agent.written(film, tools):
        restore(film, before)
        return "kept as it was: the fix left the film unable to run", said
    if all(
        same_file(film.path(n), os.path.join(before, n)) for n in ("film.js",)
    ) and not _dirs_differ(film, before):
        return "kept as it was: the author changed nothing", said
    # what else moved
    ts = [float(t) for t in range(int(film.length))]
    shutil.rmtree(film.path("temp", "motion-after"), ignore_errors=True)
    async with tools.lock:
        tools.gate()
        await tools._script(
            "stills",
            "sketch-render.py",
            ["--stills", ",".join("%g" % t for t in ts), "--into", "temp/motion-after"],
            pools=[("browser", 1)],
            timeout=120 + 2 * len(ts),
        )
    moved = await asyncio.to_thread(
        changed_frames,
        was_frames,
        film.path("temp", "motion-after"),
        [(f["t0"], f["t1"]) for f in musts],
    )
    if moved:
        pick = moved[:: max(1, len(moved) // GUARD_PAIRS)][:GUARD_PAIRS]
        sheet = await asyncio.to_thread(
            pairs_sheet, pick, film.path("outputs", "review", "fix-check.jpg")
        )
        d, _ = await asyncio.wait_for(ask(GUARD, [jpeg(sheet)]), CALL_S)
        if isinstance(d, dict) and d.get("broken"):
            restore(film, before)
            await agent.written(film, tools)
            return "kept as it was: the fix broke something else (%s)" % str(d.get("why") or "")[
                :200
            ], said
    return "fixed", said


def _dirs_differ(film, before):
    for sub in SAVED_DIRS:
        a, b = film.path(sub), os.path.join(before, sub)
        names = set(os.listdir(a) if os.path.isdir(a) else []) | set(
            os.listdir(b) if os.path.isdir(b) else []
        )
        if any(not same_file(os.path.join(a, n), os.path.join(b, n)) for n in names):
            return True
    return False


EDITOR_NOTE = (
    "\n\nBefore this pass the studio had the whole film read by someone who did not make it, a "
    "frame a second (outputs/review/film-01.jpg ... -- Read them: they are the whole film in "
    "order, each frame with its time and the words being said). They found:\n\n%s\n\nFix what a "
    'viewer would take for a mistake (the lines not marked "could be better") in the scene '
    "files, `check`, and `strip` each moment you changed to see it; prefer the fix that keeps "
    "the scene."
)


async def for_editor(film, emit, tools, auth):
    """A film made in scenes has no one session to fix it in once it is whole, so it is read
    before its last pass and the editor is told what was found: the text to add to the
    editor's opening message ("" when nothing was found, or the reading failed). Read once: a
    second try of the editor is told the same. Never raises."""
    import agent  # noqa: PLC0415
    import ytdraft  # noqa: PLC0415

    t0 = time.time()
    try:
        rec = film.record()
        had = rec.get("review")
        if had:
            found = had.get("findings") or []
            return EDITOR_NOTE % words(found) if found else ""
        if not enabled() or rec.get("template"):
            return ""

        async def ask(text, images):
            return await ytdraft.ask_json(
                text, images, auth, film, ytdraft.MODEL, EFFORT, system(), "review"
            )

        emit(
            {"type": "stage", "name": "claude", "text": "Checking the whole film, a frame a second"}
        )
        r = await read(view_of(film, tools), ask, log=lambda s: emit({"type": "log", "text": s}))
        out = {
            "findings": r["findings"],
            "events": len(r["events"]),
            "calls": r["calls"],
            "read_s": r["seconds"],
            "cost_usd": r["cost_usd"],
            "outcome": "given to the editor" if r["findings"] else "clean",
            "seconds": round(time.time() - t0, 1),
        }
        film.update(review=out)
        await agent.save(film.id, {"review": out})
        return EDITOR_NOTE % words(r["findings"]) if r["findings"] else ""
    except (Exception, SystemExit) as e:  # noqa: BLE001 -- never fails a film
        print(
            "REVIEW %s failed before the editor: %s" % (film.id, e or type(e).__name__), flush=True
        )
        with contextlib.suppress(Exception):
            note = {"outcome": "not read: %s" % (str(e) or type(e).__name__)[:200]}
            film.update(review=note)
            await agent.save(film.id, {"review": note})
        return ""


async def gate(film, emit, meter, tools, auth, overtime=False):
    """The studio's step after the author's last turn: read the film, and if something must be
    fixed, one bounded turn to fix exactly that. Returns the record kept on the film (also under
    `review` in studio.json), or None when it did not run. Never raises: a reader that breaks
    leaves the film as its author finished it."""
    import agent  # noqa: PLC0415
    import ytdraft  # noqa: PLC0415

    t0 = time.time()
    try:
        rec = film.record()
        if not enabled() or overtime or rec.get("review") or tools.span or rec.get("template"):
            # stood in for; out of time already; read before (a film carried on); a scene's own
            # pass; a template's film (a remake of one a person approved, whose flips and wipes
            # are meant: not measured yet, so it keeps the path it had)
            return None

        async def ask(text, images):
            return await ytdraft.ask_json(
                text, images, auth, film, ytdraft.MODEL, EFFORT, system(), "review"
            )

        emit(
            {
                "type": "stage",
                "name": "claude",  # a name the pages know: its text says what is happening
                "text": "Checking the finished film, a frame a second",
            }
        )
        r = await read(view_of(film, tools), ask, log=lambda s: emit({"type": "log", "text": s}))
        musts = sorted([f for f in r["findings"] if f["must"]], key=lambda f: f["t0"])[:MAX_MUST]
        out = {
            "findings": r["findings"],
            "events": len(r["events"]),
            "calls": r["calls"],
            "read_s": r["seconds"],
            "cost_usd": r["cost_usd"],
            "outcome": "clean" if not musts else "to fix",
        }
        film.update(review=out)  # before the fix: a restart must not read the film a second time
        await agent.save(film.id, {"review": out})
        for f in r["findings"]:
            emit({"type": "log", "text": "the check: " + words([f]).lstrip("- ")})
        if musts and film.mode != "scenes":  # a film made in scenes has no one session to fix it in
            emit(
                {
                    "type": "stage",
                    "name": "claude",
                    "text": "Claude is fixing %d thing(s) the check found" % len(musts),
                }
            )
            m0 = meter.usd()
            out["outcome"], out["author_said"] = await fix(
                film, emit, meter, tools, auth, musts, ask
            )
            out["fix_cost_usd"] = round(max(0.0, meter.usd() - m0), 4)
        elif musts:
            out["outcome"] = "kept as it was: made in scenes"
        out["seconds"] = round(time.time() - t0, 1)
        emit({"type": "log", "text": "the check: %s" % out["outcome"]})
        film.update(review=out)
        await agent.save(film.id, {"review": out})
        return out
    # SystemExit too: claude_env() exits when the key is missing
    except (Exception, SystemExit) as e:  # noqa: BLE001 -- never fails a film
        print("REVIEW %s failed: %s" % (film.id, e or type(e).__name__), flush=True)
        with contextlib.suppress(Exception):
            tools.only = None
            emit({"type": "log", "text": "the check did not finish; the film goes on as it is"})
            note = {
                "outcome": "not read: %s" % (str(e) or type(e).__name__)[:200],
                "seconds": round(time.time() - t0, 1),
            }
            film.update(review=note)
            await agent.save(film.id, {"review": note})
        return None


# ------------------------------------------------------------------ a film's folder, read by hand
# python studio/review.py --film <id>   (ops.sh review <id> on the VM): the same reading, of a film
# that is already finished, printed. It changes nothing of the film: no record, no fix.
KIT = os.path.dirname(HERE)
PROBE_STEP = 0.1


def render_stills(d, times, into, extra=()):
    """sketch-render.py --stills over a film's folder (its own sketch.json); raises with the
    script's last lines."""
    argv = [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
    argv += ["--manifest", os.path.join(d, "sketch.json")]
    argv += ["--stills", ",".join("%g" % t for t in times), "--into", into, *extra]
    r = subprocess.run(
        argv, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-1500:])
    return r.stdout


def folder_length(d):
    with open(os.path.join(d, "sketch.json"), encoding="utf-8") as f:
        return float(json.load(f)["duration"])


def folder_frames(d, force=False):
    """The film's frames at motion's own rate and the probe's report, in <film>/temp/motion (kept
    while film.js is older). -> (the folder, whether it rendered them now)."""
    out = os.path.join(d, "temp", "motion")
    src = max(os.path.getmtime(os.path.join(d, f)) for f in ("film.js", "sketch.json"))
    have = os.listdir(out) if os.path.isdir(out) else []
    fresh = have and min(os.path.getmtime(os.path.join(out, f)) for f in have) > src
    if fresh and not force and "report.json" in have:
        return out, False
    for f in have:
        os.remove(os.path.join(out, f))
    render_stills(
        d,
        motion.times(folder_length(d)),
        os.path.join("temp", "motion"),
        ["--probe", "%g" % PROBE_STEP],
    )
    return out, True


def folder_events(d, force=False):
    """What the drawing code shows (motion.events over the probe's report), kept to what the
    frames show too (motion.shown)."""
    fr, _ = folder_frames(d, force)
    try:
        with open(os.path.join(fr, "report.json"), encoding="utf-8") as f:
            rep = json.load(f).get("probe") or {}
    except (OSError, ValueError):
        rep = {}
    return motion.shown(motion.events(rep), fr)


def folder_view(d, title=""):
    """A film's folder as read() takes one: its facts, and how to lay it out and look closer."""
    import tools  # noqa: PLC0415

    said = motion.spoken(os.path.join(d, "audio", "vo", "timeline.json"))
    out_dir = os.path.join(d, "outputs", "review")

    async def sheets():
        fr, _ = await asyncio.to_thread(folder_frames, d)
        return await asyncio.to_thread(motion.sheets, fr, out_dir, said)

    async def strips(want):
        n = folder_length(d)
        groups = [tools.strip_times(t, 0, n - 0.02) for t, _ in want]
        into = os.path.join(d, "temp", "strip")
        shutil.rmtree(into, ignore_errors=True)
        await asyncio.to_thread(
            render_stills, d, sorted({x for g in groups for x in g}), os.path.join("temp", "strip")
        )
        return await asyncio.to_thread(
            tools.strips_of, into, out_dir, [t for t, _ in want], groups, said, "look"
        )

    return {
        "mat": material(d, title=title),
        "sheets": sheets,
        "events": lambda: folder_events(d),
        "strips": strips,
    }


def main():
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(
        description="Read a finished film for glitches, as the studio does before a film is called "
        "done: the whole of it a frame a second, then the moments worth a closer look. Prints what "
        "it finds; changes nothing of the film."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--film", help="a film's id (its folder under the studio's projects)")
    g.add_argument(
        "--folder", help="a film's folder anywhere (sketch.json, film.js, cast/, audio/)"
    )
    ap.add_argument("--auth", choices=("login", "api"), help="default: what the film was made on")
    ap.add_argument(
        "--machine",
        action="store_true",
        help="only what the drawing code shows: no Claude call, free",
    )
    ap.add_argument("--json", action="store_true", help="print the whole result as JSON")
    a = ap.parse_args()

    import agent  # noqa: PLC0415, F401 -- imports _env first
    import ytdraft  # noqa: PLC0415

    film, title, auth = None, "", a.auth or "login"
    if a.film:
        import share  # noqa: PLC0415
        from film import Film  # noqa: PLC0415

        film = Film.open(a.film)
        if film is None:
            sys.exit("no such film: %s" % a.film)
        d, title = film.dir, str(film.record().get("title") or "")
        auth = a.auth or share.auth_of(film)
    else:
        d = os.path.abspath(a.folder)
    if a.machine:
        ev = folder_events(d)
        print("%d moment(s) the drawing code points at:" % len(ev))
        for e in ev:
            print("- %s" % e["text"])
        return

    async def ask(text, images):
        return await ytdraft.ask_json(
            text, images, auth, film, ytdraft.MODEL, EFFORT, system(), "review"
        )

    r = asyncio.run(read(folder_view(d, title), ask, log=lambda s: print("  " + s, flush=True)))
    with open(os.path.join(d, "temp", "review-last.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1, ensure_ascii=False)
    if a.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return
    musts = [f for f in r["findings"] if f["must"]]
    print(
        "\n%d thing(s) a viewer would take for a mistake, %d that could be better "
        "(%d call(s), %.0f s, $%.2f on %s):"
        % (
            len(musts),
            len(r["findings"]) - len(musts),
            r["calls"],
            r["seconds"],
            r["cost_usd"],
            auth,
        )
    )
    print(words(r["findings"]) or "- nothing: a clean film")
    print("\nIts sheets and close-ups: %s" % os.path.join(d, "outputs", "review"))


if __name__ == "__main__":
    main()
