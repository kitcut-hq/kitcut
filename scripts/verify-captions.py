#!/usr/bin/env python
"""Prove the burned-in captions are actually in sync.

Renders the caption layer alone onto a synthetic black source (no video content
to confuse colour detection, every non-black pixel is unambiguously a caption),
probes frames at chosen word timestamps, and asserts that the word rendered in
the ACTIVE colour is the word that should be active at that instant.

Classification is nearest-colour, not exact match: robust to antialiasing,
outline bleed and JPEG-ish artefacts, unlike counting exact pixel values.

Words whose ACTIVE window is under two frames are not probed. A one-frame probe
cannot decide them: ASS timestamps are centisecond-quantised and every event
fades, so the highlight can legitimately render a frame either side. Skipping
them is printed, never silent -- see the note at the filter for the measured
case that motivated it.

Invoke as:  python scripts/verify-captions.py ...
"""

import sys
import os
import json
import argparse
import subprocess
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import


import numpy as np

from PIL import Image

ENV = _env.ENV


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)], dtype=float)


def probe(ass, fontsdir, t, png, fps=60.0, size=(1920, 1080)):
    """Frame n covers [n/fps,(n+1)/fps). Sample the MIDDLE of the frame that
    contains t, so we read the frame libass actually rendered for that instant.
    """
    n = int(t * fps)
    tm = (n + 0.5) / fps
    # Do NOT seek: a short synthetic source has no frame at tm, and seeking would
    # rebase PTS to 0 so libass would look up the wrong dialogue lines anyway.
    # Instead push the single frame's PTS onto the real timeline for the ass
    # filter, then pull it back. Same fix as the preview-clip render.
    vf = "setpts=PTS+%.5f/TB,ass=filename=%s:fontsdir=%s:shaping=simple,setpts=PTS-%.5f/TB" % (
        tm,
        ass,
        fontsdir,
        tm,
    )
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=%dx%d:r=%g:d=0.05" % (size[0], size[1], fps),
        "-vf",
        vf,
        "-frames:v",
        "1",
        png,
    ]
    subprocess.run(cmd, env=ENV, check=True)
    return np.array(Image.open(png).convert("RGB"), dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", required=True, help="captions debug sidecar json")
    ap.add_argument("--style", required=True)
    ap.add_argument("--ass", required=True)
    ap.add_argument("--fontsdir", default="fonts")
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--fps",
        type=float,
        default=60.0,
        help="video frame rate; probe times snap to frame midpoints",
    )
    ap.add_argument("--tmp", default="temp/_probe.png")
    args = ap.parse_args()

    cfg = json.load(open(args.style, encoding="utf-8"))
    dbg = json.load(open(args.debug, encoding="utf-8"))
    base = hex_rgb(cfg["states"]["base"]["colour"])
    act = hex_rgb(cfg["states"]["active"]["colour"])

    # Read the resolved font size AND canvas out of the ASS rather than the
    # config: size may be derived from cap_height_px, and the canvas may have
    # been scaled to the actual video dimensions. The ASS is the ground truth.
    fsize = cfg["font"].get("size")
    size = [1920, 1080]
    for line in open(args.ass, encoding="utf-8"):
        if line.startswith("PlayResX:"):
            size[0] = int(line.split(":")[1])
        elif line.startswith("PlayResY:"):
            size[1] = int(line.split(":")[1])
        elif line.startswith("Style: Base,"):
            fsize = float(line.split(",")[2])
            break
    if not fsize:
        sys.exit("could not determine font size")

    # only groups with >1 word can demonstrate a spotlight
    cand = [(g, wi) for g in dbg if len(g["words"]) > 1 for wi in range(len(g["words"]))]

    # A word whose ACTIVE window is not comfortably wider than one frame cannot
    # be asserted by a one-frame probe, so probing it produces false failures.
    # The probe samples the midpoint of the frame containing the word's own
    # midpoint; ASS timestamps are centisecond-quantised and every event carries
    # a fade, so for a window of a frame or two the highlight can legitimately
    # land on the neighbouring frame. Measured case: DOU SKv9fUHeckE clip 01, the
    # conjunction 'І' active 15.73->15.77 -- 4 cs, EXACTLY one frame at 25 fps --
    # probed at 15.74 and rendered with the previous word still yellow. A
    # one-frame lag on a one-frame word is both invisible and unfixable (it is
    # the shortest thing the format can express), so asserting it buys no safety.
    # This is a scope limit on the probe, NOT a softened threshold: every word
    # wide enough to be judged is still judged, and the skipped count is printed
    # so a preset that quietly shrinks every highlight cannot hide behind it.
    min_active_s = 2.0 / args.fps
    wide = [
        (g, wi)
        for (g, wi) in cand
        if (g["words"][wi]["b"] - g["words"][wi]["a"]) / 100.0 >= min_active_s
    ]
    skipped = len(cand) - len(wide)
    if skipped:
        print(
            "skipping %d/%d candidate word(s) with an active window under "
            "%.0f ms (2 frames at %g fps) -- too short for a 1-frame probe to judge"
            % (skipped, len(cand), min_active_s * 1000.0, args.fps)
        )
    if not wide:
        sys.exit(
            "no word has an active window of at least %.0f ms -- nothing "
            "probeable; check the preset's timing block" % (min_active_s * 1000.0)
        )
    cand = wide

    random.seed(args.seed)
    picks = random.sample(cand, min(args.samples, len(cand)))
    picks.sort(key=lambda p: p[0]["words"][p[1]]["a"])

    ok = fail = 0
    failures = []
    for g, wi in picks:
        w = g["words"][wi]
        t = (w["a"] + w["b"]) / 2.0 / 100.0
        img = probe(args.ass, args.fontsdir, t, args.tmp, args.fps, tuple(size))

        # Half-height of a word's sampling box. fsize is the NOMINAL font size,
        # which is taller than the line spacing in any tight-leading preset --
        # so on a two-line card the box for a word on line 1 reaches down into
        # line 2 and reads its colour. That made a correct ASS fail: the probe
        # sampled the mint spotlight from the word underneath and reported the
        # wrong word highlighted. Clamp the box to stay inside its own line.
        rows = sorted({round(ww["cy"], 1) for ww in g["words"]})
        gap = min((b - a for a, b in zip(rows, rows[1:])), default=fsize)
        half = min(fsize / 2.0, gap * 0.45)

        scores = []
        for j, ww in enumerate(g["words"]):
            x0 = int(ww["cx"] - ww["w"] / 2) - 2
            x1 = int(ww["cx"] + ww["w"] / 2) + 2
            y0 = int(ww["cy"] - half)
            y1 = int(ww["cy"] + half)
            box = img[max(0, y0) : y1, max(0, x0) : x1]
            if box.size == 0:
                scores.append(1e9)
                continue
            lum = box.sum(axis=2)
            mask = lum > lum.max() * 0.55 if lum.max() > 60 else None
            if mask is None or mask.sum() < 5:
                scores.append(1e9)
                continue
            mean = box[mask].mean(axis=0)
            d_act = np.linalg.norm(mean - act)
            d_base = np.linalg.norm(mean - base)
            scores.append(d_act - d_base)  # most negative = most active-like

        got = int(np.argmin(scores))
        if got == wi:
            ok += 1
        else:
            fail += 1
            failures.append((t, g["gi"], w["t"], g["words"][got]["t"]))

    print("sync probes: %d/%d correct" % (ok, ok + fail))
    for t, gi, expect, gotw in failures[:15]:
        print(
            "  MISMATCH t=%.2fs group %d: expected '%s' highlighted, got '%s'"
            % (t, gi, expect, gotw)
        )
    if os.path.exists(args.tmp):
        os.remove(args.tmp)
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
