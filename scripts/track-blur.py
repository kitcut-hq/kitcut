#!/usr/bin/env python
"""Track sensitive pixels across a screen recording, and emit a blur mask
that follows them.

The wrong primitive, which this replaces: a blur RECTANGLE anchored to a TIME
window. scan-pii reports "this phone number is at (x,y) around t=204", and a
rect gated to [196, 212] is correct at the sampled instant and wrong the
moment the page scrolls -- the field moves, the rect does not, so the blur
lands on the wrong rows and the secret stays sharp somewhere else. Every
failure this project hit chasing leaks (bank rows half-covered, a record
sliding out from under its rect, blankets over whole panels as a last resort)
was this one mismatch.

The right primitive is standard: DETECT ONCE, THEN TRACK -- what editors call
tracked redaction. And a screen recording is the easy case for it, because a
browser renders the same text pixel-identically on every frame it appears:
no lighting, no perspective, no noise. So the secret is captured once as a
TEMPLATE (the actual pixels scan-pii found), and every frame is searched for
those pixels with normalized cross-correlation (cv2.matchTemplate). Wherever
they are -- scrolled, repeated twice on screen, back after a page change --
that is where the blur goes, sized exactly to the match. Content-anchored,
and minimal by construction.

The cost model, because a naive per-frame search would crawl:

  unchanged frame        nothing runs; the previous boxes are reused. On this
                         footage 60-80% of frames change nothing.
  tracked instance       searched only in a local window around where it was.
  lost / cold template   full-frame search at HALF scale, refined at full
                         scale on a hit; cold templates only every N frames.

Output per source: `track.json` (the box timeline), a folder of mask PNGs
(one per stretch of stable boxes -- a still page costs one PNG however long
it holds), and `masks.txt`, a concat listing that turns them into a mask
stream. `screen-cut.py` feeds it as a second input and blurs THROUGH it: the
frame is blurred once, and the mask decides where that blur shows. Rect count
no longer multiplies per-frame filter work.

The masks are built against the PROXY timeline (that is what renders), and a
mask stream is deliberately written LONGER than its source: alphamerge pairs
frames one-to-one, and a mask that ends early stalls the graph the same way
the looped-PNG alpha did in the shorts pipeline (see README gotchas).

Invoke as:  python scripts/track-blur.py --src <proxy.mp4> --pii <pii.json> --outdir <dir> --list
"""
import sys
import os
import re
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import cv2  # noqa: E402

ROOT = _env.ROOT

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

KINDS = {"card", "cvv", "expiry", "iban", "phone", "email", "balance"}
THR = 0.86            # NCC score to accept a match at full resolution; a
                      # near-miss blur lands a few pixels off (cosmetic), a
                      # near-miss REJECTION is a leak, so err low
THR_HALF = 0.80       # looser at half scale; a hit is refined at full res
DILATE = 6            # pixels added around every matched box
COLD_EVERY = 15       # frames between full searches for a long-unseen template
CHANGE_SKIP = 0.0006  # frame-diff fraction below which nothing is re-searched
MAX_INSTANCES = 8     # same secret shown more than this is a listing, not a leak

# Verified on the Privat24 clip, where the first version failed two ways:
#
#   SCALE. The app renders the same account number at several sizes -- the
#   card list, the detail view, the transfer form -- and NCC does not match
#   across scale. A template captured in one view left the others sharp, so
#   the full search now also tries the template resized by each of these.
SCALES = (1.0, 0.75, 1.3)
#   TRUST. A 39x11 "UA39" patch carries so little structure that it cleared
#   0.90 against a FACE. A template below this size or contrast is not
#   evidence of anything and is refused at collection time; the bigger
#   templates that share its row cover the row anyway.
MIN_TPL_W = 36
MIN_TPL_STD = 12.0
#   A small patch is not refused -- a spreadsheet cell is 44x12 and it holds a
#   phone number -- it is held to a STRICTER match. Self-match is ~1.0, so
#   recall keeps; the face-shaped 0.90 false positive does not clear 0.93.
SMALL_TPL_AREA = 800
THR_SMALL = 0.93
#   SIZE ROUTE. Below this height a template is searched at full resolution,
#   never through the half-scale prefilter -- see full_search().
SMALL_TPL_H = 24


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    return {"w": int(st["width"]), "h": int(st["height"]),
            "fps": float(num) / float(den) if float(den or 0) else 30.0,
            "dur": float((d.get("format") or {}).get("duration") or 0.0)}


def frame_at(path, t, w, h):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.2f}", "-i", path,
         "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    if len(out) < w * h:
        return None
    return np.frombuffer(out[:w * h], np.uint8).reshape(h, w)


def gray_stream(path, w, h, fps):
    """Every frame, CFR at the container's own rate, so index == time*fps."""
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path,
         "-vf", f"fps={fps}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w)
    p.stdout.close()
    p.wait()


def norm_key(kind, text):
    d = re.sub(r"\D", "", text)
    return f"{kind}:{d}" if d else f"{kind}:{re.sub(r'[^a-z0-9]', '', text.lower())}"


def collect_templates(src, pii_paths, benign, kinds, info):
    """One template per distinct secret and rendered size, cut from the frames
    OCR found it on.

    Hits are POOLED across every file given: the pixels are always cut from
    frames of the file they were found in (a template must be this source's
    rendering pipeline), but the pool decides WHAT to look for -- a secret
    OCR read in one recording is searched for in all of them.
    """
    flat_benign = [b.replace(" ", "") for b in benign]
    by_key = {}
    for pp in pii_paths:
        d = json.load(open(_env.resolve(pp), encoding="utf-8"))
        own_src = d.get("src", "")
        for h in d["hits"]:
            if h["kind"] not in kinds:
                continue
            flat = h["text"].replace(" ", "")
            if any(b in flat for b in flat_benign):
                continue
            h = dict(h, _src=own_src, _fps=d.get("sample_fps") or 0.25)
            by_key.setdefault(norm_key(h["kind"], h["text"]), []).append(h)

    templates = []
    for key, hits in sorted(by_key.items()):
        # One variant per distinct RENDERING: height bucket AND the text the
        # OCR line actually carried. Bucketing by height alone and taking the
        # widest was the recall killer the harness exposed (30.8%): the widest
        # line holding a phone number is the panel sentence that CONTAINS it
        # -- "Київ, відділення 57, 0939589090, Стрельченко Марія" -- and that
        # patch can never match the bare number in a spreadsheet cell or a
        # form field. Same digits, different surroundings, one template. Now
        # each surrounding gets its own.
        # ...and WIDTH: the same digits at the same height in Notepad (90 px,
        # monospace) and in the panel (151 px, serif) are different pixels.
        # Height alone put the serif template on the Notepad frames: 1/4.
        def bkey(h):
            return (int(round(h["rect"][3] * info["h"] / 4)),
                    int(round(h["rect"][2] * info["w"] / 12)),
                    re.sub(r"\s+", "", h["text"])[:48])
        buckets, seen = {}, {}
        for h in hits:
            k = bkey(h)
            seen[k] = seen.get(k, 0) + 1
            cur = buckets.get(k)
            if cur is None or h["conf"] > cur["conf"]:
                buckets[k] = h
        # most-seen renderings first, so the cap keeps the common ones
        ordered = sorted(buckets.items(), key=lambda kv: -seen[kv[0]])
        for _k, h in ordered[:12]:
            x, y, w, hh = h["rect"]
            px, py = int(x * info["w"]), int(y * info["h"])
            pw, ph = int(w * info["w"]), int(hh * info["h"])
            if pw < MIN_TPL_W or ph < 10:
                continue
            # Cut the pixels from the file the hit was FOUND in -- at this
            # source's working resolution, so a pooled template is directly
            # comparable. The pii scans read the 4K originals; the proxy of
            # that same recording is the frame the render actually sees.
            hsrc = h.get("_src") or src
            hsrc = hsrc.replace("\\", "/").replace("/sources/", "/temp/proxy/")
            if not os.path.exists(hsrc):
                hsrc = h.get("_src") or src
            # The hit's time can be off by up to one sample period: scans made
            # before scan-pii recorded real pts_time label the slot, not the
            # frame, and that put a "16.0 s" spreadsheet cell on a Notepad
            # window. So probe the slot and take the crop with the most
            # structure -- text has variance, a wrong frame's blank does not.
            period = 1.0 / float(h.get("_fps") or 0.25)
            best, best_std = None, -1.0
            for dt_ in (0.0, period * 0.5, period, -period * 0.5, period * 0.25, period * 0.75):
                fr = frame_at(hsrc, max(0.0, h["t"] + dt_), info["w"], info["h"])
                if fr is None:
                    continue
                cand = fr[max(0, py):py + ph, max(0, px):px + pw]
                if cand.size and cand.std() > best_std:
                    best, best_std = cand, float(cand.std())
                if best_std >= 40:
                    break
            patch = best
            if patch is None or patch.size == 0 or patch.std() < MIN_TPL_STD:
                continue  # a flat patch matches everything; useless and unsafe
            variants = []
            for s in SCALES:
                sw, sh = int(pw * s), int(ph * s)
                if sw < MIN_TPL_W // 2 or sh < 8:
                    continue
                img = patch if s == 1.0 else cv2.resize(patch, (sw, sh))
                variants.append({
                    "img": img,
                    "half": cv2.resize(img, (max(2, sw // 2), max(2, sh // 2))),
                })
            templates.append({
                "key": key, "kind": h["kind"], "text": h["text"][:40],
                "img": patch, "variants": variants,
            })
    return templates


def nms(points, w, h):
    out = []
    for x, y, s in sorted(points, key=lambda p: -p[2]):
        if all(abs(x - ox) > w * 0.6 or abs(y - oy) > h * 0.6 for ox, oy, _ in out):
            out.append((x, y, s))
        if len(out) >= MAX_INSTANCES:
            break
    return out


def full_search(frame_half, frame, tpl):
    """Full-frame sweep per SCALE VARIANT. Returns [(x, y, w, h)] -- the size
    comes back too, because a match at 0.75x is a smaller region than the
    template it came from.

    Two routes, chosen by template height, and the split is the single most
    important number in this file. The --recall harness measured 26.9% on a
    source whose own OCR hits were the templates -- the tracker could not
    find pixels cut from the very frame it was searching. Cause: the
    half-scale prefilter. A 13-19 px line of text is 6-9 px at half scale,
    and the phase difference between resizing a crop and resizing the frame
    it came from drops NCC below any usable gate. So small templates are
    searched at FULL resolution directly (a 100x15 template over 1818x1080 is
    ~30 ms), and only tall ones take the half-scale shortcut.
    """
    hits = []
    for v in tpl["variants"]:
        H, W = v["img"].shape
        if H < SMALL_TPL_H:
            if frame.shape[0] <= H or frame.shape[1] <= W:
                continue
            thr = THR_SMALL if W * H < SMALL_TPL_AREA else THR
            r = cv2.matchTemplate(frame, v["img"], cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(r >= thr)
            for x, y, _ in nms([(x, y, r[y, x]) for x, y in zip(xs, ys)], W, H):
                hits.append((int(x), int(y), W, H))
            continue
        th, tw = v["half"].shape
        if frame_half.shape[0] <= th or frame_half.shape[1] <= tw:
            continue
        r = cv2.matchTemplate(frame_half, v["half"], cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(r >= THR_HALF)
        cand = nms([(x, y, r[y, x]) for x, y in zip(xs, ys)], tw, th)
        for cx, cy, _ in cand:
            x0, y0 = cx * 2, cy * 2
            win = frame[max(0, y0 - 8):y0 + H + 8, max(0, x0 - 8):x0 + W + 8]
            if win.shape[0] < H or win.shape[1] < W:
                continue
            rr = cv2.matchTemplate(win, v["img"], cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(rr)
            if score >= THR:
                hits.append((max(0, x0 - 8) + loc[0],
                             max(0, y0 - 8) + loc[1], W, H))
    # de-duplicate across scales: two variants can claim the same spot
    return nms4(hits)


def nms4(hits):
    out = []
    for x, y, w, h in hits:
        if all(abs(x - ox) > ow * 0.5 or abs(y - oy) > oh * 0.5
               for ox, oy, ow, oh in out):
            out.append((x, y, w, h))
        if len(out) >= MAX_INSTANCES:
            break
    return out


def local_search(frame, tpl, inst, pad=70):
    """Re-find one sized instance near where it last was."""
    x, y, W, H = inst
    v = next((v for v in tpl["variants"] if v["img"].shape == (H, W)), None)
    if v is None:
        return None
    win = frame[max(0, y - pad):y + H + pad, max(0, x - pad):x + W + pad]
    if win.shape[0] < H or win.shape[1] < W:
        return None
    r = cv2.matchTemplate(win, v["img"], cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(r)
    if score < (THR_SMALL if W * H < SMALL_TPL_AREA else THR):
        return None
    return (max(0, x - pad) + loc[0], max(0, y - pad) + loc[1], W, H)


def track(src, templates, info, verbose=True):
    """Per-frame box lists. The heart of it; see the cost model up top."""
    boxes_per_frame = []
    instances = {id(t): [] for t in templates}   # template -> [(x, y)]
    last_seen = {id(t): -10**9 for t in templates}
    prev = None
    stats = {"frames": 0, "skipped": 0, "local": 0, "full": 0}
    for i, fr in enumerate(gray_stream(src, info["w"], info["h"], info["fps"])):
        stats["frames"] += 1
        if prev is not None:
            moved = float((np.abs(fr.astype(np.int16) - prev) > 12).mean())
            if moved < CHANGE_SKIP:
                stats["skipped"] += 1
                boxes_per_frame.append(boxes_per_frame[-1])
                continue
        else:
            moved = 1.0
        prev = fr.astype(np.int16)
        fr_half = cv2.resize(fr, (info["w"] // 2, info["h"] // 2))

        frame_boxes = []
        for t in templates:
            tid = id(t)
            kept = []
            for inst in instances[tid]:
                found = local_search(fr, t, inst)
                if found is not None:
                    kept.append(found)
                    stats["local"] += 1
            # a lost or never-seen template gets a full sweep -- every frame
            # while warm, every COLD_EVERY frames once it has gone quiet
            warm = (i - last_seen[tid]) < info["fps"] * 3
            if not kept and (warm or i % COLD_EVERY == 0 or moved > 0.10):
                kept = full_search(fr_half, fr, t)
                stats["full"] += 1
            if kept:
                last_seen[tid] = i
            instances[tid] = kept
            for x, y, W, H in kept:
                # plain ints: matchTemplate hands back numpy int64, which the
                # json module refuses to serialize when the timeline is saved
                frame_boxes.append((int(max(0, x - DILATE)), int(max(0, y - DILATE)),
                                    int(min(info["w"], x + W + DILATE)),
                                    int(min(info["h"], y + H + DILATE)), t["key"]))
        boxes_per_frame.append(frame_boxes)
        if verbose and i % int(info["fps"] * 30) == 0:
            print(f"    ...frame {i} ({i / info['fps']:.0f}s) "
                  f"{len(frame_boxes)} box(es)", file=sys.stderr)
    return boxes_per_frame, stats


def write_masks(boxes_per_frame, info, outdir):
    """One PNG per stretch of stable boxes, plus the concat listing.

    A still page costs one PNG no matter how long it holds; a scroll costs one
    per frame while it moves. The listing is written LONGER than the source --
    see the module docstring for why a short mask is fatal, not cosmetic.
    """
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.startswith("mask_") and f.endswith(".png"):
            os.remove(os.path.join(outdir, f))
    runs = []
    for i, boxes in enumerate(boxes_per_frame):
        if runs and runs[-1][2] == boxes:
            runs[-1][1] = i
        else:
            runs.append([i, i, boxes])
    lines = []
    for n, (f0, f1, boxes) in enumerate(runs):
        m = np.zeros((info["h"], info["w"]), np.uint8)
        for x0, y0, x1, y1, _key in boxes:
            m[y0:y1, x0:x1] = 255
        if boxes:
            m = cv2.GaussianBlur(m, (9, 9), 0)   # feathered edge reads as blur
        name = f"mask_{n:06d}.png"
        cv2.imwrite(os.path.join(outdir, name), m)
        dur = (f1 - f0 + 1) / info["fps"]
        lines.append(f"file '{name}'\nduration {dur:.4f}")
    # tail: hold the last mask well past the end of the source
    lines.append(f"file 'mask_{len(runs) - 1:06d}.png'\nduration 5")
    lines.append(f"file 'mask_{len(runs) - 1:06d}.png'")
    listing = os.path.join(outdir, "masks.txt")
    with open(listing, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return runs, listing


def load_runs(outdir):
    """The box timeline a previous run persisted, or None."""
    p = os.path.join(outdir, "track.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    return d.get("runs"), d


def boxes_at(runs, frame):
    """Boxes on one frame, by binary search over the run list."""
    lo, hi = 0, len(runs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        f0, f1, boxes = runs[mid]
        if frame < f0:
            hi = mid - 1
        elif frame > f1:
            lo = mid + 1
        else:
            return boxes
    return []


def hand_boxes_at(hand_rects, t, info):
    """Manifest hand rects active at time t, as pixel boxes -- the render
    applies them alongside the tracked mask, so recall must count them."""
    out = []
    for b in hand_rects or []:
        w = b.get("when")
        if w and not (w[0] <= t <= w[1]):
            continue
        x, y, bw, bh = b["rect"]
        out.append((int(x * info["w"]), int(y * info["h"]),
                    int((x + bw) * info["w"]), int((y + bh) * info["h"]), "hand"))
    return out


def recall(runs, pii_paths, src, info, benign, kinds, min_cover=0.8, hand_rects=None):
    """How much of what OCR found in THIS source do the boxes actually cover?

    This is the measurement that was skipped before the first three renders
    with this tool, and the gate found 183 leaks. The OCR hits are a free
    ground truth: for every hit found in this recording, look at the frame it
    was read on and ask whether the tracked boxes cover at least `min_cover`
    of its rectangle. Per secret, so a template that never matches is named,
    not averaged away. Costs seconds; blocks the render below --recall-min.
    """
    flat_benign = [b.replace(" ", "") for b in benign]
    own = os.path.basename(src)
    per = {}
    misses = []
    for pp in pii_paths:
        d = json.load(open(_env.resolve(pp), encoding="utf-8"))
        if os.path.basename(d.get("src", "")) != own:
            continue
        period = 1.0 / float(d.get("sample_fps") or 0.25)
        for h in d["hits"]:
            if h["kind"] not in kinds:
                continue
            if any(b in h["text"].replace(" ", "") for b in flat_benign):
                continue
            key = norm_key(h["kind"], h["text"])
            x, y, w, hh = h["rect"]
            hx0, hy0 = x * info["w"], y * info["h"]
            hx1, hy1 = hx0 + w * info["w"], hy0 + hh * info["h"]
            area = max(1.0, (hx1 - hx0) * (hy1 - hy0))
            # the hit's time may label the slot rather than the frame (see
            # collect_templates); score the best frame within the slot
            covered = 0.0
            for dt_ in (0.0, period * 0.25, period * 0.5, period * 0.75, period, -period * 0.5):
                frame = int(round((h["t"] + dt_) * info["fps"]))
                cov = 0.0
                for bx0, by0, bx1, by1, _k in (boxes_at(runs, frame)
                                               + hand_boxes_at(hand_rects, h["t"] + dt_, info)):
                    ix = max(0.0, min(hx1, bx1) - max(hx0, bx0))
                    iy = max(0.0, min(hy1, by1) - max(hy0, by0))
                    cov += ix * iy
                covered = max(covered, cov)
            # An OCR line often carries its label -- "Телефон: 0935630503" --
            # and the tracked box rightly covers only the number, a third of
            # that line. Judge such lines by the digits' share of the box.
            digits = len(re.sub(r"\D", "", h["text"]))
            need = min_cover if digits >= 0.7 * max(1, len(h["text"].replace(" ", ""))) \
                else min_cover * digits / max(1, len(h["text"].replace(" ", "")))
            ok = covered / area >= need
            tot, good = per.get(key, (0, 0))
            per[key] = (tot + 1, good + (1 if ok else 0))
            if not ok:
                misses.append((h["t"], key, h["text"][:40],
                               round(covered / area, 2)))
    return per, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="the video the render will read (the proxy)")
    ap.add_argument("--pii", default="",
                    help="scan-pii hits: comma-separated, and POOL THEM. One "
                         "session's secrets cross its recordings -- the card "
                         "number typed into the Claude panel in one recording "
                         "was OCR-read only in another, so a per-source pool "
                         "left it sharp exactly where it mattered. Every "
                         "same-geometry source should hand its hits to every "
                         "other.")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--manifest", help="read benign_text from here; with no "
                    "--pii, also pool every same-geometry source's scan")
    ap.add_argument("--kinds", default=",".join(sorted(KINDS)))
    ap.add_argument("--list", action="store_true",
                    help="show the templates and price the tracking; touches nothing")
    ap.add_argument("--recall", action="store_true",
                    help="score the existing track against this source's OCR "
                         "hits and print the misses; no tracking, seconds")
    ap.add_argument("--recall-min", type=float, default=0.98,
                    help="exit non-zero when overall recall is below this")
    args = ap.parse_args()

    src = _env.resolve(args.src)
    info = probe(src)
    benign, man = [], {}
    if args.manifest:
        man = json.load(open(_env.resolve(args.manifest), encoding="utf-8"))
        benign = man.get("benign_text") or []
    kinds = set(args.kinds.split(","))
    pii_paths = args.pii.split(",") if args.pii else pool_from_manifest(man, args.manifest, info)
    if not pii_paths:
        raise SystemExit("no scans to pool: give --pii or a --manifest whose "
                         "sources have temp/pii/<base>.pii.json")

    # this source's hand rects count as coverage: the render applies them
    hand = []
    for s in (man.get("sources") or []):
        names = {os.path.basename(s.get("path", "")), os.path.basename(s.get("proxy") or "")}
        if os.path.basename(src) in names:
            hand = s.get("blur") or []

    if args.recall:
        loaded = load_runs(_env.resolve(args.outdir))
        if loaded is None or loaded[0] is None:
            raise SystemExit(f"no track.json under {args.outdir}; run the tracker first")
        runs, _ = loaded
        per, misses = recall(runs, pii_paths, src, info, benign, kinds, hand_rects=hand)
        tot = sum(t for t, _ in per.values())
        good = sum(g for _, g in per.values())
        print(f"{os.path.basename(src)}  recall {good}/{tot} = "
              f"{(good / tot * 100) if tot else 100:.1f}%  "
              f"({len(per)} secret(s), min {args.recall_min * 100:.0f}%)")
        for key, (t, g) in sorted(per.items(), key=lambda kv: kv[1][1] / kv[1][0]):
            flag = "" if g == t else "   <- MISSES"
            print(f"    {key:<28} {g:>3}/{t:<3}{flag}")
        for t, key, text, cov in misses[:25]:
            print(f"      miss {t:7.1f}s  {key:<24} cover {cov:.2f}  {text}")
        # which renderings the pool actually holds for the missed secrets --
        # a miss with no template of its own text form is a pooling gap, a
        # miss WITH one is a matching bug; the two are fixed in different places
        missed_keys = {m[1] for m in misses}
        if missed_keys:
            tpls = collect_templates(src, pii_paths, benign, kinds, info)
            print("    templates held for the missed secrets:")
            for key in sorted(missed_keys):
                forms = [f"{t['img'].shape[1]}x{t['img'].shape[0]} '{t['text'][:28]}'"
                         for t in tpls if t["key"] == key]
                print(f"      {key:<26} {len(forms)}: " + "; ".join(forms[:4]))
        if tot and good / tot < args.recall_min:
            raise SystemExit(1)
        return

    templates = collect_templates(src, pii_paths, benign, kinds, info)
    n_secrets = len({t["key"] for t in templates})
    print(f"{os.path.basename(src)}  {info['w']}x{info['h']} @ {info['fps']:.0f}fps "
          f"{info['dur']:.0f}s   {n_secrets} secret(s), {len(templates)} template(s)")
    for t in templates:
        H, W = t["img"].shape
        print(f"    {t['kind']:<8} {W:>4}x{H:<3} {t['text']}")
    if args.list:
        print(f"\n  would track {int(info['dur'] * info['fps'])} frames")
        return
    if not templates:
        print("  nothing to track")
        return

    boxes, stats = track(src, templates, info)
    runs, listing = write_masks(boxes, info, _env.resolve(args.outdir))
    covered = sum(1 for b in boxes if b)
    print(f"  {stats['frames']} frames: {stats['skipped']} unchanged, "
          f"{stats['local']} local match(es), {stats['full']} full sweep(s)")
    print(f"  boxes on {covered} frame(s) ({covered / max(1, len(boxes)) * 100:.0f}%), "
          f"{len(runs)} mask PNG(s) -> {args.outdir}")

    # The box timeline is persisted with the template key on every box, so
    # --recall and the review sheet can read it back without re-tracking.
    with open(os.path.join(_env.resolve(args.outdir), "track.json"), "w",
              encoding="utf-8") as f:
        json.dump({"src": src, "fps": info["fps"], "size": [info["w"], info["h"]],
                   "secrets": n_secrets, "templates": len(templates),
                   "frames_with_boxes": covered, "masks": len(runs),
                   "keys": {t["key"]: {"kind": t["kind"], "text": t["text"]}
                            for t in templates},
                   "runs": [[f0, f1, [list(b) for b in bx]] for f0, f1, bx in runs]},
                  f)

    per, misses = recall(runs, pii_paths, src, info, benign, kinds, hand_rects=hand)
    tot = sum(t for t, _ in per.values())
    good = sum(g for _, g in per.values())
    print(f"  recall against this source's OCR hits: {good}/{tot} = "
          f"{(good / tot * 100) if tot else 100:.1f}%"
          f"{'' if not tot or good / tot >= args.recall_min else '   <- BELOW ' + str(args.recall_min)}")
    for key, (t, g) in sorted(per.items(), key=lambda kv: kv[1][1] / kv[1][0])[:8]:
        if g < t:
            print(f"    {key:<28} {g:>3}/{t:<3}")


def pool_from_manifest(man, manifest_path, info):
    """Every same-geometry source's scan, by the temp/pii/<base> convention."""
    if not man or not manifest_path:
        return []
    pdir = os.path.dirname(_env.resolve(manifest_path))
    out = []
    for s in man.get("sources", []):
        base = os.path.splitext(os.path.basename(s["path"]))[0]
        proxy = _env.resolve(s.get("proxy") or s["path"])
        try:
            geo = probe(proxy)
        except Exception:
            continue
        if (geo["w"], geo["h"]) != (info["w"], info["h"]):
            continue
        p = os.path.join(pdir, "temp", "pii", base + ".pii.json")
        if os.path.exists(p):
            out.append(p)
    return out


if __name__ == "__main__":
    main()
