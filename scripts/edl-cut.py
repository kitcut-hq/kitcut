#!/usr/bin/env python
"""Assemble a film from hand-chosen ranges of several silent recordings.

`screen-cut.py` decides what to keep from screen motion, which is right for an
hour of desktop capture nobody wants to watch twice. It is wrong for a handful
of takes that a person has already watched: there the decisions are editorial
("the second download is the better one", "keep two seconds of that hover,
not fifteen") and a motion metric cannot make them -- on bpo-realtor it
labelled the whole two-minute fill "still", because a progress bar moves below
any sensible threshold. So this script takes the decisions as data: an edit
decision list of (source, from, to, speed), in film order, with a `_why` on
every line.

THE ELAPSED COUNTER is the reason it exists. A sped-up wait needs a clock, and
a clock over sped-up footage lies unless it is driven by SOURCE time. Every
film frame is mapped back through the EDL to the source instant it shows, and
the card drawn on that frame reads (source instant - counter start). So the
digits race while the footage runs 10x, crawl at 1x, jump honestly across a
cut inside the counted span, and land on the true total the moment the
footage reaches the end event -- whatever speeds the EDL uses. The card is
drawn by Pillow, one PNG per distinct state, and piped into a short alpha
video that is overlaid in the film's one encode. Each digit sits in a fixed
cell, because Montserrat's figures are proportional and a clock whose digits
shuffle sideways every second reads as broken.

PAINT AND BLUR run in SOURCE time, before the speed change, so a window you
measured on a source frame stays true. `paint` fills a rect with a flat
colour (browser chrome: tab titles and a local file path, erased to the
chrome's own colour); `blur` defocuses one (an on-screen number that
contradicts the counter). A fixed rect is only right while the picture holds
still, and a screen recorder that zooms toward the cursor moves the chrome
out from under it -- so every frame the EDL uses is tested, and where the
chrome has moved the rects are carried by a tracked transform instead.

ZOOMS are accents authored in source time on a canvas rect, rendered by
zoompan on a 2x upscale inside the same pass. `rotate: 180` turns a phone
take whose rotation tag is missing or wrong.

  --list      the EDL with film in/out, the runtime, the counter's film span
              and final value, the zooms and where chrome is followed;
              encodes nothing
  --frame T   the finished frame at film time T as a PNG, card included --
              the placement check that costs one frame, not one encode
  (none)      render

Invoke as:  python scripts/edl-cut.py --manifest projects/<id>/edit.json --list
"""
import sys
import os
import json
import math
import argparse
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import _encode  # noqa: E402 -- the one place encoder keys are chosen
import _overlay  # noqa: E402
import _progress  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_RENDER = {"speed": 5, "cq": 20, "maxrate": "12M", "bufsize": "24M"}
DEFAULT_STYLE = "config/overlays/elapsed-counter.json"


def parse_t(v):
    """Seconds, or 'M:SS.s' / 'H:MM:SS.s' as a human reads a timecode."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def fmt(t):
    t = max(0.0, t)
    return "%d:%04.1f" % (int(t // 60), t % 60)


def clock(t):
    t = int(math.floor(max(0.0, t) + 1e-6))
    return "%d:%02d" % (t // 60, t % 60)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- the plan

def load(mpath):
    m = json.load(open(mpath, encoding="utf-8"))
    cw, ch = m.get("canvas", [1920, 1080])
    fps = float(m.get("fps", 30))
    srcs = {}
    for key, s in (m.get("sources") or {}).items():
        path = _env.resolve(s["path"], base=_env.workspace())
        if not os.path.exists(path):
            sys.exit("source %s: %s does not exist" % (key, s["path"]))
        w, h, sfps, dur = _overlay.probe(path)
        if int(s.get("rotate", 0)) not in (0, 180):
            sys.exit("source %s: rotate %s -- only 0 and 180 are supported (a "
                     "90-degree turn changes the frame's shape)" % (key, s["rotate"]))
        srcs[key] = dict(s, key=key, abspath=path, w=w, h=h, fps=sfps, dur=dur)
    segs = []
    frame = 0
    for i, e in enumerate(m.get("edl") or []):
        if e.get("card"):
            # A generated full-frame card (checklist-card.py). It is rendered
            # to a clip, cached on its spec + style + canvas, and from here on
            # it is just another source played 0 -> its own length.
            e = dict(e, src=card_source(e, srcs, (cw, ch), fps, m, mpath), **{"from": 0})
            e["to"] = srcs[e["src"]]["dur"]
        if e["src"] not in srcs:
            sys.exit("edl[%d]: unknown source %r" % (i, e["src"]))
        s = srcs[e["src"]]
        a, b = parse_t(e["from"]), parse_t(e["to"])
        sp = float(e.get("speed", 1.0))
        if not (0 <= a < b <= s["dur"] + 1e-3) or sp <= 0:
            sys.exit("edl[%d] %s %s->%s x%s is outside the source (0-%s) or "
                     "has no speed" % (i, e["src"], fmt(a), fmt(b), sp, fmt(s["dur"])))
        # Frame-exact film length: every film offset below is a sum of these,
        # so the counter and the picture cannot drift apart across segments.
        n = int(math.floor((b - a) / sp * fps + 1e-6))
        if n < 1:
            sys.exit("edl[%d] is shorter than one frame at x%s" % (i, sp))
        crop = e.get("crop")
        if crop:
            cx_, cy_, cw_, ch_ = [int(v) for v in crop]
            if cx_ < 0 or cy_ < 0 or cx_ + cw_ > s["w"] or cy_ + ch_ > s["h"]:
                sys.exit("edl[%d] crop %s leaves the %dx%d source" % (i, crop, s["w"], s["h"]))
        segs.append({"i": i, "src": s, "from": a, "to": b, "speed": sp,
                     "f0": frame, "n": n, "why": e.get("_why", ""), "crop": crop})
        frame += n
    if not segs:
        sys.exit("the manifest has no edl entries")
    return m, srcs, segs, (cw, ch), fps, frame


def card_source(e, srcs, canvas, fps, m, mpath):
    """Render (or reuse) a checklist card clip and register it as a source."""
    import hashlib
    from importlib import import_module
    ck = import_module("checklist-card")
    spec, style = ck.load(e["card"], e["style"])
    key = "card-" + hashlib.sha1(json.dumps([spec, style, canvas, fps], sort_keys=True)
                                 .encode()).hexdigest()[:10]
    if key not in srcs:
        mid = m.get("id") or os.path.basename(os.path.dirname(os.path.abspath(mpath)))
        d = os.path.join(_project.projects_dir(), mid, "temp", "edl")
        os.makedirs(d, exist_ok=True)
        clip = os.path.join(d, key + ".mp4")
        if not os.path.exists(clip):
            print("  drawing card %s (%s) ..." % (e["card"], os.path.basename(e["style"])))
            ck.render_clip(spec, style, tuple(canvas), fps, clip)
        w, h, sfps, dur = _overlay.probe(clip)
        srcs[key] = {"key": key, "path": rel(clip), "abspath": clip, "w": w, "h": h,
                     "fps": sfps, "dur": dur, "bg": "#000000"}
    return key


def seg_at(segs, g):
    for s in segs:
        if s["f0"] <= g < s["f0"] + s["n"]:
            return s
    return None


def src_time(seg, g, fps):
    """The source instant film frame g shows."""
    return seg["from"] + (g - seg["f0"]) / fps * seg["speed"]


# ---------------------------------------------------------------- counter

def counter_plan(spec, segs, fps, total):
    """Per-frame states for one counter: (g, value_s, done, speed) and the span.

    Refuses a counter whose start or end event is not in the film. A card that
    starts but never finishes would freeze mid-count, and one that never
    starts would be a silent no-op -- the same failure a name label past the
    end of a film has.
    """
    key = spec["src"]
    c0, c1 = parse_t(spec["start"]), parse_t(spec["end"])
    g0 = gend = None
    for g in range(total):
        s = seg_at(segs, g)
        if s["src"]["key"] != key:
            continue
        t = src_time(s, g, fps)
        if g0 is None and t >= c0:
            g0 = g
        if g0 is not None and t >= c1:
            gend = g
            break
    if g0 is None:
        sys.exit("counter start %s (%s) is not in the film" % (fmt(c0), key))
    if gend is None:
        sys.exit("counter end %s (%s) is not in the film -- the clock would "
                 "freeze mid-count" % (fmt(c1), key))
    hold = float(spec.get("hold_after", 3.0))
    fade = float(spec.get("fade", 0.3))
    g1 = min(total, gend + int(round((hold + fade) * fps)))
    frames = []
    v = 0.0
    for g in range(g0, g1):
        s = seg_at(segs, g)
        if g < gend:
            # A cutaway to another source inside the span shows no source
            # time of ours, so the clock holds rather than inventing seconds.
            if s["src"]["key"] == key:
                v = max(0.0, src_time(s, g, fps) - c0)
            frames.append((g, v, False, s["speed"] if s["src"]["key"] == key else 1.0))
        else:
            frames.append((g, c1 - c0, True, 1.0))
    # Source seconds of the counted span that the EDL does not show: the
    # clock jumps across them. Honest, but worth saying before an encode.
    shown = 0.0
    for s in segs:
        if s["src"]["key"] == key:
            shown += max(0.0, min(s["to"], c1) - max(s["from"], c0))
    return {"g0": g0, "gend": gend, "g1": g1, "frames": frames,
            "total_s": c1 - c0, "cut_s": max(0.0, (c1 - c0) - shown),
            "fade": fade}


class Card:
    """Draws the elapsed-time card. One instance per render; caches states."""

    def __init__(self, style, spec, canvas_h):
        self.st = style
        self.spec = spec
        # sizes are authored for a 1080-line landscape frame; `scale` lets a
        # vertical style pick its own size instead of inheriting 1920/1080
        k = float(style.get("scale", canvas_h / 1080.0))
        self.k = k
        c = style["card"]
        self.w, self.h = int(round(c["w"] * k)), int(round(c["h"] * k))
        f = lambda d: ImageFont.truetype(_overlay.repo_path(d["font"]),  # noqa: E731
                                         max(6, int(round(d["size"] * k))))
        self.f_label = f(style["label"])
        self.f_dig = f(style["digits"])
        self.f_chip = f(style["chip"])
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        # the widest figure sets every digit cell, so nothing moves sideways
        self.cell = max(probe.textlength(d, font=self.f_dig) for d in "0123456789")
        self.colon = probe.textlength(":", font=self.f_dig)
        self.cache = {}

    def draw(self, value, done, speed, alpha, pulse):
        key = (clock(value), done, round(speed, 2), round(alpha, 2), round(pulse, 1))
        if key in self.cache:
            return self.cache[key]
        st, k = self.st, self.k
        c = st["card"]
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.w - 1, self.h - 1], radius=int(c["radius"] * k),
                            fill=_overlay.hex_rgba(c["fill"], int(255 * c["alpha"])),
                            outline=_overlay.hex_rgba(c["border"]), width=max(1, int(k)))
        pad = st["pad"] * k
        # label row: a live dot while counting, a check once done
        ly = pad * 0.78
        lab_h = self.f_label.getbbox("H")[3]
        cy = ly + lab_h / 2.0 + 1
        r = 5.5 * k
        if done:
            col = _overlay.hex_rgba(st["done"])
            d.ellipse([pad, cy - r * 1.35, pad + r * 2.7, cy + r * 1.35], fill=col)
            x0, y0 = pad + r * 1.35, cy
            d.line([(x0 - r * 0.7, y0), (x0 - r * 0.15, y0 + r * 0.55),
                    (x0 + r * 0.75, y0 - r * 0.55)], fill=(255, 255, 255, 255),
                   width=max(2, int(2 * k)))
            text = self.spec.get("done_label", "DONE")
            tcol = _overlay.hex_rgba(st["done"])
        else:
            a = int(255 * (0.45 + 0.55 * pulse))
            d.ellipse([pad + r * 0.35, cy - r, pad + r * 2.35, cy + r],
                      fill=_overlay.hex_rgba(st["accent"], a))
            text = self.spec.get("label", "ELAPSED")
            tcol = _overlay.hex_rgba(st["label"]["color"])
        _overlay.draw_text_tracked(d, (pad + r * 2.7 + 9 * k, ly), text.upper(),
                                   self.f_label, tcol, st["label"]["tracking"] * k)
        # the clock, one fixed cell per figure
        txt = clock(value)
        dig_top = self.f_dig.getbbox("0")[1]
        dig_h = self.f_dig.getbbox("0")[3] - dig_top
        base_y = self.h - pad * 0.72 - dig_h - dig_top
        x = pad
        dcol = _overlay.hex_rgba(st["digits"]["color"])
        for chx in txt:
            if chx == ":":
                d.text((x, base_y - 3 * k), ":", font=self.f_dig, fill=dcol)
                x += self.colon + 2 * k
            else:
                wch = d.textlength(chx, font=self.f_dig)
                d.text((x + (self.cell - wch) / 2.0, base_y), chx,
                       font=self.f_dig, fill=dcol)
                x += self.cell
        # the speed chip: why the digits are racing
        if not done and speed > 1.01 and st.get("speed_chip", True):
            label = "%g×" % round(speed, 1)
            tw = d.textlength(label, font=self.f_chip)
            th = self.f_chip.getbbox("0")[3] - self.f_chip.getbbox("0")[1]
            tri = th * 0.9
            cw_ = tri * 2 + 6 * k + tw + 22 * k
            chh = th + 16 * k
            cx1 = self.w - pad
            cx0 = cx1 - cw_
            cy1 = base_y + dig_top + dig_h
            cy0 = cy1 - chh
            d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(chh / 2),
                                fill=_overlay.hex_rgba(st["chip"]["fill"]))
            tx = cx0 + 11 * k
            my = (cy0 + cy1) / 2.0
            white = _overlay.hex_rgba(st["chip"]["color"])
            for j in range(2):
                ox = tx + j * tri * 0.85
                d.polygon([(ox, my - tri / 2), (ox + tri * 0.8, my), (ox, my + tri / 2)],
                          fill=white)
            d.text((tx + tri * 1.9 + 6 * k, my - th / 2 - self.f_chip.getbbox("0")[1]),
                   label, font=self.f_chip, fill=white)
        if alpha < 0.999:
            a = img.getchannel("A").point(lambda p: int(p * alpha))
            img.putalpha(a)
        self.cache[key] = img
        return img

    def xy(self, cw, ch):
        mx, my = [v * self.k for v in self.st.get("margin", [40, 20])]
        corner = self.st.get("corner", "bottom-right")
        x = (cw - self.w - mx if "right" in corner else
             mx if "left" in corner else (cw - self.w) // 2)
        y = ch - self.h - my if "bottom" in corner else my
        return int(round(x)), int(round(y))


def card_frames(cp, card, fps):
    """(g, PIL image) for every film frame the card is on."""
    fade_n = max(1, int(round(cp["fade"] * fps)))
    hz = float(card.st.get("pulse_hz", 1.0))
    out = []
    for idx, (g, v, done, sp) in enumerate(cp["frames"]):
        a = min(1.0, (idx + 1) / fade_n, (len(cp["frames"]) - idx) / fade_n)
        pulse = 0.5 + 0.5 * math.cos(2 * math.pi * hz * (g / fps))
        out.append((g, card.draw(v, done, sp, a, round(pulse * 4) / 4)))
    return out


def write_card_video(frames, card, fps, path):
    """Pipe the card frames into a short PNG-in-MOV clip that keeps alpha."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (card.w, card.h),
           "-r", str(fps), "-i", "-", "-c:v", "png", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=ENV)
    for _, im in frames:
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait():
        sys.exit("could not write the counter clip %s" % path)


# ---------------------------------------------------------------- follow

REST_TOL = 20        # colour distance that still counts as the painted colour
REST_MIN = 0.45      # fraction of a paint rect that must be its colour at rest
FOLLOW_PAD = 0.3     # seconds of rest kept either side of a moved run


def _decode(src, a, b, fps=None, scale=1.0, fmt_="rgb24"):
    """Frames of a source stretch as a numpy array, rotation applied."""
    import numpy as np
    w, h = int(src["w"] * scale) // 2 * 2, int(src["h"] * scale) // 2 * 2
    vf = ["hflip,vflip"] if int(src.get("rotate", 0)) == 180 else []
    if fps:
        vf.append("fps=%g" % fps)
    vf.append("scale=%d:%d" % (w, h))
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a),
                        "-i", src["abspath"], "-vf", ",".join(vf),
                        "-f", "rawvideo", "-pix_fmt", fmt_, "-"],
                       env=ENV, capture_output=True)
    if fmt_ == "rgb24":
        return np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w, 3)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w)


def moved_runs(src, segs):
    """Source windows where a painted source's chrome is NOT where it was
    measured -- a recorder's zoom, a scroll of the whole window.

    A fixed rect is only right while the thing under it holds still. Cursorful
    zooms toward the cursor, and a drawbox that stays put then lands on the
    page while the real address bar, file path and all, slides into view
    beside it (bpo-realtor review 1). So every frame the EDL uses is tested:
    at rest, each paint rect is mostly its own colour; when it is not, the
    frame has moved and needs following.
    """
    import numpy as np
    paint = src.get("paint") or []
    if not paint:
        return []
    k = 0.25
    runs = []
    for s in segs:
        if s["src"]["key"] != src["key"]:
            continue
        fr = _decode(src, s["from"], s["to"], fps=10, scale=k).astype(int)
        H, W = fr.shape[1:3]
        moved = []
        for i, f in enumerate(fr):
            worst = 1.0
            for p in paint:
                x, y, rw, rh = rect_px(p["rect"], W, H)
                c = np.array(_overlay.hex_rgba(p["color"])[:3])
                reg = f[y:y + rh, x:x + rw]
                if reg.size:
                    worst = min(worst, (np.abs(reg - c).sum(-1) < REST_TOL).mean())
            if worst < REST_MIN:
                moved.append(s["from"] + i / 10.0)
        for t in moved:
            if runs and t - runs[-1][1] <= 0.25:
                runs[-1][1] = t
            else:
                runs.append([t, t])
    out = []
    for a, b in runs:
        a, b = max(0.0, a - FOLLOW_PAD), min(src["dur"], b + 0.1 + FOLLOW_PAD)
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def track(src, a, b, cache_dir):
    """Per-frame similarity transforms (2x3) from the frame at `a` to each
    frame of [a, b], at the source's own frame rate.

    Tracked, not matched: the reference is warped by the previous frame's
    transform and only the residual is fitted, because at a 1.5x zoom a
    single-scale ORB match against the unzoomed frame finds nothing (measured:
    3 inliers of 400). The mask is the band around the paint rects -- browser
    chrome moves rigidly with the zoom and does not change with the page. A
    frame whose fit fails, or whose warped reference no longer matches it,
    stops the render with its time: a guessed rect over a file path is a leak.
    """
    import numpy as np
    import cv2
    import hashlib
    key = hashlib.sha1(json.dumps([src["abspath"], os.path.getsize(src["abspath"]),
                                   round(a, 3), round(b, 3), src.get("paint"),
                                   src.get("rotate", 0)]).encode()).hexdigest()[:12]
    cache = os.path.join(cache_dir, "follow-%s-%s.npy" % (src["key"], key))
    if os.path.exists(cache):
        return np.load(cache)
    fr = _decode(src, a, b, fmt_="gray")
    H, W = fr.shape[1:3]
    xs, ys = [], []
    for p in src["paint"]:
        x, y, rw, rh = rect_px(p["rect"], W, H)
        xs += [x, x + rw]
        ys += [y, y + rh]
    pad = int(0.06 * H)
    mask = np.zeros((H, W), np.uint8)
    mask[max(0, min(ys) - pad):min(H, max(ys) + pad),
         max(0, min(xs) - pad):min(W, max(xs) + pad)] = 255
    orb = cv2.ORB_create(3000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ref = fr[0]
    M = np.array([[1, 0, 0], [0, 1, 0]], np.float32)

    def h3(A):
        return np.vstack([A, [0, 0, 1]])

    out = []
    print("  following %s %s-%s (%d frames) ..." % (src["key"], fmt(a), fmt(b), len(fr)))
    for i, f in enumerate(fr):
        wr = cv2.warpAffine(ref, M, (W, H))
        wm = cv2.warpAffine(mask, M, (W, H), flags=cv2.INTER_NEAREST)
        kr, dr = orb.detectAndCompute(wr, wm)
        kf, df = orb.detectAndCompute(f, wm)
        ok = False
        if dr is not None and df is not None:
            m = bf.match(dr, df)
            if len(m) >= 8:
                pa = np.float32([kr[x.queryIdx].pt for x in m])
                pb = np.float32([kf[x.trainIdx].pt for x in m])
                R, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC,
                                                     ransacReprojThreshold=2.0)
                if R is not None and inl is not None and int(inl.sum()) >= 12:
                    M = (h3(R) @ h3(M))[:2].astype(np.float32)
                    ok = True
        vis = cv2.warpAffine(mask, M, (W, H), flags=cv2.INTER_NEAREST) > 0
        err = (np.abs(cv2.warpAffine(ref, M, (W, H)).astype(int) - f.astype(int))[vis].mean()
               if vis.any() else 0.0)
        if not ok and vis.any():
            sys.exit("follow: lost the chrome of %s at %s -- refusing to guess where "
                     "a painted rect goes" % (src["key"], fmt(a + i / src["fps"])))
        if err > 8.0:
            sys.exit("follow: %s at %s matches its reference badly (mean error %.1f) "
                     "-- refusing" % (src["key"], fmt(a + i / src["fps"]), err))
        out.append(M.copy())
    out = np.array(out)
    np.save(cache, out)
    return out


def follow_clip(src, mats, path):
    """The paint rects, carried by each frame's transform, as an alpha clip."""
    k = 0.5
    W, H = int(src["w"] * k) // 2 * 2, int(src["h"] * k) // 2 * 2
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (W, H),
           "-r", "%.6f" % src["fps"], "-i", "-", "-c:v", "png", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=ENV)
    for M in mats:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for pt in src["paint"]:
            x, y, rw, rh = rect_px(pt["rect"], src["w"], src["h"])
            x0 = M[0][0] * x + M[0][1] * y + M[0][2]
            y0 = M[1][0] * x + M[1][1] * y + M[1][2]
            x1 = M[0][0] * (x + rw) + M[0][1] * (y + rh) + M[0][2]
            y1 = M[1][0] * (x + rw) + M[1][1] * (y + rh) + M[1][2]
            d.rectangle([x0 * k, y0 * k, x1 * k, y1 * k],
                        fill=_overlay.hex_rgba(pt["color"]))
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait():
        sys.exit("could not write the follow clip %s" % path)


def prepare_follows(srcs, segs, tmpdir):
    """{source key: [(a, b, clip path)]} for every moved run the EDL uses."""
    out = {}
    for src in srcs.values():
        for a, b in moved_runs(src, segs):
            mats = track(src, a, b, tmpdir)
            clip = os.path.join(tmpdir, "follow-%s-%.2f-%d.mov" % (src["key"], a, len(mats)))
            if not os.path.exists(clip):
                follow_clip(src, mats, clip)
            out.setdefault(src["key"], []).append((a, b, clip))
    return out


# ---------------------------------------------------------------- zoom

def zoom_plan(specs, segs, fps):
    """Film-time windows for the accent zooms, resolved from SOURCE times.

    A zoom is authored against a source frame -- that is where you can see
    what deserves it -- so `from`/`to` are source seconds of `src`, and `rect`
    is x, y, width of the canvas to end up filling it, all fractions (the
    height follows from the canvas aspect). Resolved here, so a zoom survives
    an EDL change that moves it in the film.
    """
    out = []
    for i, z in enumerate(specs):
        a, b = parse_t(z["from"]), parse_t(z["to"])
        fa = fb = None
        total = segs[-1]["f0"] + segs[-1]["n"]
        for g in range(total):
            s = seg_at(segs, g)
            if fa is None:
                if s["src"]["key"] == z["src"] and src_time(s, g, fps) >= a:
                    fa = fb = g
                continue
            # The window ends at the first frame that leaves this source or
            # passes `to`. Taking "the last frame at or before `to`" instead
            # let a zoom that ended on a cut to the phone reach across the
            # cutaway to the frame after it, and magnified the phone.
            if s["src"]["key"] != z["src"] or src_time(s, g, fps) > b:
                break
            fb = g
        if fa is None or fb is None or fb <= fa:
            sys.exit("zooms[%d]: %s %s-%s is not in the film" % (i, z["src"], fmt(a), fmt(b)))
        rx, ry, rw = [float(v) for v in z["rect"]]
        if not (0 <= rx and 0 <= ry and 0 < rw <= 1 and rx + rw <= 1.0001
                and ry + rw <= 1.0001):
            sys.exit("zooms[%d]: rect %s leaves the canvas" % (i, z["rect"]))
        out.append({"a": fa / fps, "b": (fb + 1) / fps, "rx": rx, "ry": ry, "rw": rw,
                    "in": float(z.get("in", 0.6)), "out": float(z.get("out", 0.6)),
                    "why": z.get("_why", "")})
    return out


def _ease(T, a, d, rising):
    """smoothstep from 0 to 1 over [a, a+d] (rising) or 1 to 0 over [a-d, a]."""
    u = ("((%s-%.4f)/%.4f)" % (T, a, d)) if rising else ("((%.4f-%s)/%.4f)" % (a, T, d))
    return "(%s*%s*(3-2*%s))" % (u, u, u)


def zoom_expr(zooms, f0, fps, canvas):
    """zoompan for one segment whose first film frame is f0. Film time is
    rebuilt from zoompan's own input frame counter, so it is exact."""
    cw, ch = canvas
    U = 2
    T = "((%d+in)/%g)" % (f0, fps)
    terms = []
    for z in zooms:
        a, b, i, o = z["a"], z["b"], z["in"], z["out"]
        e = "1"
        if o > 0:
            e = "if(gt(%s,%.4f),%s,%s)" % (T, b - o, _ease(T, b, o, False), e)
        if i > 0:
            e = "if(lt(%s,%.4f),%s,%s)" % (T, a + i, _ease(T, a, i, True), e)
        terms.append(("if(between(%s,%.4f,%.4f),%s,0)" % (T, a, b, e), z))
    ow = "(1-(%s))" % "+".join("%s*%.5f" % (e, 1 - z["rw"]) for e, z in terms)
    ox = "(%s)" % "+".join("%s*%.5f" % (e, z["rx"]) for e, z in terms)
    oy = "(%s)" % "+".join("%s*%.5f" % (e, z["ry"]) for e, z in terms)
    zp = ("zoompan=z='1/%s':x='%s*%d':y='%s*%d':d=1:s=%dx%d:fps=%g"
          % (ow, ox, cw * U, oy, ch * U, cw, ch, fps))
    return zp.replace(",", "\\,"), U


# ---------------------------------------------------------------- filters

def rect_px(r, w, h):
    x, y, rw, rh = r
    return (int(round(x * w)), int(round(y * h)),
            max(2, int(round(rw * w))), max(2, int(round(rh * h))))


def enable(when, t0, length, holes=()):
    """`:enable=...` for a source-time window minus `holes`, in the chain's
    local time (0 = t0). None when the item is never on in this stretch."""
    terms = []
    if when:
        a, b = parse_t(when[0]) - t0, parse_t(when[1]) - t0
        if b <= 0 or a >= length:
            return None
        terms.append("between(t\\,%.3f\\,%.3f)" % (a, b))
    for a, b in holes:
        a, b = a - t0, b - t0
        if a <= 0 and b >= length:
            return None
        if b > 0 and a < length:
            terms.append("not(between(t\\,%.3f\\,%.3f))" % (a, b))
    return (":enable='%s'" % "*".join(terms)) if terms else ""


class Inputs:
    """ffmpeg -i arguments, handing out each input's index as it is added."""

    def __init__(self):
        self.args = []
        self.n = 0

    def add(self, *args):
        self.args += list(args)
        self.n += 1
        return self.n - 1


def treat(src, t0, length, lab_in, tag, follows, inputs):
    """Paint (fixed, or followed through a zoom) and blur for one source
    stretch starting at source time t0."""
    parts, cur = [], lab_in
    w, h = src["w"], src["h"]
    mine = [(a, b, c) for a, b, c in follows.get(src["key"], [])
            if b > t0 and a < t0 + length]
    holes = [(a, b) for a, b, _ in mine]
    for j, p in enumerate(src.get("paint") or []):
        en = enable(p.get("when"), t0, length, holes)
        if en is None:
            continue
        x, y, rw, rh = rect_px(p["rect"], w, h)
        nxt = "%sp%d" % (tag, j)
        parts.append("[%s]drawbox=x=%d:y=%d:w=%d:h=%d:color=0x%s:t=fill%s[%s]"
                     % (cur, x, y, rw, rh, p["color"].lstrip("#"), en, nxt))
        cur = nxt
    for j, (a, b, clip) in enumerate(mine):
        ix = inputs.add("-i", clip)
        off = a - t0
        lead = ("trim=start=%.4f," % -off) if off < 0 else ""
        shift = ("+%.4f/TB" % off) if off > 0 else ""
        nxt = "%sf%d" % (tag, j)
        # nearest, not bilinear: a smooth upscale blends the clear pixels' black
        # into each rect's edge and draws a dark outline round it
        parts.append("[%d:v]scale=%d:%d:flags=neighbor,format=rgba,%ssetpts=PTS-STARTPTS%s[%sk]"
                     % (ix, w, h, lead, shift, nxt))
        parts.append("[%s][%sk]overlay=0:0:eof_action=pass:"
                     "enable='between(t\\,%.3f\\,%.3f)'[%s]"
                     % (cur, nxt, max(0.0, off), b - t0, nxt))
        cur = nxt
    for j, bl in enumerate(src.get("blur") or []):
        en = enable(bl.get("when"), t0, length)
        if en is None:
            continue
        x, y, rw, rh = rect_px(bl["rect"], w, h)
        sig = float(bl.get("sigma", 6))
        nxt = "%sb%d" % (tag, j)
        parts.append("[%s]split[%sa][%sc]" % (cur, nxt, nxt))
        parts.append("[%sc]crop=%d:%d:%d:%d,gblur=sigma=%.1f[%sk]"
                     % (nxt, rw, rh, x, y, sig, nxt))
        parts.append("[%sa][%sk]overlay=%d:%d%s[%s]" % (nxt, nxt, x, y, en, nxt))
        cur = nxt
    return parts, cur


def fit(cw, ch, bg):
    return ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=0x%s,setsar=1"
            % (cw, ch, cw, ch, bg.lstrip("#")))


def build(segs, canvas, fps, follows, zooms, card_clip=None, card_xy=None, card_g0=0,
          captions=None, audio=None, overlays=None):
    cw, ch = canvas
    inputs, parts = Inputs(), []
    for k, s in enumerate(segs):
        src = s["src"]
        length = s["to"] - s["from"]
        ix = inputs.add("-ss", "%.3f" % s["from"], "-t", "%.3f" % length,
                        "-i", src["abspath"])
        lab = "%d:v" % ix
        if int(src.get("rotate", 0)) == 180:
            # a phone's rotation tag can be wrong or missing; this one had none
            # and the picture was upside down (the keyboard legends read inverted)
            parts.append("[%s]hflip,vflip[r%d]" % (lab, k))
            lab = "r%d" % k
        tp, cur = treat(src, s["from"], length, lab, "s%d" % k, follows, inputs)
        parts += tp
        sp = s["speed"]
        pts = "PTS-STARTPTS" if sp == 1.0 else "(PTS-STARTPTS)/%g" % sp
        # A crop is how a landscape screen becomes a vertical short: it runs
        # AFTER paint and blur, so their rects stay in full-source pixels --
        # the one frame a human measured them on.
        crop = ("crop=%d:%d:%d:%d," % (s["crop"][2], s["crop"][3], s["crop"][0], s["crop"][1])
                if s.get("crop") else "")
        chain = ("%ssetpts=%s,fps=%g,%s,trim=end_frame=%d,setpts=PTS-STARTPTS"
                 % (crop, pts, fps, fit(cw, ch, src.get("bg", "#000000")), s["n"]))
        a, b = s["f0"] / fps, (s["f0"] + s["n"]) / fps
        mine = [z for z in zooms if z["b"] > a and z["a"] < b]
        if mine:
            zp, U = zoom_expr(mine, s["f0"], fps, canvas)
            # zoompan crops on whole input pixels; at 2x the step is half a
            # film pixel, which is what keeps a slow push from shimmering
            chain += ",scale=%d:%d:flags=lanczos,%s" % (cw * U, ch * U, zp)
        parts.append("[%s]%s,format=yuv420p[v%d]" % (cur, chain, k))
    parts.append("".join("[v%d]" % k for k in range(len(segs)))
                 + "concat=n=%d:v=1:a=0[film]" % len(segs))
    out = "film"
    if card_clip:
        ci = inputs.add("-i", card_clip)
        parts.append("[%d:v]format=rgba,setpts=PTS-STARTPTS+%.6f/TB[card]"
                     % (ci, card_g0 / fps))
        parts.append("[film][card]overlay=%d:%d:eof_action=pass:format=auto,"
                     "format=yuv420p[vout]" % card_xy)
        out = "vout"
    if overlays:
        # image-overlay.py owns the look and the motion; it hands back PNGs to
        # add as looped inputs and a graph to splice onto the tail of ours
        io = _imgoverlay()
        pngs, ofc, oout = io.prepare(overlays["preset"], overlays["specs"], cw, ch,
                                     overlays["tmpdir"], tag="edl", base=out,
                                     first_input=inputs.n, runtime=overlays["runtime"])
        for png in pngs:
            inputs.add("-loop", "1", "-framerate", "%g" % fps, "-i", png)
        if ofc:
            parts.append(ofc)
            out = oout
    if captions:
        # after the counter card, so a caption is never drawn under it; the
        # path is repo-relative because ffmpeg runs from ROOT and a Windows
        # drive letter's colon breaks the filter's own option parser
        parts.append("[%s]subtitles='%s':fontsdir='fonts'[vcap]" % (out, captions))
        out = "vcap"
    aout = None
    if audio:
        rt = (segs[-1]["f0"] + segs[-1]["n"]) / fps
        fmt_a = "aformat=sample_rates=48000:channel_layouts=stereo"
        vi = inputs.add("-i", audio["voice"])
        parts.append("[%d:a]%s,volume=%.1fdB,apad,atrim=0:%.4f[vo]"
                     % (vi, fmt_a, float(audio.get("voice_db", 0)), rt))
        if audio.get("music"):
            mi = inputs.add("-stream_loop", "-1", "-i", audio["music"])
            fade_out = float(audio.get("music_fade_out", 3.0))
            parts.append("[%d:a]%s,atrim=0:%.4f,volume=%.1fdB,afade=t=in:d=%.2f,"
                         "afade=t=out:st=%.4f:d=%.2f[mu]"
                         % (mi, fmt_a, rt, float(audio.get("music_db", -20)),
                            float(audio.get("music_fade_in", 1.5)),
                            max(0.0, rt - fade_out), fade_out))
            # the voice keys a compressor on the music: the bed drops under
            # every line and comes back up in the pauses, by itself
            d = audio.get("duck") or {}
            parts.append("[vo]asplit[vo1][vok]")
            parts.append("[mu][vok]sidechaincompress=threshold=%g:ratio=%g:attack=%g:release=%g[duck]"
                         % (d.get("threshold", 0.03), d.get("ratio", 8), d.get("attack", 15),
                            d.get("release", 400)))
            parts.append("[vo1][duck]amix=inputs=2:normalize=0:duration=first[mix]")
            src = "mix"
        else:
            src = "vo"
        parts.append("[%s]loudnorm=I=%g:TP=-1.5:LRA=11,aresample=48000,atrim=0:%.4f[aout]"
                     % (src, float(audio.get("lufs", -14)), rt))
        aout = "aout"
    return inputs.args, ";".join(parts), out, aout


# ---------------------------------------------------------------- modes

def show_list(segs, fps, total, cps, zooms, runs):
    print("\n  %-3s %-8s %-19s %6s  %-17s %s" % ("#", "source", "source in->out",
                                                "speed", "film in->out", "why"))
    for s in segs:
        a = s["f0"] / fps
        b = (s["f0"] + s["n"]) / fps
        print("  %-3d %-8s %8s->%-9s %5gx  %7s->%-8s %s"
              % (s["i"], s["src"]["key"], fmt(s["from"]), fmt(s["to"]), s["speed"],
                 fmt(a), fmt(b), s["why"][:70]))
    src_in = sum(s["to"] - s["from"] for s in segs)
    print("\n  runtime %s (%d frames at %g fps) from %s of source"
          % (fmt(total / fps), total, fps, fmt(src_in)))
    for spec, cp in cps:
        print("  counter '%s': film %s -> %s, stops at %s (true source interval "
              "%.2f s), holds to %s"
              % (spec.get("label"), fmt(cp["g0"] / fps), fmt(cp["gend"] / fps),
                 clock(cp["total_s"]), cp["total_s"], fmt(cp["g1"] / fps)))
        if cp["cut_s"] > 0.05:
            print("    note: %.1f s of the counted interval is cut; the clock "
                  "jumps across it" % cp["cut_s"])
    for z in zooms:
        print("  zoom %.2fx film %s -> %s (in %.1fs, out %.1fs)  %s"
              % (1 / z["rw"], fmt(z["a"]), fmt(z["b"]), z["in"], z["out"], z["why"][:60]))
    for key, rs in runs.items():
        for a, b in rs:
            print("  follow %s %s -> %s: the chrome moves here, so its paint is tracked"
                  % (key, fmt(a), fmt(b)))


def one_frame(segs, canvas, fps, t, follows, zooms, cards, out_png):
    """The real graph, one frame long -- so the check cannot disagree with the render."""
    g = int(round(t * fps))
    s = seg_at(segs, g)
    if s is None:
        sys.exit("film time %s is past the end" % fmt(t))
    st = src_time(s, g, fps)
    mini = dict(s, **{"from": st, "to": min(s["src"]["dur"], st + 2.0 * s["speed"] / fps),
                      "f0": g, "n": 1})
    inputs, graph, out, _ = build([mini], canvas, fps, follows, zooms)
    tmp = out_png + ".base.png"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs
                       + ["-filter_complex", graph, "-map", "[%s]" % out,
                          "-frames:v", "1", tmp], env=ENV, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    im = Image.open(tmp).convert("RGBA")
    os.remove(tmp)
    for card, xy, frames in cards:
        for fg, cim in frames:
            if fg == g:
                im.alpha_composite(cim, xy)
    im.convert("RGB").save(out_png)
    print("  film %s = %s %s (x%g)  ->  %s"
          % (fmt(t), s["src"]["key"], fmt(st), s["speed"], rel(out_png)))


def _imgoverlay():
    from importlib import import_module
    return import_module("image-overlay")


def caption_ass(spec, canvas, tmpdir):
    """Build the ASS for the manifest's captions (words + style) with the
    repo's own caption builder, scaled to the canvas; returns a repo-relative
    path for ffmpeg.

    The words are the VOICE-OVER's (dub-clips.py writes them in film time), not
    an ASR pass over the film: a silent screencast has nothing to transcribe,
    and the TTS's own timings are exact where a transcription is a guess.
    """
    out = os.path.join(tmpdir, "captions.ass")
    words = _env.resolve(spec["words"], base=_env.workspace())
    if spec.get("display"):
        words = display_words(words, spec["display"], os.path.join(tmpdir, "captions.words.json"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build-captions-ass.py"),
                        "--words", words,
                        "--style", _env.resolve(spec["style"]),
                        "--out", out, "--scale-to", str(canvas[0]), str(canvas[1])],
                       env=ENV, capture_output=True, text=True)
    if r.returncode:
        sys.exit("caption build failed:\n" + (r.stderr or r.stdout)[-2000:])
    return rel(out)


def _bare(w):
    import re
    return re.sub(r"[^\w'-]", "", w.lower())


def display_words(path, table, out):
    """Rewrite spoken phrases into how they should READ, keeping the timing.

    A voice says "five hundred and thirty-four"; the picture and the viewer
    both mean 534, and a caption that spells it out is five words to read
    where one would do. Each `display` entry maps a spoken phrase to its
    written form; the matched words collapse into one, from the first word's
    start to the last word's end, and keep the last word's punctuation.
    """
    import re
    doc = json.load(open(path, encoding="utf-8"))
    words = doc["words"] if isinstance(doc, dict) else doc
    keyed = sorted(((k.lower().split(), v) for k, v in table.items() if not k.startswith("_")),
                   key=lambda kv: -len(kv[0]))
    res, i, hits = [], 0, 0
    while i < len(words):
        for spoken, written in keyed:
            n = len(spoken)
            if [_bare(w["text"]) for w in words[i:i + n]] == [_bare(x) for x in spoken]:
                tail = re.sub(r"^.*?([^\w'-]*)$", r"\1", words[i + n - 1]["text"].strip())
                res.append(dict(words[i], text=written + tail, end=words[i + n - 1]["end"]))
                i += n
                hits += 1
                break
        else:
            res.append(words[i])
            i += 1
    if isinstance(doc, dict):
        doc = dict(doc, words=res)
    else:
        doc = res
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("  captions: %d spoken phrase(s) shown in written form" % hits)
    return out


def audio_peak(path):
    """Peak level of a file's audio in dB, or None if it has none."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", "volumedetect", "-f", "null", "-"],
                       env=ENV, capture_output=True, text=True)
    for line in (r.stderr or "").splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split("dB")[0])
            except ValueError:
                return None
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the EDL, runtime, counter, zooms and followed chrome; "
                         "encode nothing")
    ap.add_argument("--frame", action="append", default=[], metavar="M:SS",
                    help="write the finished frame at this FILM time as a PNG; repeatable")
    ap.add_argument("--out", help="override the manifest's output path")
    args = ap.parse_args()

    m, srcs, segs, canvas, fps, total = load(args.manifest)
    mid = m.get("id") or os.path.basename(os.path.dirname(os.path.abspath(args.manifest)))
    style = json.load(open(_env.resolve(m.get("counter_style", DEFAULT_STYLE)),
                           encoding="utf-8"))
    specs = m.get("counters") or []
    if len(specs) > 1:
        sys.exit("one counter per film for now; the overlay chain takes one clip")
    cps = [(sp, counter_plan(sp, segs, fps, total)) for sp in specs]
    zooms = zoom_plan(m.get("zooms") or [], segs, fps)
    tmpdir = os.path.join(_project.projects_dir(), mid, "temp", "edl")
    os.makedirs(tmpdir, exist_ok=True)

    if args.list:
        runs = {k: moved_runs(s, segs) for k, s in srcs.items() if s.get("paint")}
        show_list(segs, fps, total, cps, zooms, {k: v for k, v in runs.items() if v})
        return

    follows = prepare_follows(srcs, segs, tmpdir)
    cards = []
    for sp, cp in cps:
        st = dict(style, **{k: sp[k] for k in ("hold_after", "fade") if k in sp})
        card = Card(st, sp, canvas[1])
        cards.append((card, card.xy(*canvas), card_frames(cp, card, fps)))

    if args.frame:
        for t in args.frame:
            tt = parse_t(t)
            one_frame(segs, canvas, fps, tt, follows, zooms, cards,
                      os.path.join(tmpdir, "frame-%s.png" % fmt(tt).replace(":", "m")))
        return

    dst = _env.resolve(args.out or m["output"], base=_env.workspace())
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    clip = xy = None
    g0 = 0
    if cards:
        card, xy, frames = cards[0]
        clip = os.path.join(tmpdir, "counter.mov")
        write_card_video(frames, card, fps, clip)
        g0 = cps[0][1]["g0"]
    capspec = m.get("captions")
    ass = caption_ass(capspec, canvas, tmpdir) if capspec else None
    audio = m.get("audio")
    if audio:
        audio = dict(audio, voice=_env.resolve(audio["voice"], base=_env.workspace()),
                     music=(_env.resolve(audio["music"], base=_env.workspace())
                            if audio.get("music") else None))
        for k in ("voice", "music"):
            if audio.get(k) and not os.path.exists(audio[k]):
                sys.exit("audio.%s: %s does not exist" % (k, audio[k]))
    img_specs = m.get("image_overlays") or []
    ov = None
    if img_specs:
        preset = m.get("overlay_preset", "config/overlays/end-card.json")
        pdoc = json.load(open(_env.resolve(preset), encoding="utf-8"))
        for i, sp in enumerate(img_specs):
            at, _ = _imgoverlay().resolve_window(sp, pdoc, total / fps)
            if at >= total / fps:
                sys.exit("image overlay %d starts at %.1fs but the film runs %.1fs"
                         % (i, at, total / fps))
        ov = {"preset": preset, "specs": img_specs, "tmpdir": tmpdir, "runtime": total / fps,
              "doc": pdoc}
    inputs, graph, out, aout = build(segs, canvas, fps, follows, zooms, clip, xy, g0,
                                     captions=ass, audio=audio, overlays=ov)
    render = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    runtime = total / fps
    tmp = dst + ".part.mp4"
    prog = _progress.begin(mid, runtime, rel(dst))
    cmd = (["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-progress", prog] + inputs
           + ["-filter_complex", graph, "-map", "[%s]" % out]
           + (["-map", "[%s]" % aout] if aout else ["-an"]) + ["-r", "%g" % fps]
           + _encode.video_args(render)
           + (_encode.audio_args(render) if aout else [])
           + ["-movflags", "+faststart", "-y", tmp])
    print("\n  rendering %s  (%s, %d segments, %s)"
          % (rel(dst), fmt(runtime), len(segs), _encode.describe(render)))
    try:
        p = subprocess.run(cmd, env=ENV, capture_output=True, text=True, cwd=ROOT)
    finally:
        _progress.end(mid)
    if p.returncode:
        sys.stderr.write((p.stderr or "")[-4000:])
        sys.exit("ffmpeg failed")
    got = _overlay.probe(tmp)[3]
    if abs(got - runtime) > 2.0 / fps + 0.05:
        sys.exit("output is %.3fs, the EDL predicted %.3fs; %s left in place"
                 % (got, runtime, tmp))
    if aout:
        peak = audio_peak(tmp)
        if peak is None or peak < -60:
            sys.exit("the rendered audio is silent (peak %s dB); %s left in place" % (peak, tmp))
    shutil.move(tmp, dst)
    print("  %s  %s  %.1f MB" % (rel(dst), fmt(got), os.path.getsize(dst) / 1e6))

    burned = ["EDL cut: %d segments from %d sources, %s"
              % (len(segs), len({s["src"]["key"] for s in segs}), fmt(runtime))]
    for s in srcs.values():
        if int(s.get("rotate", 0)):
            burned.append("rotate %s by %s" % (s["key"], s["rotate"]))
        for p_ in s.get("paint") or []:
            burned.append("paint %s %s: %s" % (s["key"], p_["rect"], p_.get("_why", "")))
        for a, b, _ in follows.get(s["key"], []):
            burned.append("paint on %s tracked through %s-%s (the recorder zooms there)"
                          % (s["key"], fmt(a), fmt(b)))
        for b in s.get("blur") or []:
            burned.append("blur %s %s %s: %s" % (s["key"], b["rect"], b.get("when"),
                                                 b.get("_why", "")))
    for z in zooms:
        burned.append("zoom %.2fx film %s-%s: %s" % (1 / z["rw"], fmt(z["a"]), fmt(z["b"]),
                                                     z["why"]))
    for sp in img_specs:
        burned.append(_imgoverlay().describe(sp, ov["doc"], total / fps))
    if capspec:
        burned.append("captions %s from %s" % (capspec["style"], capspec["words"]))
    if audio:
        a_ = m["audio"]
        burned.append("audio: voice %s%s, loudnorm %s LUFS"
                      % (a_["voice"],
                         (" + music %s at %s dB, ducked under the voice"
                          % (a_["music"], a_.get("music_db", -20))) if a_.get("music")
                         else ", no music", a_.get("lufs", -14)))
    for sp, cp in cps:
        burned.append("elapsed counter '%s' film %s-%s, stops at %s (source %s->%s)"
                      % (sp.get("label"), fmt(cp["g0"] / fps), fmt(cp["g1"] / fps),
                         clock(cp["total_s"]), sp["start"], sp["end"]))
    _project.record(_project.project_id(m, args.manifest), "render",
                    out=dst, script=__file__, argv=sys.argv[1:], kind="edl",
                    manifest=args.manifest, burned=burned)


if __name__ == "__main__":
    main()
