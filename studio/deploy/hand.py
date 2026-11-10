#!/usr/bin/env python
"""The laptop's half of changing a finished film by hand (ops.sh take, ops.sh put). Stdlib only.

    python studio/deploy/hand.py stamp <dir> '<json from rounds.py --where>'
    python studio/deploy/hand.py changed <dir> <film-id>

`stamp` writes <dir>/.kitcut-take.json beside files just taken from the VM: the film, the
version it was at, what that version is made of (the studio's digest), and every file's own
hash. `changed` reads it back and prints, one a line, the files that are new or not what was
taken -- the only ones `put` sends -- after the stamp's first line of JSON. The studio accepts
them only while the film is still what the stamp says it was (rounds.clean_hand), which is the
point: a film changed since, from its maker's notes or by anyone, is never replaced by files that
did not start from it (KI-061).
"""

import hashlib
import json
import os
import sys

STAMP = ".kitcut-take.json"
# never a version's to change (rounds.OWN), and what a preview leaves beside the film
SKIP = (
    "studio.json",
    "events.jsonl",
    "temp",
    "notes",
    "versions",
    "library",
    "share",
    "youtube",
    "project.json",
    "journal.md",
    "outputs",
)


def files(d):
    """{path from d, forward slashes: sha256}, without the stamp, dot-files, SKIP and review*/."""
    out = {}
    for root, dirs, names in os.walk(d):
        rel = os.path.relpath(root, d).replace(os.sep, "/")
        if rel == ".":
            dirs[:] = [
                n
                for n in dirs
                if n not in SKIP and not n.startswith(".") and not n.startswith("review")
            ]
            names = [n for n in names if n not in SKIP and not n.startswith(".")]
        for n in names:
            h = hashlib.sha256()
            with open(os.path.join(root, n), "rb") as f:
                for part in iter(lambda: f.read(1 << 20), b""):
                    h.update(part)
            out[n if rel == "." else rel + "/" + n] = h.hexdigest()
    return out


def stamp(d, at):
    at = json.loads(at)
    if at.get("state") != "done":
        sys.exit("%s is %s, not a finished film" % (at.get("film"), at.get("state")))
    if at.get("round"):
        sys.exit(
            "a version of %s is being made from its maker's notes: take it when that is done"
            % at.get("film")
        )
    took = {k: at[k] for k in ("film", "version", "digest")} | {"files": files(d)}
    with open(os.path.join(d, STAMP), "w", encoding="utf-8") as f:
        json.dump(took, f, indent=1)
    print("%s version %d: %d files in %s" % (took["film"], took["version"], len(took["files"]), d))


def changed(d, film):
    try:
        with open(os.path.join(d, STAMP), encoding="utf-8") as f:
            took = json.load(f)
    except (OSError, ValueError):
        sys.exit("%s was not taken with ops.sh take (no %s): take the film first" % (d, STAMP))
    if took.get("film") != film:
        sys.exit("%s holds %s, not %s" % (d, took.get("film"), film))
    now = files(d)
    gone = sorted(set(took["files"]) - set(now))
    if gone:
        print(
            "not sent (a file removed here stays in the film): %s" % ", ".join(gone),
            file=sys.stderr,
        )
    out = sorted(n for n, h in now.items() if took["files"].get(n) != h)
    if not out:
        sys.exit("nothing in %s differs from what was taken" % d)
    print(json.dumps({k: took[k] for k in ("film", "version", "digest")}))
    print("\n".join(out))


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("stamp", "changed"):
        sys.exit(__doc__)
    (stamp if sys.argv[1] == "stamp" else changed)(sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
