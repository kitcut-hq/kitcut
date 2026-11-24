#!/usr/bin/env python
"""A smooth camera tour over one document page, inside a real app screen.

A phone screen recording of a filled PDF is honest but unwatchable: a one-page
form is unreadable at full-page zoom, and a thumb's pinch-and-drag is jerky.
This renders the tour the thumb was trying to make -- full page, then eased
moves to each block, each block highlighted with a label, then back out -- on
a high-resolution render of the page, composited into a still of the real
viewer (its status bar, address bar and toolbar), so the tour cuts in where the
recording showed the same page at the same framing.

The spec is data:

    {"page": "assets/form.png",        # high-res page render
     "chrome": "temp/viewer.png",      # a viewer frame, the screen source's size
     "viewport": [0, 562, 1080, 1728], # where the page is drawn inside the chrome
     "bg": "#EFF3F7",                  # the viewer's own background around the page
     "start": {"s": 0.285, "x": 56, "y": 1},   # the recording's framing: page px -> screen
     "focus_y": 0.40,                  # a stop's block lands this far down the viewport
     "stops": [{"rect": [x0, y0, x1, y1], "width": 1700, "move": 0.8, "hold": 1.6,
                "marks": [{"rect": [...], "label": "From the policy"}]}],
     "out": "temp/tour.mp4"}

`rect` (page px) is what a stop is about and `width` how many page px fill the
viewport's width there; `marks` are boxes highlighted while the camera holds.
A stop with no `rect` returns to `start`. Every frame is a pure function of t.

  --plan     print every stop's film time, zoom and the type size it shows; render nothing
  --frame T  one frame at T as a PNG
  (none)     render the MP4

Invoke as:  python scripts/page-tour.py --spec projects/<id>/tour.json --plan
"""

import sys
import os
import json
import math
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import _encode  # noqa: E402
import _project  # noqa: E402

DEFAULT_STYLE = {
    "fill": "#F2B630",
    "fill_alpha": 0.22,
    "stroke": "#F2B630",
    "stroke_px": 6,
    "radius": 10,
    "pad": 8,
    "label_font": "fonts/Montserrat-Bold.ttf",
    "label_size": 30,
    "label_bg": "#16181D",
    "label_fg": "#F2B630",
    "fade": 0.25,
    "mark_stagger": 0.35,
}


def rgba(c, a=1.0):
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4)) + (int(round(255 * a)),)


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class Tour:
    def __init__(self, spec, base):
        self.spec = spec
        rp = lambda p: _env.resolve(p, base=base)  # noqa: E731
        self.page = Image.open(rp(spec["page"])).convert("RGB")
        self.chrome = Image.open(rp(spec["chrome"])).convert("RGB")
        self.vx, self.vy, self.vw, self.vh = spec["viewport"]
        self.bg = rgba(spec.get("bg", "#FFFFFF"))
        self.fps = float(spec.get("fps", 30))
        self.style = dict(DEFAULT_STYLE, **spec.get("style", {}))
        self.font = ImageFont.truetype(
            _env.resolve(self.style["label_font"]), self.style["label_size"]
        )
        if self.style.get("label_variation"):  # a variable font: the named instance
            self.font.set_variation_by_name(self.style["label_variation"])
        st = spec["start"]
        # A view is (centre x, centre y, page px across the viewport width).
        w0 = self.vw / st["s"]
        self.v0 = ((self.vw / 2 - st["x"]) / st["s"], (self.vh / 2 - st["y"]) / st["s"], w0)
        fy = float(spec.get("focus_y", 0.40))
        self.keys = [(0.0, self.v0, [])]  # (t, view, marks)
        t = float(spec.get("lead", 0.8))
        self.keys.append((t, self.v0, []))
        for s in spec["stops"]:
            if s.get("rect"):
                x0, y0, x1, y1 = s["rect"]
                w = float(s["width"])
                h = w * self.vh / self.vw
                v = ((x0 + x1) / 2.0, (y0 + y1) / 2.0 + (0.5 - fy) * h, w)
            else:
                v = self.v0
            t_arrive = t + float(s.get("move", 0.8))
            t_leave = t_arrive + float(s.get("hold", 1.5))
            self.keys.append((t_arrive, v, s.get("marks", []), t_leave))
            self.keys.append((t_leave, v, []))
            t = t_leave
        self.dur = t + float(spec.get("tail", 0.0))

    def view(self, t):
        ks = [(k[0], k[1]) for k in self.keys]
        if t <= ks[0][0]:
            return ks[0][1]
        for (ta, va), (tb, vb) in zip(ks, ks[1:], strict=False):
            if ta <= t <= tb:
                u = ease((t - ta) / (tb - ta)) if tb > ta else 1.0
                # zoom eases in log space, so a 3x zoom does not race at the start
                w = math.exp(math.log(va[2]) + (math.log(vb[2]) - math.log(va[2])) * u)
                return (va[0] + (vb[0] - va[0]) * u, va[1] + (vb[1] - va[1]) * u, w)
        return ks[-1][1]

    def marks_at(self, t):
        out = []
        st = self.style
        for k in self.keys:
            if len(k) < 4 or not k[2]:
                continue
            ta, tl = k[0], k[3]
            for i, mk in enumerate(k[2]):
                a = ta + i * st["mark_stagger"]
                if a <= t <= tl:
                    alpha = min(1.0, (t - a) / st["fade"], (tl - t) / st["fade"])
                    out.append((mk, max(0.0, alpha)))
        return out

    def frame(self, t):
        cx, cy, w = self.view(t)
        s = self.vw / w
        h = self.vh / s
        wx0, wy0 = cx - w / 2, cy - h / 2
        vp = Image.new("RGB", (self.vw, self.vh), self.bg[:3])
        pw, ph = self.page.size
        ix0, iy0 = max(0.0, wx0), max(0.0, wy0)
        ix1, iy1 = min(float(pw), wx0 + w), min(float(ph), wy0 + h)
        if ix1 > ix0 and iy1 > iy0:
            sx0, sy0 = (ix0 - wx0) * s, (iy0 - wy0) * s
            tw, th = max(1, round((ix1 - ix0) * s)), max(1, round((iy1 - iy0) * s))
            crop = self.page.resize((tw, th), Image.BICUBIC, box=(ix0, iy0, ix1, iy1))
            vp.paste(crop, (round(sx0), round(sy0)))
        marks = self.marks_at(t)
        if marks:
            vp = vp.convert("RGBA")
            st = self.style
            for mk, al in marks:
                lay = Image.new("RGBA", vp.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(lay)
                x0, y0, x1, y1 = mk["rect"]
                p = st["pad"]
                b = [(x0 - wx0) * s - p, (y0 - wy0) * s - p, (x1 - wx0) * s + p, (y1 - wy0) * s + p]
                d.rounded_rectangle(b, st["radius"], fill=rgba(st["fill"], st["fill_alpha"] * al))
                d.rounded_rectangle(
                    b, st["radius"], outline=rgba(st["stroke"], al), width=st["stroke_px"]
                )
                if mk.get("label"):
                    tw = d.textlength(mk["label"], font=self.font)
                    lh = st["label_size"] + 22
                    side = mk.get("side", "above")
                    lx = min(max(8, b[0]), self.vw - tw - 40)
                    ly = b[1] - lh - 8 if side == "above" else b[3] + 8
                    d.rounded_rectangle(
                        [lx, ly, lx + tw + 32, ly + lh],
                        lh / 2,
                        fill=rgba(st["label_bg"], 0.95 * al),
                    )
                    d.text(
                        (lx + 16, ly + lh / 2),
                        mk["label"],
                        font=self.font,
                        fill=rgba(st["label_fg"], al),
                        anchor="lm",
                    )
                vp = Image.alpha_composite(vp, lay)
            vp = vp.convert("RGB")
        out = self.chrome.copy()
        out.paste(vp, (self.vx, self.vy))
        # UI that floats over the page in the real app (a chat bubble) is put
        # back on top from the chrome still: [cx, cy, r] circles.
        for cx_, cy_, r in self.spec.get("keep_circles", []):
            m = Image.new("L", out.size, 0)
            ImageDraw.Draw(m).ellipse([cx_ - r, cy_ - r, cx_ + r, cy_ + r], fill=255)
            out.paste(self.chrome, (0, 0), m)
        return out


def main():
    ap = argparse.ArgumentParser(description="A smooth camera tour over a document page.")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--plan", action="store_true", help="print the stops; render nothing")
    ap.add_argument("--frame", type=float, help="write the frame at T as a PNG")
    args = ap.parse_args()
    sp = _env.resolve(args.spec, base=_env.workspace())
    spec = json.load(open(sp, encoding="utf-8"))
    tour = Tour(spec, _env.workspace())
    fps = tour.fps
    pt = float(spec.get("page_px_per_pt", 1.0))
    if args.plan or args.frame is None:
        print("  tour %.2fs at %g fps, %d frames" % (tour.dur, fps, int(tour.dur * fps)))
        for k in tour.keys:
            if len(k) == 4:
                s = tour.vw / k[1][2]
                print(
                    "  %5.2f-%5.2f  scale %.3f  7.5pt type -> %.0f px   %s"
                    % (k[0], k[3], s, 7.5 * pt * s, ", ".join(m.get("label", "") for m in k[2]))
                )
        if args.plan:
            return
    if args.frame is not None:
        out = os.path.splitext(sp)[0] + "-%05.2f.png" % args.frame
        tour.frame(args.frame).save(out)
        print(out)
        return
    out = _env.resolve(spec["out"], base=_env.workspace())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    W, H = tour.chrome.size
    cfg = _encode.resolve({"cq": 16})
    cmd = (
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24"]
        + ["-s", "%dx%d" % (W, H), "-r", "%g" % fps, "-i", "-"]
        + _encode.video_args(cfg)
        + [out]
    )
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=_env.ENV)
    n = int(round(tour.dur * fps))
    for i in range(n):
        p.stdin.write(tour.frame(i / fps).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        sys.exit("ffmpeg failed")
    print("  %s  %.2fs" % (out, n / fps))
    pd = _project.find_project_dir(out)
    if pd:
        _project.record(
            os.path.basename(pd),
            "page tour %.2fs (%d stops)" % (n / fps, len(spec["stops"])),
            out=out,
            script=__file__,
            manifest=sp,
            kind="section",
        )


if __name__ == "__main__":
    main()
