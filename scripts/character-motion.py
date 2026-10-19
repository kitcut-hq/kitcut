#!/usr/bin/env python
"""How a character moves, read off a probe render: pops, stillness, and motion, side by side.

A character played by swapping drawn pieces (sketch/actors.js) and one played by bending a rigged
cut-out (sketch/puppet.js) can be given the same script and the same voice; this says which of
the two a viewer will read as moving and which as flicking between pictures. The first rigged
test (padel-tactics films/05-history/puppet-test, 2026-10-19) was compared with the swapped one
this way, every iteration: 12 pops carrying 83 % of the swapped Enrique's unexplained change and
20 % of his time standing still, against 8 pops carrying 28 % and none, for the puppet.

Give it a **probe** render: the character alone, a fixed camera, on white (a film.js that draws
only the character when the manifest's `data.probe` is set; see the puppet test). A moving camera
or a background makes every pixel move and the scores read the set, not the actor.

Each frame is predicted from the one before by dense optical flow (Farneback, 640 px wide), and
what the prediction cannot explain -- pixels that appear from nowhere, as a swap makes them -- is
counted as a share of the figure. Continuous motion is explained by flow; a swap is not.

    pops       frames where over 3 % of the figure is unexplained (a swap, a jump)
    pop_share  the share of all unexplained change carried by those frames
    worst_pop  the biggest single frame's unexplained share
    still      frames where nothing visible changed over a tenth of a second
    longest    the longest still run, in seconds
    moving     frames where something moved that flow explains (over 0.3 % of the figure)

Lower pops, pop_share, worst_pop and still are better; higher moving is better. A mouth that
opens and a blink are small pops of their own (under 1 %), so a talking character never scores
zero. The script only reads files: it encodes nothing and spends nothing.

Invoke as:
    python scripts/character-motion.py <probe.mp4> [<probe.mp4> ...] [--label A --label B]
                                       [--json scores.json] [--frames frames.json]
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402, F401 -- re-execs into .venv; before any 3rd-party import

import cv2  # noqa: E402
import numpy as np  # noqa: E402

W, H = 640, 360  # what the video is read at
PAPER = 235  # a grey level under this is the figure, on a white probe
CHANGED, RESIDUE = 24, 40  # grey levels: a pixel that changed; one flow cannot explain
POP, STILL, MOVE = 0.03, 0.0005, 0.003  # shares of the figure's area


def fps_of(path):
    rate = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0"]
        + ["-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    num, den = (rate.split("/") + ["1"])[:2]
    return float(num) / float(den)


def figure_frames(path):
    """Every frame, grey, cropped to the box the figure ever occupies; and the figure's area."""
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    cmd += ["-vf", "scale=%d:%d,format=gray" % (W, H), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    F = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
    ys, xs = np.nonzero((F < PAPER).any(0))
    if not len(ys):
        sys.exit("%s: no figure on white -- is it a probe render?" % path)
    y0, y1 = max(ys.min() - 8, 0), min(ys.max() + 9, H)
    x0, x1 = max(xs.min() - 8, 0), min(xs.max() + 9, W)
    box = F[:, y0:y1, x0:x1]
    return box, float((box < PAPER).any(0).sum())


def score(path, label=""):
    box, area = figure_frames(path)
    fps = fps_of(path)
    gy, gx = np.mgrid[0 : box.shape[1], 0 : box.shape[2]].astype(np.float32)
    U, C = [], []
    for i in range(1, len(box)):
        p, n = box[i - 1], box[i]
        ch = np.abs(n.astype(int) - p.astype(int)) > CHANGED
        C.append(ch.sum() / area)
        if not ch.any():
            U.append(0.0)
            continue
        # where each new pixel came from, then what that cannot account for
        fl = cv2.calcOpticalFlowFarneback(n, p, None, 0.5, 4, 21, 5, 7, 1.5, 0)
        warped = cv2.remap(p, gx + fl[..., 0], gy + fl[..., 1], cv2.INTER_LINEAR)
        res = (np.abs(warped.astype(int) - n.astype(int)) > RESIDUE) & ch
        res = cv2.morphologyEx(res.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        U.append(res.sum() / area)
    U, C = np.array(U), np.array(C)
    # still: nothing changed over a tenth of a second (a slow breath moves under a pixel a frame
    # and is still life, so frame-to-frame would call a breathing figure frozen)
    k = max(1, round(fps / 10))
    C10 = np.array(
        [
            (np.abs(box[i].astype(int) - box[max(0, i - k)].astype(int)) > CHANGED).sum() / area
            for i in range(1, len(box))
        ]
    )
    still = C10 < STILL
    run = best = 0
    for s in still:
        run = run + 1 if s else 0
        best = max(best, run)
    pop = U > POP
    out = {
        "label": label or os.path.basename(path),
        "pops": int(pop.sum()),
        "pop_share": round(float(U[pop].sum() / max(U.sum(), 1e-9)), 3),
        "worst_pop": round(float(U.max()), 3),
        "still": round(float(still.mean()), 3),
        "longest_still_s": round(best / fps, 2),
        "moving": round(float(((C - U) > MOVE).mean()), 3),
        "seconds": round(len(box) / fps, 2),
    }
    frames = {"fps": fps, "unexplained": U.round(5).tolist(), "changed": C.round(5).tolist()}
    return out, frames


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("videos", nargs="+", help="probe renders: the character alone on white")
    ap.add_argument("--label", action="append", default=[], help="a name per video, in order")
    ap.add_argument("--json", help="write the scores here")
    ap.add_argument("--frames", help="write every frame's unexplained/changed share here")
    a = ap.parse_args()
    rows, per = [], {}
    for i, v in enumerate(a.videos):
        out, frames = score(v, a.label[i] if i < len(a.label) else "")
        rows.append(out)
        per[out["label"]] = frames
    keys = ["pops", "pop_share", "worst_pop", "still", "longest_still_s", "moving", "seconds"]
    width = max(12, *(len(r["label"]) for r in rows))
    print("%-*s " % (width, "") + " ".join("%10s" % k[:10] for k in keys))
    for r in rows:
        print("%-*s " % (width, r["label"]) + " ".join("%10s" % r[k] for k in keys))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)
    if a.frames:
        with open(a.frames, "w") as f:
            json.dump(per, f)


if __name__ == "__main__":
    main()
