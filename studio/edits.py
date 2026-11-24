"""A change to one scene or character of a project, asked for in words (and marks on its
picture), outside any episode: Claude makes one to four variations, the person looks at them
beside the one in use and chooses.

    start(...)        an edit's job: Claude, in a working copy of one of the project's episodes
    listing / get     a member's edits as its page shows them
    use(...)          a variation becomes the member's next version (assets.put_drawn /
                      library._put_painted): every new episode gets it
    stop / dismiss    end one being made / throw its variations away
    sweep()           at startup: edits a server that is gone left half-way are ended

Why a copy of an episode: a drawn member is code that needs the series' engine, fonts, modules
and the rest of the cast to draw; a painted one needs the series' painter and style (paint.json).
The newest finished episode has all of it. The copy is rounds.copy_of's (the same pins), with the
library's current cast laid over it, and it is thrown away when the edit ends.

What Claude may write there (Work.writable), and nothing else:

    drawn     variations/a.js ... d.js   each the whole member, registering SK.cast.<name>, in
                                         place of cast/<name>.js; `look` draws each alone
                                         (variations/a.png) with the rest of the cast loaded
    painted   paint.json                 images v_a ... v_d, each painted from the member's
                                         picture ("ref": "cast_<name>"); `paint` paints them

and it answers with `variation(letter, what)` for each one it stands behind, then `summary`.
A variation Claude did not name, or that does not draw, is not kept.

A new scene (start(new=...): the Scenes tab's "New scene") is an edit with nothing to start from:
the person describes the place, Claude makes it in one to four variations (drawn or painted, as
the project's episodes are), and the one chosen is its version 1. Until then the scene is a
draft (_draft): its edits are kept under its name as any member's, and the library lists it in
`drafts`, not in its cast.

An edit's record and what it made live with the member, in the project's library:

    cast\\<name>\\edits\\<k>\\edit.json     the asking, its state, the variations and what each changed
    cast\\<name>\\edits\\<k>\\a.js|a.jpg    a variation, as it would be written
    cast\\<name>\\edits\\<k>\\a.png         its picture (PICTURE px), a.thumb.png small
    cast\\<name>\\edits\\<k>\\marks.png     the picture the person marked, as Claude saw it

and one document in studio_runs (kind "edit", _id "<project>.<name>.e<k>"), with the states a
round's has: the site settles the edit's credits on it (done: `delivered` variations; failed,
cancelled, interrupted, unchanged: nothing).
"""

import os
import re
import json
import time
import shutil
import asyncio
import contextlib
from datetime import datetime, timedelta

import film as films
import live
import peers
import store
import assets
import library
import tools as toolbox

ACTIVE = ("queued", "running", "finishing")
LETTERS = "abcd"
MAX_N = len(LETTERS)
ASK_MAX = 1000  # characters of what the person asks for
MARKS = 8  # marks on the picture
MARK_MAX = 300  # characters of a mark's own note
PER_DAY = int(os.environ.get("STUDIO_EDITS_PER_DAY") or 20)  # edits a project may have in a day
KEEP_DAYS = 30  # an edit nobody chose from is thrown away after this
FABLE_EFFORT = "medium"  # the only effort an edit takes with Fable (owner, 2026-11-24)
EFFORT = "high"  # an edit's own, when none is asked for
RING = (217, 115, 63)
VARIATION = re.compile(r"^[a-d]\.js$")

JOBS = {}  # edit id -> the edit being made here


class EditError(Exception):
    """Refused, with a status, words for the person, and a reason for the site."""

    def __init__(self, status, text, reason=None):
        super().__init__(text)
        self.status, self.text, self.reason = status, text, reason


def _now():
    return datetime.now().isoformat(timespec="seconds")


def eid_of(project, name, k):
    return "%s.%s.e%d" % (project, name, k)


# ------------------------------------------------------------------ where an edit is kept
def _edits(lib, name):
    return os.path.join(library.dir_of(lib), "cast", name, "edits")


def _dir(lib, name, k):
    return os.path.join(_edits(lib, name), str(int(k)))


def _read(lib, name, k):
    try:
        with open(os.path.join(_dir(lib, name, k), "edit.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None


def _write(lib, name, e):
    d = _dir(lib, name, e["k"])
    os.makedirs(d, exist_ok=True)
    films._write_json(os.path.join(d, "edit.json"), e)
    return e


def _all(lib, name):
    """A member's edits, newest first."""
    try:
        ks = sorted((int(k) for k in os.listdir(_edits(lib, name)) if k.isdigit()), reverse=True)
    except OSError:
        return []
    return [e for e in (_read(lib, name, k) for k in ks) if e]


def _member(client, project, name):
    lib = library.owner(client, project)
    if not lib or not project:
        raise EditError(404, "No such project.")
    if not library.NAME.match(name or ""):
        raise EditError(404, "No such scene or character.")
    idx = library.load(lib)
    m = idx["cast"].get(name)
    if not m or m.get("deleted"):
        raise EditError(404, "No such scene or character.")
    return lib, idx, m


def _draft_of(e):
    """The scene a new-scene edit is making, as a member is listed (version 0: none chosen)."""
    return {
        "name": e["name"],
        "kind": "place",
        "about": (e.get("new") or {}).get("about") or "",
        "painted": bool(e.get("painted")),
        "version": 0,
        "hash": None,
        "new": True,
    }


def _draft(lib, idx, name):
    """A scene being made from words and not chosen yet: its newest new-scene edit's, or None."""
    have = idx["cast"].get(name)
    if have and not have.get("deleted"):
        return None
    e = next((e for e in _all(lib, name) if e.get("new")), None)
    return _draft_of(e) if e else None


def _target(client, project, name):
    """(lib, idx, member) of a member's edit routes: one of the project's members, or a scene
    being made from words."""
    lib = library.owner(client, project)
    if not lib or not project:
        raise EditError(404, "No such project.")
    if not library.NAME.match(name or ""):
        raise EditError(404, "No such scene or character.")
    idx = library.load(lib)
    m = idx["cast"].get(name)
    if m and not m.get("deleted"):
        return lib, idx, m
    d = _draft(lib, idx, name)
    if not d:
        raise EditError(404, "No such scene or character.")
    return lib, idx, d


def drafts(lib, idx=None):
    """The scenes being made from words, or made and waiting to be chosen from, as the library
    lists them (library_list's `drafts`): [{name, kind, about, painted, draft: {k, state, now}}]."""
    idx = idx or library.load(lib)
    try:
        names = os.listdir(os.path.join(library.dir_of(lib), "cast"))
    except OSError:
        return []
    out = []
    for n in sorted(names):
        d = _draft(lib, idx, n) if library.NAME.match(n) else None
        if not d:
            continue
        e = next(e for e in _all(lib, n) if e.get("new"))
        if e["state"] not in ACTIVE and not (e["state"] == "done" and e.get("variations")):
            continue
        out.append(
            {k: d[k] for k in ("name", "kind", "about", "painted")}
            | {"draft": {"k": e["k"], "state": e["state"], "now": e.get("now"), "n": e.get("n")}}
        )
    return out


def _painted_project(idx):
    """Whether the project's episodes are painted (painted or collage): its new scenes are too."""
    ep = assets.episode_of(idx)
    return bool(ep) and getattr(ep, "look", None) in ("painted", "collage")


def public(e):
    """An edit as the member's page shows it."""
    return {
        "id": e["id"],
        "k": e["k"],
        "state": e["state"],
        "now": e.get("now"),
        "asked": e.get("asked"),
        "finished": e.get("finished"),
        "ask": e.get("ask"),
        "marks": e.get("marks") or [],
        "n": e.get("n"),
        "model": e.get("model"),
        "effort": e.get("effort"),
        "base": {k: (e.get("base") or {}).get(k) for k in ("version", "edit", "letter")},
        "variations": [
            {"letter": v["letter"], "what": v.get("what"), "used": v.get("used")}
            for v in e.get("variations") or []
        ],
        "summary": e.get("summary"),
        "error": e.get("error"),
        "painted": bool(e.get("painted")),
        **({"new": True} if e.get("new") else {}),
    }


def listing(client, project, name):
    """A member's edits, newest first: the one being made, and the ones with variations to
    choose from or chosen from. Old ones nobody chose from go (KEEP_DAYS)."""
    lib, _, _ = _target(client, project, name)
    out = []
    old = (datetime.now() - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    for e in _all(lib, name):
        if e["state"] not in ACTIVE and (e.get("finished") or e.get("asked") or "") < old:
            shutil.rmtree(_dir(lib, name, e["k"]), ignore_errors=True)
            continue
        out.append(public(e))
    return out


def get(client, project, name, k):
    lib, _, _ = _target(client, project, name)
    e = _read(lib, name, k)
    if not e:
        raise EditError(404, "No such edit.")
    return public(e)


def pending(lib, name):
    """How many of a member's edits have variations nobody has chosen from yet, or are being
    made: the number on its card."""
    return sum(
        1
        for e in _all(lib, name)
        if e["state"] in ACTIVE
        or (e["state"] == "done" and not any(v.get("used") for v in e.get("variations") or []))
    )


def picture(client, project, name, k, letter, small=False):
    """The path of a variation's picture, or of the marked picture (letter "marks"), or None."""
    try:
        lib, _, _ = _target(client, project, name)
    except EditError:
        return None
    if letter != "marks" and letter not in LETTERS:
        return None
    p = os.path.join(_dir(lib, name, k), letter + (".thumb.png" if small else ".png"))
    return p if os.path.exists(p) else None


# ------------------------------------------------------------------ what an edit may cost
def limits(n, model=None, painted=False):
    """An edit's allowance: Claude's working time by its variations, and a budget far under a
    film's -- one file is read and written, not a film. A model's rate is film.CLAUDE_MODELS'."""
    rate = films.CLAUDE_MODELS.get(model, 1.0)
    work = (4 + 2 * n) * 60 if painted else (6 + 3 * n) * 60
    usd = (0.6 + 0.3 * (n - 1)) if painted else (1.5 + 0.75 * (n - 1))
    return {
        "claude_s": work,
        "wall_s": work + 15 * 60,
        "budget_usd": round(usd * rate, 2),
        "reserve_usd": round(usd * rate / 2, 2),
        "max_turns": 60 + 30 * n,
    }


def reserve(n, auth, model=None, painted=False):
    return limits(n, model, painted)["reserve_usd"] if auth == "api" else 0.05


def in_flight():
    return {j["id"] for j in JOBS.values() if j["state"] in ACTIVE}


def mine(client=None):
    """The edits being made here, as the server counts work in the making: (client, reserve)."""
    return [
        (j["client"], j["reserve"])
        for j in JOBS.values()
        if j["state"] in ACTIVE and (client is None or j["client"] == client)
    ]


# ------------------------------------------------------------------ what is asked
def clean(ask, marks, n, claude):
    """The asking, checked: (ask, marks, n, claude). marks: [{x, y, w?, h?, text}], fractions of
    the picture; a mark with w and h is a box around (x, y), else a point."""
    ask = " ".join(str(ask or "").split())
    out = []
    if marks is not None and not isinstance(marks, list):
        raise EditError(400, "marks is a list.")
    for m in marks or []:
        if not isinstance(m, dict):
            raise EditError(400, "A mark is {x, y, text}, with w and h for a box.")
        try:
            x, y = float(m.get("x")), float(m.get("y"))
            w = float(m["w"]) if m.get("w") is not None else None
            h = float(m["h"]) if m.get("h") is not None else None
        except (TypeError, ValueError):
            raise EditError(400, "A mark's x, y, w and h are numbers from 0 to 1.") from None
        if not (0 <= x <= 1 and 0 <= y <= 1) or any(
            v is not None and not 0 < v <= 1 for v in (w, h)
        ):
            raise EditError(400, "A mark's x, y, w and h are numbers from 0 to 1.")
        text = " ".join(str(m.get("text") or "").split())
        if len(text) > MARK_MAX:
            raise EditError(400, "A mark's note is at most %d characters." % MARK_MAX)
        box = {"w": round(w, 4), "h": round(h, 4)} if w and h else {}
        out.append({"x": round(x, 4), "y": round(y, 4), **box, "text": text})
    if len(out) > MARKS:
        raise EditError(400, "At most %d marks." % MARKS)
    if not ask and not any(m["text"] for m in out):
        raise EditError(400, "Say what should change.")
    if len(ask) > ASK_MAX:
        raise EditError(400, "At most %d characters." % ASK_MAX)
    try:
        n = int(n if n is not None else 1)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= MAX_N:
        raise EditError(400, "variations is 1 to %d." % MAX_N)
    claude = {k: v for k, v in (claude or {}).items() if v is not None}
    if claude.get("model") is not None and claude["model"] not in films.CLAUDE_MODELS:
        raise EditError(400, "model must be one of: %s" % ", ".join(films.CLAUDE_MODELS))
    if claude.get("effort") is not None and claude["effort"] not in films.EFFORTS:
        raise EditError(400, "effort must be one of: %s" % ", ".join(films.EFFORTS))
    if (
        "fable" in (claude.get("model") or "")
        and claude.get("effort", FABLE_EFFORT) != FABLE_EFFORT
    ):
        raise EditError(400, "With Fable, an edit is made at %s effort." % FABLE_EFFORT, "effort")
    if "fable" in (claude.get("model") or ""):
        claude["effort"] = FABLE_EFFORT
    return ask, out, n, claude


def _today(lib):
    """The edits a project asked for in the last day, over all its members."""
    since = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    d = os.path.join(library.dir_of(lib), "cast")
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    return sum(1 for n in names for e in _all(lib, n) if (e.get("asked") or "") >= since)


# ------------------------------------------------------------------ the working copy
class Work(films.Film):
    """The copy an edit works in: Claude writes its variations and nothing else."""

    edit_painted = False

    def writable(self, p):
        p = os.path.normcase(os.path.realpath(p))
        parent, name = os.path.dirname(p), os.path.basename(p)
        if self.edit_painted:
            return parent == os.path.normcase(os.path.realpath(self.dir)) and name == "paint.json"
        return parent == os.path.normcase(os.path.realpath(self.path("variations"))) and bool(
            VARIATION.match(name)
        )

    def editable(self):
        return ("paint.json",) if self.edit_painted else ()


def _base_file(lib, name, m, base):
    """The file an edit starts from: the member's version in use, or a variation of an earlier
    edit (Refine this). -> (path, {"version", "hash", "edit"?, "letter"?})."""
    info = {"version": m["version"], "hash": m.get("hash")}
    if m.get("new") and not base:
        return None, info  # a new scene: nothing to start from
    ext = m.get("ext") if m.get("painted") else "js"
    cur = os.path.join(library.dir_of(lib), "cast", name, "v%d.%s" % (m["version"], ext))
    if not base:
        if not os.path.exists(cur):
            raise EditError(409, "This version's file is no longer kept.")
        return cur, info
    e = _read(lib, name, base.get("edit")) if isinstance(base, dict) else None
    v = next(
        (v for v in (e or {}).get("variations") or [] if v["letter"] == base.get("letter")), None
    )
    p = os.path.join(_dir(lib, name, e["k"]), v["file"]) if v else None
    if not p or not os.path.exists(p):
        raise EditError(404, "That variation is no longer kept.")
    return p, info | {"edit": e["k"], "letter": v["letter"]}


def _marked(src, marks, out):
    """The picture with each mark ringed and numbered, as Claude is shown it. src: a picture, or
    None (nothing to mark on). Returns whether it was written."""
    from PIL import Image, ImageDraw, ImageFont

    if not src or not os.path.exists(src):
        return False
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((1280, 1280))
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", max(20, im.width // 40))
        except OSError:
            font = ImageFont.load_default()
        for i, m in enumerate(marks, 1):
            cx, cy = m["x"] * im.width, m["y"] * im.height
            if m.get("w"):
                x0, y0 = cx - m["w"] * im.width / 2, cy - m["h"] * im.height / 2
                x1, y1 = cx + m["w"] * im.width / 2, cy + m["h"] * im.height / 2
                for k, col in ((4, (255, 255, 255)), (0, RING)):
                    d.rectangle((x0 - k, y0 - k, x1 + k, y1 + k), outline=col, width=4)
                tx, ty = x0 + 6, y0 + 4
            else:
                r = max(16, im.width // 55)
                for k, col in ((r + 4, (255, 255, 255)), (r, RING)):
                    d.ellipse((cx - k, cy - k, cx + k, cy + k), outline=col, width=4)
                tx, ty = cx + r + 6, cy - r
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                d.text((tx + dx, ty + dy), str(i), fill=(255, 255, 255), font=font)
            d.text((tx, ty), str(i), fill=RING, font=font)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        im.save(out)
    return True


def _where(m):
    col = "left" if m["x"] < 0.34 else "right" if m["x"] > 0.66 else "middle"
    row = "top" if m["y"] < 0.34 else "bottom" if m["y"] > 0.66 else "centre"
    return "%s %s of the picture" % (row, col) + (", a boxed area" if m.get("w") else "")


def marks_text(marks):
    if not marks:
        return ""
    return "\n".join(
        "%d. (%s) %s" % (i, _where(m), m["text"] or "see what is asked above")
        for i, m in enumerate(marks, 1)
    )


def prepare(lib, idx, name, m, e, episode):
    """The working copy for an edit: a copy of `episode` (rounds.copy_of) with the library's
    current cast over it, the base to change, and the marked picture. Returns the Work."""
    import rounds

    rid = "edit-" + e["id"]
    copy = rounds.copy_of(episode, rid, [])
    work = Work(copy.dir)
    work.edit_painted = bool(m.get("painted"))
    rec = dict(work.record())
    for k in ("characters", "round_of", "people", "model", "effort"):
        rec.pop(k, None)
    rec.update(
        state="claude",
        prompt="(an edit of %s)" % name,
        edit_of={"project": e["project"], "name": name, "id": e["id"]},
        **{k: e[k] for k in ("model", "effort") if e.get(k)},
    )
    films._write_json(work.path("studio.json"), rec)
    d = library.dir_of(lib)
    base, _ = _base_file(lib, name, m, e.get("base_asked"))
    if work.edit_painted and base is None:  # a new painted scene: painted from words alone
        try:
            with open(work.path("paint.json"), encoding="utf-8") as f:
                paint = json.load(f)
        except (OSError, ValueError):
            paint = {}
        paint["images"] = []
        films._write_json(work.path("paint.json"), paint)
        shutil.rmtree(work.path("images"), ignore_errors=True)
        marked = False
    elif work.edit_painted:
        # the member's picture, as the paintings' "ref": "cast_<name>" reads it
        ext = os.path.splitext(base)[1].lstrip(".")
        rel = "inputs/cast_%s.%s" % (name, ext)
        os.makedirs(work.path("inputs"), exist_ok=True)
        for x in library.PICTURE_EXT:
            with contextlib.suppress(OSError):
                os.remove(work.path("inputs", "cast_%s.%s" % (name, x)))
        shutil.copyfile(base, work.path(*rel.split("/")))
        with open(work.manifest, encoding="utf-8") as f:
            man = json.load(f)
        man.setdefault("images", {})["cast_" + name] = rel
        films._write_json(work.manifest, man)
        try:
            with open(work.path("paint.json"), encoding="utf-8") as f:
                paint = json.load(f)
        except (OSError, ValueError):
            paint = {}
        paint["images"] = []  # the episode's own paintings are not this edit's to paint again
        films._write_json(work.path("paint.json"), paint)
        shutil.rmtree(work.path("images"), ignore_errors=True)
        marked = _marked(base, e["marks"], work.path("variations", "marks.png"))
    else:
        os.makedirs(work.path("cast"), exist_ok=True)
        for n, c in idx["cast"].items():  # the library's cast as it is now, over the episode's
            src = os.path.join(d, "cast", n, "v%d.js" % c["version"])
            if not c.get("deleted") and not c.get("painted") and os.path.exists(src):
                shutil.copyfile(src, work.path("cast", n + ".js"))
        with contextlib.suppress(OSError):
            os.remove(
                work.path("cast", name + ".js")
            )  # a new scene's name: no older one in its way
        if base:
            shutil.copyfile(base, work.path("cast", name + ".js"))
        os.makedirs(work.path("variations"), exist_ok=True)
        pic = None if m.get("new") else assets.picture(e["client"], e["project"], name)
        if e.get("base_asked"):
            pic = os.path.join(_dir(lib, name, e["base"]["edit"]), "%s.png" % e["base"]["letter"])
        marked = _marked(pic, e["marks"], work.path("variations", "marks.png"))
    return work, marked


# ------------------------------------------------------------------ what Claude is told
ASK_DRAWN = """\
This is not a film to make. The series' maker wants ONE member of its cast changed, outside any \
episode: %(what)s `%(name)s` (%(about)s). Every later episode will draw the version they choose, \
so it must stay the same member: the same name, the same way of being called (draw(x, y, o), \
and for a place its kind and camera), the same size and place on the stage, and everything the \
maker did not mention exactly as it is.

The member is cast/%(name)s.js: read it first, whole. The rest of the cast is in cast/ beside \
it; the episode in this folder (film.js) shows how the series uses them, to read, not to change.

What the maker asks for:

%(ask)s
%(marks)s
Make %(n)d variation%(s)s. Write each as a whole file, variations/a.js%(more)s: a complete \
replacement for cast/%(name)s.js that registers SK.cast.%(name)s. You can write nothing else.
%(differ)s
How to work:
- Start each variation from the member's own code: copy it, then change what is asked. Do not \
rewrite what was not asked about.
- `look` draws every variation you have written, alone, as the maker will see it, and tells you \
where each picture is: Read them. Look after every change; a variation you have not looked at \
is not done.
- Compare with the member as it is (%(now)s): is what was asked different, and is everything \
else the same?
- When a variation is right, call `variation` with its letter and one plain sentence for the \
maker saying what is different in it (no file names, no code words). Only variations you name \
are shown to the maker.
- Something asked for that cannot be done in this member (it belongs to an episode, or to \
another member): say so in `summary`, and make the variations as close as the member allows.
- Last, `summary`: one or two plain sentences on what you made.
Your working time: about %(minutes)d minutes.
"""
ASK_PAINTED = """\
This is not a film to make. The series' maker wants ONE picture of its cast changed, outside any \
episode: %(what)s `%(name)s` (%(about)s). Every later episode is painted from the picture they \
choose, so it must stay the same %(thing)s: everything the maker did not mention exactly as it \
is -- the same framing, colours, style and proportions.

The picture is inputs/%(file)s: Read it first.

What the maker asks for:

%(ask)s
%(marks)s
Make %(n)d variation%(s)s, as paintings in paint.json: images named v_a%(more)s, each with \
"ref": "cast_%(name)s" so the painter starts from the picture itself, and a prompt that says: \
this exact picture, identical in every way -- same framing, same style, same colours, same \
everything -- with one change only, and then the change, in plain visual words (where in the \
picture, what it becomes). Leave the rest of paint.json as it is. You can write nothing else.
%(differ)s
How to work:
- `paint` paints them; then Read images/v_a.jpg%(more2)s and compare each with the picture: is \
what was asked different, and is everything else the same? A painting that drifted (another \
face, another room, another style) is painted again with a tighter prompt: `paint` with retake.
- You have %(runs)d paintings in all, retakes included.
- When a variation is right, call `variation` with its letter and one plain sentence for the \
maker saying what is different in it. Only variations you name are shown to the maker.
- Last, `summary`: one or two plain sentences on what you made.
Your working time: about %(minutes)d minutes.
"""
ASK_NEW_DRAWN = """\
This is not a film to make. The series' maker wants a NEW place for its cast, outside any \
episode: `%(name)s`, a place the episodes will come back to. What they ask for:

%(ask)s

Every later episode will draw it as SK.cast.%(name)s, so write it the way this series writes its \
places: %(examples)s The episode in this folder (film.js) shows how the series uses its cast and \
its places, to read, not to change.

Make %(n)d variation%(s)s. Write each as a whole file, variations/a.js%(more)s: a new cast member \
that registers SK.cast.%(name)s, with kind: 'place' and an about: line saying in one sentence \
what the place is. You can write nothing else.
%(differ)s
How to work:
- A place is the whole room or street as the camera sees it: nobody in it and no words in it, in \
the series' own style, palette and line, the same size on the stage as its other places.
- `look` draws every variation you have written, alone, as the maker will see it, and tells you \
where each picture is: Read them. Look after every change; a variation you have not looked at \
is not done.
- When a variation is right, call `variation` with its letter and one plain sentence for the \
maker saying what it shows (no file names, no code words). Only variations you name are shown \
to the maker.
- Last, `summary`: one or two plain sentences on what you made.
Your working time: about %(minutes)d minutes.
"""
ASK_NEW_PAINTED = """\
This is not a film to make. The series' maker wants a NEW painted place for its cast, outside \
any episode: `%(name)s`, a place the episodes will come back to. Every scene set there will be \
painted from the picture they choose. What they ask for:

%(ask)s

Make %(n)d variation%(s)s, as paintings in paint.json: images named v_a%(more)s, each a wide \
painting of the whole place as the camera sees it -- nobody in it, no words, letters or signs -- \
in the series' look: keep paint.json's `style`, and paint with its palette and light. Describe \
each fully, in plain visual words. No "ref": this is a new place. Leave the rest of paint.json \
as it is. You can write nothing else.
%(differ)s
How to work:
- `paint` paints them; then Read images/v_a.jpg%(more2)s: is it the place asked for, in the \
series' look, with nobody in it? One that is not is painted again with a tighter prompt: `paint` \
with retake.
- You have %(runs)d paintings in all, retakes included.
- When a variation is right, call `variation` with its letter and one plain sentence for the \
maker saying what it shows. Only variations you name are shown to the maker.
- Last, `summary`: one or two plain sentences on what you made.
Your working time: about %(minutes)d minutes.
"""
DIFFER_NEW = (
    "The variations are different takes on the place the maker described (the view, the "
    "layout, the light, the mood) for them to choose between: not the same picture %d times, "
    "and nothing the maker did not ask for.\n"
)
DIFFER = (
    "The variations answer the same asking in different ways the maker can choose between "
    "(how far the change goes, its shape, its colour): not the same picture %d times, and "
    "never a change the maker did not ask for.\n"
)


def ask(work, name, m, e, lim, marked):
    n = e["n"]
    marks = marks_text(e["marks"])
    if marks:
        marks = "\nThe maker marked the picture%s:\n\n%s\n" % (
            " (variations/marks.png: Read it; each mark is ringed and numbered)" if marked else "",
            marks,
        )
    common = {
        "name": name,
        "about": m.get("about") or "no description",
        "ask": e["ask"] or "(see the marks below)",
        "marks": marks,
        "n": n,
        "s": "" if n == 1 else "s",
        "differ": DIFFER % n if n > 1 else "",
        "minutes": lim["claude_s"] // 60,
    }
    letters = list(LETTERS[:n])
    if m.get("new") and not e.get("base_asked"):
        common["differ"] = DIFFER_NEW % n if n > 1 else ""
        if work.edit_painted:
            return ASK_NEW_PAINTED % (
                common
                | {
                    "more": "".join(", v_%s" % x for x in letters[1:]),
                    "more2": "".join(", images/v_%s.jpg" % x for x in letters[1:]),
                    "runs": n * 2 + 1,
                }
            )
        places = (
            sorted(
                k
                for k, c in (library.load(library.lib_of(work.record())) or {"cast": {}})[
                    "cast"
                ].items()
                if c.get("kind") == "place" and not c.get("painted") and not c.get("deleted")
            )
            if library.lib_of(work.record())
            else []
        )
        examples = (
            "its places are %s: read %s first, whole."
            % (", ".join("cast/%s.js" % x for x in places), "them" if len(places) > 1 else "it")
            if places
            else "it has no place yet, so read how cast/ members are written (the "
            "SK.cast.<name> = {...} shape, about:, draw) and how film.js draws its backgrounds."
        )
        return ASK_NEW_DRAWN % (
            common
            | {
                "examples": examples,
                "more": "".join(", variations/%s.js" % x for x in letters[1:]),
            }
        )
    if work.edit_painted:
        file = "cast_%s.%s" % (name, os.path.splitext(_base_name(work, name))[1].lstrip("."))
        return ASK_PAINTED % (
            common
            | {
                "what": "the painted place"
                if m.get("kind") == "place"
                else "the painted character",
                "thing": "place" if m.get("kind") == "place" else "character",
                "file": file,
                "more": "".join(", v_%s" % x for x in letters[1:]),
                "more2": "".join(", images/v_%s.jpg" % x for x in letters[1:]),
                "runs": n * 2 + 1,
            }
        )
    return ASK_DRAWN % (
        common
        | {
            "what": "the place" if m.get("kind") == "place" else "the character or thing",
            "more": "".join(", variations/%s.js" % x for x in letters[1:]),
            "now": "variations/marks.png shows it" if marked else "`look` shows it beside them",
        }
    )


def _base_name(work, name):
    for x in library.PICTURE_EXT:
        if os.path.exists(work.path("inputs", "cast_%s.%s" % (name, x))):
            return "cast_%s.%s" % (name, x)
    return "cast_%s.png" % name


class State:
    """What an edit adds to the film's tools (tools.Tools.round): `look`, `variation` and
    `summary`, and what they collect."""

    def __init__(self, work, name, n, tools, on_change, place=False):
        self.work, self.name, self.n, self.t, self.on_change = work, name, n, tools, on_change
        self.place = place  # a new scene: each variation must say kind: 'place'
        self.named, self.summary = {}, None  # letter -> what
        self.drawn = {}  # letter -> the hash of the code its picture was drawn from
        self.without = ()  # tools.only already leaves only what an edit uses

    def letters(self):
        return list(LETTERS[: self.n])

    def code(self, letter):
        try:
            with open(self.work.path("variations", letter + ".js"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def problem(self, letter, code):
        """Why a variation's file cannot be the member, or None."""
        names = re.findall(r"\bSK\.cast\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", code)
        if names != [self.name]:
            return (
                "variations/%s.js must register SK.cast.%s, once, and nothing else (it has %s)"
                % (
                    letter,
                    self.name,
                    ", ".join(names) or "none",
                )
            )
        if len(code.encode("utf-8")) > library.MAX_BYTES:
            return "variations/%s.js is over %d bytes" % (letter, library.MAX_BYTES)
        if self.place and library._kind(code) != "place":
            return "variations/%s.js must say kind: 'place' (it is a scene)" % letter
        return None

    async def draw(self, letters):
        """Each of these variations drawn alone, in place of the member: variations/<l>.png."""
        w, orig = self.work, self.work.path("cast", self.name + ".js")
        keep = None  # a new scene has no file of its own yet
        if os.path.exists(orig):
            with open(orig, encoding="utf-8") as f:
                keep = f.read()
        out = {}
        try:
            for x in letters:
                code = self.code(x)
                with open(orig, "w", encoding="utf-8") as f:
                    f.write(code)
                man, times = library.sheet(w, [self.name])
                with contextlib.suppress(OSError):
                    os.remove(w.path("variations", x + ".png"))
                try:
                    await self.t.cast_sheet(man, times)
                except toolbox.ToolError as err:
                    out[x] = "did not draw: %s" % str(err)[-400:]
                    continue
                im = library.thumbs(w, [self.name], assets.PICTURE).get(self.name)
                if im is None:
                    out[x] = "drew nothing"
                    continue
                im.save(w.path("variations", x + ".png"))
                self.drawn[x] = library._hash(code)
                out[x] = None
        finally:
            if keep is None:
                with contextlib.suppress(OSError):
                    os.remove(orig)
            else:
                with open(orig, "w", encoding="utf-8") as f:
                    f.write(keep)
        return out

    async def look(self):
        have = [x for x in self.letters() if self.code(x) is not None]
        if not have:
            raise toolbox.ToolError("Write variations/a.js first.")
        said = []
        for x in have:
            bad = self.problem(x, self.code(x))
            if bad:
                said.append("%s: %s" % (x, bad))
        ok = [x for x in have if not self.problem(x, self.code(x))]
        self.on_change("Drawing the variations")
        res = await self.draw(ok) if ok else {}
        for x in ok:
            said.append(
                "%s: %s" % (x, res[x]) if res[x] else "%s: drawn. Read variations/%s.png" % (x, x)
            )
        return "\n".join(said)

    async def variation(self, letter, what):
        letter = str(letter or "").strip().lower()
        if letter not in self.letters():
            raise toolbox.ToolError("letter is one of: %s" % ", ".join(self.letters()))
        what = " ".join(str(what or "").split())[:300]
        if not what:
            raise toolbox.ToolError("what: one plain sentence for the maker")
        if self.work.edit_painted:
            if not os.path.exists(self.work.path("images", "v_%s.jpg" % letter)):
                raise toolbox.ToolError("v_%s is not painted yet: `paint` first." % letter)
        else:
            code = self.code(letter)
            if code is None:
                raise toolbox.ToolError("variations/%s.js is not written yet." % letter)
            bad = self.problem(letter, code)
            if bad:
                raise toolbox.ToolError(bad)
            if self.drawn.get(letter) != library._hash(code):
                raise toolbox.ToolError(
                    "variations/%s.js changed since you looked at it: `look`, Read its picture, "
                    "then name it." % letter
                )
        self.named[letter] = what
        self.on_change("Variation %s is ready" % letter.upper())
        left = [x for x in self.letters() if x not in self.named]
        return "Kept." + (" Still to name: %s." % ", ".join(left) if left else "")

    async def say_summary(self, text):
        text = " ".join(str(text or "").split())[:500]
        if not text:
            raise toolbox.ToolError("text: one or two plain sentences for the maker")
        self.summary = text
        self.on_change("Wrapping up")
        return "Kept."

    def tools(self, tool, wrap):
        out = [
            tool(
                "variation",
                "Name a finished variation for the maker: its letter, and what -- one plain "
                "sentence saying what is different in it.",
                {
                    "type": "object",
                    "properties": {"letter": {"type": "string"}, "what": {"type": "string"}},
                    "required": ["letter", "what"],
                },
            )(wrap(lambda a: self.variation(a.get("letter"), a.get("what")))),
            tool(
                "summary",
                "Say what you made, in one or two plain sentences.",
                {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )(wrap(lambda a: self.say_summary(a.get("text")))),
        ]
        if not self.work.edit_painted:
            out.insert(
                0,
                tool(
                    "look",
                    "Draw every variation written so far, each alone as the maker will see it; "
                    "says where each picture is, or why one did not draw.",
                    {"type": "object", "properties": {}},
                )(wrap(lambda a: self.look())),
            )
        return out


# ------------------------------------------------------------------ asking
def start(
    client,
    project,
    name,
    sched,
    ask,
    marks=None,
    n=1,
    key=None,
    member=None,
    priority=0,
    auth="api",
    claude=None,
    base=None,
    new=None,
):
    """Make variations of this member; the edit's job. Asked again with the same key, the edit
    already asked for. Raises EditError for what cannot be one. new ({} or {"about"}): a new
    scene under this name, made from the asking alone (base: a variation of an earlier one)."""
    if new is not None:
        lib, idx, m = _new_scene(client, project, name, ask, new, base)
    else:
        lib, idx, m = _member(client, project, name)
    for e in _all(lib, name):
        if key and e.get("key") == key:
            return JOBS.get(e["id"]) or {"id": e["id"], "k": e["k"], "state": e["state"]}
    ask, marks, n, claude = clean(ask, marks, n, claude)
    canon = library.clients.canon(client)
    if any(j["state"] in ACTIVE and j["owner"] == canon for j in JOBS.values()):
        raise EditError(
            409, "Another edit is being made. This one can start when it is done.", "edit"
        )
    if _today(lib) >= PER_DAY:
        raise EditError(429, "This project has had its %d edits for today." % PER_DAY, "edits")
    if not assets.episode_of(idx):
        raise EditError(
            409,
            "This project has no finished episode yet: an edit is made with an episode's setup. "
            "Make the first episode, then change its scenes and characters here.",
            "episode",
        )
    _, info = _base_file(lib, name, m, base)
    k = max([e["k"] for e in _all(lib, name)] + [0]) + 1
    e = {
        "id": eid_of(project, name, k),
        "k": k,
        "project": project,
        "name": name,
        "client": client,
        "member": member,
        "key": key,
        "state": "queued",
        "asked": _now(),
        "ask": ask,
        "marks": marks,
        "n": n,
        "model": claude.get("model"),
        "effort": claude.get("effort") or EFFORT,
        "painted": bool(m.get("painted")),
        "kind": m.get("kind"),
        **({"new": {"about": m["about"]}} if m.get("new") else {}),
        "base": info,
        "base_asked": base if base else None,
        "auth": auth,
        "priority": int(bool(priority)),
        "server": peers.SERVER_ID,
        "now": "Waiting for a free studio",
        "variations": [],
    }
    _write(lib, name, e)
    job = {
        "id": e["id"],
        "k": k,
        "name": name,
        "project": project,
        "state": "queued",
        "client": client,
        "owner": canon,
        "reserve": reserve(n, auth, claude.get("model"), e["painted"]),
        "cost_usd": 0,
        "stopped": False,
        "task": None,
    }
    JOBS[e["id"]] = job
    job["task"] = asyncio.get_running_loop().create_task(_run(job, lib, sched))
    return job


def _new_scene(client, project, name, ask, new, base):
    """(lib, idx, the draft) for a new scene asked for under `name`; refused when the project has
    a member by that name, or its places are full."""
    lib = library.owner(client, project)
    if not lib or not project:
        raise EditError(404, "No such project.")
    if not library.NAME.match(name or ""):
        raise EditError(
            400,
            "A scene's name is lowercase letters, digits and _, starting with a letter.",
            "name",
        )
    idx = library.load(lib)
    have = idx["cast"].get(name)
    if have and not have.get("deleted"):
        raise EditError(409, "The project has @%s already: choose another name." % name, "name")
    if (
        base is None
        and _draft(lib, idx, name)
        and any(e["state"] in ACTIVE for e in _all(lib, name))
    ):
        raise EditError(409, "@%s is being made already." % name, "edit")
    places = [c for c in idx["cast"].values() if c.get("kind") == "place" and not c.get("deleted")]
    if len(places) >= library.PLACES:
        raise EditError(
            409, "A project keeps up to %d scenes: remove one first." % library.PLACES, "places"
        )
    about = " ".join(str((new or {}).get("about") or ask or "").split())[: library.MAX_ABOUT]
    painted = _painted_project(idx)
    d = _draft(lib, idx, name)
    if d and base is not None:  # a variation of the draft refined: the draft keeps its kind
        painted = d["painted"]
    return (
        lib,
        idx,
        {
            "name": name,
            "kind": "place",
            "about": about,
            "painted": painted,
            "version": 0,
            "hash": (have or {}).get("hash") if have else None,
            "new": True,
        },
    )


def stop(client, project, name, k):
    lib, _, _ = _target(client, project, name)
    e = _read(lib, name, k)
    if not e or e["state"] not in ACTIVE:
        raise EditError(409, "No edit is being made.", "none")
    job = JOBS.get(e["id"])
    if job is not None and job["task"] is not None and not job["task"].done():
        job["stopped"] = True
        job["task"].cancel()
        return public(dict(e, state="cancelled"))
    e.update(state="cancelled", finished=_now(), server=None, now=None)
    _write(lib, name, e)
    return public(e)


async def stop_all():
    tasks = [j["task"] for j in JOBS.values() if j["task"] is not None and not j["task"].done()]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=20)


def dismiss(client, project, name, k):
    """Throw an edit's variations away (not one being made)."""
    lib, idx, m = _target(client, project, name)
    e = _read(lib, name, k)
    if not e:
        raise EditError(404, "No such edit.")
    if e["state"] in ACTIVE:
        raise EditError(409, "This edit is being made: stop it first.", "active")
    shutil.rmtree(_dir(lib, name, k), ignore_errors=True)
    if m.get("new") and not _all(lib, name):  # a draft with nothing left: no trace of it
        shutil.rmtree(os.path.join(library.dir_of(lib), "cast", name), ignore_errors=True)
    return True


def sweep():
    """At startup: an edit a server that is gone left in the making is ended as interrupted (its
    credits come back; the person asks again). -> [(edit id, fields for its studio_runs doc)]."""
    out = []
    try:
        owners = os.listdir(library.ROOT)
    except OSError:
        return out
    for o in owners:
        for root, dirs, files in os.walk(os.path.join(library.ROOT, o)):
            if os.path.basename(os.path.dirname(root)) != "edits" or "edit.json" not in files:
                continue
            dirs[:] = []
            try:
                with open(os.path.join(root, "edit.json"), encoding="utf-8") as f:
                    e = json.load(f)
            except (OSError, ValueError):
                continue
            if (
                e.get("state") in ACTIVE
                and e["id"] not in JOBS
                and not peers.alive(e.get("server"))
            ):
                why = "The studio restarted while this edit was being made."
                e.update(state="interrupted", error=why, finished=_now(), server=None, now=None)
                films._write_json(os.path.join(root, "edit.json"), e)
                import rounds

                shutil.rmtree(rounds.work_dir("edit-" + e["id"]), ignore_errors=True)
                out.append((e["id"], {"kind": "edit", "state": "interrupted", "error": why}))
    return out


# ------------------------------------------------------------------ the job
async def _run(job, lib, sched):
    import agent
    import rounds
    from sched import Clock, waiting_text

    eid, name, k = job["id"], job["name"], job["k"]
    e = _read(lib, name, k)
    auth = e.get("auth") or "api"
    lim = limits(e["n"], e.get("model"), e["painted"])
    t0, meter, clock = time.time(), agent.Meter(), Clock()
    said = {"at": 0.0}
    work, state = None, None

    def put(st=None, **more):
        nonlocal e
        if st:
            job["state"] = st
            e["state"] = st
        e.update(more)
        with contextlib.suppress(OSError):
            _write(lib, name, e)

    told = live.of(eid, lambda r, fields: agent.STORE.save(r, {"kind": "edit", **fields}))

    def tell_now(text, force=False):
        told.say(text, ahead=None)
        if not force and time.time() - said["at"] < 4:
            return
        said["at"] = time.time()
        put(now=text)

    def emit(ev):
        kind = ev.get("type")
        if kind == "cost":
            job["cost_usd"] = ev["usd"] if auth == "api" else 0
        elif kind == "wait":
            told.event(ev)
            if job["state"] == "queued":
                put(now=ev.get("text"))
        elif kind == "stage":
            tell_now(ev.get("text") or "Working", force=True)
        elif kind == "tool":
            told.event(ev)
            if rounds.plain(ev.get("text")):
                tell_now(rounds.plain(ev.get("text")))

    def on_wait(pool, ahead):
        emit({"type": "wait", "pool": pool, "ahead": ahead, "text": waiting_text(pool, ahead)})

    def cost():
        img = (
            sum(x.get("cost_usd") or 0 for x in agent._spend(work, "images", "spend.jsonl"))
            if work
            else 0
        )
        claude = round(meter.usd(), 4)
        return {
            "cost_usd": round((claude if auth == "api" else 0) + img, 4),
            "claude_cost_usd": claude,
            "claude_billed": auth == "api",
            "image_cost_usd": round(img, 6),
            "tokens": meter.tokens(),
            "seconds": round(time.time() - t0, 1),
            "auth": auth,
            "release": films.RELEASE,
        }

    doc = {
        "kind": "edit",
        "project_id": e["project"],
        "name": name,
        "k": k,
        "job": eid,
        "client": e["client"],
        **({"member": e["member"]} if e.get("member") else {}),
        "key": e.get("key"),
        "host": store.HOST,
        "model": e.get("model") or agent.MODEL,
        "effort": e.get("effort"),
        "asked_for": e["n"],
        "painted": e["painted"],
        "release": films.RELEASE,
        "auth": auth,
    }

    async def over(st, error=None, **more):
        put(st, error=error, finished=_now(), server=None, now=None, **more)
        await agent.save(
            eid,
            {**doc, "state": st, "error": error, **cost(), **more, "finished_at": store.now()},
            True,
        )

    await agent.save(eid, {**doc, "state": "queued", "now": e["now"], "cost_usd": 0.0})
    try:
        peers.hold_own()
        async with sched["claude"].hold(1, eid, on_wait, priority=e.get("priority", 0)):
            clock.t0, clock.paused = time.time(), 0.0
            first = "Reading what you asked for"
            put("running", started=_now(), now=first)
            await agent.save(
                eid, {**doc, "state": "running", "started_at": store.now(), "now": first}
            )
            idx = library.load(lib)
            m = idx["cast"].get(name)
            if e.get("new"):
                if m and not m.get("deleted"):
                    raise EditError(409, "The project has @%s already." % name)
                m = _draft_of(e) | {"hash": (m or {}).get("hash")}
            elif not m or m.get("deleted"):
                raise EditError(409, "It was removed from the project meanwhile.")
            episode = assets.episode_of(idx)
            if not episode:
                raise EditError(409, "The project's episodes are no longer here.")
            work, marked = await asyncio.to_thread(prepare, lib, idx, name, m, e, episode)
            if marked:
                os.makedirs(_dir(lib, name, k), exist_ok=True)
                shutil.copyfile(
                    work.path("variations", "marks.png"),
                    os.path.join(_dir(lib, name, k), "marks.png"),
                )
            t = toolbox.Tools(work, sched, emit, clock)
            t.priority, t.pulse = e.get("priority", 0), agent.Pulse()
            t.only = ("paint",) if work.edit_painted else ()
            state = State(
                work,
                name,
                e["n"],
                t,
                lambda text: tell_now(text, force=True),
                place=bool(e.get("new")),
            )
            t.round = state
            say = {
                "prompt": ask(work, name, m, e, lim, marked),
                "system": agent.system_prompt(work.look, work.caps),
                "effort": e.get("effort") or EFFORT,
                "budget_usd": lim["budget_usd"],
            }
            res = None
            for attempt in (1, 2):
                try:
                    res = await agent._within(
                        agent.run_claude(work, emit, meter, t, auth, **say), clock, lim, t.pulse
                    )
                    break
                except (agent.SignInError, agent.PlanLimit) as err:
                    if auth != "login" or attempt == 2:
                        raise RuntimeError("Claude could not be reached: %s" % err) from None
                    auth = "api"
                    job["reserve"] = reserve(e["n"], auth, e.get("model"), e["painted"])
                except agent.apikey.CreditOut as err:
                    if attempt == 2:
                        raise RuntimeError("Claude could not be reached: %s" % err) from None
                except agent.Stalled:
                    raise RuntimeError("Claude stopped answering") from None
                except TimeoutError:
                    break  # past its time: the variations it named so far are kept
            if res is not None and res.is_error and not state.named:
                raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
            put("finishing", now="Keeping the variations")
            kept = await _collect(lib, name, k, work, state)
        if not kept:
            await over(
                "unchanged",
                "Claude could not make the change asked for."
                if not (state and state.summary)
                else state.summary,
                summary=state.summary if state else None,
                delivered=0,
            )
            return
        await over("done", summary=state.summary, variations=kept, delivered=len(kept))
    except asyncio.CancelledError:
        st = "cancelled" if job["stopped"] else "interrupted"
        with contextlib.suppress(Exception):
            await asyncio.shield(
                over(
                    st,
                    None
                    if job["stopped"]
                    else "The studio restarted while this edit was being made.",
                )
            )
        raise
    except EditError as err:
        await over("failed", err.text)
    except Exception as err:  # noqa: BLE001 -- whatever went wrong, the edit ends and says so
        await over("failed", str(err)[:300] or type(err).__name__)
    finally:
        if work is not None:
            with contextlib.suppress(Exception):
                t.kill()
            await asyncio.to_thread(shutil.rmtree, work.dir, True)
        JOBS.pop(eid, None)


async def _collect(lib, name, k, work, state):
    """The variations Claude named, into the edit's folder with their pictures:
    [{"letter", "what", "file"}]."""
    from PIL import Image

    d = _dir(lib, name, k)
    os.makedirs(d, exist_ok=True)
    kept = []
    for x in state.letters():
        if x not in state.named:
            continue
        if work.edit_painted:
            src = work.path("images", "v_%s.jpg" % x)
            if not os.path.exists(src):
                continue
            file = "%s.jpg" % x
            shutil.copyfile(src, os.path.join(d, file))
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((assets.PICTURE, assets.PICTURE))
                im.save(os.path.join(d, x + ".png"))
        else:
            code = state.code(x)
            if code is None or state.problem(x, code):
                continue
            if state.drawn.get(x) != library._hash(code):  # changed after the last look
                if (await state.draw([x])).get(x):
                    continue
            pic = work.path("variations", x + ".png")
            if not os.path.exists(pic):
                continue
            file = "%s.js" % x
            with open(os.path.join(d, file), "w", encoding="utf-8") as f:
                f.write(code)
            shutil.copyfile(pic, os.path.join(d, x + ".png"))
        with Image.open(os.path.join(d, x + ".png")) as im:
            im = im.convert("RGBA")
            im.thumbnail((480, 480))
            im.save(os.path.join(d, x + ".thumb.png"))
        kept.append({"letter": x, "what": state.named[x], "file": file})
    return kept


# ------------------------------------------------------------------ choosing
def use(client, project, name, k, letter, force=False):
    """A variation becomes the member's next version. Refused (409, reason "moved") when the
    member changed since the edit started, unless force: the person is asked first, as choosing
    would write over that change. Returns assets.info()."""
    from PIL import Image

    lib, idx, m = _target(client, project, name)
    e = _read(lib, name, k)
    v = next((v for v in (e or {}).get("variations") or [] if v["letter"] == letter), None)
    if not e or e["state"] != "done" or not v:
        raise EditError(404, "No such variation.")
    d = _dir(lib, name, k)
    src = os.path.join(d, v["file"])
    if not os.path.exists(src):
        raise EditError(404, "That variation is no longer kept.")
    if not m.get("new") and m.get("hash") != (e.get("base") or {}).get("hash") and not force:
        raise EditError(
            409,
            "%s has changed since this edit was made (it is version %d now). Using this "
            "variation replaces that change." % (name, m["version"]),
            "moved",
        )
    now = _now()
    if e.get("painted"):
        with library._lock(lib):
            idx = library.load(lib)
            cur = idx["cast"].get(name)
            if m.get("new"):  # a new scene: its first version, a place
                if cur and not cur.get("deleted"):
                    raise EditError(409, "The project has @%s already." % name)
                library._put_painted(
                    lib, idx, name, src, m.get("about"), now, edited=e["id"], kind="place"
                )
            elif not cur or cur.get("deleted") or cur.get("hash") != m.get("hash"):
                raise EditError(409, "%s changed in the project meanwhile: try again." % name)
            else:
                library._put_painted(lib, idx, name, src, cur.get("about"), now, edited=e["id"])
            library._save(lib, idx)
            library._contact(lib, idx)
    else:
        with open(src, encoding="utf-8") as f:
            it = assets.member_of(name, f.read())
        with Image.open(os.path.join(d, letter + ".thumb.png")) as small:
            small.load()
        with Image.open(os.path.join(d, letter + ".png")) as large:
            large.load()
        if m.get("new"):
            cur = idx["cast"].get(name)
            if cur and not cur.get("deleted"):
                raise EditError(409, "The project has @%s already." % name)
            it["about"] = it["about"] or m.get("about") or ""
            seen = (cur or {}).get("hash") if cur else None
        else:
            seen = m.get("hash")
        try:
            assets.put_drawn(lib, [it], {name: seen}, {name: small}, {name: large}, edited=e["id"])
        except assets.AssetError as err:
            raise EditError(err.status, err.text) from None
    got = assets.info(client, project, name)
    for x in e["variations"]:
        if x["letter"] == letter:
            x["used"] = {"version": got["version"], "at": now}
    _write(lib, name, e)
    return got
