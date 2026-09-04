#!/usr/bin/env python
"""Where does a channel park its caption card? Measured, not eyeballed.

Give it one or more of the channel's own published shorts and it reports the
vertical band their caption card occupies -- per video, and the consensus
across videos -- plus the `bottom_margin_px` (on the 1920x1080 authoring
canvas) that reproduces that position through `scale_style()`.

Why it exists: `lennys-podcast-vertical.json` carried a margin read off a
couple of paused frames, and the position still read as awkward on review.
`docs/todo.md` item 1b names the trap this tool closes: a single frame cannot
tell a caption box from a black turtleneck. The card comes and goes with
speech; the sweater is in every frame. So the discriminator is TEMPORAL --
per pixel row, over many sampled frames, how often does that row look like a
caption (a dark card region with bright text inside it)? Clothing rows are
dark in every frame but almost never carry bright text; caption rows carry
both, in most frames of a talking-head short.

The detector assumes the common shorts idiom this repo's presets share: a
dark card (or outline block) with light text, in the middle of the frame
width. That covers Lenny's Podcast (measured: #000000 card at alpha 115,
white text). A channel with light cards would need the thresholds flipped;
refuse loudly rather than guess (see --min-hit).

Free by nature -- it never writes anything. This is the measuring half of the
`## Step 0` procedure in the video-shorts skill.

Invoke as:
    python scripts/measure-caption-band.py projects/<id>/temp/ref/*.mp4
    python scripts/measure-caption-band.py a.mp4 b.mp4 --frames 60
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402

AUTHORING_H = 1080.0  # presets are authored on 1920x1080; scale_style scales
# bottom_margin_px by H/1080, so the authoring value is
# the measured output value divided by that ratio.


def row_caption_signal(frame, x0_frac=0.15, x1_frac=0.85):
    """Per-row booleans: does this row look like caption card + text?

    Dark-card pixels (luma < 70) must hold a real share of the row's central
    span, AND bright pixels (luma > 190) must be present -- text on the card.
    Either alone is ambiguous (a sweater; a white wall). Both together, on the
    same row, almost never happens outside a caption.
    """
    h, w = frame.shape[:2]
    band = frame[:, int(w * x0_frac) : int(w * x1_frac)]
    luma = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    dark = (luma < 70).mean(axis=1)
    bright = (luma > 190).mean(axis=1)
    return (dark > 0.20) & (bright > 0.008)


def measure(video, n_frames):
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit("cannot open %s" % video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # skip the first/last 5%: intros and end cards carry non-caption graphics
    lo, hi = int(total * 0.05), int(total * 0.95)
    idxs = np.linspace(lo, max(lo + 1, hi - 1), n_frames).astype(int)
    hits = np.zeros(h, dtype=float)
    used = 0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        hits += row_caption_signal(frame)
        used += 1
    cap.release()
    if not used:
        sys.exit("no readable frames in %s" % video)
    return hits / used, h, used


def band_from_hits(hits, min_hit):
    """The contiguous run of rows most often caption-like. Returns (y0, y1)
    of the longest run above threshold, or None when nothing clears it.
    """
    above = hits >= min_hit
    best, cur_start = None, None
    for y, a in enumerate(above):
        if a and cur_start is None:
            cur_start = y
        elif not a and cur_start is not None:
            if best is None or (y - cur_start) > (best[1] - best[0]):
                best = (cur_start, y)
            cur_start = None
    if cur_start is not None:
        y = len(above)
        if best is None or (y - cur_start) > (best[1] - best[0]):
            best = (cur_start, y)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("videos", nargs="+", help="the channel's own published shorts")
    ap.add_argument("--frames", type=int, default=48, help="frames sampled per video (default 48)")
    ap.add_argument(
        "--min-hit",
        type=float,
        default=0.30,
        help="a row must look caption-like in this fraction of "
        "frames to count (default 0.30). If nothing clears "
        "it the channel likely uses a light card -- measure "
        "by hand rather than lowering this blindly.",
    )
    args = ap.parse_args()

    print("caption band per video (dark card + light text, temporal):")
    bottoms, tops = [], []
    for v in args.videos:
        v = _env.resolve(v)
        hits, h, used = measure(v, args.frames)
        band = band_from_hits(hits, args.min_hit)
        name = os.path.basename(v)
        if band is None:
            print(
                "  %-24s NO band clears %.2f over %d frames -- light card, "
                "burned variety, or no captions" % (name, args.min_hit, used)
            )
            continue
        y0, y1 = band
        peak = hits[y0:y1].max()
        print(
            "  %-24s rows %4d..%4d of %d  (height %3d, from bottom %4d, "
            "peak presence %2d%%, %d frames)" % (name, y0, y1, h, y1 - y0, h - y1, 100 * peak, used)
        )
        bottoms.append((h - y1, h))
        tops.append(h - y0)

    if not bottoms:
        sys.exit("no video yielded a band; nothing to recommend")
    from_bottom = sorted(b for b, _ in bottoms)
    consensus = from_bottom[len(from_bottom) // 2]
    out_h = bottoms[0][1]
    authoring = consensus / (out_h / AUTHORING_H)
    print()
    print(
        "consensus: card bottom sits %d px above the frame bottom (median "
        "of %d videos)" % (consensus, len(bottoms))
    )
    print(
        "preset value: bottom_margin_px %d on the %dx1080 authoring canvas "
        "(scale_style multiplies by %.4f for %d-tall output)"
        % (round(authoring), int(AUTHORING_H * 16 / 9), out_h / AUTHORING_H, out_h)
    )


if __name__ == "__main__":
    main()
