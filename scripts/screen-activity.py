#!/usr/bin/env python
"""Measure when a silent screen recording is actually doing something.

The screencast pipeline cuts on speech: `screencast-cut.py` drops a gap where
the speaker is silent AND the screen is static. A recording made with no
microphone has no speech track at all -- Windows' recorder wrote a digitally
silent AAC stream (-91 dB, not room tone) -- so there is nothing to cut on and
that pipeline degenerates. The picture is the only signal left.

So measure the picture. Decode small and slow (gray, a few hundred pixels
wide, a handful of frames a second), and for each sampled pair count the
fraction of pixels that moved by more than a noise floor. A static screen
scores ~0. Typing, scrolling and streaming text score high. That one number
per sample is enough to answer both questions an edit asks:

  where is nothing happening      -> drop it, or speed it up
  where does a new thing start    -> a chapter boundary worth a frame grab

One number for the whole frame is not enough, though, and the footage says so.
On a screencast of an agent working, two very different things both read as
"the screen is moving": the human clicking through a checkout, and an AI
streaming text into a side panel. Cutting the first is vandalism; watching the
second at 1x is the boring part. So activity is measured per named REGION as
well as whole-frame, and the edit is a three-way decision rather than a
two-way one -- keep where the work happens, speed up where only the panel
moves, drop where nothing does. --probe-motion found the panel here without
being told: every recording's still-stretch motion sat in the same column.

Two things make the naive version wrong, and both cost a render to discover:

  A spinner never stops.  A "thinking" animation, a blinking caret, a taskbar
      clock or the recorder's own running timer keep a dead screen permanently
      above any threshold, so nothing is ever cut. `ignore` rectangles (in
      FRACTIONS of frame size, so they survive a resolution change) are blanked
      before the difference is taken. --probe-motion names the offenders by
      reporting which regions move in otherwise-still stretches.

  Compression noise is not motion.  H.264 at 4K re-quantizes flat areas
      between keyframes, so an untouched screen still flickers by a few levels.
      The threshold is on the pixel DELTA (default 10/255), not on equality.

Nothing here renders or decides. It writes an activity track and prices the
thresholds; `screen-cut.py` consumes the track. Sweep with --list before
spending an encode -- picking a still threshold by eye is exactly the guess
this exists to remove.

Invoke as:  python scripts/screen-activity.py --src projects/<id>/sources/<f>.mp4 --list
"""
import sys
import os
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402

ROOT = _env.ROOT

# Sampling defaults. 6 fps is fine for "is anything moving": a mouse drag or a
# streaming caret shows in every sample, and a 320-wide gray frame is 1/108th
# of a 4K plane, so an hour of footage measures in seconds of numpy.
FPS = 6.0
WIDTH = 320
PIXEL_DELTA = 10        # 0-255; below this a pixel counts as unchanged
STILL = 0.004           # fraction of pixels moving, below which a frame is still
MIN_STILL = 1.2         # seconds; a still run shorter than this is not worth cutting


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-show_entries", "format=duration",
         "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    return {
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "fps": float(num) / float(den) if float(den or 0) else 0.0,
        "duration": float((d.get("format") or {}).get("duration") or 0.0),
    }


def decode_gray(path, fps, width, hwaccel=True):
    """Yield (index, HxW uint8) sampled at `fps`, scaled to `width` wide.

    NVDEC is asked for and its failure is not fatal: a machine without it, or
    a codec its build does not cover, must still measure -- just slower.
    """
    info = probe(path)
    if not info["width"]:
        raise SystemExit(f"no video stream: {path}")
    h = max(2, int(round(width * info["height"] / info["width"])) // 2 * 2)

    def build(hw):
        cmd = ["ffmpeg", "-v", "error", "-nostdin"]
        if hw:
            cmd += _encode.decode_args()
        cmd += ["-i", path,
                "-vf", f"fps={fps},scale={width}:{h}",
                "-pix_fmt", "gray", "-f", "rawvideo", "-"]
        return cmd

    # decode_args() already answers whether NVDEC exists, so the hardware rung
    # is only worth attempting when it does -- otherwise the two rungs build
    # the identical command and the file is decoded twice to learn nothing.
    hw_first = hwaccel and bool(_encode.decode_args())
    for hw in ([True, False] if hw_first else [False]):
        p = subprocess.Popen(build(hw), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        n = width * h
        i = 0
        got = False
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            got = True
            yield i, np.frombuffer(buf, np.uint8).reshape(h, width)
            i += 1
        p.stdout.close()
        err = p.stderr.read().decode("utf-8", "replace")
        p.wait()
        if got:
            return
        if hw:
            print(f"  nvdec decode produced nothing, retrying on cpu", file=sys.stderr)
        else:
            raise SystemExit(f"decode failed: {err.strip()[:400]}")


def mask_from(ignore, w, h):
    """Boolean keep-mask from fractional rectangles [x, y, w, h] in 0..1."""
    keep = np.ones((h, w), bool)
    for r in ignore or []:
        x0 = max(0, min(w, int(round(r[0] * w))))
        y0 = max(0, min(h, int(round(r[1] * h))))
        x1 = max(0, min(w, int(round((r[0] + r[2]) * w))))
        y1 = max(0, min(h, int(round((r[1] + r[3]) * h))))
        keep[y0:y1, x0:x1] = False
    return keep


def rect_slice(r, w, h):
    """Fractional [x, y, w, h] -> pixel slices, clamped to the frame."""
    x0 = max(0, min(w - 1, int(round(r[0] * w))))
    y0 = max(0, min(h - 1, int(round(r[1] * h))))
    x1 = max(x0 + 1, min(w, int(round((r[0] + r[2]) * w))))
    y1 = max(y0 + 1, min(h, int(round((r[1] + r[3]) * h))))
    return slice(y0, y1), slice(x0, x1)


def measure(path, fps=FPS, width=WIDTH, delta=PIXEL_DELTA, ignore=None,
            probe_motion=False, regions=None):
    """Activity per sample: the fraction of unmasked pixels that moved.

    `regions` is {name: [x, y, w, h]} in frame fractions; each gets its own
    track, measured on the SAME difference image so the numbers are directly
    comparable to the whole-frame one and to each other.

    Also returns, for the stillest samples, which eighth-of-the-frame cells
    did move -- that is what names a spinner without a human hunting for it.
    """
    prev = None
    keep = None
    slices = None
    act = []
    per = {k: [] for k in (regions or {})}
    cells = None
    grid = (8, 8)
    for i, fr in decode_gray(path, fps, width):
        if prev is not None:
            if keep is None:
                h, w = fr.shape
                keep = mask_from(ignore, w, h)
                slices = {k: rect_slice(v, w, h) for k, v in (regions or {}).items()}
                if probe_motion:
                    cells = np.zeros(grid, float)
            # cv2.absdiff, not `np.abs(fr.astype(np.int16) - prev)`: the
            # upcast allocates a 4 MB int16 array per frame and walks it
            # again to take the abs. Same boolean array, 17x faster
            # (3.99 ms -> 0.23 ms, verified array-equal). See frame_change()
            # in track-blur.py, where this line was half the runtime.
            d = cv2.absdiff(fr, prev) > delta
            d &= keep
            act.append(float(d.mean()))
            for k, (ys, xs) in slices.items():
                per[k].append(float(d[ys, xs].mean()))
            if probe_motion and act[-1] < STILL * 4:
                gh, gw = fr.shape[0] // grid[0], fr.shape[1] // grid[1]
                for a in range(grid[0]):
                    for b in range(grid[1]):
                        cells[a, b] += d[a * gh:(a + 1) * gh,
                                         b * gw:(b + 1) * gw].mean()
        prev = fr
    return (np.array(act, float),
            {k: np.array(v, float) for k, v in per.items()},
            cells)


def runs(act, fps, still, min_still):
    """Still runs as (start_s, end_s), merged across single-sample blips.

    A lone active sample inside a dead stretch is a compression burp or one
    mouse twitch, not the screen doing something; splitting the run there
    produces two sub-threshold halves and cuts nothing. So smooth first.
    """
    q = act < still
    if q.size >= 3:
        # close a 1-sample hole
        holes = (~q[1:-1]) & q[:-2] & q[2:]
        q[1:-1] |= holes
    out = []
    i = 0
    n = q.size
    while i < n:
        if not q[i]:
            i += 1
            continue
        j = i
        while j < n and q[j]:
            j += 1
        a, b = i / fps, j / fps
        if b - a >= min_still:
            out.append((a, b))
        i = j
    return out


def sweep(act, fps, dur, stills, min_stills):
    rows = []
    for s in stills:
        for m in min_stills:
            rr = runs(act, fps, s, m)
            dead = sum(b - a for a, b in rr)
            rows.append({"still": s, "min_still": m, "runs": len(rr),
                         "dead_s": dead, "kept_s": dur - dead,
                         "longest_s": max((b - a for a, b in rr), default=0.0)})
    return rows


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}"


def find_panel(path, samples=(0.1, 0.25, 0.4, 0.55, 0.7, 0.85), width=960):
    """Where a side panel's divider sits, as a fraction of the frame width.

    The strongest long vertical edge in the right half of ONE frame is not
    the answer -- a dialog or a scrollbar wins on any single timestamp, and
    this gave three different values on one recording. Across six timestamps
    the divider is the one edge that never moves, so the MODE of the per-frame
    argmax is what gets returned. On the books-giveaway footage that was
    x=0.748 on every recording that had the Edge side panel open.
    """
    import collections
    dur = probe(path)["duration"]
    hits = collections.Counter()
    for pct in samples:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{dur * pct:.2f}",
             "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2",
             "-pix_fmt", "gray", "-f", "rawvideo", "-"],
            capture_output=True).stdout
        h = len(out) // width
        if h < 10:
            continue
        a = np.frombuffer(out[:h * width], np.uint8).reshape(h, width).astype(np.int16)
        band = a[int(h * 0.2):int(h * 0.85)]
        g = np.abs(np.diff(band, axis=1)).mean(0)
        x0, x1 = int(width * 0.60), int(width * 0.98)
        hits[round((int(np.argmax(g[x0:x1])) + x0) / width, 3)] += 1
    if not hits:
        raise SystemExit(f"could not read frames from {path}")
    return hits.most_common(1)[0][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="video to measure")
    ap.add_argument("--out", help="write the activity track here (JSON)")
    ap.add_argument("--list", action="store_true",
                    help="price still thresholds; measures, encodes nothing")
    ap.add_argument("--probe-motion", action="store_true",
                    help="name the frame regions that move while the screen is still")
    ap.add_argument("--ignore", action="append", default=[],
                    help="x,y,w,h in FRACTIONS of the frame, excluded from the "
                         "difference; repeatable. Use for spinners and clocks.")
    ap.add_argument("--ignore-from", help="manifest whose sources[].ignore to use")
    ap.add_argument("--region", action="append", default=[],
                    help="name=x,y,w,h in FRACTIONS; repeatable. Each gets its "
                         "own activity track so the cut can tell the work area "
                         "apart from a side panel that is merely streaming.")
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--width", type=int, default=WIDTH)
    ap.add_argument("--delta", type=int, default=PIXEL_DELTA)
    ap.add_argument("--still", type=float, default=STILL)
    ap.add_argument("--min-still", type=float, default=MIN_STILL)
    ap.add_argument("--find-panel", action="store_true",
                    help="locate the vertical divider of a side panel (mode of "
                         "the strongest long vertical edge across six frames) "
                         "and print the regions it implies")
    ap.add_argument("--write-regions", metavar="MANIFEST",
                    help="with --find-panel: write main/panel regions into this manifest")
    args = ap.parse_args()

    if args.find_panel:
        x = find_panel(_env.resolve(args.src))
        print(f"{os.path.basename(args.src)}  panel divider x={x:.3f}")
        regions = {"main": [0, 0, round(x, 3), 0.98],
                   "panel": [round(x, 3), 0, round(1 - x, 3), 0.98]}
        print("  regions:", json.dumps(regions))
        if args.write_regions:
            mp = _env.resolve(args.write_regions)
            man = json.load(open(mp, encoding="utf-8"))
            man["regions"] = dict(man.get("regions") or {}, **regions)
            man["regions"]["_comment"] = (
                f"x={x:.3f}: side-panel divider found by screen-activity.py "
                f"--find-panel (mode of the strongest vertical edge across six "
                f"timestamps of {os.path.basename(args.src)})")
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(man, f, ensure_ascii=False, indent=2)
            print(f"  wrote regions into {args.write_regions}")
        return

    src = _env.resolve(args.src)
    info = probe(src)
    man = {}
    if args.ignore_from:
        man = json.load(open(_env.resolve(args.ignore_from), encoding="utf-8"))

    ignore = [[float(v) for v in s.split(",")] for s in args.ignore]
    for s in man.get("sources", []):
        if os.path.basename(_env.resolve(s.get("path", ""))) == os.path.basename(src):
            ignore += s.get("ignore", [])

    regions = {}
    for s in args.region:
        name, _, spec = s.partition("=")
        regions[name] = [float(v) for v in spec.split(",")]
    for name, rect in (man.get("regions") or {}).items():
        # a manifest region block carries prose too (_comment); only a
        # four-number list is a rectangle
        if name.startswith("_") or not isinstance(rect, list) or len(rect) != 4:
            continue
        regions.setdefault(name, rect)

    print(f"{os.path.basename(src)}  {info['width']}x{info['height']}  "
          f"{fmt(info['duration'])}  ignore={len(ignore)} rect(s)"
          f"{'  regions=' + ','.join(regions) if regions else ''}")
    act, per, cells = measure(src, args.fps, args.width, args.delta, ignore,
                              args.probe_motion, regions)
    dur = act.size / args.fps

    if args.probe_motion and cells is not None:
        tot = cells.sum() or 1.0
        flat = [(cells[a, b] / tot, a, b) for a in range(8) for b in range(8)]
        flat.sort(reverse=True)
        print("\n  motion during still stretches, by frame cell (x,y in eighths):")
        for share, a, b in flat[:6]:
            if share < 0.02:
                break
            print(f"    x={b/8:.3f} y={a/8:.3f} w=0.125 h=0.125   {share*100:5.1f}%"
                  f"   --ignore {b/8:.3f},{a/8:.3f},0.125,0.125")

    if per and args.list:
        print("\n  share of runtime each region is the ONLY thing moving:")
        names = list(per)
        for k in names:
            others = [per[o] for o in names if o != k]
            alone = (per[k] >= args.still)
            for o in others:
                alone &= (o < args.still)
            print(f"    {k:<10} active {(per[k] >= args.still).mean()*100:5.1f}%"
                  f"   alone {alone.mean()*100:5.1f}%")
        quiet = np.ones(act.size, bool)
        for k in names:
            quiet &= (per[k] < args.still)
        print(f"    {'(nothing)':<10} {' ' * 14}{quiet.mean()*100:5.1f}%")

    if args.list:
        stills = [0.001, 0.002, 0.004, 0.008, 0.015]
        min_stills = [0.8, 1.2, 2.0, 3.0]
        print(f"\n  {'still':>7} {'min':>5} {'runs':>5} {'dead':>8} {'kept':>8} {'longest':>8}")
        for r in sweep(act, args.fps, dur, stills, min_stills):
            mark = " <-" if (r["still"] == args.still and
                             r["min_still"] == args.min_still) else ""
            print(f"  {r['still']:>7.3f} {r['min_still']:>5.1f} {r['runs']:>5} "
                  f"{fmt(r['dead_s']):>8} {fmt(r['kept_s']):>8} "
                  f"{fmt(r['longest_s']):>8}{mark}")

        rr = runs(act, args.fps, args.still, args.min_still)
        print(f"\n  longest still runs at still={args.still} min_still={args.min_still}:")
        for a, b in sorted(rr, key=lambda x: x[1] - x[0], reverse=True)[:12]:
            print(f"    {fmt(a)} -> {fmt(b)}   {b - a:6.1f}s")

    if args.out:
        out = _env.resolve(args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({
                "src": _env.resolve(src),
                "duration": info["duration"],
                "sample_fps": args.fps,
                "width": args.width,
                "delta": args.delta,
                "ignore": ignore,
                "regions": regions,
                "activity": [round(v, 6) for v in act.tolist()],
                "region_activity": {k: [round(x, 6) for x in v.tolist()]
                                    for k, v in per.items()},
            }, f)
        print(f"\n  wrote {args.out}  ({act.size} samples)")


if __name__ == "__main__":
    main()
