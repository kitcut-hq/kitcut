#!/usr/bin/env python
"""Find time ranges where the SOURCE video already has its own graphic overlay
in the lower part of the frame, so burned-in captions can be lifted clear of it.

Discriminating a graphic from red scene content (this video contains a red car
and a meat counter) needs more than "is there red". A graphic is:
  * near-pure #FF0000 -- scene reds are darker and desaturated
  * arranged in long horizontal runs (a filled bar/pill, not texture)
  * spanning several consecutive rows (a rectangle, not speckle)
  * containing near-white pixels inside it (the caption text)

Invoke as:  python -X utf8 -E scripts/detect-overlays.py ...
"""
import sys, os, json, argparse, subprocess

# Drop any site-packages that belongs to a DIFFERENT Python install. A stale
# machine-wide PYTHONPATH gets prepended to sys.path and shadows this
# interpreter's packages with incompatible ones (or, once that install is
# removed, with nothing at all). sys.path is frozen at startup so clearing
# os.environ in-process cannot help -- hence also `-E` at the call site.
import sysconfig as _sc, site as _site
def _norm(p):
    return os.path.normcase(os.path.abspath(p))
_own = {_norm(p) for p in (_sc.get_paths().get("purelib"),
                           _sc.get_paths().get("platlib")) if p}
for _getter in (lambda: [_site.getusersitepackages()], _site.getsitepackages):
    try:
        _own.update(_norm(p) for p in _getter())
    except Exception:
        pass          # user site is where Store Python puts pip installs
sys.path[:] = [p for p in sys.path
               if "site-packages" not in p.lower() or _norm(p) in _own]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np

ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
SW = 480                   # analysis width; height follows the source aspect


def src_dims(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
                       capture_output=True, text=True, env=ENV)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def decode(src, fps, sh, hwaccel=True):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if hwaccel:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", src, "-vf", "fps=%g,scale=%d:%d" % (fps, SW, sh),
            "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)


def longest_run(row):
    best = run = 0
    for v in row:
        run = run + 1 if v else 0
        if run > best:
            best = run
    return best


def analyse(frame, y_from, min_run, min_rows, target=None, tol=60, fy=4.0):
    """Return (present, top_y, bottom_y) in FULL-RES coords.

    Colour-agnostic by default. A graphic is separated from saturated *scene*
    content (armchairs, clothing, a red car) by requiring all of:
      * a single near-uniform colour, not a shaded gradient
      * long contiguous horizontal runs of it -- a filled bar, not texture
      * several consecutive such rows -- a rectangle, not speckle
      * near-white pixels inside the block -- the caption text
    The text test is the strongest discriminator; furniture has no white text on it.

    Pass `target` (an (r,g,b) tuple) to look for one specific colour instead.
    """
    band = frame[y_from:, :, :].astype(np.int16)
    mx = band.max(axis=2)
    mn = band.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1)

    if target is None:
        # dominant saturated colour in the band, quantised
        cand = band[(sat > 0.35) & (mx > 90)]
        if len(cand) < min_run * min_rows:
            return False, None, None
        q = (cand // 32).astype(np.int32)
        keys, counts = np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2], return_counts=True)
        k = keys[counts.argmax()]
        target = np.array([(k // 1024) * 32 + 16, ((k // 32) % 32) * 32 + 16, (k % 32) * 32 + 16])
    else:
        target = np.array(target, dtype=np.int16)

    # Per-channel (Chebyshev) distance, NOT sum-of-absolute. Sum-of-abs conflates
    # "slightly off in every channel" with "wildly off in one", so a tolerance
    # loose enough to catch antialiased #FF0000 edges also lets orange through.
    # Chebyshev at 70 reproduces the original r>=200 & g<=70 & b<=70 test, which
    # was validated at 9/9 real graphics with no false positives.
    dist = np.abs(band - target.reshape(1, 1, 3)).max(axis=2)
    mask = dist <= tol

    good_rows = [yi for yi in range(band.shape[0])
                 if mask[yi].any() and longest_run(mask[yi]) >= min_run]
    if len(good_rows) < min_rows:
        return False, None, None

    lo, hi = min(good_rows), max(good_rows)
    block = band[lo:hi + 1]
    if mask[lo:hi + 1].mean() < 0.25:                 # must be a filled shape
        return False, None, None
    bright = (block[:, :, 0] > 200) & (block[:, :, 1] > 200) & (block[:, :, 2] > 200)
    if bright.sum() < 12:                             # caption text inside it
        return False, None, None
    return True, int((y_from + lo) * fy), int((y_from + hi) * fy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--y-from", type=int, default=620, help="y to start scanning (1080p-reference px, auto-scaled)")
    ap.add_argument("--min-run-px", type=int, default=240, help="min horizontal run (1080p-reference px, auto-scaled)")
    ap.add_argument("--min-rows-px", type=int, default=28, help="min block height (1080p-reference px, auto-scaled)")
    ap.add_argument("--pad", type=float, default=0.6, help="seconds of padding each side")
    ap.add_argument("--merge-gap", type=float, default=1.5)
    ap.add_argument("--no-hwaccel", action="store_true")
    ap.add_argument("--colour", default="#FF0000",
                    help="#RRGGBB of the source graphic to hunt for. Targeted mode is "
                         "the reliable one -- set this to the channel's lower-third "
                         "colour. Default is the red used by many Ukrainian channels.")
    ap.add_argument("--auto", action="store_true",
                    help="EXPERIMENTAL colour-agnostic mode. Produces false positives on "
                         "footage with large saturated props (armchairs, clothing); "
                         "verify its output before trusting it.")
    ap.add_argument("--tol", type=int, default=70,
                    help="per-channel colour tolerance (Chebyshev)")
    ap.add_argument("--max-block-px", type=int, default=170,
                    help="full-res: reject blocks taller than this; a caption bar is "
                         "short, scene content bleeding to the frame edge is not")
    args = ap.parse_args()

    target = None
    if not args.auto:
        h = args.colour.lstrip("#")
        target = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    # CLI px thresholds are authored against a 1920x1080 reference; scale them to
    # the actual source, then down to analysis resolution. For a 1080p source
    # every value reduces to exactly the original numbers.
    w, h = src_dims(args.src)
    SH = max(2, int(round(h * SW / w / 2.0)) * 2)
    fx, fy = w / float(SW), h / float(SH)
    y_from = int(args.y_from * h / 1080.0 / fy)
    min_run = max(1, int(args.min_run_px * w / 1920.0 / fx))
    min_rows = max(1, int(args.min_rows_px * h / 1080.0 / fy))
    max_block = int(args.max_block_px * h / 1080.0)
    print("source %dx%d -> analysis %dx%d" % (w, h, SW, SH))

    proc = decode(args.src, args.fps, SH, not args.no_hwaccel)
    fs = SW * SH * 3
    hits = []
    i = 0
    while True:
        buf = proc.stdout.read(fs)
        if len(buf) < fs:
            break
        fr = np.frombuffer(buf, dtype=np.uint8).reshape(SH, SW, 3)
        present, top, bot = analyse(fr, y_from, min_run, min_rows, target, args.tol, fy)
        if present and (bot - top) > max_block:
            present = False          # too tall to be a caption bar
        if present:
            hits.append((i / args.fps, top, bot))
        i += 1
    proc.stdout.close()
    proc.wait()
    print("frames analysed: %d (%.1f s at %g fps)" % (i, i / args.fps, args.fps))
    print("frames with a source graphic: %d" % len(hits))

    # group consecutive hits into ranges
    ranges = []
    for t, top, bot in hits:
        if ranges and t - ranges[-1]["_last"] <= args.merge_gap:
            r = ranges[-1]
            r["_last"] = t
            r["top_y"] = min(r["top_y"], top)
            r["bottom_y"] = max(r["bottom_y"], bot)
        else:
            ranges.append(dict(start=t, _last=t, top_y=top, bottom_y=bot))

    out = []
    for r in ranges:
        s = max(0.0, r["start"] - args.pad)
        e = r["_last"] + 1.0 / args.fps + args.pad
        if e - s < 0.5:
            continue
        out.append(dict(start=round(s, 2), end=round(e, 2),
                        top_y=int(r["top_y"]), bottom_y=int(r["bottom_y"])))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("source-graphic ranges: %d" % len(out))
    for r in out:
        print("  %7.2f - %7.2f s  (%5.1f s)  y %d..%d"
              % (r["start"], r["end"], r["end"] - r["start"], r["top_y"], r["bottom_y"]))
    tot = sum(r["end"] - r["start"] for r in out)
    print("total covered: %.1f s" % tot)


if __name__ == "__main__":
    main()
