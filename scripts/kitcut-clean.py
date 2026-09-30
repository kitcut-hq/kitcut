#!/usr/bin/env python
"""Make a KitCut film usable as an insert: cut its closing promo card, remove
its corner watermark, drop its soundtrack.

A film exported from kitcut.ai carries two pieces of KitCut advertising that
must never reach one of our videos:

  * a "made with kitcut.ai" mark burned into the bottom-right corner of EVERY
    frame, and
  * a closing card -- a cocktail glass, "Make your own film", "kitcut.ai" --
    over the last couple of seconds.

Neither is removed by hardcoding where it was last time. The mark is FOUND in
each file: it is the only thing in the corner that never moves, so its box is
the ink of the per-pixel median over the film's first half. The card is found
twice over and the earlier wins: the moment that mark disappears (the card
replaces the whole frame, mark included) and the first frame with the card's
lime-green glass in it. The film is cut a quarter second before that.

The mark is removed with ffmpeg's `delogo`, which rebuilds the box from its
own border on every frame -- on KitCut's flat background that is the
background, and next to a soft shadow it is that shadow, with no seam. That is
only honest where nothing else in the picture is under the mark, which cannot
be seen directly, so the thing that CAN be seen is measured instead: how close
the film's own drawing ever comes to the box, and when. A film whose drawing
touches the box is refused unless --force, with the times to go and look at.

The audio is dropped on purpose. A KitCut insert sits inside our film, whose
voice-over and music run across it; KitCut's own score would fight both.

The output is checked, not assumed: the box is sampled again in the written
file and must have no mark ink left, and the duration must be the cut.

Invoke as:
  python scripts/kitcut-clean.py --job <kitcut.mp4> <clean.mp4> [--job ...] --list
  python scripts/kitcut-clean.py --job projects/<id>/outputs/film_web.mp4 projects/<id>/sources/kitcut/k1-intro.mp4 --project <id>
"""

import sys
import os
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np

import _encode  # noqa: E402 -- the one place encoder keys are chosen
import _project

ENV = _env.ENV

# An insert is re-encoded again inside the film, so this pass is kept close to
# transparent: a generation lost here is lost for good.
DEFAULT_RENDER = {"speed": 5, "cq": 16, "maxrate": "30M", "bufsize": "60M"}

CORNER = (0.70, 0.80)  # the mark lives right of 70% width, below 80% height
INK = 230  # a pixel whose darkest channel is below this is ink, not background
PAD = 3  # px of border around the mark's ink that delogo also rebuilds
CLEAR = 200  # drawing darker than this within RING px of the box is "touching"
RING = 4
PERSIST = 0.97  # share of pre-card frames a pixel must be ink in to be the mark
MAX_MARK = (0.12, 0.09)  # a mark box larger than this share of the frame is suspect
MARGIN_S = 0.25  # cut this long before the card begins
CARD_LEAD_S = 1.5  # the card's slide-in starts up to this long before its glass shows
MARK_DARK = 120  # the mark's outline is near-black (20-90); drawing on KitCut's paper never is
GUIDE = 40  # rows above the box used to match a clone source frame
# A clone source is matched on how many guide pixels differ STRONGLY, not on an
# average. A pulsing outline is a 2-px line: on K3 it is exactly 80 px of the
# 5,520-px guide band, differing by ~85, while a calm frame differs by 0. A mean
# (0.94) and a 98th percentile (10) both read that as a match and pasted a grey
# corner under a blue outline -- the corner visibly cut.
CLONE_DIFF = 30  # a guide pixel differs if any channel is off by more than this
CLONE_TOL = 8  # this many differing pixels or fewer: the same frame's twin is used
CLONE_MAX = 20  # refuse a clone whose best twin still has more differing pixels


def probe(path):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        env=ENV,
    )
    if r.returncode:
        sys.exit("cannot read %s\n%s" % (path, r.stderr.strip()))
    j = json.loads(r.stdout)
    s = j["streams"][0]
    num, den = (int(v) for v in s["avg_frame_rate"].split("/"))
    return {
        "w": int(s["width"]),
        "h": int(s["height"]),
        "fps": num / float(den or 1),
        "dur": float(j["format"]["duration"]),
    }


def sample(path, vf, w, h, fps=10):
    """Frames of `path` through filter `vf`, as an (n, h, w, 3) uint8 array."""
    r = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            "fps=%g,%s" % (fps, vf),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        env=ENV,
    )
    n = len(r.stdout) // (w * h * 3)
    return np.frombuffer(r.stdout, np.uint8)[: n * w * h * 3].reshape(n, h, w, 3)


def measure(path, fps=10, cut=None):
    """Where the mark is, when the card starts, how close the drawing comes."""
    p = probe(path)
    W, H = p["w"], p["h"]
    cx, cy = int(W * CORNER[0]), int(H * CORNER[1])
    cw, ch = W - cx, H - cy
    corner = sample(path, "crop=%d:%d:%d:%d" % (cw, ch, cx, cy), cw, ch, fps)
    dark = corner.astype(int).min(axis=3)  # (n, ch, cw), darkest channel
    n = len(dark)

    # the card: first frame with the lime glass anywhere in the right half,
    # sampled small because only its colour matters
    sw, sh = 240, 270
    right = sample(path, "crop=%d:%d:%d:0,scale=%d:%d" % (W // 2, H, W // 2, sw, sh), sw, sh, fps)
    g = right.astype(int)
    lime = (
        (g[..., 1] > 150) & (g[..., 0] < 170) & (g[..., 2] < 120) & (g[..., 1] - g[..., 2] > 60)
    ).mean(axis=(1, 2))
    # The glass is detected as lime APPEARING, not lime being there: a scene can
    # carry its own green (film_web11's sticker is the glass's exact lime and
    # sits in the right half from frame 0, which read as "card from 0.00s").
    base = float(np.median(lime[: max(1, int(fps))]))
    card_lime = next((i for i, v in enumerate(lime) if v > base * 3 + 0.0005), None)

    # the mark: ink that is there on the FIRST frames and on nearly every frame
    # up to the card. "Static in the corner" alone is not enough -- K3 of
    # acord-commercial holds a form beside the mark for most of the film, and a
    # median took that form into the box (215x172 instead of 132x60). KitCut
    # burns the mark from frame 0; a drawing has to arrive first.
    # The mark goes BEFORE the glass shows: the card slides in over ~0.7 s
    # (30.0 -> 30.75 s, 15.0 -> 15.7 s measured), and counting those mark-less
    # frames as "before the card" is how K4 lost its mark under PERSIST.
    pre = dark[: max(3, (card_lime or n) - int(CARD_LEAD_S * fps))]
    half = max(3, len(pre) // 2)
    always = (pre < INK).mean(axis=0) >= PERSIST
    first = (pre[:3] < INK).all(axis=0)
    ys, xs = np.where(always & first)
    mark = None
    card_mark = None
    if len(xs):
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
        mark = (cx + x0, cy + y0, cx + x1, cy + y1)
        ink = (dark[:, y0 : y1 + 1, x0 : x1 + 1] < INK).mean(axis=(1, 2))
        base = np.median(ink[:half])
        card_mark = next((i for i in range(half, n) if ink[i] < base * 0.3), None)

    if mark and ((mark[2] - mark[0]) > W * MAX_MARK[0] or (mark[3] - mark[1]) > H * MAX_MARK[1]):
        sys.exit(
            "%s: the corner mark measured %dx%d px -- too big for a mark, so something"
            " static in the drawing merged into it. Look at the corner before cleaning."
            % (path, mark[2] - mark[0] + 1, mark[3] - mark[1] + 1)
        )

    starts = [i for i in (card_lime, card_mark) if i is not None]
    card = min(starts) / float(fps) if starts else None
    cut_at = max(0.0, (card if card is not None else p["dur"]) - (MARGIN_S if card else 0))
    if cut is not None:
        cut_at = min(cut_at, float(cut))
    cut = cut_at

    touch = None
    if mark:
        # drawing that ever comes within RING px of the padded box, before the cut
        bx0, by0, bx1, by1 = (v - cx if i % 2 == 0 else v - cy for i, v in enumerate(mark))
        bx0, by0, bx1, by1 = bx0 - PAD, by0 - PAD, bx1 + PAD, by1 + PAD
        keep = dark[: int(cut * fps)]
        ring = np.ones(keep.shape[1:], bool)
        ring[max(0, by0 - RING) : by1 + RING + 1, max(0, bx0 - RING) : bx1 + RING + 1] = False
        ring = ~ring
        ring[max(0, by0) : by1 + 1, max(0, bx0) : bx1 + 1] = False
        if len(keep):
            worst = keep[:, ring].min(axis=1)
            hits = [i / float(fps) for i, v in enumerate(worst) if v < CLEAR]
            touch = {"darkest": int(worst.min()), "times": hits}
    return dict(p, mark=mark, card=card, cut=cut, touch=touch)


def delogo_box(m):
    """The padded mark box, kept one pixel off every frame edge (delogo needs a border)."""
    x0, y0, x1, y1 = m["mark"]
    x0, y0 = max(1, x0 - PAD), max(1, y0 - PAD)
    x1, y1 = min(m["w"] - 2, x1 + PAD), min(m["h"] - 2, y1 + PAD)
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1


def clean(src, dst, m, cfg):
    vf = []
    if m["mark"]:
        x, y, w, h = delogo_box(m)
        vf.append("delogo=x=%d:y=%d:w=%d:h=%d" % (x, y, w, h))
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    cmd = (
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-t", "%.4f" % m["cut"], "-an"]
        + (["-vf", ",".join(vf)] if vf else [])
        + _encode.video_args(cfg)
        + [dst]
    )
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if r.returncode:
        sys.exit("ffmpeg failed on %s\n%s" % (src, r.stderr.strip()[-800:]))


def plan_clone(src, m, dy, fps):
    """For every frame, which frame's twin region (dy px above) rebuilds the box.

    Used where the drawing itself runs under the mark, so no border can be
    interpolated honestly -- but the same drawing repeats elsewhere. On K3 of
    acord-commercial the three form icons are pixel copies 320 px apart (mean
    diff 0.05/255), so the corner the mark hides on the bottom form is the
    corner the middle form shows. When the bottom form pulses and the middle
    one does not, the twin is taken from the frame where the middle form was
    at the same point of its own, identical, pulse -- matched on the GUIDE rows
    just above the box, which both forms show.
    """
    bx, by, bw, bh = delogo_box(m)
    if by - dy - GUIDE < 0:
        sys.exit("--clone %d reaches above the frame" % dy)
    rows = dy + GUIDE
    strip = sample(src, "crop=%d:%d:%d:%d" % (bw, rows, bx, by - dy - GUIDE), bw, rows, fps)
    strip = strip[: int(round(m["cut"] * fps))]
    g2 = strip[:, :GUIDE].astype(np.int16)  # above the twin
    patch = strip[:, GUIDE : GUIDE + bh]  # the twin itself
    g3 = sample(src, "crop=%d:%d:%d:%d" % (bw, GUIDE, bx, by - GUIDE), bw, GUIDE, fps)
    g3 = g3[: len(strip)].astype(np.int16)  # above the box
    n = len(strip)
    choice, err = [], []
    for t in range(n):
        same = int((np.abs(g3[t] - g2[t]).max(axis=2) > CLONE_DIFF).sum())
        if same <= CLONE_TOL:
            choice.append(t)
            err.append(same)
            continue
        d = (np.abs(g2 - g3[t][None]).max(axis=3) > CLONE_DIFF).sum(axis=(1, 2))
        s_ = int(d.argmin())
        choice.append(s_)
        err.append(float(d[s_]))
    return {"choice": choice, "err": err, "patch": patch, "box": (bx, by, bw, bh)}


def clean_clone(src, dst, m, cfg, cl):
    """Stream the film, paste each frame's chosen twin over the box, encode."""
    W, H = m["w"], m["h"]
    bx, by, bw, bh = cl["box"]
    n = len(cl["choice"])
    dec = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            src,
            "-vf",
            "fps=%g" % m["fps"],
            "-frames:v",
            str(n),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        env=ENV,
    )
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    enc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "%dx%d" % (W, H),
            "-r",
            "%g" % m["fps"],
            "-i",
            "-",
        ]
        + _encode.video_args(cfg)
        + [dst],
        stdin=subprocess.PIPE,
        env=ENV,
    )
    size = W * H * 3
    for t in range(n):
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        fr[by : by + bh, bx : bx + bw] = cl["patch"][cl["choice"][t]]
        enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    dec.stdout.close()
    if enc.wait() or dec.wait() not in (0, None):
        sys.exit("clone encode failed on %s" % src)


def keep_main_frame(fr, bg, cv2, thresh=232, grow=15):
    """Erase every object on the flat background except the largest one.

    A KitCut scene often dresses its subject with small props -- a coffee cup,
    a pencil, a sticker -- that ride the same camera move, so no fixed patch
    can hold them. They are separate islands on the paper, though, while the
    subject (a folder and the forms coming out of it) is one mass once its
    parts are dilated together. Keep that mass; paint every other island,
    grown by `grow` px to take its soft edge, with the background colour. The
    corner mark is such an island too, so it goes with them.
    """
    import numpy as np

    ink = (fr.min(axis=2) < thresh).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow))
    blob = cv2.dilate(ink, k)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    if n <= 2:
        return fr, 0
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    # Only islands OUTSIDE the subject go. The subject's own details are
    # islands too -- on film_web11 the coloured title bars printed on the forms
    # are separate from the folder, and the first version of this erased them
    # (168 "objects" a frame). So the subject's convex hull is the keep zone.
    pts = cv2.findNonZero((lab == main).astype(np.uint8))
    hull = np.zeros_like(ink)
    cv2.fillConvexPoly(hull, cv2.convexHull(pts), 1)
    keep = hull.astype(bool)
    drop = np.zeros(ink.shape, bool)
    dropped = 0
    for i in range(1, n):
        if i == main:
            continue
        m_i = lab == i
        if not (m_i & keep).any():
            drop |= m_i
            dropped += 1
    out = fr.copy()
    out[drop] = bg
    return out, dropped


def clean_keep_main(src, dst, m, cfg):
    """Stream the film through keep_main_frame, cut at the card, encode."""
    import cv2
    import numpy as np

    W, H = m["w"], m["h"]
    n = int(round(m["cut"] * m["fps"]))
    dec = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            src,
            "-frames:v",
            str(n),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        env=ENV,
    )
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    enc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "%dx%d" % (W, H),
            "-r",
            "%g" % m["fps"],
            "-i",
            "-",
        ]
        + _encode.video_args(cfg)
        + [dst],
        stdin=subprocess.PIPE,
        env=ENV,
    )
    size, bg, erased = W * H * 3, None, 0
    for _ in range(n):
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        if bg is None:
            corners = np.array([fr[4, 4], fr[4, W - 5], fr[H - 5, 4], fr[H - 5, W - 5]])
            bg = np.median(corners, axis=0).astype(np.uint8)
        out, k = keep_main_frame(fr, bg, cv2)
        erased = max(erased, k)
        enc.stdin.write(out.tobytes())
    enc.stdin.close()
    dec.stdout.close()
    if enc.wait() or dec.wait() not in (0, None):
        sys.exit("keep-main encode failed on %s" % src)
    return erased


def verify(dst, m):
    """No mark ink left in the box, and the duration is the cut."""
    q = probe(dst)
    if abs(q["dur"] - m["cut"]) > 2.0 / m["fps"]:
        sys.exit("%s is %.2fs, expected %.2fs" % (dst, q["dur"], m["cut"]))
    if not m["mark"]:
        return 0.0
    x, y, w, h = delogo_box(m)
    box = sample(dst, "crop=%d:%d:%d:%d" % (w, h, x, y), w, h, fps=2)
    left = float((box.astype(int).min(axis=3) < MARK_DARK).mean())
    if left > 0.002:
        sys.exit("%s still has mark ink in the box (%.2f%% of pixels)" % (dst, 100 * left))
    return left


def fmt_t(v):
    return "-" if v is None else "%.2fs" % v


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--job",
        nargs=2,
        action="append",
        metavar=("SRC", "DST"),
        required=True,
        help="a KitCut export and where its clean copy goes; repeatable",
    )
    ap.add_argument("--project", help="project id, to record the clean copies")
    ap.add_argument(
        "--list", action="store_true", help="measure and print the plan -- encode nothing"
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="clean even where the drawing touches the mark box (look at the times first)",
    )
    ap.add_argument(
        "--clone",
        type=int,
        metavar="DY",
        help="rebuild the mark box from the identical drawing DY px above it, frame-matched"
        " (for a film whose drawing runs under the mark; see plan_clone)",
    )
    ap.add_argument(
        "--cut",
        type=float,
        metavar="S",
        help="end the clean copy by this many seconds at the latest (the card still wins if earlier)",
    )
    ap.add_argument(
        "--keep-main",
        action="store_true",
        help="keep only the largest object on the background; erase props, stickers and the"
        " corner mark with it (see keep_main_frame)",
    )
    ap.add_argument("--encoder", help="override render.encoder for this run")
    a = ap.parse_args()

    cfg = _encode.resolve(dict(DEFAULT_RENDER, **({"encoder": a.encoder} if a.encoder else {})))
    plans = []
    blocked = False
    for src, dst in a.job:
        src, dst = _env.resolve(src), _env.resolve(dst)
        m = measure(src, cut=a.cut)
        plans.append((src, dst, m))
        t = m["touch"]
        state = "clear"
        if t and t["times"]:
            state = "TOUCHES the box (darkest %d) at %s" % (
                t["darkest"],
                ", ".join("%.1fs" % v for v in t["times"][:8]),
            )
            blocked = blocked or not a.force
        print(
            "%-28s %dx%d %.0ffps %.2fs | mark %s | card from %s | keep 0-%s | %s"
            % (
                os.path.basename(src),
                m["w"],
                m["h"],
                m["fps"],
                m["dur"],
                "none"
                if not m["mark"]
                else "x%d-%d y%d-%d" % (m["mark"][0], m["mark"][2], m["mark"][1], m["mark"][3]),
                fmt_t(m["card"]),
                fmt_t(m["cut"]),
                state,
            )
        )

    if a.list:
        print("\n--list: nothing encoded (%s)" % _encode.describe(cfg))
        return
    if blocked:
        sys.exit("\nrefused: drawing touches the mark box -- look at those frames, then --force")

    for src, dst, m in plans:
        cl = None
        if a.clone and m["mark"]:
            cl = plan_clone(src, m, a.clone, m["fps"])
            moved = sum(1 for t, c in enumerate(cl["choice"]) if c != t)
            print(
                "  clone %+d px: %d frames, %d taken from another frame's twin,"
                " worst match %d differing px"
                % (-a.clone, len(cl["choice"]), moved, max(cl["err"]))
            )
            if max(cl["err"]) > CLONE_MAX:
                bad = [i / m["fps"] for i, e in enumerate(cl["err"]) if e > CLONE_MAX]
                sys.exit(
                    "refused: no twin matches within %d px at %s"
                    % (CLONE_MAX, ", ".join("%.2fs" % v for v in bad[:8]))
                )
            clean_clone(src, dst, m, cfg, cl)
        elif a.keep_main:
            k = clean_keep_main(src, dst, m, cfg)
            print("  keep-main: up to %d other object(s) erased per frame" % k)
        else:
            clean(src, dst, m, cfg)
        verify(dst, m)
        print("  %s  %.2fs, mark removed, card cut, audio dropped" % (_project.norm(dst), m["cut"]))
        if a.project:
            _project.record(
                a.project,
                "kitcut-clean",
                out=dst,
                script=__file__,
                argv=sys.argv[1:],
                kind="insert",
                burned=[
                    "cut at %.2fs, before the KitCut closing card (%s)"
                    % (m["cut"], fmt_t(m["card"])),
                    (
                        "KitCut corner mark rebuilt from the identical drawing %d px above,"
                        " frame-matched, box %s" % (a.clone, delogo_box(m))
                        if a.clone
                        else "KitCut corner mark removed with delogo, box %s" % (delogo_box(m),)
                    )
                    if m["mark"]
                    else "no corner mark found",
                    "KitCut soundtrack dropped",
                ],
                note="from %s" % _project.norm(src),
            )


if __name__ == "__main__":
    main()
