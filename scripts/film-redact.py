#!/usr/bin/env python
"""Redact the FINISHED film, in film time, on its distinct screen states.

Why this exists, and why it replaced the source-time tracker for this job:

  The old shape detected secrets on 47 minutes of SOURCE, blurred them there,
  rendered the cut, then gated the 8-minute film and mapped every hit BACK
  through the cut, the 3x/19x speed change and the centred pad. Every serious
  bug of that pipeline lived in the mapping: the `fps` filter labelling a slot
  rather than a frame (twice -- KI-006, KI-022), patch windows landing six
  seconds off, the same rect appended three rounds running while the film did
  not change. And it was slow in the one place a loop repeats: 2 h 16 m per
  gate round, because the gate re-checked all 14,400 frames.

  Measured on `books-giveaway`: a readable secret is on screen for 148 of the
  film's 480 s -- 31 %. Secrets are the film's normal state, not a few patches.
  But the film has only ~500 page-scale changes in those 14,400 frames. So the
  unit of work is not the frame and not the source: it is the SCREEN STATE,
  a run of frames showing the same thing.

  Detect on one representative frame per state, carry the boxes across the
  state's run, blur once, and gate with the same detector on the render. One
  timebase, no mapping, and the expensive step runs a few hundred times
  instead of 14,400.

Four modes, in order:

    --states   segment base.mp4 into states; write states.json + rep PNGs
    --detect   per rep: OCR rules, known-secret digit match, template NCC
    --blur     one masked-gaussian pass over base.mp4 -> the deliverable
    --gate     the same detector on the RENDER; a hit is already a film box

`redaction-review.py --states` sits between --detect and --blur and is the
acceptance test: a human sees one tile per state.

Invoke as:  python scripts/film-redact.py --project <id> --states --detect
"""

import sys
import os
import re
import json
import time
import argparse
import glob
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import _encode  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --- state segmentation -----------------------------------------------------
# Fractions of pixels that must differ (by more than 12 levels) for a frame to
# count as a change. Both measured on the books-giveaway film: 41 % of frames
# move at all, but only 497 of 14,400 move more than 10 % -- so STILL sorts
# caret blinks and spinners away, and PAGE catches a navigation.
STILL = 0.0006
PAGE = 0.10
# A state may not run longer than this without a fresh look: a slow reveal
# (a dropdown, a toast, text typed a character at a time) never trips PAGE but
# does put new words on screen.
# How different a frame must be from its state's FIRST frame before it counts
# as a new screen. 2 % of pixels is a paragraph of text appearing, a dialog, a
# list repainting -- but not a caret, a hover highlight or one typed character.
DRIFT = 0.02
MAX_STATE_S = 2.0
# Above this, coarsen rather than melt the review. Only states that carry a
# detection become a yes/no tile; the rest are a thumbnail grid, so a
# thousand-odd states is a readable page, not a thousand questions.
MAX_STATES = 2000
# Reps between a shard's checkpoints. 25 reps is about a minute of OCR, so an
# interrupted run loses a minute per worker rather than everything it did.
CHECKPOINT = 25

DILATE = 6  # pixels around every detected box
BLUR_DOWNSCALE = 8
BLUR_SIGMA = 3.0

# A box is "actually blurred" when its Laplacian variance is far below the
# sharp text it was cut from. Measured on the real render: sharp instances
# scored 0.80-1.05 of their template's variance, blurred ones 0.000. Anything
# under this is blurred; the margin is three orders of magnitude, so the exact
# number does not matter.
SHARP_RATIO = 0.25


def fmt(t):
    t = float(t or 0)
    return f"{int(t) // 60}:{t % 60:04.1f}"


def load(name):
    """Import a hyphenated sibling script by path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), os.path.join(HERE, name + ".py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def probe(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    d = json.loads(out)
    st = d["streams"][0]

    def rate(x):
        n, _, dn = (x or "0/1").partition("/")
        return float(n) / float(dn) if dn and float(dn) else 0.0

    fps = rate(st.get("r_frame_rate")) or rate(st.get("avg_frame_rate")) or 30.0
    return {
        "w": int(st["width"]),
        "h": int(st["height"]),
        "fps": fps,
        "dur": float(d["format"]["duration"]),
    }


def gray_stream(path, w, h):
    """Every frame, in order, as gray. The film is ours and CFR, so the frame
    INDEX is the timebase -- no pts parsing, and none of the `fps`-filter
    slot-labelling trouble that cost this pipeline two separate bugs.
    """
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin"]
        + _encode.decode_args()
        + ["-i", path, "-vf", f"scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    n = w * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w)
    p.stdout.close()
    p.wait()


def frame_change(fr, prev):
    """Fraction of pixels that moved by more than 12 levels; see the twin in
    track-blur.py for why this is cv2.absdiff and not the numpy spelling.
    """
    d = cv2.absdiff(fr, prev)
    return cv2.countNonZero(cv2.threshold(d, 12, 1, cv2.THRESH_BINARY)[1]) / float(fr.size)


_HANN = {}


def shift_of(a, b):
    """Vertical pixel shift from a to b, or None if it is not a clean scroll.

    phaseCorrelate returns a subpixel offset and a response; a real scroll has
    a sharp peak and a mostly-vertical offset. A page change has neither.

    Run at quarter of the segmentation resolution and with the Hanning window
    CACHED: this is called for most of the film's changed frames (5,857 of
    14,400 here), and building a fresh window per call made the states pass
    the most expensive stage in the script.
    """
    h, w = a.shape[0] // 2, a.shape[1] // 2
    if (w, h) not in _HANN:
        _HANN[(w, h)] = cv2.createHanningWindow((w, h), cv2.CV_32F)
    win = _HANN[(w, h)]
    fa = cv2.resize(a, (w, h)).astype(np.float32) * win
    fb = cv2.resize(b, (w, h)).astype(np.float32) * win
    (dx, dy), resp = cv2.phaseCorrelate(fa, fb)
    if resp < 0.10 or abs(dy) < 0.25 or abs(dx) > max(1.0, abs(dy) * 0.5):
        return None
    return float(dy) * 2.0


def segment(path, info, drift=DRIFT, verbose=True):
    """Frames -> [{i0, i1, kind}], one state per DISTINCT SCREEN.

    The first version started a new state on every changed frame and produced
    4,600 states for an 8-minute film -- because a caret, a hover and a
    character typed into a field are all "changed". A state is not a frame
    that differs from the last one; it is a stretch showing the same thing.

    So the test is drift from the state's ANCHOR (its first frame), not from
    the previous frame:

      drift >= DRIFT   the screen has become a different screen -> new state
      m     >= PAGE    a navigation; new state immediately
      run   >  MAX     nothing tripped, but a slow reveal may have put new
                       words on screen, so take a fresh look anyway

    The frame-to-frame change is still computed, but only to tell a scroll
    (content sliding, detectable as a vertical shift) from an edit.
    """
    w, h = info["w"] // 2, info["h"] // 2
    max_run = max(1, int(round(MAX_STATE_S * info["fps"])))
    states = []
    prev = anchor = None
    cur = None
    moved_v = 0
    for i, fr in enumerate(gray_stream(path, w, h)):
        if prev is None:
            cur = {"i0": 0, "i1": 0, "kind": "page"}
            prev = anchor = fr
            continue
        m = frame_change(fr, prev)
        d = frame_change(fr, anchor)
        if m >= STILL and shift_of(prev, fr) is not None:
            moved_v += 1
        prev = fr
        run = i - cur["i0"]
        if m < PAGE and d < drift and run < max_run:
            cur["i1"] = i
            continue
        if m >= PAGE:
            kind = "page"
        elif moved_v >= max(2, run // 4):
            kind = "scroll"  # most of this state's motion was sliding
        elif d >= drift:
            kind = "edit"  # text appeared in place
        else:
            kind = "hold"  # only the max-run cap fired
        cur["kind"] = kind
        states.append(cur)
        cur = {"i0": i, "i1": i, "kind": "page"}
        anchor = fr
        moved_v = 0
        if verbose and len(states) % 100 == 0:
            print(
                f"    ...frame {i} ({i / info['fps']:.0f}s) {len(states)} states", file=sys.stderr
            )
    if cur:
        states.append(cur)
    return states


def states_of(path, info, out_json, reps_dir, verbose=True):
    """Segment, coarsening until the count is reviewable, then write reps."""
    drift = DRIFT
    for _ in range(5):
        states = segment(path, info, drift, verbose)
        if len(states) <= MAX_STATES:
            break
        drift *= 2.0
        print(
            f"  {len(states)} states is more than a human will review; "
            f"raising the drift threshold to {drift:.4f} and re-segmenting"
        )
    # A representative frame: the LAST frame of the state. A page change's
    # first frames can still be painting -- a spinner, a half-drawn list --
    # and the secret arrives with the text, not with the navigation.
    for s in states:
        s["rep"] = s["i1"]
        s["t"] = round(s["i0"] / info["fps"], 3)
        s["dur"] = round((s["i1"] - s["i0"] + 1) / info["fps"], 3)
    os.makedirs(reps_dir, exist_ok=True)
    for f in os.listdir(reps_dir):
        if f.startswith("rep_") and f.endswith(".png"):
            os.remove(os.path.join(reps_dir, f))
    write_reps(path, info, states, reps_dir, verbose)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "film": _project.norm(path),
                "fps": info["fps"],
                "w": info["w"],
                "h": info["h"],
                "drift": drift,
                "states": states,
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    return states


def write_reps(path, info, states, reps_dir, verbose=True):
    """One full-resolution PNG per state, written by ffmpeg itself.

    `select` picks the wanted frame indices and image2 writes the files, so
    NOTHING goes through a pipe. Measured on this film: 700 reps in 28 s that
    way, against a stall when the same frames were piped as raw BGR -- 14,400
    frames at 1920x1080x3 is 89 GB of pipe, and the reader is the bottleneck
    long before ffmpeg is. Seeking per state instead would be hundreds of
    seeks and risks landing on the wrong frame, the trap that cost this
    pipeline two separate bugs, so: one pass, one expression, no pipe.

    Selected by PRESENTATION TIME, not by frame index. `select`'s `n` counts
    frames since the last decoder initialisation, and this film is a
    stream-copied concat whose eighth piece is a portrait phone clip: the
    decoder re-initialises there, `n` restarts, and `eq(n\\,100)` matched twice
    -- once at 3.33 s and again at 163.00 s. That is how a request for 1,330
    frames produced 1,495 files. `t` does not reset, so every frame is asked
    for by its own time with a half-frame window.

    And it is verified rather than trusted: `showinfo` reports the time of
    each frame actually emitted, files are matched back to states by that, and
    a state left without a frame is a hard failure. Guessing that file k is
    state k is what the old pipeline did, twice, and both times it was wrong.

    The expression is ~30 characters per state and a Windows command line dies
    at 32 KB (KI-008), so it goes in a script file like every other graph here.
    """
    fps = info["fps"]
    want = [(n, s["rep"] / fps) for n, s in enumerate(states)]
    half = 0.5 / fps
    expr = "+".join(r"lt(abs(t-%.6f)\,%.6f)" % (t, half) for _, t in want)
    os.makedirs(reps_dir, exist_ok=True)
    raw = os.path.join(reps_dir, "_raw")
    os.makedirs(raw, exist_ok=True)
    for f in os.listdir(raw):
        os.remove(os.path.join(raw, f))
    gpath = os.path.join(reps_dir, "select.txt")
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(f"[0:v]select='{expr}',showinfo[out]")
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-nostdin", "-y"]
        + _encode.decode_args()
        + [
            "-i",
            path,
            "-filter_complex_script",
            gpath,
            "-map",
            "[out]",
            "-fps_mode",
            "passthrough",
            "-start_number",
            "0",
            os.path.join(raw, "f_%05d.png"),
        ],
        stderr=subprocess.PIPE,
        text=True,
    )
    if r.returncode != 0:
        tail = "\n".join((r.stderr or "").strip().splitlines()[-15:])
        raise SystemExit(f"reps failed ({r.returncode}):\n{tail}")
    times = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr or "")]
    files = sorted(f for f in os.listdir(raw) if f.endswith(".png"))
    if len(times) != len(files):
        raise SystemExit(
            f"reps: {len(files)} file(s) but {len(times)} showinfo "
            f"line(s); cannot match frames to states"
        )
    # nearest wanted time wins; a duplicate emission loses to the first
    for f in os.listdir(reps_dir):
        if f.startswith("rep_") and f.endswith(".png"):
            os.remove(os.path.join(reps_dir, f))
    taken = {}
    for fn, t in zip(files, times):
        n, wt = min(want, key=lambda w: abs(w[1] - t))
        if abs(wt - t) > half * 2 or n in taken:
            os.remove(os.path.join(raw, fn))
            continue
        taken[n] = t
        os.replace(os.path.join(raw, fn), os.path.join(reps_dir, f"rep_{n:05d}.png"))
    missing = [n for n, _ in want if n not in taken]
    if missing:
        raise SystemExit(
            f"reps: {len(missing)} state(s) got no frame "
            f"(first: state {missing[0]} at "
            f"{states[missing[0]]['rep'] / fps:.3f}s)"
        )
    if verbose and len(files) != len(want):
        print(
            f"    {len(files)} frames emitted for {len(want)} states; "
            f"{len(files) - len(want)} duplicate(s) dropped by timestamp"
        )
    os.rmdir(raw)
    return len(taken)


# --- detection --------------------------------------------------------------
def known_secrets(pdir, kinds):
    """Digit strings this project's earlier source OCR already found.

    A film-time scan does not NEED these -- the rules find secrets on their
    own -- but a known string is the cheapest, surest detector there is, and
    it catches the case where OCR reads the digits but the rule's punctuation
    assumption misses (the national `0XX` phone form did exactly that once).
    Optional: a project with no source scan simply has none.
    """
    out = {}
    pii = os.path.join(pdir, "temp", "pii")
    if not os.path.isdir(pii):
        return out
    for f in sorted(os.listdir(pii)):
        if not f.endswith(".pii.json"):
            continue
        try:
            d = json.load(open(os.path.join(pii, f), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for h in d.get("hits") or []:
            if h.get("kind") not in kinds:
                continue
            digits = re.sub(r"\D", "", h.get("text") or "")
            if len(digits) >= 6:
                out.setdefault(digits, h["kind"])
    return out


def digit_runs(text):
    """Every maximal digit run in an OCR line, with its character span."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\d+", text)]


def match_known(text, known, min_len=6):
    """Is a known secret's digit sequence inside this line?

    Compared on digits alone, so `+38 (099) 676-7726`, `380996767726` and
    `0996767726` are the same secret however either side punctuated it, and an
    OCR misread of one character still matches on a long enough tail.
    """
    d = re.sub(r"\D", "", text)
    if len(d) < min_len:
        return None
    for k, kind in known.items():
        if len(k) < min_len:
            continue
        if k in d or d in k:
            return kind
        # tolerate one bad character in a long run: compare the tails
        if len(k) >= 9 and (k[-9:] in d or k[:9] in d):
            return kind
    return None


def detect_rep(png, sp, tb, rules_kinds, known, templates, ocr_width):
    """Every secret box on one representative frame, in frame fractions."""
    img = cv2.imread(png, cv2.IMREAD_COLOR)
    if img is None:
        return []
    H, W = img.shape[:2]
    boxes = []

    small = cv2.resize(img, (ocr_width, max(2, ocr_width * H // W)), interpolation=cv2.INTER_AREA)
    res, _ = sp.OCR(small)
    lines = []
    for box, text, conf in res or []:
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(
            {
                "text": text,
                "conf": conf,
                "box": [
                    min(xs) / small.shape[1],
                    min(ys) / small.shape[0],
                    (max(xs) - min(xs)) / small.shape[1],
                    (max(ys) - min(ys)) / small.shape[0],
                ],
            }
        )

    hits = sp.apply_rules([{"t": 0.0, "lines": lines}], only=rules_kinds)
    for h in hits:
        boxes.append(
            {
                "rect": [round(v, 5) for v in h["rect"]],
                "kind": h["kind"],
                "via": "rule",
                "text": h["text"][:60],
            }
        )
    for ln in lines:
        kind = match_known(ln["text"], known)
        if kind:
            boxes.append(
                {
                    "rect": [round(v, 5) for v in ln["box"]],
                    "kind": kind,
                    "via": "known",
                    "text": ln["text"][:60],
                }
            )

    if templates:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        half = cv2.resize(gray, (W // 2, H // 2))
        for tpl in templates:
            for x, y, w, h in tb.full_search(half, gray, tpl, scales=(1.0,)):
                boxes.append(
                    {
                        "rect": [
                            round(x / W, 5),
                            round(y / H, 5),
                            round(w / W, 5),
                            round(h / H, 5),
                        ],
                        "kind": tpl["kind"],
                        "via": "template",
                        "text": tpl["text"][:60],
                    }
                )
    return merge_boxes(boxes)


def merge_boxes(boxes, iou=0.25):
    """Union boxes that overlap; three detectors find the same field."""
    out = []
    for b in sorted(boxes, key=lambda b: -b["rect"][2] * b["rect"][3]):
        for o in out:
            if overlap(o["rect"], b["rect"]) > iou:
                o["rect"] = union(o["rect"], b["rect"])
                if b["via"] not in o["via"]:
                    o["via"] += "+" + b["via"]
                break
        else:
            out.append(dict(b))
    return out


def overlap(a, b):
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1e-9, min(a[2] * a[3], b[2] * b[3]))


def union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [round(x0, 5), round(y0, 5), round(x1 - x0, 5), round(y1 - y0, 5)]


def sweep_union(states, per_state):
    """A scrolling run's boxes become ONE TALL box per column, spanning the
    whole sweep, applied to every state in the run.

    Chasing a moving box means the blur lags the text by however far it moved
    since the sampled frame. Keeping the sampled positions as separate boxes
    is no better: a secret sampled at y=0.70, 0.50 and 0.30 is SHARP at 0.60
    on the frames in between. So every box that shares a horizontal band with
    another in the run is unioned vertically into a single box covering min-y
    to max-y+h. It over-blurs a column for a second or two; it cannot leak.
    """
    n = 0
    i = 0
    while i < len(states):
        if states[i]["kind"] != "scroll":
            i += 1
            continue
        j = i
        while j + 1 < len(states) and states[j + 1]["kind"] == "scroll":
            j += 1
        pool = [b for k in range(i, j + 1) for b in per_state.get(str(k), [])]
        if pool:
            cols = []
            for b in pool:
                x, y, w, h = b["rect"]
                for c in cols:
                    cx, cw = c["rect"][0], c["rect"][2]
                    # same column: the horizontal spans overlap at all
                    if x < cx + cw and cx < x + w:
                        nx0, nx1 = min(cx, x), max(cx + cw, x + w)
                        ny0 = min(c["rect"][1], y)
                        ny1 = max(c["rect"][1] + c["rect"][3], y + h)
                        c["rect"] = [
                            round(nx0, 5),
                            round(ny0, 5),
                            round(nx1 - nx0, 5),
                            round(ny1 - ny0, 5),
                        ]
                        if b["via"] not in c["via"]:
                            c["via"] += "+" + b["via"]
                        break
                else:
                    cols.append(dict(b, via=b["via"] + "+sweep"))
            for k in range(i, j + 1):
                per_state[str(k)] = [dict(c) for c in cols]
                n += 1
        i = j + 1
    return n


# --- blur -------------------------------------------------------------------
def hand_boxes(hand, t0, t1):
    """Manifest `film_blur` rects whose window overlaps [t0, t1).

    Detection cannot see everything and never will: a card face drawn as art,
    text the user has SELECTED, a name the OCR reads no Cyrillic for. The
    source-time route carried those as `sources[].blur` with a reason on each;
    film time needs the same escape hatch or it leaks exactly where the old
    one was patched by hand (KI-002, KI-017, KI-026).
    """
    out = []
    for b in hand or []:
        w = b.get("when")
        if w and (t1 <= float(w[0]) or t0 >= float(w[1])):
            continue
        out.append(
            {
                "rect": [float(v) for v in b["rect"]],
                "kind": b.get("kind", "hand"),
                "via": "hand",
                "text": b.get("why", "")[:60],
            }
        )
    return out


def mask_runs(states, per_state, decisions, info, outdir, hand=None):
    """Mask PNGs + a concat listing, one PNG per stretch of identical boxes.

    Written LONGER than the film on purpose: alphamerge pairs frames one to
    one and a mask that ends early stalls the graph forever -- the looped-PNG
    trap, the same one the shorts pipeline hit.
    """
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.startswith("mask_") and f.endswith(".png"):
            os.remove(os.path.join(outdir, f))
    W, H = info["w"], info["h"]
    dx, dy = DILATE / float(W), DILATE / float(H)
    runs = []
    fps = float(info["fps"])
    for n, s in enumerate(states):
        if decisions.get(str(n)) == "clear":
            boxes = []
        else:
            boxes = list(per_state.get(str(n), []))
        # A hand rect is never cleared by a review decision: it is there
        # BECAUSE a person looked at the frame and the detector could not.
        boxes += hand_boxes(hand, s["i0"] / fps, (s["i1"] + 1) / fps)
        key = sorted(tuple(round(v, 4) for v in b["rect"]) for b in boxes)
        if runs and runs[-1]["key"] == key:
            runs[-1]["i1"] = s["i1"]
        else:
            runs.append({"i0": s["i0"], "i1": s["i1"], "key": key})
    lines = []
    for n, r in enumerate(runs):
        m = np.zeros((H, W), np.uint8)
        for x, y, w, h in r["key"]:
            x0 = max(0, int(round((x - dx) * W)))
            y0 = max(0, int(round((y - dy) * H)))
            x1 = min(W, int(round((x + w + dx) * W)))
            y1 = min(H, int(round((y + h + dy) * H)))
            if x1 > x0 and y1 > y0:
                m[y0:y1, x0:x1] = 255
        if r["key"]:
            m = cv2.GaussianBlur(m, (9, 9), 0)
        name = f"mask_{n:06d}.png"
        cv2.imwrite(os.path.join(outdir, name), m)
        dur = (r["i1"] - r["i0"] + 1) / info["fps"]
        lines.append(f"file '{name}'\nduration {dur:.4f}")
    lines.append(f"file 'mask_{len(runs) - 1:06d}.png'\nduration 5")
    lines.append(f"file 'mask_{len(runs) - 1:06d}.png'")
    listing = os.path.join(outdir, "masks.txt")
    with open(listing, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return runs, listing


def blur_cmd(base, listing, info, out, cq=21, preset="p5", prog=None):
    """One pass: blur the whole frame once, show it through the mask.

    The measured idiom (KI-021): downscale by 8, gblur, bicubic back up, so
    the gaussian runs on 1/64th of the pixels and still reads as a blur rather
    than a mosaic; alphamerge the blurred copy over the sharp one.
    """
    W, H = info["w"], info["h"]
    d, sig = BLUR_DOWNSCALE, BLUR_SIGMA
    g = (
        f"[0:v]split[clean][src];"
        f"[src]scale=iw/{d}:ih/{d}:flags=area,gblur=sigma={sig},"
        f"scale={W}:{H}:flags=bicubic[blur];"
        f"[1:v]fps={info['fps']:.4f},scale={W}:{H}:flags=neighbor,format=gray[m];"
        f"[blur][m]alphamerge[a];[clean][a]overlay[out]"
    )
    gpath = os.path.splitext(out)[0] + ".filtergraph.txt"
    os.makedirs(os.path.dirname(gpath), exist_ok=True)
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(g)
    cmd = ["ffmpeg", "-v", "error", "-stats", "-nostdin", "-y"]
    if prog:
        cmd += ["-progress", prog]
    cmd += (
        [
            "-i",
            base,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-filter_complex_script",
            gpath,
            "-map",
            "[out]",
            "-an",
        ]
        + _encode.video_args(_encode.resolve({"preset": preset, "cq": cq}))
        + ["-movflags", "+faststart", out]
    )
    return cmd


# --- gate -------------------------------------------------------------------
def sharpness(img):
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def gate_boxes(render, info, states, per_state, reps_dir):
    """Which detected boxes are still SHARP on the render.

    The detector already told us where every secret is; the only question the
    gate has to answer is whether the blur landed there. Comparing each box's
    Laplacian variance on the render against the same box on the unblurred rep
    is exact, needs no templates, and takes seconds -- against 2 h 16 m for
    the old whole-frame re-search.
    """
    want = {s["rep"]: n for n, s in enumerate(states) if per_state.get(str(n))}
    hits, ratios = [], []
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin"]
        + _encode.decode_args()
        + ["-i", render, "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    n = info["w"] * info["h"]
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        if i in want:
            k = want[i]
            fr = np.frombuffer(buf, np.uint8).reshape(info["h"], info["w"])
            rep = cv2.imread(os.path.join(reps_dir, f"rep_{k:05d}.png"), cv2.IMREAD_GRAYSCALE)
            for b in per_state[str(k)]:
                x, y, w, h = b["rect"]
                x0, y0 = int(x * info["w"]), int(y * info["h"])
                x1, y1 = int((x + w) * info["w"]), int((y + h) * info["h"])
                if x1 <= x0 or y1 <= y0:
                    continue
                cut = fr[y0:y1, x0:x1]
                ref = rep[y0:y1, x0:x1] if rep is not None else None
                if cut.size == 0 or ref is None or ref.size == 0:
                    continue
                ratio = sharpness(cut) / max(sharpness(ref), 1e-6)
                ratios.append(ratio)
                if ratio > SHARP_RATIO:
                    hits.append(
                        {
                            "state": k,
                            "t": round(i / info["fps"], 3),
                            "kind": b["kind"],
                            "via": b["via"],
                            "text": b.get("text", "")[:60],
                            "rect": b["rect"],
                            "sharp_ratio": round(ratio, 3),
                        }
                    )
        i += 1
    p.stdout.close()
    p.wait()
    return hits, ratios


# --- driver -----------------------------------------------------------------
def paths(pdir):
    fd = os.path.join(pdir, "temp", "film")
    return {
        "dir": fd,
        "base": os.path.join(fd, "base.mp4"),
        "states": os.path.join(fd, "states.json"),
        "reps": os.path.join(fd, "reps"),
        "detect": os.path.join(fd, "detect.json"),
        "masks": os.path.join(fd, "masks"),
        "decisions": os.path.join(fd, "decisions.json"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--manifest")
    ap.add_argument(
        "--states", action="store_true", help="segment the base film into screen states"
    )
    ap.add_argument(
        "--detect",
        action="store_true",
        help="find every secret on each state's representative frame",
    )
    ap.add_argument(
        "--blur", action="store_true", help="one masked pass over the base film -> the deliverable"
    )
    ap.add_argument(
        "--gate",
        action="store_true",
        help="check the RENDER: is every detected box actually blurred",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="what the current states/detections cost, without doing it",
    )
    ap.add_argument("--jobs", "-j", type=int, default=max(1, min(6, (os.cpu_count() or 4) // 3)))
    ap.add_argument(
        "--ocr-width",
        type=int,
        default=1600,
        help="OCR resolution. Measured on this film: 1.75 s/rep at "
        "1600, 1.58 s at 960 -- width is nearly free, so keep "
        "the recall.",
    )
    ap.add_argument(
        "--shard", metavar="I/N", help="internal: this worker handles states where k %% N == I"
    )
    ap.add_argument(
        "--threads",
        type=int,
        default=1,
        help="OCR intra-op threads PER WORKER. 1 is right when "
        "--jobs already fills the cores: onnxruntime scales "
        "only 1.24x from one thread to all of them, so the "
        "parallelism belongs between processes, not inside "
        "them.",
    )
    ap.add_argument(
        "--fresh",
        action="store_true",
        help="discard any half-finished shard files and re-OCR "
        "everything (default is to resume them)",
    )
    ap.add_argument("--cq", type=int, default=21)
    ap.add_argument("--out", help="override the blurred output path")
    args = ap.parse_args()

    pdir = os.path.join(_project.projects_dir(), args.project)
    mpath = _env.resolve(args.manifest) if args.manifest else os.path.join(pdir, "screen.json")
    man = json.load(open(mpath, encoding="utf-8"))
    P = paths(pdir)
    kinds = set(man.get("blur_kinds") or ["card", "cvv", "expiry", "iban", "phone"])

    if not os.path.exists(P["base"]):
        raise SystemExit(
            f"no base film at {P['base']}\n"
            f"  build it first:  python scripts/screen-cut.py --manifest "
            f"{os.path.relpath(mpath, ROOT)} --no-redact"
        )
    info = probe(P["base"])
    print(
        f"{args.project}: base film {fmt(info['dur'])}  "
        f"{info['w']}x{info['h']} @ {info['fps']:.0f}fps"
    )

    if args.states:
        t0 = time.time()
        states = states_of(P["base"], info, P["states"], P["reps"])
        kc = {}
        for s in states:
            kc[s["kind"]] = kc.get(s["kind"], 0) + 1
        print(
            f"  {len(states)} states in {fmt(time.time() - t0)}   "
            + "  ".join(f"{k}={v}" for k, v in sorted(kc.items()))
        )
        print(f"  reps -> {os.path.relpath(P['reps'], ROOT)}")

    if args.detect:
        if not os.path.exists(P["states"]):
            raise SystemExit("run --states first")
        states = json.load(open(P["states"], encoding="utf-8"))["states"]
        t0 = time.time()
        known = known_secrets(pdir, kinds)

        if args.shard:
            # A worker: OCR its slice and write its own file. Sharded
            # subprocesses rather than a thread pool because RapidOCR is
            # CPU-bound in C and holds the GIL, and rather than
            # multiprocessing because this script re-execs itself into the
            # venv -- a spawned child would re-exec again.
            i, n = (int(x) for x in args.shard.split("/"))
            sp = load("scan-pii")
            tb = load("track-blur")
            from rapidocr_onnxruntime import RapidOCR

            # onnxruntime does NOT read OMP_NUM_THREADS or any env var for its
            # intra-op pool (KI-024): it must be told in the constructor. Left
            # to itself every worker opens a pool per core, so eight workers
            # oversubscribe 8:1 and the pool is slower than ONE process --
            # measured 0.21 rep/s against 0.37 for a single unthreaded run.
            sp.OCR = RapidOCR(intra_op_num_threads=args.threads)
            part = P["detect"] + f".{i}"
            per, done = {}, set()
            if os.path.exists(part):
                # Resume. Detection is an hour of OCR and it WILL be
                # interrupted -- a killed run must cost the last checkpoint,
                # not the whole hour (KI-025).
                d = json.load(open(part, encoding="utf-8"))
                per = d.get("per") or {}
                done = set(d.get("done") or [])
            mine = [k for k in range(len(states)) if k % n == i]
            todo = [k for k in mine if k not in done]
            if done:
                print(
                    f"    [{i}] resuming: {len(done)} done, {len(todo)} to go",
                    file=sys.stderr,
                    flush=True,
                )

            def checkpoint():
                tmp = part + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"per": per, "done": sorted(done)}, f, ensure_ascii=False)
                os.replace(tmp, part)  # atomic: never a half-read file

            for c, k in enumerate(todo):
                png = os.path.join(P["reps"], f"rep_{k:05d}.png")
                if os.path.exists(png):
                    boxes = detect_rep(png, sp, tb, kinds, known, [], args.ocr_width)
                    if boxes:
                        per[str(k)] = boxes
                done.add(k)
                if (c + 1) % CHECKPOINT == 0:
                    checkpoint()
                    print(
                        f"    [{i}] {len(done)}/{len(mine)}  "
                        f"{sum(len(v) for v in per.values())} box(es)",
                        file=sys.stderr,
                        flush=True,
                    )
            checkpoint()
            print(
                f"  shard {i}/{n}: {len(mine)} reps, "
                f"{sum(len(v) for v in per.values())} box(es) in "
                f"{fmt(time.time() - t0)}"
            )
            return 0

        print(f"  {len(known)} known secret digit-string(s) from the source scans")
        done0 = 0
        if args.fresh:
            for f in glob.glob(P["detect"] + ".*"):
                os.remove(f)
        else:
            for f in glob.glob(P["detect"] + ".[0-9]*"):
                try:
                    done0 += len(json.load(open(f, encoding="utf-8")).get("done") or [])
                except (ValueError, OSError):
                    os.remove(f)  # a torn file from an older format
        # Measured on this machine (8 physical cores / 16 logical), on this
        # film's own reps. ONE process alone: 2.7 s/rep = 0.37 rep/s. EIGHT
        # workers at one OCR thread each: 0.44 rep/s aggregate -- 19 % more,
        # not eight times more, because the model is memory-bound rather than
        # core-bound. Do not promise a speedup the machine will not deliver.
        eta = (len(states) - done0) / (0.37 if args.jobs == 1 else 0.44)
        print(
            f"  detecting on {len(states)} rep frame(s) with {args.jobs} "
            f"worker(s) x {args.threads} thread(s)"
            + (f", {done0} already done" if done0 else "")
            + f"  (~{fmt(eta)} at 2.7 s/rep)"
        )
        # Each worker gets its OWN log: eight workers sharing one stdout wrote
        # nothing but their headers and died invisibly, and an hour went into
        # blaming the wrong thing (KI-023). The thread budget is NOT set here
        # -- onnxruntime ignores these variables and has to be told in its
        # constructor (KI-024); they are set only for the numpy/BLAS side.
        env = dict(
            os.environ,
            OMP_NUM_THREADS=str(args.threads),
            OPENBLAS_NUM_THREADS=str(args.threads),
            MKL_NUM_THREADS=str(args.threads),
        )
        logs, procs = [], []
        for i in range(args.jobs):
            lp = os.path.join(P["dir"], f"detect.{i}.log")
            lf = open(lp, "w", encoding="utf-8")
            logs.append((lp, lf))
            procs.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        os.path.abspath(__file__),
                        "--project",
                        args.project,
                        "--detect",
                        "--shard",
                        f"{i}/{args.jobs}",
                        "--threads",
                        str(args.threads),
                        "--ocr-width",
                        str(args.ocr_width),
                    ]
                    + (["--manifest", args.manifest] if args.manifest else []),
                    cwd=ROOT,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            )
        bad = [p.wait() for p in procs]
        for _, lf in logs:
            lf.close()
        if any(bad):
            for (lp, _), rc in zip(logs, bad):
                if rc:
                    tail = open(lp, encoding="utf-8").read().strip().splitlines()[-8:]
                    print(f"  shard log {os.path.basename(lp)} (exit {rc}):")
                    for ln in tail:
                        print(f"    {ln}")
            raise SystemExit(f"detect: {sum(1 for b in bad if b)} shard(s) failed")
        per = {}
        for i in range(args.jobs):
            f = P["detect"] + f".{i}"
            if not os.path.exists(f):
                continue
            per.update(json.load(open(f, encoding="utf-8")).get("per") or {})
            os.remove(f)
        swept = sweep_union(states, per)
        with open(P["detect"], "w", encoding="utf-8") as f:
            json.dump({"states": len(states), "per_state": per}, f, ensure_ascii=False, indent=1)
        nb = sum(len(v) for v in per.values())
        secs = sorted({b["kind"] for v in per.values() for b in v})
        covered = sum(states[int(k)]["dur"] for k in per)
        print(
            f"  {nb} box(es) on {len(per)} of {len(states)} states "
            f"({covered:.0f}s of {info['dur']:.0f}s film) in {fmt(time.time() - t0)}"
        )
        print(f"  kinds: {', '.join(secs) if secs else 'none'}   scroll states unioned: {swept}")

    if args.blur:
        for p in (P["states"], P["detect"]):
            if not os.path.exists(p):
                raise SystemExit(f"missing {os.path.relpath(p, ROOT)}; run --states --detect first")
        states = json.load(open(P["states"], encoding="utf-8"))["states"]
        per = json.load(open(P["detect"], encoding="utf-8"))["per_state"]
        decisions = {}
        if os.path.exists(P["decisions"]):
            decisions = json.load(open(P["decisions"], encoding="utf-8"))
        hand = man.get("film_blur") or []
        runs, listing = mask_runs(states, per, decisions, info, P["masks"], hand=hand)
        out = _env.resolve(args.out or man["output"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cleared = sum(1 for v in decisions.values() if v == "clear")
        print(
            f"  {len(runs)} mask run(s) -> {os.path.relpath(P['masks'], ROOT)}"
            + (f"   {len(hand)} hand rect(s)" if hand else "")
            + (f"   {cleared} state(s) cleared by review" if cleared else "")
        )
        t0 = time.time()
        cmd = blur_cmd(P["base"], listing, info, out, cq=args.cq)
        r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if r.returncode != 0:
            tail = "\n".join((r.stderr or "").strip().splitlines()[-20:])
            raise SystemExit(f"blur pass failed ({r.returncode}):\n{tail}")
        got = probe(out)["dur"]
        if abs(got - info["dur"]) > 2.0:
            raise SystemExit(
                f"FAIL: base is {fmt(info['dur'])} but the blurred render is {fmt(got)}"
            )
        print(f"  blurred {fmt(got)} in {fmt(time.time() - t0)} -> {out}")
        _project.record(
            args.project,
            "film-redact",
            out=out,
            script=__file__,
            argv=sys.argv[1:],
            kind="film",
            manifest=mpath,
            burned={
                "redaction": "film-time, per screen state",
                "mask_runs": len(runs),
                "boxes": sum(len(v) for v in per.values()),
                "hand_rects": len(hand),
            },
            note=f"{len(states)} states, {len(runs)} mask runs",
        )

    if args.gate:
        states = json.load(open(P["states"], encoding="utf-8"))["states"]
        per = json.load(open(P["detect"], encoding="utf-8"))["per_state"]
        out = _env.resolve(args.out or man["output"])
        if not os.path.exists(out):
            raise SystemExit(f"no render at {out}; run --blur first")
        t0 = time.time()
        hits, ratios = gate_boxes(out, info, states, per, P["reps"])
        with open(os.path.join(P["dir"], "gate.json"), "w", encoding="utf-8") as f:
            json.dump({"render": _project.norm(out), "hits": hits}, f, ensure_ascii=False, indent=1)
        nb = sum(len(v) for v in per.values())
        print(
            f"  gate: {len(hits)} of {nb} detected box(es) still sharp in {fmt(time.time() - t0)}"
        )
        # Show where the threshold actually sits. A detector nobody has
        # measured is the mistake this project already paid for once: if the
        # blurred boxes cluster at 0.02 and the bar is 0.25, the bar is doing
        # nothing, and if they crowd it the next render will flap.
        if ratios:
            q = sorted(ratios)

            def pc(f):
                return q[min(len(q) - 1, int(f * len(q)))]

            print(
                f"  sharpness ratio vs the unblurred frame over {len(q)} box(es): "
                f"p50 {pc(0.50):.3f}  p90 {pc(0.90):.3f}  p99 {pc(0.99):.3f}  "
                f"max {q[-1]:.3f}   (bar {SHARP_RATIO})"
            )
        for h in hits[:15]:
            print(
                f"    {fmt(h['t']):>7}  state {h['state']:<5} {h['kind']:<7} "
                f"ratio {h['sharp_ratio']:.2f}  {h['text'][:40]}"
            )
        if hits:
            return 1
        print("  CLEAN: every detected secret is blurred on the render")

    if args.list:
        if os.path.exists(P["states"]):
            d = json.load(open(P["states"], encoding="utf-8"))
            print(f"  states: {len(d['states'])} (drift={d.get('drift', 0):.4f})")
        if os.path.exists(P["detect"]):
            d = json.load(open(P["detect"], encoding="utf-8"))
            print(
                f"  detections: {sum(len(v) for v in d['per_state'].values())} "
                f"boxes on {len(d['per_state'])} states"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
