#!/usr/bin/env python
"""Burn a running commentary onto a film: what the cut did here, and why.

A finished render is silent about its own reasoning. You can see that the film
switched to camera 4, but not that it did so because voice 2 was speaking, from
tape frame 1206, on an anchor of +73 that the sound and the picture agreed on.
This puts that on the picture, in the corner, for the moments it applies to.

It is an ASS subtitle track, not a stack of overlays. libass already does the
two hard parts -- per-note timing and corner placement -- so N notes cost ONE
filter in the graph instead of N image inputs, and the whole thing rides inside
the render's existing NVENC pass. The technique is the one cut-clips.py uses to
burn captions; only the styling and the source of the text differ.

Notes are addressed in FRAMES, like everything else in the multicam round trip,
and every boundary is rounded to centiseconds exactly once so that consecutive
notes share byte-identical edges and libass never flashes a gap between them.

The first line of a note is its heading and is drawn in the accent colour; the
rest are body. Nothing here is branded or animated on purpose -- a debug note
is an instrument, and it should never be mistaken for part of the film.

  --frame T   composite the notes onto the real frame at T and write a PNG,
              which is how you check placement without spending an encode
  (none)      write the .ass

Invoke as:  python scripts/debug-notes.py --notes notes.json --out notes.ass
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT
ENV = _env.ENV

BS = chr(92)             # dodge backslash-escaping pain, as the caption builder does

DEFAULT_STYLE = {
    "font": "Montserrat-Medium", "fontsdir": "fonts",
    "size_px": 17,
    "ink": "#F2F2F2", "accent": "#7FD1C4",
    "box": "#000000", "box_alpha": 0.62, "pad_px": 10,
    "corner": "bottom-left", "margin_x_px": 24, "margin_y_px": 20,
}

# ASS numeric alignment: 1..3 bottom, 4..6 middle, 7..9 top; 1/4/7 left.
CORNERS = {"bottom-left": 1, "bottom-centre": 2, "bottom-center": 2,
           "bottom-right": 3, "top-left": 7, "top-centre": 8,
           "top-center": 8, "top-right": 9}


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def filter_path(p):
    """A path safe to put inside a filter option value.

    ffmpeg splits filter options on colons, so an absolute Windows path dies on
    its own drive letter -- `filename=C:/x.ass` parses as an option `C` and a
    stray `/x.ass`. Repo-relative with forward slashes has neither a colon nor
    a backslash for libass to read as an escape, so callers run ffmpeg from
    ROOT and pass the short form.
    """
    p = os.path.abspath(p)
    root = os.path.normpath(ROOT)
    if os.path.normcase(p).startswith(os.path.normcase(root + os.sep)):
        p = p[len(root) + 1:]
    return p.replace("\\", "/")


def fmt_cs(c):
    c = max(0, int(c))
    h, c = divmod(c, 360000)
    m, c = divmod(c, 6000)
    s, c = divmod(c, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, c)


def ass_colour(hexstr, opacity=1.0):
    """&HAABBGGRR, where AA is TRANSPARENCY: 00 is opaque and FF is invisible.

    Taking `opacity` and inverting it here is the whole point -- writing the
    byte directly is how a fully opaque colour gets written as FF and the text
    renders as nothing at all, which is exactly what happened the first time.
    """
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(round((1.0 - max(0.0, min(1.0, opacity))) * 255))
    return "&H%02X%02X%02X%02X" % (a, b, g, r)


def ass_1c(hexstr):
    """The \\1c override form: &HBBGGRR&, no alpha byte."""
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "&H%02X%02X%02X&" % (b, g, r)


def esc_text(s):
    """ASS eats braces as override blocks and collapses runs of spaces."""
    return (str(s).replace("{", "(").replace("}", ")")
            .replace(BS, "/").replace("\n", " ").strip())


def load_style(path=None):
    st = dict(DEFAULT_STYLE)
    p = rel(path or "config/overlays/debug-notes.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            st.update({k: v for k, v in json.load(f).items()
                       if not k.startswith("_")})
    return st


def build(notes, width, height, fps, style):
    """The whole .ass as a string.

    Boundaries are computed from frame indices once, so note N's end and note
    N+1's start are the same integer and there is no frame with neither.
    """
    st = dict(DEFAULT_STYLE, **(style or {}))
    align = CORNERS.get(st["corner"])
    if align is None:
        sys.exit("corner must be one of: %s" % ", ".join(sorted(CORNERS)))
    size = float(st["size_px"])
    pad = int(st["pad_px"])

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\n"
        "PlayResY: %d\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: None\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        # BorderStyle 3 is libass's opaque box: Outline becomes the padding and
        # BackColour the box. One style does panel and text together, which is
        # why this needs no drawing commands and no text measurement.
        "Style: Dbg,%s,%.1f,%s,%s,%s,%s,0,0,0,0,100,100,0,0,3,%d,0,%d,%d,%d,%d,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
        % (int(width), int(height),
           st["font"], size,
           ass_colour(st["ink"]), ass_colour(st["ink"]),
           ass_colour(st["box"], st["box_alpha"]),
           ass_colour(st["box"], st["box_alpha"]),
           pad, align,
           int(st["margin_x_px"]), int(st["margin_x_px"]), int(st["margin_y_px"])))

    def cs(frame):
        return int(round(frame * 100.0 / fps))

    accent, ink = ass_1c(st["accent"]), ass_1c(st["ink"])
    sp = BS + "N"
    ev = []
    for n in notes:
        lines = [esc_text(x) for x in n["lines"] if str(x).strip() != ""]
        if not lines:
            continue
        text = "{%s1c%s}%s{%s1c%s}" % (BS, accent, lines[0], BS, ink)
        if lines[1:]:
            text += sp + sp.join(lines[1:])
        ev.append("Dialogue: 0,%s,%s,Dbg,,0,0,0,,%s"
                  % (fmt_cs(cs(n["start"])), fmt_cs(cs(n["end"])), text))
    return head + "\n".join(ev) + "\n"


def write(notes, width, height, fps, style, out):
    doc = build(notes, width, height, fps, style)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    return out


def prepare(notes, width, height, fps, tmpdir, tag="", preset=None,
            base="vcat", label="dbgout"):
    """(ass path, filter fragment, out label) for a caller's filter_complex.

    Forward slashes, always: a Windows backslash reaches libass through the
    ass filter as an escape, and temp\\x.ass silently becomes tempx.ass.
    """
    st = load_style(preset)
    ass = os.path.join(tmpdir, "debug-notes%s.ass" % (tag and "-" + tag))
    write(notes, width, height, fps, st, ass)
    fc = ("[%s]ass=filename=%s:fontsdir=%s:shaping=simple[%s]"
          % (base, filter_path(ass), st.get("fontsdir", "fonts"), label))
    return ass, fc, label


def preview(video, ass, t, out, fontsdir="fonts"):
    """Composite the notes onto the real frame at t.

    Pushes PTS forward instead of seeking into the filter, the same trick
    verify-captions.py uses: a seek resets timestamps to zero and every
    time-gated event would evaluate against the wrong clock.
    """
    vf = ("setpts=PTS+%.4f/TB,ass=filename=%s:fontsdir=%s:shaping=simple,"
          "setpts=PTS-%.4f/TB" % (t, filter_path(ass), fontsdir, t))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-nostdin", "-ss", "%.4f" % t, "-i", video,
                        "-frames:v", "1", "-vf", vf, "-y", out],
                       capture_output=True, text=True, env=ENV, cwd=ROOT)
    if r.returncode:
        sys.exit("preview failed:\n%s" % (r.stderr or "")[-2000:])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--notes", required=True,
                    help="JSON: {width,height,fps,notes:[{start,end,lines[]}]}")
    ap.add_argument("--style", help="default config/overlays/debug-notes.json")
    ap.add_argument("--out", help="default beside the notes, as .ass")
    ap.add_argument("--frame", type=float,
                    help="composite onto the real frame at this time and stop")
    ap.add_argument("--video", help="the film, for --frame")
    ap.add_argument("--png", help="where --frame writes, default temp/")
    args = ap.parse_args()

    with open(rel(args.notes), encoding="utf-8") as f:
        doc = json.load(f)
    st = load_style(args.style)
    out = rel(args.out) if args.out else \
        os.path.splitext(rel(args.notes))[0] + ".ass"
    write(doc["notes"], doc["width"], doc["height"], doc["fps"], st, out)
    print("wrote %s -- %d notes" % (out.replace("\\", "/"), len(doc["notes"])))

    if args.frame is not None:
        if not args.video:
            sys.exit("--frame needs --video")
        png = rel(args.png or os.path.join("temp", "debug-notes-frame.png"))
        os.makedirs(os.path.dirname(png) or ".", exist_ok=True)
        preview(rel(args.video), out, args.frame, png,
                st.get("fontsdir", "fonts"))
        print("preview %s" % png.replace("\\", "/"))


if __name__ == "__main__":
    main()
