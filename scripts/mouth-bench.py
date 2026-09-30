#!/usr/bin/env python
"""How closely does a talking head's mouth follow the voice? Measured against a real mouth.

Given a video of somebody talking to the camera, this measures their real mouth opening on
every frame (MediaPipe's face landmarker, via head-rig.py's models: the inner-lip gap over the
face's height, and the jawOpen blendshape), computes the mouth track sketch films use
(_heads.mouth_track) from the same video's own audio, and reports how well the two agree: the
Pearson correlation over the syllable band (2-8 Hz) at every lag from -300 to +300 ms (the peak
says whether the real mouth moves before or after the track), and how often the two agree on
open versus shut. The whole signals barely correlate (r ~0.0-0.1 on the first footage): a real
mouth also opens to breathe before a sentence and holds open between words, which no sound
shows, so the syllables are what is compared.

Measured 2026-09-30 on two phone takes of a man talking to camera in Ukrainian (claude-demo
IMG_2695 30-90 s, PXL_...160930856 0-23 s): syllable-band r peaks at 0.20-0.21, with the real
mouth 80-140 ms ahead of its sound -- which is why TRACK's lead is 0.08 s, not the first 0.04.

`--sweep` prices the track's knobs on the same footage (the dynamic range it maps onto the
mouth, the curve, the attack and release, the lead) so a change to _heads.py is measured, not
guessed. The frames are read once and cached in temp/mouth-bench/.

Nothing leaves the machine; the video is only read.

Invoke as:
    python scripts/mouth-bench.py --video projects/<id>/sources/take.mp4 --start 20 --secs 60
    python scripts/mouth-bench.py --video ... --start 20 --secs 60 --sweep
"""

import sys
import os
import json
import hashlib
import argparse
import subprocess
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _heads  # noqa: E402
import _sketch  # noqa: E402


def frames(video, start, secs, fps, rotate):
    """(t, gap/face-height, jawOpen) for every frame, measured once and cached."""
    key = hashlib.sha1(
        json.dumps(
            [os.path.abspath(video), os.path.getsize(video), start, secs, fps, rotate]
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    cache = _env.resolve(os.path.join("temp", "mouth-bench", key + ".json"))
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    rig = import_module("head-rig")
    ms = rig.Measurer()
    w, h = 640, 360
    vf = "fps=%d,scale=%d:%d" % (fps, w, h)
    if rotate:
        vf = {"cw": "transpose=1", "ccw": "transpose=2", "180": "hflip,vflip"}[rotate] + "," + vf
        if rotate in ("cw", "ccw"):
            w, h = h, w
            vf = vf.replace("scale=%d:%d" % (h, w), "scale=%d:%d" % (w, h))
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-noautorotate",
        "-ss",
        str(start),
        "-t",
        str(secs),
        "-i",
        video,
        "-vf",
        vf,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    out = []
    for i in range(n):
        img = np.frombuffer(raw, np.uint8, w * h * 3, i * w * h * 3).reshape(h, w, 3)
        P, bs = ms.landmarks(img)
        if P is None:
            out.append([i / fps, None, None])
            continue
        H = np.linalg.norm(P[rig.CHIN] - P[rig.TOP])
        gap = float(np.linalg.norm(P[13] - P[14]) / H)
        out.append([i / fps, gap, bs.get("jawOpen", 0.0)])
    ms.close()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def audio(video, start, secs):
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(start),
            "-t",
            str(secs),
            "-i",
            video,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(_heads.SR),
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def syllabic(s, fs):
    """The 2-8 Hz part of a signal: the syllables, without the slow drift -- a real mouth also
    opens to breathe and holds open between words, which no sound shows."""
    from scipy.signal import butter, filtfilt

    b, a = butter(2, [2.0 / (fs / 2), 8.0 / (fs / 2)], "band")
    return filtfilt(b, a, s)


def agree(track, fps_t, times, real, fps_v):
    """Correlation at each lag (ms -> r) over the syllable band, and the share of frames where
    both say open or shut. A positive best lag: the real mouth moves that much before the
    track does (the track's lead should grow by it)."""
    o = np.array(track, np.float64) / 100
    tt = np.arange(len(o)) / fps_t
    real = np.where(np.isnan(real), np.nanmean(real), real)
    out = {}
    for lag in range(-300, 301, 20):
        pred = np.interp(times + lag / 1000, tt, o, left=0, right=0)
        out[lag] = float(np.corrcoef(syllabic(pred, fps_v), syllabic(real, fps_v))[0, 1])
    best = max(out, key=out.get)
    pred = np.interp(times, tt, o, left=0, right=0)
    thr_r = np.nanpercentile(real, 55)
    both = float(np.mean((pred > 0.25) == (real > thr_r)))
    return out, best, both


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True, help="somebody talking to the camera, with sound")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--rotate", choices=["cw", "ccw", "180"], help="turn the frames upright")
    ap.add_argument("--sweep", action="store_true", help="price the track's knobs on this footage")
    a = ap.parse_args()
    video = _env.resolve(a.video)
    rows = frames(video, a.start, a.secs, a.fps, a.rotate)
    times = np.array([r[0] for r in rows])
    gap = np.array([np.nan if r[1] is None else r[1] for r in rows])
    jaw = np.array([np.nan if r[2] is None else r[2] for r in rows])
    seen = np.mean(~np.isnan(gap))
    print(
        "%s  %.0f-%.0fs  %d frames, a face in %.0f%%"
        % (os.path.basename(video), a.start, a.start + a.secs, len(rows), seen * 100)
    )
    x = audio(video, a.start, a.secs)
    tr = _heads.mouth_track(x)
    for name, real in (("lip gap", gap), ("jawOpen", jaw)):
        lags, best, both = agree(tr["o"], tr["fps"], times, real, a.fps)
        print(
            "  vs %-8s syllable-band r=%.3f at 0 ms, best r=%.3f at %+d ms (%s), open/shut agree %.0f%%"
            % (
                name,
                lags[0],
                lags[best],
                best,
                "the real mouth moves first"
                if best > 0
                else "the track moves first"
                if best < 0
                else "in step",
                both * 100,
            )
        )
    if not a.sweep:
        return
    print("\n  sweep (vs the lip gap, r at 0 ms / best r @ lag):")
    base = dict(_heads.TRACK)
    grid = [
        ("range_db", [20, 28, 36]),
        ("power", [1.0, 1.35, 1.8]),
        ("attack", [0.5, 0.75, 1.0]),
        ("release", [0.25, 0.4, 0.6]),
        ("lead", [0.0, 0.04, 0.08]),
    ]
    for knob, values in grid:
        cells = []
        for v in values:
            tr = _heads.mouth_track(x, **{**base, knob: v})
            lags, best, _ = agree(tr["o"], tr["fps"], times, gap, a.fps)
            cells.append("%s=%s: %.3f / %.3f@%+d" % (knob, v, lags[0], lags[best], best))
        print("    " + "   ".join(cells))


if __name__ == "__main__":
    main()
