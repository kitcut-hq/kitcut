#!/usr/bin/env python
"""An animated checklist end screen: items tick in one after another.

A full-frame card, not an overlay: a headline, then each line's box pops in,
its text slides in beside it, and a check mark draws itself into the box --
one line after another -- then a call to action. Built for the end of a
product demo, where the film has shown the work and the card says what was
done, in the film's own backdrop colour so it reads as the same film.

Three things are separate, as with make-card.py: the WORDS are a project spec
(`projects/<id>/cards/*.json`: headline, items, cta), the LOOK is a style
(`config/cards/checklist/*.json`: colours, fonts, panel, sizes), and the
TIMING lives in the style too (when the first item lands, the step between
items, how long a tick takes to draw). Swap the style and it is another look;
swap the spec and it is another film.

Every frame is drawn by Pillow from time t, so a still at any t is exactly the
frame the render will contain. edl-cut.py places the card in a film as an EDL
entry `{"card": <spec>, "style": <style>}`; its length comes from here.

  --list          the timeline: when each line lands, the hold, the total
  --png T         the frame at card time T (default: the final state)
  --sheet         a strip of frames across the animation, for review
  --clip OUT      the whole card as a video clip (what edl-cut.py consumes)

Invoke as:  python scripts/checklist-card.py --spec projects/<id>/cards/checklist.json --style config/cards/checklist/window.json --list
"""
import sys
import os
import json
import math
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
import _overlay  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_TIMING = {"headline_at": 0.25, "first_at": 1.0, "step": 0.75,
                  "pop": 0.28, "tick_delay": 0.18, "tick": 0.32,
                  "cta_after": 0.5, "hold": 2.2}


def rgba(h, a=255):
    return _overlay.hex_rgba(h, a)


def ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def ease_back(u):
    """Overshoots a little and settles -- the 'pop' of a box landing."""
    u = min(1.0, max(0.0, u))
    c = 1.70158
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


def timing(style):
    return dict(DEFAULT_TIMING, **(style.get("timing") or {}))


def timeline(spec, style):
    """(headline_t, [item_t...], cta_t, total) in card seconds."""
    tm = timing(style)
    items = [tm["first_at"] + i * tm["step"] for i in range(len(spec["items"]))]
    last_tick = items[-1] + tm["tick_delay"] + tm["tick"] if items else tm["first_at"]
    cta = last_tick + tm["cta_after"] if spec.get("cta") else None
    end = (cta + 0.4 if cta is not None else last_tick) + tm["hold"]
    return tm["headline_at"], items, cta, end


class Checklist:
    def __init__(self, spec, style, size):
        self.spec, self.st = spec, style
        self.W, self.H = size
        self.k = self.H / 1080.0
        f = lambda key: ImageFont.truetype(  # noqa: E731
            _overlay.repo_path(style[key]["font"]), max(6, int(round(style[key]["size"] * self.k))))
        self.f_head, self.f_item, self.f_cta = f("headline"), f("item"), f("cta")
        self.t_head, self.t_items, self.t_cta, self.total = timeline(spec, style)
        self.tm = timing(style)
        self._bg = self._background()
        self._layout()

    # -- static parts ----------------------------------------------------
    def _background(self):
        st, W, H = self.st, self.W, self.H
        bg = Image.new("RGBA", (W, H), rgba(st["background"]))
        glow = st.get("glow")
        if glow:
            # the recorder's backdrop is not flat: lighter in the middle
            g = Image.new("L", (W, H), 0)
            ImageDraw.Draw(g).ellipse([W * 0.15, H * 0.05, W * 0.85, H * 0.95], fill=255)
            g = g.filter(ImageFilter.GaussianBlur(H * 0.18))
            bg = Image.composite(Image.new("RGBA", (W, H), rgba(glow)), bg, g)
        p = st.get("panel")
        if p:
            pw, ph = int(p["w"] * self.k), int(self._panel_h())
            x0, y0 = (W - pw) // 2, (H - ph) // 2
            self.panel_box = (x0, y0, x0 + pw, y0 + ph)
            if p.get("shadow"):
                sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(sh).rounded_rectangle(
                    [x0, y0 + 18 * self.k, x0 + pw, y0 + ph + 18 * self.k],
                    radius=int(p["radius"] * self.k), fill=rgba(p["shadow"], int(255 * p.get("shadow_alpha", 0.18))))
                sh = sh.filter(ImageFilter.GaussianBlur(28 * self.k))
                bg.alpha_composite(sh)
            ImageDraw.Draw(bg).rounded_rectangle([x0, y0, x0 + pw, y0 + ph],
                                                 radius=int(p["radius"] * self.k),
                                                 fill=rgba(p["fill"]))
        else:
            self.panel_box = None
        return bg

    def _panel_h(self):
        st, k = self.st, self.k
        n = len(self.spec["items"])
        h = st["pad"] * 2 + st["headline"]["size"] * 1.25 + st["gap_head"] + \
            n * st["row"] + (st["gap_cta"] + st["cta"]["size"] * 1.4 if self.spec.get("cta") else 0)
        return h * k

    def _layout(self):
        st, k = self.st, self.k
        n = len(self.spec["items"])
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        widest = max([d.textlength(t, font=self.f_item) for t in self.spec["items"]] + [1])
        box = st["box"]["size"] * k
        chip = 2 * st["item_chip"]["pad"] * k if st.get("item_chip") else 0
        block_w = max(box + st["box"]["gap"] * k + widest + chip,
                      d.textlength(self.spec["headline"], font=self.f_head))
        block_h = self._panel_h() - 2 * st["pad"] * k
        if self.panel_box:
            x0, y0, x1, y1 = self.panel_box
            self.left = x0 + st["pad"] * k if st.get("align") == "left" else (self.W - block_w) / 2
            self.top = y0 + st["pad"] * k
        else:
            self.left = (self.W - block_w) / 2
            self.top = (self.H - block_h) / 2
        self.block_w = block_w
        self.row_y = [self.top + (st["headline"]["size"] * 1.25 + st["gap_head"] + i * st["row"]) * k
                      for i in range(n)]
        self.cta_y = self.top + (st["headline"]["size"] * 1.25 + st["gap_head"] + n * st["row"]
                                 + st["gap_cta"]) * k

    # -- one frame -------------------------------------------------------
    def frame(self, t):
        st, k, tm = self.st, self.k, self.tm
        im = self._bg.copy()
        # Shapes go on their own layer and are composited: ImageDraw on an RGBA
        # image REPLACES pixels rather than blending, so a clear fill wrote
        # opaque green into the empty box, and a half-faded pop wrote holes.
        shapes = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(shapes)
        # headline: rises 24 px and fades in
        u = ease_out((t - self.t_head) / 0.45)
        if u > 0:
            self._text(im, (self.left, self.top + (1 - u) * 24 * k), self.spec["headline"],
                       self.f_head, st["headline"]["colour"], u)
        box = st["box"]["size"] * k
        for i, (txt, t0) in enumerate(zip(self.spec["items"], self.t_items)):
            y = self.row_y[i]
            p = (t - t0) / tm["pop"]
            if p <= 0:
                continue
            s = ease_back(p)
            a = min(1.0, p * 2)
            cx, cy = self.left + box / 2, y + box / 2
            half = box / 2 * max(0.01, s)
            tick_u = (t - t0 - tm["tick_delay"]) / tm["tick"]
            filled = tick_u > 0
            r = st["box"]["radius"] * k
            if st["box"].get("shape") == "circle":
                r = half
            if filled:
                d.rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=min(r, half),
                                    fill=rgba(st["box"]["fill"], int(255 * a)))
            else:
                ea = st["box"].get("empty_alpha", 0)
                d.rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=min(r, half),
                                    fill=(rgba(st["box"].get("empty", st["box"]["fill"]), int(255 * a * ea))
                                          if ea else None),
                                    outline=rgba(st["box"]["outline"], int(255 * a)),
                                    width=max(2, int(st["box"]["stroke"] * k)))
            if filled:
                self._tick(d, cx, cy, box, min(1.0, tick_u), st["box"]["tick"])
            # the line slides in from the left and fades
            tu = ease_out((t - t0 - 0.05) / 0.4)
            if tu > 0:
                tx = self.left + box + st["box"]["gap"] * k - (1 - tu) * 30 * k
                ty = cy - self.f_item.getbbox("Hg")[3] / 2 - self.f_item.getbbox("H")[1] / 2 + 2 * k
                if st.get("item_chip"):
                    self._chip(im, tx, cy, txt, tu)
                self._text(im, (tx + (st["item_chip"]["pad"] * k if st.get("item_chip") else 0), ty),
                           txt, self.f_item, st["item"]["colour"], tu)
        im.alpha_composite(shapes)
        if self.t_cta is not None:
            u = ease_out((t - self.t_cta) / 0.5)
            if u > 0:
                self._text(im, (self.left, self.cta_y + (1 - u) * 16 * k), self.spec["cta"],
                           self.f_cta, st["cta"]["colour"], u)
                dot = st.get("cta_dot")
                if dot:
                    w = ImageDraw.Draw(im).textlength(self.spec["cta"], font=self.f_cta)
                    rr = 7 * k
                    cy = self.cta_y + (1 - u) * 16 * k + self.f_cta.getbbox("H")[3] * 0.62
                    ImageDraw.Draw(im).ellipse([self.left + w + 12 * k, cy - rr, self.left + w + 12 * k + 2 * rr, cy + rr],
                                               fill=rgba(dot, int(255 * u)))
        return im

    def _text(self, im, xy, txt, font, colour, alpha):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(xy, txt, font=font, fill=rgba(colour, int(255 * alpha)))
        im.alpha_composite(layer)

    def _chip(self, im, x, cy, txt, u):
        c, k = self.st["item_chip"], self.k
        w = ImageDraw.Draw(im).textlength(txt, font=self.f_item) + 2 * c["pad"] * k
        h = self.st["item"]["size"] * k * 1.9
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle([x, cy - h / 2, x + w, cy + h / 2], radius=int(h / 2),
                                                fill=rgba(c["fill"], int(255 * u)))
        im.alpha_composite(layer)

    def _tick(self, d, cx, cy, box, u, colour):
        """A check mark drawn as a stroke that grows along its two legs."""
        k = self.k
        p0 = (cx - box * 0.24, cy + box * 0.02)
        p1 = (cx - box * 0.06, cy + box * 0.20)
        p2 = (cx + box * 0.26, cy - box * 0.18)
        l1 = math.dist(p0, p1)
        l2 = math.dist(p1, p2)
        run = u * (l1 + l2)
        w = max(3, int(self.st["box"].get("tick_width", 5) * k))
        if run <= l1:
            f = run / l1
            d.line([p0, (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)],
                   fill=rgba(colour), width=w, joint="curve")
        else:
            f = (run - l1) / l2
            d.line([p0, p1, (p1[0] + (p2[0] - p1[0]) * f, p1[1] + (p2[1] - p1[1]) * f)],
                   fill=rgba(colour), width=w, joint="curve")


def load(spec_path, style_path):
    spec = json.load(open(_env.resolve(spec_path, base=_env.workspace()), encoding="utf-8"))
    style = json.load(open(_env.resolve(style_path), encoding="utf-8"))
    if not spec.get("items"):
        sys.exit("%s has no items" % spec_path)
    return spec, style


def render_clip(spec, style, size, fps, out):
    """Every frame of the card into a clip; returns its duration in seconds."""
    card = Checklist(spec, style, size)
    n = int(math.ceil(card.total * fps))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % size, "-r", "%g" % fps,
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "12",
           "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=ENV)
    for i in range(n):
        p.stdin.write(card.frame(i / fps).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait():
        sys.exit("could not write %s" % out)
    return n / fps


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True, help="the words: projects/<id>/cards/*.json")
    ap.add_argument("--style", required=True, help="the look: config/cards/checklist/*.json")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--list", action="store_true", help="print the timeline; draw nothing")
    ap.add_argument("--png", nargs="?", const="end", metavar="T",
                    help="write the frame at card time T (default: the final state)")
    ap.add_argument("--sheet", action="store_true", help="a strip of frames across the animation")
    ap.add_argument("--clip", metavar="OUT", help="render the whole card as a clip")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--out", help="where --png/--sheet write (default temp/cards/)")
    args = ap.parse_args()

    spec, style = load(args.spec, args.style)
    size = tuple(int(v) for v in args.size.lower().split("x"))
    th, ti, tc, total = timeline(spec, style)
    tag = "%s-%s" % (os.path.splitext(os.path.basename(args.spec))[0],
                     os.path.splitext(os.path.basename(args.style))[0])
    outdir = os.path.join(ROOT, "temp", "cards")
    os.makedirs(outdir, exist_ok=True)

    if args.list:
        print("  headline at %.2fs" % th)
        for txt, t in zip(spec["items"], ti):
            print("  %.2fs  [ ] -> [x] at %.2fs   %s" % (t, t + timing(style)["tick_delay"], txt))
        if tc is not None:
            print("  cta at %.2fs   %s" % (tc, spec["cta"]))
        print("  total %.2fs (holds %.1fs on the finished card)" % (total, timing(style)["hold"]))
        return
    card = Checklist(spec, style, size)
    if args.png:
        t = total - 0.01 if args.png == "end" else float(args.png)
        out = args.out or os.path.join(outdir, "%s-%s.png" % (tag, args.png.replace(".", "_")))
        card.frame(t).convert("RGB").save(out)
        print("  %s" % os.path.relpath(out, ROOT))
    if args.sheet:
        times = [th + 0.2] + [t + 0.12 for t in ti] + [total - 0.01]
        frames = [card.frame(t).convert("RGB").resize((480, 270)) for t in times]
        sheet = Image.new("RGB", (480 * len(frames), 270))
        for i, f in enumerate(frames):
            sheet.paste(f, (480 * i, 0))
        out = args.out or os.path.join(outdir, "%s-sheet.png" % tag)
        sheet.save(out)
        print("  %s  (%s)" % (os.path.relpath(out, ROOT), ", ".join("%.2f" % t for t in times)))
    if args.clip:
        d = render_clip(spec, style, size, args.fps, args.clip)
        print("  %s  %.2fs" % (args.clip, d))


if __name__ == "__main__":
    main()
