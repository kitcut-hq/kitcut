#!/usr/bin/env python
"""Which shipped renders carry whisper's split-punctuation defect on a card?

The loader now glues whisper's suffix tokens ("60" + ",000" -> "60,000"), so
every NEW render is clean -- but renders made before the fix may have burned
"60 ,000" onto their cards. A transcript's dirty-token count says nothing by
itself: 77 dirty tokens in a 40-minute interview are harmless if none fall
inside a rendered clip's window. This audit answers the only question that
matters -- per recorded deliverable, how many glue merges land INSIDE its
actual window -- so re-render decisions are taken on numbers, not vibes.

Free by nature: it reads project.json files, transcripts and clip sidecars,
renders nothing, writes nothing. Deliverables it cannot window (no clip
sidecar on disk, dubbed cuts whose captions come from dub words) are listed
as skipped rather than silently guessed.

Invoke as:  python scripts/audit-caption-glue.py
            python scripts/audit-caption-glue.py --id <project>
"""

import sys
import os
import json
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_outline = import_module("transcript-outline")
_project = import_module("_project")


def load_raw_words(path):
    """The transcript exactly as whisper wrote it -- no glue. The loader glues
    now, so the BEFORE picture has to come from the file directly.
    """
    d = json.load(open(path, encoding="utf-8"))
    words = d["words"] if isinstance(d, dict) else d
    return [w for w in words if isinstance(w, dict) and w.get("text")]


def merges_in_window(raw, t0, t1):
    span = [w for w in raw if t0 <= w["start"] <= t1]
    glued = _outline.glue_words(span)
    examples = [
        g["text"]
        for g in glued
        if any(
            g["text"].endswith(s["text"]) and g["text"] != s["text"]
            for s in span
            if _outline.glues_back(s["text"])
        )
    ]
    return len(span) - len(glued), examples[:3]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id", default=None, help="one project (default: all)")
    args = ap.parse_args()

    pdir = _project.projects_dir()
    ids = (
        [args.id]
        if args.id
        else sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(pdir, "*"))
            if os.path.isfile(os.path.join(p, "project.json"))
        )
    )

    dirty, clean, skipped = [], 0, []
    for pid in ids:
        pj = os.path.join(pdir, pid, "project.json")
        try:
            proj = json.load(open(pj, encoding="utf-8"))
        except Exception as e:
            skipped.append((pid, "-", "unreadable project.json: %s" % e))
            continue
        for out, dl in (proj.get("deliverables") or {}).items():
            burned = " ".join(dl.get("burned") or [])
            if "caption" not in burned:
                continue
            name = os.path.basename(out)
            if dl.get("kind") == "short-dubbed":
                skipped.append((pid, name, "dubbed -- captions come from dub words"))
                continue
            man = dl.get("manifest")
            mpath = _env.resolve(man) if man else None
            if not mpath or not os.path.exists(mpath):
                skipped.append((pid, name, "manifest missing: %s" % man))
                continue
            m = json.load(open(mpath, encoding="utf-8"))
            wpath = _env.resolve(m.get("words", ""))
            if not m.get("words") or not os.path.exists(wpath):
                skipped.append((pid, name, "transcript not on disk"))
                continue
            raw = load_raw_words(wpath)
            clip_sc = (dl.get("sidecars") or {}).get("clip")
            if clip_sc and os.path.exists(_env.resolve(clip_sc)):
                sc = json.load(open(_env.resolve(clip_sc), encoding="utf-8"))
                t0, t1 = float(sc["start"]), float(sc["end"])
            elif dl.get("kind") == "captions":
                t0, t1 = 0.0, float("inf")  # whole-video captions
            else:
                skipped.append((pid, name, "no clip sidecar on disk"))
                continue
            n, ex = merges_in_window(raw, t0, t1)
            if n:
                dirty.append((pid, name, n, ex, dl.get("status", "?"), dl.get("built_utc", "?")))
            else:
                clean += 1

    if dirty:
        print(
            "deliverables whose window CONTAINS glue-merge sites (a render "
            "built after the loader fix landed is already clean -- check "
            "built_utc against the fix commit):"
        )
        for pid, name, n, ex, status, built in sorted(dirty, key=lambda r: -r[2]):
            print(
                "  %-16s %-52s %2d merge(s)  built %s  [%s]  e.g. %s"
                % (pid, name, n, built, status, ", ".join(ex) or "-")
            )
    print("\n%d dirty | %d clean | %d skipped" % (len(dirty), clean, len(skipped)))
    for pid, name, why in skipped:
        print("  skip %-16s %-52s %s" % (pid, name, why))


if __name__ == "__main__":
    main()
