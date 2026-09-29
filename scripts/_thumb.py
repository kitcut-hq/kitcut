"""Thumbnail options from a film's own stills: which frame, where the words go, how they look,
and proof that the result reads where YouTube shows it smallest.

The picture is always a frame of the film itself. The words are laid out here, in Python, with
the same font files the browser paints them with -- so the line breaks, the font size and the
cap height are numbers this module chose, not whatever a page happened to do -- and the browser
only paints them (config/thumbnails/layouts/*.svg; one headless shot holds every option). Each
layer is shot twice, as it will look and as a bare white mask of its letters, and the checks
read the finished picture through the mask.

    stills     clean frames of a sketch film: its manifest copied without the Free plan's
               closing mark ("tail") and rendered by sketch-render.py --stills
    moments    the times a writer chooses from, and the labelled sheet it sees them on
    concepts   four {at, words, layout}, checked: inside the film, apart, short, not the title
    settle     the frame near a moment that is not mid-transition, and not a thin one
    layout     font (glyphs covered), size, line breaks, the quietest place, the colours
    paint      one browser shot of every layer and every mask
    checks     cap height at 168 px, contrast, YouTube's overlays, overflow, file size
    fallbacks  a scrim, then a slab, then the still alone -- an option that fails is never shown

Config: config/thumbnails/thumbnails.json. CLI: scripts/thumb-options.py. Studio:
studio/thumbs.py. Self-test: scripts/check-thumbnail.py.
"""

import os
import re
import sys
import json
import math
import time
import shutil
import colorsys
import hashlib
import difflib
import pathlib
import importlib
import itertools
import subprocess
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont  # noqa: E402

CONFIG = "config/thumbnails/thumbnails.json"
LAYOUT_DIR = "config/thumbnails/layouts"
LAYOUTS = ("headline", "slab", "panel", "still")
WORD = re.compile(r"[\w'’-]+", re.UNICODE)
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "the", "this", "to", "what", "why", "with", "you", "your",
}  # fmt: skip

_CFG = None
_CACHE = {}


def cfg():
    global _CFG
    if _CFG is None:
        with open(_env.resolve(CONFIG), encoding="utf-8") as f:
            _CFG = json.load(f)
    return _CFG


def size():
    return tuple(cfg()["size"])


# ------------------------------------------------------------------ colour
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def rgb_hex(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in c[:3])


def _lin(v):
    v = np.asarray(v, dtype="float64") / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    """WCAG relative luminance of one colour (0..1)."""
    r, g, b = (_lin(x) for x in rgb[:3])
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


def luminance_map(img):
    a = _lin(np.asarray(img.convert("RGB")))
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def contrast(l1, l2):
    """WCAG contrast ratio between two luminances (arrays broadcast)."""
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def fit_contrast(rgb, against, target):
    """`rgb` moved in lightness, away from `against`, until the two reach `target` contrast --
    so an accent stays its own hue but can be read on what it sits on."""
    la = luminance(against)
    h, l, s = colorsys.rgb_to_hls(*(v / 255.0 for v in rgb[:3]))
    step = 0.03 if la < 0.18 else -0.03  # brighten on a dark ground, darken on a light one
    for _ in range(40):
        c = tuple(v * 255 for v in colorsys.hls_to_rgb(h, l, s))
        if float(contrast(luminance(c), la)) >= target:
            return c
        l = min(1.0, max(0.0, l + step))
    return c


def _small(img, w=240):
    h = max(1, round(img.height * w / img.width))
    return img.convert("RGB").resize((w, h), Image.BILINEAR)


def accent_colour(img):
    """The film's own accent: the vivid colour that stands out -- the yellow stars on a night
    sky, the red of a crossed-out weekend on a white app screen -- or the default when the frame
    has none (pencil on paper, a dark wine film).

    Each vivid colour (quantised, on a 320-px copy so a few small stars still count) scores its
    pixel count ** 0.3 times its Lab distance from the frame's mean ** 1.5: difference outweighs
    area. The ground's own hue is never the accent -- a blueprint's blue is everywhere on it. Of
    four scorings compared on twelve frames of eight films (2026-09-29), this one picked the
    colour that pops on nine; count-weighted ones picked the sky, the trunk or the paper."""
    c = cfg()["colours"]
    sm = img.convert("RGB").resize((320, 180), Image.BILINEAR)
    hsv = np.asarray(sm.convert("HSV"), dtype="float64") / 255.0
    rgb = np.asarray(sm, dtype="float64")
    lab = np.asarray(sm.convert("LAB"), dtype="float64")
    vivid = (hsv[..., 1] > c["accent_min_sat"]) & (hsv[..., 2] > c["accent_min_val"])
    if vivid.sum() < 5:
        return hex_rgb(c["accent_default"])
    frame = lab.reshape(-1, 3).mean(axis=0)
    gh, gs, _ = colorsys.rgb_to_hsv(*(np.asarray(ground_colour(img)) / 255.0))
    pix, lpix = rgb[vivid], lab[vivid]
    q = (pix // 32).astype(int)
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    best, mean = -1.0, None
    for k in np.unique(keys):
        m = keys == k
        if m.sum() < max(5, 0.0005 * rgb.shape[0] * rgb.shape[1]):
            continue
        col = pix[m].mean(axis=0)
        h, s_, _ = colorsys.rgb_to_hsv(*(col / 255.0))
        if gs > 0.25 and min(abs(h - gh), 1 - abs(h - gh)) < c["accent_ground_hue"] / 360:
            continue  # the ground's own colour
        score = m.sum() ** 0.3 * float(np.linalg.norm(lpix[m].mean(axis=0) - frame)) ** 1.5
        if score > best:
            best, mean = score, col
    if mean is None:
        return hex_rgb(c["accent_default"])
    h, s, v = colorsys.rgb_to_hsv(*(mean / 255.0))
    return tuple(x * 255 for x in colorsys.hsv_to_rgb(h, max(s, 0.62), max(v, 0.82)))


def ground_colour(img):
    """The frame's commonest colour -- on a drawn film, its paper."""
    rgb = np.asarray(_small(img, 160), dtype="float64").reshape(-1, 3)
    q = (rgb // 24).astype(int)
    keys = q[:, 0] * 4096 + q[:, 1] * 64 + q[:, 2]
    top = np.bincount(keys).argmax()
    return tuple(rgb[keys == top].mean(axis=0))


# ------------------------------------------------------------------ fonts
def font_chain(look):
    f = cfg()["fonts"]
    return list(f.get(look) or []) + list(f["fallback"])


def _cmap(path):
    k = ("cmap", path)
    if k not in _CACHE:
        from fontTools.ttLib import TTFont

        t = TTFont(_env.resolve(path), lazy=True)
        os2 = t["OS/2"]
        _CACHE[k] = (
            set(t.getBestCmap()),
            (getattr(os2, "sCapHeight", 0) or 0.7 * t["head"].unitsPerEm) / t["head"].unitsPerEm,
        )
    return _CACHE[k]


def covers(path, text):
    cmap = _cmap(path)[0]
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


def cap_ratio(path):
    return _cmap(path)[1]


def pick_font(text, look):
    """The first font of the look that has a glyph for every character, as a spec dict."""
    for spec in font_chain(look):
        t = text.upper() if spec.get("upper") else text
        if covers(spec["file"], t):
            return spec
    return None


def pil_font(path, px):
    k = ("pil", path, px)
    if k not in _CACHE:
        _CACHE[k] = ImageFont.truetype(_env.resolve(path), px)
    return _CACHE[k]


def font_uri(path):
    return pathlib.Path(_env.resolve(path)).resolve().as_uri()


# ------------------------------------------------------------------ words
def tokens(words):
    """Each word as its runs: "Can't *sleep*?" -> [[("Can't", False)], [("sleep", True),
    ("?", False)]]. A *starred* part takes the accent colour; what hugs it (a ?, a comma)
    does not."""
    out = []
    for w in (words or "").split():
        m = re.fullmatch(r"([^*]*)\*([^*]+)\*([^*]*)", w)
        if m:
            segs = ((m.group(1), False), (m.group(2), True), (m.group(3), False))
            out.append([x for x in segs if x[0]])
        else:
            out.append([(w.replace("*", ""), False)])
    return out


def word_text(segs):
    return "".join(t for t, _ in segs)


def plain(words):
    return " ".join(word_text(w) for w in tokens(words))


def word_count(words):
    return len(WORD.findall(plain(words)))


def title_overlap(words, title):
    """Share of the thumbnail's content words that the title already says."""
    w = [x.lower() for x in WORD.findall(plain(words)) if x.lower() not in STOP]
    if not w:
        return 0.0
    t = {x.lower() for x in WORD.findall(title or "")}
    return sum(1 for x in w if x in t) / len(w)


# ------------------------------------------------------------------ concepts
def check_concepts(raw, length, title=""):
    """Four {at, words, layout} held to the rules: (concepts, notes, problems).

    `notes` are what was put right here; `problems` ({n, text}; n is the thumbnail, None for
    all of them) are what only the writer can fix -- words that are too long or repeat the
    title, moments on top of each other. A draft is asked once more with them; what survives a
    second answer is fixed up by fill_concepts()."""
    c, notes, problems = cfg(), [], []
    edge = cfg()["moments"]["edge"]
    items = [x for x in (raw if isinstance(raw, list) else []) if isinstance(x, dict)]
    if len(items) != 4:
        problems.append(
            {"n": None, "text": "give exactly four thumbnails (you gave %d)" % len(items)}
        )
    items = items[:4]
    out = []
    for i, x in enumerate(items, 1):
        try:
            at = float(x.get("at"))
        except (TypeError, ValueError):
            problems.append({"n": i, "text": "thumbnail %d has no time" % i})
            continue
        if not math.isfinite(at) or at < -1 or at > length + 1:
            problems.append(
                {"n": i, "text": "thumbnail %d is at %.1f s, outside the film" % (i, at)}
            )
            continue
        lo, hi = edge, max(edge, length - edge)
        if not lo <= at <= hi:
            notes.append("thumbnail %d moved from %.2f s inside the film" % (i, at))
            at = min(hi, max(lo, at))
        lay = str(x.get("layout") or "").strip().lower()
        words = " ".join(str(x.get("words") or "").split())
        stars = re.findall(r"\*[^*\s]+\*", words)
        if len(stars) > 1:
            for s in stars[1:]:
                words = words.replace(s, s.strip("*"), 1)
            notes.append("thumbnail %d: one highlighted word kept" % i)
        where = str(x.get("place") or "").strip().lower() or None
        if where and where not in cfg()["places"]:
            notes.append(
                "thumbnail %d: place %r is not one of %s" % (i, where, ", ".join(cfg()["places"]))
            )
            where = None
        out.append({"at": round(at, 2), "words": words, "layout": lay, "place": where})
    # one of each layout: an unknown or repeated one takes a layout nobody used
    seen = set()
    for o in out:
        if o["layout"] in LAYOUTS:
            seen.add(o["layout"])
    free = [x for x in c["concepts"]["layouts"] if x not in seen]
    taken = set()
    for o in out:
        if o["layout"] not in LAYOUTS or o["layout"] in taken:
            if free:
                notes.append("a %r thumbnail became %r" % (o["layout"] or "?", free[0]))
                o["layout"] = free.pop(0)
        taken.add(o["layout"])
    w = c["words"]
    for i, o in enumerate(out, 1):
        if o["layout"] == "still":
            if o["words"]:
                notes.append("thumbnail %d is the picture alone: its words were dropped" % i)
            o["words"] = ""
            continue
        n = word_count(o["words"])
        if n == 0:
            problems.append({"n": i, "text": "thumbnail %d (%s) needs words" % (i, o["layout"])})
        elif n > w["max_words"] or len(plain(o["words"])) > w["max_chars"]:
            problems.append({"n": i, "text": "thumbnail %d's words %r are too long: at most %d words, %d characters"
                             % (i, plain(o["words"]), w["max_words"], w["max_chars"])})  # fmt: skip
        ov = title_overlap(o["words"], title)
        if ov > w["title_overlap_max"]:
            problems.append({"n": i, "text": "thumbnail %d's words %r repeat the title: say what the title does not"
                             % (i, plain(o["words"]))})  # fmt: skip
    ats = sorted(o["at"] for o in out)
    gap = c["concepts"]["min_gap"]
    if any(b - a < gap for a, b in zip(ats, ats[1:])):
        problems.append({"n": None, "text": "the four moments must be at least %.0f s apart" % gap})
    return out, notes, problems


def fill_concepts(concepts, moments, length):
    """What a writer's answer could not supply, made up from the film: a missing thumbnail is
    the picture alone at a moment nobody chose, and moments too close together are spread."""
    gap = cfg()["concepts"]["min_gap"]
    out = []
    for o in concepts:
        if all(abs(o["at"] - p["at"]) >= gap for p in out):
            out.append(dict(o))
    spare = [t for t in moments if all(abs(t - p["at"]) >= gap for p in out)]
    for t in spread(spare, 4 - len(out)):
        out.append({"at": round(t, 2), "words": "", "layout": "still"})
    return out[:4]


def spread(times, k):
    """k of `times`, evenly apart."""
    times = sorted(times)
    if k <= 0 or not times:
        return []
    if len(times) <= k:
        return times
    return [times[round(i * (len(times) - 1) / max(1, k - 1))] for i in range(k)]


def auto_concepts(length, fractions=(0.25, 0.5, 0.75)):
    """The baseline: the picture alone at fixed points of the film -- about what YouTube offers
    when it picks for itself."""
    return [{"at": round(length * f, 2), "words": "", "layout": "still"} for f in fractions]


# ------------------------------------------------------------------ stills
def clean_manifest(film_dir, into):
    """A copy of the film's manifest that draws the film and nothing added after it: no Free
    plan closing, whose mark sits exactly where YouTube stamps the duration. Every path is made
    absolute (painted scenes included -- sketch-render finds them beside the manifest
    otherwise), and the copy renders into its own folder, never the film's outputs."""
    with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    m.pop("tail", None)

    def ab(p):
        return p if os.path.isabs(p) else os.path.join(film_dir, p)

    m["film"] = ab(m.get("film") or "film.js")
    # a font the film fetched for itself lives in the film (web/fonts/...); the tooling's own are
    # ROOT-relative (fonts/...) and stay as they are. Missing this failed the first real publish.
    m["fonts"] = [
        dict(f, file=ab(f["file"]))
        if isinstance(f, dict)
        and isinstance(f.get("file"), str)
        and not os.path.isabs(f["file"])
        and os.path.exists(ab(f["file"]))
        else f
        for f in m.get("fonts") or []
    ]
    for k in ("vo", "engine", "cast"):
        if isinstance(m.get(k), str):
            m[k] = ab(m[k])
    images = {k: ab(v) for k, v in (m.get("images") or {}).items()}
    paint = m.pop("paint", None)
    if paint:
        pj = paint
        if isinstance(paint, str):
            with open(ab(paint), encoding="utf-8") as f:
                pj = json.load(f)
        for im in pj.get("images") or []:
            name = str(im.get("name") or "")
            p = os.path.join(film_dir, "images", name + ".jpg")
            if re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name) and os.path.exists(p):
                images.setdefault(name, p)
    m["images"] = images
    audio = dict(m.get("audio") or {})
    audio["vo_timeline"] = ab(audio.get("vo_timeline") or "audio/vo/timeline.json")
    m["audio"] = {"vo_timeline": audio["vo_timeline"]}  # stills need no score or effects
    m["slug"] = "thumbs"
    os.makedirs(into, exist_ok=True)
    out = os.path.join(into, "sketch.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    return out


def film_key(film_dir):
    """What a film's frames depend on: a changed film gets new stills, an unchanged one keeps
    them (a finished film does not change, so this is nearly always a cache hit)."""
    h = hashlib.sha256()
    for rel in ("sketch.json", "film.js", "paint.json", "audio/vo/timeline.json"):
        p = os.path.join(film_dir, rel)
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(rel.encode() + b"\0" + f.read())
    for d in ("engine", "cast", "images"):
        p = os.path.join(film_dir, d)
        if os.path.isdir(p):
            for n in sorted(os.listdir(p)):
                st = os.stat(os.path.join(p, n))
                h.update(("%s/%s %d %d" % (d, n, st.st_size, int(st.st_mtime))).encode())
    return h.hexdigest()[:16]


def stills_dir(film_dir):
    return os.path.join(film_dir, "temp", "thumbs", "stills-" + film_key(film_dir))


def still_name(t):
    return "%06.2f.png" % t


def render_stills(film_dir, times, into=None, env=None, timeout=900):
    """{t: path} of clean 1920x1080 frames, rendering only the ones not already made. One
    browser run for all of them (~0.12 s a still after ~3 s of start-up)."""
    into = into or stills_dir(film_dir)
    os.makedirs(into, exist_ok=True)
    ts = sorted({round(float(t), 2) for t in times})
    have = {t: os.path.join(into, still_name(t)) for t in ts}
    need = [t for t, p in have.items() if not os.path.exists(p)]
    if need:
        man = clean_manifest(film_dir, os.path.join(into, "manifest"))
        cmd = _env.PY + [
            os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
            "--manifest",
            man,
            "--stills",
            ",".join("%.2f" % t for t in need),
            "--into",
            into,
        ]
        r = subprocess.run(
            cmd, env=env or _env.ENV, capture_output=True, text=True, timeout=timeout
        )
        missing = [t for t in need if not os.path.exists(have[t])]
        if missing:
            said = (r.stderr or r.stdout or "").strip().splitlines()[-6:]
            raise RuntimeError(
                "no still at %s: %s"
                % (", ".join("%.2f" % t for t in missing[:4]), " | ".join(said))
            )
    return have


def load_still(path):
    k = ("img", path)
    if k not in _CACHE:
        _CACHE[k] = Image.open(path).convert("RGB")
    return _CACHE[k]


# ------------------------------------------------------------------ moments
def narration(film_dir):
    """[{start, end, text}] as spoken, from the film's voice timeline ([] without one)."""
    p = os.path.join(film_dir, "audio", "vo", "timeline.json")
    try:
        with open(p, encoding="utf-8") as f:
            tl = json.load(f)
    except (OSError, ValueError):
        return []
    return [
        {
            "start": float(L.get("start") or 0),
            "end": float(L.get("end") or 0),
            "text": L.get("text") or "",
        }
        for L in tl.get("lines") or []
        if isinstance(L, dict)
    ]


def moment_times(lines, length):
    """The times a writer picks thumbnails from: just before each narration line ends (what
    the line talks about has been drawn by then), spread over the film, between min and max."""
    c = cfg()["moments"]
    lo, hi = c["edge"], max(c["edge"], length - c["edge"] - 0.1)
    ts = sorted(min(hi, max(lo, L["end"] - c["lead_out"])) for L in lines if L.get("end"))

    def dedupe(xs):
        out = []
        for t in sorted(xs):
            if not out or t - out[-1] >= c["min_gap"]:
                out.append(t)
        return out

    ts = dedupe(ts)
    if len(ts) > c["max"]:
        ts = spread(ts, c["max"])
    n = c["min"]
    while len(ts) < c["min"] and n <= 4 * c["min"]:
        grid = [lo + (hi - lo) * (i + 0.5) / n for i in range(n)]
        ts = dedupe(ts + [g for g in grid if all(abs(g - t) >= c["min_gap"] for t in ts)])
        n += 2
    return [round(t, 2) for t in ts[: c["max"]]]


def moments_sheet(stills, out, cols=4, tile=(480, 270)):
    """The moments as one labelled picture, times large enough for a writer to read."""
    ts = sorted(stills)
    rows = (len(ts) + cols - 1) // cols
    tw, th = tile
    sheet = Image.new("RGB", (cols * tw, max(1, rows) * th), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    f = pil_font("fonts/Montserrat-Bold.ttf", 30)
    for i, t in enumerate(ts):
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(load_still(stills[t]).resize(tile, Image.LANCZOS), (x, y))
        label = "%.1f s" % t
        w = d.textlength(label, font=f)
        d.rounded_rectangle([x + 8, y + 8, x + 28 + w, y + 52], radius=10, fill=(0, 0, 0))
        d.text((x + 18, y + 12), label, font=f, fill=(255, 255, 255))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(20, 20, 20), width=2)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=85)
    return out


# ------------------------------------------------------------------ settle
def _sig(img, w=96):
    return (
        np.asarray(img.convert("L").resize((w, w * 9 // 16), Image.BILINEAR), dtype="float32")
        / 255.0
    )


def detail(img):
    """How much is drawn: mean gradient of a 160x90 grey copy (a blank ground scores ~0)."""
    a = np.asarray(img.convert("L").resize((160, 90), Image.BILINEAR), dtype="float32") / 255.0
    return float(np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean())


def settle_times(at, length):
    """(candidates, every time to render): a few frames around `at`, each with a probe either
    side of it."""
    s, e = cfg()["settle"], cfg()["moments"]["edge"]
    lo, hi = e, max(e, length - e)
    cands = sorted({round(min(hi, max(lo, at + o)), 2) for o in s["offsets"]})
    probes = {
        round(min(length - 0.05, max(0.05, t + d)), 2)
        for t in cands
        for d in (-s["probe"], s["probe"])
    }
    return cands, sorted(set(cands) | probes)


def settle(at, stills, length):
    """The frame near `at` that is not moving: (t, score rows). A crossfade, a line still
    drawing itself or a camera move all show as a difference between the probes; among the
    still ones, a thin frame (a scene not drawn in yet, a fade) loses to a fuller one."""
    s = cfg()["settle"]
    cands, _ = settle_times(at, length)
    rows = []
    for t in cands:
        a = round(min(length - 0.05, max(0.05, t - s["probe"])), 2)
        b = round(min(length - 0.05, max(0.05, t + s["probe"])), 2)
        if t not in stills or a not in stills or b not in stills:
            continue
        motion = float(np.abs(_sig(load_still(stills[a])) - _sig(load_still(stills[b]))).mean())
        rows.append({"t": t, "motion": motion, "detail": detail(load_still(stills[t]))})
    if not rows:
        raise RuntimeError("no stills rendered near %.2f s" % at)
    full = max(r["detail"] for r in rows)
    ok = [r for r in rows if r["detail"] >= s["min_detail_frac"] * full] or rows
    best = min(ok, key=lambda r: (round(r["motion"], 4), -r["detail"], abs(r["t"] - at)))
    return best["t"], rows


# ------------------------------------------------------------------ where the words go
def detail_map(img, cell=8):
    """Per 8x8 cell, how busy the picture is there: gradient of the grey image, smoothed."""
    W, H = size()
    g = (
        np.asarray(img.convert("L").resize((W // cell, H // cell), Image.BILINEAR), dtype="float32")
        / 255.0
    )
    m = np.zeros_like(g)
    m[:, 1:] += np.abs(np.diff(g, axis=1))
    m[1:, :] += np.abs(np.diff(g, axis=0))
    from scipy import ndimage

    return ndimage.uniform_filter(m, size=3).astype("float32")


def subject_map(img, w=128):
    """Where the subjects are, on the detail map's grid, summing to 1: spectral-residual
    saliency (Hou & Zhang 2007) over the three Lab channels. Measured on the studio's films it
    finds the characters, the phone, the bottle and ignores repeated texture (hatching, a row of
    trees) on drawn and clean films; on painted ones it scatters and misses large subjects, so
    there the writer's `place` carries the placement and this only fine-tunes it."""
    from scipy import ndimage

    W, H = size()
    h = w * 9 // 16
    a = np.asarray(img.convert("LAB").resize((w, h), Image.BILINEAR), dtype="float64")
    out = np.zeros((h, w))
    for c in range(3):
        f = np.fft.fft2(a[..., c])
        amp, ph = np.log(np.abs(f) + 1e-9), np.angle(f)
        res = amp - ndimage.uniform_filter(amp, size=3, mode="wrap")
        out += ndimage.gaussian_filter(np.abs(np.fft.ifft2(np.exp(res + 1j * ph))) ** 2, 2.5)
    out = np.asarray(
        Image.fromarray(out.astype("float32")).resize((W // 8, H // 8), Image.BILINEAR)
    )
    return out / max(1e-12, float(out.sum()))


def ocr():
    if "ocr" not in _CACHE:
        from rapidocr_onnxruntime import RapidOCR

        _CACHE["ocr"] = RapidOCR()
    return _CACHE["ocr"]


def text_boxes(img):
    """The words the film itself draws in this frame, as pixel boxes grown a little: RapidOCR
    (local) on a half-size copy, 0.2-0.7 s a frame. Measured on the studio's films it finds
    headings, thin labels, handwriting, Cyrillic and a rotated bottle label. The thumbnail's own
    words, slabs and panels may cover none of them: a bake-off option that slid a panel over a
    wine film's "DEEP - FLORAL" and a slab over an app ad's "Month-end" is why (2026-09-29).
    Words under min_h_px tall are left to the subject map: an app's screen is full of them, and
    protecting every one left no room for a slab anywhere on it."""
    if "_text" in img.info:
        return img.info["_text"]
    W, H = size()
    t = cfg()["text"]
    small = img.convert("RGB").resize((W // 2, H // 2), Image.BILINEAR)
    res, _ = ocr()(np.asarray(small))
    out = []
    for item in res or []:
        box, score = item[0], float(item[2]) if len(item) > 2 else 1.0
        if score < t["min_score"]:
            continue
        xs, ys = [float(q[0]) * 2 for q in box], [float(q[1]) * 2 for q in box]
        if max(ys) - min(ys) < t["min_h_px"]:
            continue  # a phone's or a card's own small print: part of the picture, not a line to read
        g = t["grow_px"]
        out.append(
            (max(0, min(xs) - g), max(0, min(ys) - g), min(W, max(xs) + g), min(H, max(ys) + g))
        )
    img.info["_text"] = out
    return out


def text_grid(img, cell=8):
    """text_boxes on the detail map's grid: True where the film has words."""
    W, H = size()
    g = np.zeros((H // cell, W // cell), dtype=bool)
    for x0, y0, x1, y1 in text_boxes(img):
        g[
            int(y0 // cell) : int(math.ceil(y1 / cell)), int(x0 // cell) : int(math.ceil(x1 / cell))
        ] = True
    return g


def region(name):
    """A named part of the frame (`place` in a concept) as a pixel box, or None."""
    W, H = size()
    f = cfg()["places"].get(name or "")
    return (f[0] * W, f[1] * H, f[2] * W, f[3] * H) if f else None


def safe_rects():
    """(margins box, the duration badge's corner) in pixels."""
    W, H = size()
    s = cfg()["safe"]
    mx, my = round(W * s["margin_frac"][0]), round(H * s["margin_frac"][1])
    bottom = min(H - my, round(H * (1 - s["bar_frac"])))
    badge = (round(W * (1 - s["badge_frac"][0])), round(H * (1 - s["badge_frac"][1])), W, H)
    return (mx, my, W - mx, bottom), badge


def _hits(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def place(bw, bh, dmap, smap=None, area=None, centre_penalty=0.0, cell=8, tmap=None):
    """Where a bw x bh block goes, inside `area`, clear of the badge and of the film's own words
    (tmap): (x0, y0, busy, cover), or None. Busy is the mean detail under the block; cover is the
    share of the subjects (smap) it would hide. It goes where it hides least, then where it is
    quietest."""
    W, H = size()
    safe, badge = safe_rects()
    ax0, ay0, ax1, ay1 = area or safe
    ax0, ay0 = int(math.ceil(max(ax0, safe[0]))), int(math.ceil(max(ay0, safe[1])))
    ax1, ay1 = int(min(ax1, safe[2])), int(min(ay1, safe[3]))
    if bw > ax1 - ax0 or bh > ay1 - ay0:
        return None
    ii = np.pad(dmap, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    sm = smap if smap is not None else np.zeros_like(dmap)
    si = np.pad(sm, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    tm = tmap if tmap is not None else np.zeros(dmap.shape, dtype=bool)
    ti = np.pad(tm.astype("int32"), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    cw, ch = max(1, math.ceil(bw / cell)), max(1, math.ceil(bh / cell))
    best = None
    step = 2 * cell
    xs = list(range(ax0, ax1 - bw + 1, step)) + [ax1 - bw]
    ys = list(range(ay0, ay1 - bh + 1, step)) + [ay1 - bh]
    for y in ys:
        for x in xs:
            if _hits((x, y, x + bw, y + bh), badge):
                continue
            cx, cy = x // cell, y // cell
            cx1, cy1 = min(dmap.shape[1], cx + cw), min(dmap.shape[0], cy + ch)
            if ti[cy1, cx1] - ti[cy, cx1] - ti[cy1, cx] + ti[cy, cx]:
                continue  # it would hide words the film itself shows
            s = ii[cy1, cx1] - ii[cy, cx1] - ii[cy1, cx] + ii[cy, cx]
            busy = float(s / max(1, (cy1 - cy) * (cx1 - cx)))
            cover = float(si[cy1, cx1] - si[cy, cx1] - si[cy1, cx] + si[cy, cx])
            # a small nudge off dead centre, where the subject usually is
            dx = abs((x + bw / 2) / W - 0.5) * 2
            dy = abs((y + bh / 2) / H - 0.5) * 2
            score = cover + busy + centre_penalty * (1 - max(dx, dy)) * 0.01
            if best is None or score < best[4]:
                best = (x, y, busy, cover, score)
    return best[:4] if best else None


# ------------------------------------------------------------------ text blocks
def _splits(n, max_lines):
    """Every way to cut n words into 1..max_lines contiguous lines."""
    for k in range(1, min(n, max_lines) + 1):
        for cuts in itertools.combinations(range(1, n), k - 1):
            b = (0,) + cuts + (n,)
            yield [(b[i], b[i + 1]) for i in range(k)]


def block_at(toks, font, cap, max_w, max_h, max_lines, gap_frac, pad=0.0):
    """The words at cap height `cap` in the fewest, most even lines that fit max_w x max_h:
    a dict of lines with their widths and ink extents, or None."""
    ratio = cap_ratio(font["file"])
    px = max(8, round(cap / ratio))
    f = pil_font(font["file"], px)
    tr = font.get("tracking", 0.0) * px
    up = font.get("upper")
    words = [[(t.upper() if up else t, a) for t, a in segs] for segs in toks]
    best = None
    for sp in _splits(len(words), max_lines):
        lines = []
        for a, b in sp:
            ws = words[a:b]
            text = " ".join(word_text(w) for w in ws)
            x0, y0, x1, y1 = f.getbbox(text, anchor="ls")
            w = f.getlength(text) + tr * max(0, len(text) - 1)
            lines.append({"words": ws, "text": text, "w": w, "top": y0, "bottom": y1})
        # baseline to baseline: a cap and the gap, plus whatever hangs below a line
        stepb = cap * (1 + gap_frac) + max([0] + [L["bottom"] for L in lines[:-1]])
        h = -lines[0]["top"] + stepb * (len(lines) - 1) + max(0, lines[-1]["bottom"])
        w = max(L["w"] for L in lines) + 2 * pad
        h += 2 * pad
        if w <= max_w and h <= max_h:
            key = (len(lines), max(L["w"] for L in lines) - min(L["w"] for L in lines))
            if best is None or key < best[0]:
                best = (key, {"lines": lines, "w": w, "h": h, "cap": cap, "px": px, "step": stepb,
                              "ascent": -lines[0]["top"], "font": font, "tracking": tr})  # fmt: skip
    return best[1] if best else None


def runs(ws, ink, accent):
    """A line's words as SVG runs: the accented part in the accent, the rest in ink."""
    out = []
    for i, segs in enumerate(ws):
        for j, (t, a) in enumerate(segs):
            space = " " if j == len(segs) - 1 and i < len(ws) - 1 else ""
            out.append({"text": t + space, "fill": rgb_hex(accent if a else ink)})
    return out


def _mean_rgb(img, box):
    x0, y0, x1, y1 = (int(v) for v in box)
    a = np.asarray(img.crop((x0, y0, x1, y1)).convert("RGB"), dtype="float64")
    return tuple(a.reshape(-1, 3).mean(axis=0))


# ------------------------------------------------------------------ layouts
def tries(wanted):
    """(cap height, area) to try, largest first: inside the writer's place, then anywhere."""
    c = cfg()["cap"]
    caps = range(c["max_px"], c["min_px"] - 1, -c["step_px"])
    return [(cap, area) for area in ([wanted, None] if wanted else [None]) for cap in caps]


def layout_headline(img, words, look, scrim=False, where=None):
    """Words large over the picture where they hide the least of it (inside the writer's
    `where` when given): an option dict, or None when they cannot be set legibly there."""
    c, h = cfg(), cfg()["headline"]
    W, H = size()
    toks = tokens(words)
    font = pick_font(plain(words), look)
    if not font or not toks:
        return None
    dm, sm, tm = detail_map(img), subject_map(img), text_grid(img)
    stroke = h["stroke_frac"]
    tried = []
    for cap, area in tries(region(where)):
        if tried and area is None and tried[-1][2] is not None:
            break  # the writer's place had room: keep to it
        pad = stroke * cap / cap_ratio(font["file"]) / 2
        b = block_at(
            toks,
            font,
            cap,
            W * h["max_w_frac"],
            H * 0.62,
            h["max_lines"],
            c["cap"]["line_gap"],
            pad,
        )
        if not b:
            continue
        p = place(round(b["w"]), round(b["h"]), dm, sm, area, h["centre_penalty"], tmap=tm)
        if not p:
            continue
        tried.append((b, p, area))
        if p[3] <= h["cover_max"]:
            break
    if not tried:
        return None
    clear = [t for t in tried if t[1][3] <= h["cover_max"]]
    b, p, _ = clear[0] if clear else min(tried, key=lambda t: (t[1][3], -t[0]["cap"]))
    x0, y0, busy, cover = p
    box = (x0, y0, x0 + round(b["w"]), y0 + round(b["h"]))
    under = _mean_rgb(img, box)
    light = luminance(under) > 0.36
    col = c["colours"]
    ink = hex_rgb(col["ink_dark"] if light else col["ink_light"])
    edge = hex_rgb(col["ink_light"] if light else col["ink_dark"])
    accent = fit_contrast(accent_colour(img), edge, c["contrast_min"] + 0.5)
    anchor = (
        "start"
        if (x0 + b["w"] / 2) < W * 0.42
        else ("end" if (x0 + b["w"] / 2) > W * 0.58 else "middle")
    )
    pad = stroke * b["px"] / 2
    ax = {"start": x0 + pad, "end": box[2] - pad, "middle": (box[0] + box[2]) / 2}[anchor]
    lines, y = [], y0 + pad + b["ascent"]
    for L in b["lines"]:
        lines.append(
            {
                "x": round(ax, 1),
                "y": round(y, 1),
                "anchor": anchor,
                "runs": runs(L["words"], ink, accent),
            }
        )
        y += b["step"]
    return {
        "layout": "headline",
        "words": words,
        "font": font,
        "cap": b["cap"],
        "px": b["px"],
        "box": box,
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "scrim": scrim or busy > h["quiet_max"],
        "scrim_dark": not light,
        "ctx": {
            "family": font["family"],
            "weight": font["weight"],
            "size": b["px"],
            "tracking": round(b["tracking"], 2),
            "ink": rgb_hex(ink),
            "stroke": rgb_hex(edge),
            "stroke_w": round(stroke * b["px"], 1),
            "shadow": col["shadow"] if not light else rgb_hex(edge),
            "shadow_blur": round(h["shadow_blur_frac"] * b["px"], 1),
            "shadow_dy": round(h["shadow_dy_frac"] * b["px"], 1),
            "lines": [
                dict(
                    L,
                    family=font["family"],
                    weight=font["weight"],
                    size=b["px"],
                    tracking=round(b["tracking"], 2),
                )
                for L in lines
            ],  # fmt: skip
        },
    }


def layout_slab(img, words, look, where=None):
    """Each line of words on its own block of the film's accent, tilted a touch."""
    c, s = cfg(), cfg()["slab"]
    W, H = size()
    toks = tokens(words)
    font = pick_font(plain(words), look)
    if not font or not toks:
        return None
    dm, sm, tm = detail_map(img), subject_map(img), text_grid(img)
    slab = accent_colour(img)
    col = c["colours"]
    inks = [hex_rgb(col["ink_dark"]), hex_rgb(col["ink_light"])]
    ink = max(inks, key=lambda k: float(contrast(luminance(k), luminance(slab))))
    if float(contrast(luminance(ink), luminance(slab))) < c["contrast_min"]:
        slab = fit_contrast(slab, ink, c["contrast_min"] + 0.5)
    chosen = None
    for cap, area in tries(region(where)):
        if chosen and area is None and chosen[-1] is not None:
            break  # the writer's place had room: keep to it
        px_, py_ = s["pad_frac"][0] * cap, s["pad_frac"][1] * cap
        b = block_at(
            toks,
            font,
            cap,
            W * s["max_w_frac"] - 2 * px_,
            H * 0.7,
            s["max_lines"],
            c["cap"]["line_gap"],
        )
        if not b:
            continue
        rows = []
        for L in b["lines"]:
            rh = (L["bottom"] - min(L["top"], -cap)) + 2 * py_
            rows.append({"L": L, "rw": L["w"] + 2 * px_, "rh": rh})
        gap = s["gap_frac"] * cap
        bw = max(r["rw"] for r in rows) + 0.05 * cap  # the tilt reaches past the widest slab
        bh = sum(r["rh"] for r in rows) + gap * (len(rows) - 1) + 0.04 * bw
        p = place(round(bw), round(bh), dm, sm, area, cfg()["headline"]["centre_penalty"], tmap=tm)
        if p and (chosen is None or p[3] < chosen[2][3]):
            chosen = (b, rows, p, px_, py_, gap, bw, bh, area)
        if p and p[3] <= cfg()["headline"]["cover_max"]:
            chosen = (b, rows, p, px_, py_, gap, bw, bh, area)
            break
    if not chosen:
        return None
    b, rows, (x0, y0, busy, cover), px_, py_, gap, bw, bh, _ = chosen
    out, y = [], y0 + 0.02 * bw
    for r in rows:
        L = r["L"]
        top = min(L["top"], -b["cap"])
        base = y + py_ - top
        ry = y
        out.append({
            "rx": round(x0, 1), "ry": round(ry, 1), "rw": round(r["rw"], 1), "rh": round(r["rh"], 1),
            "cx": round(x0 + r["rw"] / 2, 1), "cy": round(ry + r["rh"] / 2, 1),
            "x": round(x0 + px_, 1), "y": round(base, 1),
            "runs": runs(L["words"], ink, ink),
            "family": font["family"], "weight": font["weight"], "size": b["px"],
            "tracking": round(b["tracking"], 2),
        })  # fmt: skip
        y += r["rh"] + gap
    return {
        "layout": "slab",
        "words": words,
        "font": font,
        "cap": b["cap"],
        "px": b["px"],
        "box": (x0, y0, round(x0 + bw), round(y0 + bh)),
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "scrim": False,
        "ctx": {
            "tilt": s["tilt"],
            "radius": round(s["radius_frac"] * b["cap"], 1),
            "slab": rgb_hex(slab),
            "ink": rgb_hex(ink),
            "shadow": c["colours"]["shadow"],
            "shadow_blur": round(0.06 * b["cap"], 1),
            "shadow_dy": round(0.05 * b["cap"], 1),
            "lines": out,
        },
    }


def layout_panel(img, words, look, where=None):
    """The picture on one side, the words on a panel of the film's ground on the other; the
    picture slides so its busy part stays in view."""
    c, pnl = cfg(), cfg()["panel"]
    W, H = size()
    toks = tokens(words)
    font = pick_font(plain(words), look)
    if not font or not toks:
        return None
    dm = detail_map(img)
    third = dm.shape[1] * 2 // 5
    sm = subject_map(img)
    words_in_film = text_boxes(img)
    if where and "left" in where:
        sides = [True, False]
    elif where and "right" in where:
        sides = [False, True]
    else:  # the side that hides less of the subjects first
        sides = [True, False] if sm[:, :third].sum() <= sm[:, -third:].sum() else [False, True]
    ground = ground_colour(img)
    col = c["colours"]
    inks = [hex_rgb(col["ink_dark"]), hex_rgb(col["ink_light"])]
    ink = max(inks, key=lambda k: float(contrast(luminance(k), luminance(ground))))
    accent = fit_contrast(accent_colour(img), ground, c["contrast_min"] + 0.5)
    safe, badge = safe_rects()
    cols = dm.mean(axis=0)
    cx = float((cols * np.arange(len(cols))).sum() / max(1e-6, cols.sum())) * 8
    chosen = None
    for left_quiet, frac in ((s_, f) for f in pnl["w_fracs"] for s_ in sides):
        pw = round(W * frac)
        px0 = 0 if left_quiet else W - pw
        # slide the picture so the middle of what is drawn lands in the middle of what shows. It
        # may only slide under the panel, never away from the far edge, and the film's own words
        # must stay in view -- not under the panel, not slid off the frame
        if left_quiet:
            want, lo, hi, view = pw + (W - pw) / 2 - cx, 0, pw, (pw, W)
        else:
            want, lo, hi, view = (W - pw) / 2 - cx, -pw, 0, (0, W - pw)
        for x0_, _, x1_, _ in words_in_film:
            lo, hi = max(lo, view[0] - x0_), min(hi, view[1] - x1_)
        if lo > hi:
            continue  # no slide keeps them all in view: the other side, a wider panel, or a slab
        shift = min(hi, max(lo, want))
        inner = pw * 0.1
        area = (max(px0 + inner, safe[0]), safe[1], min(px0 + pw - inner, safe[2]), safe[3])
        for cap in range(c["cap"]["max_px"], c["cap"]["min_px"] - 1, -c["cap"]["step_px"]):
            b = block_at(
                toks,
                font,
                cap,
                area[2] - area[0],
                area[3] - area[1],
                pnl["max_lines"],
                c["cap"]["line_gap"],
            )
            if not b:
                continue
            # centred in the panel, clear of the duration badge when the panel is on the right
            x0 = area[0]
            y0 = (H - b["h"]) / 2
            box = (x0, y0, x0 + b["w"], y0 + b["h"])
            if _hits(box, badge):
                y0 = max(area[1], badge[1] - b["h"] - 8)
                box = (x0, y0, x0 + b["w"], y0 + b["h"])
                if _hits(box, badge) or y0 < area[1]:
                    continue
            chosen = (b, x0, y0, left_quiet, pw, px0, shift)
            break
        if chosen:
            break
    if not chosen:
        return None
    b, x0, y0, left_quiet, pw, px0, shift = chosen
    lines, y = [], y0 + b["ascent"]
    for L in b["lines"]:
        lines.append({"x": round(x0, 1), "y": round(y, 1), "anchor": "start",
                      "runs": runs(L["words"], ink, accent), "family": font["family"],
                      "weight": font["weight"], "size": b["px"], "tracking": round(b["tracking"], 2)})  # fmt: skip
        y += b["step"]
    rule = fit_contrast(accent_colour(img), ground, 3.0)
    rw = pnl["rule_px"]
    return {
        "layout": "panel",
        "words": words,
        "font": font,
        "cap": b["cap"],
        "px": b["px"],
        "box": (round(x0), round(y0), round(x0 + b["w"]), round(y0 + b["h"])),
        "busy": 0.0,
        "scrim": False,
        "shift": round(shift),
        "ctx": {
            "px": px0,
            "pw": pw,
            "h": H,
            "panel": rgb_hex(ground),
            "rule": rgb_hex(rule),
            "rule_x": (pw - rw) if left_quiet else (W - pw),
            "rule_w": rw,
            "ink": rgb_hex(ink),
            "lines": lines,
        },
    }


def layout_still(img):
    """The picture alone, graded -- and pushed in a little toward its subjects, but only when
    the push keeps them whole (a star cut by the top edge looks like a mistake)."""
    W, H = size()
    sm = subject_map(img)
    ys, xs = np.indices(sm.shape)
    cx, cy = float((sm * xs).sum()) * 8, float((sm * ys).sum()) * 8
    z = cfg()["still"]["max_zoom"]
    cw, ch = W / z, H / z
    x0 = min(W - cw, max(0, cx - cw / 2))
    y0 = min(H - ch, max(0, cy - ch / 2))
    kept = float(sm[int(y0 // 8) : int((y0 + ch) // 8), int(x0 // 8) : int((x0 + cw) // 8)].sum())
    cut = any(a < x0 or b < y0 or c > x0 + cw or d > y0 + ch for a, b, c, d in text_boxes(img))
    if kept < cfg()["still"]["keep_min"] or cut:
        z = 1.0
    return {"layout": "still", "words": "", "zoom": z, "centre": (cx, cy), "scrim": False}


def layout(kind, img, words, look, scrim=False, where=None):
    if kind == "headline":
        return layout_headline(img, words, look, scrim, where)
    if kind == "slab":
        return layout_slab(img, words, look, where)
    if kind == "panel":
        return layout_panel(img, words, look, where)
    return layout_still(img)


# ------------------------------------------------------------------ the plate
def plate(img, o):
    """The picture under the words: graded, slid (panel), zoomed (still), scrimmed."""
    W, H = size()
    g = cfg()["grade"]
    im = (
        img.convert("RGB").resize((W, H), Image.LANCZOS)
        if img.size != (W, H)
        else img.convert("RGB")
    )
    im = ImageEnhance.Color(im).enhance(g["colour"])
    im = ImageEnhance.Contrast(im).enhance(g["contrast"])
    if o["layout"] == "still" and o.get("zoom", 1) > 1:
        z = o["zoom"]
        cw, ch = W / z, H / z
        cx, cy = o["centre"]
        x0 = min(W - cw, max(0, cx - cw / 2))
        y0 = min(H - ch, max(0, cy - ch / 2))
        im = im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize(
            (W, H), Image.LANCZOS
        )
    if o["layout"] == "panel" and o.get("shift"):
        canvas = Image.new("RGB", (W, H), hex_rgb(o["ctx"]["panel"]))
        canvas.paste(im, (o["shift"], 0))
        im = canvas
    if o.get("scrim"):
        s = cfg()["scrim"]
        x0, y0, x1, y1 = o["box"]
        grow = s["grow_frac"] * o["cap"]
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rounded_rectangle(
            [x0 - grow, y0 - grow, x1 + grow, y1 + grow],
            radius=grow,
            fill=round(255 * s["strength"]),
        )
        m = m.filter(ImageFilter.GaussianBlur(s["feather_px"]))
        tone = (0, 0, 0) if o.get("scrim_dark", True) else (255, 255, 255)
        im = Image.composite(Image.new("RGB", (W, H), tone), im, m)
    return im


# ------------------------------------------------------------------ paint
def _h2i():
    if "h2i" not in _CACHE:
        _CACHE["h2i"] = importlib.import_module("html-to-image")
    return _CACHE["h2i"]


def _template(name):
    k = ("tpl", name)
    if k not in _CACHE:
        with open(_env.resolve(os.path.join(LAYOUT_DIR, name)), encoding="utf-8") as f:
            _CACHE[k] = f.read()
    return _CACHE[k]


def render_template(tpl, ctx):
    if "mc" not in _CACHE:
        _CACHE["mc"] = importlib.import_module("make-card")
    return _CACHE["mc"].render_template(tpl, ctx)


def paint(options, into, browser=None):
    """Every option's layer and letter mask in one headless shot: [(layer RGBA, mask L)] in
    the order given (a still option gets (None, None))."""
    W, H = size()
    todo = [o for o in options if o["layout"] != "still"]
    if not todo:
        return [(None, None) for _ in options]
    fonts, panels = {}, []
    for i, o in enumerate(todo):
        f = o["font"]
        fonts[(f["family"], f["weight"])] = {
            "family": f["family"],
            "weight": f["weight"],
            "url": font_uri(f["file"]),
        }
        tpl = _template(o["layout"] + ".svg")
        for mask in (False, True):
            ctx = dict(o["ctx"], n=i, mask=mask, w=W)
            panels.append({"w": W, "h": H, "body": render_template(tpl, ctx)})
    page = render_template(
        _template("_page.html"), {"fonts": list(fonts.values()), "panels": panels}
    )
    os.makedirs(into, exist_ok=True)
    html_path = os.path.join(into, "layers.html")
    png = os.path.join(into, "layers.png")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)
    try:
        _h2i().render(
            html_path, png, browser=browser, viewport=(W, H * len(panels)), scale=1, crop=False
        )
    except SystemExit as e:  # html-to-image reports by exiting; a caller wants an exception
        raise RuntimeError("the layers did not paint: %s" % e) from None
    big = Image.open(png).convert("RGBA")
    if big.size != (W, H * len(panels)):
        raise RuntimeError(
            "the layers came back %dx%d, not %dx%d" % (*big.size, W, H * len(panels))
        )
    shots = iter(
        (
            big.crop((0, k * H, W, (k + 1) * H)),
            big.crop((0, (k + 1) * H, W, (k + 2) * H)).getchannel("A"),
        )
        for k in range(0, len(panels), 2)
    )
    return [next(shots) if o["layout"] != "still" else (None, None) for o in options]


def compose(img, o, layer):
    im = plate(img, o).convert("RGBA")
    if layer is not None:
        im.alpha_composite(layer)
    return im.convert("RGB")


# ------------------------------------------------------------------ checks
def jpeg(im, quality=None):
    buf = BytesIO()
    im.save(buf, "JPEG", quality=quality or cfg()["jpeg_quality"], optimize=True, progressive=True)
    return buf.getvalue()


def covered_text(o, layer):
    """Pixels of the film's own words that this option's graphics hide (letters, slab, panel)."""
    if layer is None:
        return 0
    a = np.asarray(layer.getchannel("A")) > 160
    shift = o.get("shift") or 0
    W, H = size()
    n = 0
    for x0, y0, x1, y1 in text_boxes(o["img"]):
        x0, x1 = int(max(0, x0 + shift)), int(min(W, x1 + shift))
        n += int(a[int(y0) : int(y1), x0:x1].sum()) if x1 > x0 else 0
    return n


def checks(o, final, mask, layer=None):
    """Every rule the option is held to: (scores, failures). Scores are what the bake-off and
    the CLI print; failures are the rules broken."""
    from scipy import ndimage

    c = cfg()
    W, H = size()
    res, fails = {}, []
    data = jpeg(final)
    res["bytes"] = len(data)
    if len(data) > c["max_bytes"]:
        fails.append("the JPEG is %.1f MB" % (len(data) / 1e6))
    if o["layout"] == "still":
        return res, fails
    res["hides_text"] = covered_text(o, layer)
    if res["hides_text"] > cfg()["text"]["hide_max_px"]:
        fails.append("it hides %d pixels of the film's own words" % res["hides_text"])
    m = np.asarray(mask) > 127
    if m.sum() < 50:
        fails.append("no letters were painted")
        return res, fails
    # legibility where YouTube shows it smallest: the cap height it was set at, and the cap
    # height the letters really reached (the ink of the tallest line)
    small = c["feed"]["smallest_w"] / W
    res["cap_px"] = o["cap"]
    res["cap_168"] = round(o["cap"] * small, 1)
    if res["cap_168"] < c["feed"]["min_cap_px"]:
        fails.append(
            "letters %.1f px tall at %d px wide" % (res["cap_168"], c["feed"]["smallest_w"])
        )
    ys, xs = np.nonzero(m)
    ink = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    res["ink_box"] = ink
    # the letters stay where they were put, and out of YouTube's corner and margins
    safe, badge = safe_rects()
    tol = 0.12 * o["cap"]
    x0, y0, x1, y1 = o["box"]
    if o["layout"] != "slab" and (
        ink[0] < x0 - tol or ink[1] < y0 - tol or ink[2] > x1 + tol or ink[3] > y1 + tol
    ):
        fails.append("the letters ran outside their box %s: %s" % (o["box"], ink))
    res["in_badge"] = int(m[badge[1] :, badge[0] :].sum())
    if res["in_badge"]:
        fails.append("%d letter pixels under YouTube's duration stamp" % res["in_badge"])
    edge = int(
        m[:, : safe[0]].sum()
        + m[:, safe[2] :].sum()
        + m[: safe[1], :].sum()
        + m[safe[3] :, :].sum()
    )
    res["in_margin"] = edge
    if edge > 0.002 * m.sum():
        fails.append("%d letter pixels in the margins" % edge)
    # contrast: the letters against the ring of pixels immediately around them (the outline,
    # where there is one), on the finished picture; 90% of letter pixels must reach it
    r = max(2, round(0.045 * o["px"]))
    inner = ndimage.binary_erosion(m, iterations=2)
    ring = ndimage.binary_dilation(m, iterations=r) & ~ndimage.binary_dilation(m, iterations=1)
    L = luminance_map(final)
    if inner.sum() < 20 or ring.sum() < 20:
        fails.append("the letters are too thin to measure")
    else:
        lr = float(np.median(L[ring]))
        ratio = contrast(L[inner], lr)
        res["contrast"] = round(float(np.percentile(ratio, 10)), 2)
        if res["contrast"] < c["contrast_min"]:
            fails.append("contrast %.2f:1 against what is around the letters" % res["contrast"])
    return res, fails


def ocr_recall(final, words, widths=None):
    """{width: share of the words OCR reads back} on the picture shrunk to each feed width and
    blown back up -- a second opinion on legibility, used by the bake-off (a machine that
    misreads a word says less about people than the cap height does). A word counts as read
    when it appears in what OCR read with the spaces taken out: at 168 px OCR runs words
    together ("withOlga"), which is not a word it failed to see. RapidOCR reads Latin script
    only, so words in any other script get None, not a failure."""
    if not words:
        return {}
    want = [re.sub(r"\W", "", w.lower()) for w in WORD.findall(plain(words))]
    if not all(re.fullmatch(r"[a-z0-9]+", w) for w in want if w):
        return {w: None for w in widths or cfg()["feed"]["check_widths"]}
    out = {}
    for w in widths or cfg()["feed"]["check_widths"]:
        h = round(w * final.height / final.width)
        small = final.resize((w, h), Image.LANCZOS).resize((w * 4, h * 4), Image.BICUBIC)
        got, _ = ocr()(np.asarray(small))
        seen = re.sub(r"\W", "", " ".join(x[1] for x in got or []).lower())

        def read(x, seen=seen):
            m = difflib.SequenceMatcher(None, x, seen).find_longest_match(0, len(x), 0, len(seen))
            return m.size >= 0.8 * len(x)

        out[w] = round(sum(1 for x in want if x and read(x)) / max(1, len(want)), 2)
    return out


# ------------------------------------------------------------------ the whole thing
DROP = ("ctx", "box", "font", "cap", "px", "shift", "zoom", "centre", "busy", "cover", "scrim_dark")
FALLBACK = {
    "headline": ["headline+scrim", "slab", "still"],
    "slab": ["still"],
    "panel": ["slab", "still"],
}


def _lay(o, kind, look):
    if kind == "headline+scrim":
        return layout_headline(o["img"], o["words"], look, scrim=True, where=o["place"])
    if kind == "still" or not o["words"]:
        return layout_still(o["img"])
    return layout(kind, o["img"], o["words"], look, where=o["place"])


def first_layout(o, kind, look):
    """The first layout, from `kind` down its fallbacks, that can be set at all (the still
    alone always can)."""
    while True:
        lay = _lay(o, kind, look)
        if lay is not None:
            return lay
        o["notes"].append("the words could not be set as %s" % kind)
        o["tried"].append(kind)
        kind = _next(o)


def _next(o):
    """What an option that failed becomes."""
    steps = FALLBACK.get(o["requested"], ["still"])
    done = o.get("tried", [])
    for s in steps:
        if s not in done:
            return s
    return "still"


def film_look(film_dir):
    """crayon / clean / painted, from the studio's record of the film (clean when unknown)."""
    try:
        with open(os.path.join(film_dir, "studio.json"), encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError):
        r = {}
    if r.get("look") == "painted" or os.path.exists(os.path.join(film_dir, "paint.json")):
        return "painted"
    style = ((r.get("direction") or {}).get("style") or "").lower()
    return "crayon" if style == "crayon" else "clean"


def film_length(film_dir):
    with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
        return float(json.load(f).get("duration") or 0)


def make_options(
    film_dir, concepts, out_dir, title="", look=None, env=None, browser=None, log=print
):
    """Four finished options for a film: [{n, file, layout, requested, at, t, words, checks,
    notes}], every one of them passing. Stills are cached per film; the JPEGs go to out_dir."""
    t0 = time.time()
    W, H = size()
    look = look or film_look(film_dir)
    length = film_length(film_dir)
    work = os.path.join(film_dir, "temp", "thumbs", "work")
    shutil.rmtree(work, ignore_errors=True)
    # 1. every frame the settle step looks at, in one browser run
    want = set()
    for o in concepts:
        want |= set(settle_times(o["at"], length)[1])
    stills = render_stills(film_dir, want, env=env)
    t_stills = time.time() - t0
    # 2. the frame, then the words on it
    opts = []
    for i, cpt in enumerate(concepts, 1):
        t, rows = settle(cpt["at"], stills, length)
        o = {"n": i, "at": cpt["at"], "t": t, "requested": cpt["layout"], "words": cpt["words"],
             "place": cpt.get("place"), "notes": [], "tried": []}  # fmt: skip
        if abs(t - cpt["at"]) > 0.01:
            o["notes"].append("settled at %.2f s (asked %.2f s)" % (t, cpt["at"]))
        o["img"] = load_still(stills[t])
        o.update(first_layout(o, cpt["layout"], look))
        opts.append(o)
    # 3. paint, check, fall back -- until every option passes
    for rnd in range(4):
        pending = [o for o in opts if "final" not in o]
        if not pending:
            break
        shots = paint(pending, os.path.join(work, "round%d" % rnd), browser=browser)
        for o, (layer, mask) in zip(pending, shots):
            final = compose(o["img"], o, layer)
            res, fails = checks(o, final, mask, layer)
            o["checks"] = res
            if not fails:
                o["final"] = final
                continue
            o["notes"].append(
                "%s failed: %s"
                % (o["layout"] + ("+scrim" if o.get("scrim") else ""), "; ".join(fails))
            )
            o["tried"].append(o["layout"] + ("+scrim" if o.get("scrim") else ""))
            lay = first_layout(o, _next(o), look)
            for k in DROP:
                o.pop(k, None)
            o.update(lay)
            if o["layout"] == "still":
                o["words"] = ""
    for o in opts:
        if "final" not in o:  # out of rounds: the picture alone, which has nothing to fail
            for k in DROP:
                o.pop(k, None)
            o.update(layout_still(o["img"]))
            o["words"] = ""
            o["final"] = compose(o["img"], o, None)
            o["checks"], _ = checks(o, o["final"], None)
    # 4. write
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for o in opts:
        path = os.path.join(out_dir, "thumb-%d.jpg" % o["n"])
        with open(path, "wb") as f:
            f.write(jpeg(o["final"]))
        out.append({
            "n": o["n"], "file": path, "layout": o["layout"], "requested": o["requested"],
            "at": o["at"], "t": o["t"], "words": o["words"] if o["layout"] != "still" else "",
            "place": o.get("place"),
            "font": (o.get("font") or {}).get("family"), "checks": o.get("checks", {}),
            "notes": o["notes"], "final": o["final"],
        })  # fmt: skip
    log(
        "  thumbnails: %d options in %.1f s (stills %.1f s, %d frames)"
        % (len(out), time.time() - t0, t_stills, len(want))
    )
    return out


def contact_sheet(images, labels, out, cols=2, tile=(960, 540)):
    """Options side by side, each labelled."""
    rows = (len(images) + cols - 1) // cols
    tw, th = tile
    pad = 44
    sheet = Image.new("RGB", (cols * tw, rows * (th + pad)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = pil_font("fonts/Montserrat-Bold.ttf", 24)
    for i, (im, lab) in enumerate(zip(images, labels)):
        x, y = (i % cols) * tw, (i // cols) * (th + pad)
        d.text((x + 12, y + 9), lab[:80], font=f, fill=(235, 235, 235))
        sheet.paste(im.resize(tile, Image.LANCZOS), (x, y + pad))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=88)
    return out


def feed_sheet(images, title, channel, out, duration="0:30"):
    """The options where people meet them: YouTube's home grid (360 px), search (246 px) and
    the up-next sidebar (168 px), on its dark and light pages."""
    f_t = pil_font("fonts/Montserrat-Bold.ttf", 15)
    f_s = pil_font("fonts/Montserrat-Medium.ttf", 13)
    f_b = pil_font("fonts/Montserrat-Bold.ttf", 11)
    col_w = 400
    widths = (360, 246, 168)
    bands = []
    for bg, fg, sub in (
        ((15, 15, 15), (241, 241, 241), (170, 170, 170)),
        ((255, 255, 255), (15, 15, 15), (96, 96, 96)),
    ):
        band = Image.new("RGB", (col_w * len(images), 700), bg)
        d = ImageDraw.Draw(band)
        for i, im in enumerate(images):
            x, y = i * col_w + 20, 16
            for w in widths:
                h = round(w * 9 / 16)
                band.paste(im.resize((w, h), Image.LANCZOS), (x, y))
                bw = d.textlength(duration, font=f_b) + 8
                d.rounded_rectangle(
                    [x + w - bw - 4, y + h - 20, x + w - 4, y + h - 4], radius=3, fill=(0, 0, 0)
                )
                d.text((x + w - bw, y + h - 19), duration, font=f_b, fill=(255, 255, 255))
                tx = x if w > 200 else x + w + 8
                ty = y + h + 6 if w > 200 else y
                d.text((tx, ty), (title or "")[: 34 if w > 200 else 18], font=f_t, fill=fg)
                d.text((tx, ty + 20), channel or "", font=f_s, fill=sub)
                y += h + (56 if w > 200 else 30)
        bands.append(band)
    sheet = Image.new("RGB", (bands[0].width, sum(b.height for b in bands)))
    y = 0
    for b in bands:
        sheet.paste(b, (0, y))
        y += b.height
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=88)
    return out
