#!/usr/bin/env python
"""Burn an animated social-handle badge into a video.

The badge is a camera glyph above an @handle. It hops between anchor points on
a timer and alternates between a flat glyph and a gradient one -- the moving
target that makes a clip harder to strip and re-upload without attribution.

Two halves, and the split is the point:

  * the badge is drawn once per colour variant into a PNG, by Pillow, where
    fonts, gradients and outlines are easy;
  * the animation is an ffmpeg overlay whose x/y and enable are expressions in
    `t`, so the whole thing is one filter pass with no per-frame Python.

That means it costs a single re-encode and composes with any other filter --
`cut-clips.py` applies it while cutting, so a clip is never encoded twice.

Everything visual lives in a preset under `config/handles/`. Values are authored
on the preset's canvas and scaled to the real video, so 720p / 1080p / vertical
all land in the same place.

Invoke as:  python scripts/handle-overlay.py --video in.mp4 --handle @name
"""
import sys, os, json, math, argparse, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import



from PIL import Image, ImageDraw, ImageFont

ENV = _env.ENV

DEFAULT_PRESET = "config/handles/default.json"


# ---------------------------------------------------------------- drawing


def hex_rgba(h, alpha=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def font_for_cap_height(path, cap_px):
    """Pick the nominal size whose CAP height measures cap_px.

    Sizing by cap height rather than nominal size is the only way two different
    typefaces land the same optical size -- nominal size includes ascent and
    descent, which vary wildly. Same reason the caption presets do it.
    """
    lo, hi = 4, max(16, int(cap_px * 8))
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(path, mid)
        box = f.getbbox("H")          # (x0, y0, x1, y1) of the glyph ink
        h = box[3] - box[1]
        if h == cap_px:
            return f
        if h < cap_px:
            best = f
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ImageFont.truetype(path, max(4, int(cap_px)))


def draw_text_tracked(draw, xy, text, font, fill, tracking, stroke, stroke_fill):
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


def gradient_image(size, colours, angle_deg):
    """Linear multi-stop gradient, evaluated per pixel along the angle."""
    w, h = size
    img = Image.new("RGBA", size)
    px = img.load()
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    # project every corner to normalise the ramp over the whole box
    projs = [x * dx + y * dy for x in (0, w - 1) for y in (0, h - 1)]
    lo, hi = min(projs), max(projs)
    span = (hi - lo) or 1.0
    stops = [hex_rgba(c) for c in colours]
    n = len(stops) - 1
    for y in range(h):
        for x in range(w):
            u = ((x * dx + y * dy) - lo) / span
            f = u * n
            i = min(int(f), n - 1)
            k = f - i
            c0, c1 = stops[i], stops[i + 1]
            px[x, y] = (int(c0[0] + (c1[0] - c0[0]) * k),
                        int(c0[1] + (c1[1] - c0[1]) * k),
                        int(c0[2] + (c1[2] - c0[2]) * k), 255)
    return img


def glyph_mask(size, stroke, radius):
    """A camera mark: rounded square, lens circle, viewfinder dot.

    Returned as an L mask so the same shape can be filled flat or with a
    gradient -- Pillow can paste through a mask, and ASS could not do gradients
    at all, which is why the badge is a PNG and not a subtitle line.
    """
    ss = 4                                   # supersample: crisp curves at any size
    S = size * ss
    w = max(1, int(round(stroke * ss)))
    r = radius * ss
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    half = w / 2.0
    d.rounded_rectangle([half, half, S - 1 - half, S - 1 - half],
                        radius=r, outline=255, width=w)
    lens = S * 0.235
    cx = cy = S / 2.0
    d.ellipse([cx - lens, cy - lens, cx + lens, cy + lens], outline=255, width=w)
    dot = S * 0.062
    dx, dy = S * 0.745, S * 0.255
    d.ellipse([dx - dot, dy - dot, dx + dot, dy + dot], fill=255)
    return m.resize((size, size), Image.LANCZOS)


def render_icon(cfg, scale, variant):
    size = max(8, int(round(cfg["size_px"] * scale)))
    stroke = max(1.0, cfg["stroke_px"] * scale)
    radius = cfg["corner_radius_px"] * scale
    out_px = int(round(cfg.get("outline_px", 0) * scale))

    mask = glyph_mask(size, stroke, radius)
    if variant == "gradient":
        fill = gradient_image((size, size), cfg["gradient"],
                              cfg.get("gradient_angle_deg", 45))
    else:
        fill = Image.new("RGBA", (size, size), hex_rgba(cfg["colour"]))

    pad = out_px * 2 + 2
    img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    if out_px > 0:
        # Dark halo so a white glyph survives a white shirt or a bright sky.
        # Built by stamping the mask around a circle rather than by dilating --
        # a circular stamp keeps the corner radius from going square.
        halo = Image.new("L", img.size, 0)
        steps = max(8, out_px * 8)
        for i in range(steps):
            th = 2 * math.pi * i / steps
            ox = int(round(math.cos(th) * out_px))
            oy = int(round(math.sin(th) * out_px))
            halo.paste(mask, (pad + ox, pad + oy), mask)
        img.paste(Image.new("RGBA", img.size, hex_rgba(cfg["outline_colour"])),
                  (0, 0), halo)
    img.paste(fill, (pad, pad), mask)
    return img


def render_badge(preset, handle, scale, variant):
    fcfg, tcfg, icfg = preset["font"], preset["text"], preset["icon"]
    text = handle.upper() if fcfg.get("uppercase", True) else handle
    font = font_for_cap_height(fcfg["file"], max(4, int(round(fcfg["cap_height_px"] * scale))))
    tracking = fcfg.get("tracking_px", 0) * scale
    t_stroke = int(round(tcfg.get("outline_px", 0) * scale))

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = text_width_tracked(probe, text, font, tracking)
    asc, desc = font.getmetrics()
    th = asc + desc

    icon = render_icon(icfg, scale, variant)
    gap = int(round(icfg.get("gap_px", 0) * scale))

    pad = t_stroke + 2
    w = int(math.ceil(max(icon.width, tw + 2 * pad)))
    h = icon.height + gap + int(math.ceil(th + 2 * pad))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(icon, ((w - icon.width) // 2, 0), icon)

    d = ImageDraw.Draw(img)
    draw_text_tracked(d, ((w - tw) / 2.0, icon.height + gap + pad), text, font,
                      hex_rgba(tcfg["colour"]), tracking,
                      t_stroke, hex_rgba(tcfg["outline_colour"]))
    return img


# ---------------------------------------------------------------- animation


def esc(expr):
    """ffmpeg splits filter options on commas, so commas inside an expression
    have to be escaped. Doing it here means callers write normal expressions."""
    return expr.replace(",", r"\,")


def pick(index_expr, values):
    """Nested if() choosing among constants by an integer expression."""
    out = "%g" % values[-1]
    for i in range(len(values) - 2, -1, -1):
        out = "if(eq(%s,%d),%g,%s)" % (index_expr, i, values[i], out)
    return out


def prepare(preset_path, handle, vid_w, vid_h, tmpdir, tag="", base="0:v"):
    """Render the badge variants and build the filter graph that animates them.

    Returns (png_paths, filter_complex, out_label). The caller adds each png as
    an ffmpeg input, in order, immediately after the video. `base` is the label
    the badge composites onto, so a caller that crops or burns subtitles first
    can hand in the tail of its own chain and keep everything to one pass.

    vid_w/vid_h are the dimensions of THAT label, not of the source file --
    a vertical crop changes both, and the badge scales to what it lands on.
    """
    preset = json.load(open(preset_path, encoding="utf-8"))
    canvas = preset.get("canvas", {"width": 1920, "height": 1080})
    scale = vid_w / float(canvas["width"])
    m = preset["motion"]
    variants = list(m.get("colour_cycle", ["flat"]))

    os.makedirs(tmpdir, exist_ok=True)
    pngs, sizes = [], []
    for v in variants:
        img = render_badge(preset, handle, scale, v)
        p = os.path.join(tmpdir, "handle%s-%s.png" % (tag, v))
        img.save(p)
        pngs.append(p)
        sizes.append(img.size)

    # every variant is the same badge in a different colour, so one geometry
    bw, bh = max(s[0] for s in sizes), max(s[1] for s in sizes)
    sy = vid_h / float(canvas.get("height", 1080))
    xs, ys = [], []
    for cx, cy in m["positions"]:
        x = cx * scale - bw / 2.0
        y = cy * sy - bh / 2.0
        xs.append(round(min(max(x, 0), max(0, vid_w - bw))))
        ys.append(round(min(max(y, 0), max(0, vid_h - bh))))

    start = int(m.get("start_index", 0))
    if start:
        xs = xs[start:] + xs[:start]
        ys = ys[start:] + ys[:start]

    pos_i = "mod(floor(t/%g),%d)" % (float(m.get("move_every_s", 7.0)), len(xs))
    x_expr, y_expr = pick(pos_i, xs), pick(pos_i, ys)
    col_i = "mod(floor(t/%g),%d)" % (float(m.get("colour_every_s", 4.5)), len(variants))

    alpha = float(m.get("opacity", 1.0))
    parts, cur = [], base
    for i, _ in enumerate(variants):
        parts.append("[%d:v]format=rgba,colorchannelmixer=aa=%g[hb%d]" % (i + 1, alpha, i))
    for i, _ in enumerate(variants):
        nxt = "hv%d" % i
        enable = "1" if len(variants) == 1 else "eq(%s,%d)" % (col_i, i)
        parts.append("[%s][hb%d]overlay=x=%s:y=%s:format=auto:enable=%s[%s]"
                     % (cur, i, esc(x_expr), esc(y_expr), esc(enable), nxt))
        cur = nxt
    return pngs, ";".join(parts), cur


def probe_dims(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "json", path],
                         env=ENV, capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s\n%s" % (path, out.stderr.strip()))
    s = json.loads(out.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="input video (omit with --badges-only)")
    ap.add_argument("--out", help="output video; default <input>-handle.mp4")
    ap.add_argument("--handle", required=True, help="e.g. @kris_zahrebelna")
    ap.add_argument("--preset", default=DEFAULT_PRESET)
    ap.add_argument("--tmp", default="temp")
    ap.add_argument("--badges-only", action="store_true",
                    help="render the badge PNGs and stop, to eyeball the style")
    ap.add_argument("--width", type=int, default=1920, help="with --badges-only")
    ap.add_argument("--height", type=int, default=1080, help="with --badges-only")
    ap.add_argument("--cq", default="21")
    ap.add_argument("--encoder", default="h264_nvenc")
    args = ap.parse_args()

    if args.badges_only:
        pngs, _, _ = prepare(args.preset, args.handle, args.width, args.height, args.tmp)
        for p in pngs:
            print("%s  %dx%d" % (p, *Image.open(p).size))
        return

    if not args.video:
        sys.exit("--video is required")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    w, h = probe_dims(args.video)
    pngs, fc, label = prepare(args.preset, args.handle, w, h, args.tmp)
    out = args.out or os.path.splitext(args.video)[0] + "-handle.mp4"

    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-i", args.video]
    for p in pngs:
        cmd += ["-i", p]
    cmd += ["-filter_complex", fc, "-map", "[%s]" % label, "-map", "0:a:0?",
            "-c:v", args.encoder, "-preset", "p5", "-rc", "vbr", "-cq", str(args.cq),
            "-b:v", "0", "-maxrate", "16M", "-bufsize", "32M", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-y", out]
    if subprocess.run(cmd, env=ENV).returncode:
        sys.exit("ffmpeg failed for %s" % out)
    print("%s  %.1f MB" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
