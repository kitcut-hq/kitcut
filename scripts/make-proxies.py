#!/usr/bin/env python
"""Transcode a manifest's sources once, at the size the work actually happens.

Every pass over this footage -- the activity measurement, the contact sheets,
the proof frames, the render itself -- decodes 3840x2280 and then throws most
of those pixels away in its first filter. `screen-activity.py` analyses at 320
pixels wide and still pays to decode 4K to get there; the render's very first
step is a scale to 1080p. That decode is the dominant cost of the whole
pipeline, and it is paid again on every iteration.

So pay it once. A proxy at the canvas fit size is not a preview of the work --
it IS the working resolution, because the deliverable is 1080p and because
every rectangle in this pipeline is stored as a FRACTION of the frame rather
than in pixels. Proxy and original are interchangeable by construction; there
is no "apply the decisions to the big one" step to get wrong.

Where a proxy does NOT help, and it is worth knowing why: OCR. Text recognition
is resolution-bound, so shrinking first costs recall on exactly the step that
costs the most. `scan-pii.py` reads the ORIGINAL, and the lever there is fewer
frames (--skip-static), not smaller ones.

Quality is not assumed. Screen text is where H.264 hurts most, so the proxy is
encoded near-transparent and --verify scores it against the source frame by
frame; anything below the SSIM floor is reported rather than shipped.

Invoke as:  python scripts/make-proxies.py --manifest projects/<id>/screen.json --list
"""
import sys
import os
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402

ROOT = _env.ROOT

CQ = 16          # near-transparent for screen text; --verify checks it
SSIM_FLOOR = 0.985


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries",
         "format=duration,size", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    fm = d.get("format") or {}
    return {"width": int(st.get("width") or 0), "height": int(st.get("height") or 0),
            "duration": float(fm.get("duration") or 0.0),
            "size": int(fm.get("size") or 0)}


def fit(sw, sh, cw, ch):
    """The size a source lands at inside the canvas, preserving aspect."""
    f = min(cw / sw, ch / sh)
    return (max(2, int(round(sw * f)) // 2 * 2),
            max(2, int(round(sh * f)) // 2 * 2))


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0


def gray_frames(path, fps, width):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path,
         "-vf", f"fps={fps},scale={width}:-2", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    info = probe(path)
    h = max(2, int(round(width * info["height"] / info["width"])) // 2 * 2)
    n = width * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, width)
    p.stdout.close()
    p.wait()


def ssim(a, b):
    """Global SSIM on one pair of frames -- enough to catch a bad transcode.

    Deliberately NOT the per-frame join test compare-videos.py does: this is
    asking "did the picture survive re-encoding", not "is this the right
    frame", and the two questions want different instruments.
    """
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2) /
            ((mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2)))


def verify(src, dst, fps=0.2, width=640):
    """Score the proxy against its source on sampled frames."""
    scores = []
    for a, b in zip(gray_frames(src, fps, width), gray_frames(dst, fps, width)):
        if a.shape != b.shape:
            return None, "frame sizes differ"
        scores.append(ssim(a, b))
    if not scores:
        return None, "no frames compared"
    return (float(np.mean(scores)), float(np.min(scores))), ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", help="default: <project>/temp/proxy")
    ap.add_argument("--list", action="store_true",
                    help="price the transcode; encodes nothing")
    ap.add_argument("--verify", action="store_true",
                    help="score each proxy against its source after building")
    ap.add_argument("--force", action="store_true",
                    help="rebuild proxies that already exist")
    ap.add_argument("--cq", type=int, default=CQ)
    ap.add_argument("--write", action="store_true", default=True,
                    help="record the proxy path on each source in the manifest")
    args = ap.parse_args()

    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cw, ch = (man.get("cut") or {}).get("canvas", [1920, 1080])
    outdir = _env.resolve(args.outdir) if args.outdir else \
        os.path.join(os.path.dirname(mpath), "temp", "proxy")
    os.makedirs(outdir, exist_ok=True)

    rows = []
    for s in man["sources"]:
        src = _env.resolve(s["path"])
        info = probe(src)
        vw, vh = fit(info["width"], info["height"], cw, ch)
        dst = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".mp4")
        rows.append((s, src, dst, info, vw, vh))

    print(f"{os.path.basename(mpath)}  canvas {cw}x{ch}  -> {os.path.relpath(outdir, ROOT)}")
    print(f"  {'source':<40} {'from':>12} {'to':>12} {'size':>9} {'state':>9}")
    for s, src, dst, info, vw, vh in rows:
        have = os.path.exists(dst) and not args.force
        state = "have" if have else "build"
        if info["width"] == vw and info["height"] == vh:
            state = "native"
        print(f"  {os.path.basename(src)[:40]:<40} "
              f"{info['width']}x{info['height']:<7} {vw}x{vh:<7} "
              f"{human(info['size']):>9} {state:>9}")
    if args.list:
        return

    for s, src, dst, info, vw, vh in rows:
        rel = os.path.relpath(dst, _env.workspace()).replace("\\", "/")
        if info["width"] == vw and info["height"] == vh:
            print(f"\n  {os.path.basename(src)}: already at {vw}x{vh}, no proxy needed")
            continue
        if os.path.exists(dst) and not args.force:
            print(f"\n  {os.path.basename(src)}: have {rel}")
        else:
            print(f"\n  {os.path.basename(src)} -> {vw}x{vh} ...")
            cmd = ["ffmpeg", "-v", "error", "-stats", "-nostdin", "-y",
                   "-hwaccel", "cuda", "-i", src,
                   "-vf", f"scale={vw}:{vh}:flags=lanczos,setsar=1",
                   "-an",
                   "-c:v", "h264_nvenc", "-preset", "p7", "-rc", "vbr",
                   "-cq", str(args.cq), "-b:v", "0", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", dst]
            r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
            if r.returncode != 0:
                tail = "\n".join((r.stderr or "").strip().splitlines()[-15:])
                raise SystemExit(f"ffmpeg failed ({r.returncode}):\n{tail}")
            print(f"    {human(probe(dst)['size'])}  "
                  f"({probe(dst)['size'] / max(1, info['size']) * 100:.0f}% of source)")

        if args.verify:
            got, err = verify(src, dst)
            if got is None:
                print(f"    VERIFY FAILED: {err}")
                continue
            mean, worst = got
            flag = "" if worst >= SSIM_FLOOR else "   <- BELOW FLOOR"
            print(f"    ssim mean {mean:.4f}  worst {worst:.4f}"
                  f"  (floor {SSIM_FLOOR}){flag}")

        if args.write:
            s["proxy"] = rel

    if args.write:
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        print(f"\n  wrote proxy paths into {args.manifest}")


if __name__ == "__main__":
    main()
