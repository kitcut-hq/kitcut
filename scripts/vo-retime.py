#!/usr/bin/env python
"""Keep a sketch film's sound effects on their words after its narration is recorded again.

sfx.json cues are in seconds, while the picture hangs off words (SK.w). Record the narration again --
a new voice direction, a fixed pronunciation, a line added -- and every word can land a few seconds
from where it was (the Leo episodes moved by up to 5 s, 2026-10-01): the picture follows, the boing
on "Bats!" stays where "Bats!" used to be. This moves each cue by what the narration around it did:
the words of the old timeline and the new are paired (lines matched by their text, so a line added
or removed is fine; words by position inside a line that kept its word count), and a cue's time is
carried along the piecewise-linear map between those pairs. Cues before the first word move with
it, cues after the last with the last.

    python scripts/vo-retime.py --manifest projects/<id>/sketch.json --before <old timeline.json>
    python scripts/vo-retime.py --manifest projects/<id>/sketch.json --before <old> --write

Without --write it only prints what would move (nothing is changed). With it, sfx.json is rewritten
and the old one kept as sfx.before-retime.json.

Invoke as:  python scripts/vo-retime.py --manifest <sketch.json> --before <timeline.json> [--write]
"""

import argparse
import bisect
import difflib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def norm(s):
    return re.sub(r"[^\w]", "", str(s).lower())


def anchors(old, new):
    """[(old seconds, new seconds)] from two timelines' lines: matched by text, then their words."""
    a = [norm(L["text"]) for L in old]
    b = [norm(L["text"]) for L in new]
    pairs = []
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            Lo, Ln = old[blk.a + k], new[blk.b + k]
            pairs += [(Lo["start"], Ln["start"]), (Lo["end"], Ln["end"])]
            wo, wn = Lo.get("words") or [], Ln.get("words") or []
            if len(wo) == len(wn):
                pairs += [(x["s"], y["s"]) for x, y in zip(wo, wn, strict=True)]
    pairs.sort()
    out = []  # keep the map monotonic: a pair that would run time backwards is left out
    for p in pairs:
        if not out or (p[0] > out[-1][0] and p[1] >= out[-1][1]):
            out.append(p)
    return out


def warp(t, pairs):
    if not pairs:
        return t
    xs = [p[0] for p in pairs]
    i = bisect.bisect_right(xs, t)
    if i == 0:
        return t + pairs[0][1] - pairs[0][0]
    if i == len(pairs):
        return t + pairs[-1][1] - pairs[-1][0]
    (x0, y0), (x1, y1) = pairs[i - 1], pairs[i]
    return y0 + (t - x0) * (y1 - y0) / (x1 - x0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True, help="the film's sketch.json")
    ap.add_argument(
        "--before", required=True, help="the narration's timeline.json before it was recorded again"
    )
    ap.add_argument("--write", action="store_true", help="rewrite sfx.json (else only print)")
    args = ap.parse_args()
    root = os.path.dirname(os.path.abspath(args.manifest))
    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)
    sfx_path = os.path.join(root, (m.get("audio") or {}).get("sfx") or "sfx.json")
    with open(args.before, encoding="utf-8") as f:
        old = json.load(f)["lines"]
    with open(os.path.join(root, "audio", "vo", "timeline.json"), encoding="utf-8") as f:
        new_tl = json.load(f)
    new = new_tl["lines"]
    pairs = anchors(old, new)
    with open(sfx_path, encoding="utf-8") as f:
        cues = json.load(f)
    dur = new_tl.get("duration") or m.get("duration") or 1e9
    moved = 0
    for c in cues:
        t = c.get("t")
        if not isinstance(t, (int, float)):
            continue
        n = round(min(max(0.0, warp(t, pairs)), dur - 0.05), 2)
        if abs(n - t) >= 0.05:
            moved += 1
            print("  %-10s %7.2f -> %7.2f  (%+.2f)" % (c.get("fx", "?"), t, n, n - t))
        c["t"] = n
    print("%d of %d cues move, on %d word and line anchors" % (moved, len(cues), len(pairs)))
    if args.write and moved:
        shutil.copyfile(sfx_path, os.path.join(root, "sfx.before-retime.json"))
        with open(sfx_path, "w", encoding="utf-8") as f:
            json.dump(cues, f, ensure_ascii=False, indent=1)
        print("-> %s (the old one: sfx.before-retime.json)" % sfx_path)
    elif not args.write:
        print("(--write to rewrite sfx.json)")


if __name__ == "__main__":
    main()
