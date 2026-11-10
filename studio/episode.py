#!/usr/bin/env python
"""A series' next episode starts from its last episode's code, not from nothing.

    python studio/episode.py --plan <film id>    what the film would start from, and why not
                                                 when it would not; writes nothing

Why: the first write of a film's picture was 47% of Claude's time over 172 films, and a
template's remake -- a film that starts from finished code -- takes a median 5.6 minutes of Claude
against 13.7 for a 30 s film from scratch (docs/studio-speed.md). An episode of a series used to
start empty, with its earlier episodes only to read (library/films/); it starts from the last one
now, the way a template's film starts from the template (templates.seed), and changes the story.

What it is given, in its own folder (carry), as its own to edit:

    film.js, score.json          the last episode's, as it finished
    paint.json                   the series' painting style; no paintings (paint this episode's)
    vo.json                      the voice, its style, its language and the character voices; no
                                 lines (this episode's narration is its own, and recorded anew)
    fonts                        the faces the last episode fetched for itself, in the manifest
    cast/<name>.js               where the last episode's own copy of a member is newer than the
                                 library's (a round changed it, which never reaches the library)
    engine/                      the last episode's engine, when it changed its copy: as it was
                                 on the same release; merged onto this release's otherwise (git
                                 merge-file, base = the engine it started from); when that does
                                 not merge, this release's, and library/start/engine.diff
    library/start/               the last episode as it was, read-only: film.js, vo.json (its
                                 narration), score.json, sfx.json, paint.json, about.json, and
                                 the engine this one started from (engine_diff measures against it)

Never: sfx.json (its cues are seconds on the old narration), scenes, pictures or a spend log.

Which episode: the project's finished one made last (created), not the one finished last: an old
episode finished again moves to the front of the library's index. Only when the two are alike
(compatible): a series, not a collection; the same look, frame, captions and music-or-none; no
people on either side; one conversation, not scenes; narrated both. Otherwise the episode starts
as any film does, and its record says why (carried.skipped).

When: after its length is picked (agent.make_film), because a picked length can make a film one
made in scenes. Once: a film that has carried (its record's `carried`) is never carried again, so
a film picked up after a restart keeps what Claude wrote.

On while STUDIO_EPISODE_CARRY says so: "all", or a comma-separated list of project ids (empty or
"off": off), read from the studio's .env at the moment it is asked -- no restart.

The guards (agent.py): a film.js left as the last episode's fails the film (untouched); words of
the last episode's story still on screen get one turn to go (leftovers), never a failure.
"""

import os
import re
import sys
import json
import shutil
import hashlib
import argparse
import subprocess
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup  # noqa: E402 -- the stdlib only: the studio's .env
import library  # noqa: E402
from film import HOME, KIT, Film, _write_json, home_rel, modules  # noqa: E402

SETTING = "STUDIO_EPISODE_CARRY"
START = ("library", "start")  # in the new film: the last episode as it was, read-only
CODE = ("film.js", "score.json", "words.json")  # carried as they are (words.json: since 2026-11-01)
SEEN = (
    "film.js",
    "words.json",
    "vo.json",
    "score.json",
    "sfx.json",
    "paint.json",
)  # library/start/
VO_KEEP = ("voice", "style", "language", "cast")  # what of vo.json is the series', not the story
PAINT_KEEP = ("style",)
# a string in film.js that reads as words on screen: a few words, not a key or a colour
WORDS = re.compile(r"""(['"`])((?:(?!\1)[^\\\n]|\\.){12,200})\1""")
CODEISH = re.compile(r"\d+px|\b(?:rgba?|hsla?)\(|#[0-9a-fA-F]{3,8}\b|\$\{|=>|\bfunction\b")


def setting():
    return (backup.setting(SETTING) or os.environ.get(SETTING, "")).strip()


def enabled(project):
    """Whether this project's episodes start from their last one's."""
    pid = (project or {}).get("id")
    on = setting()
    if not pid or on.lower() in ("", "off", "0", "no"):
        return False
    return on.lower() == "all" or pid in {x.strip() for x in on.split(",")}


def source(film):
    """The project's finished episode made last, other than this one: a Film, or None."""
    rec = film.record()
    lib = library.lib_of(rec)
    if not lib or not lib[1]:
        return None
    best = None
    for fid in library.load(lib)["films"]:
        f = Film.open(fid)
        if f is None or f.id == film.id or f.state != "done":
            continue
        r = f.record()
        if (r.get("project") or {}).get("id") != lib[1]:
            continue
        if best is None or (r.get("created") or "") > (best.record().get("created") or ""):
            best = f
    return best


def _frame(rec):
    return rec.get("frame") or "16:9"


def compatible(prev, film):
    """None when film can start from prev's code, else why not (a few words)."""
    a, b = prev.record(), film.record()
    project = b.get("project") or {}
    if library.is_collection(project):
        return "a collection: its films are each their own"
    if b.get("template") or a.get("template"):
        return "a template's film"
    if prev.look != film.look:
        return "another look (%s, now %s)" % (prev.look, film.look)
    if _frame(a) != _frame(b):
        return "another frame (%s, now %s)" % (_frame(a), _frame(b))
    if a.get("people") or b.get("people"):
        return "people drawn from photos"
    if ("captions" in prev.caps) != ("captions" in film.caps):
        return "captions in one and not the other"
    if (a.get("music") == "none") != (b.get("music") == "none"):
        return "music in one and not the other"
    if prev.mode != "single" or film.mode != "single":
        return "made in scenes"
    if (a.get("narration") is False) != (b.get("narration") is False):
        return "narrated in one and not the other"
    if not set(modules(prev.caps)) <= set(modules(film.caps)):
        return "its engine modules are not this film's"
    if not os.path.exists(prev.path("film.js")):
        return "no film.js"
    return None


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _json(p):
    try:
        with open(p, encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _writable(p):
    with contextlib.suppress(OSError):
        os.chmod(p, os.stat(p).st_mode | 0o600)


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)  # copyfile, not copy2: a release's files are read-only
    _writable(dst)


def _parses(path):
    node = shutil.which("node")
    if not node:
        return True  # the check tool says so later, as for any film
    try:
        return (
            subprocess.run([node, "--check", path], capture_output=True, timeout=60).returncode == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def merge(base, ours, theirs, work):
    """Three-way merge of one file's text: (merged text, clean). ours: the series' copy, theirs:
    this release's, base: what the series' copy started from."""
    os.makedirs(work, exist_ok=True)
    paths = []
    for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
        p = os.path.join(work, name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        paths.append(p)
    try:
        r = subprocess.run(["git", "merge-file", "-p", *paths], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    if r.returncode < 0 or r.returncode > 127:
        return None, False
    return r.stdout.decode("utf-8", "replace"), r.returncode == 0


def _engine(prev, film, start):
    """The last episode's engine changes, on this film's engine copy (this release's): each file
    it changed merged three ways, base = what it started from. On the release it was made on that
    is its own copy exactly. -> what happened, for the record: {"files": [names], "how": "copied"
    | "merged" | "conflict"}, or None when it changed none."""
    changed = []
    for name in film.engine_files():
        mine, base = _read(prev.path("engine", name)), prev.engine_base(name)
        if mine is not None and base is not None and mine != base:
            changed.append((name, mine, base))
    if not changed:
        return None
    out, diff = {}, []
    for name, mine, base in changed:
        now = _read(film.path("engine", name)) or ""
        text, clean = merge(base, mine, now, film.path("temp", "merge", name))
        if not clean or text is None:
            import difflib  # noqa: PLC0415

            diff += difflib.unified_diff(
                base.splitlines(keepends=True),
                mine.splitlines(keepends=True),
                "engine/" + name + " (as it started)",
                "engine/" + name + " (as the last episode left it)",
            )
            continue
        out[name] = text
    shutil.rmtree(film.path("temp", "merge"), ignore_errors=True)
    if diff:  # one file that does not merge: none of them, so the engine stays one release's
        with open(os.path.join(start, "engine.diff"), "w", encoding="utf-8") as f:
            f.writelines(diff)
        return {"files": [n for n, _, _ in changed], "how": "conflict"}
    for name, text in out.items():
        p = film.path("engine", name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if not _parses(p):  # merged cleanly, and is not code: this release's after all
            for back in out:
                _copy(os.path.join(KIT, "sketch", back), film.path("engine", back))
            with open(os.path.join(start, "engine.diff"), "w", encoding="utf-8") as f:
                f.write("engine/%s did not parse once merged\n" % name)
            return {"files": [n for n, _, _ in changed], "how": "conflict"}
    # what this film started from, kept for engine_diff: only what Claude changes counts as its
    os.makedirs(os.path.join(start, "engine"), exist_ok=True)
    for name in film.engine_files():
        if os.path.exists(film.path("engine", name)):
            _copy(film.path("engine", name), os.path.join(start, "engine", name))
    film.update(engine_from=home_rel(os.path.join(start, "engine")))
    same = all(out[n] == mine for n, mine, _ in changed)
    return {"files": sorted(out), "how": "copied" if same else "merged"}


def _cast(prev, film):
    """Members whose last episode's copy is newer than what the library gave this film -- a
    round changed it, and rounds never reach the library: the library holds the version that
    episode started from, or the one it saved itself, or none of that name. One another episode
    changed since is the library's. -> [names] taken."""
    lib = library.lib_of(film.record())
    idx = library.load(lib) if lib else {"cast": {}}
    started = {
        c["name"]: c.get("hash") for c in (prev.record().get("library") or {}).get("cast") or []
    }
    d = prev.path("cast")
    took = []
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        name = n[:-3]
        if not n.endswith(".js") or not library.NAME.match(name):
            continue
        code = _read(os.path.join(d, n))
        if code is None:
            continue
        e = idx["cast"].get(name)
        if e and e.get("deleted"):
            continue  # its person took it out of the series
        if e and e.get("hash") == library._hash(code):
            continue  # the same
        if e and e.get("hash") != started.get(name) and e.get("film") != prev.id:
            continue  # another episode's, since: the library's is newer
        _copy(os.path.join(d, n), film.path("cast", n))
        took.append(name)
    return took


def _fonts(prev, film):
    """The faces the last episode fetched for itself (a file in its own folder), into this film's
    manifest and folder. -> [files]."""
    pm, fm = _json(prev.manifest), _json(film.manifest)
    have = {x.get("file") for x in fm.get("fonts") or [] if isinstance(x, dict)}
    added = []
    for x in pm.get("fonts") or []:
        rel = x.get("file") if isinstance(x, dict) else None
        if not rel or rel in have or ".." in rel.split("/") or os.path.isabs(rel):
            continue
        src = prev.path(*rel.split("/"))
        if not os.path.isfile(src):
            continue
        _copy(src, film.path(*rel.split("/")))
        fm.setdefault("fonts", []).append(x)
        added.append(rel)
    if added:
        _write_json(film.manifest, fm)
    return added


def _touched(film):
    """Every file a carry may write in the film's folder, relative to it."""
    out = list(CODE) + ["vo.json", "paint.json", "sketch.json"]
    for sub in ("cast", "engine"):
        d = film.path(sub)
        out += [sub + "/" + n for n in (sorted(os.listdir(d)) if os.path.isdir(d) else [])]
    return out


def _snapshot(film):
    got = {}
    for rel in _touched(film):
        with contextlib.suppress(OSError), open(film.path(*rel.split("/")), "rb") as f:
            got[rel] = f.read()
    return got


def _restore(film, got):
    """The film's folder as it was before a carry that failed: what it wrote, put back or taken
    out (the fonts it copied stay: nothing names them once the manifest is put back)."""
    for rel in _touched(film):
        p = film.path(*rel.split("/"))
        if rel not in got:
            with contextlib.suppress(OSError):
                os.remove(p)
            continue
        with open(p, "wb") as f:
            f.write(got[rel])


def wanted(film):
    """Whether carry() has anything to do for this film: an episode of a project that has it on,
    not done yet. Cheap and synchronous: make_film asks before it hops to a thread for the carry,
    because every await ahead of a film's Claude slot is time in which POST /api/films reads that
    the film has no slot yet and answers "running" for one that should wait."""
    rec = film.record()
    if rec.get(
        "localized"
    ):  # a translation (localize.py) has the original's code, never the last episode's
        return False
    return "carried" not in rec and bool(rec.get("project")) and enabled(rec.get("project"))


def carry(film):
    """Start this film from its series' last episode, once. -> its record's `carried`:
    {film, version, release, title, length, hashes, cast, fonts, engine} or {"skipped": why};
    None when it is not on for this film (not an episode, not on, already done). Never raises:
    a carry that fails half-way takes back what it copied, and the film starts as any film does."""
    rec = film.record()
    if not wanted(film):
        return None
    before = _snapshot(film)
    try:
        return _carry(film)
    except Exception as e:  # noqa: BLE001 -- the episode is made from nothing instead
        _restore(film, before)
        shutil.rmtree(film.path(*START), ignore_errors=True)
        print("film %s: not carried: %s: %s" % (film.id, type(e).__name__, e), file=sys.stderr)
        got = {"skipped": "failed: %s" % str(e)[:200]}
        film.update(carried=got, engine_from=None)
        return got


def _carry(film):
    prev = source(film)
    why = "no earlier episode" if prev is None else compatible(prev, film)
    if why:
        got = {"skipped": why}
        film.update(carried=got)
        return got
    start = film.path(*START)
    os.makedirs(start, exist_ok=True)
    for name in SEEN:
        if os.path.exists(prev.path(name)):
            _copy(prev.path(name), os.path.join(start, name))
    pr = prev.record()
    _write_json(
        os.path.join(start, "about.json"),
        {
            "film": prev.id,
            "title": pr.get("title") or pr.get("prompt", "")[:80],
            "prompt": pr.get("prompt", ""),
            "length": prev.length,
            "made": (pr.get("created") or "")[:10],
        },
    )
    hashes = {}
    for name in CODE:
        if os.path.exists(prev.path(name)):
            _copy(prev.path(name), film.path(name))
            hashes[name] = _sha(_read(film.path(name)))
    vo = _json(film.path("vo.json"))
    if vo:
        old = _json(prev.path("vo.json"))
        vo.update({k: old[k] for k in VO_KEEP if k in old})
        vo["lines"] = []
        _write_json(film.path("vo.json"), vo)
    paint = _json(film.path("paint.json"))
    if paint:
        old = _json(prev.path("paint.json"))
        paint.update({k: old[k] for k in PAINT_KEEP if old.get(k)})
        _write_json(film.path("paint.json"), paint)
    from guard import pin_paint, pin_vo  # noqa: PLC0415 -- guard imports validate, and more

    pin_vo(film)  # the person's narrator and the studio's own settings win over the last's
    pin_paint(film)
    got = {
        "film": prev.id,
        "version": int(pr.get("version") or 1),
        "release": pr.get("release"),
        "title": pr.get("title") or pr.get("prompt", "")[:80],
        "length": prev.length,
        "hashes": hashes,
        "cast": _cast(prev, film),
        "fonts": _fonts(prev, film),
        "engine": _engine(prev, film, start),
    }
    film.update(carried=got)
    return got


def carried(film):
    """Its record's `carried` when it did start from an earlier episode, else None."""
    c = film.record().get("carried") or {}
    return c if c.get("film") and not c.get("skipped") else None


def untouched(film):
    """Whether film.js is still exactly the last episode's."""
    c = carried(film)
    if not c or "film.js" not in (c.get("hashes") or {}):
        return False
    return _sha(_read(film.path("film.js"))) == c["hashes"]["film.js"]


def _strings(code):
    """The strings in code that read as words: two or more words of letters, not a font, a
    colour or a size."""
    return {
        s
        for s in (m.group(2) for m in WORDS.finditer(code or ""))
        if len(re.findall(r"[^\W\d_]{3,}", s)) >= 2 and not CODEISH.search(s)
    }


def leftovers(film):
    """Words of the last episode's own story still in film.js: strings of a few words in its
    film.js that are still here, unless two or more of the series' earlier episodes (what the
    library gave this film to read) have them too -- a title, a catchphrase, a sign-off. [str]"""
    if not carried(film):
        return []
    start = film.path(*START)
    before = _strings(
        (_read(os.path.join(start, "film.js")) or "")
        + (_read(os.path.join(start, "words.json")) or "")
    )
    now = (_read(film.path("film.js")) or "") + (_read(film.path("words.json")) or "")
    seen = {}
    for m in (film.record().get("library") or {}).get("films") or []:
        for s in _strings(_read(film.path(*m["dir"].split("/"), "film.js"))):
            seen[s] = seen.get(s, 0) + 1
    return sorted(s for s in before if s in now and seen.get(s, 0) < 2)[:12]


def note(film):
    """What the first message says about where this film starts ("" when it starts empty)."""
    c = carried(film)
    if not c:
        return ""
    n = film.asked
    eng = c.get("engine") or {}
    out = [
        'This episode starts from the last one\'s code: film.js and score.json are those of "%s" '
        "(%d s), already in this folder. Read film.js first. Keep what makes the series itself -- "
        "the look and its helpers, the ground and the palette, the type, the camera's habits, how "
        "the characters are drawn, the opening and the end card, the music -- and replace the "
        "story: every scene, every cue and every word on screen is this episode's own, written "
        "for this prompt and this length (%d s). Change it with Edit, part by part; do not write "
        "it again from nothing, and do not leave the last episode's story in it."
        % (c.get("title") or "the last episode", c.get("length") or 0, n),
        "vo.json keeps the series' voice and has no lines: write this episode's narration and "
        "record it, and hang every SK.w cue on a word of the new lines. sfx.json is this "
        "episode's to write. score.json is the series' music: fit it to this episode's length "
        "and moments.",
    ]
    if film.record().get("look") in ("painted", "collage"):
        out.append(
            "paint.json keeps the series' painting style and no pictures: paint what this "
            "episode shows (the last episode's list is in library/start/paint.json)."
        )
    if eng.get("how") in ("copied", "merged"):
        out.append(
            "engine/ carries the series' own changes to the engine (%s), %s."
            % (
                ", ".join(eng.get("files") or []),
                "as the last episode left them"
                if eng["how"] == "copied"
                else "merged onto today's engine",
            )
        )
    elif eng.get("how") == "conflict":
        out.append(
            "The last episode changed its engine (%s), and those changes do not fit today's "
            "engine: engine/ is today's, and what they were is in library/start/engine.diff. "
            "Make them again in engine/ only if film.js needs them (check will say)."
            % ", ".join(eng.get("files") or [])
        )
    out.append(
        "The last episode as it was, to read: library/start/ (film.js, vo.json with its "
        "narration, score.json, sfx.json, paint.json, about.json)."
    )
    return "\n\n".join(out)


# a carried film longer than agent.LONG_S: the same rule as LONG_FILM, for a film.js that exists
LONG = (
    "\n\nThis is a long film, so work in parts: change film.js a few scenes at a time (Edit), "
    "and check each batch -- never the whole picture in one reply. A reply that runs for many "
    "minutes is cut off and lost. Let the narration breathe too: a short pause (half a second to "
    "a second) between its sections."
)
# the one turn for what is left of the last episode's story (agent.episode_leftovers)
LEFTOVERS = (
    "film.js still has words of the last episode's story: %s. Replace each with this episode's, "
    "or take it out -- unless it is the series' own (its title, a catchphrase, a sign-off), which "
    "stays. Then call check, and stop with one sentence."
)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", metavar="ID", required=True, help="what this film would start from")
    a = ap.parse_args()
    f = Film.open(a.plan)
    if f is None:
        sys.exit("no film %s under %s" % (a.plan, HOME))
    p = source(f)
    print(
        "on for its project: %s (%s=%r)" % (enabled(f.record().get("project")), SETTING, setting())
    )
    if p is None:
        print("no earlier episode to start from")
        sys.exit(0)
    why = compatible(p, f)
    print("last episode: %s %r" % (p.id, p.record().get("title")))
    print("would start from it" if not why else "would not: %s" % why)
    changed = [
        n for n in f.engine_files() if _read(p.path("engine", n)) not in (None, p.engine_base(n))
    ]
    print("its engine changes: %s" % (", ".join(changed) or "none"))
