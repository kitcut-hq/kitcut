#!/usr/bin/env python
"""Burn a broadcast lower-third name label into a video.

A dark rounded card with the person's name over their title, and a mint
rounded rectangle sitting a few pixels down-right of it so an accent sliver
shows along the bottom and right edges. It fades up, holds, and fades out.

Measured, not invented: every default in `config/labels/lower-third.json` was
read off x.com/RiskReversal/status/2092685768833605757 at t=9.0 by diffing the
frame against t=10.6 (the label's own fade-out) to isolate its pixels, then
classifying them. That frame is 1280x720, so each number was scaled by 1.5 onto
the 1920x1080 canvas the presets are authored on. `_measured` in the preset
keeps the raw 720p readings next to the scaled ones.

Drawn by Pillow into a PNG, animated by an ffmpeg `fade` on that PNG's alpha
plus an `overlay` gated by `enable` -- the split `_overlay.py` describes, which
this shares with the handle badge. One filter pass, no per-frame Python.

That means it composes: `screencast-cut.py` hands `prepare()` the tail of its
own chain and the label lands inside the film's single NVENC pass, so a labelled
film is not a re-encode of an unlabelled one.

Invoke as:  python scripts/name-label.py --video in.mp4 --name "..." --title "..."
"""

import sys
import os
import json
import argparse
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen

from PIL import Image, ImageDraw
import _overlay
from _overlay import (
    hex_rgba,
    font_for_cap_height,
    draw_text_tracked,
    text_width_tracked,
    esc,
    probe,
    anchor_xy,
)

ENV = _env.ENV
ROOT = _overlay.ROOT

DEFAULT_PRESET = "config/labels/lower-third.json"

# Supersample factor for the card shapes. Rounded corners drawn at 1x and then
# left alone show their stair steps against a moving background; drawn at 4x
# and resampled down they read as curves. Same trick as the handle badge's mask.
SS = 4


# ---------------------------------------------------------------- drawing


def _line_cfg(preset, key):
    """A line's style, with the preset's `lines.common` block underneath it."""
    lines = preset["lines"]
    cfg = dict(lines.get("common", {}))
    cfg.update(lines[key])
    return cfg


def measure(preset, texts, scale):
    """Card geometry for this text at this scale, before anything is drawn.

    Returned separately from render() because the auto-fit loop needs the width
    of a candidate scale without paying to rasterise it.
    """
    pen = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    card = preset["card"]
    pad_x = card["pad_x_px"] * scale
    pad_y = card["pad_y_px"] * scale
    gap = card["line_gap_px"] * scale

    rows = []
    for key, text in texts:
        if not text:
            continue
        c = _line_cfg(preset, key)
        if c.get("uppercase"):
            text = text.upper()
        f = font_for_cap_height(
            _overlay.repo_path(c["file"]), max(4, int(round(c["cap_height_px"] * scale)))
        )
        tracking = c.get("tracking_px", 0) * scale
        w = text_width_tracked(pen, text, f, tracking)
        cap = f.getbbox("H")
        asc, desc = f.getmetrics()
        rows.append(
            {
                "key": key,
                "text": text,
                "font": f,
                "tracking": tracking,
                "w": w,
                "cap_top": cap[1],
                "cap_h": cap[3] - cap[1],
                "desc": desc,
                "colour": c["colour"],
            }
        )

    if not rows:
        raise SystemExit("name-label: nothing to draw -- give at least a name")

    # Height is stacked on the INK, not on the font box: cap height for each
    # line, plus a descender allowance for the last one. Font boxes carry the
    # tallest accent and the deepest tail in the whole typeface, which would
    # pad this card differently for every string put in it.
    ink = sum(r["cap_h"] for r in rows) + gap * (len(rows) - 1) + rows[-1]["desc"]
    return {
        "rows": rows,
        "w": max(r["w"] for r in rows) + 2 * pad_x,
        "h": ink + 2 * pad_y,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "gap": gap,
    }


def render_card(preset, texts, scale):
    """Draw the accent rectangle, the card on top of it, then the two lines."""
    card = preset["card"]
    acc = preset["accent"]
    g = measure(preset, texts, scale)

    cw, chh = int(round(g["w"])), int(round(g["h"]))
    dx = int(round(acc.get("offset_x_px", 0) * scale))
    dy = int(round(acc.get("offset_y_px", 0) * scale))
    radius = card["corner_radius_px"] * scale

    img = Image.new("RGBA", (cw + max(0, dx), chh + max(0, dy)), (0, 0, 0, 0))

    # The accent is a whole rounded rectangle offset behind the card, not a
    # stroke along two edges: that is what puts a rounded corner on the sliver
    # at bottom-right and lets it taper out at top-right and bottom-left,
    # which is what the reference does.
    if acc.get("enabled", True) and (dx or dy):
        acc_layer = Image.new("RGBA", (cw * SS, chh * SS), (0, 0, 0, 0))
        ImageDraw.Draw(acc_layer).rounded_rectangle(
            [0, 0, cw * SS - 1, chh * SS - 1],
            radius=radius * SS,
            fill=hex_rgba(acc["colour"], int(round(255 * acc.get("alpha", 1.0)))),
        )
        img.alpha_composite(acc_layer.resize((cw, chh), Image.LANCZOS), (max(0, dx), max(0, dy)))

    card_layer = Image.new("RGBA", (cw * SS, chh * SS), (0, 0, 0, 0))
    ImageDraw.Draw(card_layer).rounded_rectangle(
        [0, 0, cw * SS - 1, chh * SS - 1],
        radius=radius * SS,
        fill=hex_rgba(card["colour"], int(round(255 * card.get("alpha", 1.0)))),
    )
    img.alpha_composite(card_layer.resize((cw, chh), Image.LANCZOS), (max(0, -dx), max(0, -dy)))

    d = ImageDraw.Draw(img)
    x0, y0 = max(0, -dx), max(0, -dy)
    y = y0 + g["pad_y"]
    for i, r in enumerate(g["rows"]):
        # Draw from the cap top: PIL anchors text at the font box top, and the
        # gap between that and the cap differs per weight, so subtracting
        # cap_top is what makes the two lines sit on the spacing we measured.
        draw_text_tracked(
            d,
            (x0 + (g["w"] - r["w"]) / 2.0, y - r["cap_top"]),
            r["text"],
            r["font"],
            hex_rgba(r["colour"]),
            r["tracking"],
        )
        y += r["cap_h"] + (g["gap"] if i < len(g["rows"]) - 1 else 0)
    return img


def render_label(preset, spec, scale, max_w=None):
    """Render one label, shrinking the type if it would outgrow max_w.

    A name long enough to run off the frame is the failure this catches. It is
    reported rather than silently absorbed, because a card that quietly shrank
    to 70% next to one that did not is a style bug nobody sees until it ships.
    """
    texts = [("name", spec.get("name", "")), ("title", spec.get("title", ""))]
    s = scale
    if max_w:
        for _ in range(24):
            if measure(preset, texts, s)["w"] <= max_w:
                break
            s *= 0.97
        if s < scale:
            sys.stderr.write(
                "  note: %r shrunk to %.0f%% to fit %dpx\n"
                % (spec.get("name", ""), 100 * s / scale, max_w)
            )
    return render_card(preset, texts, s)


# ---------------------------------------------------------------- animation


# anchor_xy now lives in _overlay.py -- the image overlay is its third caller,
# and corner placement was never specific to the name card.


def prepare(preset_path, specs, vid_w, vid_h, tmpdir, tag="", base="0:v", first_input=1):
    """Render each label's PNG and build the filter graph that animates them.

    Returns (png_paths, filter_complex, out_label). The caller adds each png as
    an ffmpeg input -- `-loop 1 -framerate <fps>`, in order, starting at input
    index `first_input`. `base` is the label the cards composite onto, so a
    caller that has already cut, composited and concatenated hands in the tail
    of its own chain and the whole film still costs one pass.

    vid_w/vid_h are the dimensions of THAT label, not of the source file.
    """
    preset = json.load(open(_overlay.repo_path(preset_path), encoding="utf-8"))
    canvas = preset.get("canvas", {"width": 1920, "height": 1080})
    scale = vid_w / float(canvas["width"])
    sy = vid_h / float(canvas.get("height", 1080))
    layout = preset.get("layout", {})
    anim = preset.get("animation", {})
    max_w = layout.get("max_width_px")
    max_w = int(round(max_w * scale)) if max_w else None

    os.makedirs(tmpdir, exist_ok=True)
    pngs, parts, cur = [], [], base
    for i, spec in enumerate(specs):
        img = render_label(preset, spec, scale, max_w)
        p = os.path.join(tmpdir, "namelabel%s-%d.png" % (tag, i))
        img.save(p)
        pngs.append(p)

        lay = dict(layout)
        lay.update(spec.get("layout", {}))
        x, y = anchor_xy(lay, img.width, img.height, vid_w, vid_h, scale, sy)

        at = float(spec["at"])
        dur = float(spec.get("dur", anim.get("hold_s", 5.5)))
        fin = float(spec.get("fade_in_s", anim.get("fade_in_s", 0.4)))
        fout = float(spec.get("fade_out_s", anim.get("fade_out_s", 0.35)))
        end = at + dur

        # The card's alpha is faded on the IMAGE stream, whose own pts start at
        # zero and advance at the output frame rate, so `st=` is film time --
        # the same clock the caller thinks in. Gating the overlay with `enable`
        # as well keeps the composite out of the graph entirely for the rest of
        # the film, which is nearly all of it.
        src = "%d:v" % (first_input + i)
        parts.append(
            "[%s]format=rgba,fade=t=in:st=%.3f:d=%.3f:alpha=1,"
            "fade=t=out:st=%.3f:d=%.3f:alpha=1[nl%s%d]"
            % (src, at, fin, max(at, end - fout), fout, tag, i)
        )
        nxt = "nlv%s%d" % (tag, i)
        # shortest=1 is not optional: these are -loop 1 image inputs and so are
        # INFINITE. Without it the overlay never sees its second input end, the
        # render never finishes, and the file it leaves behind has no moov atom.
        parts.append(
            "[%s][nl%s%d]overlay=x=%d:y=%d:format=auto:shortest=1"
            ":enable=%s[%s]" % (cur, tag, i, x, y, esc("between(t,%.3f,%.3f)" % (at, end)), nxt)
        )
        cur = nxt
    return pngs, ";".join(parts), cur


# ---------------------------------------------------------------- cli


def load_specs(args):
    if args.labels:
        specs = json.load(open(_overlay.repo_path(args.labels), encoding="utf-8"))
        if isinstance(specs, dict):
            specs = specs.get("labels", [])
        return specs
    if not args.name:
        sys.exit("give --name (and usually --title), or --labels <json>")
    return [{"name": args.name, "title": args.title or "", "at": args.at, "dur": args.dur}]


def main():
    ap = argparse.ArgumentParser(description="Burn a lower-third name label into a video.")
    ap.add_argument("--video", help="input video (omit with --card-only)")
    ap.add_argument("--out", help="output video; default <input>-labelled.mp4")
    ap.add_argument("--name", help='e.g. "Oleksandr Gamaniuk"')
    ap.add_argument("--title", help='e.g. "CEO, Instafill.ai"')
    ap.add_argument("--at", type=float, default=2.0, help="film time the label fades up (s)")
    ap.add_argument("--dur", type=float, default=5.5, help="how long it stays, fades included (s)")
    ap.add_argument("--labels", help="JSON list of label specs, for several")
    ap.add_argument("--preset", default=DEFAULT_PRESET)
    ap.add_argument("--tmp", default="temp")
    ap.add_argument(
        "--card-only",
        action="store_true",
        help="render the card PNG and stop, to eyeball the style",
    )
    ap.add_argument(
        "--frame",
        type=float,
        metavar="T",
        help="composite onto the frame at T and write a PNG -- "
        "proves placement without spending an encode",
    )
    ap.add_argument(
        "--clip", action="store_true", help="encode only the label windows, not the whole film"
    )
    ap.add_argument("--width", type=int, default=1920, help="with --card-only")
    ap.add_argument("--height", type=int, default=1080, help="with --card-only")
    ap.add_argument("--cq", default="21")
    ap.add_argument(
        "--encoder",
        default=None,
        help="default: the best one this machine can run (see _encode.py)",
    )
    args = ap.parse_args()

    specs = load_specs(args)

    if args.card_only:
        pngs, _, _ = prepare(args.preset, specs, args.width, args.height, args.tmp)
        for p in pngs:
            print("%s  %dx%d" % (p, *Image.open(p).size))
        return

    if not args.video:
        sys.exit("--video is required")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    w, h, fps, dur = probe(args.video)
    for s in specs:
        if float(s["at"]) >= dur:
            sys.exit(
                "label %r starts at %.1fs but the film is %.1fs long"
                % (s.get("name"), float(s["at"]), dur)
            )
    pngs, fc, out_label = prepare(args.preset, specs, w, h, args.tmp)

    # --frame: one composited still. The cheapest possible proof that the card
    # lands where it should and stays legible over THIS footage, and the check
    # to run before spending a full encode on a 1080p film.
    if args.frame is not None:
        png = os.path.splitext(args.video)[0] + "-label-%.0fs.png" % args.frame
        png = os.path.join(args.tmp, os.path.basename(png))
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-nostdin",
            "-ss",
            "%.3f" % args.frame,
            "-i",
            args.video,
        ]
        for p in pngs:
            cmd += ["-i", p]
        # The still is grabbed at T, so the image inputs' clocks restart at zero
        # and the fades would land somewhere else entirely. Composite the cards
        # flat instead: this mode is about WHERE the card sits, not when.
        preset = json.load(open(_overlay.repo_path(args.preset), encoding="utf-8"))
        sx = w / float(preset["canvas"]["width"])
        sy = h / float(preset["canvas"].get("height", 1080))
        parts, cur = [], "0:v"
        for i, p in enumerate(pngs):
            lay = dict(preset.get("layout", {}))
            lay.update(specs[i].get("layout", {}))
            im = Image.open(p)
            x, y = anchor_xy(lay, im.width, im.height, w, h, sx, sy)
            parts.append("[%d:v]format=rgba[q%d]" % (i + 1, i))
            parts.append("[%s][q%d]overlay=x=%d:y=%d[o%d]" % (cur, i, x, y, i))
            cur = "o%d" % i
        cmd += [
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[%s]" % cur,
            "-frames:v",
            "1",
            "-y",
            png,
        ]
        if subprocess.run(cmd, env=ENV).returncode:
            sys.exit("ffmpeg failed building the preview frame")
        print(png)
        return

    out = args.out or os.path.splitext(args.video)[0] + "-labelled.mp4"
    trim = []
    if args.clip:
        a = max(0.0, min(float(s["at"]) for s in specs) - 1.5)
        b = min(dur, max(float(s["at"]) + float(s.get("dur", 5.5)) for s in specs) + 1.5)
        # -ss AFTER -i so the input keeps its original timeline and the fade
        # start times still mean what they say; seeking first would rebase t.
        trim = ["-ss", "%.3f" % a, "-to", "%.3f" % b]
        out = os.path.splitext(out)[0] + "-clip.mp4"

    # One place decides the encoder keys; these preview burns get the
    # same treatment as a pipeline render.
    rcfg = _encode.resolve(
        {"encoder": args.encoder, "cq": args.cq, "speed": 5, "maxrate": "16M", "bufsize": "32M"}
    )
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-i", args.video]
    for p in pngs:
        cmd += ["-loop", "1", "-framerate", "%g" % fps, "-i", p]
    cmd += ["-filter_complex", fc, "-map", "[%s]" % out_label, "-map", "0:a:0?"]
    cmd += trim
    cmd += (
        _encode.video_args(rcfg)
        + ["-r", "%g" % fps]
        + _encode.audio_args(rcfg)
        + ["-movflags", "+faststart", "-y", out]
    )
    if subprocess.run(cmd, env=ENV).returncode:
        sys.exit("ffmpeg failed for %s" % out)

    got = probe(out)[3]
    want = (b - a) if args.clip else dur
    if abs(got - want) > 0.5:
        sys.exit("output is %.2fs, expected %.2fs -- %s left in place" % (got, want, out))
    print("%s  %.1fs  %.1f MB" % (out, got, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
