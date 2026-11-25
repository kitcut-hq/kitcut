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
import sys
import glob
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets  # noqa: E402
import library  # noqa: E402
from film import Film  # noqa: E402

DECLARES = library.DECLARES


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
    if len(code.encode("utf-8")) > library.max_bytes(code):
        sys.exit("%s: over %d bytes" % (path, library.max_bytes(code)))
    h = library._hash(code)
    return {
        "name": names[0],
        "code": code,
        "hash": h,
        "about": library._about(code),
        "kind": library._kind(code),
    }


def draw(d, idx, items, episode, out):
    """Each member drawn alone (assets.draw): ({name: thumbnail}, {name: large picture})."""
    try:
        pics = assets.draw(d, idx, items, episode, (480, assets.PICTURE))
    except assets.AssetError as e:
        sys.exit("the cast sheet did not render:\n" + e.text)
    if out:
        os.makedirs(out, exist_ok=True)
        for n, im in pics[480].items():
            im.save(os.path.join(out, n + ".png"))
    return pics[480], pics[assets.PICTURE]


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
    pics, large = draw(d, idx, items, episode, a.out)
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
    try:
        wrote = assets.put_drawn(lib, items, seen, pics, large, by_hand=now)
    except assets.AssetError as e:
        sys.exit(e.text)
    print("written: %s" % ", ".join("%s v%d" % (n, v) for n, v in wrote.items()))


if __name__ == "__main__":
    main()
