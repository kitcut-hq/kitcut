#!/usr/bin/env python
"""Put cast members into a project's library by hand: a back-fill, not a film.

    python studio/library_put.py --project p-myodgkrkbv [--dry-run] [--out DIR] cast/room.js ...

What a series' episodes drew in their own film.js (a room, a house, a street) never reached the
library; this takes such a member, written as a cast file (`SK.cast.<name> = {...}`, a place with
kind: 'place'), and makes it the library's next version of that name, as a finished film's keep()
would: each one drawn alone for its thumbnail (library.sheet, with every current member loaded, so
a place drawn by a character's file finds it), the sheet (cast.png) redrawn, and the member
marked used now, so the next episode is seeded with it.

  --dry-run   draws the thumbnails (into --out, when given) and says what it would write; writes
              nothing to the library
  --replace   a member the library already has, with other code, becomes a new version of it;
              without it that is refused (an episode may have changed it since you copied it)

A member the library already has with the same code is left as it is. The library's own lock is
held while it writes (library._lock), so an episode finishing meanwhile cannot interleave; a
member that changed between the plan and the write is refused, never written over.
"""

import os
import re
import sys
import glob
import json
import shutil
import argparse
import tempfile
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import library  # noqa: E402
from film import KIT, Film  # noqa: E402

DECLARES = re.compile(r"\bSK\.cast\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{")


class Stage:
    """Enough of a film for library.sheet/thumbs: a folder with a manifest and a cast/."""

    def __init__(self, d, manifest):
        self.dir, self.manifest = d, manifest

    def path(self, *p):
        return os.path.join(self.dir, *p)


def find(project):
    """The project's library folder and its (client, project), read off one of its episodes."""
    dirs = glob.glob(os.path.join(library.ROOT, "*", project))
    if len(dirs) != 1:
        sys.exit("project %s: %d libraries found" % (project, len(dirs)))
    idx = json.load(open(os.path.join(dirs[0], "index.json"), encoding="utf-8"))
    for fid in idx.get("films") or []:
        f = Film.open(fid)
        if f and f.record().get("client"):
            lib = library.lib_of(f.record())
            if lib and os.path.normcase(library.dir_of(lib)) == os.path.normcase(dirs[0]):
                return dirs[0], lib, f
    sys.exit("project %s: no episode names its library" % project)


def read_member(path):
    code = open(path, encoding="utf-8").read()
    names = DECLARES.findall(code)
    if len(names) != 1 or not library.NAME.match(names[0]):
        sys.exit("%s: declares %s; a cast file registers one lowercase member" % (path, names))
    if os.path.basename(path) != names[0] + ".js":
        sys.exit("%s: registers %s, so it is %s.js" % (path, names[0], names[0]))
    if len(code.encode("utf-8")) > library.MAX_BYTES:
        sys.exit("%s: over %d bytes" % (path, library.MAX_BYTES))
    h = library._hash(code)
    return {
        "name": names[0],
        "code": code,
        "hash": h,
        "about": library._about(code),
        "kind": library._kind(code),
    }


def draw(d, idx, items, episode, out):
    """Each member drawn alone, with the library's whole current cast loaded: {name: image}."""
    stage = Stage(tempfile.mkdtemp(prefix="library-put-"), None)
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
            sys.exit("the cast sheet did not render:\n" + (r.stdout + r.stderr)[-1500:])
        pics = library.thumbs(stage, names)
        if out:
            os.makedirs(out, exist_ok=True)
            for n, im in pics.items():
                im.save(os.path.join(out, n + ".png"))
        return pics
    finally:
        shutil.rmtree(stage.dir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--out", help="also save each thumbnail here")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    d, lib, episode = find(a.project)
    idx = library.load(lib)
    items, seen = [], {}
    for p in a.files:
        it = read_member(p)
        e = idx["cast"].get(it["name"])
        if e and e.get("hash") == it["hash"] and not e.get("deleted"):
            print("%-12s unchanged (v%d): left as it is" % (it["name"], e["version"]))
            continue
        if e and not e.get("deleted") and not a.replace:
            sys.exit(
                "%s: the library has v%d with other code; --replace makes this v%d"
                % (it["name"], e["version"], e["version"] + 1)
            )
        seen[it["name"]] = e.get("hash") if e else None
        items.append(it)
        print(
            "%-12s %s v%d, %s, %d bytes: %s"
            % (
                it["name"],
                "new" if not e else "replaces",
                (e["version"] if e else 0) + 1,
                it["kind"] or "a character or thing",
                len(it["code"]),
                it["about"][:90],
            )
        )
    if not items:
        return
    pics = draw(d, idx, items, episode, a.out)
    for it in items:
        print(
            "%-12s thumbnail: %s"
            % (
                it["name"],
                "%dx%d" % pics[it["name"]].size
                if it["name"] in pics
                else "NONE (it drew nothing alone)",
            )
        )
    if a.dry_run:
        print("dry run: nothing written to %s" % d)
        return
    now = datetime.now().isoformat(timespec="seconds")
    with library._lock(lib):
        idx = library.load(lib)
        for it in items:  # nothing may have moved since the plan
            e = idx["cast"].get(it["name"])
            if (e.get("hash") if e else None) != seen[it["name"]]:
                sys.exit("%s changed in the library meanwhile: nothing written" % it["name"])
        for it in items:
            n = it["name"]
            e = idx["cast"].get(n) or {"version": 0, "films": [], "created": now, "from_film": None}
            v = e["version"] + 1
            md = os.path.join(d, "cast", n)
            os.makedirs(md, exist_ok=True)
            with open(os.path.join(md, "v%d.js" % v), "w", encoding="utf-8") as f:
                f.write(it["code"])
            for old in range(1, v - library.KEEP + 1):
                try:
                    os.remove(os.path.join(md, "v%d.js" % old))
                except OSError:
                    pass
            tp = os.path.join(md, "thumb.png")
            if n in pics:
                pics[n].save(tp)
            elif os.path.exists(tp):
                os.remove(tp)
            e.update(
                version=v,
                hash=it["hash"],
                about=it["about"] or e.get("about", ""),
                kind=it["kind"],
                updated=now,
                last_used=now,
                film=None,
                by_hand=now,
                thumb=n in pics,
            )
            e.pop("deleted", None)
            idx["cast"][n] = e
        library._save(lib, idx)
        library._contact(lib, idx)
    print(
        "written: %s"
        % ", ".join("%s v%d" % (it["name"], idx["cast"][it["name"]]["version"]) for it in items)
    )


if __name__ == "__main__":
    main()
