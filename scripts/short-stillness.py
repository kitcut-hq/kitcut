#!/usr/bin/env python
"""How much of a Short's picture stands still: the check behind the Shorts guidebook's rule 33.

A wide film can hold a diagram while the narrator explains it. A Short cannot: the first raw cut
of five padel Shorts (2026-10-09) was the wide film's scenes fitted into a tall frame, and the
owner's whole answer was "it's still for seconds. the image doesnt move at all." Measured, the
picture stood still for 49 to 65% of each. This reads a finished file and says so before a person
has to.

It reads the video at five frames a second, looks only at the picture (not the caption cards,
which change with every word and would hide a frozen picture behind them), and counts the share
of the picture's pixels that changed since the frame before. Two bars, because a slowly drifting
background passes the first on its own:

    still   under 0.4% changed: a frozen picture
    slow    under 3% changed: a drift, nothing a viewer would call movement

Per video it prints the share of the running time under each bar, the slow stretches of 1.5 s and
longer, and the median change. --check fails (exit 1) a file that is still for more than 5% of
its time or holds a slow stretch longer than 3 s: the bar the rebuilt Shorts passed (0% still,
longest slow stretch 2.0 s) and the rejected ones missed by a factor of ten.

--box is the picture's band as two shares of the height, top and bottom. The default, 0.08 to
0.66, is everything above the caption band of a studio Short; a Short with a fixed title block
above its picture measures truer with the title left out (the padel Shorts: 0.19,0.68).

Invoke as:
    python scripts/short-stillness.py <video.mp4> [<video.mp4> ...] [--box 0.08,0.66] [--check]
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402, F401 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

W, H, FPS = 135, 240, 5  # what the video is read at: small enough that film grain is not movement
CHANGED = 6  # grey levels a pixel must move by to count as changed
STILL, SLOW = 0.004, 0.03  # shares of the picture's pixels
RUN = 1.5  # a slow stretch worth naming, seconds
MAX_STILL, MAX_RUN = (
    0.05,
    3.0,
)  # --check: the most stillness, and the longest slow stretch, a Short may have


def frames(path, box):
    """The picture's band of every sampled frame, as signed greys (frames, rows, W)."""
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    cmd += ["-vf", "fps=%d,scale=%d:%d,format=gray" % (FPS, W, H), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    top, bot = int(H * box[0]), int(H * box[1])
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W)[:, top:bot, :].astype(np.int16)


def moved(f):
    """Per sampled frame after the first: the share of the picture that changed since the last."""
    return (np.abs(np.diff(f, axis=0)) >= CHANGED).mean(axis=(1, 2))


def stretches(under, fps=FPS, least=RUN):
    """[(start s, length s)] of the runs of True in `under` that last `least` seconds or more."""
    runs, start = [], None
    for i, s in enumerate(list(under) + [False]):
        if s and start is None:
            start = i
        elif not s and start is not None:
            if (i - start) / fps >= least:
                runs.append((start / fps, (i - start) / fps))
            start = None
    return runs


def measure(f):
    """-> {seconds, still, slow (shares of the time), runs (slow stretches), median, ok}."""
    m = moved(f)
    runs = stretches(m < SLOW)
    still = float((m < STILL).mean()) if len(m) else 0.0
    return {
        "seconds": len(f) / FPS,
        "still": still,
        "slow": float((m < SLOW).mean()) if len(m) else 0.0,
        "runs": runs,
        "median": float(np.median(m)) if len(m) else 0.0,
        "ok": still <= MAX_STILL and max((r[1] for r in runs), default=0.0) <= MAX_RUN,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("videos", nargs="+")
    ap.add_argument(
        "--box", default="0.08,0.66", help="the picture's band: top,bottom as shares of the height"
    )
    ap.add_argument("--check", action="store_true", help="exit 1 when a video misses the bar")
    a = ap.parse_args()
    box = [float(x) for x in a.box.split(",")]
    if len(box) != 2 or not 0 <= box[0] < box[1] <= 1:
        sys.exit("--box wants top,bottom as shares of the height, e.g. 0.08,0.66")
    bad = 0
    for path in a.videos:
        r = measure(frames(path, box))
        longest = max((x[1] for x in r["runs"]), default=0)
        name = "/".join(path.replace("\\", "/").split("/")[-2:])
        print(
            "%-30s %5.1f s   still %3.0f%%   slow %3.0f%%   slow stretches of %.1f s+: %2d (%.0f s in all, "
            "longest %.1f s)   median change %.1f%%%s"
            % (
                name,
                r["seconds"],
                r["still"] * 100,
                r["slow"] * 100,
                RUN,
                len(r["runs"]),
                sum(x[1] for x in r["runs"]),
                longest,
                r["median"] * 100,
                "" if r["ok"] else "   <- stands still",
            )
        )
        if r["runs"]:
            print("    " + "  ".join("%.0f-%.0fs" % (s, s + d) for s, d in r["runs"]))
        bad += not r["ok"]
    if a.check and bad:
        sys.exit(
            "%d of %d stand still: over %d%% of the time, or a slow stretch over %g s"
            % (bad, len(a.videos), MAX_STILL * 100, MAX_RUN)
        )


if __name__ == "__main__":
    main()
