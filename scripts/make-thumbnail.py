#!/usr/bin/env python
"""A YouTube thumbnail (1280x720) in the channel's house style, from a spec.

The Instafill channel's thumbnails share one grammar, read off the last six
public uploads: a dark navy/purple field, a heavy condensed headline in white
with ONE phrase on a yellow slab, the form itself on the right -- tilted, with
a drop shadow -- a yellow time badge on the form, a yellow caption strip under
it, and the logo top-left. This draws that grammar; the words, the picture and
the colours are data.

html-to-image.py is not used because it exists for overlays and refuses an
opaque page, and a thumbnail is nothing but opaque.

Spec (projects/<id>/thumbnail.json):
  headline   [{"text": "...", "slab": false}, ...]   one line each; slab=true
             draws that line in dark ink on the accent slab
  sub        a smaller pill under the headline (optional)
  image      a frame grab; `crop` [x, y, w, h] in pixels of that image
  badge      short text for the round badge on the image ("1:50")
  strip      the caption strip under the image
  logo       a PNG; its dark lettering is re-inked white for the dark field
  top        y of the logo, to centre a short left column (default 44)
  colours    bg_top, bg_bottom, accent, ink, pill (all optional)

  --list     print the layout boxes and flag any headline line that had to
             shrink to fit; draws nothing
  (none)     write the PNG (default <spec>.png); YouTube's limit is 2 MB, and
             the file is checked against it

Invoke as:  python scripts/make-thumbnail.py --spec projects/<id>/thumbnail.json
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
import _overlay  # noqa: E402

W, H = 1280, 720
DEFAULT_COLOURS = {"bg_top": "#2B1570", "bg_bottom": "#120A33", "accent": "#FFB81C",
                   "ink": "#FFFFFF", "slab_ink": "#111111", "pill": "#5B3FD1"}
HEAD_FONT = "fonts/Anton-Regular.ttf"
BODY_FONT = "fonts/Montserrat-Bold.ttf"
LIMIT = 2 * 1024 * 1024


def rgba(h, a=255):
    return _overlay.hex_rgba(h, a)


def font(path, size):
    return ImageFont.truetype(_env.resolve(path), size)


def background(c):
    """A vertical gradient with a soft light in the upper left, like the channel's."""
    top, bot = rgba(c["bg_top"]), rgba(c["bg_bottom"])
    bg = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        u = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * u) for i in range(3)) + (255,))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([-300, -300, 700, 500], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg = Image.composite(Image.new("RGBA", (W, H), (120, 90, 255, 255)), bg, glow)
    return bg


def logo_white(path, height):
    """The logo, with its dark lettering re-inked white; the avatar keeps its colours.

    Only pixels that are dark AND grey become white -- the mark's portrait has
    dark hair on a saturated yellow tile, and a plain 'dark -> white' swap
    turned her hair white.
    """
    im = Image.open(_env.resolve(path)).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) < 110 and max(r, g, b) - min(r, g, b) < 40 and x > im.height * 0.85:
                px[x, y] = (255, 255, 255, a)
    return im.resize((int(im.width * height / im.height), height), Image.LANCZOS)


def fit_font(path, text, max_w, size, min_size=40):
    """The largest size up to `size` at which `text` fits `max_w`; (font, shrunk?)."""
    d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    s = size
    while s > min_size and d.textlength(text, font=font(path, s)) > max_w:
        s -= 2
    return font(path, s), s < size


def draw(spec, base_dir, report=False):
    c = dict(DEFAULT_COLOURS, **(spec.get("colours") or {}))
    im = background(c)
    d = ImageDraw.Draw(im)
    notes = []

    # -- the picture, right, tilted, shadowed ---------------------------------
    src = Image.open(_env.resolve(spec["image"], base=base_dir)).convert("RGBA")
    if spec.get("crop"):
        x, y, w, h = spec["crop"]
        src = src.crop((x, y, x + w, y + h))
    pw = int(spec.get("image_width", 640))
    src = src.resize((pw, int(src.height * pw / src.width)), Image.LANCZOS)
    card = Image.new("RGBA", (src.width + 16, src.height + 16), (255, 255, 255, 255))
    card.paste(src, (8, 8))
    tilt = float(spec.get("tilt", -4))
    rot = card.rotate(tilt, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), mask=rot.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    cx = W - rot.width - int(spec.get("image_right", 28))
    cy = (H - rot.height) // 2 + int(spec.get("image_dy", 0))
    im.alpha_composite(shadow, (cx + 10, cy + 18))
    im.alpha_composite(rot, (cx, cy))

    # -- the badge, top-right of the picture ---------------------------------
    if spec.get("badge"):
        r = 74
        bx, by = cx + rot.width - r - 6, cy - r // 2 + 4
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=rgba(c["accent"]),
                  outline=rgba(c["bg_bottom"]), width=6)
        f = font(HEAD_FONT, 62)
        tw = d.textlength(spec["badge"], font=f)
        d.text((bx - tw / 2, by - 44), spec["badge"], font=f, fill=rgba(c["slab_ink"]))
        if spec.get("badge_sub"):
            f2 = font(BODY_FONT, 19)
            tw = d.textlength(spec["badge_sub"], font=f2)
            d.text((bx - tw / 2, by + 22), spec["badge_sub"], font=f2, fill=rgba(c["slab_ink"]))

    # -- the strip, over the bottom edge of the picture ----------------------
    if spec.get("strip"):
        f = font(BODY_FONT, 26)
        tw = d.textlength(spec["strip"], font=f)
        sx1 = cx + rot.width - 20
        sx0 = sx1 - tw - 44
        sy1 = cy + rot.height - 6
        sy0 = sy1 - 52
        strip = Image.new("RGBA", (int(sx1 - sx0), int(sy1 - sy0)), rgba(c["accent"]))
        ImageDraw.Draw(strip).text((22, 9), spec["strip"], font=f, fill=rgba(c["slab_ink"]))
        strip = strip.rotate(-2, resample=Image.BICUBIC, expand=True)
        im.alpha_composite(strip, (int(sx0), int(sy0)))

    # -- logo ------------------------------------------------------------------
    left = 56
    y = int(spec.get("top", 44))   # lower it to centre a short left column
    if spec.get("logo"):
        lg = logo_white(spec["logo"], int(spec.get("logo_height", 56)))
        im.alpha_composite(lg, (left, y))
        y += lg.height + 34

    # -- headline -------------------------------------------------------------
    max_w = cx - left - 20
    for line in spec["headline"]:
        size = int(line.get("size", 104))
        f, shrunk = fit_font(HEAD_FONT, line["text"], max_w - (40 if line.get("slab") else 0), size)
        if shrunk:
            notes.append("headline %r shrank from %d to fit %d px" % (line["text"], size, max_w))
        # Space by the INK, not the font metrics: Anton's ascent is far taller
        # than its capitals, and metric spacing ran four lines off the frame.
        top, bottom = f.getbbox(line["text"])[1], f.getbbox(line["text"])[3]
        cap = bottom - top
        tw = d.textlength(line["text"], font=f)
        if line.get("slab"):
            pad = 18
            slab = Image.new("RGBA", (int(tw + 2 * pad), cap + 2 * pad), rgba(c["accent"]))
            ImageDraw.Draw(slab).text((pad, pad - top), line["text"], font=f, fill=rgba(c["slab_ink"]))
            slab = slab.rotate(float(line.get("tilt", -2)), resample=Image.BICUBIC, expand=True)
            im.alpha_composite(slab, (left - 8, int(y) - 4))
            y += slab.height + 14
        else:
            d.text((left, y - top), line["text"], font=f, fill=rgba(line.get("colour", c["ink"])))
            y += cap + 22

    if spec.get("sub"):
        f = font(BODY_FONT, 30)
        tw = d.textlength(spec["sub"], font=f)
        y += 14
        d.rounded_rectangle([left, y, left + tw + 48, y + 58], radius=29, fill=rgba(c["pill"]))
        d.text((left + 24, y + 11), spec["sub"], font=f, fill=rgba(c["ink"]))
        y += 58
    if y > H - 30:
        notes.append("the left column runs to y=%d, past the frame" % y)
    if report:
        print("  picture box x %d-%d, y %d-%d; headline column width %d; text ends y=%d"
              % (cx, cx + rot.width, cy, cy + rot.height, max_w, y))
        for n in notes:
            print("  note:", n)
    return im.convert("RGB"), notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out")
    ap.add_argument("--list", action="store_true", help="print the layout; write nothing")
    args = ap.parse_args()
    spath = _env.resolve(args.spec, base=_env.workspace())
    spec = json.load(open(spath, encoding="utf-8"))
    im, notes = draw(spec, _env.workspace(), report=True)
    if args.list:
        return
    out = args.out or os.path.splitext(spath)[0] + ".png"
    im.save(out, optimize=True)
    size = os.path.getsize(out)
    if size > LIMIT:
        im.save(os.path.splitext(out)[0] + ".jpg", quality=90)
        sys.exit("%s is %.1f MB, over YouTube's 2 MB limit; wrote a JPEG beside it"
                 % (out, size / 1e6))
    print("  %s  %dx%d  %.0f KB" % (os.path.relpath(out, _env.ROOT), W, H, size / 1024))


if __name__ == "__main__":
    main()
