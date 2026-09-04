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

The default `--mode hybrid` splits each clip at its shot boundaries and decides
every shot separately, because measuring showed the pan-vs-static argument has
no global answer:

  static  the face barely moves in this shot -- freeze the window
  pan     it moves -- track it
  pad     no face at all -- do not crop; show the whole frame letterboxed over
          a blurred fill, the only way a full-width burned-in graphic survives

`--mode compare` measures all three against each other and writes nothing, which
is how that default was chosen rather than guessed. `--mode pan` is the older
behaviour and needs no scenedetect.

A `pad` decision is only ever "no face was found here". That is usually b-roll,
but it is also what a shot where the subject looks away looks like. Review them.

Invoke as:  python scripts/auto-reframe.py --manifest config/clips/<id>-vertical.json
"""

import sys
import os
import json
import argparse
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

_outline = import_module("transcript-outline")
_cut = import_module("cut-clips")


import numpy as np
import cv2

ENV = _env.ENV


def sample_faces(src, start, dur, src_w, src_h, fps, probe_w=480, min_face=0.045):
    """Decode the span at `fps` and return (t, centre_x_in_source) per sample.

    Frames come through a pipe as raw grey rather than via VideoCapture seeks:
    one sequential decode beats thousands of seeks on a long source.
    """
    h = int(round(probe_w * src_h / float(src_w))) // 2 * 2
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-ss",
        "%.3f" % start,
        "-t",
        "%.3f" % dur,
        "-i",
        src,
        "-vf",
        "fps=%g,scale=%d:%d" % (fps, probe_w, h),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
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
            for x, y, fw, fh in cc.detectMultiScale(img, 1.15, 5, minSize=(mn, mn)):
                found.append((fw * fh, x + fw / 2.0))
        # a talking head is the biggest face in frame; crowds behind her are not
        cx = max(found)[1] * scale_back if found else None
        out.append((i / float(fps), cx))
        i += 1
    p.stdout.close()
    p.wait()
    return out


def smooth(samples, half_win, cut_jump, default_x):
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
            prev = v  # a real cut: snap, do not pan across it
        else:
            prev = prev + (v - prev) * 0.25
        out.append(prev)
    return out


def _have_scenedetect():
    try:
        import scenedetect  # noqa: F401

        return True
    except Exception:
        return False


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
        if 0.25 < t < dur - 0.25:  # a shot shorter than that is a flash
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
            keys.append([round(t0 - snap, 3), keys[-1][1]])  # hold, then snap
        keys.append([round(t0, 3), round(x)])
    keys[0][0] = 0.0
    return keys, flagged


def hybrid_keys(
    samples,
    shots,
    xs,
    x_lo,
    x_hi,
    default_x,
    dur,
    min_hits=0.2,
    static_spread=90.0,
    snap=0.05,
    dead=26.0,
    min_gap=0.6,
):
    """Decide each shot on its own terms: static, pan, or don't crop at all.

    Measuring per-shot showed the pan/static argument is not global -- a static
    frame wins where the subject sits still and loses badly where they walk. So
    the spread of the face within a shot picks the treatment, and a shot with no
    subject is not cropped at all but letterboxed over a blurred background,
    which is the only way a full-width burned-in graphic survives 9:16.

    Returns (keys, pads) where pads is [[t0, t1], ...] to letterbox.
    """
    ends = shots[1:] + [dur]
    keys, pads, plan = [], [], []
    for t0, t1 in zip(shots, ends):
        hits = [cx for t, cx in samples if t0 <= t < t1 and cx is not None]
        n = sum(1 for t, _ in samples if t0 <= t < t1)
        if not n:
            continue
        if len(hits) < max(1, int(n * min_hits)):
            pads.append([round(t0, 3), round(t1, 3)])
            plan.append("pad")
            continue

        hs = sorted(hits)
        spread = hs[int(len(hs) * 0.9)] - hs[int(len(hs) * 0.1)]
        seg = [(t, x) for (t, _), x in zip(samples, xs) if t0 <= t < t1]
        if spread <= static_spread or len(seg) < 3:
            pts = [(t0, float(np.median(hits)))]
            plan.append("static")
        else:
            pts = [seg[0]]
            for t, x in seg[1:]:
                if abs(x - pts[-1][1]) >= dead and t - pts[-1][0] >= min_gap:
                    pts.append((t, x))
            plan.append("pan")

        for j, (t, x) in enumerate(pts):
            x = min(max(x, x_lo), x_hi)
            t = t0 if j == 0 else t
            if keys and j == 0:
                keys.append([round(t - snap, 3), keys[-1][1]])  # hold, then snap
            keys.append([round(t, 3), round(x)])
    if not keys:
        keys = [[0.0, round(default_x)]]
    keys[0][0] = 0.0
    return keys, pads, plan


def in_pads(t, pads):
    return any(a <= t < b for a, b in pads)


def track_at(keys, t):
    """Evaluate the keyframe track in Python -- same piecewise-linear shape that
    cut-clips.crop_x_expr hands to ffmpeg, so the report measures what renders.
    """
    if t <= keys[0][0]:
        return float(keys[0][1])
    for (t0, x0), (t1, x1) in zip(keys, keys[1:]):
        if t < t1:
            if t1 == t0:
                return float(x1)
            return x0 + (x1 - x0) * (t - t0) / float(t1 - t0)
    return float(keys[-1][1])


def measure(samples, keys, cw, pads=()):
    """How well a track holds the subject, and how much it moves doing it.

    Only frames with an actual detection are scored -- on a held frame there is
    no ground truth, and counting it would flatter whichever track happened to
    freeze there.
    """
    # A letterboxed stretch shows the whole frame, so "off-centre" is meaningless
    # there -- scoring it as perfect would flatter the hybrid for free.
    errs = [
        abs(cx - track_at(keys, t)) for t, cx in samples if cx is not None and not in_pads(t, pads)
    ]
    half = cw / 2.0
    move = sum(
        abs(track_at(keys, b[0]) - track_at(keys, a[0]))
        for a, b in zip(samples, samples[1:])
        if not in_pads(a[0], pads)
    )
    span = max(samples[-1][0] - samples[0][0], 1e-6)
    if not errs:
        return None
    errs.sort()
    return dict(
        n=len(errs),
        mean=sum(errs) / len(errs),
        p95=errs[min(len(errs) - 1, int(len(errs) * 0.95))],
        out=100.0 * sum(1 for e in errs if e > half) / len(errs),
        edge=100.0 * sum(1 for e in errs if e > half * 0.7) / len(errs),
        move=move / span,
    )


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


def merge_sidecar(old, result, force):
    """Merge fresh tracker output into an existing sidecar WITHOUT destroying
    hand edits. Returns (merged, refused_msgs, warn_msgs).

    The sidecar exists to be edited -- a cleared false pad, a letterboxed
    graphic insert, a window pinned through a two-box seam -- and a regen used
    to throw those edits away with a WARNING at best. It cannot merge them
    back either: entries are in CLIP time, so the moment a clip's boundary
    moves every hand-tuned time in them means something else. What it can do
    is refuse. The rule matches the repo's prose-marker convention
    (`_comment`, `_why`, `_pad_why` -- what `project-scan.py` promises never
    to touch):

      * an entry carrying any `_`-prefixed key is HAND-EDITED -> kept, the
        fresh result for that clip is dropped, and the refusal says so;
      * a `_`-prefixed key at the TOP of the sidecar marks the whole file ->
        every existing entry is kept;
      * `--force-regen` overrides both, because after a boundary change the
        right move IS to regenerate and then re-apply the edit in the new
        time base.

    One film had the same letterbox override silently wiped three times in a
    session; another sidecar in this repo carries `"_pad_why"` today and would
    have been wiped by the next innocent regen.
    """
    file_marked = any(k.startswith("_") for k in old)
    merged, refused, warns = dict(old), [], []
    for cid, entry in sorted(result.items()):
        prev = old.get(cid)
        marked = isinstance(prev, dict) and any(k.startswith("_") for k in prev)
        if prev is not None and (marked or file_marked) and not force:
            why = ""
            if isinstance(prev, dict):
                for k in sorted(prev):
                    if k.startswith("_") and isinstance(prev[k], str):
                        why = " -- %s: %.80s" % (k, prev[k])
                        break
            if not why and file_marked:
                for k in sorted(old):
                    if k.startswith("_") and isinstance(old[k], str):
                        why = " -- file: %.80s" % old[k]
                        break
            refused.append(
                "%s: hand-edited, keeping the existing entry "
                "(--force-regen overwrites; re-apply the edit in "
                "the clip's NEW time base after)%s" % (cid, why)
            )
            continue
        if (
            isinstance(prev, dict)
            and isinstance(entry, dict)
            and prev.get("pad")
            and prev["pad"] != entry.get("pad", [])
        ):
            warns.append(
                "%s: overwriting pad %s with %s -- if that pad was "
                "a manual override, re-apply it, in the clip's NEW "
                "time base if its start moved" % (cid, prev["pad"], entry.get("pad", []))
            )
        merged[cid] = entry
    return merged, refused, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids")
    ap.add_argument("--out", help="where to write the keys; default <manifest>.reframe.json")
    ap.add_argument("--fps", type=float, default=3.0, help="samples per second")
    ap.add_argument("--probe-width", type=int, default=480)
    ap.add_argument("--smooth-window", type=float, default=1.2, help="seconds of median filtering")
    ap.add_argument(
        "--cut-jump",
        type=float,
        default=280.0,
        help="source px of movement treated as a scene cut, not a pan",
    )
    ap.add_argument(
        "--deadband",
        type=float,
        default=26.0,
        help="source px a key must move to be worth emitting",
    )
    ap.add_argument("--min-gap", type=float, default=0.6, help="seconds between keys")
    ap.add_argument(
        "--force-regen",
        action="store_true",
        help="overwrite sidecar entries carrying hand-edit "
        "markers (_comment, _pad_why, ...) instead of "
        "keeping them",
    )
    ap.add_argument(
        "--mode",
        choices=("pan", "shot", "hybrid", "compare"),
        default="hybrid",
        help="pan: smooth track. shot: one static framing per shot. "
        "hybrid: per shot pick static/pan, letterbox shots with "
        "no subject. compare: measure all three, write nothing.",
    )
    ap.add_argument("--scene-threshold", type=float, default=27.0)
    ap.add_argument(
        "--static-spread",
        type=float,
        default=90.0,
        help="source px of face movement within a shot below which that shot is framed statically",
    )
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
    mode = args.mode
    if mode != "pan" and not _have_scenedetect():
        if mode == "compare":
            # falling back would print a comparison table of zeros and exit 0
            # -- confident, fabricated data
            sys.exit(
                "scenedetect is not installed (pip install scenedetect), "
                "so there is nothing to compare -- or use --mode pan"
            )
        print("scenedetect not installed -- falling back to --mode pan")
        mode = "pan"
    for clip in m["clips"]:
        if wanted and clip["id"] not in wanted:
            continue
        # A clip with a named crop_rect is fitted whole over a fill by
        # rect_chain; there is no 9:16 window to pan, so cut-clips never reads
        # a sidecar entry for it. Tracking it anyway spends face detection to
        # write a key list nothing will use -- and leaves an entry that reads
        # as if the clip were tracked.
        if clip.get("crop_rect", m.get("crop_rect")):
            print("%-20s skipped -- crop_rect is fixed, nothing to track" % clip["id"])
            continue
        # Honour a per-clip pad override, exactly as cut-clips.py does. The
        # sidecar's key times are CLIP-relative, so if this resolved a different
        # start than the renderer, every key would be offset by the difference
        # and the window would re-centre late at each camera cut.
        cp = clip.get("pad", {})
        start, end = _cut.resolve(
            clip, words, float(cp.get("head", pad_head)), float(cp.get("tail", pad_tail))
        )
        cw, ch, _, _ = _cut.crop_box(clip, src_w, src_h, out_w, out_h)
        x_lo, x_hi = cw / 2.0, src_w - cw / 2.0

        samples = sample_faces(src, start, end - start, src_w, src_h, args.fps, args.probe_width)
        hits = sum(1 for _, c in samples if c is not None)
        xs = smooth(samples, half_win, args.cut_jump, src_w / 2.0)
        pan = to_keys([t for t, _ in samples], xs, x_lo, x_hi, args.deadband, args.min_gap)

        shots = shot = flagged = hyb = pads = plan = None
        if mode in ("shot", "hybrid", "compare"):
            shots = detect_shots(src, start, end - start, args.scene_threshold)
            shot, flagged = shot_keys(samples, shots, x_lo, x_hi, src_w / 2.0)
            hyb, pads, plan = hybrid_keys(
                samples,
                shots,
                xs,
                x_lo,
                x_hi,
                src_w / 2.0,
                end - start,
                static_spread=args.static_spread,
                dead=args.deadband,
                min_gap=args.min_gap,
            )

        if mode == "compare":
            padded = sum(b - a for a, b in pads)
            print(
                "%-20s %4.1fs  faces %3.0f%%  shots %d  plan %s  padded %.0f%%"
                % (
                    clip["id"],
                    end - start,
                    100.0 * hits / max(1, len(samples)),
                    len(shots),
                    "/".join(plan) or "-",
                    100.0 * padded / (end - start),
                )
            )
            rows = (
                ("pan   ", measure(samples, pan, cw), pan),
                ("shot  ", measure(samples, shot, cw), shot),
                ("hybrid", measure(samples, hyb, cw, pads), hyb),
            )
            for name, r, k in rows:
                if r is None:
                    continue
                print(
                    "    %s  off-centre mean %5.1fpx  p95 %5.1fpx  "
                    "near-edge %4.1f%%  out %4.1f%%  motion %5.1f px/s  keys %2d"
                    % (name, r["mean"], r["p95"], r["edge"], r["out"], r["move"], len(k))
                )
            comparison[clip["id"]] = tuple(r for _, r, _ in rows)
            continue

        if mode == "hybrid":
            result[clip["id"]] = {"keys": hyb, "pad": pads}
            keys = hyb
        else:
            keys = shot if mode == "shot" else pan
            result[clip["id"]] = keys
        extra = ""
        if mode == "hybrid":
            extra = "  shots %d (%s)" % (len(shots), "/".join(plan) or "-")
        elif mode == "shot":
            extra = "  shots %d" % len(shots)
        print(
            "%-20s %4.1fs  faces %3d/%3d (%3.0f%%)  keys %2d  x %4d..%4d%s"
            % (
                clip["id"],
                end - start,
                hits,
                len(samples),
                100.0 * hits / max(1, len(samples)),
                len(keys),
                min(k[1] for k in keys),
                max(k[1] for k in keys),
                extra,
            )
        )

    if mode == "compare":

        def avg(i, k):
            v = [c[i][k] for c in comparison.values() if c[i]]
            return sum(v) / max(1, len(v))

        print("\n%-7s %10s %10s %12s %10s" % ("", "mean", "p95", "near-edge", "motion"))
        for name, i in (("pan", 0), ("shot", 1), ("hybrid", 2)):
            print(
                "%-7s %8.1fpx %8.1fpx %10.1f%% %8.1f px/s"
                % (name, avg(i, "mean"), avg(i, "p95"), avg(i, "edge"), avg(i, "move"))
            )
        return

    out = args.out or os.path.splitext(args.manifest)[0] + ".reframe.json"
    old = {}
    if os.path.exists(out):
        old = json.load(open(out, encoding="utf-8"))
    merged, refused, warns = merge_sidecar(old, result, args.force_regen)
    for w in warns:
        print("WARNING %s" % w)
    for r in refused:
        print("REFUSED %s" % r)
    json.dump(merged, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(
        "wrote %s%s"
        % (
            out,
            "  (%d entr%s kept, not regenerated)"
            % (len(refused), "y" if len(refused) == 1 else "ies")
            if refused
            else "",
        )
    )


if __name__ == "__main__":
    main()
