"""Where a film's captions sit, scene by scene, read off the finished film.

A film is drawn as if it had no captions (studio/film.py frame_note says nothing of them, and its
stills show none), so nothing kept its picture out of their way. Once it is rendered, this chooses
for each scene one place for all its cards: the foot of the frame, where captions are expected,
or the top, when that scene has what matters low in the frame and nothing that matters at the
top. A scene's cards never move about; the place changes only between scenes.

    scenes    the film's own (SK.scene: captions.json "scenes"), and wherever its picture has
              changed a lot from how the scene began: a cut, a fade, a slide, a long pan
    samples   the video decoded small and grey, a few frames a second, and what the film's code
              drew in those moments (sketch/probe.js, run by sketch-render: every piece of text,
              every cast member's box); both read only while a card is up
    hidden    in each of the two bands a card may take (the layer's box at the foot and at the
              top), what would be covered that matters: words (the probe's text), a head (the top
              of a cast member's box), a face (OpenCV's Haar cascades on the frame: a painting's
              people, a photograph's), and how much of the band is detail (edges, after a blur
              that drops the paper's grain and a painting's brush noise)
    choice    the top when the foot hides words, a head or a face in HIDE of the scene's samples
              and the top hides them less than half as often; the foot when the top hides them
              that often; otherwise the top only when the foot holds clearly more detail
              (TOP_RATIO times, TOP_MARGIN more of the band) and the top band is all but empty
              (TOP_CLEAR); the foot for everything else, and for a scene with too little to go on

place(video, data, report) writes each card's "at" ("top"; a card at the foot has none, as every
captions.json before this did) and data["placed"]: the scenes, what was measured in each and
where its cards went, so a choice can be looked into after. The geometry is the layer's
(sketch/captions-layer.js box), read from the captions.json style, so the band measured is the
band drawn.
"""

import os
import subprocess

import _env  # noqa: F401 -- re-execs into .venv; before any 3rd-party import

import cv2
import numpy as np

ENV = _env.ENV
FPS = 3  # frames sampled a second
PROBE = 640  # the sampled frame's long side, in pixels
THUMB = 24  # the picture a scene is told apart by: the frame shrunk to THUMB x THUMB, grey
CHANGE = 22  # a mean difference (0-255) from the scene's first thumbnail that starts a new one
SETTLE = 0.75  # seconds after a scene starts in which its picture is still arriving
EDGE = 48  # a pixel is detail when its Sobel magnitude (|dx| + |dy|, blurred grey) is above this
HIDE = 0.25  # words, a head or a face under a band in this share of a scene's samples
TOP_RATIO = 1.4  # on detail alone, the foot must hold this many times the top's
TOP_MARGIN = 0.04  # and this much more of the band (a share of its pixels)
TOP_CLEAR = 0.03  # and the top band no more detail than this: nothing reaches up into it
HEAD = 0.28  # the top share of a cast member's box that is its head
FIGURE = 0.08  # a cast box shorter than this share of the frame is no figure (a hand, a prop)
MIN_SAMPLES = 2  # a scene with fewer samples keeps its cards at the foot


def band(data, at=None):
    """The band a card stays inside, (x0, y0, x1, y1) in the frame's pixels, at the foot or (at
    "top") the top: sketch/captions-layer.js box() from the captions.json's frame and style."""
    W, H = data["frame"]
    o = data.get("style") or {}
    size, lh, pad_y, pad_x = o["size"], o.get("lh", 1.2), o.get("padY", 0.26), o.get("padX", 0.42)
    h, w = 2 * size * lh + 2 * size * pad_y, o["w"] + 2 * size * pad_x
    y = (o["top"] if "top" in o else H - o["y"]) if at == "top" else o["y"]
    r = lambda v: int(np.floor(v + 0.5))  # noqa: E731 -- Math.round
    return (r(W / 2 - w / 2), r(y - h / 2), r(W / 2 + w / 2), r(y + h / 2))


def frames(video, W, H):
    """(t, grey frame, its scale) a few times a second, the long side PROBE pixels."""
    k = PROBE / float(max(W, H))
    pw, ph = int(round(W * k)) // 2 * 2, int(round(H * k)) // 2 * 2
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", video, "-an", "-vf"]
    cmd += ["fps=%g,scale=%d:%d" % (FPS, pw, ph), "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)
    n, i = pw * ph, 0
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            # ffmpeg's fps filter takes the frame nearest each tick: frame i is at i / FPS
            yield i / float(FPS), np.frombuffer(buf, np.uint8).reshape(ph, pw), pw / float(W)
            i += 1
    finally:
        p.stdout.close()
        p.wait()


def covers(b, box, share):
    """Whether band b covers `share` of box's height, across a good part of its width."""
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return False
    w = min(b[2], x1) - max(b[0], x0)
    h = min(b[3], y1) - max(b[1], y0)
    return w > 0.3 * (x1 - x0) and h > share * (y1 - y0)


class Looker:
    """What a frame's picture holds under each band: detail, and the faces in it."""

    def __init__(self):
        d = cv2.data.haarcascades
        self.cascades = [
            cv2.CascadeClassifier(os.path.join(d, n))
            for n in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")
        ]
        self.cascades = [c for c in self.cascades if not c.empty()]

    def faces(self, img):
        """Face boxes (x0, y0, x1, y1), stretched down over the chin and the neck."""
        mn = max(16, int(min(img.shape) * 0.06))
        eq = cv2.equalizeHist(img)
        out = []
        for c in self.cascades:
            for x, y, w, h in c.detectMultiScale(eq, 1.15, 6, minSize=(mn, mn)):
                out.append((x, y, x + w, y + h * 1.45))
        return out

    def look(self, img, bands):
        """For each band (x0, y0, x1, y1, in this frame's pixels): (its share of detail, whether
        a face is under it)."""
        g = cv2.GaussianBlur(img, (5, 5), 0)
        mag = np.abs(cv2.Sobel(g, cv2.CV_16S, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_16S, 0, 1))
        busy = mag > EDGE
        faces = self.faces(img)
        out = []
        for b in bands:
            x0, y0, x1, y1 = b
            share = float(busy[y0:y1, x0:x1].mean()) if y1 > y0 and x1 > x0 else 0.0
            out.append((share, any(covers(b, f, 0.2) for f in faces)))
        return out


def drawn_at(report, W, H):
    """The probe's frames as [(t, [what must not be covered, (x0, y0, x1, y1) in the frame's
    pixels])]: each piece of text, and the head of each cast member drawn as a figure."""
    out = []
    for f in (report or {}).get("frames") or []:
        boxes = [
            (x[0] * W / 1e3, x[1] * H / 1e3, x[2] * W / 1e3, x[3] * H / 1e3)
            for x in f.get("x") or []
        ]
        for s in f.get("s") or []:
            # [key, x0, y0, x1, y1, ops, anMax, anMin, cut, clipped, alpha, overlay, parent]
            if len(s) < 13 or s[12] != -1 or s[11] or s[10] < 0.5 or s[4] - s[2] < FIGURE * 1e3:
                continue
            x0, y0, x1, y1 = s[1] * W / 1e3, s[2] * H / 1e3, s[3] * W / 1e3, s[4] * H / 1e3
            boxes.append((x0, y0, x1, y0 + HEAD * (y1 - y0)))
        out.append((float(f["t"]), boxes))
    return out


def scenes(samples, forced, end):
    """The scenes, [(start, end)]: a new one starts at each of the film's own (`forced`), and
    wherever the picture has changed by CHANGE from the scene's first sample -- a cut, a fade, a
    slide, a long pan. A change within SETTLE of a scene's start is that scene still arriving (the
    rest of a fade): its picture is the one after it. samples: [(t, thumbnail)]."""
    starts, ref, forced = [0.0], None, sorted(f for f in forced if 0 < f < end)
    for t, thumb in samples:
        while forced and forced[0] <= t:
            f = forced.pop(0)
            if f - starts[-1] >= SETTLE:
                starts.append(f)
            ref = None
        if ref is None or float(np.abs(thumb - ref).mean()) <= CHANGE:
            ref = thumb if ref is None else ref
            continue
        at = t - 0.5 / FPS  # it changed between this sample and the one before
        if at - starts[-1] >= SETTLE:
            starts.append(at)
        ref = thumb
    starts += [f for f in forced if f - starts[-1] >= SETTLE]
    return [(s, starts[i + 1] if i + 1 < len(starts) else end) for i, s in enumerate(starts)]


def choose(foot, top, hide_foot, hide_top, n):
    """Where one scene's cards go ("top", or None for the foot), from the mean detail under each
    band and the share of samples in which each hides words, a head or a face."""
    if n < MIN_SAMPLES:
        return None
    if hide_foot >= HIDE and hide_foot > 2 * hide_top:
        return "top"
    if hide_top >= HIDE:
        return None
    if foot > TOP_RATIO * top and foot - top > TOP_MARGIN and top <= TOP_CLEAR:
        return "top"
    return None


def place(video, data, report=None):
    """Put each scene's cards at the foot of the frame or its top (card "at"), from what the
    rendered video shows under each band while they are up and what the film's code drew there
    (report: sketch/probe.js's, or None); data["placed"] says why. Answers data."""
    cards = data.get("cards") or []
    for c in cards:
        c.pop("at", None)
    if not cards:
        return data
    W, H = data["frame"]
    end = float(data.get("duration") or 0) or max(c["e"] for c in cards)
    full = [band(data), band(data, "top")]
    up = lambda t: any(c["s"] <= t < c["e"] for c in cards)  # noqa: E731
    looker, scaled, k_of, samples = Looker(), None, None, []
    for t, img, k in frames(video, W, H):
        th = cv2.resize(img, (THUMB, THUMB), interpolation=cv2.INTER_AREA).astype(np.int16)
        if k_of != k:
            k_of = k
            scaled = [tuple(int(round(v * k)) for v in b) for b in full]
        # what is under the bands while no card is up is nobody's business
        samples.append((t, th, looker.look(img, scaled) if up(t) else None))
    forced = [s for s, _ in data.get("scenes") or []]
    rows = [
        {
            "s": s,
            "e": e,
            "n": 0,
            "foot": 0.0,
            "top": 0.0,
            "ff": 0,
            "ft": 0,
            "m": 0,
            "df": 0,
            "dt": 0,
        }
        for s, e in scenes([x[:2] for x in samples], forced, end)
    ]
    which = lambda t: next((r for r in reversed(rows) if r["s"] <= t), rows[0])  # noqa: E731
    for t, _, seen in samples:
        if seen:
            (foot, hf), (top, ht) = seen
            r = which(t)
            r["n"] += 1
            r["foot"] += foot
            r["top"] += top
            r["ff"] += hf
            r["ft"] += ht
    for t, boxes in drawn_at(report, W, H):
        if up(t):
            r = which(t)
            r["m"] += 1
            r["df"] += any(covers(full[0], b, 0.3) for b in boxes)
            r["dt"] += any(covers(full[1], b, 0.3) for b in boxes)
    placed = []
    for r in rows:
        n, m = r["n"] or 1, r["m"] or 1
        hide = [max(r["ff"] / n, r["df"] / m), max(r["ft"] / n, r["dt"] / m)]
        r["at"] = choose(r["foot"] / n, r["top"] / n, hide[0], hide[1], r["n"])
        placed.append(
            {
                "s": round(r["s"], 3),
                "e": round(r["e"], 3),
                "at": r["at"] or "bottom",
                "samples": r["n"],
                # [under the foot's band, under the top's]
                "detail": [round(r["foot"] / n, 3), round(r["top"] / n, 3)],
                "faces": [round(r["ff"] / n, 2), round(r["ft"] / n, 2)],
                "drawn": [round(r["df"] / m, 2), round(r["dt"] / m, 2)],
            }
        )
    for c in cards:
        r = which((c["s"] + c["e"]) / 2)  # a card across a cut goes with the scene it is most in
        if r["at"]:
            c["at"] = r["at"]
    data["placed"] = {"v": 1, "scenes": placed}
    return data
