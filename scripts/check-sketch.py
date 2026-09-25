#!/usr/bin/env python
"""Self-test for the sketch-film scripts: no API, no browser, no encode, seconds.

Exercises the pieces a paid or slow run would otherwise be the first to reach: the score
notation and every event type, every SFX and drum generator, the speech ducker, the
tail-word cut that fixes eleven_v3's clipped endings, word timings with [audio tags],
caption chunking, and the page bundler against the committed example film.

After touching _sketch.py, _sketchaudio.py, sketch-vo.py, sketch-audio.py, sketch-render.py or
anything under sketch/, run it.

Invoke as:  python scripts/check-sketch.py
"""

import sys
import os
import json
import shutil
import argparse
import tempfile
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _sketch  # noqa: E402
import _sketchaudio as A  # noqa: E402

SR = _sketch.SR
FAILS = []


def check(name, ok, detail=""):
    print(
        "%s  %s%s"
        % ("ok  " if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else "")
    )
    if not ok:
        FAILS.append(name)


def main():
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    # ---- notes and the score notation
    check("M() spellings", A.M("C4") == 60 and A.M("F#4") == A.M("Gb4") == 66 and A.M("Bb1") == 34)
    notes = A.parse_notes("1 E6 .5; 2 C4+E4+G4 1 .3")
    check(
        "parse_notes", notes == [(1.0, [88], 0.5, None), (2.0, [60, 64, 67], 1.0, 0.3)], str(notes)
    )
    score = {
        "bpm": 120,
        "events": [
            {"inst": "celesta", "vel": 0.4, "notes": "0 C5 1; 1 E5+G5 1", "transpose": 12},
            {"type": "strum", "at": 4, "chord": "C3+E3+G3", "vel": 0.5, "pattern": "half"},
            {
                "type": "gliss",
                "from": 8,
                "to": 9,
                "lo": "C4",
                "hi": "C5",
                "v0": 0.1,
                "v1": 0.4,
                "root": "C",
            },
            {
                "type": "roll",
                "inst": "timpani",
                "note": "C2",
                "from": 10,
                "to": 11,
                "step": 0.25,
                "v0": 0.1,
                "v1": 0.5,
            },
            {"type": "arp", "inst": "celesta", "at": 12, "notes": "C5 E5 G5", "step": 0.25},
            {
                "type": "drums",
                "from": 16,
                "bars": 2,
                "kit": {"kick": "x...x...x...x...", "hat": "o.o.o.o.o.o.o.o."},
            },
        ],
    }
    ev = A.score_events(score)
    kinds = {e[0] for e in ev}
    check("score: transpose", any(e[0] == "celesta" and e[1] == 84 for e in ev))
    check(
        "score: strum is 3 hits x 3 strings",
        sum(1 for e in ev if e[0] == "acoustic_guitar_nylon") == 9,
    )
    check("score: C major gliss has 8 notes", sum(1 for e in ev if e[0] == "orchestral_harp") == 8)
    check("score: roll steps", sum(1 for e in ev if e[0] == "timpani") == 5)
    check(
        "score: drums 2 bars",
        sum(1 for e in ev if e[0] == "drum") == 2 * (4 + 8),
        str(sum(1 for e in ev if e[0] == "drum")),
    )
    check(
        "score: drums need no samples",
        ("drum", "kick") not in A.needed_samples(ev) and "drum" in kinds,
    )
    try:
        A.score_events({"events": [{"type": "nope"}]})
        check("score: unknown type refused", False)
    except ValueError:
        check("score: unknown type refused", True)

    # ---- every generator makes finite, non-silent sound
    small = {"sec": 0.2}
    for name, f in sorted(A.FX.items()):
        args = dict(small) if "sec" in f.__code__.co_varnames else {}
        y = f(**args)
        check("fx %-12s" % name, y.size > 0 and np.isfinite(y).all() and np.abs(y).max() > 1e-4)
    for piece in A.DRUM_PAN:
        y = A.drum(piece)
        check("drum %-10s" % piece, y.size > 0 and np.isfinite(y).all() and np.abs(y).max() > 1e-4)
    check("drum seeds are stable", np.array_equal(A.drum("snare"), A.drum("snare")))

    # ---- ducking: full in the gaps, reduced under speech
    vo = np.zeros(SR * 3)
    vo[SR : 2 * SR] = np.sin(np.arange(SR) * 2 * np.pi * 200 / SR) * 0.3
    g = A.duck_gain(vo, amount=0.6)
    check("duck: 1.0 before speech", g[int(0.5 * SR)] > 0.98)
    check("duck: reduced under speech", g[int(1.6 * SR)] < 0.6, "%.2f" % g[int(1.6 * SR)])
    check("duck: recovers after", g[int(2.9 * SR)] > 0.8, "%.2f" % g[int(2.9 * SR)])

    # ---- the tail-word cut and word timing
    vo_mod = import_module("sketch-vo")
    tone = lambda s: np.sin(np.arange(int(s * SR)) * 2 * np.pi * 220 / SR) * 0.3  # noqa: E731
    x = np.concatenate([np.zeros(int(0.1 * SR)), tone(1.0), np.zeros(int(0.4 * SR)), tone(0.5)])
    text = "[soft] Hi there\n\nAlright."
    starts = []
    ends = []
    for i, _ch in enumerate(text):
        t0 = 0.1 + i * 0.08 if i < 15 else 1.5 + (i - 15) * 0.05
        starts.append(t0)
        ends.append(t0 + 0.07)
    align = {
        "characters": list(text),
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }
    y, lead, ok = vo_mod.cut_at_tail(x, align, "Alright.")
    check("tail: cut found a clean gap", ok)
    check("tail: tail removed, line kept", 0.95 < len(y) / SR < 1.3, "%.2fs" % (len(y) / SR))
    words = vo_mod.word_times(align, lead, "Alright.")
    check(
        "words: [tags] and tail dropped",
        [w["text"] for w in words] == ["Hi", "there"],
        str([w["text"] for w in words]),
    )

    # ---- captions
    tl = {
        "duration": 10,
        "lines": [
            {
                "start": 0,
                "end": 4,
                "words": [
                    {"text": t, "s": i * 0.4, "e": i * 0.4 + 0.3}
                    for i, t in enumerate(
                        "One two three. Four five six seven eight nine ten eleven.".split()
                    )
                ],
            }
        ],
    }
    cues = _sketch.captions(tl, max_words=9)
    check(
        "captions: split at the sentence end",
        cues[0][2] == "One two three." and len(cues) == 2,
        str(cues),
    )

    # ---- the bundler, against the committed example
    ex = os.path.join(_env.ROOT, "config", "sketch", "example")
    tmp = tempfile.mkdtemp(prefix="check-sketch-")
    try:
        shutil.copytree(ex, os.path.join(tmp, "example"))
        m = _sketch.load(os.path.join(tmp, "example", "sketch.json"))
        render = import_module("sketch-render")
        page = render.bundle(m, audio=False)
        left = [
            k
            for k in (
                "__TITLE__",
                "__ENGINE__",
                "__PROPS__",
                "__FILM__",
                "__FONTFACES__",
                "__VO__",
                "__IMAGES__",
            )
            if k in page
        ]
        check("bundle: every placeholder filled", not left, str(left))
        check("bundle: fonts inlined", "data:font/woff2;base64," in page)
        art = render.artifact_flavour(page)
        check(
            "artifact: no html/head/body wrapper",
            "<html" not in art and "<head>" not in art and "<body>" not in art and "<title>" in art,
        )
        with open(os.path.join(ex, "score.json"), encoding="utf-8") as f:
            ev = A.score_events(json.load(f))
        check("example score parses", len(ev) > 20, str(len(ev)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
