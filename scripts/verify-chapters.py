#!/usr/bin/env python
"""Print what is actually being said at each chapter mark, to review a list.

A lint proves a chapter file is well-formed. It cannot prove the timestamps
mean anything -- plausible titles against invented times pass every structural
check and are wrong in the only way that matters. So this puts the transcript
next to the marks: for each one, the words that follow it. Reading title
against speech is the check; there is no way to automate it that works.

WHAT THIS DELIBERATELY DOES NOT DO is fail a mark for not following a pause.
That was the first design, and measuring killed it. Across these transcripts a
0.3s pause sits in front of authored marks more often than chance -- median gap
0.59s vs 0.18s for random times on one video -- but roughly half of RANDOM
timestamps clear the same bar, because the speakers barely pause. As a gate it
flagged five marks in the channel's own published, working chapters. A check
that cries wolf on known-good input is worse than no check, so the pause is
printed as context and nothing more.

The one genuine error it does enforce is a mark past the end of the speech.

Invoke as:
  python scripts/verify-chapters.py config/chapters/<id>.txt
  python scripts/verify-chapters.py "config/chapters/*.txt"
"""

import sys
import os
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _ytchapters as ch  # noqa: E402


def load_words(path):
    d = json.load(open(path, encoding="utf-8"))
    words = d["words"] if isinstance(d, dict) else d
    return [
        {"t": float(w["start"]), "e": float(w["end"]), "x": w.get("text", w.get("word", ""))}
        for w in words
    ]


def at(words, t):
    """(index of the first word starting at or after t, pause before it)."""
    for i, w in enumerate(words):
        if w["t"] >= t - 0.5:
            gap = w["t"] - words[i - 1]["e"] if i else 99.0
            return i, gap
    return None, None


def review(chapters_path, words_path, width):
    marks = ch.parse_marks(
        "".join(l for l in open(chapters_path, encoding="utf-8") if not l.strip().startswith("#"))
    )
    words = load_words(words_path)
    end = words[-1]["e"] if words else 0
    errors = 0

    print(
        f"\n{'=' * 78}\n{os.path.basename(chapters_path)}  "
        f"{len(marks)} marks, speech ends {ch.fmt_ts(end)}\n"
    )
    for t, line in marks:
        title = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
        i, gap = at(words, t)
        print(f"  {ch.fmt_ts(t):>6}  {title}")
        if i is None:
            print("          !! ERROR: past the end of the speech")
            errors += 1
            continue
        said = " ".join(w["x"] for w in words[i : i + 24])
        print(f"          [{gap:4.2f}s] {said[:width]}")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("chapters", nargs="+")
    ap.add_argument("--transcripts", default="transcripts")
    ap.add_argument("--width", type=int, default=110)
    args = ap.parse_args()

    paths = []
    for p in args.chapters:
        paths += sorted(glob.glob(p)) or [p]

    errors = 0
    for p in paths:
        vid = os.path.splitext(os.path.basename(p))[0]
        wp = os.path.join(args.transcripts, f"{vid}.words.json")
        if not os.path.exists(wp):
            print(f"\n{os.path.basename(p)} -- no transcript, skipped")
            continue
        errors += review(p, wp, args.width)

    print(f"\n{errors} marks past the end of the speech")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
