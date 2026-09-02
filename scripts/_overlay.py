#!/usr/bin/env python
"""Drawing and filter-graph helpers shared by everything that burns a graphic in.

Two scripts composite a Pillow-drawn PNG onto video through an ffmpeg
`overlay` — `handle-overlay.py` (the animated social badge) and
`name-label.py` (the lower third). They were written apart and grew the same
five helpers twice; this is the one copy.

Both follow the same shape, and it is worth stating because the next overlay
should follow it too:

  * Pillow draws the graphic once into a PNG, where fonts, gradients, rounded
    corners and outlines are easy and cost nothing per frame.
  * ffmpeg animates that PNG with expressions in `t` — `overlay`'s x/y/enable,
    or a `fade` on its alpha.

So the motion costs one filter pass and no per-frame Python, and it composes:
each module exposes `prepare()` returning (png_paths, filter_complex,
out_label), which a caller splices onto the tail of its own chain to keep the
whole render to a single encode.
"""
import os, sys, json, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import ImageFont

ENV = _env.ENV
ROOT = _env.ROOT


def hex_rgba(h, alpha=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def repo_path(path):
    """Preset paths are repo-relative so a preset is portable between machines."""
    return _env.resolve(path)


def font_for_cap_height(path, cap_px):
    """Pick the nominal size whose CAP height measures cap_px.

    Sizing by cap height rather than nominal size is the only way two typefaces
    -- or two weights of one -- land at the same optical size. Nominal size
    includes ascent and descent, which vary wildly between faces, so sizing by
    it sets a ratio nobody chose. The caption presets size the same way.
    """
    lo, hi = 4, max(16, int(cap_px * 8))
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(repo_path(path), mid)
        box = f.getbbox("H")          # (x0, y0, x1, y1) of the glyph ink
        h = box[3] - box[1]
        if h == cap_px:
            return f
        if h < cap_px:
            best = f
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ImageFont.truetype(repo_path(path), max(4, int(cap_px)))


def draw_text_tracked(draw, xy, text, font, fill, tracking,
                      stroke=0, stroke_fill=None):
    """Pillow has no letter-spacing, so place glyph by glyph."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)
        x += draw.textlength(ch, font=font) + tracking
    return x - tracking - xy[0]


def text_width_tracked(draw, text, font, tracking):
    if not text:
        return 0.0
    return sum(draw.textlength(c, font=font) for c in text) + tracking * (len(text) - 1)


def esc(expr):
    """ffmpeg splits filter options on commas, so commas inside an expression
    have to be escaped. Doing it here means callers write normal expressions."""
    return expr.replace(",", r"\,")


def anchor_xy(layout, cw, ch, vid_w, vid_h, scale, sy):
    """Place a graphic from a named corner, clamped into the frame.

    `corner` is top/bottom crossed with left/right -- anything else centres on
    that axis, so "centre" centres both. Margins are authored on the preset's
    canvas and scaled: `scale` horizontally, `sy` vertically, because a 9:16
    crop of a 16:9 canvas stretches the two differently and a margin that
    followed the width alone would drift off the bottom of a vertical frame.
    """
    corner = layout.get("corner", "bottom-left")
    mx = layout.get("margin_x_px", 96) * scale
    my = layout.get("margin_y_px", 120) * sy

    if "left" in corner:
        x = mx
    elif "right" in corner:
        x = vid_w - cw - mx
    else:
        x = (vid_w - cw) / 2.0
    if "top" in corner:
        y = my
    elif "bottom" in corner:
        y = vid_h - ch - my
    else:
        y = (vid_h - ch) / 2.0
    return (int(round(min(max(x, 0), max(0, vid_w - cw)))),
            int(round(min(max(y, 0), max(0, vid_h - ch)))))


def probe_dims(path):
    w, h, _, _ = probe(path)
    return w, h


def probe(path):
    """(width, height, fps, duration) for a video, straight from ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height,r_frame_rate"
                          ":format=duration", "-of", "json", path],
                         env=ENV, capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s\n%s" % (path, out.stderr.strip()))
    j = json.loads(out.stdout)
    s = j["streams"][0]
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1)
    dur = float(j.get("format", {}).get("duration") or 0.0)
    return int(s["width"]), int(s["height"]), fps, dur


