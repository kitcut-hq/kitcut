"""A film's cuts and its still stretches, from frames a few times a second: what a sheet of six
stills cannot show -- a scene that holds still for ten seconds, a cut that lands on an empty
stage. tools.motion() renders the frames; this reads them.

Measured on the films so far (2026-09-26): between frames a quarter of a second apart, a film in
motion changes 1-3% of its pixels (a small character moving is enough), a still one well under
1% (the crayon line's boil does not register at this size), and a cut or a crossfade changes
over 10% in a burst of a frame or two. A longer burst is a camera move, not a cut.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CHANGE = (
    12  # a pixel has changed when it moved by more than this (of 255), on a small blurred frame
)
STILL = 1.0  # % of pixels changing: less, and nothing on screen moves
CUT = 10.0  # % of pixels changing: more, in a short burst, and it is a cut or a transition
STILL_S = 4.0  # a still stretch this long is worth a word
CUT_MAX_S = 0.75  # a longer burst of change is a camera move
SHEET_CUTS, SHEET_STILLS = 6, 4  # how many of each the sheet shows (the text lists them all)


def rate(length):
    """Frames a second to look at: every 0.25 s for a short film, fewer for a long one."""
    return 4 if length <= 45 else 3 if length <= 80 else 2


def times(length):
    fps = rate(length)
    return [round(i / fps, 3) for i in range(int(length * fps))]


def _frames(d):
    out = []
    for name in os.listdir(d):
        if name.endswith(".png"):
            try:
                out.append((float(name[:-4]), os.path.join(d, name)))
            except ValueError:
                continue
    return sorted(out)


def _runs(flags):
    """[(first, last)] index runs where flags is true."""
    runs, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def analyse(d, sheet_path, shown="outputs/review/motion.png"):
    """The frames in folder d (<t>.png) -> (text for Claude, whether a sheet was written at
    sheet_path, which Claude knows as `shown`)."""
    fs = _frames(d)
    if len(fs) < 3:
        return "Too few frames to judge the motion.", False
    ts = [t for t, _ in fs]
    small = [
        np.asarray(
            Image.open(p)
            .convert("L")
            .resize((192, 108), Image.BILINEAR)
            .filter(ImageFilter.GaussianBlur(1)),
            dtype=np.int16,
        )
        for _, p in fs
    ]
    # ch[i]: the % of pixels that changed from frame i-1 to frame i (ch[0] is not a change)
    ch = [0.0] + [
        100.0 * float(np.mean(np.abs(small[i] - small[i - 1]) > CHANGE))
        for i in range(1, len(small))
    ]
    step = ts[1] - ts[0]

    stills = []
    for a, b in _runs([i > 0 and c < STILL for i, c in enumerate(ch)]):
        t0, t1 = ts[a - 1], ts[b]  # the frames from a-1 to b are all alike
        if t1 - t0 >= STILL_S:
            stills.append((t0, t1))
    cuts = []
    for a, b in _runs([c > CUT for c in ch]):
        x, y = ts[a - 1], ts[b]  # the last frame before, the first after
        # not the opening draw-on, nor the fade at the end
        if (b - a + 1) * step <= CUT_MAX_S and x >= 0.5 and y < ts[-1] - 0.3:
            cuts.append((x, y))

    lines = ["Motion, from frames every %.2f s:" % step]
    if cuts:
        lines.append(
            "- Cuts or transitions at %s. For each, the sheet shows the frame before, the frame "
            "after and one a second later: see that something carries over from one scene to the "
            "next (a character, an object, the camera's move), and that the new scene has its "
            "subject in frame, not an empty stage waiting for it."
            % ", ".join("%.1f s" % ((x + y) / 2) for x, y in cuts)
        )
    else:
        lines.append("- No cuts: one continuous shot.")
    if stills:
        for t0, t1 in stills:
            lines.append(
                "- Still for %.1f s, from %.1f to %.1f s: nothing on screen moves. Give it motion "
                "(a slow camera drift or push, a character's small action, something drawing on)."
                % (t1 - t0, t0, t1)
            )
    else:
        lines.append("- Nothing holds still for %g s or more." % STILL_S)

    rows = [
        (
            "cut at %.1f s" % ((x + y) / 2),
            [(x, "before"), (y, "after"), (min(y + 1, ts[-1]), "+1 s")],
        )
        for x, y in cuts[:SHEET_CUTS]
    ] + [
        ("still %.1f-%.1f s" % (x, y), [(x, "start"), ((x + y) / 2, "middle"), (y, "end")])
        for x, y in stills[:SHEET_STILLS]
    ]
    if not rows:
        return "\n".join(lines), False
    near = lambda t: min(fs, key=lambda f: abs(f[0] - t))[1]  # noqa: E731
    W, H, top = 480, 270, 30
    sheet = Image.new("RGB", (3 * W + 20, len(rows) * (H + top + 6)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    for r, (label, cells) in enumerate(rows):
        y = r * (H + top + 6)
        for c, (t, what) in enumerate(cells):
            x = c * (W + 10)
            sheet.paste(Image.open(near(t)).convert("RGB").resize((W, H)), (x, y + top))
            draw.text(
                (x + 4, y + 5), "%s -- %s (%.2f s)" % (label, what, t), fill="black", font=font
            )
    os.makedirs(os.path.dirname(sheet_path), exist_ok=True)
    sheet.save(sheet_path)
    lines.append("Read %s to see them." % shown)
    return "\n".join(lines), True
