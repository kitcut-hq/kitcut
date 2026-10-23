#!/usr/bin/env python
"""A showreel out of finished films: one at a time with a caption, then grids of 4, 8 and 16.

The reel is a list of acts on a beat grid. A `solo` act shows one film full frame with a short
caption; a `grid` act lays several out as cells; an `end` act sinks the last grid behind a card
(logo, name, one line, the address). Every cut, reflow and reveal is placed in beats, and the
music is ARRANGED FROM THE SAME ACTS -- each layer of a style's patterns is laid over the acts it
plays in, risers end on the beat a grid lands, hits fall on act starts -- so the music and the cut
cannot drift apart, whatever the act lengths. A raw cut (`--raw`) is the same reel with the
manifest's shorter `raw` lengths and a smaller frame, and its music follows it for free.

Films keep playing as they move: a film that leaves full frame for a cell carries on where it was,
a cell may `jump` to another moment of its film when a new act starts (the reflow hides the cut),
and a film that would run out wraps to its `in`. Pieces of each film are cut from its address
(media.kitcut.ai or a local path) once, at the reel's frame rate, into the project's
`sources/showreel/`; the render reads them back at the size each stage needs.

Manifest (projects/<id>/showreel.json):
    frame [W, H], fps, style (look json), default option, options {name: {music, solo_transition,
    bpm?}}, raw {frame, fps, beats {act: beats}}, clips {key: {src, in, caption [kicker, line],
    fit cover|contain, focus [x, y], zoom, caption_at, jump {act: seconds}, loop}}, acts [{name, solo: key |
    grid: [[key | [keys switched on the beat] | @logo | null per row]...] | end: true, beats}]
Look (config/showreel/*.json): background, gaps, corner radius, caption panel and type, the logo
tile and the end card. Music (config/showreel/music/*.json): bpm, instruments, pattern layers,
drums, hits on act starts, the gap before a drop, and the sound effects of each transition.

Invoke as:
    python scripts/showreel.py --manifest projects/<id>/showreel.json --list
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive --raw --list
    python scripts/showreel.py --manifest projects/<id>/showreel.json --fetch
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive --frame 14.5
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive --music
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive --raw
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive
    python scripts/showreel.py --manifest projects/<id>/showreel.json --option drive --remux
"""

import sys
import os
import json
import math
import argparse
import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import _encode  # noqa: E402
import _progress  # noqa: E402
import _project  # noqa: E402
import _sketch  # noqa: E402
import _sketchaudio as A  # noqa: E402

ROOT = _env.ROOT
SR = _sketch.SR
DEFAULT_RENDER = {"speed": 5, "cq": 19, "maxrate": "16M", "bufsize": "32M", "audio_bitrate": "256k"}
CACHE_RENDER = {"speed": 3, "cq": 13}  # the pieces cut from each film: near-lossless, re-read once
GUARD = 1.0  # never play a film's last second (a closing card, a fade)
SOLO_TRANSITIONS = ("cut", "whip", "zoom")


# ------------------------------------------------------------------ small helpers
def clamp(x, a=0.0, b=1.0):
    return a if x < a else min(x, b)


def ease_io(u):
    u = clamp(u)
    return 4 * u * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def ease_out(u):
    return 1 - (1 - clamp(u)) ** 3


def ease_in(u):
    return clamp(u) ** 3


def ease_back(u, k=1.6):
    u = clamp(u) - 1
    return 1 + (k + 1) * u * u * u + k * u * u


def lerp(a, b, u):
    return a + (b - a) * u


def lerp_rect(r0, r1, u):
    return tuple(lerp(a, b, u) for a, b in zip(r0, r1, strict=True))


def scale_rect(r, s):
    x, y, w, h = r
    return (x + w * (1 - s) / 2, y + h * (1 - s) / 2, w * s, h * s)


def hexbgr(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def hexrgb(h):
    b, g, r = hexbgr(h)
    return (r, g, b)


def fmt(t):
    return "%d:%05.2f" % (t // 60, t % 60)


def rel(p):
    try:
        return os.path.relpath(p, ROOT)
    except ValueError:
        return p


# ------------------------------------------------------------------ manifest
def load(path, option, raw):
    path = _env.resolve(path)
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m["_path"] = path
    m["_dir"] = os.path.dirname(path)
    m["_id"] = os.path.basename(m["_dir"])
    opts = m.get("options") or {}
    name = option or m.get("option") or (sorted(opts)[0] if opts else None)
    if opts and name not in opts:
        sys.exit("--option %r: the manifest has %s" % (name, ", ".join(sorted(opts))))
    o = opts.get(name, {})
    m["_option"] = name
    with open(_env.resolve(o.get("music") or m["music"]), encoding="utf-8") as f:
        m["_music"] = json.load(f)
    m["_music_path"] = o.get("music") or m["music"]
    with open(_env.resolve(o.get("style") or m["style"]), encoding="utf-8") as f:
        m["_style"] = json.load(f)
    m["bpm"] = float(o.get("bpm") or m["_music"]["bpm"])
    m["solo_transition"] = o.get("solo_transition") or m.get("solo_transition", "cut")
    if m["solo_transition"] not in SOLO_TRANSITIONS:
        sys.exit("solo_transition must be one of %s" % ", ".join(SOLO_TRANSITIONS))
    m["_raw"] = bool(raw)
    if raw:
        r = m.get("raw") or {}
        m["frame"] = r.get("frame", [960, 540])
        m["fps"] = r.get("fps", m.get("fps", 30))
        for a in m["acts"]:
            a["beats"] = (r.get("beats") or {}).get(a["name"], a["beats"])
    m.setdefault("fps", 30)
    for k, c in m["clips"].items():
        c["key"] = k
        c.setdefault("fit", "cover")
    return m


# ------------------------------------------------------------------ timeline
def timeline(m):
    """Acts with their beats and seconds, and each grid's cell rectangles."""
    beat = 60.0 / m["bpm"]
    W, H = m["frame"]
    st = m["_style"]
    k = H / 1080.0
    gap = st.get("gap", 14) * k
    b = 0.0
    acts = []
    for i, a in enumerate(m["acts"]):
        a = dict(a)
        a["i"] = i
        a["kind"] = (
            "solo" if "solo" in a else "grid" if "grid" in a else "end" if "end" in a else None
        )
        if not a["kind"]:
            sys.exit("act %r: needs solo, grid or end" % a.get("name"))
        a["b0"], a["b1"] = b, b + a["beats"]
        a["t0"], a["t1"] = a["b0"] * beat, a["b1"] * beat
        b = a["b1"]
        a["cells"] = {}
        if a["kind"] == "solo":
            if a["solo"] not in m["clips"]:
                sys.exit("act %s: no clip %r" % (a["name"], a["solo"]))
            a["cells"][a["solo"]] = (0.0, 0.0, float(W), float(H))
        elif a["kind"] == "grid":
            rows = a["grid"]
            nr, nc = len(rows), max(len(r) for r in rows)
            cw, ch = (W - (nc + 1) * gap) / nc, (H - (nr + 1) * gap) / nr
            for r, row in enumerate(rows):
                for c, key in enumerate(row):
                    if not key:
                        continue
                    seq = key if isinstance(key, list) else [key]
                    for k2 in seq:
                        if k2 != "@logo" and k2 not in m["clips"]:
                            sys.exit("act %s: no clip %r" % (a["name"], k2))
                    key = seq[0]
                    if len(seq) > 1:  # a cell that switches films on the beat
                        a.setdefault("seq", {})[key] = seq
                    a["cells"][key] = (gap + c * (cw + gap), gap + r * (ch + gap), cw, ch)
        acts.append(a)
    for i, a in enumerate(acts):  # an end act keeps the grid before it, sunk behind the card
        if a["kind"] == "end":
            a["cells"] = dict(acts[i - 1]["cells"]) if i else {}
            # the end keeps each switching cell on the film it switched to last
            a["seq"] = {k: [v[-1]] for k, v in (acts[i - 1].get("seq") or {}).items()} if i else {}
    reflow = st.get("grid", {}).get("reflow_beats", 2) * beat
    for i, a in enumerate(acts):
        # how long before its start a grid begins to form, or the end begins to sink
        a["lead"] = reflow if a["kind"] in ("grid", "end") and i else 0.0
    return acts, beat


def act_at(acts, t):
    for a in acts:
        if t < a["t1"]:
            return a
    return acts[-1]


def solo_window(m, beat):
    st = m["_style"].get("solo", {})
    tr = m["solo_transition"]
    return {
        "cut": 0.0,
        "whip": st.get("whip_sec", 0.32),
        "zoom": st.get("zoom_sec", 0.5),
    }[tr]


def state(m, acts, beat, t):
    """What is on screen at t: [(key, rect, alpha, fx)] in drawing order, plus camera and
    overlay facts. fx: {"blur_x": px} for a whip's motion blur.
    """
    W, H = m["frame"]
    st = m["_style"]
    a = act_at(acts, t)
    nxt = acts[a["i"] + 1] if a["i"] + 1 < len(acts) else None
    out = []
    g = st.get("grid", {})
    stagger, enter_from = g.get("stagger", 0.06), g.get("enter_scale", 0.55)
    # a grid (or the end) forming out of the act before it
    if nxt and nxt["kind"] in ("grid", "end") and t >= nxt["t0"] - nxt["lead"]:
        u_raw = (t - (nxt["t0"] - nxt["lead"])) / nxt["lead"]
        u = ease_io(u_raw)
        old, new = a["cells"], nxt["cells"]
        entering = [k for k in new if k not in old]
        for key, r1 in new.items():
            if key in old:
                out.append((showing(a, key, t, beat), lerp_rect(old[key], r1, u), 1.0, {}))
        for j, key in enumerate(entering):
            d = min(0.5, j * stagger / max(nxt["lead"], 1e-6))
            v = clamp((u_raw - d) / (1 - d))
            s = lerp(enter_from, 1.0, ease_back(v, 1.3))
            out.append((key, scale_rect(new[key], s), ease_out(v * 1.6), {}))
        for key, r0 in old.items():
            if key not in new:
                out.append((key, scale_rect(r0, lerp(1, 0.6, u)), 1 - ease_out(u * 1.4), {}))
        return out
    if a["kind"] in ("grid", "end"):
        return [(showing(a, k, t, beat), r, 1.0, {}) for k, r in a["cells"].items()]
    # a solo act, and the transition from the solo before it
    key = a["solo"]
    prev = acts[a["i"] - 1] if a["i"] else None
    tr = m["solo_transition"]
    w = solo_window(m, beat)
    full = (0.0, 0.0, float(W), float(H))
    punch = st.get("solo", {}).get("punch", 0.07)
    # leaving for the next solo, half the transition before that act starts
    if nxt and nxt["kind"] == "solo" and tr != "cut" and t >= nxt["t0"] - w / 2:
        return solo_pair(m, a["solo"], nxt["solo"], (t - (nxt["t0"] - w / 2)) / w, tr, full)
    if prev and prev["kind"] == "solo" and tr != "cut" and t < a["t0"] + w / 2:
        return solo_pair(m, prev["solo"], key, (t - (a["t0"] - w / 2)) / w, tr, full)
    if tr == "cut" and prev is not None:
        s = 1 + punch * (1 - ease_out((t - a["t0"]) / st.get("solo", {}).get("punch_sec", 0.45)))
        return [(key, scale_rect(full, s), 1.0, {})]
    if prev is None:  # the opening shot settles too
        s = 1 + punch * (1 - ease_out(t / 0.7))
        return [(key, scale_rect(full, s), 1.0, {})]
    return [(key, full, 1.0, {})]


def showing(a, key, t, beat):
    """Which film a grid cell shows at t: a cell listed as several clips splits its act into
    equal parts, each switch on a whole bar."""
    seq = (a.get("seq") or {}).get(key)
    if not seq or len(seq) == 1:
        return seq[0] if seq else key
    bars = a["beats"] / 4.0
    per = max(1.0, round(bars / len(seq))) * 4 * beat
    return seq[min(len(seq) - 1, int(max(0.0, t - a["t0"]) // per))]


def solo_pair(m, k0, k1, u, tr, full):
    W, H = m["frame"]
    u = clamp(u)
    if tr == "whip":
        e = ease_io(u)
        x = -W * e
        # speed of the move, as pixels per frame: the motion blur follows it
        v = W * 6 * u * (1 - u) / m["fps"] * 1.5
        blur = {"blur_x": v * 0.55}
        x0, y0, w, h = full
        return [(k0, (x0 + x, y0, w, h), 1.0, blur), (k1, (x0 + x + W, y0, w, h), 1.0, blur)]
    # zoom: the old shot pushes in and dissolves, the new one settles from a little larger
    e = ease_io(u)
    return [
        (k0, scale_rect(full, lerp(1.0, 1.35, ease_in(u))), 1.0, {"blur": 18 * e}),
        (
            k1,
            scale_rect(full, lerp(1.18, 1.0, ease_out(u))),
            ease_io(u * 1.25),
            {"blur": 14 * (1 - e)},
        ),
    ]


def camera(m, acts, t):
    """(scale, sink): the whole picture's slow push-in during a grid, and how far the end has
    sunk (0..1).
    """
    g = m["_style"].get("grid", {})
    drift = g.get("drift", 0.03)
    a = act_at(acts, t)
    nxt = acts[a["i"] + 1] if a["i"] + 1 < len(acts) else None

    def held(act, tt):
        if act["kind"] != "grid":
            return 1.0
        n2 = acts[act["i"] + 1] if act["i"] + 1 < len(acts) else None
        end = act["t1"] - (n2["lead"] if n2 else 0)
        return 1 + drift * clamp((tt - act["t0"]) / max(end - act["t0"], 1e-6))

    if a["kind"] == "end":
        e = m["_style"].get("end", {})
        u = ease_io((t - a["t0"] + a["lead"]) / (a["lead"] + e.get("sink_sec", 0.6)))
        prev = acts[a["i"] - 1]
        return lerp(held(prev, a["t0"] - a["lead"]), e.get("scale", 0.94), u), u
    if nxt and nxt["kind"] in ("grid", "end") and t >= nxt["t0"] - nxt["lead"]:
        u = ease_io((t - (nxt["t0"] - nxt["lead"])) / nxt["lead"])
        s0 = held(a, nxt["t0"] - nxt["lead"])
        if nxt["kind"] == "end":
            e = m["_style"].get("end", {})
            uu = ease_io((t - (nxt["t0"] - nxt["lead"])) / (nxt["lead"] + e.get("sink_sec", 0.6)))
            return lerp(s0, e.get("scale", 0.94), uu), uu
        return lerp(s0, 1.0, u), 0.0
    return held(a, t), 0.0


# ------------------------------------------------------------------ the plan: who plays what
def plan(m, acts, beat):
    """Every frame's visible clips with their source times, and per clip the source windows it
    plays (for --fetch and --list). A clip's playhead runs while it is on screen, jumps where its
    `jump` names the act that is forming, and wraps to its `loop` (default `in`) before its end.
    """
    fps = m["fps"]
    total = acts[-1]["t1"]
    n = int(round(total * fps))
    heads, seen, frames = {}, {}, []
    windows = {}  # key -> list of [src0, src1]
    wraps = []
    durs = probe(m)
    for i in range(n):
        t = i / fps
        a = act_at(acts, t)
        nxt = acts[a["i"] + 1] if a["i"] + 1 < len(acts) else None
        forming = nxt if nxt and nxt["kind"] != "solo" and t >= nxt["t0"] - nxt["lead"] else a
        vis = state(m, acts, beat, t)
        row = []
        for key, rect, alpha, fx in vis:
            if key == "@logo":
                row.append((key, rect, alpha, fx, None))
                continue
            c = m["clips"][key]
            jump = (c.get("jump") or {}).get(forming["name"])
            if key not in heads:
                heads[key] = float(c["in"])
                windows.setdefault(key, []).append([heads[key], heads[key]])
                seen[key] = forming["name"]
            elif (
                jump is not None and seen.get(key) != forming["name"] and seen.get(key) is not None
            ):
                heads[key] = float(jump)
                windows[key].append([heads[key], heads[key]])
            seen[key] = forming["name"]
            limit = durs.get(key, 1e9) - GUARD
            if heads[key] > limit:
                back = float(c.get("loop", c["in"]))
                wraps.append((key, t, heads[key], back))
                heads[key] = back
                windows[key].append([back, back])
            row.append((key, rect, alpha, fx, heads[key]))
            windows[key][-1][1] = heads[key] + 1.0 / fps
            heads[key] += 1.0 / fps
        # a clip that left the screen keeps its place; `seen` forgets nothing
        frames.append(row)
    return frames, windows, wraps


def probe(m):
    """Each clip's source length, cached beside the manifest's temp files."""
    cache = os.path.join(m["_dir"], "temp", "showreel-probe.json")
    got = {}
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            got = json.load(f)
    need = [c for c in m["clips"].values() if c["src"] not in got]

    def one(c):
        p = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                src_path(c["src"]),
            ],
            capture_output=True,
            text=True,
        )
        if p.returncode:
            sys.exit("cannot read %s: %s" % (c["src"], p.stderr.strip()[:300]))
        d = json.loads(p.stdout)
        s = d["streams"][0]
        return c["src"], {"dur": float(d["format"]["duration"]), "w": s["width"], "h": s["height"]}

    if need:
        with ThreadPoolExecutor(8) as ex:
            for src, info in ex.map(one, need):
                got[src] = info
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(got, f, indent=1)
    for c in m["clips"].values():
        c["_w"], c["_h"] = got[c["src"]]["w"], got[c["src"]]["h"]
    return {k: got[c["src"]]["dur"] for k, c in m["clips"].items()}


def src_path(src):
    return src if "://" in src else _env.resolve(src)


# ------------------------------------------------------------------ pieces cut from each film
def piece_path(m, key, s0, s1):
    c = m["clips"][key]
    W, H = m["frame"]
    tag = "%s|%.3f|%.3f|%s|%dx%d" % (c["src"], s0, s1, m["fps"], W, H)
    h = hashlib.sha1(tag.encode()).hexdigest()[:10]
    d = os.path.join(m["_dir"], "sources", "showreel")
    return os.path.join(d, "%s-%.2f-%s.mp4" % (key, s0, h))


def pieces(m, windows):
    """[(key, s0, s1, path)] -- each window rounded out a little, so a small change to a clip's
    timing reuses the piece already cut.
    """
    out = []
    for key, wins in windows.items():
        for s0, s1 in wins:
            a = math.floor(s0 * 4) / 4
            b = math.ceil((s1 + 0.25) * 4) / 4
            out.append((key, a, b, piece_path(m, key, a, b)))
    return out


def piece_size(m, key):
    """The size a piece is cut at: the reel's frame for a landscape film, its height for a tall
    one (shown whole on a blurred bed of itself).
    """
    c = m["clips"][key]
    W, H = m["frame"]
    sw, sh = c["_w"], c["_h"]
    if sw / sh >= W / H:
        h = H
        w = int(round(h * sw / sh / 2)) * 2
    else:
        w = W
        h = int(round(w * sh / sw / 2)) * 2
        if c["fit"] == "contain":
            h = H
            w = int(round(h * sw / sh / 2)) * 2
    return w, h


def fetch(m, items, jobs=4):
    todo = [p for p in items if not os.path.exists(p[3])]
    if not todo:
        print("  pieces: all %d already cut" % len(items))
        return
    os.makedirs(os.path.dirname(todo[0][3]), exist_ok=True)
    cfg = _encode.resolve(dict(CACHE_RENDER))
    print("  cutting %d of %d pieces (%s)" % (len(todo), len(items), _encode.describe(cfg)))

    def one(p):
        key, a, b, path = p
        w, h = piece_size(m, key)
        tmp = path + ".part.mp4"
        cmd = (
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "%.3f" % a,
                "-i",
                src_path(m["clips"][key]["src"]),
                "-t",
                "%.3f" % (b - a),
                "-an",
                "-vf",
                "fps=%g,scale=%d:%d:flags=lanczos" % (m["fps"], w, h),
            ]
            + _encode.video_args(cfg)
            + ["-y", tmp]
        )
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            return key, a, "FAILED: " + r.stderr.strip()[-300:]
        os.replace(tmp, path)
        return key, a, "%.1fs of film in %.0fs" % (b - a, time.time() - t0)

    with ThreadPoolExecutor(jobs) as ex:
        for key, a, msg in ex.map(one, todo):
            print("    %-18s from %7.2f  %s" % (key, a, msg))
            if msg.startswith("FAILED"):
                sys.exit(1)


class Reader:
    """Frames of one piece, in order, at one size."""

    def __init__(self, path, offset, w, h, fps):
        self.w, self.h = w, h
        self.p = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "%.4f" % max(0, offset),
                "-i",
                path,
                "-vf",
                "fps=%g,scale=%d:%d:flags=area" % (fps, w, h),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=w * h * 3 * 2,
        )
        self.last = None

    def read(self):
        buf = self.p.stdout.read(self.w * self.h * 3)
        if len(buf) == self.w * self.h * 3:
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        return self.last if self.last is not None else np.zeros((self.h, self.w, 3), np.uint8)

    def close(self):
        try:
            self.p.stdout.close()
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001 -- a reader that already ended is fine
            pass


class Feeds:
    """One reader per visible clip; reopened when the playhead jumps, the piece changes or the
    clip needs a different size (a full-frame shot becoming a cell).
    """

    def __init__(self, m, items):
        self.m = m
        self.items = items
        self.open = {}  # key -> (reader, path, next_src, level)
        W, _ = m["frame"]
        self.ladder = [W / 4, W / 3, W / 2, W]

    def level(self, key, rect):
        need = rect[2] * 1.04
        for lv in self.ladder:
            if lv >= need:
                return lv
        return self.ladder[-1]

    def frame(self, key, src_t, rect):
        m = self.m
        fps = m["fps"]
        lv = self.level(key, rect)
        cur = self.open.get(key)
        if cur and abs(cur[2] - src_t) < 0.5 / fps and cur[3] == lv:
            r = cur[0]
        else:
            if cur:
                cur[0].close()
            path, a = self.find(key, src_t)
            fw, fh = piece_size(m, key)
            W, _ = m["frame"]
            k = lv / W
            w, h = max(2, int(round(fw * k / 2)) * 2), max(2, int(round(fh * k / 2)) * 2)
            r = Reader(path, src_t - a, w, h, fps)
        img = r.read()
        self.open[key] = (r, None, src_t + 1.0 / fps, lv)
        return img

    def find(self, key, t):
        best = None
        for k, a, b, path in self.items:
            if k == key and a - 1e-6 <= t < b:
                if best is None or a > best[1]:
                    best = (path, a)
        if best is None or not os.path.exists(best[0]):
            sys.exit("no piece of %s at %.2f s: run --fetch" % (key, t))
        return best

    def drop(self, keep):
        for key in list(self.open):
            if key not in keep:
                self.open[key][0].close()
                del self.open[key]

    def close(self):
        self.drop(set())


# ------------------------------------------------------------------ drawing
def font(st, size, weight=700):
    f = ImageFont.truetype(_env.resolve(st.get("font", "fonts/Inter-VF.ttf")), int(size))
    try:
        axes = f.get_variation_axes()
        vals = [
            weight
            if str(a.get("name", b"")).lower().find("weight") >= 0
            else a.get("default", a["minimum"])
            for a in axes
        ]
        f.set_variation_by_axes(
            [clamp(v, a["minimum"], a["maximum"]) for v, a in zip(vals, axes, strict=True)]
        )
    except OSError:  # a static font has no axes; it is what it is
        pass
    return f


def rgba_to_layer(img):
    a = np.asarray(img).astype(np.float32)
    bgr = a[:, :, [2, 1, 0]]
    al = a[:, :, 3:4] / 255.0
    return bgr, al


def caption_layer(m, clip):
    """The caption of a solo act: a small accent kicker over one line, on a dark panel."""
    st = m["_style"]
    cs = st.get("caption", {})
    W, H = m["frame"]
    k = H / 1080.0
    kick, line = (clip.get("caption") or ["", ""])[:2]
    fk = font(st, cs.get("kicker_size", 24) * k, cs.get("kicker_weight", 650))
    fl = font(st, cs.get("line_size", 54) * k, cs.get("line_weight", 720))
    px, py = (v * k for v in cs.get("pad", [30, 24]))
    gapk = cs.get("gap", 10) * k
    track = cs.get("kicker_tracking", 0.14)
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    def tracked_width(s, f):
        return sum(d.textlength(ch, font=f) for ch in s) + track * fk.size * max(0, len(s) - 1)

    kw = tracked_width(kick.upper(), fk) if kick else 0
    lb = d.textbbox((0, 0), line, font=fl)
    lw, lh = lb[2] - lb[0], lb[3]
    kh = fk.size if kick else 0
    bar = cs.get("bar", 6) * k
    w = int(max(kw, lw) + 2 * px + bar)
    h = int(kh + (gapk if kick else 0) + lh + 2 * py)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    panel = hexrgb(cs.get("panel", "#141210"))
    dr.rounded_rectangle(
        (0, 0, w - 1, h - 1),
        radius=cs.get("radius", 14) * k,
        fill=panel + (int(255 * cs.get("panel_alpha", 0.72)),),
    )
    dr.rectangle(
        (0, py * 0.9, bar, h - py * 0.9), fill=hexrgb(st.get("accent", "#e5894f")) + (255,)
    )
    x, y = bar + px, py
    if kick:
        cx = x
        for ch in kick.upper():
            dr.text(
                (cx, y), ch, font=fk, fill=hexrgb(cs.get("kicker_color", st.get("accent"))) + (255,)
            )
            cx += d.textlength(ch, font=fk) + track * fk.size
        y += kh + gapk
    dr.text(
        (x, y - lb[1] * 0.15),
        line,
        font=fl,
        fill=hexrgb(cs.get("line_color", st.get("ink"))) + (255,),
    )
    return rgba_to_layer(img)


def logo_tile(m, w, h):
    """The centre cell of the 3x3: the logo and the name on the accent colour."""
    st = m["_style"]
    t = st.get("tile", {})
    img = Image.new(
        "RGBA", (int(w), int(h)), hexrgb(t.get("bg", st.get("accent", "#e5894f"))) + (255,)
    )
    logo = Image.open(_env.resolve(st["logo"])).convert("RGBA")
    lh = int(h * t.get("logo_frac", 0.62))
    logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
    f = font(st, h * t.get("name_frac", 0.2), 800)
    d = ImageDraw.Draw(img)
    nb = d.textbbox((0, 0), st.get("name", "KitCut"), font=f)
    total = logo.width + h * 0.06 + (nb[2] - nb[0])
    x = (w - total) / 2
    img.alpha_composite(logo, (int(x), int((h - lh) / 2)))
    d.text(
        (x + logo.width + h * 0.06, (h - (nb[3] + nb[1])) / 2),
        st.get("name", "KitCut"),
        font=f,
        fill=hexrgb(t.get("ink", "#1a120c")) + (255,),
    )
    return np.asarray(img)[:, :, [2, 1, 0]].copy()


def end_layers(m):
    """The end card's pieces, each (bgr, alpha, (x, y), appear_beat)."""
    st = m["_style"]
    e = st.get("end", {})
    W, H = m["frame"]
    k = H / 1080.0
    out = []
    logo = Image.open(_env.resolve(st["logo"])).convert("RGBA")
    lh = int(e.get("logo_h", 300) * k)
    logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
    fname = font(st, e.get("name_size", 132) * k, 800)
    fline = font(st, e.get("line_size", 40) * k, 500)
    furl = font(st, e.get("url_size", 38) * k, 700)
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    nb = d.textbbox((0, 0), st.get("name", "KitCut"), font=fname)
    lb = d.textbbox((0, 0), st.get("line", ""), font=fline)
    ub = d.textbbox((0, 0), st.get("url", ""), font=furl)
    gap = 26 * k
    block_w = logo.width + gap + nb[2] - nb[0]
    top = H / 2 - (lh + gap * 1.2 + (lb[3] - lb[1]) + gap * 1.6 + (ub[3] - ub[1]) + 40 * k) / 2
    x0 = (W - block_w) / 2
    out.append((logo, (x0, top), 0.0))
    nimg = Image.new("RGBA", (nb[2] + 4, nb[3] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(nimg).text(
        (0, 0), st.get("name", "KitCut"), font=fname, fill=hexrgb(st.get("ink")) + (255,)
    )
    out.append((nimg, (x0 + logo.width + gap, top + (lh - nb[3]) / 2), e.get("name_at", 0.5)))
    y = top + lh + gap * 1.2
    limg = Image.new("RGBA", (lb[2] + 4, lb[3] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(limg).text(
        (0, 0), st.get("line", ""), font=fline, fill=hexrgb(st.get("ink_2", "#b6aea3")) + (255,)
    )
    out.append((limg, ((W - lb[2]) / 2, y), e.get("line_at", 1.0)))
    y += (lb[3] - lb[1]) + gap * 1.6
    pw, ph = ub[2] - ub[0] + 56 * k, ub[3] - ub[1] + 30 * k
    pimg = Image.new("RGBA", (int(pw), int(ph)), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pimg)
    pd.rounded_rectangle(
        (0, 0, pw - 1, ph - 1), radius=ph / 2, fill=hexrgb(st.get("accent")) + (255,)
    )
    pd.text(
        ((pw - (ub[2] - ub[0])) / 2 - ub[0], (ph - (ub[3] - ub[1])) / 2 - ub[1]),
        st.get("url", ""),
        font=furl,
        fill=hexrgb(st.get("tile", {}).get("ink", "#1a120c")) + (255,),
    )
    out.append((pimg, ((W - pw) / 2, y), e.get("url_at", 1.5)))
    return [(rgba_to_layer(img), xy, at) for img, xy, at in out]


def paste(canvas, bgr, alpha, x, y, opacity=1.0):
    """Alpha-blend a float layer onto the canvas at (x, y), clipped to the frame."""
    H, W = canvas.shape[:2]
    h, w = bgr.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0 or opacity <= 0:
        return
    sb = bgr[y0 - y : y1 - y, x0 - x : x1 - x]
    sa = alpha[y0 - y : y1 - y, x0 - x : x1 - x] * opacity
    dst = canvas[y0:y1, x0:x1]
    canvas[y0:y1, x0:x1] = dst + (sb - dst) * sa


_MASKS = {}


def corner_mask(w, h, r):
    key = (w, h, int(r))
    if key not in _MASKS:
        mk = np.zeros((h, w), np.uint8)
        r = int(max(0, min(r, w // 2, h // 2)))
        if r == 0:
            mk[:] = 255
        else:
            s = 4  # draw large, shrink: a soft, even edge
            big = np.zeros((h * s, w * s), np.uint8)
            cv2.rectangle(big, (r * s, 0), ((w - r) * s, h * s), 255, -1)
            cv2.rectangle(big, (0, r * s), (w * s, (h - r) * s), 255, -1)
            for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
                cv2.circle(big, (cx * s, cy * s), r * s, 255, -1)
            mk = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
        if len(_MASKS) > 400:
            _MASKS.clear()
        _MASKS[key] = mk.astype(np.float32)[:, :, None] / 255.0
    return _MASKS[key]


def fit_cell(m, key, img, w, h):
    """The film's frame shaped to a w x h cell: cropped to fill it, or (fit: contain) whole on a
    blurred, darkened bed of itself.
    """
    c = m["clips"][key]
    ih, iw = img.shape[:2]
    if c["fit"] == "contain" and iw / ih < w / h * 0.8:
        s = max(w / iw, h / ih)
        bw, bh = int(iw * s / 8) + 1, int(ih * s / 8) + 1
        bed = cv2.resize(img, (bw, bh), interpolation=cv2.INTER_AREA)
        bed = cv2.GaussianBlur(bed, (0, 0), 6)
        bed = cv2.resize(bed, (int(iw * s) + 1, int(ih * s) + 1), interpolation=cv2.INTER_LINEAR)
        oy, ox = (bed.shape[0] - h) // 2, (bed.shape[1] - w) // 2
        out = (bed[oy : oy + h, ox : ox + w].astype(np.float32) * 0.45).astype(np.uint8)
        s2 = min(w / iw, h / ih)
        fw, fh = max(1, int(iw * s2)), max(1, int(ih * s2))
        fg = cv2.resize(img, (fw, fh), interpolation=cv2.INTER_AREA if s2 < 1 else cv2.INTER_LINEAR)
        out[(h - fh) // 2 : (h - fh) // 2 + fh, (w - fw) // 2 : (w - fw) // 2 + fw] = fg
        return out
    fx, fy = c.get("focus", [0.5, 0.5])
    a = w / h
    if iw / ih > a:
        cw, ch = ih * a, ih
    else:
        cw, ch = iw, iw / a
    z = max(1.0, float(c.get("zoom", 1.0)))  # crop a film's own edge (a source line) away
    cw, ch = cw / z, ch / z
    x0 = clamp(fx * iw - cw / 2, 0, iw - cw)
    y0 = clamp(fy * ih - ch / 2, 0, ih - ch)
    crop = img[int(y0) : int(y0 + ch), int(x0) : int(x0 + cw)]
    interp = cv2.INTER_AREA if cw > w else cv2.INTER_LINEAR
    return cv2.resize(crop, (w, h), interpolation=interp)


class Painter:
    def __init__(self, m, acts, beat, items):
        self.m, self.acts, self.beat = m, acts, beat
        self.feeds = Feeds(m, items)
        st = m["_style"]
        self.bg = np.array(hexbgr(st.get("background", "#0e0d0b")), np.float32)
        self.caps = {}
        self.tiles = {}
        self.end = None

    def draw(self, t, row):
        m, st = self.m, self.m["_style"]
        W, H = m["frame"]
        k = H / 1080.0
        canvas = np.empty((H, W, 3), np.float32)
        canvas[:] = self.bg
        a = act_at(self.acts, t)
        radius = st.get("radius", 14) * k
        keep = set()
        for key, rect, alpha, fx, src_t in row:
            x, y, w, h = rect
            iw, ih = int(round(w)), int(round(h))
            if iw < 4 or ih < 4 or alpha <= 0.01:
                continue
            if key == "@logo":
                if (iw, ih) not in self.tiles:
                    self.tiles[(iw, ih)] = logo_tile(m, iw, ih)
                cell = self.tiles[(iw, ih)]
            else:
                keep.add(key)
                img = self.feeds.frame(key, src_t, rect)
                cell = fit_cell(m, key, img, iw, ih)
            if fx.get("blur_x", 0) > 1.5:
                kx = int(fx["blur_x"]) | 1
                cell = cv2.blur(cell, (kx, 1))
            if fx.get("blur", 0) > 0.6:
                cell = cv2.GaussianBlur(cell, (0, 0), fx["blur"] * k)
            r = radius if w < W * 0.985 else 0
            mk = corner_mask(iw, ih, r)
            paste(canvas, cell.astype(np.float32), mk, x, y, alpha)
        self.feeds.drop(keep)
        s, sink = camera(m, self.acts, t)
        if abs(s - 1) > 1e-4:
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
            canvas = cv2.warpAffine(
                canvas,
                M,
                (W, H),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=self.bg.tolist(),
            )
        if sink > 0:
            e = st.get("end", {})
            sm = cv2.resize(canvas, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            sm = cv2.GaussianBlur(sm, (0, 0), e.get("blur", 5) * sink + 0.01)
            bl = cv2.resize(sm, (W, H), interpolation=cv2.INTER_LINEAR)
            canvas = lerp(canvas, bl, clamp(sink * 1.5))
            canvas = canvas * (1 - e.get("dim", 0.72) * sink) + self.bg * e.get("dim", 0.72) * sink
            self.draw_end(canvas, t)
        if a["kind"] == "solo":
            self.draw_caption(canvas, t, a)
        if t < 0.18:
            canvas *= t / 0.18
        return np.clip(canvas, 0, 255).astype(np.uint8)

    def draw_caption(self, canvas, t, a):
        m, st = self.m, self.m["_style"]
        cs = st.get("caption", {})
        c = m["clips"][a["solo"]]
        if not c.get("caption"):
            return
        if a["name"] not in self.caps:
            self.caps[a["name"]] = caption_layer(m, c)
        bgr, al = self.caps[a["name"]]
        W, H = m["frame"]
        k = H / 1080.0
        mx, my = (v * k for v in cs.get("margin", [64, 64]))
        nxt = self.acts[a["i"] + 1] if a["i"] + 1 < len(self.acts) else None
        end = a["t1"] - (nxt["lead"] if nxt else 0)
        if nxt and nxt["kind"] == "solo" and m["solo_transition"] != "cut":
            end -= solo_window(m, self.beat) / 2
        t_in = a["t0"] + cs.get("delay", 0.12)
        if a["i"] and m["solo_transition"] != "cut":
            t_in += solo_window(m, self.beat) / 2
        u_in = ease_out((t - t_in) / cs.get("in_sec", 0.35))
        u_out = clamp((end - t) / cs.get("out_sec", 0.18))
        op = u_in * u_out
        if op <= 0:
            return
        h, w = bgr.shape[:2]
        x = mx - (1 - u_in) * 40 * k
        y = H - my - h
        if c.get("caption_at", cs.get("anchor", "bottom-left")) == "top-left":
            y = my
        paste(canvas, bgr, al, x, y, op)

    def draw_end(self, canvas, t):
        a = [x for x in self.acts if x["kind"] == "end"]
        if not a:
            return
        a = a[0]
        if self.end is None:
            self.end = end_layers(self.m)
        for (bgr, al), (x, y), at in self.end:
            u = (t - (a["t0"] + at * self.beat)) / 0.45
            if u <= 0:
                continue
            s = ease_back(u, 1.4) if at == 0 else 1.0
            op = ease_out(u * 1.4)
            if abs(s - 1) > 1e-3:
                h, w = bgr.shape[:2]
                ss = max(0.05, s)
                b2 = cv2.resize(bgr, (max(1, int(w * ss)), max(1, int(h * ss))))
                a2 = cv2.resize(al, (b2.shape[1], b2.shape[0]))[:, :, None]
                paste(canvas, b2, a2, x + (w - b2.shape[1]) / 2, y + (h - b2.shape[0]) / 2, op)
            else:
                dy = (1 - ease_out(u)) * 18 * self.m["frame"][1] / 1080.0
                paste(canvas, bgr, al, x, y + dy, op)

    def close(self):
        self.feeds.close()


# ------------------------------------------------------------------ music, arranged from the acts
def matches(spec, act):
    spec = spec if isinstance(spec, list) else [spec]
    return "all" in spec or act["name"] in spec or act["kind"] in spec


def shifted(ev, beat0):
    """A score event moved to start at beat0 (its own beats count from 0)."""
    e = dict(ev)
    t = e.get("type", "notes")
    if t == "notes":
        e["shift"] = float(e.get("shift", 0)) + beat0
    elif t in ("roll", "gliss"):
        e["from"] += beat0
        e["to"] += beat0
    elif t in ("strum", "arp"):
        e["at"] += beat0
    elif t == "drums":
        e["from"] = e.get("from", 0) + beat0
    return e


def restrikes(ev):
    """A held chord, struck again every `repeat.every` beats until `repeat.until`, each a little
    softer (`repeat.decay`). Every GM sample here is 3.1 s long, so a note written longer than
    that simply stops: the closing chords fell silent 2.5 s before the end card did."""
    r = ev.get("repeat")
    if not r or ev.get("type", "notes") != "notes":
        return [ev]
    out = []
    every, until, decay = float(r["every"]), float(r["until"]), float(r.get("decay", 0.85))
    k, b = 0, 0.0
    while b < until - 1e-6:
        e = {x: y for x, y in ev.items() if x != "repeat"}
        e["shift"] = float(ev.get("shift", 0)) + b
        e["vel"] = ev.get("vel", 0.5) * decay**k
        notes = []
        for part in ev["notes"].split(";"):
            f = part.split()
            if len(f) > 3:
                f[3] = "%.3f" % (float(f[3]) * decay**k)
            notes.append(" ".join(f))
        e["notes"] = "; ".join(notes)
        out.append(e)
        k += 1
        b += every
    return out


def arrange(m, acts, beat):
    """The score and the cues for these acts: (score, cues, report lines)."""
    mu = m["_music"]
    total_b = acts[-1]["b1"]
    gap_b = mu.get("gap_beats", 1.0)
    gaps = []  # beats [g0, g1) where the drop holds its breath
    for a in acts[1:]:
        if matches(mu.get("gap_before", []), a):
            gaps.append((a["b0"] - gap_b, a["b0"]))

    def in_gap(b, layer):
        return layer.get("gap", True) and any(g0 <= b < g1 for g0, g1 in gaps)

    # where each act's patterns count from: a run of solo shots is one section, so the
    # progression runs on across them; every grid (each drop) and the end start on the one
    anchor, prev = {}, None
    for a in acts:
        same = prev is not None and prev["kind"] == a["kind"] == "solo"
        anchor[a["i"]] = anchor[prev["i"]] if same else a["b0"]
        prev = a
    events = []
    report = []
    for L in mu.get("layers", []):
        pat = A.parse_notes(L["notes"])
        n = float(L.get("len", 16))
        out = []
        for a in acts:
            if not matches(L.get("acts", "all"), a):
                continue
            g = (L.get("gain") or {}).get(a["name"], (L.get("gain") or {}).get(a["kind"], 1.0))
            r0 = anchor[a["i"]]
            r = r0 + math.floor((a["b0"] - r0) / n) * n
            while r < a["b1"]:
                for b, ms, d, v in pat:
                    gb = r + b
                    if a["b0"] <= gb < a["b1"] and not in_gap(gb, L):
                        vv = (v if v is not None else L.get("vel", 0.5)) * g
                        dd = min(d, a["b1"] - gb) if L.get("cut_at_act", False) else d
                        names = "+".join(A.NAMES[x % 12] + str(x // 12 - 1) for x in ms)
                        out.append("%.4f %s %.4f %.3f" % (gb, names, dd, vv))
                r += n
        if out:
            ev = {
                "inst": L["inst"],
                "vel": L.get("vel", 0.5),
                "notes": "; ".join(out),
                "humanize": L.get("humanize", False),
            }
            if "transpose" in L:
                ev["transpose"] = L["transpose"]
            events.append(ev)
            report.append("  %-22s %4d notes" % (L.get("name", L["inst"]), len(out)))
    nd = 0
    for D in mu.get("drums", []):
        bpb, steps = D.get("beats_per_bar", 4), D.get("steps", 16)
        for a in acts:
            if not matches(D.get("acts", "all"), a):
                continue
            b = a["b0"]
            while b < a["b1"] - 1e-6:
                left = a["b1"] - b
                for g0, _g1 in gaps:  # stop at a drop's breath
                    if b < g0 < b + bpb:
                        left = min(left, g0 - b)
                if any(g0 <= b < g1 for g0, g1 in gaps):
                    b += min(bpb, max(gap_b, 0.25))
                    continue
                span = min(bpb, left)
                k = int(round(steps * span / bpb))
                if k <= 0:
                    break
                kit = {p: s.replace(" ", "")[:k] for p, s in D["kit"].items()}
                events.append(
                    {
                        "type": "drums",
                        "from": b,
                        "bars": 1,
                        "beats_per_bar": span,
                        "steps": k,
                        "kit": kit,
                        "vel": D.get("vel", 0.8),
                        "gains": D.get("gains", {}),
                    }
                )
                nd += 1
                b += span
    report.append("  %-22s %4d bars" % ("drums", nd))
    for h in mu.get("hits", []):
        for a in acts:
            if a["i"] == 0 and not h.get("first", False):
                continue
            if matches(h.get("on", []), a):
                for ev in h["events"]:
                    for e2 in restrikes(ev):
                        events.append(shifted(e2, a["b0"] + h.get("at", 0)))
    score = {
        "bpm": m["bpm"],
        "instruments": mu.get("instruments", {}),
        "drum_gain": mu.get("drum_gain", 0.55),
        "events": events,
    }
    cues = []
    fx = mu.get("sfx", {})
    tr = m["solo_transition"]
    for a in acts:
        names = []
        if a["kind"] == "solo" and a["i"]:
            names = [tr, "solo"]
        elif a["kind"] in ("grid", "end"):
            names = [a["kind"], a["name"]]
        elif a["i"] == 0:
            names = ["open"]
        for nm in names:
            for c in fx.get(nm, []):
                c = dict(c)
                at = c.pop("at", 0.0)
                c["t"] = max(0.0, a["t0"] + at * beat + c.pop("dt", 0.0))
                if "sec_beats" in c:
                    c.setdefault("args", {})["sec"] = c.pop("sec_beats") * beat
                cues.append(c)
        if a["kind"] == "grid":  # a soft tick for each cell that arrives
            entering = [k for k in a["cells"] if k not in acts[a["i"] - 1]["cells"]]
            for j, _k in enumerate(entering):
                for c in fx.get("cell", []):
                    c = dict(c)
                    c["t"] = (
                        a["t0"]
                        - a["lead"]
                        + j * m["_style"].get("grid", {}).get("stagger", 0.06)
                        + c.pop("dt", 0.0)
                        + 0.12
                    )
                    c["pan"] = -0.5 + (j % 4) / 3.0
                    cues.append(c)
    report.append("  %-22s %4d cues" % ("sound effects", len(cues)))
    return score, cues, report, total_b


def limit(x, ceil, look=0.005, release=0.12):
    """A look-ahead peak limiter: the gain falls ahead of every peak over the 4x-oversampled
    signal (inter-sample peaks are what an AAC encode turns into clipping) and recovers over
    `release` seconds. Gain reduction, not waveshaping: a soft clipper here added the very
    overtones that came back from the encoder 4 dB over full scale.
    """
    from scipy.ndimage import maximum_filter1d
    from scipy.signal import resample_poly

    up = np.abs(resample_poly(x, 4, 1, axis=1)).max(axis=0)
    env = up.reshape(-1, 4).max(axis=1)[: x.shape[1]]
    n = max(1, int(look * SR))
    need = np.minimum(1.0, ceil / np.maximum(maximum_filter1d(env, 2 * n + 1), 1e-9))
    cur = 1.0
    dec = 48  # the release smoother is a Python loop: run it at SR/48 and interpolate back
    small = need.reshape(-1)[: len(need) // dec * dec].reshape(-1, dec).min(axis=1)
    gs = np.empty_like(small)
    rr = 1 - math.exp(-dec / (release * SR))
    for i, v in enumerate(small):
        cur = v if v < cur else cur + (v - cur) * rr
        gs[i] = cur
    g = np.minimum(need, np.interp(np.arange(len(need)), np.arange(len(gs)) * dec + dec / 2, gs))
    return x * g


def music(m, acts, beat, out_wav):
    mu = m["_music"]
    score, cues, report, _ = arrange(m, acts, beat)
    bad = A.check_score(score)
    if bad:
        sys.exit("music %s: %s" % (m["_music_path"], "; ".join(bad)))
    dur = acts[-1]["t1"]
    ev = A.score_events(score)
    need = A.needed_samples(ev)
    miss, got = A.fetch_samples(need)
    if miss:
        print("  fetched %d of %d missing notes" % (got, miss))
    mix = {
        "reverb_sec": 2.2,
        "music_reverb": 0.75,
        "sfx_reverb": 0.6,
        "music_db": 0.0,
        "sfx_db": 0.0,
        **mu.get("mix", {}),
    }
    dry, wet, _ = A.render_score(score, dur)
    ir = A.make_ir(mix["reverb_sec"])
    mus = A.hp(dry + A.reverb(wet, ir) * mix["music_reverb"], 30)
    sfx, swet = A.render_sfx(cues, dur)
    sfx = sfx + A.reverb(swet, ir) * mix["sfx_reverb"]
    out = mus * 10 ** (mix["music_db"] / 20) + sfx * 10 ** (mix["sfx_db"] / 20)
    k = int(mix.get("fade_out", 1.2) * SR)
    out[:, -k:] *= np.linspace(1, 0, k) ** 1.6
    out = out / (np.abs(out).max() + 1e-9) * 0.89
    pre = out_wav.replace(".wav", ".pre.wav")
    _sketch.write_wav(pre, out)
    ms = mu.get("master", {})
    # one gain to the target loudness and a soft ceiling on the peaks. loudnorm falls back to its
    # dynamic mode whenever the true-peak target binds (the kicks), and that flattened an 8 dB
    # build from the solo shots to the grids into 2 dB; the build is the point of the music
    lufs0, _ = A.measure(pre)
    y = out * 10 ** ((ms.get("lufs", -14.0) - float(lufs0)) / 20)
    _sketch.write_wav(out_wav, limit(y, 10 ** (ms.get("tp", -1.0) / 20) * 0.9))
    lufs, peak = A.measure(out_wav)
    print("\n".join(report))
    print("  music: %s LUFS, %s dBTP -> %s" % (lufs, peak, rel(out_wav)))
    return out_wav


# ------------------------------------------------------------------ --list
def listing(m, acts, beat, windows, wraps, items):
    W, H = m["frame"]
    print(
        "%s  option %s%s  %dx%d %gfps  %g bpm (beat %.3fs, bar %.2fs)  transitions: %s"
        % (
            m["_id"],
            m["_option"],
            " (raw)" if m["_raw"] else "",
            W,
            H,
            m["fps"],
            m["bpm"],
            beat,
            beat * 4,
            m["solo_transition"],
        )
    )
    print("  music %s   look %s" % (m["_music_path"], m.get("style")))
    print(
        "\n  %-9s %-5s %8s %8s %6s %6s  %s"
        % ("act", "kind", "start", "length", "beats", "bars", "what")
    )
    for a in acts:
        if a["kind"] == "solo":
            c = m["clips"][a["solo"]]
            what = '%s  "%s"' % (a["solo"], " / ".join(c.get("caption") or []))
        elif a["kind"] == "grid":
            prev = acts[a["i"] - 1]["cells"] if a["i"] else {}
            new = [k for k in a["cells"] if k not in prev]
            what = "%d cells, new: %s" % (len(a["cells"]), ", ".join(new))
        else:
            what = "card over the last grid"
        print(
            "  %-9s %-5s %8s %7.2fs %6g %6g  %s"
            % (
                a["name"],
                a["kind"],
                fmt(a["t0"]),
                a["t1"] - a["t0"],
                a["beats"],
                a["beats"] / 4,
                what,
            )
        )
    total = acts[-1]["t1"]
    print("  %-9s %-5s %8s" % ("end", "", fmt(total)))
    durs = probe(m)
    print("\n  %-18s %7s  %s" % ("clip", "film", "windows played (film seconds)"))
    for key, wins in windows.items():
        c = m["clips"][key]
        ws = "  ".join("%.1f-%.1f" % (a, b) for a, b in wins)
        print(
            "  %-18s %6.0fs  %s%s"
            % (key, durs[key], ws, "  (tall, contain)" if c["fit"] == "contain" else "")
        )
    unused = [k for k in m["clips"] if k not in windows]
    if unused:
        print("  not in this reel: %s" % ", ".join(unused))
    for key, t, at, back in wraps:
        print(
            "  WRAP  %s at %s: its film ends at %.1f s, back to %.1f s (add a jump)"
            % (key, fmt(t), at, back)
        )
    miss = [p for p in items if not os.path.exists(p[3])]
    print(
        "\n  pieces: %d, %d not cut yet%s"
        % (len(items), len(miss), " (run --fetch)" if miss else "")
    )
    print(
        "  render: %s"
        % _encode.describe(_encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {}))))
    )


def out_path(m):
    name = "%s-%s%s" % (m["_id"], m["_option"], "-raw" if m["_raw"] else "")
    return os.path.join(m["_dir"], "outputs", name + ".mp4")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--option", help="which of the manifest's options (music + transitions)")
    ap.add_argument(
        "--raw", action="store_true", help="the short raw cut: the manifest's raw lengths and frame"
    )
    ap.add_argument(
        "--list", action="store_true", help="the acts, beats and film windows; render nothing"
    )
    ap.add_argument(
        "--fetch", action="store_true", help="cut the pieces of each film this reel plays"
    )
    ap.add_argument(
        "--frame", type=float, metavar="T", help="one frame at T seconds -> PNG in temp/"
    )
    ap.add_argument("--music", action="store_true", help="arrange and render the music only")
    ap.add_argument(
        "--remux",
        action="store_true",
        help="new music under the existing render, its picture stream-copied (a sound-only fix)",
    )
    ap.add_argument("-j", "--jobs", type=int, default=4, help="pieces cut at once (default 4)")
    args = ap.parse_args()

    m = load(args.manifest, args.option, args.raw)
    acts, beat = timeline(m)
    frames, windows, wraps = plan(m, acts, beat)
    items = pieces(m, windows)
    if args.list:
        listing(m, acts, beat, windows, wraps, items)
        score, cues, report, _ = arrange(m, acts, beat)
        print("\n  music, arranged from these acts:")
        print("\n".join(report))
        return
    if args.remux:  # the music only, under a render that already exists: no film is read
        wav = os.path.join(
            m["_dir"], "audio", "showreel-%s%s.wav" % (m["_option"], "-raw" if m["_raw"] else "")
        )
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        music(m, acts, beat, wav)
        return remux(m, acts, wav)
    fetch(m, items, args.jobs)
    if args.fetch:
        return
    os.makedirs(os.path.join(m["_dir"], "outputs"), exist_ok=True)
    os.makedirs(os.path.join(m["_dir"], "temp"), exist_ok=True)
    if args.frame is not None:
        i = min(len(frames) - 1, int(round(args.frame * m["fps"])))
        p = Painter(m, acts, beat, items)
        img = p.draw(i / m["fps"], frames[i])
        p.close()
        dst = os.path.join(m["_dir"], "temp", "showreel-%s-%.2f.png" % (m["_option"], args.frame))
        cv2.imwrite(dst, img)
        print("  frame %.2f s (%s) -> %s" % (args.frame, act_at(acts, args.frame)["name"], dst))
        return
    wav = os.path.join(
        m["_dir"], "audio", "showreel-%s%s.wav" % (m["_option"], "-raw" if m["_raw"] else "")
    )
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    music(m, acts, beat, wav)
    if args.music:
        return
    render(m, acts, beat, frames, items, wav, args)


def remux(m, acts, wav):
    """The render's picture, stream-copied, with this music under it: a change to the music
    costs seconds, not a re-render of every frame."""
    dst = out_path(m)
    if not os.path.exists(dst):
        sys.exit("--remux: no render at %s yet" % rel(dst))
    cfg = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    tmp = dst + ".part.mp4"
    cmd = (
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", dst, "-i", wav]
        + ["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-shortest"]
        + _encode.audio_args(cfg)
        + ["-movflags", "+faststart", "-y", tmp]
    )
    subprocess.run(cmd, check=True)
    got = probe_duration(tmp)
    if abs(got - acts[-1]["t1"]) > 0.25:
        sys.exit("the remux is %.2f s, the reel %.2f s" % (got, acts[-1]["t1"]))
    os.replace(tmp, dst)
    print("  new music under %s (%.1f s)" % (dst, got))
    _project.record(
        m["_id"],
        "showreel %s%s: music replaced under the same picture"
        % (m["_option"], " raw cut" if m["_raw"] else ""),
        out=dst,
        script=__file__,
        argv=sys.argv[1:],
        kind="video",
        manifest=m["_path"],
        sidecars={"music": wav},
    )


def probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    return float(r.stdout.strip() or 0)


def render(m, acts, beat, frames, items, wav, args):
    W, H = m["frame"]
    fps = m["fps"]
    dst = out_path(m)
    tmp = dst + ".part.mp4"
    runtime = len(frames) / fps
    cfg = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    prog = _progress.begin(m["_id"], runtime, rel(dst))
    cmd = (
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "warning",
            "-progress",
            prog,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            "%dx%d" % (W, H),
            "-r",
            "%g" % fps,
            "-i",
            "-",
            "-i",
            wav,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-shortest",
        ]
        + _encode.video_args(cfg)
        + _encode.audio_args(cfg)
        + ["-movflags", "+faststart", "-y", tmp]
    )
    print(
        "\n  rendering %s  (%s, %d frames, %s)"
        % (rel(dst), fmt(runtime), len(frames), _encode.describe(cfg))
    )
    t0 = time.time()
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p = Painter(m, acts, beat, items)
    try:
        for i, row in enumerate(frames):
            ff.stdin.write(p.draw(i / fps, row).tobytes())
            if i and i % (fps * 5) == 0:
                el = time.time() - t0
                print(
                    "    %s of %s  (%.1fx realtime)" % (fmt(i / fps), fmt(runtime), (i / fps) / el),
                    flush=True,
                )
    finally:
        p.close()
        ff.stdin.close()
        ff.wait()
        _progress.end(m["_id"])
    if ff.returncode:
        sys.exit("ffmpeg failed (%d)" % ff.returncode)
    os.replace(tmp, dst)
    got = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
            capture_output=True,
            text=True,
        ).stdout.strip()
        or 0
    )
    if abs(got - runtime) > 0.25:
        sys.exit("the render is %.2f s, the reel %.2f s" % (got, runtime))
    print("  done in %.0f s: %s (%.1f s)" % (time.time() - t0, dst, got))
    _project.record(
        m["_id"],
        "showreel %s%s rendered (%s, %d acts, %g bpm)"
        % (m["_option"], " raw cut" if m["_raw"] else "", fmt(got), len(acts), m["bpm"]),
        out=dst,
        script=__file__,
        argv=sys.argv[1:],
        kind="video",
        manifest=m["_path"],
        sidecars={"music": wav},
        note="option %s: music %s, solo transitions %s"
        % (m["_option"], m["_music_path"], m["solo_transition"]),
    )


if __name__ == "__main__":
    main()
