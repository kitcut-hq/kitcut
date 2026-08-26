#!/usr/bin/env python
"""Work out where the 9:16 window should sit, over time, for each clip.

A fixed centre crop is a bet that the subject is centred. Over a real video they
are not: they drift, they sit off to one side, and b-roll has its own
composition. This samples each clip, finds the face, and emits a handful of
keyframes -- `[[t, centre_x], ...]` -- that `cut-clips.py` turns into a crop
whose x is an expression in `t`, so the window pans instead of jumping.

Detection is Haar cascades (frontal + profile) on small greyscale frames: no
model download, fast enough to sample a whole clip in seconds. It is not
state-of-the-art and does not need to be -- the output is smoothed hard and then
reduced to a few keys, so isolated misses and jitter never reach the crop.

Where no face is found -- b-roll, cutaways, the back of a head -- the last known
position is held. That is the honest default, but it is a guess: review the
result and hand-edit keys for inserts that need a different framing.

Invoke as:  python -X utf8 -E scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
"""
import sys, os, json, argparse, subprocess, shutil
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_outline = import_module("transcript-outline")
_cut = import_module("cut-clips")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import cv2

ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def sample_faces(src, start, dur, src_w, src_h, fps, probe_w=480, min_face=0.045):
    """Decode the span at `fps` and return (t, centre_x_in_source) per sample.

    Frames come through a pipe as raw grey rather than via VideoCapture seeks:
    one sequential decode beats thousands of seeks on a long source.
    """
    h = int(round(probe_w * src_h / float(src_w))) // 2 * 2
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % start,
           "-t", "%.3f" % dur, "-i", src,
           "-vf", "fps=%g,scale=%d:%d" % (fps, probe_w, h),
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)
    d = cv2.data.haarcascades
    front = cv2.CascadeClassifier(os.path.join(d, "haarcascade_frontalface_default.xml"))
    prof = cv2.CascadeClassifier(os.path.join(d, "haarcascade_profileface.xml"))
    if front.empty() or prof.empty():
        sys.exit("haar cascades missing -- need opencv-python<5")

    frame_bytes = probe_w * h
    scale_back = src_w / float(probe_w)
    mn = int(probe_w * min_face)
    out, i = [], 0
    while True:
        buf = p.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        img = np.frombuffer(buf, np.uint8).reshape(h, probe_w)
        img = cv2.equalizeHist(img)
        found = []
        for cc in (front, prof):
            for (x, y, fw, fh) in cc.detectMultiScale(img, 1.15, 5, minSize=(mn, mn)):
                found.append((fw * fh, x + fw / 2.0))
        # a talking head is the biggest face in frame; crowds behind her are not
        cx = max(found)[1] * scale_back if found else None
        out.append((i / float(fps), cx))
        i += 1
    p.stdout.close()
    p.wait()
    return out


def smooth(samples, src_w, half_win, cut_jump, dead, default_x):
    """Hold through misses, median-filter, then exponentially smooth.

    Median first because Haar's failure mode is a single wild box, and a mean
    would drag the window towards it for the whole smoothing window.
    """
    xs, last = [], None
    for _, cx in samples:
        if cx is not None:
            last = cx
        xs.append(last)
    # nothing detected before the first hit: back-fill from the first known
    first = next((v for v in xs if v is not None), default_x)
    xs = [first if v is None else v for v in xs]

    med = []
    for i in range(len(xs)):
        lo, hi = max(0, i - half_win), min(len(xs), i + half_win + 1)
        med.append(float(np.median(xs[lo:hi])))

    out, prev = [], med[0] if med else default_x
    for v in med:
        if abs(v - prev) > cut_jump:
            prev = v                      # a real cut: snap, do not pan across it
        else:
            prev = prev + (v - prev) * 0.25
        out.append(prev)
    return out


def detect_shots(src, start, dur, threshold=27.0):
    """Shot boundaries inside the clip's span, in seconds from clip start.

    Returns [0.0, ...] always, so callers can treat the result as shot starts.
    """
    from scenedetect import open_video, SceneManager, ContentDetector
    from scenedetect.frame_timecode import FrameTimecode

    video = open_video(src)
    fps = video.frame_rate
    video.seek(FrameTimecode(start, fps))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    sm.detect_scenes(video=video, duration=FrameTimecode(dur, fps))
    cuts = [0.0]
    for s, _ in sm.get_scene_list():
        t = s.get_seconds() - start
        if 0.25 < t < dur - 0.25:          # a shot shorter than that is a flash
            cuts.append(t)
    return sorted(set(round(c, 3) for c in cuts))


def shot_keys(samples, shots, x_lo, x_hi, default_x, min_hits=0.2, snap=0.05):
    """One static framing per shot, snapping at the boundaries.

    The alternative to panning: inside a shot the window does not move at all,
    so there is no drift and no easing across a cut. A shot with too few face
    hits (b-roll, a graphic, the back of a head) has no subject to centre on and
    inherits the previous shot's framing rather than inventing one.
    """
    ends = shots[1:] + [samples[-1][0] + 1e3]
    keys, prev_x, flagged = [], default_x, []
    for i, (t0, t1) in enumerate(zip(shots, ends)):
        hits = [cx for t, cx in samples if t0 <= t < t1 and cx is not None]
        n = sum(1 for t, _ in samples if t0 <= t < t1)
        if n and len(hits) >= max(1, int(n * min_hits)):
            x = float(np.median(hits))
        else:
            x = prev_x
            flagged.append(i)
        x = min(max(x, x_lo), x_hi)
        prev_x = x
        if keys:
            keys.append([round(t0 - snap, 3), keys[-1][1]])   # hold, then snap
        keys.append([round(t0, 3), round(x)])
    keys[0][0] = 0.0
    return keys, flagged


def track_at(keys, t):
    """Evaluate the keyframe track in Python -- same piecewise-linear shape that
    cut-clips.crop_x_expr hands to ffmpeg, so the report measures what renders."""
    if t <= keys[0][0]:
        return float(keys[0][1])
    for (t0, x0), (t1, x1) in zip(keys, keys[1:]):
        if t < t1:
            if t1 == t0:
                return float(x1)
            return x0 + (x1 - x0) * (t - t0) / float(t1 - t0)
    return float(keys[-1][1])


def measure(samples, keys, cw):
    """How well a track holds the subject, and how much it moves doing it.

    Only frames with an actual detection are scored -- on a held frame there is
    no ground truth, and counting it would flatter whichever track happened to
    freeze there.
    """
    errs = [abs(cx - track_at(keys, t)) for t, cx in samples if cx is not None]
    half = cw / 2.0
    move = sum(abs(track_at(keys, b[0]) - track_at(keys, a[0]))
               for a, b in zip(samples, samples[1:]))
    span = max(samples[-1][0] - samples[0][0], 1e-6)
    if not errs:
        return None
    errs.sort()
    return dict(n=len(errs),
                mean=sum(errs) / len(errs),
                p95=errs[min(len(errs) - 1, int(len(errs) * 0.95))],
                out=100.0 * sum(1 for e in errs if e > half) / len(errs),
                edge=100.0 * sum(1 for e in errs if e > half * 0.7) / len(errs),
                move=move / span)


def to_keys(times, xs, x_lo, x_hi, dead, min_gap):
    """Reduce a dense track to the few keys that actually matter."""
    keys = []
    for t, x in zip(times, xs):
        x = min(max(x, x_lo), x_hi)
        if not keys:
            keys.append([round(t, 2), round(x)])
            continue
        if abs(x - keys[-1][1]) >= dead and t - keys[-1][0] >= min_gap:
            keys.append([round(t, 2), round(x)])
    if len(keys) == 1:
        keys = [[0.0, keys[0][1]]]
    else:
        keys[0][0] = 0.0
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids")
    ap.add_argument("--out", help="where to write the keys; default <manifest>.reframe.json")
    ap.add_argument("--fps", type=float, default=3.0, help="samples per second")
    ap.add_argument("--probe-width", type=int, default=480)
    ap.add_argument("--smooth-window", type=float, default=1.2,
                    help="seconds of median filtering")
    ap.add_argument("--cut-jump", type=float, default=280.0,
                    help="source px of movement treated as a scene cut, not a pan")
    ap.add_argument("--deadband", type=float, default=26.0,
                    help="source px a key must move to be worth emitting")
    ap.add_argument("--min-gap", type=float, default=0.6, help="seconds between keys")
    ap.add_argument("--mode", choices=("pan", "shot", "compare"), default="pan",
                    help="pan: smooth track. shot: one static framing per shot, "
                         "snapping at cuts. compare: measure both, write nothing.")
    ap.add_argument("--scene-threshold", type=float, default=27.0)
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    m = json.load(open(args.manifest, encoding="utf-8"))
    src = m["source"]
    words = _outline.load_words(m["words"]) if m.get("words") else []
    pad = m.get("pad", {})
    pad_head, pad_tail = float(pad.get("head", 0.12)), float(pad.get("tail", 0.30))
    src_w, src_h = _cut._handle.probe_dims(src)
    vert = m.get("vertical") or {"width": 1080, "height": 1920}
    out_w, out_h = int(vert["width"]), int(vert["height"])

    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None
    comparison = {}
    half_win = max(1, int(round(args.smooth_window * args.fps / 2.0)))
    result = {}
    for clip in m["clips"]:
        if wanted and clip["id"] not in wanted:
            continue
        start, end = _cut.resolve(clip, words, pad_head, pad_tail)
        cw, ch, _, _ = _cut.crop_box(clip, src_w, src_h, out_w, out_h)
        x_lo, x_hi = cw / 2.0, src_w - cw / 2.0

        samples = sample_faces(src, start, end - start, src_w, src_h,
                               args.fps, args.probe_width)
        hits = sum(1 for _, c in samples if c is not None)
        xs = smooth(samples, src_w, half_win, args.cut_jump, args.deadband,
                    src_w / 2.0)
        pan = to_keys([t for t, _ in samples], xs, x_lo, x_hi,
                      args.deadband, args.min_gap)

        shot = flagged = None
        if args.mode in ("shot", "compare"):
            shots = detect_shots(src, start, end - start, args.scene_threshold)
            shot, flagged = shot_keys(samples, shots, x_lo, x_hi, src_w / 2.0)

        if args.mode == "compare":
            a, b = measure(samples, pan, cw), measure(samples, shot, cw)
            print("%-20s %4.1fs  faces %3.0f%%  shots %d%s"
                  % (clip["id"], end - start, 100.0 * hits / max(1, len(samples)),
                     len(shots), "  (%d without a subject)" % len(flagged) if flagged else ""))
            for name, r, k in (("pan ", a, pan), ("shot", b, shot)):
                print("    %s  off-centre mean %5.1fpx  p95 %5.1fpx  "
                      "near-edge %4.1f%%  out %4.1f%%  motion %5.1f px/s  keys %2d"
                      % (name, r["mean"], r["p95"], r["edge"], r["out"], r["move"], len(k)))
            comparison[clip["id"]] = (a, b)
            continue

        keys = shot if args.mode == "shot" else pan
        result[clip["id"]] = keys
        print("%-20s %4.1fs  faces %3d/%3d (%3.0f%%)  keys %2d  x %4d..%4d%s"
              % (clip["id"], end - start, hits, len(samples),
                 100.0 * hits / max(1, len(samples)), len(keys),
                 min(k[1] for k in keys), max(k[1] for k in keys),
                 "  shots %d" % len(shots) if args.mode == "shot" else ""))

    if args.mode == "compare":
        def avg(i, k):
            v = [c[i][k] for c in comparison.values()]
            return sum(v) / max(1, len(v))
        print("\n%-6s %10s %10s %12s %10s" % ("", "mean", "p95", "near-edge", "motion"))
        for name, i in (("pan", 0), ("shot", 1)):
            print("%-6s %8.1fpx %8.1fpx %10.1f%% %8.1f px/s"
                  % (name, avg(i, "mean"), avg(i, "p95"), avg(i, "edge"), avg(i, "move")))
        return

    out = args.out or os.path.splitext(args.manifest)[0] + ".reframe.json"
    old = {}
    if os.path.exists(out):
        old = json.load(open(out, encoding="utf-8"))
    old.update(result)
    json.dump(old, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
