#!/usr/bin/env python
"""Show every redaction before a single frame is encoded -- and stop.

The most expensive mistake of the first silent-screencast edit was not a
bug. The full film was rendered five times with a look the user had never
seen -- black boxes, then pixelated panels, then two sources cut -- and the
user had asked for a blur. About an hour and a half of a six-hour session
went to encoding a decision that was never theirs to lose.

So this is a gate. It writes ONE sheet, `temp/review/redaction-sheet.jpg`:
for every secret the tracker follows, its first appearance in each source,
before | after with the real blur applied through the real mask; every
hand-measured rect the same way; and the numbers that matter -- secrets,
templates, hand rects, how much of the frame the blur covers. Then it exits
non-zero. `--approve` records the approval in project.json together with a
fingerprint of what was approved, so the pipeline can tell an approved look
from a changed one, and a render cannot start on a look nobody has seen.

The "after" tile is computed in numpy the way the render's filtergraph does
it (downscale, gaussian, upscale, shown through the mask), so what the sheet
shows is what the film will do, not an approximation of it.

Invoke as:  python scripts/redaction-review.py --manifest projects/<id>/screen.json
"""
import sys
import os
import json
import time
import hashlib
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TILE_W, TILE_H = 440, 150      # one before/after crop
PAD = 10


def frame_at(path, t):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", path,
         "-frames:v", "1", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    info = probe(path)
    n = info["w"] * info["h"] * 3
    if len(out) < n:
        return None
    return np.frombuffer(out[:n], np.uint8).reshape(info["h"], info["w"], 3)


_probe_cache = {}


def probe(path):
    if path in _probe_cache:
        return _probe_cache[path]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    r = {"w": int(st["width"]), "h": int(st["height"]),
         "fps": float(num) / float(den) if float(den or 0) else 30.0,
         "dur": float((d.get("format") or {}).get("duration") or 0.0)}
    _probe_cache[path] = r
    return r


def blur_like_render(img, cfg):
    """The render's blur: scale down, gaussian, scale back up."""
    d = int(cfg.get("blur_downscale", 8))
    sigma = float(cfg.get("blur_sigma", 3.0))
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(2, w // d), max(2, h // d)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def composite(frame, mask, cfg):
    """Frame shown through a 0..255 mask: blurred where the mask is white."""
    bl = blur_like_render(frame, cfg)
    a = (mask.astype(np.float32) / 255.0)[..., None]
    return (frame * (1 - a) + bl * a).astype(np.uint8)


def crop_around(img, box, out_w=TILE_W, out_h=TILE_H):
    """A tile centred on the box, wide enough to show context."""
    x0, y0, x1, y1 = box
    H, W = img.shape[:2]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    cw, ch = max(bw * 3, out_w), max(bh * 4, out_h)
    # keep the tile's aspect
    if cw / ch > out_w / out_h:
        ch = int(cw * out_h / out_w)
    else:
        cw = int(ch * out_w / out_h)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    sx, sy = max(0, min(W - cw, cx - cw // 2)), max(0, min(H - ch, cy - ch // 2))
    tile = img[sy:sy + ch, sx:sx + cw]
    return cv2.resize(tile, (out_w, out_h), interpolation=cv2.INTER_AREA)


def label(canvas, text, x, y, color=(235, 235, 235), scale=0.5):
    cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def mask_for_frame(tdir, runs, frame_idx, size):
    """The mask PNG of the run containing this frame."""
    for n, (f0, f1, _boxes) in enumerate(runs):
        if f0 <= frame_idx <= f1:
            p = os.path.join(tdir, f"mask_{n:06d}.png")
            m = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if m is not None:
                return m
            break
    return np.zeros((size[1], size[0]), np.uint8)


def hand_mask(rect, size):
    m = np.zeros((size[1], size[0]), np.uint8)
    x, y, w, h = rect
    x0, y0 = int(x * size[0]), int(y * size[1])
    x1, y1 = int((x + w) * size[0]), int((y + h) * size[1])
    m[y0:y1, x0:x1] = 255
    return cv2.GaussianBlur(m, (9, 9), 0)


def redact_secret(key, kind):
    """Show the reviewer WHICH secret without printing it: first 3, last 2."""
    digits = key.split(":", 1)[-1]
    if len(digits) > 6:
        return f"{kind} {digits[:3]}…{digits[-2:]}"
    return f"{kind} {digits}"


def collect(man, mpath, cfg):
    """Every tile the sheet needs: (title, source, t, before, after, area%)."""
    tiles = []
    stats = {"secrets": set(), "templates": 0, "hand": 0, "coverage": [],
             "sources_tracked": 0, "sources_hand": 0}
    pdir = os.path.dirname(mpath)
    for s in man["sources"]:
        if s.get("skip"):
            continue
        src = _env.resolve(s.get("proxy") or s["path"])
        base = os.path.splitext(os.path.basename(s["path"]))[0]
        info = probe(src)
        size = (info["w"], info["h"])
        tdir = _env.resolve(s["track"]) if s.get("track") else None
        tj = os.path.join(tdir, "track.json") if tdir else None
        if tj and os.path.exists(tj):
            d = json.load(open(tj, encoding="utf-8"))
            runs = d.get("runs") or []
            keys = d.get("keys") or {}
            stats["sources_tracked"] += 1
            stats["templates"] += int(d.get("templates") or 0)
            fps = float(d.get("fps") or info["fps"])
            # coverage, duration-weighted
            tot_f = 0
            for n, (f0, f1, boxes) in enumerate(runs):
                area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1, *_ in boxes)
                stats["coverage"].append((area / float(size[0] * size[1]), f1 - f0 + 1))
                tot_f += f1 - f0 + 1
            first = {}
            for f0, f1, boxes in runs:
                for x0, y0, x1, y1, key in boxes:
                    if key not in first:
                        first[key] = (f0, (x0, y0, x1, y1))
            for key, (f0, box) in sorted(first.items(), key=lambda kv: kv[1][0]):
                stats["secrets"].add(key)
                t = f0 / fps
                fr = frame_at(src, t)
                if fr is None:
                    continue
                m = mask_for_frame(tdir, runs, f0, size)
                after = composite(fr, m, cfg)
                kind = (keys.get(key) or {}).get("kind", key.split(":")[0])
                tiles.append((redact_secret(key, kind), base, t,
                              crop_around(fr, box), crop_around(after, box)))
        for b in s.get("blur") or []:
            stats["hand"] += 1
            stats["sources_hand"] += 1
            w = b.get("when") or [0.0, info["dur"]]
            t = (w[0] + w[1]) / 2.0
            fr = frame_at(src, t)
            if fr is None:
                continue
            m = hand_mask(b["rect"], size)
            after = composite(fr, m, cfg)
            x, y, bw, bh = b["rect"]
            box = (int(x * size[0]), int(y * size[1]),
                   int((x + bw) * size[0]), int((y + bh) * size[1]))
            tiles.append((("hand: " + (b.get("_why") or ""))[:44], base, t,
                          crop_around(fr, box), crop_around(after, box)))
    return tiles, stats


def render_sheet(tiles, stats, cfg, out):
    cols = 2                              # two secrets per row, each before|after
    cell_w = TILE_W * 2 + PAD * 3
    cell_h = TILE_H + 44
    rows = (len(tiles) + cols - 1) // cols
    head = 96
    W = cols * cell_w + PAD
    H = head + rows * cell_h + PAD
    canvas = np.full((H, W, 3), 24, np.uint8)
    cov = stats["coverage"]
    cov_mean = (sum(a * n for a, n in cov) / max(1, sum(n for _, n in cov))) * 100
    cov_max = max((a for a, _ in cov), default=0.0) * 100
    label(canvas, "REDACTION REVIEW -- nothing renders until this is approved",
          PAD, 30, (120, 200, 255), 0.7)
    label(canvas, f"{len(stats['secrets'])} secret(s), {stats['templates']} template(s), "
                  f"{stats['hand']} hand rect(s)   mode: {cfg.get('blur_mode', 'blur')}   "
                  f"blur covers {cov_mean:.1f}% of the frame on average, {cov_max:.1f}% at most",
          PAD, 58, (200, 200, 200), 0.5)
    label(canvas, "left: as recorded   right: as it will render   "
                  "approve with:  redaction-review.py --manifest <screen.json> --approve",
          PAD, 82, (160, 160, 160), 0.45)
    for i, (title, base, t, before, after) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = PAD + c * cell_w
        y = head + r * cell_h
        canvas[y + 30:y + 30 + TILE_H, x:x + TILE_W] = before
        canvas[y + 30:y + 30 + TILE_H, x + TILE_W + PAD:x + TILE_W * 2 + PAD] = after
        label(canvas, f"{title}   {base}  @ {int(t) // 60}:{t % 60:04.1f}", x, y + 20)
    cv2.imwrite(out, canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return cov_mean, cov_max


def fingerprint(man, mpath):
    """What exactly is being approved: the manifest's redaction, and the
    track files' identities."""
    h = hashlib.sha1()
    keep = {"cut": man.get("cut"), "sources": [
        {"path": s["path"], "blur": s.get("blur"), "track": s.get("track"),
         "skip": s.get("skip")} for s in man.get("sources", [])]}
    h.update(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for s in man.get("sources", []):
        if s.get("track"):
            tj = os.path.join(_env.resolve(s["track"]), "track.json")
            try:
                st = os.stat(tj)
                h.update(f"{tj}:{st.st_size}:{int(st.st_mtime)}".encode())
            except OSError:
                h.update(f"{tj}:missing".encode())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", help="default: <project>/temp/review/redaction-sheet.jpg")
    ap.add_argument("--approve", action="store_true",
                    help="record approval of the CURRENT look in project.json")
    ap.add_argument("--check", action="store_true",
                    help="exit 0 if the current look is already approved, else 3")
    args = ap.parse_args()

    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cfg = man.get("cut") or {}
    pdir = _project.find_project_dir(mpath) or os.path.dirname(mpath)
    pid = os.path.basename(pdir)
    fp = fingerprint(man, mpath)
    doc = _project.load(pid) or {}
    approved = (doc.get("review") or {}).get("fingerprint")

    if args.check:
        ok = approved == fp
        print(f"review: {'approved' if ok else 'NOT approved'} for the current look ({fp})")
        raise SystemExit(0 if ok else 3)

    if args.approve:
        doc.setdefault("review", {})
        doc["review"] = {"fingerprint": fp,
                         "approved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "sheet": _project.norm(args.out or os.path.join(
                             pdir, "temp", "review", "redaction-sheet.jpg"))}
        with open(_project.path_for(pid), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        _project.record(pid, "redaction-review", note=f"redaction look approved ({fp})")
        print(f"approved the current redaction look ({fp}); recorded in project.json")
        return

    out = _env.resolve(args.out) if args.out else os.path.join(pdir, "temp", "review",
                                                               "redaction-sheet.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tiles, stats = collect(man, mpath, cfg)
    if not tiles:
        raise SystemExit("nothing to review: no track dirs with track.json and no hand rects")
    cov_mean, cov_max = render_sheet(tiles, stats, cfg, out)
    print(f"{len(stats['secrets'])} secret(s), {stats['templates']} template(s), "
          f"{stats['hand']} hand rect(s); blur covers {cov_mean:.1f}% of the frame "
          f"on average, {cov_max:.1f}% at most")
    print(f"sheet -> {out}")
    if approved == fp:
        print(f"this exact look is already approved ({fp})")
        return
    print(f"\nSTOP: review the sheet, then approve with\n"
          f"  python scripts/redaction-review.py --manifest {args.manifest} --approve")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
