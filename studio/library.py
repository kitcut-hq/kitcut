"""A person's library: what their films made, for their next films to bring back.

    STUDIO_HOME\\library\\<sha256(client)[:20]>\\
        index.json                     {"cast": {name: member}, "films": [film ids, newest first]}
        cast\\<name>\\v1.js v2.js ...   each kept version of a cast member (the last KEEP)
        cast\\<name>\\thumb.png         its latest version drawn alone
        cast.png                        every member on one sheet, named
        films\\<film id>.jpg            a small poster of each film in the memory
        .lock                           held while the index or a version is written: two
                                        servers may share the home during a ship (_lock)

A cast member is a file a film wrote in its cast/ folder, `SK.cast.<name> = {about, draw(x, y,
o)}`: a character, a place or a prop the person may want again. Every new film of theirs gets
(seed), before Claude starts:

    cast/<name>.js                 the latest version of each member: loaded before film.js
                                   (sketch-render), and the film's own to use, change or ignore
    library/cast.png               the members, drawn
    library/films/<n>-<slug>/      their last few films, read-only: film.js, vo.json, score.json,
                                   sfx.json, paint.json, poster.jpg, about.json

and note() tells Claude what is there, in the first message. Whether to bring anything back is
Claude's call. After a film finishes, keep() takes in what it made: a member that is new, or
changed since the film got it, becomes a new version; a failed or cancelled film keeps nothing.

Only signed-in people have a library -- a workspace's, in fact (the site's `o:<id>` clients; a
person's personal workspace was `u:<id>` before workspaces, and clients.py treats the two as one):
a visitor known only by an address could share one with a stranger. The folder is named after the
workspace (dir_of), and a personal one's old folder is moved to it the first time it is used.

A project on the site (a series, a channel) has a library of its own, inside its person's:

    STUDIO_HOME\\library\\<sha256(client)[:20]>\\<project id>\\
        index.json cast\\ cast.png films\\      as above, for the project's episodes only
        pictures\\<name>.png|jpg|webp           what the person put in the project: a logo,
        pictures\\<name>.thumb.png              character art... every episode gets them as
                                               inputs/pic_<name>.*, SK.image('pic_<name>'), unless
                                               the person chose "this episode only" at upload: that
                                               one seeds its next episode and is then gone, so a
                                               later episode needs a picture of its own (once).
                                               Each may carry a role (PICTURE_ROLES): what the
                                               person said it is for
        voice\\<key>.wav|mp3                    approved voice lines: recordings of narration
                                               lines its person approved by ear; every episode
                                               gets them in audio/vo/approved/, and a line with
                                               the same words and voice plays one (sketch-vo.py)
        actors\\<name>\\pack.json atlas-0.webp   actor packs (scripts/actor-pack.py), put in by hand
            check.jpg                          (studio/actor_put.py): every episode gets each in
                                               actors/<name>/, the manifest's "actors" and the
                                               "actors" capability (_seed_actors)
        canon.json                              the episode log, one entry per finished episode
                                               (studio/canon.py): every episode reads the whole
                                               of it (canon_note), not only the last MEMORY
        clashed\\<name>\\<film id>.js              an episode's copy of a member another episode
                                               changed while it was made, which did not merge
                                               (_keep): the next episodes are told to fold it in,
                                               and it goes once one that was told saves <name>

An episode seeds from and keeps into its project's library, never the person's own; a film outside
projects, the other way round. A library is named (client, project), project None for the
person's own; a bare client names that one too.
"""

import os
import re
import json
import shutil
import hashlib
import threading
import contextlib
import difflib
from datetime import datetime

import sys
import subprocess

import brandkit
import clients
import locks
import stylekit
from film import (
    CAST_USE,
    HOME,
    KIT,
    PROJECT_ID,
    PROJECT_KEEPS,
    VO_PINNED,
    Film,
    _write_json,
    modules,
    paint_kinds,
)

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _sketch  # noqa: E402

ROOT = os.path.join(HOME, "library")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
KEEP = 5  # versions of a member kept
SEEDED = 24  # members a film starts with (the most recently used)
MEMORY = 5  # earlier films a film may look at
LISTED = 20  # film ids the index remembers
MAX_BYTES = 64 * 1024  # one member's code
FILES = ("film.js", "vo.json", "score.json", "sfx.json", "sounds.json", "paint.json")
PICTURES = 9  # a project's pictures: every review render carries them all
PICTURE_EXT = ("png", "jpg", "webp")
# what a picture is for, as its person said (the same three on the site's Pictures tab, beside a
# film's attachments and in the MCP): no role is the old way, Claude reads it and decides
PICTURE_ROLES = _sketch.ROLES
ROLE_NOTE = {
    "show": "show it as it is (SK.image); never repaint it, never a painting's ref",
    "scene": (
        "what a place has: Read it, and write two or three of the things in it (a chair, three "
        "windows, palm trees) plainly into the prompt of the paintings of that place, no fine "
        "detail; never on screen, never a ref (a photo as a ref pulls a painting towards a photo)"
    ),
    "style": (
        "how we draw this: a drawn example of one kind of thing; every painting that shows that "
        'thing is painted with "ref" naming it (beside any cast_ ref, MAX_REFS in all); never on '
        "screen unless the prompt asks"
    ),
}
# a film that paints nothing: the roles steer what Claude draws in code
ROLE_NOTE_DRAWN = ROLE_NOTE | {
    "scene": (
        "what a place has: Read it, and draw two or three of the things in it plainly where "
        "that place is; never on screen"
    ),
    "style": (
        "how we draw this: draw that kind of thing in code the way this picture does; never on "
        "screen unless the prompt asks"
    ),
}


def role_line(role, painted=True):
    """A picture's role, said to Claude ("" for a picture without one)."""
    notes = ROLE_NOTE if painted else ROLE_NOTE_DRAWN
    return " -- %s: %s" % (role, notes[role]) if role in notes else ""


def write_roles(film, roles):
    """The film's inputs/roles.json, {picture name: role}, merged with what is there: the
    painter takes an attached picture as a ref only when its role is "style" (_sketch)."""
    if not roles:
        return
    p = film.path("inputs", "roles.json")
    got = _sketch.picture_roles(film.dir) | roles
    os.makedirs(os.path.dirname(p), exist_ok=True)
    _write_json(p, got)
VOICE_LINES = 12  # a project's approved voice lines: every episode carries them all
VOICE_KEY = re.compile(r"^[0-9a-f]{12}$")
CLASHED = "clashed"  # a project library's members that did not merge: <name>/<film id>.js
_LOCKS = {}  # a library's folder -> the lock its index is changed under
_LOCKS_LOCK = threading.Lock()


def owner(client, project=None):
    """Which library a film or a request uses: (workspace, project) for a signed-in person or a
    workspace -- one owner either way (clients.py: "u:<id>" is the personal workspace "o:<id>") --
    project None for its own; None for anyone else, or a project id that is not one."""
    if not clients.signed_in(client):
        return None
    if project is not None and not (isinstance(project, str) and PROJECT_ID.match(project)):
        return None
    return (clients.canon(client), project)


def lib_of(rec):
    """The library of the film with this record: its project's, or its person's."""
    return owner(rec.get("client"), (rec.get("project") or {}).get("id"))


def _lib(lib):
    return (lib, None) if isinstance(lib, str) else lib


def _name(client):
    return hashlib.sha256(client.encode()).hexdigest()[:20]


def dir_of(lib):
    client, project = _lib(lib)
    client = clients.canon(client)
    d = os.path.join(ROOT, _name(client))
    if not os.path.isdir(d):
        d = _adopt(client, d)
    return os.path.join(d, project) if project else d


def _adopt(client, d):
    """A personal workspace's library from before workspaces, kept under the person's name
    ("u:<id>"): moved to the workspace's, once. A rename on one disk: two servers racing both end
    with it in place. Where it cannot move yet (a file open in it, on Windows), the old folder is
    used as it is this time, so nothing is split between two."""
    old = clients.legacy(client)
    src = old and os.path.join(ROOT, _name(old))
    if not (src and os.path.isdir(src)):
        return d
    try:
        os.rename(src, d)
    except OSError:
        return d if os.path.isdir(d) else src
    return d


@contextlib.contextmanager
def _lock(lib):
    """The library's own lock: a film keeping its cast and the person removing a member (or a
    picture) at the same moment must not each write an index the other has not seen, nor two
    films both write cast/<name>/v3.js. Two locks, taken in this order: a thread lock (this
    process's films queue on it without polling), then <library>/.lock (locks.py), because during
    a ship two servers run on one home (peers.py, KI-031) and either may be keeping a film of the
    same person's. Not reentrant."""
    d = dir_of(lib)
    with _LOCKS_LOCK:
        mine = _LOCKS.setdefault(d, threading.Lock())
    with mine:
        os.makedirs(d, exist_ok=True)
        with locks.locked(os.path.join(d, ".lock")):
            yield


def _hash(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _about(code):
    m = re.search(r"\babout\s*:\s*(['\"`])(.*?)\1", code, re.S)
    return " ".join(m.group(2).split())[:200] if m else ""


def _kind(code):
    """'place' for a member that says it is one (kind: 'place': a set the films return to), else
    None: a character or a thing."""
    return "place" if re.search(r"\bkind\s*:\s*(['\"`])place\1", code or "") else None


def load(lib):
    """The library's index. A person's that has never been written starts from their finished
    films outside projects (made before there were libraries); a project's starts empty."""
    client, project = _lib(lib)
    try:
        with open(os.path.join(dir_of(lib), "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
    except (OSError, ValueError):
        idx = {}
    idx.setdefault("cast", {})
    idx.setdefault("pictures", {})
    idx.setdefault("voice", {})
    idx.setdefault("actors", {})
    if "films" not in idx:
        idx["films"] = []
        for f in [] if project else Film.all():
            rec = f.record()
            if (
                clients.same(rec.get("client"), client)
                and not rec.get("project")
                and f.state == "done"
            ):
                idx["films"].append(f.id)
        idx["films"] = idx["films"][:LISTED]
    return idx


def _save(lib, idx):
    os.makedirs(dir_of(lib), exist_ok=True)
    _write_json(os.path.join(dir_of(lib), "index.json"), idx)


def used(film):
    """The members film.js draws, by name, and the ones those draw in turn."""

    def named(code):
        return {a or b for a, b in CAST_USE.findall(code or "")}

    names = named(_read(film.path("film.js")))
    for n in list(names):  # a member's own file names it too: that is not a use
        names |= named(_read(film.path("cast", n + ".js"))) - {n}
    return sorted(names)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:32] or "film"


def _poster(lib, f):
    """A small poster of an earlier film (cached in the library), or None."""
    out = os.path.join(dir_of(lib), "films", f.id + ".jpg")
    if os.path.exists(out):
        return out
    src = f.path("outputs", "film_poster.png")
    if not os.path.exists(src):
        return None
    try:
        from PIL import Image

        os.makedirs(os.path.dirname(out), exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((960, 540))
            im.save(out, quality=82)
        return out
    except (OSError, ValueError):
        return None


def _bring_account_cast(lib):
    """A project that asked for it starts with its person's own cast (from their films outside
    projects): each live member's latest version joins the project's, once. Under the lock."""
    idx = load(lib)
    if idx.get("imported"):
        return
    mine = (lib[0], None)
    theirs, src = load(mine), dir_of(mine)
    now = datetime.now().isoformat(timespec="seconds")
    for n, e in theirs["cast"].items():
        code = os.path.join(src, "cast", n, "v%d.js" % e.get("version", 0))
        if e.get("deleted") or n in idx["cast"] or not os.path.exists(code):
            continue
        md = os.path.join(dir_of(lib), "cast", n)
        os.makedirs(md, exist_ok=True)
        shutil.copyfile(code, os.path.join(md, "v1.js"))
        thumb = os.path.join(src, "cast", n, "thumb.png")
        if os.path.exists(thumb):
            shutil.copyfile(thumb, os.path.join(md, "thumb.png"))
        idx["cast"][n] = {
            "version": 1,
            "hash": e["hash"],
            "about": e.get("about", ""),
            "kind": e.get("kind"),
            "films": [],
            "created": now,
            "updated": now,
            "from_film": e.get("from_film"),
            "thumb": os.path.exists(thumb),
            "brought": True,  # from the person's own cast
        }
    idx["imported"] = now
    _save(lib, idx)
    _contact(lib, idx)


def seed(film):
    """Give a new film its library (its project's, or its person's): the cast in cast/, the
    sheet and earlier films in library/, a project's pictures in inputs/. What it got goes into
    the film's record (library), for note() and keep(). Returns that, or None when the film's
    client has no library."""
    rec = film.record()
    lib = lib_of(rec)
    if not lib or not os.path.isdir(film.path("cast")):
        return None
    if lib[1] and (rec.get("project") or {}).get("from_account_cast"):
        with _lock(lib):
            _bring_account_cast(lib)
    idx = load(lib)
    d = dir_of(lib)
    members = sorted(
        ((n, e) for n, e in idx["cast"].items() if not e.get("deleted")),
        key=lambda x: x[1].get("last_used") or x[1].get("updated") or "",
        reverse=True,
    )[:SEEDED]
    cast = []
    for n, e in members:
        src = os.path.join(d, "cast", n, "v%d.js" % e["version"])
        if not os.path.exists(src):
            continue
        shutil.copyfile(src, film.path("cast", n + ".js"))
        cast.append(
            {
                "name": n,
                "about": e.get("about", ""),
                **({"kind": e["kind"]} if e.get("kind") else {}),
                "hash": e["hash"],
                "films": len(e.get("films") or []),
                "last_used": e.get("last_used") or e.get("updated"),
                # brought in from the person's own cast and not drawn by an episode yet: not the
                # series' own, whatever note() would otherwise call it
                **({"brought": True} if e.get("brought") and not e.get("films") else {}),
            }
        )
    into = film.path("library")
    if cast and os.path.exists(os.path.join(d, "cast.png")):
        os.makedirs(into, exist_ok=True)
        shutil.copyfile(os.path.join(d, "cast.png"), os.path.join(into, "cast.png"))
    memory = []
    for fid in idx["films"]:
        if len(memory) >= MEMORY:
            break
        f = Film.open(fid)
        if f is None or f.id == film.id or f.state != "done":
            continue
        rec = f.record()
        title = rec.get("title") or rec.get("prompt") or ""
        sub = "%d-%s" % (len(memory) + 1, _slug(title))
        out = os.path.join(into, "films", sub)
        os.makedirs(out, exist_ok=True)
        for name in FILES:
            if os.path.exists(f.path(name)):
                shutil.copyfile(f.path(name), os.path.join(out, name))
        poster = _poster(lib, f)
        if poster:
            shutil.copyfile(poster, os.path.join(out, "poster.jpg"))
        about = {
            "title": " ".join(title.split())[:80],
            "prompt": rec.get("prompt", ""),
            "made": (rec.get("created") or "")[:10],
            "length": rec.get("length"),
            "look": rec.get("look"),
            "direction": rec.get("direction") or f.direction(),
        }
        if is_collection(film.record().get("project")) and "words" not in about["direction"]:
            # a collection tells its films apart by more than a series keeps: what a film made
            # before those were recorded chose is read from its own files
            about["direction"] = f.direction() | about["direction"]
        _write_json(os.path.join(out, "about.json"), about)
        memory.append({"dir": "library/films/" + sub, "poster": bool(poster)} | about)
    got = {"cast": cast, "films": memory}
    if lib[1]:
        got["pictures"] = _seed_pictures(film, lib, idx)
        got["painted"] = _seed_painted(film, lib, idx)
        got["voice"] = _seed_voice(film, lib, idx)
        try:  # the project's brand (brandkit.py): its faces, logos and brand.js
            got["brand"] = brandkit.seed(film, lib)
        except Exception as e:  # noqa: BLE001 -- an episode is made without it rather than not
            print("film %s: brand not seeded: %s" % (film.id, e), file=sys.stderr, flush=True)
            got["brand"] = None
        # after the brand: style.js goes in front of brand.js, so the brand wins where both speak
        try:  # the project's style (stylekit.py): its picture, faces, style.js, paint route
            got["style"] = stylekit.seed(film, lib)
        except Exception as e:  # noqa: BLE001 -- an episode is made without it rather than not
            print("film %s: style not seeded: %s" % (film.id, e), file=sys.stderr, flush=True)
            got["style"] = None
        got["sounds"] = _seed_sounds(film, lib)
        try:  # the project's actors (actor packs): the film is made without them rather than not
            got["actors"] = _seed_actors(film, lib, idx)
        except Exception as e:  # noqa: BLE001
            print("film %s: actors not seeded: %s" % (film.id, e), file=sys.stderr, flush=True)
            got["actors"] = []
        got["clashed"] = _seed_clashed(film, lib, idx)
    film.update(library=got)
    return got


def clashed_of(lib, idx=None):
    """A project's members that two episodes changed at once and that did not merge, for a live
    member: [{name, film, path}], oldest first."""
    idx = idx or load(lib)
    d = os.path.join(dir_of(lib), CLASHED)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        e = idx["cast"].get(name)
        if not NAME.match(name) or not e or e.get("deleted"):
            continue
        for fn in sorted(os.listdir(os.path.join(d, name))):
            if fn.endswith(".js"):
                out.append({"name": name, "film": fn[:-3], "path": os.path.join(d, name, fn)})
    return out


def _seed_clashed(film, lib, idx):
    """Each clashed copy into the episode's library/clashed/<name>-<film>.js, to read and fold
    into its cast/<name>.js. [{name, film, file}]."""
    out = []
    for c in clashed_of(lib, idx):
        rel = "library/clashed/%s-%s.js" % (c["name"], c["film"])
        os.makedirs(film.path("library", "clashed"), exist_ok=True)
        shutil.copyfile(c["path"], film.path(*rel.split("/")))
        out.append({"name": c["name"], "film": c["film"], "file": rel})
    return out


# ---------------------------------------------------------------- a series' sounds
SOUNDS = "sounds.json"  # a project's kept sounds and themes: {"sounds": {}, "themes": {}}
SOUND_KINDS = ("sounds", "themes")


def sounds_of(lib):
    """A project's kept sounds: {"sounds": {name: entry}, "themes": {name: entry}}, each entry
    the film's own {about, cue | events} plus what the library knows (films, updated, hash)."""
    try:
        with open(os.path.join(dir_of(lib), SOUNDS), encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        got = {}
    got = got if isinstance(got, dict) else {}
    return {k: got.get(k) if isinstance(got.get(k), dict) else {} for k in SOUND_KINDS}


def _sound_hash(e):
    own = {k: e.get(k) for k in ("about", "cue", "events") if k in e}
    return hashlib.sha256(json.dumps(own, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _film_sounds(film):
    try:
        with open(film.path(SOUNDS), encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return {k: {} for k in SOUND_KINDS}
    got = got if isinstance(got, dict) else {}
    return {
        k: {n: e for n, e in (got.get(k) or {}).items() if isinstance(e, dict)}
        if isinstance(got.get(k), dict)
        else {}
        for k in SOUND_KINDS
    }


def _seed_sounds(film, lib):
    """A project's kept sounds into the episode's sounds.json, the film's own to play by name,
    change or add to. {"sounds": {name: hash}, "themes": {name: hash}} of what it got."""
    kept = sounds_of(lib)
    if not any(kept.values()):
        return {k: {} for k in SOUND_KINDS}
    own = {
        k: {n: {x: e[x] for x in ("about", "cue", "events") if x in e} for n, e in kept[k].items()}
        for k in SOUND_KINDS
    }
    _write_json(film.path(SOUNDS), own)
    return {k: {n: _sound_hash(e) for n, e in own[k].items()} for k in SOUND_KINDS}


def _keep_sounds(film, lib, now):
    """The episode's new and changed sounds and themes into its project's: a sound saved only
    over the one the film started from, as a cast member is (_keep). Returns (the names saved,
    the names left as the library had them because another episode changed them meanwhile)."""
    if not os.path.exists(film.path(SOUNDS)):
        return [], []
    had = (film.record().get("library") or {}).get("sounds") or {}
    mine, kept = _film_sounds(film), sounds_of(lib)
    saved, clashed = [], []
    for k in SOUND_KINDS:
        for n, e in mine[k].items():
            if not NAME.match(n):
                continue
            h, old = _sound_hash(e), kept[k].get(n)
            if old and old.get("hash") == h:
                old["films"] = ([film.id] + [x for x in old.get("films") or [] if x != film.id])[
                    :LISTED
                ]
                continue
            if old and old.get("hash") != (had.get(k) or {}).get(n):
                clashed.append(n)  # moved on in the library since this film got it: the newer
                continue  # stays, and the film's summary says so
            kept[k][n] = {
                **{x: e[x] for x in ("about", "cue", "events") if x in e},
                "hash": h,
                "films": [film.id] + [x for x in (old or {}).get("films") or [] if x != film.id],
                "created": (old or {}).get("created") or now,
                "updated": now,
                "from_film": film.id,
            }
            saved.append(n)
    _write_json(os.path.join(dir_of(lib), SOUNDS), kept)
    return saved, clashed


def sounds_note(film):
    """How an episode plays its series' sounds by name, and which it has: for the first message
    and the editor of a film made in scenes. "" for a film that is not an episode, and for one
    of a collection that does not keep its music (keeps)."""
    rec = film.record()
    if "music" not in keeps(rec.get("project")):
        return ""
    got = (rec.get("library") or {}).get("sounds") or {}
    kit = _film_sounds(film)
    out = [
        "A series keeps its sounds as it keeps its cast: a sound effect or a theme its episodes "
        "share goes in sounds.json, by name, and is played from sfx.json and score.json. Kept "
        "sounds are what makes a series sound like itself: play them for the moments they were "
        "made for (the same bell, the same sad trombone, the same theme), and add one when this "
        "episode makes a sound the series should keep. sounds.json is "
        '{"sounds": {"<name>": {"about": "<what it is, when it plays>", "cue": <one sfx.json '
        'cue without t>}}, "themes": {"<name>": {"about": "...", "events": [<score.json "notes" '
        'events, beats from 0>]}}}; play a sound with {"t": 3.2, "sound": "<name>"} in sfx.json '
        "(any other key overrides the kept cue's), a theme with "
        '{"type": "theme", "theme": "<name>", "at": <beat or [beats]>} in score.json (optional '
        '"transpose", and "only": [instruments] for part of it). Names: lowercase letters, '
        "digits and _.",
    ]
    names = [
        '- %s "%s": %s' % (k[:-1], n, (e.get("about") or "")[:160])
        for k in SOUND_KINDS
        for n, e in kit[k].items()
        if n in (got.get(k) or {})
    ]
    if names:
        out.append("The series' sounds, already in sounds.json:\n" + "\n".join(names))
    return "\n".join(out)


def _seed_pictures(film, lib, idx):
    """A project's pictures into the film's inputs/, each in the manifest's images as
    pic_<name> (never a painted scene's name, nor an upload's). [{name, file, w, h, role?}]. A
    picture added "once" seeds this film and then leaves the project's library, so it never
    reaches a later episode (the person adds a fresh one for that). Their roles go into the
    film's inputs/roles.json."""
    out = []
    once = []
    for n, e in sorted(idx["pictures"].items()):
        src = os.path.join(dir_of(lib), "pictures", "%s.%s" % (n, e["ext"]))
        if not os.path.exists(src):
            continue
        os.makedirs(film.path("inputs"), exist_ok=True)
        rel = "inputs/pic_%s.%s" % (n, e["ext"])
        shutil.copyfile(src, film.path(*rel.split("/")))
        out.append({"name": "pic_" + n, "file": rel, "w": e.get("w"), "h": e.get("h")})
        if e.get("role") in PICTURE_ROLES:
            out[-1]["role"] = e["role"]
        if e.get("once"):
            once.append(n)
    if out:
        with open(film.manifest, encoding="utf-8") as f:
            m = json.load(f)
        m.setdefault("images", {}).update({p["name"]: p["file"] for p in out})
        _write_json(film.manifest, m)
        write_roles(film, {p["name"]: p["role"] for p in out if p.get("role")})
    if once:
        with _lock(lib):
            idx2 = load(lib)
            d = os.path.join(dir_of(lib), "pictures")
            for n in once:
                if idx2["pictures"].get(n, {}).get("once"):
                    del idx2["pictures"][n]
                    _remove_picture(d, n)
            _save(lib, idx2)
    return out


def keeps(project):
    """What a project's films share, of film.PROJECT_KEEPS: all of it for a series -- every project that
    does not say (no "keep" in it) -- and what it names for a collection, whose films are each
    their own in the rest. () for no project."""
    if not project:
        return ()
    if not isinstance(project.get("keep"), list):
        return PROJECT_KEEPS
    return tuple(k for k in PROJECT_KEEPS if k in project["keep"])


def is_collection(project):
    """A project whose films are each their own in something: it keeps less than a series."""
    return bool(project) and len(keeps(project)) < len(PROJECT_KEEPS)


KEPT = {"cast": "its cast", "look": "its look", "voice": "its voice", "music": "its music"}
# what a collection's film is asked to choose for itself, by what the project does not keep
OWN = {
    "look": "the look of it -- the ground and its colours, the type, the way its pictures are "
    "made, how the frame is laid out",
    "voice": "the narrator and how they speak",
    "music": "the instruments and the tempo, or no music at all",
}


def _used(m):
    """One earlier film of a collection, as what it chose: for the next to differ from."""
    dr = m.get("direction") or {}
    words = dr.get("words")
    bits = [
        "%s s, %s" % (m.get("length"), m.get("look")),
        "ground %s" % dr["ground"] if dr.get("ground") else None,
        "paper %s" % dr["paper"] if dr.get("paper") else None,
        "accent %s" % dr["accent"] if dr.get("accent") else None,
        "type %s" % ", ".join(dr["faces"]) if dr.get("faces") else None,
        "painted as %s" % dr["paint_style"] if dr.get("paint_style") else None,
        "voice %s%s" % (dr["voice"], ' "%s"' % dr["voice_style"] if dr.get("voice_style") else "")
        if dr.get("voice")
        else None,
        "%s at %s bpm" % (", ".join(dr.get("instruments") or []), dr.get("bpm"))
        if dr.get("instruments")
        else None,
        "%d narration lines, %d words" % (dr.get("lines") or 0, words) if words else None,
        'opens "%s"' % dr["opening"] if dr.get("opening") else None,
    ]
    return '- %s: "%s" (%s)' % (m["dir"], m.get("title"), "; ".join(b for b in bits if b))


def _own_note(kept, memory):
    """A collection's last word: what its films share, and that the rest is this film's own."""
    share = [KEPT[k] for k in kept]
    own = [OWN[k] for k in ("look", "voice", "music") if k not in kept]
    own.append("the pace, how it opens, the order it tells things in and how it ends")
    if share:
        both = ", ".join(share[:-1]) + " and " + share[-1] if len(share) > 1 else share[0]
        head = (
            "This project is a collection, not a series: its films share %s, and what its "
            "brief asks for." % both
        )
    else:
        head = (
            "This project is a collection, not a series: its films share only what its brief "
            "asks for."
        )
    if not memory:
        return head + " Everything else is each film's own: choose it for this prompt alone."
    return (
        head + " Everything else is this film's own, and the films above are listed so that "
        "it does not repeat them. Choose for this prompt: %s. Where the films above agree with "
        "each other, do not make it one more of the same: someone who saw them side by side, or "
        "heard them one after another, should take this one for a different film. Keep to one "
        "of their choices only where the brief or this prompt asks for it." % "; ".join(own)
    )


def note(film):
    """What the film has from its library, for the first message ("" when nothing). An
    episode also hears its project's name and brief, in its person's words. A project that
    keeps less than a series does (keeps) is a collection: its film hears what the earlier ones
    chose so as to differ from them, not to match."""
    rec = film.record()
    got = rec.get("library") or {}
    project = rec.get("project") or {}
    kept, collection = keeps(project), is_collection(project)
    cast, memory = got.get("cast") or [], got.get("films") or []
    pics = got.get("pictures") or []
    voice = got.get("voice") or []
    if not cast and not memory and not project:
        return ""
    out = []
    if project:
        out.append(
            'This film is %s the project "%s".'
            % ("one of the films of" if collection else "an episode of", project.get("name"))
        )
        if (project.get("brief") or "").strip():
            out.append("Its brief, from the person who runs it:\n" + project["brief"].strip())
    if project and (got.get("brand") or {}).get("name"):
        mark = brandkit.note(film, lib_of(rec))
        if mark:
            out += ["", mark]
    if project and got.get("style"):
        look = stylekit.note(film, lib_of(rec))
        if look:
            out += ["", look]
    if pics:
        out += [
            "" if out else None,
            "The project's pictures (Read one to see it; on screen: "
            "SK.image('<name>', x, y, w)%s)%s:"
            % (
                # every painter takes a reference now, Muse too (sketch-paint.py UNLISTED_REFS)
                '; a painting made from one: "ref": "<name>" in paint.json'
                if paint_kinds(film.caps)
                else "",
                ". Where its person said what one is for, that is what it is for"
                if any(p.get("role") for p in pics)
                else "",
            ),
        ]
        out += [
            "- %s (%sx%s): %s%s"
            % (
                p["name"],
                p.get("w"),
                p.get("h"),
                p["file"],
                role_line(p.get("role"), bool(paint_kinds(film.caps))),
            )
            for p in pics
        ]
    told = project and painted_note(
        film, got.get("painted") or [], collection and "cast" not in kept
    )
    if told:
        out += ["" if out else None, told]
    told = project and named_note(film)
    if told:
        out += ["" if out else None, told]
    if got.get("actors"):
        out += ["" if out else None, actors_note(got["actors"])]
    if voice:
        out += [
            "" if out else None,
            "The project's approved voice lines: recordings its person listened to and approved. "
            "A vo.json line with exactly these words, in the same voice and model, plays that "
            "recording and is never recorded again: the series' greeting and sign-off sound the "
            "same in every episode, and a name is said the way they approved it. Use each word "
            "for word, as a line of its own, where it fits (what follows it goes in the next "
            "line):",
        ]
        out += [
            '- "%s" (%s, %s, %.1f s)'
            % (v["text"], v.get("voice"), v.get("model"), v.get("dur") or 0)
            for v in voice
        ]

    def member(c):
        n = c.get("films") or 0
        seen = "in %d film%s" % (n, "" if n == 1 else "s") if n else "not used yet"
        return "- %s%s: %s (%s)" % (
            c["name"],
            " (a place)" if c.get("kind") == "place" else "",
            c.get("about") or "no description",
            seen,
        )

    own = [c for c in cast if not (project and c.get("brought"))]
    brought = [c for c in cast if project and c.get("brought")]
    if own:
        out += [
            "" if out else None,
            "This %s (already loaded from cast/: use any as SK.cast.<name>, change it, or leave "
            "it out; Read library/cast.png to see them)%s:"
            % (
                "project's cast, from its earlier episodes"
                if project
                else "person's cast, from their earlier films",
                "; a collection's films do not share a cast, so bring one back only when this "
                "film is about that very thing"
                if collection and "cast" not in kept
                else "",
            ),
        ]
        out += [member(c) for c in own]
    if brought:
        out += [
            "" if out else None,
            "Brought in from the person's films outside projects when the project was made "
            "(also in cast/; no episode has drawn them yet). They come from other films of "
            "theirs, not from this series, so use one only when this episode is about it:",
        ]
        out += [member(c) for c in brought]
    clashed = got.get("clashed") or []
    if clashed:
        out += [
            "" if out else None,
            "Two episodes changed these members at the same time, and the changes did not merge: "
            "cast/ has the series' version, and the other episode's copy is beside it, to read. "
            "If this episode uses the member, fold what that copy added (a pose, an option) into "
            "cast/<name>.js, keeping what the series' version has:",
        ]
        out += ["- %s: %s" % (c["name"], c["file"]) for c in clashed]
    if memory and collection:
        out += [
            "" if out else None,
            "The project's earlier films, newest first, and what each chose (Read "
            "<folder>/poster.jpg to see one; they are here to be told apart from, not to be "
            "followed):",
        ]
        out += [_used(m) for m in memory]
    elif memory:
        out += [
            "" if out else None,
            "%s, newest first (Read <folder>/about.json, film.js, vo.json, score.json or "
            "poster.jpg for more):"
            % ("Its earlier episodes" if project else "Their earlier films"),
        ]
        for m in memory:
            dr = m.get("direction") or {}
            bits = [
                "%s s, %s" % (m.get("length"), m.get("look")),
                "ground %s" % dr["ground"] if dr.get("ground") else None,
                "painted as %s" % dr["paint_style"] if dr.get("paint_style") else None,
                "voice %s%s"
                % (dr["voice"], ' "%s"' % dr["voice_style"] if dr.get("voice_style") else "")
                if dr.get("voice")
                else None,
                "%s at %s bpm" % (", ".join(dr.get("instruments") or []), dr.get("bpm"))
                if dr.get("instruments")
                else None,
                "cast %s" % ", ".join(dr["cast"]) if dr.get("cast") else None,
            ]
            out.append(
                '- %s: "%s" (%s)' % (m["dir"], m.get("title"), "; ".join(b for b in bits if b))
            )
    lib = lib_of(rec)
    log = canon_note(canon_of(lib), collection) if project and lib else ""
    if log:
        out += ["", log]
    if project and lib and "music" in kept:  # kept sounds are what a series sounds like
        out += ["", sounds_note(film)]
    if collection:
        out += ["", _own_note(kept, memory)]
    elif project and memory:
        out += [
            "",
            "An episode belongs with the others: keep what makes them one series (the cast, the "
            "look, the voice, the music), unless the prompt asks for something new.",
        ]
    elif project:
        out += [
            "",
            "It is the project's first episode: what you choose now is what its next episodes "
            "will have to keep.",
        ]
    else:
        out += [
            "",
            "If this film continues one of theirs, keep what makes it the same series (the cast, "
            "the look, the voice, the music); if it is a new idea, make it its own film.",
        ]
    return "\n".join(x for x in out if x is not None)


# ---------------------------------------------------------------- the episode log
CANON = "canon.json"  # a project's episode log (studio/canon.py writes it)
CANON_NOTE_MAX = 16000  # characters of log an episode is given; older entries shrink past it
CANON_WHOLE = 8  # the newest entries, never shrunk


def canon_of(lib):
    """A project's episode log, oldest first: [entry] (studio/canon.py), [] when there is none."""
    if not lib:
        return []
    try:
        with open(os.path.join(dir_of(lib), CANON), encoding="utf-8") as f:
            got = json.load(f).get("episodes")
    except (OSError, ValueError, AttributeError):
        return []
    return [e for e in got or [] if isinstance(e, dict) and e.get("film")]


def put_canon(lib, entry):
    """Write one episode's entry into its project's log, in its film's place (a film finished
    again replaces its own), the log kept oldest first by when each film was made."""
    with _lock(lib):
        got = [e for e in canon_of(lib) if e.get("film") != entry["film"]] + [entry]
        got.sort(key=lambda e: (e.get("made") or "", e["film"]))
        _write_json(os.path.join(dir_of(lib), CANON), {"episodes": got})
    return got


def _canon_line(i, e, short=False):
    head = '%d. "%s" (%s, %s s): %s' % (
        i,
        e.get("title") or "untitled",
        (e.get("made") or "")[:10],
        e.get("length") or "?",
        e.get("story") or "",
    )
    bits = [
        "catchphrases: %s" % "; ".join('"%s"' % c for c in e["catchphrases"])
        if e.get("catchphrases")
        else None,
        None if short or not e.get("twist") else "twist: %s" % e["twist"],
        None if short or not e.get("fact") else "true fact: %s" % e["fact"],
        None if short or not e.get("new") else "new: %s" % "; ".join(e["new"]),
        None
        if short or not e.get("callbacks")
        else "could come back: %s" % "; ".join(e["callbacks"]),
    ]
    return head + "".join("\n   %s" % b for b in bits if b)


def canon_note(entries, collection=False):
    """The log as an episode reads it: every episode, oldest first. Past CANON_NOTE_MAX the
    oldest shrink to their story and catchphrases, so a long series still fits. collection: the
    films are not one story (is_collection), so the log only says what has been told."""
    if not entries:
        return ""
    lines = [_canon_line(i, e) for i, e in enumerate(entries, 1)]

    def over():
        return sum(len(x) + 1 for x in lines) > CANON_NOTE_MAX

    older = entries[: max(0, len(entries) - CANON_WHOLE)]  # the newest always stay whole
    for k, e in enumerate(older):  # the oldest first: story and catchphrases only
        if not over():
            break
        lines[k] = _canon_line(k + 1, e, short=True)
    for k, e in enumerate(older):  # then their title only
        if not over():
            break
        lines[k] = '%d. "%s"' % (k + 1, e.get("title") or "untitled")
    gone = 0
    while over() and len(lines) > CANON_WHOLE:  # then not at all
        lines.pop(0)
        gone += 1
    if gone:
        lines.insert(0, "(episodes 1-%d: too many to list)" % gone)
    if collection:
        return (
            "What the project's films have told so far, in order (its log), so that this one "
            "does not tell one of them again; a fact one of them stated may be stated here:\n"
            + "\n".join(lines)
        )
    return (
        "The series so far, every episode in order (the project's episode log). Keep to what "
        "happened: don't reuse a twist, a fact or an episode's own catchphrase unless the brief "
        "says it recurs, and where it fits, bring something back as a call-back:\n"
        + "\n".join(lines)
    )


# ---------------------------------------------------------------- after the film
def drop_unused(film):
    """Before the final render: the members the film got from the library and neither changed
    nor names anywhere (film.js, the other members) move out of cast/ into temp/, so the film's
    files carry only its own cast. Returns their names."""
    had = {c["name"]: c["hash"] for c in (film.record().get("library") or {}).get("cast") or []}
    d = film.path("cast")
    if not had or not os.path.isdir(d):
        return []
    code = {n[:-3]: _read(os.path.join(d, n)) or "" for n in os.listdir(d) if n.endswith(".js")}
    gone = []
    for n in sorted(code):
        if had.get(n) != _hash(code[n]):
            continue  # new, or changed by this film: its own
        others = [_read(film.path("film.js")) or ""] + [c for m, c in code.items() if m != n]
        if not any(re.search(r"\b%s\b" % re.escape(n), c) for c in others):
            os.makedirs(film.path("temp", "cast-unused"), exist_ok=True)
            os.replace(os.path.join(d, n + ".js"), film.path("temp", "cast-unused", n + ".js"))
            gone.append(n)
    return gone


def changes(film):
    """The members the film has that its person's library does not: new ones, and ones changed
    since the film got them. [{name, code, hash, about}]; [] when the film has no library."""
    rec = film.record()
    if not lib_of(rec) or not os.path.isdir(film.path("cast")):
        return []
    had = {c["name"]: c["hash"] for c in (rec.get("library") or {}).get("cast") or []}
    out = []
    for fn in sorted(os.listdir(film.path("cast"))):
        name = fn[:-3]
        if not fn.endswith(".js") or not NAME.match(name):
            continue
        code = _read(film.path("cast", fn))
        if not code or not code.strip() or len(code.encode("utf-8")) > MAX_BYTES:
            continue
        h = _hash(code)
        if had.get(name) != h:
            out.append(
                {"name": name, "code": code, "hash": h, "about": _about(code), "kind": _kind(code)}
            )
    return out


def sheet(film, names, items=()):
    """A small film that draws each member alone, for its thumbnail: nothing at i + 0.25 s, the
    member at i + 0.75 s. Written into the film's temp/; returns (manifest, times). A place is
    drawn at its origin through the camera it names (camera: [x, y, zoom]), so its thumbnail is
    the set as its films frame it; anything else stands at (0, 140) under the plain camera."""
    d = film.path("temp", "castsheet")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    cast = film.path("cast")
    if any(it.get("merged_from") for it in items):  # a merge (merges) is drawn as merged
        cast = os.path.join(d, "cast")
        shutil.copytree(film.path("cast"), cast)
        for it in items:
            if it.get("merged_from"):
                with open(os.path.join(cast, it["name"] + ".js"), "w", encoding="utf-8") as f:
                    f.write(it["code"])
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    js = (
        "SK.setGround('white');\n"
        "const NAMES = %s;\n"
        "const place = (m) => !!m && m.kind === 'place';\n"
        "const view = (m) => place(m) && Array.isArray(m.camera) && m.camera.length === 3\n"
        "  && m.camera.every(Number.isFinite) && m.camera[2] > 0 ? m.camera : [0, 0, 1];\n"
        "const KEYS = NAMES.flatMap((n, i) => {\n"
        "  const c = view(SK.cast[n]); return [[i + 0.05, c], [i + 0.95, c]]; });\n"
        "SK.film({ duration: %d, fadeOut: 0, handheld: false,\n"
        "  camera: SK.camera(KEYS.length ? KEYS : [[0, [0, 0, 1]]]), draw(t) {\n"
        "  const i = Math.floor(t), m = SK.cast[NAMES[i]];\n"
        "  if (!m || t - i < 0.5 || typeof m.draw !== 'function') return;\n"
        "  try { place(m) ? m.draw(0, 0, { t: 0 }) : m.draw(0, 140, { t: 0 }); } catch (e) {}\n"
        "} });\n" % (json.dumps(names), len(names) + 1)
    )
    with open(os.path.join(d, "film.js"), "w", encoding="utf-8") as f:
        f.write(js)
    man = {
        "title": "cast",
        "fps": 60,
        "duration": float(len(names) + 1),
        "film": "film.js",
        # a film's own fonts (web/fonts/, web-grab.py) are beside its manifest, not this one
        "fonts": [
            f | {"file": film.path(*f["file"].split("/"))}
            if os.path.exists(film.path(*f["file"].split("/")))
            else f
            for f in m.get("fonts", [])
        ],
        "cast": cast,
        # a member may draw with its film's modules (a collage film's pieces)
        **({"modules": m["modules"]} if m.get("modules") else {}),
        # and read what its head scripts set (a project's brand.js: SK.BRAND)
        **(
            {"head": {"scripts": [film.path(*p.split("/")) for p in m["head"]["scripts"]]}}
            if (m.get("head") or {}).get("scripts")
            else {}
        ),
        "images": {
            k: v if os.path.isabs(v) else film.path(*v.split("/"))
            for k, v in (m.get("images") or {}).items()
            if isinstance(v, str) and k.startswith("brand_")
        },
    }
    _write_json(os.path.join(d, "sketch.json"), man)
    times = [t for i in range(len(names)) for t in (i + 0.25, i + 0.75)]
    return os.path.join(d, "sketch.json"), times


def thumbs(film, names):
    """Each member's thumbnail from sheet()'s stills: the drawn frame cropped to what differs
    from the empty one. {name: PIL image}; a member that drew nothing has none."""
    from PIL import Image, ImageChops

    d = film.path("temp", "castsheet", "stills")
    out = {}
    for i, n in enumerate(names):
        a, b = (os.path.join(d, "%06.2f.png" % t) for t in (i + 0.25, i + 0.75))
        if not (os.path.exists(a) and os.path.exists(b)):
            continue
        with Image.open(a) as A, Image.open(b) as B:
            A, B = A.convert("RGB"), B.convert("RGB")
            box = ImageChops.difference(A, B).convert("L").point(lambda v: 255 if v > 24 else 0)
            box = box.getbbox()
            if not box:
                continue
            pad = 24
            box = (
                max(0, box[0] - pad),
                max(0, box[1] - pad),
                min(B.width, box[2] + pad),
                min(B.height, box[3] + pad),
            )
            im = B.crop(box)
            im.thumbnail((480, 480))
            out[n] = im
    return out


def _contact(lib, idx):
    """Every member on one sheet, named: cast.png."""
    from PIL import Image, ImageDraw, ImageFont

    d = dir_of(lib)
    names = [n for n, e in sorted(idx["cast"].items()) if not e.get("deleted")]
    p = os.path.join(d, "cast.png")
    if not names:
        if os.path.exists(p):
            os.remove(p)
        return
    W, H, cols = 400, 360, min(4, len(names))
    rows = -(-len(names) // cols)
    sheet = Image.new("RGB", (cols * W, rows * H), "white")
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    for i, n in enumerate(names):
        x, y = (i % cols) * W, (i // cols) * H
        tp = os.path.join(d, "cast", n, "thumb.png")
        if os.path.exists(tp):
            with Image.open(tp) as im:
                im = im.convert("RGB")
                im.thumbnail((W - 30, H - 70))
                sheet.paste(im, (x + (W - im.width) // 2, y + 10 + (H - 70 - im.height) // 2))
        else:
            dr.text((x + 20, y + H // 2 - 40), "(no picture)", fill="#999999", font=font)
        dr.text((x + 20, y + H - 50), n, fill="#222222", font=font)
        dr.rectangle((x, y, x + W - 1, y + H - 1), outline="#dddddd")
    sheet.save(p)


def _version_with(d, name, e, h):
    """The code of the kept version of a member whose hash is h (the last KEEP are kept), or
    None."""
    if not h:
        return None
    for v in range(int(e.get("version") or 0), 0, -1):
        code = _read(os.path.join(d, "cast", name, "v%d.js" % v))
        if code is not None and _hash(code) == h:
            return code
    return None


def _merge3(base, ours, theirs, work):
    """git merge-file of three texts: the merged text, or None when it does not merge cleanly
    (or git is not there). ours: the library's version, theirs: the episode's."""
    os.makedirs(work, exist_ok=True)
    paths = []
    for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
        p = os.path.join(work, name + ".js")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        paths.append(p)
    try:
        r = subprocess.run(["git", "merge-file", "-p", *paths], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def _parses(code, path):
    node = shutil.which("node")
    if not node:
        return False  # no way to tell: kept as a clash, as before
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(code)
    try:
        return (
            subprocess.run([node, "--check", path], capture_output=True, timeout=60).returncode == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def merges(film, items):
    """A finished film's members (changes()) whose library version moved on while it was made
    -- another episode changed them, the Pro plan's two at once -- each merged three ways: base,
    the version this film started from (one of the KEEP kept), onto the library's as it is now.
    A clean merge that parses replaces the item's code, with merged_from (the library's hash it
    went onto), for keep() to save while that is still the library's; keep_cast draws it first,
    and one that draws nothing is put back. Anything else is left as it was: keep() keeps it as a
    clash. -> (items, [names merged])."""
    lib = lib_of(film.record())
    if not lib or not items:
        return items, []
    idx, d = load(lib), dir_of(lib)
    had = {c["name"]: c["hash"] for c in (film.record().get("library") or {}).get("cast") or []}
    work = film.path("temp", "castmerge")
    out, merged = [], []
    for it in items:
        n, e = it["name"], idx["cast"].get(it["name"])
        if not e or e.get("deleted") or e.get("hash") in (had.get(n), it["hash"]):
            out.append(it)
            continue
        base = _version_with(d, n, e, had.get(n))
        ours = _read(os.path.join(d, "cast", n, "v%d.js" % e["version"]))
        code = (
            _merge3(base, ours, it["code"], os.path.join(work, n))
            if base is not None and ours is not None
            else None
        )
        if code is not None and code == ours:  # what it changed is in the library's already
            out.append(it | {"code": ours, "hash": e["hash"]})  # nothing to save, and no clash
            continue
        if not code or not _parses(code, os.path.join(work, n, "merged.js")):
            out.append(it)
            continue
        out.append(
            it
            | {
                "code": code,
                "hash": _hash(code),
                "about": _about(code) or it["about"],
                "kind": _kind(code),
                "merged_from": e["hash"],
            }
        )
        merged.append(n)
    shutil.rmtree(work, ignore_errors=True)
    return out, merged


def _clash(d, name, film):
    """The film's own copy of a member that did not go into the library, kept beside it."""
    src = film.path("cast", name + ".js")
    if not os.path.exists(src):
        return
    os.makedirs(os.path.join(d, CLASHED, name), exist_ok=True)
    shutil.copyfile(src, os.path.join(d, CLASHED, name, film.id + ".js"))


def keep(film, items, pictures=None):
    """Take in what a finished film made: its new and changed members (changes()) as new
    versions, with their thumbnails (thumbs()); the film joins the members it used and the
    library's films. Returns {"saved": [...], "used": [...]} and "clashed": [...] when a member
    had moved on in the library since the film got it (_keep), or None without a library."""
    lib = lib_of(film.record())
    if not lib:
        return None
    with _lock(lib):
        return _keep(film, lib, items, pictures or {})


def _keep(film, lib, items, pictures):
    """A member is saved only over the version the film started from. When the library's has moved
    on since (another episode changed it while this one was made, or this is an old film finished
    again), the newer one stays: saving this film's copy would undo what the other film added
    (2026-10-01: four of Leo's episodes finished again, oldest first, and the first one took his
    rain boots, bike helmet and sitting poses out of the series). The film's own copy stays in its
    cast/, and the clash is in the answer."""
    idx = load(lib)
    d = dir_of(lib)
    now = datetime.now().isoformat(timespec="seconds")
    had = {c["name"]: c["hash"] for c in (film.record().get("library") or {}).get("cast") or []}
    told = {c["name"] for c in (film.record().get("library") or {}).get("clashed") or []}
    saved, clashed, merged = [], [], []
    taken = []
    for it in items:
        n = it["name"]
        e = idx["cast"].get(n)
        if e and e.get("painted") and not e.get("deleted"):
            taken.append(n)  # a painted character's name: a drawing never replaces the picture
            continue
        if it.get("merged_from") and e and e.get("hash") == it["merged_from"]:
            merged.append(n)  # merged onto what the library holds still (merges): saved over it
        elif e and e.get("hash") != had.get(n):  # changed since this film got it, or made elsewhere
            if e.get("hash") != it["hash"]:
                clashed.append(n)
                if lib[1]:  # a project's: kept beside it, for the next episodes to fold in
                    _clash(d, n, film)
            continue
        e = e or {"version": 0, "films": [], "created": now, "from_film": film.id}
        v = e["version"] + 1
        md = os.path.join(d, "cast", n)
        os.makedirs(md, exist_ok=True)
        with open(os.path.join(md, "v%d.js" % v), "w", encoding="utf-8") as f:
            f.write(it["code"])
        for old in range(1, v - KEEP + 1):
            try:
                os.remove(os.path.join(md, "v%d.js" % old))
            except OSError:
                pass
        tp = os.path.join(md, "thumb.png")
        if n in pictures:
            pictures[n].save(tp)
        elif os.path.exists(tp):
            os.remove(tp)  # the old picture would show the old version
        e.update(
            version=v,
            hash=it["hash"],
            about=it["about"] or e.get("about", ""),
            kind=it.get("kind"),
            updated=now,
            film=film.id,
            release=film.record().get("release"),
            thumb=n in pictures,
        )
        e.pop("deleted", None)  # changed after it was deleted: the person's film brought it back
        idx["cast"][n] = e
        saved.append(n)
        if n in told:  # this film was given the clashed copies to fold in, and saved its own
            shutil.rmtree(os.path.join(d, CLASHED, n), ignore_errors=True)
    painted, refused = _keep_painted(film, lib, idx, now) if lib[1] else ([], [])
    names = used(film) + painted_used(film)
    for n in names:
        e = idx["cast"].get(n)
        if e and not e.get("deleted"):
            e["films"] = ([film.id] + [x for x in e.get("films") or [] if x != film.id])[:LISTED]
            e["last_used"] = now
    idx["films"] = ([film.id] + [x for x in idx["films"] if x != film.id])[:LISTED]
    _save(lib, idx)
    sounds, sounds_clashed = _keep_sounds(film, lib, now) if lib[1] else ([], [])
    if saved or painted:
        _contact(lib, idx)
    _poster(lib, film)
    out = {"saved": saved, "used": [n for n in names if n in idx["cast"]]}
    if painted:
        out["painted"] = painted
    if refused or taken:
        out["painted_refused"] = refused + taken
    if merged:
        out["merged"] = merged
    if clashed:
        out["clashed"] = clashed
    if sounds:
        out["sounds"] = sounds
    if sounds_clashed:
        out["sounds_clashed"] = sounds_clashed
    return out


# ---------------------------------------------------------------- what the person sees
def listing(client, project=None):
    """The library's cast and films (and a project's pictures), as the site may show them."""
    lib = owner(client, project)
    if not lib:
        return {"cast": [], "films": []}
    idx = load(lib)
    cast = [_listed(n, e) for n, e in sorted(idx["cast"].items()) if not e.get("deleted")]
    out = {"cast": cast, "films": idx["films"]}
    if project:
        out["pictures"] = [
            {"name": n, "once": bool(e.get("once"))}
            | {k: e.get(k) for k in ("w", "h", "added")}
            | ({"role": e["role"]} if e.get("role") in PICTURE_ROLES else {})
            for n, e in sorted(idx["pictures"].items())
        ]
        out["voice"] = [
            {"key": k} | e
            for k, e in sorted(idx["voice"].items(), key=lambda x: x[1].get("added") or "")
        ]
        out["actors"] = [
            {"name": n} | {k: e.get(k) for k in ("about", "faces", "poses", "added")}
            for n, e in sorted(idx["actors"].items())
        ]
        out["clashed"] = [{"name": c["name"], "film": c["film"]} for c in clashed_of(lib, idx)]
    return out


def thumb_of(client, name, project=None):
    """The path of a member's thumbnail, or None."""
    lib = owner(client, project)
    if not lib or not NAME.match(name or ""):
        return None
    e = load(lib)["cast"].get(name)
    p = os.path.join(dir_of(lib), "cast", name, "thumb.png")
    return p if e and not e.get("deleted") and os.path.exists(p) else None


def delete(client, name, project=None):
    """Take a member out of the library's next films (its files stay, for an undo). False when
    there is no such member."""
    lib = owner(client, project)
    if not lib or not NAME.match(name or ""):
        return False
    with _lock(lib):
        idx = load(lib)
        e = idx["cast"].get(name)
        if not e or e.get("deleted"):
            return False
        e["deleted"] = datetime.now().isoformat(timespec="seconds")
        _save(lib, idx)
        _contact(lib, idx)
    return True


# ---------------------------------------------------------------- a project's pictures
class PictureError(Exception):
    """Why a picture was not taken: a status for the answer, and words for a person."""

    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


def add_picture(client, project, name, src, ext, once=False, role=None):
    """Put a picture (an upload's file, checked by uploads.receive) into a project, under a name
    (the film's SK.image('pic_<name>')); the same name again replaces it. once=True: this picture
    seeds only the project's next episode, then is removed on its own (see _seed_pictures) -- the
    person adds a fresh one for the episode after that. role: what it is for (PICTURE_ROLES), or
    None for Claude to decide. Returns its entry."""
    lib = owner(client, project)
    if not lib or not project:
        raise PictureError(404, "No such project.")
    if role is not None and role not in PICTURE_ROLES:
        raise PictureError(400, "A picture's role is one of: %s." % ", ".join(PICTURE_ROLES))
    if not NAME.match(name or ""):
        raise PictureError(
            400, "A picture's name is lowercase letters, digits and _, starting with a letter."
        )
    if ext not in PICTURE_EXT:
        raise PictureError(400, "A picture is a PNG, JPEG or WebP.")
    from PIL import Image

    with _lock(lib):
        idx = load(lib)
        if name not in idx["pictures"] and len(idx["pictures"]) >= PICTURES:
            raise PictureError(409, "A project holds up to %d pictures." % PICTURES)
        d = os.path.join(dir_of(lib), "pictures")
        os.makedirs(d, exist_ok=True)
        _remove_picture(d, name)
        shutil.copyfile(src, os.path.join(d, "%s.%s" % (name, ext)))
        try:
            with Image.open(src) as im:
                w, h = im.size
                im.thumbnail((480, 480))
                im.save(os.path.join(d, name + ".thumb.png"))
        except (OSError, ValueError) as e:
            _remove_picture(d, name)
            raise PictureError(400, "That picture could not be read.") from e
        idx["pictures"][name] = {
            "ext": ext,
            "w": w,
            "h": h,
            "added": datetime.now().isoformat(timespec="seconds"),
            **({"once": True} if once else {}),
            **({"role": role} if role else {}),
        }
        _save(lib, idx)
        return {"name": name} | idx["pictures"][name]


def set_picture_role(client, project, name, role):
    """Say what a project's picture is for (PICTURE_ROLES); the next episodes are told. Its
    entry, or None when there is no such picture."""
    if role not in PICTURE_ROLES:
        raise PictureError(400, "A picture's role is one of: %s." % ", ".join(PICTURE_ROLES))
    lib = owner(client, project)
    if not lib or not project or not NAME.match(name or ""):
        return None
    with _lock(lib):
        idx = load(lib)
        e = idx["pictures"].get(name)
        if not e:
            return None
        e["role"] = role
        _save(lib, idx)
        return {"name": name} | e


def _remove_picture(d, name):
    for ext in (*PICTURE_EXT, "thumb.png"):
        try:
            os.remove(os.path.join(d, "%s.%s" % (name, ext)))
        except OSError:
            pass


def delete_picture(client, project, name):
    """Take a picture out of a project, files and all. False when there is no such picture."""
    lib = owner(client, project)
    if not lib or not project or not NAME.match(name or ""):
        return False
    with _lock(lib):
        idx = load(lib)
        if name not in idx["pictures"]:
            return False
        del idx["pictures"][name]
        _remove_picture(os.path.join(dir_of(lib), "pictures"), name)
        _save(lib, idx)
    return True


def picture_thumb(client, project, name):
    """The path of a project picture's thumbnail, or None."""
    lib = owner(client, project)
    if not lib or not project or not NAME.match(name or ""):
        return None
    p = os.path.join(dir_of(lib), "pictures", name + ".thumb.png")
    return p if name in load(lib)["pictures"] and os.path.exists(p) else None


# ---------------------------------------------------------------- a project's painted characters
# A painted cast member is a picture, not code: a character the person put in as they are ("Add
# a character" on the Cast tab, add_character), or a painting an episode kept for the series
# ("keep": true on an image in paint.json, _keep_painted). It shares the cast's names, its
# Remove (delete) and its thumbnails with the drawn members, and is told apart by "painted":
#
#     cast\<name>\v1.png v2.jpg ...   each kept version (the last KEEP), any of PICTURE_EXT
#     cast\<name>\thumb.png           its latest version, small
#
# Every episode gets each live one as inputs/cast_<name>.<ext> (_seed_painted): a painting is made
# from it with "ref": "cast_<name>" (sketch-paint.py), and it is drawn as it is with
# SK.image('cast_<name>'). Old films keep their own copy; a removed character reaches no new one.
CHARACTERS = 16  # a project's painted characters: every episode carries them all
MIN_SIDE = 512  # a character's short side: less gives the painter too little of a face
MAX_ABOUT = 200  # a character's description, as a cast member's (_about)


def _bytes_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _live_painted(idx):
    return {n: e for n, e in idx["cast"].items() if e.get("painted") and not e.get("deleted")}


def _put_painted(lib, idx, name, src, about, now, **meta):
    """A new version of painted member `name` from the picture at src (its thumbnail too), in
    idx; the caller holds the lock and saves. Returns the entry, or raises PictureError when the
    picture cannot be read."""
    from PIL import Image

    try:
        with Image.open(src) as im:
            w, h = im.size
            fmt = (im.format or "").upper()
    except (OSError, ValueError) as e:
        raise PictureError(400, "That picture could not be read.") from e
    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}.get(fmt)
    if not ext:
        raise PictureError(400, "A character is a PNG, JPEG or WebP picture.")
    e = idx["cast"].get(name) or {"version": 0, "films": [], "created": now}
    v = int(e.get("version") or 0) + 1
    md = os.path.join(dir_of(lib), "cast", name)
    os.makedirs(md, exist_ok=True)
    shutil.copyfile(src, os.path.join(md, "v%d.%s" % (v, ext)))
    for old in range(1, v - KEEP + 1):
        for x in PICTURE_EXT:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(md, "v%d.%s" % (old, x)))
    with Image.open(src) as im:
        im = im.convert("RGBA")
        im.thumbnail((480, 480))
        im.save(os.path.join(md, "thumb.png"))
    e.update(
        version=v,
        hash=_bytes_hash(src),
        about=" ".join(str(about or "").split())[:MAX_ABOUT],
        kind=None,
        painted=True,
        ext=ext,
        w=w,
        h=h,
        updated=now,
        thumb=True,
        **meta,
    )
    e.pop("deleted", None)
    idx["cast"][name] = e
    return e


def add_character(client, project, name, about, src):
    """Put a ready-made painted character (an upload's picture, checked by uploads.receive) into
    a project's cast, under a name, with a description of who it is; the same name again is its
    next version. Returns its entry as listing() shows it."""
    lib = owner(client, project)
    if not lib or not project:
        raise PictureError(404, "No such project.")
    if not NAME.match(name or ""):
        raise PictureError(
            400, "A character's name is lowercase letters, digits and _, starting with a letter."
        )
    about = " ".join(str(about or "").split())
    if not about:
        raise PictureError(400, "Say who the character is, in a line: it goes with the picture.")
    if len(about) > MAX_ABOUT:
        raise PictureError(400, "A character's description is at most %d characters." % MAX_ABOUT)
    from PIL import Image

    try:
        with Image.open(src) as im:
            short = min(im.size)
    except (OSError, ValueError) as e:
        raise PictureError(400, "That picture could not be read.") from e
    if short < MIN_SIDE:
        raise PictureError(
            400,
            "A character's picture needs at least %d px on its short side (this one has %d): "
            "the painter copies the face from it." % (MIN_SIDE, short),
        )
    now = datetime.now().isoformat(timespec="seconds")
    with _lock(lib):
        idx = load(lib)
        e = idx["cast"].get(name)
        if e and not e.get("deleted") and not e.get("painted"):
            raise PictureError(
                409, "The cast has a drawn member called %s already: choose another name." % name
            )
        if name not in _live_painted(idx) and len(_live_painted(idx)) >= CHARACTERS:
            raise PictureError(
                409, "A project holds up to %d painted characters: remove one first." % CHARACTERS
            )
        e = _put_painted(lib, idx, name, src, about, now, uploaded=now)
        _save(lib, idx)
        _contact(lib, idx)
    return _listed(name, e)


def _seed_painted(film, lib, idx):
    """A project's live painted characters into the film's inputs/ as cast_<name>.<ext>, each in
    the manifest's images. [{name, file, about, w, h, hash}] (name without its cast_)."""
    out = []
    for n, e in sorted(_live_painted(idx).items()):
        src = os.path.join(dir_of(lib), "cast", n, "v%d.%s" % (e["version"], e.get("ext")))
        if not os.path.exists(src):
            continue
        os.makedirs(film.path("inputs"), exist_ok=True)
        rel = "inputs/cast_%s.%s" % (n, e["ext"])
        shutil.copyfile(src, film.path(*rel.split("/")))
        out.append(
            {"name": n, "file": rel, "about": e.get("about", "")}
            | {k: e.get(k) for k in ("w", "h", "hash")}
        )
    if out:
        with open(film.manifest, encoding="utf-8") as f:
            m = json.load(f)
        m.setdefault("images", {}).update({"cast_" + p["name"]: p["file"] for p in out})
        _write_json(film.manifest, m)
    return out


def painted_note(film, painted, own_cast=False):
    """What an episode is told of its project's painted characters, and of keeping one."""
    paints = bool(paint_kinds(film.caps))
    out = []
    if painted:
        out.append(
            "The project's characters, as pictures (its cast: put in by its person, or kept by "
            "earlier episodes; each in inputs/, Read it to see them)%s:"
            % (
                "; a collection's films do not share a cast, so bring one in only when this film "
                "is about them"
                if own_cast
                else ""
            )
        )
        out += ["- cast_%s: %s" % (c["name"], c.get("about") or "no description") for c in painted]
        out.append(
            'Whenever one of them is in a painting, paint it with "ref": "cast_<name>" -- '
            '"ref": ["cast_<one>", "cast_<other>"] for two or more together, up to 4 -- and '
            "describe them in its prompt as written here: the painter keeps their faces, clothes "
            "and proportions, so they look the same in every film. Never give one of them another "
            "look, and never paint them from the words alone."
            if paints
            else "On screen as they are: SK.image('cast_<name>', x, y, w)."
        )
    if paints:
        full = len(painted) >= CHARACTERS
        out.append(
            "A new character the series should keep (a person or a mascot it will meet again): "
            'paint them alone, whole, on a plain ground, and mark that painting "keep": true with '
            '"about": "<who they are, what they wear>" in paint.json; after the film they join the '
            "project's cast under the painting's name (lowercase letters, digits and _), and the "
            "next episodes paint from them. A kept painting named as one of the characters above "
            "is their next version: only when this episode is meant to change how they look."
            + (
                " The cast holds %d painted characters and is full: keep a new one only by "
                "repainting one of these." % CHARACTERS
                if full
                else ""
            )
        )
    return "\n".join(out)


# "@mom" in a prompt: a cast member, by name (the site's @ list offers them). Not in a word, an
# e-mail address or a path: a@b.com and x/@y are the prompt's own text
MENTION = re.compile(r"(?<![\w@./])@([A-Za-z][A-Za-z0-9_]{0,30})\b")


def mentioned(client, project, prompt):
    """The project's cast members a prompt names as @name, in order: ([names], {typo: name}). An
    @word that is no member's name but close to one (@mum, with a mom in the cast) is a typo, for
    the person to fix before anything is held; any other @word is the prompt's own (a handle)."""
    lib = owner(client, project)
    if not lib or not project:
        return [], {}
    live = sorted(n for n, e in load(lib)["cast"].items() if not e.get("deleted"))
    named, typos = [], {}
    for w in MENTION.findall(prompt or ""):
        n = w.lower()
        if n in live:
            if n not in named:
                named.append(n)
            continue
        close = difflib.get_close_matches(n, live, 1, 0.6)  # @mum for @mom, not @kitcut
        if close:
            typos[n] = close[0]
    return named, typos


def named_note(film):
    """What a film is told of the characters its prompt names (@name): each must be in it, as
    the cast has them. "" when it names none."""
    rec = film.record()
    got = rec.get("library") or {}
    painted = {c["name"]: c for c in got.get("painted") or []}
    drawn = {c["name"]: c for c in got.get("cast") or []}
    lines = []
    for n in rec.get("characters") or []:
        if n in painted:
            lines.append(
                "- @%s: %s -- painted: inputs/%s; every painting they are in is made with "
                '"ref": "cast_%s" (or a list with it)'
                % (n, painted[n].get("about") or "", os.path.basename(painted[n]["file"]), n)
                if paint_kinds(film.caps)
                else "- @%s: %s -- a picture: SK.image('cast_%s', x, y, w)"
                % (n, painted[n].get("about") or "", n)
            )
        elif n in drawn:
            lines.append("- @%s: %s -- drawn: SK.cast.%s" % (n, drawn[n].get("about") or "", n))
    if not lines:
        return ""
    return (
        "The prompt names these characters of the project's cast (@name). Each one is in this "
        "film, as the cast has them -- the same face, clothes and proportions -- and nobody "
        "else plays them:\n" + "\n".join(lines)
    )


def painted_used(film):
    """The painted characters a film used: named by a painting's ref, or drawn as they are."""
    try:
        with open(film.path("paint.json"), encoding="utf-8") as f:
            ims = (json.load(f) or {}).get("images") or []
    except (OSError, ValueError, AttributeError):
        ims = []
    refs = [
        r
        for im in ims
        if isinstance(im, dict)
        for r in (im.get("ref") if isinstance(im.get("ref"), list) else [im.get("ref")])
    ]
    drawn = re.findall(
        r"""SK\.image\(\s*['"]cast_([a-z][a-z0-9_]*)['"]""", _read(film.path("film.js")) or ""
    )
    return sorted(
        {r[5:] for r in refs if isinstance(r, str) and r.startswith("cast_")} | set(drawn)
    )


def kept_paintings(film):
    """The paintings a film marked to keep ("keep": true, with its "about"), that it painted:
    [{name, about, path}]."""
    try:
        with open(film.path("paint.json"), encoding="utf-8") as f:
            ims = (json.load(f) or {}).get("images") or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for im in ims:
        if not (
            isinstance(im, dict) and im.get("keep") is True and NAME.match(im.get("name") or "")
        ):
            continue
        p = film.path("images", im["name"] + (".webp" if im.get("cutout") else ".jpg"))
        if os.path.exists(p):
            out.append(
                {"name": im["name"], "about": im.get("about") or im.get("prompt"), "path": p}
            )
    return out


def _keep_painted(film, lib, idx, now):
    """A finished episode's kept paintings into its project's cast (under the lock): a new member,
    or the next version of one -- but only over the version the film started from, as a drawn
    member's (_keep); never over a drawn member, nor past CHARACTERS. -> (saved, refused)."""
    had = {
        c["name"]: c.get("hash") for c in (film.record().get("library") or {}).get("painted") or []
    }
    saved, refused = [], []
    for it in kept_paintings(film):
        n, e = it["name"], idx["cast"].get(it["name"])
        live = e and not e.get("deleted")
        if live and not e.get("painted"):
            refused.append(n)  # a drawn member's name
            continue
        if live and e.get("hash") != had.get(n):
            refused.append(n)  # changed since this film got it, or made by another meanwhile
            continue
        if live and e.get("hash") == _bytes_hash(it["path"]):
            continue  # the same picture: nothing new
        if not live and len(_live_painted(idx)) >= CHARACTERS:
            refused.append(n)
            continue
        _put_painted(
            lib,
            idx,
            n,
            it["path"],
            it["about"],
            now,
            film=film.id,
            **({} if live else {"from_film": film.id}),
        )
        saved.append(n)
    return saved, refused


def _listed(n, e):
    """A cast member as listing() shows it."""
    return {
        "name": n,
        "about": e.get("about", ""),
        "kind": e.get("kind"),
        "version": e["version"],
        "films": e.get("films") or [],
        "updated": e.get("updated"),
        "thumb": bool(e.get("thumb")),
        **({"painted": True} if e.get("painted") else {}),
    }


# ---------------------------------------------------------------- a project's voice lines
# Recordings of narration lines its person approved by ear (docs/studio-voice-lines.md): a series'
# greeting and sign-off, a name the voice says right only now and then. Filed under
# _sketch.voice_line_key (the words, the TTS, the voice, the model); every episode gets them
# (audio/vo/approved/), and sketch-vo.py plays one for any line with the same key instead of
# recording it again. Why: a TTS picks a word's stress afresh on every take, and the check after
# recording (Whisper) turns speech into text, which is the same whichever syllable is stressed --
# a mis-stressed name scores 100 % and ships (KI-047).
class VoiceError(PictureError):
    """Why a voice line was not taken: a status for the answer, and words for a person."""


def _voice_dir(lib):
    return os.path.join(dir_of(lib), "voice")


def _mp3(src, out):
    """The same recording as a small MP3 to listen to (the site plays it)."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-b:a", "96k", out],
        check=True,
        capture_output=True,
    )


def add_voice(client, project, text, src, vo, film=None, line=None):
    """Put a recording of a narration line into a project as an approved voice line: text is
    what it says, src any audio file of just that line, vo the voice it is in ({tts, voice,
    model, language}). The same words in the same voice again replace it. Returns its entry."""
    lib = owner(client, project)
    if not lib or not project:
        raise VoiceError(404, "No such project.")
    words = " ".join(re.sub(r"\[[^\]]*\]", "", text or "").split())
    if not words or len(words) > 300:
        raise VoiceError(400, "A voice line is one line of narration, at most 300 characters.")
    try:
        x = _sketch.decode(src)
    except (OSError, subprocess.CalledProcessError) as e:
        raise VoiceError(400, "That recording could not be read.") from e
    dur = len(x) / _sketch.SR
    if not 0.3 <= dur <= 30:
        raise VoiceError(400, "A voice line is 0.3-30 seconds long.")
    key = _sketch.voice_line_key(words, vo)
    tts = vo.get("tts") or "gemini"
    with _lock(lib):
        idx = load(lib)
        if key not in idx["voice"] and len(idx["voice"]) >= VOICE_LINES:
            raise VoiceError(409, "A project holds up to %d voice lines." % VOICE_LINES)
        d = _voice_dir(lib)
        os.makedirs(d, exist_ok=True)
        _sketch.write_wav(os.path.join(d, key + ".wav"), x)
        _mp3(os.path.join(d, key + ".wav"), os.path.join(d, key + ".mp3"))
        idx["voice"][key] = {
            "text": words,
            "tts": tts,
            "voice": vo.get("voice") or "",
            "model": vo.get("model") or _sketch.TTS_MODEL.get(tts, ""),
            "language": (vo.get("language") or "en").lower(),
            "dur": round(dur, 2),
            "added": datetime.now().isoformat(timespec="seconds"),
            "film": film,
            "line": line,
        }
        _save(lib, idx)
        return {"key": key} | idx["voice"][key]


def _vo_of(film):
    """The voice a film's narration is in: its vo.json, with the studio's pinned TTS."""
    try:
        with open(film.path("vo.json"), encoding="utf-8") as f:
            vo = json.load(f)
    except (OSError, ValueError):
        vo = {}
    return {k: vo.get(k) for k in ("voice", "model", "language")} | {
        "tts": vo.get("tts") or VO_PINNED["tts"]
    }


def _timeline(film):
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            return json.load(f).get("lines", [])
    except (OSError, ValueError):
        return []


def film_lines(film):
    """A finished film's narration as its person may go through it: [{i, text, start, dur, key,
    approved, played_approved}]. approved: the line is one of its project's voice lines now;
    played_approved: the film played it from one."""
    lib = lib_of(film.record())
    have = load(lib)["voice"] if lib and lib[1] else {}
    vo = _vo_of(film)
    out = []
    for L in _timeline(film):
        key = _sketch.voice_line_key(L["text"], vo)
        out.append(
            {
                "i": L["i"],
                "text": L["text"],
                "start": L["start"],
                "dur": L.get("dur"),
                "key": key,
                "approved": key in have,
                "played_approved": bool(L.get("approved")),
            }
        )
    return out


def _line_file(film, i):
    L = next((x for x in _timeline(film) if x["i"] == i), None)
    p = L and os.path.join(film.dir, L["file"])
    return (L, p) if p and os.path.exists(p) else (None, None)


def film_line_audio(film, i):
    """Line i of a film, as an MP3 to listen to (made once, in the film's temp/lines/; again
    when the line was re-recorded). None when there is no such line."""
    L, src = _line_file(film, i)
    if L is None:
        return None
    out = film.path("temp", "lines", "L%02d.mp3" % i)
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        _mp3(src, out)
    return out


def add_voice_from_film(client, project, film_id, i):
    """Approve line i of one of the project's finished episodes, as it sounds in the film."""
    f = Film.open(str(film_id or ""))
    rec = f.record() if f else {}
    if (
        not f
        or not clients.same(rec.get("client"), client)
        or (rec.get("project") or {}).get("id") != project
    ):
        raise VoiceError(404, "That film is not an episode of this project.")
    if f.state != "done":
        raise VoiceError(409, "Only a finished episode's lines can be approved.")
    L, src = _line_file(f, i) if isinstance(i, int) and not isinstance(i, bool) else (None, None)
    if L is None:
        raise VoiceError(404, "That film has no such line.")
    return add_voice(client, project, L["text"], src, _vo_of(f), film=f.id, line=i)


def delete_voice(client, project, key):
    """Take a voice line out of a project, files and all. False when there is no such line."""
    lib = owner(client, project)
    if not lib or not project or not VOICE_KEY.match(key or ""):
        return False
    with _lock(lib):
        idx = load(lib)
        if key not in idx["voice"]:
            return False
        del idx["voice"][key]
        for ext in (".wav", ".mp3"):
            try:
                os.remove(os.path.join(_voice_dir(lib), key + ext))
            except OSError:
                pass
        _save(lib, idx)
    return True


def voice_audio(client, project, key):
    """The path of a voice line's MP3, or None."""
    lib = owner(client, project)
    if not lib or not project or not VOICE_KEY.match(key or ""):
        return None
    p = os.path.join(_voice_dir(lib), key + ".mp3")
    return p if key in load(lib)["voice"] and os.path.exists(p) else None


def _seed_voice(film, lib, idx):
    """A project's voice lines into the film's audio/vo/approved/ (for sketch-vo.py), with an
    index of what each says and in which voice. [{key, text, voice, model, dur}]"""
    out, index = [], {}
    d = film.path("audio", "vo", _sketch.APPROVED)
    for key, e in sorted(idx["voice"].items(), key=lambda x: x[1].get("added") or ""):
        src = os.path.join(_voice_dir(lib), key + ".wav")
        if not os.path.exists(src):
            continue
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(src, os.path.join(d, key + ".wav"))
        index[key] = {k: e.get(k) for k in ("text", "tts", "voice", "model", "language", "dur")}
        out.append({"key": key} | {k: e.get(k) for k in ("text", "voice", "model", "dur")})
    if index:
        _write_json(os.path.join(d, "index.json"), index)
    return out


# ---------------------------------------------------------------- a project's actors
# Characters an image model drew, cut into packs by scripts/actor-pack.py: the figure, a patch for
# each face, mouth shape and blink, and whole-figure poses, on atlas pages (sketch/actors.js draws
# them; docs/reference.md, "Actors"). A pack is put into a project by hand (studio/actor_put.py,
# `ops.sh actor-put`), never by a film, and every episode gets each one: actors/<name>/ in its
# folder, the manifest's "actors", and the "actors" capability -- heads.js and actors.js in its
# engine copy, studio/actors.md in its prompt.
ACTORS = 4  # a project's actors: every episode carries them all (an atlas page is ~1.5 MB)
ACTOR_PAGE = re.compile(r"^atlas-\d{1,2}\.(webp|png)$")
ACTOR_BYTES = 32 * 1024 * 1024  # one pack's files, all told
ACTOR_SHEET = "check.jpg"  # every piece laid out and named (actor-pack.py): what Claude Reads


class ActorError(PictureError):
    """Why a pack was not taken: a status, and words for whoever put it."""


def _pack_pieces(P):
    """Every piece a pack's faces and poses name."""
    yield "base"
    for group in (P["faces"], P["poses"]):
        for e in group.values():
            if e.get("piece"):
                yield e["piece"]
            for m in (e.get("mouths") or {}).values():
                yield m["piece"]
            if e.get("blink"):
                yield e["blink"]["piece"]


def read_pack(src):
    """The pack actor-pack.py wrote in folder src, checked: (pack, the files that make it).
    Raises ActorError for a folder that is not one, or one too big for every episode to carry."""
    try:
        with open(os.path.join(src, "pack.json"), encoding="utf-8") as f:
            P = json.load(f)
    except (OSError, ValueError) as e:
        raise ActorError(400, "%s: no pack.json (scripts/actor-pack.py makes one)" % src) from e
    if not isinstance(P, dict) or P.get("v") != 1:
        raise ActorError(400, "%s: pack.json is not an actor pack (v1)" % src)
    try:
        pages, pieces = P["pages"], P["pieces"]
        ok = (
            isinstance(P["figure"]["height"], (int, float))
            and isinstance(P["faces"], dict)
            and isinstance(P["poses"], dict)
            and pages
            and all(isinstance(p, str) and ACTOR_PAGE.match(p) for p in pages)
        )
        missing = [n for n in _pack_pieces(P) if n not in pieces]
        ok = ok and all(0 <= int(pc["p"]) < len(pages) for pc in pieces.values())
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise ActorError(400, "%s: pack.json is not a whole actor pack: %s" % (src, e)) from e
    if not ok:
        raise ActorError(400, "%s: pack.json's pages or pieces are not an actor pack's" % src)
    if missing:
        raise ActorError(400, "%s: pack.json names pieces it does not hold: %s" % (src, missing))
    files = ["pack.json", *pages] + (
        [ACTOR_SHEET] if os.path.isfile(os.path.join(src, ACTOR_SHEET)) else []
    )
    gone = [f for f in files if not os.path.isfile(os.path.join(src, f))]
    if gone:
        raise ActorError(400, "%s: missing %s" % (src, ", ".join(gone)))
    size = sum(os.path.getsize(os.path.join(src, f)) for f in files)
    if size > ACTOR_BYTES:
        raise ActorError(
            400, "%s: %.1f MB, over %d MB" % (src, size / 1e6, ACTOR_BYTES // (1024 * 1024))
        )
    return P, files


def _talks(P):
    """The faces of a pack that have mouths of their own: the ones it can speak in."""
    return [f for f, e in P["faces"].items() if e.get("mouths")]


def put_actor(lib, src, name=None, replace=False, about=None):
    """Put the pack in folder src into the project library lib as actor `name` (the pack's own
    name by default): its next episodes get it. A name the project already has is refused unless
    replace. about: who it is, for the episodes' Claude (default: the pack's own, from its spec's
    describe). Returns its entry."""
    if not (isinstance(lib, tuple) and lib[1]):
        raise ActorError(400, "actors belong to a project")
    P, files = read_pack(src)
    name = name or str(P.get("name") or "")
    if not NAME.match(name):
        raise ActorError(
            400,
            "an actor's name is lowercase letters, digits and _, starting with a letter: %r" % name,
        )
    with _lock(lib):
        idx = load(lib)
        if name in idx["actors"] and not replace:
            raise ActorError(409, "the project already has an actor %r" % name)
        if name not in idx["actors"] and len(idx["actors"]) >= ACTORS:
            raise ActorError(409, "a project holds up to %d actors" % ACTORS)
        d = os.path.join(dir_of(lib), "actors", name)
        new = d + ".new"
        shutil.rmtree(new, ignore_errors=True)
        os.makedirs(new)
        for f in files:
            shutil.copyfile(os.path.join(src, f), os.path.join(new, f))
        shutil.rmtree(d, ignore_errors=True)
        os.rename(new, d)
        with open(os.path.join(d, "pack.json"), "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:16]
        idx["actors"][name] = {
            "about": " ".join(str(about if about is not None else P.get("about") or "").split())[
                :600
            ],
            "faces": list(P["faces"]),
            "talk": _talks(P),
            "poses": list(P["poses"]),
            "pages": len(P["pages"]),
            "bytes": sum(os.path.getsize(os.path.join(d, f)) for f in files),
            "hash": digest,
            "built": P.get("built_utc"),
            "added": datetime.now().isoformat(timespec="seconds"),
        }
        _save(lib, idx)
        return {"name": name} | idx["actors"][name]


def delete_actor(lib, name):
    """Take an actor out of a project, files and all. False when there is no such actor."""
    if not (isinstance(lib, tuple) and lib[1]) or not NAME.match(name or ""):
        return False
    with _lock(lib):
        idx = load(lib)
        if name not in idx["actors"]:
            return False
        del idx["actors"][name]
        shutil.rmtree(os.path.join(dir_of(lib), "actors", name), ignore_errors=True)
        _save(lib, idx)
    return True


def _seed_actors(film, lib, idx):
    """A project's actors into the film: actors/<name>/ (the pack, its pages, its sheet), the
    manifest's "actors", and the "actors" capability in its record, with the modules it brings
    copied into its engine (agent.system_prompt reads the caps when Claude starts, and gives the
    film studio/actors.md). The packs are copied under the library's lock, so a pack being
    replaced (put_actor) reaches the film whole, old or new. [{name, about, faces, talk, poses,
    turned, sheet}]"""
    out, packs = [], {}
    if not idx["actors"]:
        return []
    with _lock(lib):
        now = load(lib)["actors"]
        for n in sorted(now):
            src = os.path.join(dir_of(lib), "actors", n)
            try:
                P, files = read_pack(src)
            except ActorError as e:
                print("film %s: actor %s not seeded: %s" % (film.id, n, e.text), file=sys.stderr)
                continue
            dst = film.path("actors", n)
            os.makedirs(dst, exist_ok=True)
            for f in files:
                shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
            packs[n] = "actors/" + n
            out.append(
                {
                    "name": n,
                    "about": now[n].get("about") or "",
                    "faces": list(P["faces"]),
                    "talk": _talks(P),
                    "poses": list(P["poses"]),
                    # a pose that has turned from the picture: no faces on it, mouths of its own
                    "turned": [p for p, e in P["poses"].items() if not e.get("face_at")],
                    "sheet": "actors/%s/%s" % (n, ACTOR_SHEET) if ACTOR_SHEET in files else None,
                }
            )
    if not out:
        return []
    caps = film.caps + (() if "actors" in film.caps else ("actors",))
    for name in modules(caps):  # its own engine copy, as Film.create makes one
        if not os.path.exists(film.path("engine", name + ".js")):
            shutil.copyfile(
                os.path.join(KIT, "sketch", name + ".js"), film.path("engine", name + ".js")
            )
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m.setdefault("actors", {}).update(packs)
    have = list(m.get("modules") or [])
    m["modules"] = have + [x for x in modules(caps) if x not in have]
    _write_json(film.manifest, m)
    film.update(caps=list(caps))
    return out


def actors_note(actors):
    """The project's actors, for the first message ("" for none): who each is, what it holds."""
    if not actors:
        return ""
    out = [
        "The project's actors (see \"The actors\"), in actors/: Read each one's sheet to see "
        "every face and pose before you use it."
    ]
    for a in actors:
        turned = set(a.get("turned") or ())
        poses = ", ".join(p + (" (turned)" if p in turned else "") for p in a["poses"])
        out.append(
            "- %s%s%s. Faces: %s (it speaks in %s). Poses: %s."
            % (
                a["name"],
                ": " + a["about"] if a.get("about") else "",
                " Sheet: " + a["sheet"] if a.get("sheet") else "",
                ", ".join(a["faces"]),
                ", ".join(a.get("talk") or []) or "none: its mouth never moves",
                poses or "none",
            )
        )
    return "\n".join(out)
