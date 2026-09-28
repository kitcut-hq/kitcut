"""A person's library: what their films made, for their next films to bring back.

    STUDIO_HOME\\library\\<sha256(client)[:20]>\\
        index.json                     {"cast": {name: member}, "films": [film ids, newest first]}
        cast\\<name>\\v1.js v2.js ...   each kept version of a cast member (the last KEEP)
        cast\\<name>\\thumb.png         its latest version drawn alone
        cast.png                        every member on one sheet, named
        films\\<film id>.jpg            a small poster of each film in the memory

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

Only signed-in people have a library (the site's `u:<id>` clients): a visitor known only by an
address could share one with a stranger.

A project on the site (a series, a channel) has a library of its own, inside its person's:

    STUDIO_HOME\\library\\<sha256(client)[:20]>\\<project id>\\
        index.json cast\\ cast.png films\\      as above, for the project's episodes only
        pictures\\<name>.png|jpg|webp           what the person put in the project: a logo,
        pictures\\<name>.thumb.png              character art... every episode gets them as
                                               inputs/pic_<name>.*, SK.image('pic_<name>')

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
from datetime import datetime

from film import CAST_USE, HOME, PROJECT_ID, Film, _write_json

ROOT = os.path.join(HOME, "library")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
KEEP = 5  # versions of a member kept
SEEDED = 24  # members a film starts with (the most recently used)
MEMORY = 5  # earlier films a film may look at
LISTED = 20  # film ids the index remembers
MAX_BYTES = 64 * 1024  # one member's code
FILES = ("film.js", "vo.json", "score.json", "sfx.json", "paint.json")
PICTURES = 6  # a project's pictures: every review render carries them all
PICTURE_EXT = ("png", "jpg", "webp")
_LOCKS = {}  # a library's folder -> the lock its index is changed under
_LOCKS_LOCK = threading.Lock()


def owner(client, project=None):
    """Which library a film or a request uses: (client, project) for a signed-in person, project
    None for their own; None for anyone else, or a project id that is not one."""
    if not (isinstance(client, str) and client.startswith("u:")):
        return None
    if project is not None and not (isinstance(project, str) and PROJECT_ID.match(project)):
        return None
    return (client, project)


def lib_of(rec):
    """The library of the film with this record: its project's, or its person's."""
    return owner(rec.get("client"), (rec.get("project") or {}).get("id"))


def _lib(lib):
    return (lib, None) if isinstance(lib, str) else lib


def dir_of(lib):
    client, project = _lib(lib)
    d = os.path.join(ROOT, hashlib.sha256(client.encode()).hexdigest()[:20])
    return os.path.join(d, project) if project else d


def _lock(lib):
    """The library's own lock: a film keeping its cast and the person removing a member (or a
    picture) at the same moment must not each write an index the other has not seen."""
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(dir_of(lib), threading.Lock())


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
    if "films" not in idx:
        idx["films"] = []
        for f in [] if project else Film.all():
            rec = f.record()
            if rec.get("client") == client and not rec.get("project") and f.state == "done":
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
                "hash": e["hash"],
                "films": len(e.get("films") or []),
                "last_used": e.get("last_used") or e.get("updated"),
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
        _write_json(os.path.join(out, "about.json"), about)
        memory.append({"dir": "library/films/" + sub, "poster": bool(poster)} | about)
    got = {"cast": cast, "films": memory}
    if lib[1]:
        got["pictures"] = _seed_pictures(film, lib, idx)
    film.update(library=got)
    return got


def _seed_pictures(film, lib, idx):
    """A project's pictures into the film's inputs/, each in the manifest's images as
    pic_<name> (never a painted scene's name, nor an upload's). [{name, file, w, h}]"""
    out = []
    for n, e in sorted(idx["pictures"].items()):
        src = os.path.join(dir_of(lib), "pictures", "%s.%s" % (n, e["ext"]))
        if not os.path.exists(src):
            continue
        os.makedirs(film.path("inputs"), exist_ok=True)
        rel = "inputs/pic_%s.%s" % (n, e["ext"])
        shutil.copyfile(src, film.path(*rel.split("/")))
        out.append({"name": "pic_" + n, "file": rel, "w": e.get("w"), "h": e.get("h")})
    if out:
        with open(film.manifest, encoding="utf-8") as f:
            m = json.load(f)
        m.setdefault("images", {}).update({p["name"]: p["file"] for p in out})
        _write_json(film.manifest, m)
    return out


def note(film):
    """What the film has from its library, for the first message ("" when nothing). An
    episode also hears its project's name and brief, in its person's words."""
    rec = film.record()
    got = rec.get("library") or {}
    project = rec.get("project") or {}
    cast, memory = got.get("cast") or [], got.get("films") or []
    pics = got.get("pictures") or []
    if not cast and not memory and not project:
        return ""
    out = []
    if project:
        out.append('This film is an episode of the project "%s".' % project.get("name"))
        if (project.get("brief") or "").strip():
            out.append("Its brief, from the person who runs it:\n" + project["brief"].strip())
    if pics:
        out += [
            "" if out else None,
            "The project's pictures (Read one to see it; on screen: SK.image('<name>', x, y, w)):",
        ]
        out += ["- %s (%sx%s): %s" % (p["name"], p.get("w"), p.get("h"), p["file"]) for p in pics]
    if cast:
        out += [
            "" if out else None,
            "This %s (already loaded from cast/: use any as SK.cast.<name>, change it, or leave "
            "it out; Read library/cast.png to see them):"
            % (
                "project's cast, from its earlier episodes"
                if project
                else "person's cast, from their earlier films"
            ),
        ]
        for c in cast:
            n = c.get("films") or 0
            seen = "in %d film%s" % (n, "" if n == 1 else "s") if n else "not used yet"
            out.append("- %s: %s (%s)" % (c["name"], c.get("about") or "no description", seen))
    if memory:
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
    if project and memory:
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
            out.append({"name": name, "code": code, "hash": h, "about": _about(code)})
    return out


def sheet(film, names):
    """A small film that draws each member alone, for its thumbnail: nothing at i + 0.25 s, the
    member at i + 0.75 s. Written into the film's temp/; returns (manifest, times)."""
    d = film.path("temp", "castsheet")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    js = (
        "SK.setGround('white');\n"
        "const NAMES = %s;\n"
        "SK.film({ duration: %d, fadeOut: 0, handheld: false,\n"
        "  camera: SK.camera([[0, [0, 0, 1]]]), draw(t) {\n"
        "  const i = Math.floor(t), m = SK.cast[NAMES[i]];\n"
        "  if (!m || t - i < 0.5 || typeof m.draw !== 'function') return;\n"
        "  try { m.draw(0, 140, { t: 0 }); } catch (e) {}\n"
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
        "cast": film.path("cast"),
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


def keep(film, items, pictures=None):
    """Take in what a finished film made: its new and changed members (changes()) as new
    versions, with their thumbnails (thumbs()); the film joins the members it used and the
    library's films. Returns {"saved": [...], "used": [...]}, or None without a library."""
    lib = lib_of(film.record())
    if not lib:
        return None
    with _lock(lib):
        return _keep(film, lib, items, pictures or {})


def _keep(film, lib, items, pictures):
    idx = load(lib)
    d = dir_of(lib)
    now = datetime.now().isoformat(timespec="seconds")
    saved = []
    for it in items:
        n = it["name"]
        e = idx["cast"].get(n) or {"version": 0, "films": [], "created": now, "from_film": film.id}
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
            updated=now,
            film=film.id,
            release=film.record().get("release"),
            thumb=n in pictures,
        )
        e.pop("deleted", None)  # changed after it was deleted: the person's film brought it back
        idx["cast"][n] = e
        saved.append(n)
    names = used(film)
    for n in names:
        e = idx["cast"].get(n)
        if e and not e.get("deleted"):
            e["films"] = ([film.id] + [x for x in e.get("films") or [] if x != film.id])[:LISTED]
            e["last_used"] = now
    idx["films"] = ([film.id] + [x for x in idx["films"] if x != film.id])[:LISTED]
    _save(lib, idx)
    if saved:
        _contact(lib, idx)
    _poster(lib, film)
    return {"saved": saved, "used": [n for n in names if n in idx["cast"]]}


# ---------------------------------------------------------------- what the person sees
def listing(client, project=None):
    """The library's cast and films (and a project's pictures), as the site may show them."""
    lib = owner(client, project)
    if not lib:
        return {"cast": [], "films": []}
    idx = load(lib)
    cast = [
        {
            "name": n,
            "about": e.get("about", ""),
            "version": e["version"],
            "films": e.get("films") or [],
            "updated": e.get("updated"),
            "thumb": bool(e.get("thumb")),
        }
        for n, e in sorted(idx["cast"].items())
        if not e.get("deleted")
    ]
    out = {"cast": cast, "films": idx["films"]}
    if project:
        out["pictures"] = [
            {"name": n} | {k: e.get(k) for k in ("w", "h", "added")}
            for n, e in sorted(idx["pictures"].items())
        ]
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


def add_picture(client, project, name, src, ext):
    """Put a picture (an upload's file, checked by uploads.receive) into a project, under a name
    (the film's SK.image('pic_<name>')); the same name again replaces it. Returns its entry."""
    lib = owner(client, project)
    if not lib or not project:
        raise PictureError(404, "No such project.")
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
        }
        _save(lib, idx)
        return {"name": name} | idx["pictures"][name]


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
