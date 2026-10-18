#!/usr/bin/env python
"""Put an actor pack into a project's library by hand: every next episode of the project gets it.

    python studio/actor_put.py --project p-myodgkrkbv [--name N] [--about TEXT] [--replace]
                               [--dry-run] <pack folder>
    python studio/actor_put.py --project p-myodgkrkbv --list
    python studio/actor_put.py --project p-myodgkrkbv --remove <name>

A pack is the folder scripts/actor-pack.py writes: pack.json, atlas-<n>.webp and check.jpg are
taken, nothing else (its raw/ and design/ pictures and its spend log stay behind). It is checked
first (library.read_pack): every piece its faces and poses name is on a page it holds, and the
whole is small enough for every episode to carry. Each next episode then gets it in actors/<name>/,
in its manifest's "actors" and its prompt's "The actors" (library._seed_actors); an episode being
made already keeps what it was given.

  --name      the name its episodes draw it by, SK.actor('<name>', ...) (default: the pack's own)
  --about     who it is, for the episodes' Claude (default: the pack's own, its spec's describe)
  --replace   a name the project already has: this pack takes its place
  --dry-run   checks the pack and says what it would write; writes nothing

The library's own lock is held while it writes (library._lock), so an episode starting meanwhile
gets the old pack or the new one, never half of one.
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import library  # noqa: E402
from library_put import find  # noqa: E402


def show(name, e):
    print(
        "%-12s %d faces (speaks in %s), %d poses, %d page%s, %.1f MB, added %s"
        % (
            name,
            len(e.get("faces") or []),
            ", ".join(e.get("talk") or []) or "none",
            len(e.get("poses") or []),
            e.get("pages") or 0,
            "" if e.get("pages") == 1 else "s",
            (e.get("bytes") or 0) / 1e6,
            (e.get("added") or "?")[:16],
        )
    )
    if e.get("about"):
        print("             %s" % e["about"][:200])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--name")
    ap.add_argument("--about")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true", help="the project's actors")
    ap.add_argument("--remove", metavar="NAME", help="take this actor out of the project")
    ap.add_argument("pack", nargs="?", help="the folder actor-pack.py wrote")
    a = ap.parse_args()
    _, lib, _ = find(a.project)
    if a.list:
        got = library.load(lib)["actors"]
        for n, e in sorted(got.items()):
            show(n, e)
        print("%d actor%s in %s" % (len(got), "" if len(got) == 1 else "s", a.project))
        return
    if a.remove:
        if a.dry_run:
            there = a.remove in library.load(lib)["actors"]
            print("would remove %s" % a.remove if there else "%s: no such actor" % a.remove)
            return
        if not library.delete_actor(lib, a.remove):
            sys.exit("%s: no such actor in %s" % (a.remove, a.project))
        print("removed %s from %s: its next episodes are made without it" % (a.remove, a.project))
        return
    if not a.pack:
        ap.error("a pack folder, --list or --remove")
    try:
        P, files = library.read_pack(a.pack)
    except library.ActorError as e:
        sys.exit(e.text)
    name = a.name or str(P.get("name") or "")
    idx = library.load(lib)
    there = name in idx["actors"]
    print(
        "%s: %s, %d faces, %d poses, %s"
        % (
            name,
            "replaces the project's" if there else "new",
            len(P["faces"]),
            len(P["poses"]),
            ", ".join(files),
        )
    )
    if a.dry_run:
        if there and not a.replace:
            print("(the project already has %s: --replace would put this pack in its place)" % name)
        print("dry run: nothing written")
        return
    try:
        e = library.put_actor(lib, a.pack, name=name, replace=a.replace, about=a.about)
    except library.ActorError as err:
        sys.exit(
            err.text
            + (" (--replace puts this pack in its place)" if err.status == 409 and there else "")
        )
    show(e.pop("name"), e)
    print("in %s: its next episodes get it as SK.actor('%s', ...)" % (a.project, name))


if __name__ == "__main__":
    main()
