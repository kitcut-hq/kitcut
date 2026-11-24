"""A project's scenes and characters as things its person looks at and changes one at a time:
the asset page on the site (Cast and Scenes tabs).

    info(client, project, name)          the member, with the versions the library still holds
    picture(client, project, name, n)    a version's picture, full size (None: the newest)
    restore(client, project, name, n)    an older version becomes the newest again
    put_drawn(lib, items, seen, ...)     write drawn members' next versions (library_put.py, and
                                         an edit's chosen variation: edits.py)

The library keeps no movable "current" pointer: the newest version is the one every new episode
gets (library.seed). So going back to version 3 writes version 3 again as the next one; nothing
else in the studio has to know.

A drawn member is code, so its picture is a render: draw() draws each member alone, with the
library's whole cast loaded (a place drawn by a character's file finds it), and put_drawn saves

    cast\\<name>\\thumb.png      small, as a finished film's keep() leaves it
    cast\\<name>\\v<n>.png       that version, large (PICTURE px): what the asset page shows

Versions written before this (by an episode's keep) have no v<n>.png; the page shows the small
thumbnail for the newest and a number for the older ones.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import contextlib
from datetime import datetime

import library
from film import KIT, Film

PICTURE = 1280  # a drawn version's picture, long side


class AssetError(library.PictureError):
    """Refused, with words for the person who asked."""


class Stage:
    """Enough of a film for library.sheet/thumbs: a folder with a manifest and a cast/."""

    def __init__(self, d, manifest):
        self.dir, self.manifest = d, manifest

    def path(self, *p):
        return os.path.join(self.dir, *p)


def _member(client, project, name):
    lib = library.owner(client, project)
    if not lib or not project:
        raise AssetError(404, "No such project.")
    if not library.NAME.match(name or ""):
        raise AssetError(404, "No such scene or character.")
    idx = library.load(lib)
    e = idx["cast"].get(name)
    if not e or e.get("deleted"):
        raise AssetError(404, "No such scene or character.")
    return lib, idx, e


def _file(lib, name, e, n):
    """Version n of a member, as the library holds it: its path, or None."""
    md = os.path.join(library.dir_of(lib), "cast", name)
    exts = library.PICTURE_EXT if e.get("painted") else ("js",)
    for x in exts:
        p = os.path.join(md, "v%d.%s" % (n, x))
        if os.path.exists(p):
            return p
    return None


def _picture(lib, name, e, n):
    md = os.path.join(library.dir_of(lib), "cast", name)
    if e.get("painted"):
        return _file(lib, name, e, n)
    p = os.path.join(md, "v%d.png" % n)
    if os.path.exists(p):
        return p
    thumb = os.path.join(md, "thumb.png")
    return thumb if n == e["version"] and os.path.exists(thumb) else None


def info(client, project, name):
    """A member as its page shows it: what listing() says, and each version still held, newest
    first: {"n", "picture": whether there is one to show, "current"}."""
    lib, _, e = _member(client, project, name)
    v = int(e["version"])
    versions = [
        {"n": n, "picture": bool(_picture(lib, name, e, n)), "current": n == v}
        for n in range(v, max(0, v - library.KEEP), -1)
        if _file(lib, name, e, n)
    ]
    return library._listed(name, e) | {"versions": versions}


def picture(client, project, name, n=None):
    """The path of a version's picture (the newest when n is None), or None."""
    try:
        lib, _, e = _member(client, project, name)
    except AssetError:
        return None
    n = int(e["version"]) if n is None else n
    if not 0 < n <= int(e["version"]):
        return None
    return _picture(lib, name, e, n)


def episode_of(idx):
    """One of the library's episodes whose manifest (fonts, frame) a member can be drawn with."""
    for fid in idx.get("films") or []:
        f = Film.open(fid)
        if f and os.path.exists(f.manifest):
            return f
    return None


def draw(d, idx, items, episode, sizes=(480,)):
    """Each drawn member alone, with the library's whole current cast loaded:
    {size: {name: image}}. items: [{"name", "code"}]. Raises AssetError when it does not render."""
    stage = Stage(tempfile.mkdtemp(prefix="asset-draw-"), None)
    try:
        os.makedirs(stage.path("cast"))
        for n, e in idx["cast"].items():
            src = os.path.join(d, "cast", n, "v%d.js" % e["version"])
            if not e.get("deleted") and os.path.exists(src):
                shutil.copyfile(src, stage.path("cast", n + ".js"))
        for it in items:
            with open(stage.path("cast", it["name"] + ".js"), "w", encoding="utf-8") as f:
                f.write(it["code"])
        stage.manifest = stage.path("sketch.json")
        shutil.copyfile(episode.manifest, stage.manifest)
        with open(episode.manifest, encoding="utf-8") as f:
            fonts = json.load(f).get("fonts", [])
        for ft in fonts:  # the episode's own (fonts/, web/fonts/), where the manifest names them
            src = episode.path(*ft["file"].split("/"))
            if os.path.exists(src):
                os.makedirs(os.path.dirname(stage.path(*ft["file"].split("/"))), exist_ok=True)
                shutil.copyfile(src, stage.path(*ft["file"].split("/")))
        names = [it["name"] for it in items]
        man, times = library.sheet(stage, names)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
            + ["--manifest", man, "--stills", ",".join("%g" % t for t in times)]
            + ["--into", stage.path("temp", "castsheet", "stills")],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode:
            raise AssetError(500, "It did not draw:\n" + (r.stdout + r.stderr)[-1500:])
        return {s: library.thumbs(stage, names, s) for s in sizes}
    finally:
        shutil.rmtree(stage.dir, ignore_errors=True)


def put_drawn(lib, items, seen, pics, large=None, **meta):
    """Write each drawn member's next version, as a finished film's keep() would, under the
    library's lock. items: [{"name", "code", "hash", "about", "kind"}]; seen: {name: the hash the
    caller planned over, None for a new member} -- one that moved since is refused and nothing is
    written; pics / large: {name: image} from draw(). Returns {name: version}."""
    d = library.dir_of(lib)
    now = datetime.now().isoformat(timespec="seconds")
    large = large or {}
    with library._lock(lib):
        idx = library.load(lib)
        for it in items:
            e = idx["cast"].get(it["name"])
            if (e.get("hash") if e else None) != seen[it["name"]]:
                raise AssetError(
                    409, "%s changed in the project meanwhile: nothing was written." % it["name"]
                )
        out = {}
        for it in items:
            n = it["name"]
            e = idx["cast"].get(n) or {"version": 0, "films": [], "created": now, "from_film": None}
            v = e["version"] + 1
            md = os.path.join(d, "cast", n)
            os.makedirs(md, exist_ok=True)
            with open(os.path.join(md, "v%d.js" % v), "w", encoding="utf-8") as f:
                f.write(it["code"])
            for old in range(1, v - library.KEEP + 1):
                for x in ("js", "png"):
                    with contextlib.suppress(OSError):
                        os.remove(os.path.join(md, "v%d.%s" % (old, x)))
            tp = os.path.join(md, "thumb.png")
            if n in pics:
                pics[n].save(tp)
            elif os.path.exists(tp):
                os.remove(tp)
            if n in large:
                large[n].save(os.path.join(md, "v%d.png" % v))
            e.update(
                version=v,
                hash=it["hash"],
                about=it["about"] or e.get("about", ""),
                kind=it["kind"],
                updated=now,
                last_used=now,
                film=None,
                thumb=n in pics,
                **meta,
            )
            e.pop("deleted", None)
            idx["cast"][n] = e
            out[n] = v
        library._save(lib, idx)
        library._contact(lib, idx)
    return out


def member_of(name, code):
    """A drawn member's code as put_drawn takes it."""
    return {
        "name": name,
        "code": code,
        "hash": library._hash(code),
        "about": library._about(code),
        "kind": library._kind(code),
    }


def restore(client, project, name, n):
    """Version n becomes the newest again (as the next version). Returns info()."""
    lib, idx, e = _member(client, project, name)
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n == int(e["version"]):
        raise AssetError(409, "Version %d is the one in use." % n)
    src = _file(lib, name, e, n) if 0 < n < int(e["version"]) else None
    if not src:
        raise AssetError(404, "That version is no longer kept.")
    now = datetime.now().isoformat(timespec="seconds")
    if e.get("painted"):
        with library._lock(lib):
            idx = library.load(lib)
            cur = idx["cast"].get(name)
            if not cur or cur.get("deleted") or cur.get("hash") != e.get("hash"):
                raise AssetError(409, "%s changed in the project meanwhile: try again." % name)
            library._put_painted(lib, idx, name, src, cur.get("about"), now, restored=n)
            library._save(lib, idx)
            library._contact(lib, idx)
        return info(client, project, name)
    with open(src, encoding="utf-8") as f:
        it = member_of(name, f.read())
    episode = episode_of(idx)
    if not episode:
        raise AssetError(409, "This project has no episode to draw it with yet.")
    pics = draw(library.dir_of(lib), idx, [it], episode, (480, PICTURE))
    put_drawn(lib, [it], {name: e.get("hash")}, pics[480], pics[PICTURE], restored=n)
    return info(client, project, name)
