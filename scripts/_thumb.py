"""Thumbnail options from a film's own stills, in the film's own look: which frame, where the
words go, what they look like, and proof that the result reads where YouTube shows it smallest.

The picture is always a frame of the film, and so is everything added to it: the words are set
in the film's own headline type and colours, on its own cards and paper, with its own logo --
drawn by the film's engine (sketch/thumb.js, run ahead of the film's code), not laid over it by a
template. What the film's look is, is read off the film while it draws: every text style, card
and picture it uses (the probe), so an editorial film in Source Serif gets a Source Serif
headline, a crayon film its hand-drawn type and paper. The words are laid out here, in Python,
with the same font files the page draws them with, so the line breaks, the size and the cap
height are numbers this module chose. Each option is drawn three times -- as it will look, its
letters alone, and everything it added -- and the checks read the finished picture through those.

    stills     clean frames of a sketch film (its manifest copied without the Free plan's
               closing), rendered by sketch-render.py --stills, the probe riding along
    look       the film's headline type, ink, accent, paper, cards and logo, from the probe
    moments    the times a writer chooses from, and the labelled sheet it sees them on
    concepts   four {at, words, layout, place}, checked: inside the film, apart, short, not the title
    settle     the frame near a moment that is not mid-transition, and not a thin one
    layout     size, line breaks and the quietest place for the words, in the film's type
    draw       one browser run for every option: the thumbnail, its letters, its footprint
    checks     cap height at 168 px, contrast, YouTube's overlays, the film's own words kept clear
    fallbacks  a glow of the film's paper, then a card, then the still alone -- an option that
               fails is never shown

Config: config/thumbnails/thumbnails.json. CLI: scripts/thumb-options.py. Studio:
studio/thumbs.py. Self-test: scripts/check-thumbnail.py.
"""

import os
import re
import sys
import json
import math
import colorsys
import time
import shutil
import hashlib
import difflib
import itertools
import subprocess
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from PIL import Image, ImageColor, ImageDraw, ImageFont  # noqa: E402

CONFIG = "config/thumbnails/thumbnails.json"
THUMB_JS = os.path.join(_env.ROOT, "sketch", "thumb.js")
LAYOUTS = ("headline", "card", "panel", "still")
RENAMED = {"slab": "card"}  # a writer (or an older draft) may still say slab
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


def colour(s, default=(0, 0, 0)):
    """A CSS colour a film used ("#1a1a1a", "rgb(26,26,26)", a name) as (r, g, b)."""
    try:
        return tuple(ImageColor.getrgb(str(s))[:3])
    except (ValueError, TypeError, AttributeError):
        return tuple(default)


# ------------------------------------------------------------------ fonts
def _tt(path):
    k = ("tt", path)
    if k not in _CACHE:
        from fontTools.ttLib import TTFont

        _CACHE[k] = TTFont(_env.resolve(path), lazy=True)
    return _CACHE[k]


def _cmap(path):
    k = ("cmap", path)
    if k not in _CACHE:
        t = _tt(path)
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


def readable(path):
    """Can this module measure it? A .ttf or .otf that is there (a .woff2 needs Brotli, which
    the venv does not carry -- such a film font is drawn by the page but not chosen here)."""
    p = _env.resolve(path)
    return p.lower().endswith((".ttf", ".otf")) and os.path.exists(p)


def _weight(wt):
    n = re.findall(r"\d+", str(wt))
    return int(n[0]) if n else 400


def pil_font(path, px, wt=None):
    """Pillow's font at `px`; a variable font (Caveat's is) set to the weight it is drawn at, so
    what is measured here is what the page draws."""
    k = ("pil", path, px, str(wt))
    if k not in _CACHE:
        f = ImageFont.truetype(_env.resolve(path), px)
        if wt is not None:
            try:
                axes = f.get_variation_axes()
            except (OSError, AttributeError):
                axes = None
            if axes:
                vals = []
                for a in axes:
                    name = a.get("name") or b""
                    name = name.decode("latin-1") if isinstance(name, bytes) else str(name)
                    v = a.get("default", a.get("minimum", 0))
                    if name.lower().startswith("weight") or name.lower() == "wght":
                        v = min(a["maximum"], max(a["minimum"], _weight(wt)))
                    vals.append(v)
                f.set_variation_by_axes(vals)
        _CACHE[k] = f
    return _CACHE[k]


def tooling_fonts():
    """{family: [(file, variable, weight class)]} of the .ttf/.otf files in the tooling's fonts/."""
    if "tooling" not in _CACHE:
        from fontTools.ttLib import TTFont

        out = {}
        d = os.path.join(_env.ROOT, "fonts")
        for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not n.lower().endswith((".ttf", ".otf")):
                continue
            try:
                t = TTFont(os.path.join(d, n), lazy=True)
                fam = t["name"].getDebugName(16) or t["name"].getDebugName(1)
                out.setdefault(fam, []).append(
                    (os.path.join(d, n), "fvar" in t, t["OS/2"].usWeightClass)
                )
            except Exception:  # noqa: BLE001 -- a font this cannot read is one it does not offer
                continue
        _CACHE["tooling"] = out
    return _CACHE["tooling"]


def film_fonts(film_dir):
    """The fonts a film declares (its sketch.json), [{family, weights, file}] with each file found
    -- a font the film fetched for itself beside it (web/fonts/...), the tooling's in fonts/.

    One this module cannot measure (a .woff2: the example film's Caveat) stands in as the
    tooling's .ttf of the same family when there is one -- a variable one at any weight the film
    declares, a static one only at its own. The page still draws the film's file; sketch/thumb.js
    holds each line to the width planned here, so a stand-in that runs narrower only sets the
    words a touch smaller, never outside their box."""
    with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    out = []
    for x in m.get("fonts") or []:
        if not isinstance(x, dict) or not isinstance(x.get("file"), str):
            continue
        p = x["file"]
        if not os.path.isabs(p):
            here = os.path.join(film_dir, p)
            p = here if os.path.exists(here) else _env.resolve(p)
        ws = [int(w) for w in re.findall(r"\d+", str(x.get("weight", "400")))] or [400]
        if readable(p):
            out.append({"family": x.get("family"), "weights": ws, "file": p})
            continue
        for f, var, wc in tooling_fonts().get(x.get("family"), []):
            if var or (ws[0] <= wc <= ws[-1] if len(ws) >= 2 else wc in ws):
                out.append({"family": x.get("family"), "weights": ws if var else [wc], "file": f})
    return out


def font_for(fonts, family, wt):
    """The file that draws `family` at weight `wt` (a variable font's range counts), or None."""
    w = _weight(wt)
    cands = [f for f in fonts if f["family"] == family and readable(f["file"])]
    if not cands:
        return None

    def off(f):
        ws = f["weights"]
        return 0 if len(ws) >= 2 and ws[0] <= w <= ws[-1] else min(abs(x - w) for x in ws)

    return min(cands, key=off)["file"]


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
        lay = RENAMED.get(lay, lay)
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
def film_images(film_dir, m=None):
    """{name: path} of the pictures a film shows: the ones its manifest names (a logo the page
    tool fetched, a picture the person gave) and its painted scenes."""
    if m is None:
        with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
            m = json.load(f)

    def ab(p):
        return p if os.path.isabs(p) else os.path.join(film_dir, p)

    images = {k: ab(v) for k, v in (m.get("images") or {}).items() if isinstance(v, str)}
    paint = m.get("paint")
    if paint:
        pj = paint
        if isinstance(paint, str):
            try:
                with open(ab(paint), encoding="utf-8") as f:
                    pj = json.load(f)
            except (OSError, ValueError):
                pj = {}
        for im in pj.get("images") or []:
            name = str(im.get("name") or "")
            p = os.path.join(film_dir, "images", name + ".jpg")
            if re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name) and os.path.exists(p):
                images.setdefault(name, p)
    return images


def clean_manifest(film_dir, into, head=None, fonts=()):
    """A copy of the film's manifest that draws the film and nothing added after it: no Free
    plan closing, whose mark sits exactly where YouTube stamps the duration. Every path is made
    absolute (a font or picture the film keeps in its own folder included), and the copy renders
    into its own folder, never the film's outputs. `head` runs before the film's code (default:
    sketch/thumb.js, whose probe notes the film's look as it draws); `fonts` are added for the
    page to load (a fallback for words the film's own type has no glyphs for)."""
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
    have = {(f.get("family"), str(f.get("weight"))) for f in m["fonts"] if isinstance(f, dict)}
    for f in fonts:
        if (f["family"], str(f["weight"])) not in have:
            m["fonts"].append(
                {"file": f["file"], "family": f["family"], "weight": str(f["weight"])}
            )
    for k in (
        "vo",
        "engine",
        "cast",
        "scenes",
    ):  # a long film made in scenes keeps them in a folder
        if isinstance(m.get(k), str):
            m[k] = ab(m[k])
    m["images"] = film_images(film_dir, m)
    m.pop("paint", None)
    audio = dict(m.get("audio") or {})
    audio["vo_timeline"] = ab(audio.get("vo_timeline") or "audio/vo/timeline.json")
    m["audio"] = {"vo_timeline": audio["vo_timeline"]}  # stills need no score or effects
    m["head"] = {"scripts": list(head if head is not None else [THUMB_JS])}
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


def style_path(film_dir):
    return os.path.join(stills_dir(film_dir), "style.json")


def still_name(t):
    return "%06.2f.png" % t


def merge_report(old, new):
    """Two probe reports as one: text styles and cards added up by kind, the largest kept."""
    if not old:
        return new

    def fold(a, b, key, add, top):
        d = {key(x): dict(x) for x in a}
        for x in b:
            k = key(x)
            if k not in d:
                d[k] = dict(x)
                continue
            for f in add:
                d[k][f] = d[k].get(f, 0) + x.get(f, 0)
            for f in top:
                d[k][f] = max(d[k].get(f, 0), x.get(f, 0))
        return list(d.values())

    out = dict(new)
    out["txt"] = fold(old.get("txt") or [], new.get("txt") or [],
                      lambda x: (x["font"], x["wt"], x["col"]), ("n", "chars"), ("max",))  # fmt: skip
    out["card"] = fold(old.get("card") or [], new.get("card") or [],
                       lambda x: (x["fill"], x["r"], x.get("stroke"), x.get("shadow")), ("n", "area"), ())  # fmt: skip
    img = dict(old.get("img") or {})
    for k, v in (new.get("img") or {}).items():
        o = img.get(k) or {"n": 0, "w": 0}
        img[k] = {"n": o["n"] + v.get("n", 0), "w": max(o["w"], v.get("w", 0))}
    out["img"] = img
    return out


def render_stills(
    film_dir, times, into=None, env=None, head=None, fonts=(), style=True, timeout=900
):
    """{t: path} of 1920x1080 frames, rendering only the ones not already made. One browser run
    for all of them (~0.12 s a still after ~3 s of start-up). With `style`, what the probe saw
    while they were drawn is folded into the film's recorded look (style.json)."""
    into = into or stills_dir(film_dir)
    os.makedirs(into, exist_ok=True)
    ts = sorted({round(float(t), 2) for t in times})
    have = {t: os.path.join(into, still_name(t)) for t in ts}
    need = [t for t, p in have.items() if not os.path.exists(p)]
    if need:
        man = clean_manifest(film_dir, os.path.join(into, "manifest"), head=head, fonts=fonts)
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
        rep = os.path.join(into, "report.json")
        if os.path.exists(rep):
            if style:
                with open(rep, encoding="utf-8") as f:
                    new = json.load(f)
                p = style_path(film_dir)
                old = None
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        old = json.load(f)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(merge_report(old, new), f, ensure_ascii=False)
                os.replace(p + ".tmp", p)
            os.remove(rep)
    return have


def probe(film_dir, env=None):
    """The film's look as its probe recorded it; a few of its moments are drawn first when none
    of its stills ever was with the probe (a film made before thumbnails)."""
    p = style_path(film_dir)
    if not os.path.exists(p):
        ts = moment_times(narration(film_dir), film_length(film_dir))
        tmp = os.path.join(film_dir, "temp", "thumbs", "probe")
        shutil.rmtree(tmp, ignore_errors=True)
        render_stills(film_dir, ts, into=tmp, env=env)
        shutil.rmtree(tmp, ignore_errors=True)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


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


def _ocr_lines(img):
    """Every line of words the film draws in this frame, [(x0, y0, x1, y1, height)] grown a
    little: RapidOCR (local) on a half-size copy, 0.2-0.7 s a frame."""
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
        g = t["grow_px"]
        out.append((max(0, min(xs) - g), max(0, min(ys) - g), min(W, max(xs) + g),
                    min(H, max(ys) + g), max(ys) - min(ys)))  # fmt: skip
    img.info["_text"] = out
    return out


def text_boxes(img, min_h=None):
    """The words the film itself draws in this frame that a thumbnail may not cover, as pixel
    boxes. Measured on the studio's films, OCR finds headings, thin labels, handwriting,
    Cyrillic and a rotated bottle label. A card or a panel may hide a phone's or a card's own
    small print (under min_h_px: an app screen is full of it, and protecting every one left no
    room for a card anywhere on it); words drawn straight on the picture may cross none of the
    film's words (headline_min_h_px) -- "On for everyone" set over an "AI MODEL UPDATE" label
    and a "Default" chip read as a collision (2026-09-29)."""
    h = cfg()["text"]["min_h_px"] if min_h is None else min_h
    return [b[:4] for b in _ocr_lines(img) if b[4] >= h]


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


def place(bw, bh, dmap, smap=None, area=None, centre_penalty=0.0, cell=8, busy_weight=1.0,
          avoid=(), whole=False):  # fmt: skip
    """Where a bw x bh block goes, inside `area`, clear of the badge and of the film's own words:
    (x0, y0, busy, cover), or None. Busy is the mean detail under the block; cover is the share of
    the subjects (smap) it would hide. It goes where it hides least, then where it is quietest.

    `avoid` are the film's words (text_boxes). Words drawn straight on the picture may touch none
    of them; an opaque block (`whole`: a card) may hide one entirely, like a sticker over it, but
    never cut through one -- a half-hidden "Month-e" reads broken, a covered chip does not."""
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
    cw, ch = max(1, math.ceil(bw / cell)), max(1, math.ceil(bh / cell))
    best = None
    step = 2 * cell
    xs = list(range(ax0, ax1 - bw + 1, step)) + [ax1 - bw]
    ys = list(range(ay0, ay1 - bh + 1, step)) + [ay1 - bh]
    X, Y = np.array(xs), np.array(ys)
    bad = np.zeros((len(ys), len(xs)), dtype=bool)
    for bx0, by0, bx1, by1 in avoid:
        touch = np.outer((Y < by1) & (Y + bh > by0), (X < bx1) & (X + bw > bx0))
        if whole:
            touch &= ~np.outer((Y <= by0) & (Y + bh >= by1), (X <= bx0) & (X + bw >= bx1))
        bad |= touch
    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            if bad[iy, ix] or _hits((x, y, x + bw, y + bh), badge):
                continue
            cx, cy = x // cell, y // cell
            cx1, cy1 = min(dmap.shape[1], cx + cw), min(dmap.shape[0], cy + ch)
            s = ii[cy1, cx1] - ii[cy, cx1] - ii[cy1, cx] + ii[cy, cx]
            busy = float(s / max(1, (cy1 - cy) * (cx1 - cx)))
            cover = float(si[cy1, cx1] - si[cy, cx1] - si[cy1, cx] + si[cy, cx])
            # a small nudge off dead centre, where the subject usually is
            dx = abs((x + bw / 2) / W - 0.5) * 2
            dy = abs((y + bh / 2) / H - 0.5) * 2
            score = cover + busy_weight * busy + centre_penalty * (1 - max(dx, dy)) * 0.01
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
    f = pil_font(font["file"], px, font.get("weight"))
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
    """A line's words as runs for sketch/thumb.js: the accented part in the accent, the rest in
    ink, a space after each word but the last."""
    out = []
    for i, segs in enumerate(ws):
        for j, (t, a) in enumerate(segs):
            space = " " if j == len(segs) - 1 and i < len(ws) - 1 else ""
            out.append({"text": t + space, "col": rgb_hex(accent if a else ink)})
    return out


def _mean_rgb(img, box):
    x0, y0, x1, y1 = (int(v) for v in box)
    a = np.asarray(img.crop((x0, y0, x1, y1)).convert("RGB"), dtype="float64")
    return tuple(a.reshape(-1, 3).mean(axis=0))


def tries(wanted):
    """(cap height, area) to try, largest first: inside the writer's place, then anywhere."""
    c = cfg()["cap"]
    caps = range(c["max_px"], c["min_px"] - 1, -c["step_px"])
    return [(cap, area) for area in ([wanted, None] if wanted else [None]) for cap in caps]


# ------------------------------------------------------------------ the film's own look
def film_style(film_dir, env=None):
    """How this film looks, for its thumbnails, from what its probe saw it draw:

    crayon      hand-drawn (it boils) or clean
    paper, text, ink, accent, accent_fill   its palette (SK.C: the ground's colours, as the
                film set them), as (r, g, b)
    heads       the type to set words in, best first: the film's own text styles, biggest
                first (its headline), each with its colour -- then, for words its type has no
                glyphs for or a film with no text of its own, the studio's print hand (drawn)
                or a plain sans (clean)
    card        its cards: fill, corners, outline, shadow (or a hand-drawn note on crayon)
    logo        a logo it shows ({name, file, aspect}), or None
    """
    rep = probe(film_dir, env)
    c = cfg()
    C = rep.get("C") or {}
    crayon = bool((rep.get("style") or {}).get("boil"))
    paper = colour(C.get("paper"), (247, 242, 231))
    text = colour(C.get("text") or C.get("ink"), (42, 37, 33))
    ink = colour(C.get("ink"), text)
    accent = colour(C.get("accentText") or C.get("accent"), text)
    accent_fill = colour(C.get("accent"), accent)
    fonts = film_fonts(film_dir)
    heads, seen = [], set()
    styles = [x for x in rep.get("txt") or [] if x.get("chars", 0) >= 2 and x.get("max", 0) >= 24]
    for x in sorted(styles, key=lambda x: (-x["max"], -x["n"])):
        f = font_for(fonts, x["font"], x["wt"])
        if f and (x["font"], _weight(x["wt"])) not in seen:
            seen.add((x["font"], _weight(x["wt"])))
            k = x.get("stroke") or None
            heads.append({"file": f, "family": x["font"], "weight": str(_weight(x["wt"])),
                          "col": colour(x["col"], text), "size": x["max"], "film": True,
                          "stroke": {"w": float(k["w"]), "col": colour(k["col"], ink)} if k else None})  # fmt: skip
    for f in c["fonts"]["no_text"]["crayon" if crayon else "clean"] + c["fonts"]["fallback"]:
        heads.append(dict(f, col=text, film=False))
    card = max(rep.get("card") or [], key=lambda x: x.get("area", 0), default=None)
    if card:
        card = {
            "fill": colour(card["fill"], (255, 255, 255)),
            "r": float(card.get("r") or 18),
            "stroke": colour(card["stroke"]) if card.get("stroke") else None,
            "strokeW": float(card.get("strokeW") or 2),
            "shadow": bool(card.get("shadow")),
            "sketch": False,
        }
    else:  # a film with no cards of its own: one made of its paper, edged in its accent (a
        # hand-drawn note on crayon) -- a stock white card sat on a black-and-gold wine film
        d = c["card"]["default_crayon" if crayon else "default_clean"]
        card = {
            "fill": paper,
            "r": d["r"],
            "stroke": ink if d.get("sketch") else accent_fill,
            "strokeW": d.get("strokeW", 3),
            "shadow": d.get("shadow", False),
            "sketch": bool(d.get("sketch")),
        }
    logo = None
    shown = rep.get("img") or {}
    names = [n for n in rep.get("images") or [] if "logo" in n.lower()]
    names.sort(key=lambda n: -(shown.get(n) or {}).get("n", 0))
    files = film_images(film_dir)
    for n in names:
        p = files.get(n)
        if p and os.path.exists(p):
            with Image.open(p) as im:
                logo = {"name": n, "file": p, "aspect": im.width / max(1, im.height)}
            break
    return {"crayon": crayon, "paper": paper, "text": text, "ink": ink, "accent": accent,
            "accent_fill": accent_fill, "heads": heads, "card": card, "logo": logo}  # fmt: skip


def pick_head(st, words):
    """The film's type that has every glyph of the words (its headline first)."""
    for h in st["heads"]:
        if covers(h["file"], plain(words)):
            return h
    return None


def _reads(a, b):
    return float(contrast(luminance(a), luminance(b)))


def _ink(st, head, under):
    """The words' ink: the film's own colour for this type where it reads on what is under it
    (with room to spare: grain and paper texture take a little off it on the picture), else the
    one of the film's text, ink and paper colours that does, else the best of them deepened --
    or lightened -- just enough, its hue kept. A crayon film's own text colour on its own paper
    measured 4.2-4.5:1 once drawn (2026-09-29): a touch darker reads at 168 px and looks the same."""
    need = cfg()["contrast_min"] + cfg()["ink_margin"]
    cands = [head["col"], st["text"], st["ink"], st["paper"]]
    for c in cands:
        if _reads(c, under) >= need:
            return c
    best = max(cands, key=lambda c: _reads(c, under))
    return fit_contrast(best, under, need)


def _accent(st, ink, under):
    """The starred word's colour: the film's accent for words, or its accent, where it reads with
    the ink's margin to spare (a crayon film's rust accent on its pale card: 4.6:1 as colours,
    4.2:1 once drawn under the grain and vignette, 2026-09-29) -- else deepened just enough."""
    need = cfg()["contrast_min"] + cfg()["ink_margin"]
    for c in (st["accent"], st["accent_fill"]):
        if c != ink and _reads(c, under) >= need:
            return c
    return fit_contrast(st["accent"], under, need + 0.3)


def _lines(b, ax, top, anchor, head, ink, accent, rot=0.0, cx=0.0, cy=0.0, stroke=None):
    out, y = [], top + b["ascent"]
    for L in b["lines"]:
        x = {"start": ax, "end": ax - L["w"], "middle": ax - L["w"] / 2}[anchor]
        out.append({"x": round(x, 1), "y": round(y, 1), "size": b["px"], "w": round(L["w"], 1),
                    "family": head["family"], "wt": head["weight"], "runs": runs(L["words"], ink, accent),
                    "rot": rot, "cx": round(cx, 1), "cy": round(cy, 1),
                    "stroke": {"w": round(stroke["w"] * b["px"], 1), "col": rgb_hex(stroke["col"])} if stroke else None})  # fmt: skip
        y += b["step"]
    return out


def _font(head):
    return {"file": head["file"], "weight": head["weight"], "tracking": 0.0, "upper": False}


# ------------------------------------------------------------------ layouts
def layout_headline(img, words, st, glow=False, where=None):
    """The words large over the picture, in the film's headline type and colours, where they
    hide the least of it (inside the writer's `where` when it has room). On a busy part of the
    picture, a soft glow of the film's paper goes behind them -- the film's own ground, not an
    outline the film never uses. None when they cannot be set legibly."""
    c, h = cfg(), cfg()["headline"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    dm, sm = detail_map(img), subject_map(img)
    avoid = text_boxes(img, min_h=cfg()["text"]["headline_min_h_px"])
    tried = []
    for cap, area in tries(region(where)):
        if tried and area is None and tried[-1][2] is not None:
            break  # the writer's place had room: keep to it
        pad = h["pad_frac"] * cap + (c["glow"]["grow_frac"] * cap if glow else 0)
        b = block_at(toks, font, cap, W * h["max_w_frac"], H * 0.62, h["max_lines"], c["cap"]["line_gap"], pad)  # fmt: skip
        if not b:
            continue
        p = place(round(b["w"]), round(b["h"]), dm, sm, area, h["centre_penalty"], avoid=avoid,
                  whole=glow, busy_weight=h["busy_weight"])  # fmt: skip
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
    ink = _ink(st, head, under)
    if not glow and (busy > h["quiet_max"] or _reads(ink, under) < c["contrast_min"] + 1):
        return layout_headline(img, words, st, glow=True, where=where)
    grow = c["glow"]["grow_frac"] * b["cap"]
    halo = None
    if glow:
        g = c["glow"]
        # the film's paper where it reads with the ink, else the plainest tone that does
        col = st["paper"] if _reads(ink, st["paper"]) >= c["contrast_min"] + 1 else (
            (255, 255, 255) if luminance(ink) < 0.4 else (0, 0, 0))  # fmt: skip
        gb = box  # the glow is the block: the words sit inside it, their padding its edge
        halo = {"x": round(gb[0]), "y": round(gb[1]), "w": round(gb[2] - gb[0]), "h": round(gb[3] - gb[1]),
                "r": round(grow * 0.5), "col": rgb_hex(col), "alpha": g["alpha"],
                "blur": round(g["blur_frac"] * b["cap"])}  # fmt: skip
        under = col
    accent = _accent(st, ink, under)
    mid = x0 + b["w"] / 2
    anchor = "start" if mid < W * 0.42 else ("end" if mid > W * 0.58 else "middle")
    pad = h["pad_frac"] * b["cap"] + (grow if glow else 0)
    ax = {"start": x0 + pad, "end": box[2] - pad, "middle": (box[0] + box[2]) / 2}[anchor]
    return {
        "layout": "headline",
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": box,
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "glow": bool(halo),
        "spec": {
            "lines": _lines(
                b,
                ax,
                y0 + pad,
                anchor,
                head,
                ink,
                accent,
                stroke=head.get("stroke") if ink == head["col"] and not halo else None,
            ),
            "glow": halo,
        },  # fmt: skip
    }


def layout_card(img, words, st, where=None, logo_ok=True):
    """The words on one of the film's own cards -- its fill, corners, outline and shadow (a
    hand-drawn note on a crayon film, tilted a touch) -- where it hides the least."""
    c, k = cfg(), cfg()["card"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    look = st["card"]
    fill = look["fill"]
    ink = _ink(st, head, fill)
    accent = _accent(st, ink, fill)
    tilt = k["tilt_crayon"] if st["crayon"] else 0.0
    logo = st["logo"] if logo_ok else None
    dm, sm = detail_map(img), subject_map(img)
    avoid = text_boxes(img, min_h=cfg()["text"]["headline_min_h_px"])
    chosen = None
    for cap, area in tries(region(where)):
        if chosen and area is None and chosen[-1] is not None:
            break  # the writer's place had room: keep to it
        px_, py_ = k["pad_frac"][0] * cap, k["pad_frac"][1] * cap
        lh = k["logo_h_frac"] * cap if logo else 0.0
        lgap = k["logo_gap_frac"] * cap if logo else 0.0
        b = block_at(toks, font, cap, W * k["max_w_frac"] - 2 * px_, H * 0.6 - 2 * py_ - lh - lgap, k["max_lines"], c["cap"]["line_gap"])  # fmt: skip
        if not b:
            continue
        cw = max(b["w"], lh * st["logo"]["aspect"] if logo else 0) + 2 * px_
        ch = b["h"] + 2 * py_ + lh + lgap
        room = abs(math.sin(math.radians(tilt))) * cw  # a tilted card reaches past its box
        p = place(round(cw + room), round(ch + room), dm, sm, area, cfg()["headline"]["centre_penalty"],
                  avoid=avoid, whole=True, busy_weight=cfg()["headline"]["busy_weight"])  # fmt: skip
        if p and (chosen is None or p[3] < chosen[1][3]):
            chosen = (b, p, px_, py_, cw, ch, room, lh, lgap, area)
        if p and p[3] <= cfg()["headline"]["cover_max"]:
            chosen = (b, p, px_, py_, cw, ch, room, lh, lgap, area)
            break
    if not chosen:
        return None
    b, (x0, y0, busy, cover), px_, py_, cw, ch, room, lh, lgap, _ = chosen
    x, y = x0 + room / 2, y0 + room / 2
    rot = math.radians(tilt)
    cx, cy = x + cw / 2, y + ch / 2
    card = {"x": round(x, 1), "y": round(y, 1), "w": round(cw, 1), "h": round(ch, 1), "r": look["r"],
            "fill": rgb_hex(fill), "stroke": rgb_hex(look["stroke"]) if look["stroke"] else None,
            "strokeW": look["strokeW"], "shadow": look["shadow"], "sketch": look["sketch"], "rot": rot}  # fmt: skip
    extra = {}
    if logo:  # the logo sits in the card's top band, above the words
        extra["logo"] = {"name": st["logo"]["name"], "x": round(x + px_, 1), "y": round(y + py_ + lh / 2, 1),
                         "w": round(lh * st["logo"]["aspect"], 1), "h": round(lh, 1)}  # fmt: skip
    return {
        "layout": "card",
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": (round(x0), round(y0), round(x0 + cw + room), round(y0 + ch + room)),
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "spec": {
            "cards": [card],
            "lines": _lines(
                b, x + px_, y + py_ + lh + lgap, "start", head, ink, accent, rot, cx, cy
            ),
            **extra,
        },
    }


def layout_panel(img, words, st, where=None):
    """The picture on one side, the words on a panel of the film's own paper on the other, a rule
    of its accent between them and its logo above the words when it shows one. The picture slides
    (the film's camera moves; nothing is stretched) so its busy part stays in view and the film's
    own words are never under the panel."""
    c, pnl = cfg(), cfg()["panel"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    dm = detail_map(img)
    third = dm.shape[1] * 2 // 5
    sm = subject_map(img)
    words_in_film = text_boxes(img, min_h=cfg()["text"]["headline_min_h_px"])
    if where and "left" in where:
        sides = [True, False]
    elif where and "right" in where:
        sides = [False, True]
    else:  # the side that hides less of the subjects first
        sides = [True, False] if sm[:, :third].sum() <= sm[:, -third:].sum() else [False, True]
    fill = st["paper"]
    ink = _ink(st, head, fill)
    accent = _accent(st, ink, fill)
    safe, badge = safe_rects()
    cols = dm.mean(axis=0)
    cx = float((cols * np.arange(len(cols))).sum() / max(1e-6, cols.sum())) * 8
    logo = st["logo"]
    chosen = None
    for left, frac in ((s_, f) for f in pnl["w_fracs"] for s_ in sides):
        pw = round(W * frac)
        px0 = 0 if left else W - pw
        if left:
            want, lo, hi, view = pw + (W - pw) / 2 - cx, 0, pw, (pw, W)
        else:
            want, lo, hi, view = (W - pw) / 2 - cx, -pw, 0, (0, W - pw)
        # every line of the film's words either wholly in view or wholly under the panel -- never
        # sliced at its edge or slid off the frame
        ok = []
        for sh in np.arange(lo, hi + 1, 8.0):
            if all(
                (x0_ + sh >= view[0] and x1_ + sh <= view[1])
                or (x0_ + sh >= px0 and x1_ + sh <= px0 + pw)
                for x0_, _, x1_, _ in words_in_film
            ):
                ok.append(float(sh))
        if not ok:
            continue  # no slide does: the other side, a wider panel, or a card
        shift = min(ok, key=lambda sh: abs(sh - want))
        inner = pw * 0.1
        area = (max(px0 + inner, safe[0]), safe[1], min(px0 + pw - inner, safe[2]), safe[3])
        aw = area[2] - area[0]
        lw = lh = gap = 0
        if logo:
            lw = aw * pnl["logo_w_frac"]
            lh = lw / logo["aspect"]
            if lh > H * pnl["logo_max_h_frac"]:
                lh = H * pnl["logo_max_h_frac"]
                lw = lh * logo["aspect"]
        for cap in range(c["cap"]["max_px"], c["cap"]["min_px"] - 1, -c["cap"]["step_px"]):
            gap = pnl["logo_gap_frac"] * cap if logo else 0
            b = block_at(toks, font, cap, aw, area[3] - area[1] - lh - gap, pnl["max_lines"], c["cap"]["line_gap"])  # fmt: skip
            if not b:
                continue
            total = lh + gap + b["h"]
            y0 = (H - total) / 2
            tb = (area[0], y0 + lh + gap, area[0] + b["w"], y0 + total)
            if _hits(tb, badge):
                y0 = max(area[1], badge[1] - total - 8)
                tb = (area[0], y0 + lh + gap, area[0] + b["w"], y0 + total)
                if _hits(tb, badge) or y0 < area[1]:
                    continue
            chosen = (b, left, pw, px0, shift, area, y0, lh, lw, gap)
            break
        if chosen:
            break
    if not chosen:
        return None
    b, left, pw, px0, shift, area, y0, lh, lw, gap = chosen
    rw = pnl["rule_px"]
    spec = {
        "panel": {
            "x": px0,
            "w": pw,
            "fill": rgb_hex(fill),
            "rule": {
                "x": (pw - rw) if left else (W - pw),
                "w": rw,
                "col": rgb_hex(st["accent_fill"]),
            },
        },  # fmt: skip
        "lines": _lines(b, area[0], y0 + lh + gap, "start", head, ink, accent),
        "camera": {"shift": round(shift)} if shift else None,
    }
    if logo:
        spec["logo"] = {"name": logo["name"], "x": round(area[0], 1), "y": round(y0 + lh / 2, 1),
                        "w": round(lw, 1), "h": round(lh, 1)}  # fmt: skip
    return {
        "layout": "panel",
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": (
            round(area[0]),
            round(y0 + lh + gap),
            round(area[0] + b["w"]),
            round(y0 + lh + gap + b["h"]),
        ),
        "busy": 0.0,
        "shift": round(shift),
        "spec": spec,
    }


def layout_still(img):
    """The picture alone -- the film's camera pushed in a little toward its subjects, but only
    when the push keeps them, and the film's own words, whole."""
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
    camera = None
    if kept >= cfg()["still"]["keep_min"] and not cut:
        # the point the push keeps in place, so the crop [x0, x0 + cw] is what shows
        px = x0 * z / (z - 1)
        py = y0 * z / (z - 1)
        camera = {"zoom": z, "cx": round(px, 1), "cy": round(py, 1)}
    return {"layout": "still", "words": "", "spec": {"camera": camera} if camera else {}}


def layout(kind, img, words, st, glow=False, where=None):
    if kind == "headline":
        return layout_headline(img, words, st, glow, where)
    if kind == "card":  # with the film's logo when it fits, else the words alone
        return layout_card(img, words, st, where) or (
            layout_card(img, words, st, where, logo_ok=False) if st["logo"] else None
        )
    if kind == "panel":
        return layout_panel(img, words, st, where)
    return layout_still(img)


# ------------------------------------------------------------------ drawn by the film
def paint(film_dir, options, work, st, env=None):
    """Every option drawn by the film itself (sketch/thumb.js), in one browser run:
    {n: (the thumbnail, its letters, its footprint)} -- the last two white on black."""
    keys, used = {}, set()
    for o in options:
        k = round(o["t"], 2)
        while k in used:
            k = round(k + 0.01, 2)
        used.add(k)
        keys[o["n"]] = k
    os.makedirs(work, exist_ok=True)
    js = os.path.join(work, "spec.js")
    spec = {"%.2f" % keys[o["n"]]: o.get("spec") or {} for o in options}
    with open(js, "w", encoding="utf-8") as f:
        f.write("SK.THUMB = %s;\n" % json.dumps({"options": spec}, ensure_ascii=False))
    fonts = [h for h in st["heads"] if not h.get("film")]
    times = [base + keys[o["n"]] for o in options for base in (1000, 2000, 3000)]
    shots = render_stills(film_dir, times, into=work, env=env, head=[js, THUMB_JS], fonts=fonts, style=False)  # fmt: skip
    out = {}
    for o in options:
        k = keys[o["n"]]
        out[o["n"]] = (
            Image.open(shots[round(1000 + k, 2)]).convert("RGB"),
            Image.open(shots[round(2000 + k, 2)]).convert("L"),
            Image.open(shots[round(3000 + k, 2)]).convert("L"),
        )
    return out


def covered_text(o, foot):
    """Pixels of the film's own words that this option's additions cut into (letters, card,
    panel, logo), from its footprint pass -- the film's words where the camera slide moved them.
    A card or a panel may hide a line of them whole (98% of it); words drawn straight on the
    picture may touch none."""
    if foot is None:
        return 0
    a = np.asarray(foot) > 127
    shift = ((o.get("spec") or {}).get("camera") or {}).get("shift") or 0
    W, H = size()
    whole_ok = o["layout"] in ("card", "panel") or bool(o.get("glow"))
    n = 0
    for x0, y0, x1, y1 in text_boxes(o["img"], min_h=cfg()["text"]["headline_min_h_px"]):
        x0, x1 = int(max(0, x0 + shift)), int(min(W, x1 + shift))
        if x1 <= x0:
            continue
        hit = a[int(y0) : int(y1), x0:x1]
        k = int(hit.sum())
        if k and whole_ok and k >= 0.9 * hit.size:
            continue
        n += k
    return n


def checks(o, final, mask, foot=None):
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
    res["hides_text"] = covered_text(o, foot)
    if res["hides_text"] > c["text"]["hide_max_px"]:
        fails.append("it hides %d pixels of the film's own words" % res["hides_text"])
    m = np.asarray(mask) > 127
    if m.sum() < 50:
        fails.append("no letters were drawn")
        return res, fails
    # legibility where YouTube shows it smallest: the cap height the words were set at
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
    tol = 0.25 * o["cap"]  # a hand font's glyphs overhang their origin
    x0, y0, x1, y1 = o["box"]
    if o["layout"] != "card" and (
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
    # contrast: the letters against the ring of pixels just around them, on the finished
    # picture; 90% of letter pixels must reach it
    r = max(2, round(0.045 * o["px"]))
    inner = ndimage.binary_erosion(m, iterations=2)
    ring = ndimage.binary_dilation(m, iterations=r) & ~ndimage.binary_dilation(m, iterations=1)
    L = ndimage.gaussian_filter(luminance_map(final), c["contrast_smooth_px"])
    if inner.sum() < 20 or ring.sum() < 20:
        fails.append("the letters are too thin to measure")
    else:
        lr = float(np.median(L[ring]))
        ratio = contrast(L[inner], lr)
        res["contrast"] = round(float(np.percentile(ratio, 10)), 2)
        if res["contrast"] < c["contrast_min"]:
            fails.append("contrast %.2f:1 against what is around the letters" % res["contrast"])
    return res, fails


# ------------------------------------------------------------------ the whole thing
DROP = ("spec", "box", "head", "cap", "px", "busy", "cover", "glow", "shift")
FALLBACK = {
    "headline": ["headline+glow", "card", "still"],
    "card": ["still"],
    "panel": ["card", "still"],
}


def _lay(o, kind, st):
    if kind == "headline+glow":
        return layout_headline(o["img"], o["words"], st, glow=True, where=o["place"])
    if kind == "still" or not o["words"]:
        return layout_still(o["img"])
    return layout(kind, o["img"], o["words"], st, where=o["place"])


def first_layout(o, kind, st):
    """The first layout, from `kind` down its fallbacks, that can be set at all (the still
    alone always can)."""
    while True:
        lay = _lay(o, kind, st)
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


def film_length(film_dir):
    with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
        return float(json.load(f).get("duration") or 0)


def make_options(film_dir, concepts, out_dir, env=None, log=print):
    """Four finished options for a film, in its own look: [{n, file, layout, requested, at, t,
    words, font, checks, notes, final}], every one of them passing. Stills are cached per film;
    the JPEGs go to out_dir."""
    t0 = time.time()
    length = film_length(film_dir)
    work = os.path.join(film_dir, "temp", "thumbs", "work")
    shutil.rmtree(work, ignore_errors=True)
    # 1. every frame the settle step looks at, in one browser run (the probe rides along)
    want = set()
    for o in concepts:
        want |= set(settle_times(o["at"], length)[1])
    stills = render_stills(film_dir, want, env=env)
    st = film_style(film_dir, env)
    t_stills = time.time() - t0
    # 2. the frame, then the words on it, in the film's look
    opts = []
    for i, cpt in enumerate(concepts, 1):
        t, _ = settle(cpt["at"], stills, length)
        kind = RENAMED.get(cpt["layout"], cpt["layout"])
        o = {"n": i, "at": cpt["at"], "t": t, "requested": kind, "words": cpt["words"],
             "place": cpt.get("place"), "notes": [], "tried": []}  # fmt: skip
        if abs(t - cpt["at"]) > 0.01:
            o["notes"].append("settled at %.2f s (asked %.2f s)" % (t, cpt["at"]))
        o["img"] = load_still(stills[t])
        o.update(first_layout(o, kind, st))
        opts.append(o)
    # 3. draw, check, fall back -- until every option passes
    for rnd in range(4):
        pending = [o for o in opts if "final" not in o]
        if not pending:
            break
        shots = paint(film_dir, pending, os.path.join(work, "round%d" % rnd), st, env)
        for o in pending:
            final, mask, foot = shots[o["n"]]
            res, fails = checks(o, final, mask, foot)
            o["checks"] = res
            if not fails:
                o["final"] = final
                continue
            tag = o["layout"] + ("+glow" if o.get("glow") else "")
            o["notes"].append("%s failed: %s" % (tag, "; ".join(fails)))
            o["tried"].append(tag)
            lay = first_layout(o, _next(o), st)
            for k in DROP:
                o.pop(k, None)
            o.update(lay)
            if o["layout"] == "still":
                o["words"] = ""
    for o in opts:
        if "final" not in o:  # out of rounds: the frame as the film drew it, which fails nothing
            for k in DROP:
                o.pop(k, None)
            o.update({"layout": "still", "words": "", "spec": {}})
            o["final"] = o["img"]
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
            "font": (o.get("head") or {}).get("family"), "checks": o.get("checks", {}),
            "notes": o["notes"], "final": o["final"],
        })  # fmt: skip
    log(
        "  thumbnails: %d options in %.1f s (stills %.1f s, %d frames); type %s"
        % (
            len(out),
            time.time() - t0,
            t_stills,
            len(want),
            ", ".join(sorted({x["font"] for x in out if x["font"]})) or "-",
        )  # fmt: skip
    )
    return out


def jpeg(im, quality=None):
    buf = BytesIO()
    im.save(buf, "JPEG", quality=quality or cfg()["jpeg_quality"], optimize=True, progressive=True)
    return buf.getvalue()


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
