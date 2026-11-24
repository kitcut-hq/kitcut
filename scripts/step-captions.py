#!/usr/bin/env python
"""Step captions as full-canvas PNGs, in the Mister Blocks grammar.

A product demo told in steps reads best as a few heavy words on a dark card,
low in the frame, with a small kicker pill above it ("- STEP 2") and the words
that matter in the accent colour. Each caption is 2-6 words, set in two even
lines: Mister Blocks stacks a phrase as a block, never as a long line with an
orphan. This draws those cards; image-overlay (an edl-cut `image_overlays`
entry) burns them in at their times.

The spec is data (example: config/launch-kit/step-captions.json):

    {"canvas": [1080, 1920], "outdir": "temp/caps",      # outdir: beside the spec
     "style": {"font": "fonts/Inter-VF.ttf", "font_variation": "ExtraBold",
               "size": 66, "line_h": 80, "bottom": 300, "max_w": 900,
               "balance": true, "one_line_max": 560, "cx": 540, ...},
     "captions": [{"id": "k2", "kicker": "S T E P   2", "text": "Open the *Instafill Agent.*"}],
     "badges": [{"id": "speed", "text": "8x  .  REAL WAIT 50 SEC", "fast_forward": true}]}

Text markup: `*accent words*`, and `|` forces the line break where the phrase
reads best ("Flat PDF?|It makes it *fillable.*") -- the balanced split picks
the evenest widths, which is not always the best sense.

`balance`: a caption wider than `one_line_max` px is split into the two most
even lines; one that fits stays on one line. Without it, greedy wrap at
`max_w`. `cx` centres the card elsewhere than mid-canvas (the empty half of a
16:9 frame beside a phone).

Each PNG carries a 2-alpha pixel in two corners so the overlay keeps the full
canvas and places the card exactly where it is drawn.

  --list   every caption's lines and card width; writes nothing
  (none)   write the PNGs

Invoke as:  python scripts/step-captions.py --spec projects/<id>/captions.json [--list]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import _project  # noqa: E402

DEFAULT_STYLE = {
    "font": "fonts/Inter-VF.ttf",
    "font_variation": "ExtraBold",
    "size": 66,
    "line_h": 80,
    "kicker_font": "fonts/IBMPlexMono-Bold.ttf",
    "kicker_size": 26,
    "pad_x": 40,
    "pad_y": 22,
    "bottom": 300,
    "max_w": 900,
    "radius": 18,
    "shadow": 8,
    "shadow_color": "#000000",
    "card": "#1A1A1A",
    "ink": "#FFFFFF",
    "accent": "#F5A623",
    "balance": True,
    "one_line_max": 560,
}


def hexc(c, a=255):
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4)) + (a,)


def load_font(path, size, variation=None):
    f = ImageFont.truetype(_env.resolve(path), size)
    if variation:  # a variable font (Inter-VF): pick the named instance
        f.set_variation_by_name(variation)
    return f


def words(line):
    """'*accent words*' -> [(word, is_accent)]."""
    out, acc = [], False
    for tok in re.split(r"(\*)", line):
        if tok == "*":
            acc = not acc
            continue
        out += [(w, acc) for w in tok.split()]
    return out


class Cards:
    def __init__(self, spec):
        self.S = dict(DEFAULT_STYLE, **spec.get("style", {}))
        self.W, self.H = spec["canvas"]
        S = self.S
        self.fb = load_font(S["font"], S["size"], S.get("font_variation"))
        self.fk = load_font(S["kicker_font"], S["kicker_size"], S.get("kicker_variation"))

    def width(self, d, ws):
        return d.textlength(" ".join(x for x, _ in ws), font=self.fb)

    def lines(self, d, text):
        if "|" in text:
            return [words(p) for p in text.split("|")]
        ws = words(text)
        S = self.S
        if S.get("balance"):
            if self.width(d, ws) > S["one_line_max"] and len(ws) > 1:
                i = min(
                    range(1, len(ws)),
                    key=lambda i: max(self.width(d, ws[:i]), self.width(d, ws[i:])),
                )
                return [ws[:i], ws[i:]]
            return [ws]
        out, cur = [], []
        for w in ws:
            if cur and self.width(d, [*cur, w]) > S["max_w"]:
                out.append(cur)
                cur = [w]
            else:
                cur.append(w)
        return [*out, cur]

    def caption(self, c):
        S, W, H = self.S, self.W, self.H
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        lines = self.lines(d, c["text"])
        sp = d.textlength(" ", font=self.fb)
        lw = [
            sum(d.textlength(w, font=self.fb) for w, _ in ln) + sp * (len(ln) - 1) for ln in lines
        ]
        cw = int(max(lw)) + 2 * S["pad_x"]
        ch = len(lines) * S["line_h"] + 2 * S["pad_y"]
        cx = S.get("cx", W / 2)
        x0 = int(cx - cw / 2)
        y1 = H - S["bottom"]
        y0 = y1 - ch
        o = S["shadow"]
        d.rounded_rectangle(
            [x0 + o, y0 + o, x0 + cw + o, y1 + o], S["radius"], fill=hexc(S["shadow_color"])
        )
        d.rounded_rectangle([x0, y0, x0 + cw, y1], S["radius"], fill=hexc(S["card"]))
        for i, ln in enumerate(lines):
            x = cx - lw[i] / 2
            y = y0 + S["pad_y"] + i * S["line_h"] + S["line_h"] / 2
            for w, acc in ln:
                d.text(
                    (x, y),
                    w,
                    font=self.fb,
                    fill=hexc(S["accent"] if acc else S["ink"]),
                    anchor="lm",
                )
                x += d.textlength(w, font=self.fb) + sp
        if c.get("kicker"):
            k = c["kicker"]
            kw = d.textlength(k, font=self.fk)
            dash = 22
            pw, ph = kw + dash + 3 * 14, S["kicker_size"] + 20
            kx, ky = cx - pw / 2, y0 - ph - 12
            d.rounded_rectangle(
                [kx + 4, ky + 4, kx + pw + 4, ky + ph + 4], 10, fill=hexc(S["shadow_color"])
            )
            d.rounded_rectangle([kx, ky, kx + pw, ky + ph], 10, fill=hexc(S["card"]))
            d.rectangle(
                [kx + 14, ky + ph / 2 - 4, kx + 14 + dash, ky + ph / 2 + 4], fill=hexc(S["accent"])
            )
            d.text(
                (kx + 28 + dash, ky + ph / 2 + 1),
                k,
                font=self.fk,
                fill=hexc(S["accent"]),
                anchor="lm",
            )
        return self.pin(im), [" ".join(w for w, _ in ln) for ln in lines], cw

    def badge(self, b):
        S, W, H = self.S, self.W, self.H
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        f = load_font(S["kicker_font"], b.get("size", 28), S.get("kicker_variation"))
        tw = d.textlength(b["text"], font=f)
        ff = 44 if b.get("fast_forward") else 0  # two drawn triangles: the mono font has no glyph
        pw, ph = tw + 40 + ff, b.get("size", 28) + 24
        x, y = W - pw - b.get("right", 40), b.get("top", 40)
        d.rounded_rectangle(
            [x + 4, y + 4, x + pw + 4, y + ph + 4], 10, fill=hexc(S["shadow_color"])
        )
        d.rounded_rectangle([x, y, x + pw, y + ph], 10, fill=hexc(S["accent"]))
        if ff:
            cy, th = y + ph / 2, 9
            for dx in (20, 38):
                d.polygon(
                    [(x + dx, cy - th), (x + dx + 16, cy), (x + dx, cy + th)], fill=hexc(S["card"])
                )
        d.text((x + 20 + ff, y + ph / 2 + 1), b["text"], font=f, fill=hexc(S["card"]), anchor="lm")
        return self.pin(im)

    def pin(self, im):
        im.putpixel((0, 0), (0, 0, 0, 2))
        im.putpixel((self.W - 1, self.H - 1), (0, 0, 0, 2))
        return im


def main():
    ap = argparse.ArgumentParser(description="Step captions as full-canvas PNGs.")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--list", action="store_true", help="print lines and widths; write nothing")
    args = ap.parse_args()
    sp = _env.resolve(args.spec, base=_env.workspace())
    with open(sp, encoding="utf-8") as f:
        spec = json.load(f)
    cards = Cards(spec)
    out = os.path.join(os.path.dirname(sp), spec["outdir"])
    if not args.list:
        os.makedirs(out, exist_ok=True)
    for c in spec["captions"]:
        im, lines, cw = cards.caption(c)
        if args.list:
            print("  %-6s %4d px  %s" % (c["id"], cw, "  /  ".join(lines)))
        else:
            im.save(os.path.join(out, c["id"] + ".png"))
    for b in spec.get("badges", []):
        if not args.list:
            cards.badge(b).save(os.path.join(out, b["id"] + ".png"))
    if args.list:
        return
    print("  %d captions -> %s" % (len(spec["captions"]), out))
    d = _project.find_project_dir(sp)
    if d:
        _project.record(
            os.path.basename(d),
            "step captions: %d cards from %s" % (len(spec["captions"]), os.path.basename(sp)),
            script=__file__,
        )


if __name__ == "__main__":
    main()
