"""Thumbnail options from a film's own pieces or frames, in the film's own look, made the way
YouTube thumbnails are: what the picture shows, where the words go, what they look like, and
proof that the result reads where YouTube shows it smallest.

A film that shows pictures -- cut-out characters and props, photographs -- gets posters composed
from them by a template: one picture large on the film's own page (a figure from the waist up,
an object whole), another tucked in behind it, the words beside or above. The template varies
from option to option and film to film (which of two skeletons, the side, the lean, the paper
behind the hero), from the film's key, so a channel's thumbnails share a hand without being one
picture. A film that draws everything itself gets a frame of it instead, as below.

The picture is always the film -- a frame of it with its own titles and labels left out, its
camera pushed in on its subject -- and so is everything added to it: the words are set in the
film's own title type, case, colours and outline, on its own labels, cards and paper, with its own
logo -- drawn by the film's engine (sketch/thumb.js, run ahead of the film's code), not laid over
it by a template. What the film's look is, is read off the film while it draws: every text style,
card, label strip and picture it uses (the probe), so a collage film in indigo-edged Oswald
capitals gets an indigo-edged Oswald headline, a crayon film its hand-drawn type and paper. The
words are laid out here, in Python, with the same font files the page draws them with, so the line
breaks, the size and the cap height are numbers this module chose. Each option is drawn three
times -- as it will look, its letters alone, and everything it added -- and the checks read the
finished picture through those.

    stills     frames of a sketch film (its manifest copied without the Free plan's closing), and
               each candidate again without the film's own words (the 4000 pass, which also
               notes where its pictures, cards and bursts landed), by sketch-render.py --stills
    look       the film's title type and outline, ink, accent, paper, labels, cards and logo
    moments    the times a writer chooses from, and the labelled sheet it sees them on
    concepts   four {at, words, layout, place}: inside the film, apart, short, the first the
               video's message
    settle     the frame near a moment that is not mid-transition, and not a thin one
    posters    for a film with pictures: its pieces (film_pieces), who each poster is built on
               (poster_heroes), the film's bare page (the 5000 pass) and the template on it
               (layout_poster, poster_variant) -- in place of the two steps below
    compose    the subject (the film's pictures, else saliency), the side the words take, the push
    layout     size, line breaks and the cleanest place for the words, in the film's type
    draw       one browser run for every option: the thumbnail, its letters, its footprint
    checks     cap height at 168 px, contrast, YouTube's overlays, the film's own words kept clear
    fallbacks  a poster's words on strips of the film's paper, then a frame; on a frame a glow
               of the film's paper, then a card, then the frame alone -- an option that fails is
               never shown

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
import threading
import subprocess
import collections
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _sketch  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageColor, ImageDraw, ImageFont  # noqa: E402

CONFIG = "config/thumbnails/thumbnails.json"
THUMB_JS = os.path.join(_env.ROOT, "sketch", "thumb.js")
# How stills are drawn. v2: a collage film's cut-outs (.webp) are in them -- v1 stills left every
# one out, so its thumbnails, moments sheet and share picture showed empty paper (2026-09-30).
# v3: the probe also notes the pictures a film draws itself, past SK.image (2026-10-05).
STILLS = "v3"
DECLUTTER = 4000  # a still's time + this: the film with its own words left out (sketch/thumb.js)
# How options are designed. yt-2: the film's own words left out, its subject pushed in, the
# message large in its title type and outline, its logo (2026-09-30). Options saved under another
# design are made again (studio/thumbs.py saved()).
# yt-3: a film that shows pictures gets posters composed from them -- its own cut-outs large on
# its own page, its words in its title type or on its label strips -- not frames of it
# (2026-10-05: the frames read as slides with a caption; see docs/reference.md).
DESIGN = "yt-3"
LAYOUTS = ("poster", "headline", "card", "panel", "still")
RENAMED = {"slab": "card"}  # a writer (or an older draft) may still say slab
WORD = re.compile(r"[\w'’-]+", re.UNICODE)
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it",
    "of", "on", "or", "the", "this", "to", "what", "why", "with", "you", "your",
}  # fmt: skip

_CFG = None
_CACHE = {}
# Decoded stills, least recently used first, up to STILLS_MB. A 1080p still is 6.2 MB decoded and a
# film's thumbnails look at ~40, so an unbounded cache grows by ~250 MB a film in a process that
# makes many: `share.py --missing` held 15 GB of the studio VM's 16 after 55 films (2026-09-29),
# and the films being made could not start Claude. The cap holds two films at once (thumbs.JOBS).
STILLS_MB = int(os.environ.get("THUMB_STILLS_MB", "600"))
_STILLS = collections.OrderedDict()  # path -> (image, bytes)
_STILLS_LOCK = threading.Lock()  # thumbnails run in threads (thumbs.py: asyncio.to_thread)


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


JOINED = re.compile(r"[֐-ࣿיִ-﷿ﹰ-ﻼ]")  # Hebrew, Arabic, Persian...


def shapes():
    """Can Pillow shape text here (libraqm)? Letters that join -- Persian, Arabic -- are far
    narrower joined than one by one, and only a shaping engine measures them as a page draws them."""
    if "raqm" not in _CACHE:
        from PIL import features

        _CACHE["raqm"] = bool(features.check("raqm"))
    return _CACHE["raqm"]


def pil_font(path, px, wt=None):
    """Pillow's font at `px`; a variable font (Caveat's is) set to the weight it is drawn at, so
    what is measured here is what the page draws. Pillow shapes with libraqm where it has it
    (shapes(): the studio's machine does, a Windows laptop does not)."""
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
NUMBER = {1: "one", 2: "two", 3: "three", 4: "four"}


def check_concepts(raw, length, title="", n=4, layouts=None, pieces=None):
    """Four {at, words, layout} held to the rules: (concepts, notes, problems). `n` and `layouts`
    ask for another number of them, from fewer layouts (the share image: two, headline or card).
    A concept may name the pictures its poster is built on ("hero", "with": names from `pieces`,
    the film's own); a name the film has no picture for is dropped, and the poster then takes the
    pieces of its moment's frame. A poster's writer gives no layout: one is kept in hand for a
    concept that cannot be made as a poster.

    `notes` are what was put right here; `problems` ({n, text}; n is the thumbnail, None for
    all of them) are what only the writer can fix -- words that are too long or repeat the
    title, moments on top of each other. A draft is asked once more with them; what survives a
    second answer is fixed up by fill_concepts()."""
    c, notes, problems = cfg(), [], []
    edge = cfg()["moments"]["edge"]
    items = [x for x in (raw if isinstance(raw, list) else []) if isinstance(x, dict)]
    count = NUMBER.get(n, str(n))
    if len(items) != n:
        problems.append(
            {"n": None, "text": "give exactly %s thumbnails (you gave %d)" % (count, len(items))}
        )
    items = items[:n]
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
        o = {"at": round(at, 2), "words": words, "layout": lay, "place": where}
        hero = str(x.get("hero") or "").strip() or None
        extra = x.get("with") if isinstance(x.get("with"), list) else []
        extra = [str(e).strip() for e in extra if str(e).strip()][:1]
        if pieces is not None:
            for name in [hero, *extra]:
                if name and name not in pieces:
                    notes.append("thumbnail %d: the film has no picture named %r" % (i, name))
            hero = hero if hero in pieces else None
            extra = [e for e in extra if e in pieces and e != hero]
        if hero or extra:
            o.update(hero=hero, **{"with": extra})
        out.append(o)
    # the layouts asked for, each as many times as it is listed (a second headline): an unknown
    # one, or one past its count, takes a layout nobody used yet
    free = list(layouts or c["concepts"]["layouts"])
    keep = []
    for o in out:
        keep.append(o["layout"] in free)
        if keep[-1]:
            free.remove(o["layout"])
    for o, kept in zip(out, keep, strict=True):
        if not kept and free:
            if o["layout"]:  # a poster's writer names none: nothing was changed
                notes.append("a %r thumbnail became %r" % (o["layout"], free[0]))
            o["layout"] = free.pop(0)
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
        problems.append(
            {"n": None, "text": "the %s moments must be at least %.0f s apart" % (count, gap)}
        )
    return out, notes, problems


def fill_concepts(concepts, moments, length, n=4):
    """What a writer's answer could not supply, made up from the film: a missing thumbnail is
    the picture alone at a moment nobody chose, and moments too close together are spread. `n`
    is how many there are to be."""
    gap = cfg()["concepts"]["min_gap"]
    out = []
    for o in concepts:
        if all(abs(o["at"] - p["at"]) >= gap for p in out):
            out.append(dict(o))
    spare = [t for t in moments if all(abs(t - p["at"]) >= gap for p in out)]
    for t in spread(spare, n - len(out)):
        out.append({"at": round(t, 2), "words": "", "layout": "still"})
    return out[:n]


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
        try:  # where the render finds them: a collage film's cut-outs are .webp
            for name, p in _sketch.painted_images(pj, film_dir).items():
                images.setdefault(name, ab(p))
        except ValueError:  # a name no path may be built from: the render refuses it too
            pass
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
    # what a template's film reads as SK.DATA (content.json, a route): the film's own files, by
    # their place. Left relative, every still of every template film failed (the copy has no
    # content.json beside it), so such a film got no share picture and no thumbnail options.
    if isinstance(m.get("data"), dict):
        m["data"] = {k: ab(p) if isinstance(p, str) else p for k, p in m["data"].items()}
    m.pop("paint", None)
    audio = dict(m.get("audio") or {})
    audio["vo_timeline"] = ab(audio.get("vo_timeline") or "audio/vo/timeline.json")
    m["audio"] = {"vo_timeline": audio["vo_timeline"]}  # stills need no score or effects
    # the film's own head scripts first (a project's brand.js: SK.BRAND, which its code reads)
    own = [ab(p) for p in (m.get("head") or {}).get("scripts", []) if isinstance(p, str)]
    m["head"] = {"scripts": own + list(head if head is not None else [THUMB_JS])}
    m["slug"] = "thumbs"
    os.makedirs(into, exist_ok=True)
    out = os.path.join(into, "sketch.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    return out


def film_key(film_dir):
    """What a film's frames depend on: a changed film gets new stills, an unchanged one keeps
    them (a finished film does not change, so this is nearly always a cache hit). STILLS names
    how they are drawn: stills made before a fix to that are made again."""
    h = hashlib.sha256()
    h.update(STILLS.encode() + b"\0")
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
                      lambda x: (x.get("kind", "txt"), x["font"], x["wt"], x["col"], (x.get("stroke") or {}).get("col")),
                      ("n", "chars", "letters", "upper"), ("max",))  # fmt: skip
    out["card"] = fold(old.get("card") or [], new.get("card") or [],
                       lambda x: (x["fill"], x["r"], x.get("stroke"), x.get("shadow")), ("n", "area"), ())  # fmt: skip
    out["strip"] = fold(old.get("strip") or [], new.get("strip") or [],
                        lambda x: (x["col"], x["ink"], x["font"], x["wt"]), ("n", "chars"), ("max",))  # fmt: skip
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
            with open(rep, encoding="utf-8") as f:
                new = json.load(f)
            got = new.pop("boxes", None) or {}
            if got:  # where each picture landed on the uncluttered pass, per still
                bp = os.path.join(into, "boxes.json")
                old_b = {}
                if os.path.exists(bp):
                    with open(bp, encoding="utf-8") as f:
                        old_b = json.load(f)
                old_b.update(got)
                with open(bp + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(old_b, f)
                os.replace(bp + ".tmp", bp)
            if style:
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


def boxes_at(into, t):
    """[{name, box}] of the pictures the film drew in its uncluttered still at `t` (screen
    pixels), as the 4000 pass recorded them; [] when it drew none or was not asked."""
    try:
        with open(os.path.join(into, "boxes.json"), encoding="utf-8") as f:
            return json.load(f).get("%.2f" % t) or []
    except (OSError, ValueError):
        return []


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
    """A still, decoded once while it is in use; the least recently used go past STILLS_MB."""
    with _STILLS_LOCK:
        if path in _STILLS:
            _STILLS.move_to_end(path)
            return _STILLS[path][0]
    img = Image.open(path).convert("RGB")
    size = img.width * img.height * 3
    with _STILLS_LOCK:
        _STILLS[path] = (img, size)
        total = sum(n for _, n in _STILLS.values())
        while total > STILLS_MB * 1_000_000 and len(_STILLS) > 1:
            _, (_, n) = _STILLS.popitem(last=False)
            total -= n
    return img


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
          avoid=(), whole=False, level=0.0, edges=None):  # fmt: skip
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
    ei = None
    if edges is not None:  # (threshold, share): at most `share` of the block's cells over it
        e_thr, e_max = edges
        ei = np.pad((dmap > e_thr).astype("float32"), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
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
            if ei is not None:
                e = ei[cy1, cx1] - ei[cy, cx1] - ei[cy1, cx] + ei[cy, cx]
                if e > e_max * max(1, (cy1 - cy) * (cx1 - cx)):
                    continue
            cover = float(si[cy1, cx1] - si[cy, cx1] - si[cy1, cx] + si[cy, cx])
            # a small nudge off dead centre, where the subject usually is
            dx = abs((x + bw / 2) / W - 0.5) * 2
            dy = abs((y + bh / 2) / H - 0.5) * 2
            score = cover + busy_weight * busy + centre_penalty * (1 - max(dx, dy)) * 0.01
            # on an even picture, the block level with the middle of its area, not in a corner
            score += level * abs((y + bh / 2) - (ay0 + ay1) / 2) / H
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
    tr = font.get("tracking", 0.0) * px
    up = font.get("upper")
    words = [[(t.upper() if up else t, a) for t, a in segs] for segs in toks]
    # letters that join are measured joined where Pillow can (shapes()); elsewhere one by one,
    # which is wider than the page draws them: the words come out smaller, never out of their box
    joined = bool(JOINED.search(" ".join(word_text(w) for w in words)))
    f = pil_font(font["file"], px, font.get("weight"))
    how = {"direction": "rtl"} if joined and shapes() else {}
    best = None
    for sp in _splits(len(words), max_lines):
        # a dash belongs to the line it ends, never the start of the next
        if any(not re.search(r"\w", word_text(words[a])) for a, _ in sp[1:]):
            continue
        lines = []
        for a, b in sp:
            ws = words[a:b]
            text = " ".join(word_text(w) for w in ws)
            x0, y0, x1, y1 = f.getbbox(text, anchor="ls", **how)
            w = f.getlength(text, **how) + tr * max(0, len(text) - 1)
            # a hand font's swash reaches past its advance (Caveat's d, 30 px at a 246 px size):
            # the room a line takes is its ink, where that is wider
            over = max(0.0, x1 - w)
            lines.append({"words": ws, "text": text, "w": w + over, "top": y0, "bottom": y1})
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
def _chroma(rgb):
    return (max(rgb) - min(rgb)) / 255.0


def _near(a, b, d=60):
    """Two colours a viewer would call the same one (RGB distance under d)."""
    return math.dist(a[:3], b[:3]) < d


def film_style(film_dir, env=None):
    """How this film looks, for its thumbnails, from what its probe saw it draw:

    crayon      hand-drawn (it boils) or clean
    paper, text, ink, accent, accent_fill   its palette (SK.C: the ground's colours, as the
                film set them), as (r, g, b)
    heads       the type to set words in, best first: the film's own titles (SK.txt, and
                SK.headline on a collage film), biggest first, each with its colour, its case
                (a film that titles in capitals gets capitals), its tracking and its outline;
                then its label type; then, for words its type has no glyphs for or a film with no
                text of its own, the studio's print hand (drawn) or a plain sans (clean)
    outline     how the film makes a title shout, when it does: the outline of its biggest
                outlined title, and the fills words take inside it -- the most neutral of its
                outlined fills for the words, another of them (else its accent) for the starred
                one. A collage film's cream and lemon Oswald edged in indigo. None when it never
                outlines a title
    card        what the film sets words on: its label strip (collage.js's tape) when it labels
                with strips more than it uses cards, else its biggest card, else one of its paper
                edged in its accent (a hand-drawn note on crayon)
    logo        a logo it shows ({name, file, aspect, round}: round when it is a square picture,
                drawn as a paper badge like a channel's face), or None
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
    rank = {"tape": 1}  # a title's type before a label's

    def lettered(x):  # a style that set words, not only a digit or a "?"
        return x["letters"] >= 3 if "letters" in x else x.get("chars", 0) >= 2

    styles = [x for x in rep.get("txt") or [] if lettered(x) and x.get("max", 0) >= 24]
    heads, seen = [], set()
    for x in sorted(styles, key=lambda x: (rank.get(x.get("kind"), 0), -x["max"], -x["n"])):
        f = font_for(fonts, x["font"], x["wt"])
        if f and (x["font"], _weight(x["wt"])) not in seen:
            seen.add((x["font"], _weight(x["wt"])))
            k = x.get("stroke") or None
            heads.append({"file": f, "family": x["font"], "weight": str(_weight(x["wt"])),
                          "col": colour(x["col"], text), "size": x["max"], "film": True,
                          "upper": x.get("letters", 0) >= 3 and x.get("upper", 0) >= 0.8 * x["letters"],
                          "ls": float(x.get("ls") or 0),
                          "stroke": {"w": float(k["w"]), "col": colour(k["col"], ink)} if k else None})  # fmt: skip
    for f in c["fonts"]["no_text"]["crayon" if crayon else "clean"] + c["fonts"]["fallback"]:
        heads.append(dict(f, col=text, film=False))
    outline = outline_of(styles, text, paper, ink, accent, accent_fill)
    strips = rep.get("strip") or []
    cards = rep.get("card") or []
    strip = max(strips, key=lambda x: (x.get("n", 0), x.get("chars", 0)), default=None)
    card = max(cards, key=lambda x: x.get("area", 0), default=None)
    if strip and strip.get("n", 0) >= sum(x.get("n", 0) for x in cards):
        card = {"strip": True, "fill": colour(strip["col"], paper), "ink": colour(strip["ink"], text),
                "r": 0, "stroke": None, "strokeW": 0, "shadow": True, "sketch": False}  # fmt: skip
    elif card:
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
                a = im.width / max(1, im.height)
                rgba = im.convert("RGBA")
                w, h = rgba.size
                corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
                opaque = min(rgba.getpixel(xy)[3] for xy in corners) > 200
            logo = {"name": n, "file": p, "aspect": a, "round": 0.8 <= a <= 1.25 and opaque}
            break
    return {"crayon": crayon, "paper": paper, "text": text, "ink": ink, "accent": accent,
            "accent_fill": accent_fill, "heads": heads, "outline": outline, "card": card,
            "strips": [colour(x["col"], paper) for x in strips if x.get("n", 0) >= 2],
            "logo": logo}  # fmt: skip


def outline_of(styles, text, paper, ink, accent, accent_fill):
    """How a film makes a title shout, from its text styles (the probe's): the outline of its
    biggest outlined title and the fills words take inside it -- the most neutral of its outlined
    fills (else its text or paper colour) that reads on the outline for the words, another of them
    (else its accent) for the starred word. None when it never outlines a title."""
    c = cfg()
    need = c["contrast_min"] + c["ink_margin"]
    o = c["outline"]
    outs = [x for x in styles if x.get("kind") != "tape" and x.get("stroke")
            and float(x["stroke"].get("w") or 0) >= o["min_w"]]  # fmt: skip
    if not outs:
        return None
    big = max(outs, key=lambda x: x["max"])
    sc = colour(big["stroke"]["col"], ink)
    fills = [colour(x["col"], text) for x in sorted(outs, key=lambda x: -x["max"])]
    ok = [f for f in [*fills, text, paper] if _reads(f, sc) >= need]
    if not ok:
        return None
    base = min(ok, key=lambda f: (_chroma(f), -_reads(f, sc)))
    acc = next((f for f in [*fills, accent_fill, accent]
                if not _near(f, base) and _reads(f, sc) >= need), None)  # fmt: skip
    return {"fill": base, "accent": acc or base,
            "stroke": {"w": min(o["max_w"], float(big["stroke"]["w"])), "col": sc}}  # fmt: skip


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
    4.2:1 once drawn under the grain and vignette, 2026-09-29) and does not look like the ink
    (a collage film's lemon words got a lemon accent) -- else deepened just enough."""
    need = cfg()["contrast_min"] + cfg()["ink_margin"]
    for c in (st["accent"], st["accent_fill"]):
        if not _near(c, ink) and _reads(c, under) >= need:
            return c
    return fit_contrast(st["accent"], under, need + 0.3)


def _pair(st, head, fill):
    """(ink, accent) for words set on a flat `fill` (a panel, a card, a strip): the film's outlined
    title colours when both read on it -- the thumbnail's words keep one voice across layouts --
    else its ink and accent for that fill."""
    need = cfg()["contrast_min"] + cfg()["ink_margin"]
    o = st.get("outline")
    if o and _reads(o["fill"], fill) >= need and _reads(o["accent"], fill) >= need:
        return o["fill"], o["accent"]
    ink = _ink(st, head, fill)
    return ink, _accent(st, ink, fill)


def _lines(b, ax, top, anchor, head, ink, accent, rot=0.0, cx=0.0, cy=0.0, stroke=None):
    out, y = [], top + b["ascent"]
    for L in b["lines"]:
        x = {"start": ax, "end": ax - L["w"], "middle": ax - L["w"] / 2}[anchor]
        out.append({"x": round(x, 1), "y": round(y, 1), "size": b["px"], "w": round(L["w"], 1),
                    "family": head["family"], "wt": head["weight"], "runs": runs(L["words"], ink, accent),
                    "rot": rot, "cx": round(cx, 1), "cy": round(cy, 1), "ls": round(b.get("tracking") or 0, 2),
                    "anchor": anchor,
                    "stroke": {"w": round(stroke["w"] * b["px"], 1), "col": rgb_hex(stroke["col"])} if stroke else None})  # fmt: skip
        y += b["step"]
    return out


def _font(head):
    ls = head.get("ls") or 0.0
    return {"file": head["file"], "weight": head["weight"], "upper": bool(head.get("upper")),
            "tracking": ls if ls >= 0.01 else 0.0}  # fmt: skip


# ------------------------------------------------------------------ the picture under the words
SIDES = ("left", "right", "top", "bottom")
HINT = {"left": "left", "top-left": "left", "bottom-left": "left", "right": "right",
        "top-right": "right", "top": "top", "bottom": "bottom"}  # fmt: skip


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _clip(b, box):
    return (max(b[0], box[0]), max(b[1], box[1]), min(b[2], box[2]), min(b[3], box[3]))


def subject_box(img, boxes):
    """(box, how): what the frame is of, in pixels. The pictures the film drew there -- a clay
    character, a product shot, a heart -- exactly, when it drew any worth the name (not its logo,
    not a painted scene filling the frame, not a speck, not one mostly off screen, not a prop a
    fraction the size of the main ones); else the middle of the uncluttered picture's saliency."""
    W, H = size()
    k = cfg()["compose"]
    frame = (0, 0, W, H)
    cand = []
    for b in boxes or []:
        box = tuple(float(v) for v in b["box"])
        a, vis = _area(box), _area(_clip(box, frame))
        name = str(b.get("name", ""))
        if not a or vis < 0.5 * a or "logo" in name.lower() or name.startswith("#"):
            continue
        if vis > k["backdrop_frac"] * W * H or vis < k["min_frac"] * W * H:
            continue
        cand.append((_clip(box, frame), vis))
    if cand:
        big = max(v for _, v in cand)
        keep = [bx for bx, v in cand if v >= k["minor"] * big]
        return (min(b[0] for b in keep), min(b[1] for b in keep),
                max(b[2] for b in keep), max(b[3] for b in keep)), "pictures"  # fmt: skip
    sm = subject_map(img)
    q = k["mass"]
    cx, cy = np.cumsum(sm.sum(axis=0)), np.cumsum(sm.sum(axis=1))
    x0, x1 = int(np.searchsorted(cx, q)) * 8, (int(np.searchsorted(cx, 1 - q)) + 1) * 8
    y0, y1 = int(np.searchsorted(cy, q)) * 8, (int(np.searchsorted(cy, 1 - q)) + 1) * 8
    return (x0, y0, min(W, x1), min(H, y1)), "saliency"


def _pictures(boxes):
    """The film's pictures in a frame (not its bursts), as (name, box)."""
    return [(str(b.get("name", "")), tuple(float(v) for v in b["box"]))
            for b in boxes or [] if not str(b.get("name", "")).startswith("#")]  # fmt: skip


def empty_backings(boxes, img=None):
    """The ids of what would show empty once the film's words are left out: its bursts and discs
    with no picture on them (backings for a number or a stamp -- empty paper circles), and its cards
    that held words and nothing else (a title card -- an empty white slab on a painted film,
    2026-09-30): words were left out inside it, no picture or other card is on it, and on the clean
    picture its inside is flat -- an app screen that lost only its heading keeps its rows."""
    dm = detail_map(img) if img is not None else None
    W, H = size()
    big = (
        cfg()["compose"]["backdrop_frac"] * W * H
    )  # a painted scene is behind everything, not on it
    pics = [b for _, b in _pictures(boxes) if _area(_clip(b, (0, 0, W, H))) <= big]
    gone = [tuple(float(v) for v in b["box"]) for b in boxes or [] if b.get("name") == "#words"]

    def holds(bb, p):
        return _area(_clip(p, bb)) >= 0.25 * min(_area(p), _area(bb))

    def inside(bb, w):
        return bb[0] <= w[0] <= bb[2] and bb[1] <= w[1] <= bb[3]

    out = []
    for b in boxes or []:
        bb = tuple(float(v) for v in b["box"])
        if b.get("name") == "#burst" and not any(holds(bb, p) for p in pics):
            out.append(b["id"])
        elif b.get("name") == "#card" and b.get("id") and any(inside(bb, w) for w in gone):
            # a card whose words were left out, with no picture and no other card on it
            if any(holds(bb, p) for p in pics) or any(
                o is not b and o.get("name") == "#card" and inside(bb, o["box"]) for o in boxes
            ):
                continue
            x0, y0, x1, y1 = bb
            mx, my = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
            cell = dm[max(0, int((y0 + my) // 8)) : max(0, int((y1 - my) // 8)),
                      max(0, int((x0 + mx) // 8)) : max(0, int((x1 - mx) // 8))] if dm is not None else None  # fmt: skip
            if (
                cell is not None
                and cell.size
                and float(cell.mean()) < cfg()["declutter"]["empty_detail"]
            ):
                out.append(b["id"])
    return out


def frame_border(img):
    """Boxes of the flat band a film draws round an inset sheet (a collage film's indigo frame),
    one per side that has one: rows or columns from the edge in the edge's own colour, up to
    border_frac of the frame, before the picture's colour changes."""
    W, H = size()
    k = cfg()["compose"]
    a = np.asarray(img.convert("RGB").resize((W // 4, H // 4), Image.BILINEAR), dtype="float32")
    h, w = a.shape[:2]
    out = []
    for side in ("top", "bottom", "left", "right"):
        n = round(k["border_frac"] * (h if side in ("top", "bottom") else w))
        line = {"top": lambda i: a[i], "bottom": lambda i: a[h - 1 - i],
                "left": lambda i: a[:, i], "right": lambda i: a[:, w - 1 - i]}[side]  # fmt: skip
        edge = line(0).mean(axis=0)
        if float(np.abs(line(0) - edge).mean()) > 12:  # the edge itself is not one flat colour
            continue
        d = 0
        while d < n and float(np.abs(line(d).mean(axis=0) - edge).mean()) < 10:
            d += 1
        if 0 < d < n:
            px = 4 * d
            out.append({"top": (0, 0, W, px), "bottom": (0, H - px, W, H),
                        "left": (0, 0, px, H), "right": (W - px, 0, W, H)}[side])  # fmt: skip
    return out


def compose(img, boxes, hint=None, sides=SIDES, frac=None):
    """Which side of the frame the words take, and how far the film's camera pushes in so its
    subject fills the rest -- the grammar of a YouTube thumbnail (the subject large on one side,
    the words on the other) out of the film's own frame, which it draws again at the push (no
    pixel is stretched). Every side, push (1.0 to max_zoom -- less on a painted scene, whose
    pixels would go soft, and on a guessed subject) and position the push allows is scored: the
    subject as large as it gets, less what of it lies under the words or off screen, less every
    other picture cut in two by the frame, less the small print left in view (a progress bar's
    labels: the clean picture keeps what is under min_words_px), never the film's logo cut in two.
    `hint` is the writer's `place`, a nudge when two sides are close.

    {side, zone (the words' area on screen), camera (the push, or None), img (the picture as the
    push shows it), subject (its box on screen), zoom, logo (the film's logo box on screen when the
    frame shows it whole, else None), how, hide (empty_backings), pics (the film's other pictures
    and cards on screen: what words over the picture should not cross), score, alts (the next
    sides, best first, each a dict like this one)}."""
    W, H = size()
    k = cfg()["compose"]
    S, how = subject_box(img, boxes)
    frame = (0, 0, W, H)
    pics = _pictures(boxes)
    raster = any(_area(_clip(b, frame)) > k["backdrop_frac"] * W * H for _, b in pics)
    zmax = k["max_zoom_raster"] if raster else k["max_zoom"]
    if how == "saliency":
        zmax = min(zmax, k["max_zoom_saliency"])
    logos = [b for n, b in pics if "logo" in n.lower()]
    cards = [tuple(float(v) for v in b["box"]) for b in boxes or [] if b.get("name") == "#card"]
    others = [b for n, b in pics if "logo" not in n.lower()] + cards
    others = [
        b for b in others if 0.5 * _area(b) < _area(_clip(b, frame)) < k["backdrop_frac"] * W * H
    ]
    # the small print left on the clean picture, away from the subject: chrome to crop
    chrome = [b for b in text_boxes(img, min_h=0)
              if not (S[0] <= (b[0] + b[2]) / 2 <= S[2] and S[1] <= (b[1] + b[3]) / 2 <= S[3])]  # fmt: skip
    chrome_area = sum(_area(b) for b in chrome)
    border = frame_border(img)
    border_area = sum(_area(b) for b in border)
    m = k["margin_frac"] * H
    bests = {}
    for side in sides:
        best = None
        f = frac or (k["side_frac"] if side in ("left", "right") else k["band_frac"])
        tz = {"left": (0, 0, W * f, H), "right": (W * (1 - f), 0, W, H),
              "top": (0, 0, W, H * f), "bottom": (0, H * (1 - f), W, H)}[side]  # fmt: skip
        sz = {"left": (W * f, 0, W, H), "right": (0, 0, W * (1 - f), H),
              "top": (0, H * f, W, H), "bottom": (0, 0, W, H * (1 - f))}[side]  # fmt: skip
        sw, sh = max(1.0, S[2] - S[0]), max(1.0, S[3] - S[1])
        zfit = max(1.0, min(zmax, (sz[2] - sz[0] - 2 * m) / sw, (sz[3] - sz[1] - 2 * m) / sh))
        zs = sorted({1.0, round(zfit, 3)} | {round(z, 2) for z in np.arange(1.1, zmax + 1e-6, 0.1)})
        for z in zs:
            vw, vh = W / z, H / z
            cx0 = min(W - vw, max(0.0, (S[0] + S[2]) / 2 - (sz[0] + sz[2]) / 2 / z))
            cy0 = min(H - vh, max(0.0, (S[1] + S[3]) / 2 - (sz[1] + sz[3]) / 2 / z))

            def fit(v, lo_=0.0, hi_=0.0):
                return round(min(hi_, max(lo_, v)), 1)

            xs = {fit(cx0, 0, W - vw), 0.0, fit(W - vw, 0, W - vw),
                  fit(S[0] - m / z, 0, W - vw), fit(S[2] + m / z - vw, 0, W - vw)}  # fmt: skip
            ys = {fit(cy0, 0, H - vh), 0.0, fit(H - vh, 0, H - vh),
                  fit(S[1] - m / z, 0, H - vh), fit(S[3] + m / z - vh, 0, H - vh)}  # fmt: skip
            for vx0 in sorted(xs):
                for vy0 in sorted(ys):

                    def on(b, vx0=vx0, vy0=vy0, z=z):
                        return (
                            (b[0] - vx0) * z,
                            (b[1] - vy0) * z,
                            (b[2] - vx0) * z,
                            (b[3] - vy0) * z,
                        )

                    def seen(b, on=on):
                        return _area(_clip(on(b), frame)) / max(1.0, _area(on(b)))

                    Sp = on(S)
                    over = _area(_clip(Sp, tz)) / _area(Sp)
                    cut = 1 - seen(S)
                    halved = any(0.02 < seen(b) < 0.98 for b in logos)
                    split = sum(1 for b in others if 0.05 < seen(b) < 0.95)
                    left = (
                        sum(seen(b) * _area(b) for b in chrome) / chrome_area if chrome_area else 0
                    )
                    rim = (
                        sum(seen(b) * _area(b) for b in border) / border_area if border_area else 0
                    )
                    score = (Sp[3] - Sp[1]) / H - k["overlap_weight"] * over - k["cut_weight"] * cut
                    score -= k["cut_weight"] if halved else 0
                    score -= (
                        k["split_weight"] * split
                        + k["chrome_weight"] * left
                        + k["border_weight"] * rim
                    )
                    score += k["hint_bonus"] if HINT.get(hint or "") == side else 0
                    if best is None or score > best[0] + 1e-9:
                        best = (score, side, tz, z, vx0, vy0, Sp, [on(b) for b in logos],
                                [on(b) for b in others])  # fmt: skip
        bests[side] = best
    hide = empty_backings(boxes, img)

    def made(b):
        _, side, tz, z, vx0, vy0, Sp, lp, op = b
        camera, shown = None, img
        if z > 1.01:
            # the point the push keeps in place, so the crop [vx0, vx0 + W/z] is what shows
            camera = {
                "zoom": round(z, 4),
                "cx": round(vx0 * z / (z - 1), 2),
                "cy": round(vy0 * z / (z - 1), 2),
            }
            crop = (round(vx0), round(vy0), round(vx0 + W / z), round(vy0 + H / z))
            shown = img.crop(crop).resize((W, H), Image.LANCZOS)
        logo = next((b for b in lp if _area(_clip(b, frame)) >= 0.98 * _area(b)), None)
        return {"side": side, "zone": tuple(round(v) for v in tz), "camera": camera, "img": shown,
                "subject": tuple(round(v) for v in Sp), "zoom": round(z, 3), "logo": logo, "how": how,
                "hide": hide, "pics": [tuple(round(v) for v in b) for b in op], "score": round(b[0], 3)}  # fmt: skip

    ranked = sorted(bests.values(), key=lambda b: -b[0])
    out = made(ranked[0])
    out["alts"] = [made(b) for b in ranked[1 : k["alt_sides"]]]
    return out


# ------------------------------------------------------------------ layouts
def _lockup(logo, cap):
    """(height, width, gap) the film's logo takes above the words, or zeros without one."""
    if not logo:
        return 0, 0, 0
    k = cfg()["logo"]
    W, H = size()
    a = 1.0 if logo.get("round") else logo["aspect"]
    h = min(k["h_frac"] * H, k["max_w_frac"] * W / a)  # a wide wordmark is held to its width
    return round(h), round(h * a), round(k["gap_frac"] * cap)


def _logo_spec(logo, x, y_top, h, w, rim_col):
    """The logo for sketch/thumb.js: x its left, y its centre."""
    rim = round(cfg()["logo"]["rim_frac"] * h) if logo.get("round") else 0
    return {"name": logo["name"], "x": round(x, 1), "y": round(y_top + h / 2, 1), "w": w, "h": h,
            "round": bool(logo.get("round")), "rim": rim, "rimCol": rgb_hex(rim_col)}  # fmt: skip


def layout_headline(img, words, st, glow=False, area=None, logo=None, pics=(), strict=False):
    """The words large over the picture, in the film's title type -- in its outline when it
    outlines its titles, which reads on anything -- where they hide the least of the subject
    (inside `area`, the side compose() gave them, when they fit there), the film's logo above them
    when it is to carry one. Without an outline, a busy spot gets a soft glow of the film's paper
    behind the words -- its own ground, not an outline it never uses. None when they cannot be set
    legibly."""
    c, h = cfg(), cfg()["headline"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    out = st.get("outline") if head.get("film") else None
    if out:
        glow = False  # an outline carries the words over any picture
    dm, sm = detail_map(img), subject_map(img)
    words_in_film = text_boxes(img, min_h=c["text"]["headline_min_h_px"])
    # words over the picture touch none of the film's pictures when they can: a headline across a
    # building's dome read as a collision (2026-09-30); then, where there is no such room, they may
    shrunk = [(x0 + 12, y0 + 12, x1 - 12, y1 - 12) for x0, y0, x1, y1 in pics]
    tried = []
    passes = [words_in_film + shrunk, words_in_film] if pics else [words_in_film]
    edges = None
    if strict:  # the side it was given, clear of everything drawn, or nothing
        passes = passes[:1]
        if not out:
            edges = (h["edge_detail"], h["edge_share"])
    for avoid in passes:
        for cap, ar in tries(area):
            if strict and ar is None:
                break
            if tried and ar is None and tried[-1][2] is not None:
                break  # the side it was given had room: keep to it
            pad = h["pad_frac"] * cap + (c["glow"]["grow_frac"] * cap if glow else 0)
            lh, lw, lg = _lockup(logo, cap)
            max_h = H * h["max_h_frac"] - lh - lg
            b = block_at(
                toks,
                font,
                cap,
                W * h["max_w_frac"],
                max_h,
                h["max_lines"],
                c["cap"]["line_gap"],
                pad,
            )
            if not b:
                continue
            bw, bh = round(max(b["w"], lw + 2 * pad)), round(b["h"] + lh + lg)
            p = place(bw, bh, dm, sm, ar, h["centre_penalty"], avoid=avoid, whole=glow,
                      busy_weight=1.0 if out else h["busy_weight"], level=h["level"], edges=edges)  # fmt: skip
            if not p:
                continue
            tried.append((b, p, ar, lh, lw, lg, bw, bh))
            if p[3] <= h["cover_max"]:
                break
        if tried and tried[-1][2] is not None:
            break
    if not tried:
        return None
    pool = [t for t in tried if t[2] is not None] or tried  # the side it was given, first
    clear = [t for t in pool if t[1][3] <= h["cover_max"]]
    b, p, _, lh, lw, lg, bw, bh = (
        clear[0] if clear else min(pool, key=lambda t: (t[1][3], -t[0]["cap"]))
    )
    x0, y0, busy, cover = p
    wy0 = y0 + lh + lg  # the words, under the logo
    box = (x0, wy0, x0 + bw, y0 + bh)
    under = _mean_rgb(img, box)
    if out:
        ink, accent, stroke = out["fill"], out["accent"], out["stroke"]
    else:
        ink = _ink(st, head, under)
        stroke = head.get("stroke") if ink == head["col"] else None
        if not glow and (busy > h["quiet_max"] or _reads(ink, under) < c["contrast_min"] + 1):
            if strict:
                return None  # a clean place needs no glow; this side has none
            return layout_headline(img, words, st, glow=True, area=area, logo=logo, pics=pics)
    grow = c["glow"]["grow_frac"] * b["cap"]
    halo = None
    if glow:
        g = c["glow"]
        # the film's paper where it reads with the ink, else the plainest tone that does
        col = st["paper"] if _reads(ink, st["paper"]) >= c["contrast_min"] + 1 else (
            (255, 255, 255) if luminance(ink) < 0.4 else (0, 0, 0))  # fmt: skip
        halo = {"x": round(box[0]), "y": round(box[1]), "w": round(box[2] - box[0]), "h": round(box[3] - box[1]),
                "r": round(grow * 0.5), "col": rgb_hex(col), "alpha": g["alpha"],
                "blur": round(g["blur_frac"] * b["cap"])}  # fmt: skip
        under = col
        stroke = None
    if not out:
        accent = _accent(st, ink, under)
    mid = x0 + bw / 2
    anchor = "start" if mid < W * 0.42 else ("end" if mid > W * 0.58 else "middle")
    pad = h["pad_frac"] * b["cap"] + (grow if glow else 0)
    ax = {"start": x0 + pad, "end": box[2] - pad, "middle": (box[0] + box[2]) / 2}[anchor]
    spec = {
        "lines": _lines(b, ax, wy0 + pad, anchor, head, ink, accent, stroke=stroke),
        "glow": halo,
    }
    if logo:
        lx = {"start": x0 + pad, "end": box[2] - pad - lw, "middle": mid - lw / 2}[anchor]
        spec["logo"] = _logo_spec(
            logo, lx, y0, lh, lw, st["outline"]["fill"] if out else st["paper"]
        )
    return {
        "layout": "headline",
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": tuple(round(v) for v in box),
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "glow": bool(halo),
        "stroke_px": round(stroke["w"] * b["px"], 1) if stroke else 0,
        "spec": spec,
    }


def layout_strips(img, words, st, area=None, logo=None):
    """The words on strips like the film's own labels (collage.js's tape), a line to a strip,
    stacked and tilted as the film tilts its labels, where they hide the least -- the film's logo
    above them when it is to carry one."""
    c, k = cfg(), cfg()["strip"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    look = st["card"]
    fill = look["fill"]
    need = c["contrast_min"] + c["ink_margin"]
    ink = look["ink"] if _reads(look["ink"], fill) >= need else _ink(st, head, fill)
    accent = _accent(st, ink, fill)
    o = st.get("outline")
    if o and not _near(o["accent"], ink) and _reads(o["accent"], fill) >= need:
        accent = o["accent"]
    rot = k["rot"]
    dm, sm = detail_map(img), subject_map(img)
    avoid = text_boxes(img, min_h=c["text"]["headline_min_h_px"])
    chosen = None
    for cap, ar in tries(area):
        if chosen and ar is None and chosen[-1] is not None:
            break
        px_, py_ = k["pad"][0] * cap, k["pad"][1] * cap
        gap = (2 * py_ + k["gap_frac"] * cap) / cap
        lh, lw, lg = _lockup(logo, cap)
        hl = c["headline"]
        max_w, max_h = W * hl["max_w_frac"] - 2 * px_, H * hl["max_h_frac"] - 2 * py_ - lh - lg
        b = block_at(toks, font, cap, max_w, max_h, hl["max_lines"], gap)
        if not b:
            continue
        bw = max(max(L["w"] for L in b["lines"]) + 2 * px_, lw)
        bh = b["h"] + 2 * py_ + lh + lg
        room = abs(math.sin(rot)) * bw
        p = place(round(bw + room), round(bh + room), dm, sm, ar, c["headline"]["centre_penalty"],
                  avoid=avoid, whole=True, busy_weight=1.0, level=c["headline"]["level"])  # fmt: skip
        if p and (chosen is None or p[3] < chosen[1][3]):
            chosen = (b, p, px_, py_, bw, bh, room, lh, lw, lg, ar)
        if p and p[3] <= c["headline"]["cover_max"]:
            chosen = (b, p, px_, py_, bw, bh, room, lh, lw, lg, ar)
            break
    if not chosen:
        return None
    b, (x0, y0, busy, cover), px_, py_, bw, bh, room, lh, lw, lg, _ = chosen
    x, y = x0 + room / 2, y0 + room / 2
    left = x0 + bw / 2 < W / 2
    cards, lines = [], []
    top = y + lh + lg + py_  # the first line's cap top
    for i, L in enumerate(b["lines"]):
        base = top + b["ascent"] + i * b["step"]
        sw = L["w"] + 2 * px_
        sx = x if left else x + bw - sw
        sy = base - b["cap"] - py_
        sh = b["cap"] + 2 * py_ + max(0, L["bottom"])
        r = rot * (1 if i % 2 == 0 else -0.6)
        cx, cy = sx + sw / 2, sy + sh / 2
        cards.append({"x": round(sx, 1), "y": round(sy, 1), "w": round(sw, 1), "h": round(sh, 1), "r": 0,
                      "fill": rgb_hex(fill), "strip": True, "rot": r})  # fmt: skip
        one = dict(b, lines=[L])
        lines += _lines(one, sx + px_, base - b["ascent"], "start", head, ink, accent, r, cx, cy)
    spec = {"cards": cards, "lines": lines}
    if logo:
        spec["logo"] = _logo_spec(logo, x if left else x + bw - lw, y, lh, lw, st["paper"])
    return {
        "layout": "card",
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": (round(x0), round(y0), round(x0 + bw + room), round(y0 + bh + room)),
        "busy": round(busy, 4),
        "cover": round(cover, 3),
        "spec": spec,
    }


def layout_card(img, words, st, area=None, logo=None):
    """The words on one of the film's own cards -- its fill, corners, outline and shadow (a
    hand-drawn note on a crayon film, tilted a touch), or strips like its labels on a film that
    labels with strips -- where it hides the least, its logo in the card's top band."""
    if st["card"].get("strip"):
        return layout_strips(img, words, st, area, logo)
    c, k = cfg(), cfg()["card"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks:
        return None
    font = _font(head)
    look = st["card"]
    fill = look["fill"]
    ink, accent = _pair(st, head, fill)
    tilt = k["tilt_crayon"] if st["crayon"] else 0.0
    dm, sm = detail_map(img), subject_map(img)
    avoid = text_boxes(img, min_h=cfg()["text"]["headline_min_h_px"])
    chosen = None
    for cap, ar in tries(area):
        if chosen and ar is None and chosen[-1] is not None:
            break  # the side it was given had room: keep to it
        px_, py_ = k["pad_frac"][0] * cap, k["pad_frac"][1] * cap
        lh, lw, lgap = _lockup(logo, cap)
        max_w, max_h = W * k["max_w_frac"] - 2 * px_, H * k["max_h_frac"] - 2 * py_ - lh - lgap
        b = block_at(toks, font, cap, max_w, max_h, k["max_lines"], c["cap"]["line_gap"])
        if not b:
            continue
        cw = max(b["w"], lw) + 2 * px_
        ch = b["h"] + 2 * py_ + lh + lgap
        room = abs(math.sin(math.radians(tilt))) * cw  # a tilted card reaches past its box
        p = place(round(cw + room), round(ch + room), dm, sm, ar, cfg()["headline"]["centre_penalty"],
                  avoid=avoid, whole=True, busy_weight=cfg()["headline"]["busy_weight"])  # fmt: skip
        if p and (chosen is None or p[3] < chosen[1][3]):
            chosen = (b, p, px_, py_, cw, ch, room, lh, lw, lgap, ar)
        if p and p[3] <= cfg()["headline"]["cover_max"]:
            chosen = (b, p, px_, py_, cw, ch, room, lh, lw, lgap, ar)
            break
    if not chosen:
        return None
    b, (x0, y0, busy, cover), px_, py_, cw, ch, room, lh, lw, lgap, _ = chosen
    x, y = x0 + room / 2, y0 + room / 2
    rot = math.radians(tilt)
    cx, cy = x + cw / 2, y + ch / 2
    card = {"x": round(x, 1), "y": round(y, 1), "w": round(cw, 1), "h": round(ch, 1), "r": look["r"],
            "fill": rgb_hex(fill), "stroke": rgb_hex(look["stroke"]) if look["stroke"] else None,
            "strokeW": look["strokeW"], "shadow": look["shadow"], "sketch": look["sketch"], "rot": rot}  # fmt: skip
    extra = {}
    if logo:  # the logo sits in the card's top band, above the words
        extra["logo"] = _logo_spec(logo, x + px_, y + py_, lh, lw, fill)
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


def layout_panel(img, words, st, side=None, logo=None, subject=None):
    """The picture on one side, the words on a panel of the film's own paper on the other, a rule
    of its accent between them and its logo above the words when it is to carry one. compose() has
    already pushed the subject into the picture's side; the picture slides (the film's camera
    moves; nothing is stretched; the panel covers the edge it uncovers) so the subject sits in the
    middle of what stays in view, as far as keeps the film's own words out from under the panel's
    edge. A push alone cannot move a subject past the frame's middle: the owl of a night film sat
    half under the panel until it slid (2026-09-30)."""
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
    if side == "left":
        sides = [True]
    elif side == "right":
        sides = [False]
    else:  # the side that hides less of the subjects first
        sides = [True, False] if sm[:, :third].sum() <= sm[:, -third:].sum() else [False, True]
    fill = st["paper"]
    ink, accent = _pair(st, head, fill)
    safe, badge = safe_rects()
    if subject:
        cx = (subject[0] + subject[2]) / 2
    else:
        cols = dm.mean(axis=0)
        cx = float((cols * np.arange(len(cols))).sum() / max(1e-6, cols.sum())) * 8
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
        for cap in range(c["cap"]["max_px"], c["cap"]["min_px"] - 1, -c["cap"]["step_px"]):
            lh, lw, gap = _lockup(logo, cap)
            if lw > aw:
                lh = lw = gap = 0
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
    if lh:
        spec["logo"] = _logo_spec(logo, area[0], y0, lh, lw, ink)
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


def layout(kind, img, words, st, glow=False, area=None, logo=None, side=None, pics=(),
           subject=None):  # fmt: skip
    if kind == "headline":
        return layout_headline(img, words, st, glow, area, logo, pics)
    if kind == "card":  # with the film's logo when it fits, else the words alone
        return layout_card(img, words, st, area, logo) or (
            layout_card(img, words, st, area) if logo else None
        )
    if kind == "panel":
        return layout_panel(img, words, st, side, logo, subject)
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
        page = {"options": spec, "minWords": cfg()["declutter"]["min_words_px"]}
        f.write("SK.THUMB = %s;\n" % json.dumps(page, ensure_ascii=False))
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
    # a poster is set on the film's bare stage: there are none of its words under it to hide
    res["hides_text"] = 0 if o["layout"] == "poster" else covered_text(o, foot)
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
    # picture; 90% of letter pixels must reach it. Outlined letters are read against their
    # outline: the ring is the part of it outside the letters, not the picture past it
    r = max(2, round(0.045 * o["px"]))
    if o.get("stroke_px"):
        r = max(2, round(0.4 * o["stroke_px"]))
    inner = ndimage.binary_erosion(m, iterations=2)
    near = ndimage.binary_dilation(m, iterations=r)
    ring = near & ~ndimage.binary_dilation(m, iterations=1)
    L = ndimage.gaussian_filter(luminance_map(final), c["contrast_smooth_px"])
    if inner.sum() < 20 or ring.sum() < 20:
        fails.append("the letters are too thin to measure")
    else:
        # each letter (or run of touching ones) against its own ring: a poster's strips set dark
        # words on a light strip and light on a dark one, and one median over every ring read the
        # second as 1.4:1 (2026-10-05)
        lab, n = ndimage.label(near)
        lr = np.full(n + 1, float(np.median(L[ring])))
        got = ndimage.median(L, labels=np.where(ring, lab, 0), index=np.arange(1, n + 1))
        lr[1:] = np.where(np.isfinite(got), got, lr[1:])
        ratio = contrast(L[inner], lr[lab[inner]])
        res["contrast"] = round(float(np.percentile(ratio, 10)), 2)
        if res["contrast"] < c["contrast_min"]:
            fails.append("contrast %.2f:1 against what is around the letters" % res["contrast"])
    return res, fails


# ------------------------------------------------------------------ posters
STAGE = 5000  # a still's time + this: the film's ground and pages, nothing on them (thumb.js)
FIGURE = re.compile(r"\b(full figure|full body|full[- ]length|whole figure|standing)\b", re.I)
FIGURE_TALL = 1.5  # ...and this much taller than wide: "a tablet and a laptop standing" is not one
# A picture of somebody, by what it was painted as: who a poster is built on before any object,
# and the only kind shown from the waist up ("a tall sheaf of wheat, standing" is no figure).
BEING = re.compile(
    r"\b(girl|boy|woman|man|women|men|mum|mom|mother|dad|father|kid|child|children|teen|teenager"
    r"|baby|person|people|lady|guy|grandma|grandpa|grandmother|grandfather|sister|brother|friend"
    r"|student|teacher|doctor|nurse|chef|baker|farmer|hunter|worker|builder|driver|seller|buyer"
    r"|customer|scientist|engineer|artist|king|queen|robot|mascot|character|portrait|cat|dog|fox"
    r"|bear|bird|rabbit|owl|lion|tiger|monkey|horse|donkey|dragon|monster|alien)\b",
    re.I,
)
MARK = re.compile(r"(^|[_-])(mark|icon|favicon|wordmark|brand|badge)($|[_-])", re.I)
TEMPLATES = ("side", "band")


def _pick(seed, n, what, choices):
    """One of `choices`: the same one every time for this film, option and question."""
    h = hashlib.sha256(("%s|%s|%s" % (seed, n, what)).encode()).digest()
    return choices[int.from_bytes(h[:4], "big") % len(choices)]


def _lab(rgb):
    """CIE L*a*b* of an sRGB colour: distances in it are differences a viewer sees."""
    r, g, b = (float(_lin(v)) for v in rgb[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _apart(a, b):
    return math.dist(_lab(a), _lab(b))


def _lettered(rgba):
    """Is this picture full of words (a flyer, a screenshot, an infographic somebody gave the
    film)? A thumbnail carries one message: such a picture is the last thing a poster is built
    on, and never tucked in as its second piece. Read with OCR at 640 px (~0.3 s), so only asked
    of pictures nobody described (a painted one was told to carry no words)."""
    k = cfg()["poster"]
    im = Image.new("RGB", rgba.size, (255, 255, 255))
    im.paste(rgba, mask=rgba.getchannel("A"))
    im.thumbnail((640, 640))
    try:
        res, _ = ocr()(np.asarray(im))
    except Exception:  # noqa: BLE001 -- no OCR here: nothing is known, so nothing is held back
        return False
    lines = [
        x for x in res or [] if (float(x[2]) if len(x) > 2 else 1.0) >= cfg()["text"]["min_score"]
    ]
    return len(lines) >= k["lettered_lines"]


def film_pieces(film_dir):
    """{name: {file, w, h, cut, being, figure, mark, lettered, about, colours}} -- what a poster
    can be composed from: the film's pictures, each of which it can set as large as it likes.

    cut      the picture has a transparent ground (a clay character, a prop cut out of paper): it
             is set as it is, with the shadow paper casts. Without one it is a print: set with a
             border of the film's paper, the way a photograph is pinned to a page
    being    a picture of somebody, from what it was painted as (paint.json: BEING)
    figure   ...standing whole (FIGURE), and tall: a poster shows a figure from the waist up, so
             its face is the size a thumbnail needs
    mark     a brand's mark by its name (web_mark, an icon): the last thing to build a poster on
    lettered a picture full of words (_lettered): the last thing too, and never the second piece
    colours  its main ones, [(rgb, share)]

    Never the film's logo, which a poster carries as its badge."""
    key = ("pieces", film_dir, film_key(film_dir))
    if key in _CACHE:
        return _CACHE[key]
    with open(os.path.join(film_dir, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    pj = m.get("paint") or {}
    if isinstance(pj, str):
        try:
            with open(
                pj if os.path.isabs(pj) else os.path.join(film_dir, pj), encoding="utf-8"
            ) as f:
                pj = json.load(f)
        except (OSError, ValueError):
            pj = {}
    said = {
        x["name"]: str(x.get("prompt") or "")
        for x in pj.get("images") or []
        if isinstance(x, dict) and x.get("name")
    }
    out = {}
    for name, path in film_images(film_dir, m).items():
        if "logo" in name.lower() or not os.path.exists(path):
            continue
        try:
            with Image.open(path) as im:
                rgba = im.convert("RGBA")
        except OSError:
            continue
        w, h = rgba.size
        if min(w, h) < cfg()["poster"]["piece_min_px"]:
            continue
        k = 64 / max(w, h)
        a = np.asarray(rgba.resize((max(1, round(w * k)), max(1, round(h * k)))))
        al = a[..., 3]
        cut = sum(1 for v in (al[0, 0], al[0, -1], al[-1, 0], al[-1, -1]) if v < 16) >= 3
        px = np.ascontiguousarray(a[al > 200][:, :3])
        if len(px) < 30:
            continue
        q = Image.fromarray(px.reshape(-1, 1, 3), "RGB").quantize(
            5, method=Image.Quantize.MEDIANCUT
        )
        pal = q.getpalette()
        cols = sorted(
            ((n / len(px), tuple(pal[3 * i : 3 * i + 3])) for n, i in q.getcolors()), reverse=True
        )
        being = bool(BEING.search(said.get(name, "")))
        out[name] = {"file": path, "w": w, "h": h, "cut": cut, "about": said.get(name, ""),
                     "being": being, "lettered": name not in said and _lettered(rgba),
                     "figure": cut and being and bool(FIGURE.search(said[name])) and h >= FIGURE_TALL * w,
                     "mark": bool(MARK.search(name)),
                     "colours": [(c, round(share, 3)) for share, c in cols]}  # fmt: skip
    _CACHE[key] = out
    return out


def stage_at(into, t):
    """[{box, col}] of the pages the film had down at `t` (the 5000 pass), largest first."""
    try:
        with open(os.path.join(into, "boxes.json"), encoding="utf-8") as f:
            got = json.load(f).get("P%.2f" % t) or []
    except (OSError, ValueError):
        got = []
    return sorted(got, key=lambda b: -_area(b["box"]))


def stage_camera(pages):
    """The push that makes the film's page fill the frame (a collage film lays its pages on a
    mat, a band of it showing all round: at 168 px that band is a frame round a smaller picture),
    as thumb.js's camera -- or None when there is no page, or it fills the frame already."""
    W, H = size()
    if not pages:
        return None
    x0, y0, x1, y1 = pages[0]["box"]
    k = cfg()["poster"]
    z = max(W / max(1, x1 - x0), H / max(1, y1 - y0))
    if z <= 1.01:
        return None
    # a little past the fit: a page's torn edge and its white rim stay out of the frame
    z = min(k["stage_zoom_max"], z * k["stage_overscan"])
    vw, vh = W / z, H / z
    vx0 = min(W - vw, max(0.0, (x0 + x1) / 2 - vw / 2))
    vy0 = min(H - vh, max(0.0, (y0 + y1) / 2 - vh / 2))
    return {
        "zoom": round(z, 4),
        "cx": round(vx0 * z / (z - 1), 2),
        "cy": round(vy0 * z / (z - 1), 2),
    }


def staged(img, camera):
    """The stage still as the camera's push shows it: what the poster's words are set on."""
    if not camera:
        return img
    W, H = size()
    z = camera["zoom"]
    vx0, vy0 = camera["cx"] * (z - 1) / z, camera["cy"] * (z - 1) / z
    box = (round(vx0), round(vy0), round(vx0 + W / z), round(vy0 + H / z))
    return img.crop(box).resize((W, H), Image.LANCZOS)


def cast_at(pcs, boxes):
    """The film's pieces in a frame, largest on screen first -- not a picture that is the frame's
    whole scene (a painted backdrop), which is no piece of it."""
    W, H = size()
    seen = {}
    for b in boxes or []:
        n = str(b.get("name", ""))
        if n in pcs:
            a = _area(_clip(tuple(float(v) for v in b["box"]), (0, 0, W, H)))
            seen[n] = max(seen.get(n, 0), a)
    big = cfg()["compose"]["backdrop_frac"] * W * H
    return [n for n, a in sorted(seen.items(), key=lambda x: -x[1]) if 0 < a < big]


def _rank(pcs, names, shown=None, used=()):
    """Pieces in the order a poster would build on them: one no other option has taken, somebody
    (a face) before an object, a cut-out before a print, a brand's mark last, then as given --
    or, with `shown` (the probe's {name: {n, w}}), the ones the film draws most often."""
    order = {n: i for i, n in enumerate(names)}

    def key(n):
        p = pcs[n]
        often = -(shown.get(n) or {}).get("n", 0) if shown is not None else order[n]
        return (p["mark"] or p["lettered"], n in used, not p["being"], not p["cut"], often)

    return sorted(names, key=key)


def poster_heroes(pcs, casts, concepts, shown=None):
    """[(hero, extras)], one per concept, for a film's posters: the writer's own choice when it
    named pieces the film has; else, of the pieces in that moment's frame (`casts`), somebody
    before an object, with the largest thing that is not a figure beside it; else -- a moment
    with no piece on screen -- a piece no other option has taken, the ones the film shows most
    first, never one it lays across the whole frame (a painted scene is the frame, not a piece
    of it). Never, unasked, a brand's mark or a picture full of words: a film with nothing else
    to show gets frames. (None, []) for a concept no poster can be made for."""
    W, _ = size()
    wide = cfg()["poster"]["scene_w"] * W
    shown = shown or {}
    out = []
    named = [cpt.get("hero") for cpt in concepts if cpt.get("hero") in pcs]

    def plain(n):
        return not pcs[n]["mark"] and not pcs[n]["lettered"]

    for cpt, cast in zip(concepts, casts, strict=True):
        hero = cpt.get("hero") if cpt.get("hero") in pcs else None
        extras = [n for n in cpt.get("with") or [] if n in pcs and n != hero]
        cast = [n for n in cast if plain(n)]
        if not hero and cast:
            # of the frame's pieces, one the options before this have not built on
            hero = _rank(pcs, cast, None, named + [h for h, _ in out if h])[0]
            if not extras:
                extras = [n for n in cast if n != hero and not pcs[n]["figure"]]
        out.append([hero, extras[:1]])
    used = [h for h, _ in out if h]
    free = [n for n in pcs
            if plain(n) and (pcs[n]["cut"] or (shown.get(n) or {}).get("w", 0) < wide)]  # fmt: skip
    for row in out:
        if not row[0] and free:
            row[0] = _rank(pcs, free, shown, used)[0]
            used.append(row[0])
    return [(h, e) for h, e in out]


def backing_colour(st, page, piece, seed, n):
    """The colour of the paper behind a poster's hero: of the colours the film itself uses (its
    labels', its accent, its paper), one far from both the page and the hero's own colours -- a
    lemon hoodie on a lemon burst is one yellow shape."""
    cands = list(st.get("strips") or []) + [st["accent_fill"], st["paper"]]
    if st.get("outline"):
        cands += [st["outline"]["fill"], st["outline"]["accent"]]
    uniq = []
    for c in cands:
        if not any(_near(c, u, 30) for u in uniq):
            uniq.append(tuple(c))
    main = [c for c, share in piece["colours"] if share >= 0.12] or [piece["colours"][0][0]]

    def score(c):
        return min(_apart(c, page), min(_apart(c, m) for m in main))

    ranked = sorted(uniq, key=lambda c: -score(c))
    good = [c for c in ranked if score(c) >= 0.8 * score(ranked[0])]
    return _pick(seed, n, "backing", good)


def poster_variant(seed, n):
    """What changes from one poster to the next -- across one film's four options, and from film
    to film on a channel: the template, which side the hero stands, how close it is, how the words
    lean, the paper behind the hero. The same film and option always get the same answer."""
    k = cfg()["poster"]
    flip = {"left": "right", "right": "left"}
    first = _pick(seed, 0, "side", ["left", "right"])
    lead = _pick(seed, 0, "template", [0, 1])
    return {
        "template": TEMPLATES[(n + lead) % len(TEMPLATES)],
        "side": first if (n - 1) // 2 % 2 == 0 else flip[first],
        "tilt": _pick(seed, n, "tilt", k["tilts"]),
        "close": _pick(seed, n, "close", k["figure_hs"]),
        "backing": _pick(seed, n, "backing-kind", k["backings"]),
        "spin": _pick(seed, n, "spin", [0.0, 0.07, 0.13]),
    }


def _fit_words(toks, font, stroke, zw, zh, rot, cap_max, max_lines, strips=False):
    """(block, pad, strip padding) for the words at the largest cap height that fits zw x zh once
    turned by `rot` -- each line on a strip of paper when `strips` -- or None."""
    c, k = cfg(), cfg()["poster"]
    cs, sn = abs(math.cos(rot)), abs(math.sin(rot))
    for cap in range(cap_max, c["cap"]["min_px"] - 1, -c["cap"]["step_px"]):
        px = cap / cap_ratio(font["file"])
        if strips:
            sx, sy = c["strip"]["pad"][0] * cap, c["strip"]["pad"][1] * cap
            gap = (2 * sy + c["strip"]["gap_frac"] * cap) / cap
            b = block_at(toks, font, cap, zw - 2 * sx, zh - 2 * sy, max_lines, gap)
            if (
                b
                and (b["w"] + 2 * sx) * cs + (b["h"] + 2 * sy) * sn <= zw
                and (b["w"] + 2 * sx) * sn + (b["h"] + 2 * sy) * cs <= zh
            ):
                return b, 0.0, (sx, sy)
            continue
        pad = (stroke["w"] * px * 0.5 if stroke else 0) + 0.04 * cap
        b = block_at(toks, font, cap, zw, zh, max_lines, k["line_gap"], pad)
        if b and b["w"] * cs + b["h"] * sn <= zw and b["w"] * sn + b["h"] * cs <= zh:
            return b, pad, None
    return None


def _turned(w, h, rot):
    """Half the width and height of a w x h picture's box once turned by `rot`."""
    cs, sn = abs(math.cos(rot)), abs(math.sin(rot))
    return (w * cs + h * sn) / 2, (w * sn + h * cs) / 2


def _backing(st, page, P, v, seed, n, x, y, r):
    k = cfg()["poster"]
    fill = backing_colour(st, page, P, seed, n)
    rim = st["outline"]["fill"] if st.get("outline") else st["paper"]
    if _near(rim, fill, 40) or _near(rim, page, 40):
        rim = None
    b = {"k": "burst", "x": round(x), "y": round(y), "r": round(r), "col": rgb_hex(fill),
         "rim": rgb_hex(rim) if rim else None, "rot": v["spin"], "seed": 60 + n}  # fmt: skip
    b.update(k["shapes"][v["backing"]])
    return b


def _piece(name, P, x, y, w, rot, st):
    """A piece for thumb.js: a cut-out as it is, a print with a border of the film's paper."""
    d = {"k": "cut" if P["cut"] else "print", "name": name, "x": round(x), "y": round(y),
         "w": round(w), "rot": round(rot, 4)}  # fmt: skip
    if not P["cut"]:
        k = cfg()["poster"]
        light = max((st["paper"], st["text"], (255, 255, 255)), key=luminance)
        d.update(border=round(k["print_border"] * w), col=rgb_hex(light), zoom=k["print_zoom"])
    return d


def strip_pair(st, head, page):
    """(fill, ink, accent) for words on strips of paper: the film's own label when it labels with
    strips, else of its colours the one furthest from the page that one of its inks reads on."""
    need = cfg()["contrast_min"] + cfg()["ink_margin"]
    inks = [st["paper"], st["text"], st["ink"]]
    if st.get("outline"):
        inks.append(st["outline"]["fill"])
    look = st["card"]
    fills = ([look["fill"]] if look.get("strip") else []) + list(st.get("strips") or [])
    fills += [st["ink"], st["text"], st["accent_fill"], st["paper"]]
    ok = [f for f in fills if max(_reads(i, f) for i in inks) >= need and _apart(f, page) >= 25]
    # a strip's paper grain takes more off the contrast than a page's does (navy on an orange
    # strip: 5.4:1 as colours, 4.49:1 drawn): a pair with room to spare before one without
    roomy = [f for f in ok if max(_reads(i, f) for i in inks) >= need + cfg()["strip"]["margin"]]
    ok = roomy or ok
    fill = ok[0] if look.get("strip") and ok and ok[0] == look["fill"] else (
        max(ok, key=lambda f: _apart(f, page)) if ok else max(fills, key=lambda f: _apart(f, page)))  # fmt: skip
    ink = max(inks, key=lambda i: _reads(i, fill))
    if _reads(ink, fill) < need:
        ink = fit_contrast(ink, fill, need)
    accent = _accent(st, ink, fill)
    o = st.get("outline")
    if o and not _near(o["accent"], ink) and _reads(o["accent"], fill) >= need:
        accent = o["accent"]
    # the starred word's line on a strip of another of the film's colours, when it has one that
    # stands off both the first strip and the page: the stack then says which line matters
    hots = list(st.get("strips") or []) + [st["accent_fill"]] + ([o["accent"]] if o else [])
    hots = [h for h in hots if not _near(h, fill, 70) and _apart(h, page) >= 25 and _chroma(h) >= 0.35
            and max(_reads(i, h) for i in inks) >= need + cfg()["strip"]["margin"]]  # fmt: skip
    hot = None
    if hots:
        hf = max(hots, key=lambda h: min(_apart(h, fill), _apart(h, page)))
        hot = (hf, max(inks, key=lambda i: _reads(i, hf)))
    return fill, ink, accent, hot


def layout_poster(words, st, pcs, hero, extras, pages, v, seed, n, logo=None, stage=None,
                  strips=False):  # fmt: skip
    """A poster, composed from the film's own pieces rather than cut from one of its frames: its
    page filling the frame, one of its pictures large on a burst of its paper -- a figure from the
    waist up, an object whole and turned, a print with a paper border -- another piece tucked in
    behind it, and the words as large as the room allows, in the film's title type and outline (or,
    with `strips`, each line on a strip of its paper, the way it labels), leaning a little.

    Two templates (v["template"]), both read off channels that draw rather than film:
      side   the words stacked on one side, the hero on the other
      band   the words in a line or two across the top, the hero under them, off the bottom edge
    `stage` is the picture the words are set on (the film's bare page, as the push shows it).
    None when the words cannot be set at a legible size."""
    k = cfg()["poster"]
    W, H = size()
    toks = tokens(words)
    head = pick_head(st, words)
    if not head or not toks or hero not in pcs:
        return None
    font = _font(head)
    P = pcs[hero]
    page = colour(pages[0]["col"], st["paper"]) if pages else st["paper"]
    if stage is not None:
        page = _mean_rgb(stage, (W * 0.2, H * 0.2, W * 0.8, H * 0.8))
    out = st.get("outline") if head.get("film") and not strips else None
    stroke = out["stroke"] if out else None
    safe, badge = safe_rects()
    mx, gap, rot = k["margin"] * W, k["gap"] * W, v["tilt"]
    lh = lw = 0
    lbox = None
    if logo:
        lh = round(k["logo_h"] * H)
        lw = lh if logo.get("round") else round(min(lh * logo["aspect"], 0.3 * W))
        lh = lh if logo.get("round") else round(lw / logo["aspect"])
        m = k["logo_margin"] * H
        lx = m if k["logo_corner"].endswith("left") else W - m - lw
        ly = m if k["logo_corner"].startswith("top") else H - m - lh
        lbox = (lx, ly, lx + lw, ly + lh)
    scene = []
    if v["template"] == "band":
        kb = k["band"]
        rot *= kb["tilt"]  # a line across the whole frame climbs a long way at the same lean
        fit = _fit_words(toks, font, stroke, safe[2] - safe[0], kb["h"] * H - safe[1], rot,
                         kb["cap_max"], kb["max_lines"], strips)  # fmt: skip
        if not fit:
            return None
        b, pad, sp = fit
        bw, bh = b["w"] + (2 * sp[0] if sp else 0), b["h"] + (2 * sp[1] if sp else 0)
        rw, rh = (2 * e for e in _turned(bw, bh, rot))
        cx, cy = W / 2, safe[1] + rh / 2
        floor = cy + rh / 2 + 0.01 * H  # where the picture starts, under the words
        left = (lbox is not None and lbox[0] < W / 2) or (lbox is None and v["side"] == "left")
        sign = 1 if left else -1  # the hero stands off the logo's side; its prop on that side
        hx = W * (kb["hero_cx"] if left else 1 - kb["hero_cx"])
        if P["figure"]:
            fh = min(kb["bust_h"] * H, k["max_up"] * P["h"])
            fw = fh * P["w"] / P["h"]
            hy, hrot = floor + fh / 2, 0.0
            bx, by, br = hx, floor + 0.2 * fh, k["burst_r"] * H
        else:
            hrot = -sign * k["object_rot"]
            room = (H - floor) / (1 - kb["cut"])
            s = min(kb["object_w"] * W / P["w"], room / P["h"], k["max_up"])
            fw, fh = P["w"] * s, P["h"] * s
            ex, ey = _turned(fw, fh, hrot)
            hy = floor + ey
            bx, by, br = hx, hy, 1.05 * max(ex, ey)
        # the burst stays under the words' line: words without an outline do not read across
        # its edge (white on an orange burst: 3.3:1), and with one a burst behind them is clutter.
        # Words on strips of paper read over anything. A burst cut down to a crown is left out.
        reach = br if strips else min(br, by - floor + (k["burst_over"] * H if stroke else 0))
        if v["backing"] and reach >= k["burst_keep"] * br:
            scene.append(_backing(st, page, P, v, seed, n, bx, by, reach))
        for name in extras:
            Q = pcs[name]
            if Q["figure"] and P["figure"]:  # somebody beside somebody: a second bust, behind
                qh = fh * k["mate"]
                qw = qh * Q["w"] / Q["h"]
                qx = hx - sign * fw * kb["mate_out"]
                scene.append(_piece(name, Q, qx, floor + k["mate_drop"] * H + qh / 2, qw, 0.0, st))
                continue
            s = min(kb["prop_h"] * H / Q["h"], kb["prop_w"] * W / Q["w"], k["max_up"])
            qw = Q["w"] * s
            qx = hx - sign * (fw / 2 + qw * (0.5 - kb["prop_in"]))
            scene.append(_piece(name, Q, qx, kb["prop_cy"] * H, qw, -sign * k["prop_rot"], st))
        scene.append(_piece(hero, P, hx, hy, fw, hrot, st))
        side = "top"
    else:
        left = v["side"] == "left"
        sign = 1 if left else -1  # toward the middle of the frame, from the hero
        if P["figure"]:
            fh = min(v["close"] * H, k["max_up"] * P["h"])
            fw = fh * P["w"] / P["h"]
            if fw > k["hero_w"] * W:
                fw = k["hero_w"] * W
                fh = fw * P["h"] / P["w"]
            top = k["figure_top"] * H
            hx, hy, hrot = (mx + fw / 2 if left else W - mx - fw / 2), top + fh / 2, 0.0
            hbox = (hx - fw / 2, top, hx + fw / 2, H)
            bx, by, br = hx, top + 0.3 * fh, k["burst_r"] * H
        else:
            hrot = -sign * k["object_rot"]
            ex, ey = _turned(P["w"], P["h"], hrot)
            s = min(k["object_w"] * W / (2 * ex), k["object_h"] * H / (2 * ey), k["max_up"])
            fw, fh = P["w"] * s, P["h"] * s
            ex, ey = ex * s, ey * s
            om = max(mx, k["object_margin"] * W)
            hx, hy = (om + ex if left else W - om - ex), k["object_cy"] * H
            hbox = (hx - ex, hy - ey, hx + ex, hy + ey)
            bx, by, br = hx, hy, 1.08 * max(ex, ey)
        inner = hbox[2] if left else hbox[0]
        for name in extras:
            Q = pcs[name]
            if Q["figure"] and P["figure"]:  # somebody beside somebody: a second figure, behind
                qh = fh * k["mate"]
                qw = qh * Q["w"] / Q["h"]
                qx = inner + sign * qw * (k["mate_out"] - 0.5)
                scene.append(_piece(name, Q, qx, top + k["mate_drop"] * H + qh / 2, qw, 0.0, st))
                inner = qx + sign * qw / 2
                continue
            qrot = sign * k["prop_rot"]
            s = min(k["prop_h"] * H / Q["h"], k["prop_w"] * W / Q["w"], k["max_up"])
            qw = Q["w"] * s
            qex, _ = _turned(qw, Q["h"] * s, qrot)
            qx = inner + sign * (2 * qex * k["prop_out"] - qex)
            scene.append(_piece(name, Q, qx, k["prop_cy"] * H, qw, qrot, st))
            inner = qx + sign * qex
        scene.append(_piece(hero, P, hx, hy, fw, hrot, st))
        zx0, zx1 = (inner + gap, safe[2]) if left else (safe[0], inner - gap)
        zy0, zy1 = safe[1], safe[3]
        # behind everything, and short of the words' side (as in the band)
        reach = (zx0 - bx) if left else (bx - zx1)
        reach = br if strips else min(br, reach + (k["burst_over"] * H if stroke else 0))
        if v["backing"] and reach >= k["burst_keep"] * br:
            scene.insert(0, _backing(st, page, P, v, seed, n, bx, by, reach))
        if zx1 > badge[0]:
            zy1 = min(zy1, badge[1])
        if lbox and lbox[2] > zx0 and lbox[0] < zx1:  # the logo's corner is in the words' side
            if lbox[1] > H / 2:
                zy1 = min(zy1, lbox[1] - 0.02 * H)
            else:
                zy0 = max(zy0, lbox[3] + 0.02 * H)
        fit = _fit_words(toks, font, stroke, zx1 - zx0, zy1 - zy0, rot, k["cap_max"],
                         k["max_lines"], strips)  # fmt: skip
        if not fit:
            return None
        b, pad, sp = fit
        bw, bh = b["w"] + (2 * sp[0] if sp else 0), b["h"] + (2 * sp[1] if sp else 0)
        rw, rh = (2 * e for e in _turned(bw, bh, rot))
        cx, cy = (zx0 + zx1) / 2, zy0 + rh / 2 + (zy1 - zy0 - rh) * k["words_cy"]
        side = "right" if left else "left"
    box = tuple(round(e) for e in (cx - rw / 2, cy - rh / 2, cx + rw / 2, cy + rh / 2))
    spec = {"stage": True, "camera": stage_camera(pages), "scene": scene}
    if sp:  # a line to a strip, the strips stacked about the middle and leaning as one
        fill, ink, accent, hot = strip_pair(st, head, page)
        cards, lines = [], []
        top = cy - bh / 2 + sp[1]
        for i, L in enumerate(b["lines"]):
            base = top + b["ascent"] + i * b["step"]
            sw, sh = L["w"] + 2 * sp[0], b["cap"] + 2 * sp[1] + max(0, L["bottom"])
            sx, sy = cx - sw / 2, base - b["cap"] - sp[1]
            starred = hot and len(b["lines"]) > 1 and any(a for segs in L["words"] for _, a in segs)
            f_, i_, a_ = (hot[0], hot[1], hot[1]) if starred else (fill, ink, accent)
            # every strip turns about the block's middle, so the stack leans as one piece
            cards.append({"x": round(sx, 1), "y": round(sy, 1), "w": round(sw, 1), "h": round(sh, 1),
                          "r": 0, "fill": rgb_hex(f_), "strip": True, "rot": rot,
                          "cx": round(cx, 1), "cy": round(cy, 1)})  # fmt: skip
            one = dict(b, lines=[L])
            lines += _lines(one, cx, base - b["ascent"], "middle", head, i_, a_, rot, cx, cy)
        spec.update(cards=cards, lines=lines)
    else:
        if out:
            ink, accent = out["fill"], out["accent"]
        else:
            under = _mean_rgb(stage, box) if stage is not None else page
            ink = _ink(st, head, under)
            accent = _accent(st, ink, under)
        spec["lines"] = _lines(b, cx, cy - b["h"] / 2 + pad, "middle", head, ink, accent, rot,
                               cx, cy, stroke)  # fmt: skip
    if lbox:
        rim = st["outline"]["fill"] if st.get("outline") else st["paper"]
        spec["logo"] = _logo_spec(logo, lbox[0], lbox[1], lh, lw, rim)
    return {
        "layout": "poster",
        "template": v["template"],
        "words": words,
        "head": head,
        "cap": b["cap"],
        "px": b["px"],
        "box": box,
        "stroke_px": round(stroke["w"] * b["px"], 1) if stroke else 0,
        "strips": bool(sp),
        "side": side,
        "spec": spec,
    }


# ------------------------------------------------------------------ the whole thing
DROP = ("spec", "box", "head", "cap", "px", "busy", "cover", "glow", "shift", "stroke_px",
        "strips", "template", "alt")  # fmt: skip
FALLBACK = {
    "poster": ["poster+alt", "headline", "headline+glow", "card", "still"],
    "headline": ["headline+glow", "card", "still"],
    "card": ["still"],
    "panel": ["card", "still"],
}


def _lay(o, kind, st):
    """One layout for the option: on the picture compose() made (the film's own words left out,
    the camera pushed in on its subject), in the side it gave the words -- or, for the still, the
    frame as the film drew it."""
    if kind == "still" or not o["words"]:
        return layout_still(o["film"])
    if kind in ("poster", "poster+alt"):
        p = o["poster"]
        lay = None
        # the other way of setting the words (strips for type, type for strips) is the first
        # thing a poster falls back to: words that do not read on a page read on a strip of paper
        alt = kind == "poster+alt"
        # Its own template with its second piece, unless the words come out much larger another
        # way: in the other template (a long word wants the whole width, a short line a side), or
        # without the second piece, whose room they then take. A thumbnail is read at 168 px.
        k = cfg()["poster"]
        best = None
        for tpl in [p["variant"]["template"]] + [
            t for t in TEMPLATES if t != p["variant"]["template"]
        ]:
            for extras in [p["extras"], []] if p["extras"] else [[]]:
                got = layout_poster(o["words"], st, p["pieces"], p["hero"], extras, p["pages"],
                                    dict(p["variant"], template=tpl), p["seed"], o["n"],
                                    logo=p["logo"], stage=p["stage"],
                                    strips=p["variant"]["strips"] != alt)  # fmt: skip
                if got is None:
                    continue
                score = got["cap"] / (
                    (1 if tpl == p["variant"]["template"] else k["switch"])
                    * (1 if len(extras) == len(p["extras"]) else k["drop_prop"])
                )
                if best is None or score > best[0] + 1e-9:
                    best = (score, got)
        if best:
            lay = best[1]
            lay["alt"] = alt
            o["img"] = p["stage"]
        return lay
    comp = o["comp"]
    lay = None
    if kind == "headline":
        for c in [comp, *comp.get("alts", [])]:
            lay = layout_headline(c["img"], o["words"], st, area=c["zone"], logo=o["logo"],
                                  pics=c["pics"], strict=True)  # fmt: skip
            if lay is not None:
                if c is not comp:
                    o["notes"].append("words %s instead: a clean place" % c["side"])
                comp = c
                break
    o["img"] = comp["img"]  # what the checks read: the picture this layout was set on
    if lay is None and kind == "headline+glow":
        lay = layout_headline(o["img"], o["words"], st, glow=True, area=comp["zone"], logo=o["logo"],
                              pics=comp["pics"])  # fmt: skip
    elif lay is None:
        lay = layout(kind, o["img"], o["words"], st, area=comp["zone"], logo=o["logo"],
                     side=comp["side"], pics=comp["pics"], subject=comp["subject"])  # fmt: skip
    if lay is not None:
        lay["side"] = comp["side"]
        spec = lay["spec"]
        spec["declutter"] = True
        if comp.get("hide"):
            spec["hide"] = comp["hide"]
        cam = dict(comp["camera"] or {})
        cam.update(spec.get("camera") or {})  # a panel's slide rides on the push
        spec["camera"] = cam or None
    return lay


def poster_note(o):
    """What a poster was composed of, for the record: its template, its pieces, how its words are set."""
    names = [L["name"] for L in o["spec"]["scene"] if L["k"] in ("cut", "print")]
    return "poster (%s%s): %s" % (
        o["template"], ", strips" if o.get("strips") else "", " + ".join(reversed(names)))  # fmt: skip


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


def wants_logo(n, logo):
    """Does option n carry the film's logo? `logo`: "all", "none", or the option numbers that do
    (config logo.options: some with it and some without, so the person picking sees both)."""
    if logo in (None, "config"):
        logo = cfg()["logo"]["options"]
    if logo == "all":
        return True
    if logo == "none":
        return False
    return n in logo


def make_options(film_dir, concepts, out_dir, env=None, log=print, logo=None):
    """Four finished options for a film, in its own look: [{n, file, layout, requested, at, t,
    words, font, logo, checks, notes, final}], every one of them passing. Stills are cached per
    film; the JPEGs go to out_dir. `logo` says which carry the film's logo (wants_logo)."""
    t0 = time.time()
    length = film_length(film_dir)
    work = os.path.join(film_dir, "temp", "thumbs", "work")
    shutil.rmtree(work, ignore_errors=True)
    # 1. every frame the settle step looks at, and each candidate without the film's own words,
    # in one browser run (the probe rides along, and notes where the film's pictures landed)
    pcs = film_pieces(film_dir)  # a film with cut-outs gets posters composed from them
    seed = film_key(film_dir)
    want = set()
    for o in concepts:
        cands, every = settle_times(o["at"], length)
        want |= set(every) | {DECLUTTER + t for t in cands}
        if pcs:
            want |= {STAGE + t for t in cands}
    stills = render_stills(film_dir, want, env=env)
    st = film_style(film_dir, env)
    shown = probe(film_dir, env).get("img") or {}  # how often, and how large, it draws each
    strips_n = _pick(seed, 0, "strips", cfg()["poster"]["strips_options"])
    t_stills = time.time() - t0
    # 2. the frame, the picture made of it, then the words on it, in the film's look
    settled = [settle(cpt["at"], stills, length)[0] for cpt in concepts]
    casts = [cast_at(pcs, boxes_at(stills_dir(film_dir), t)) for t in settled]
    heroes = poster_heroes(pcs, casts, concepts, shown)
    opts = []
    for i, cpt in enumerate(concepts, 1):
        t = settled[i - 1]
        kind = RENAMED.get(cpt["layout"], cpt["layout"])
        o = {"n": i, "at": cpt["at"], "t": t, "requested": kind, "words": cpt["words"],
             "place": cpt.get("place"), "notes": [], "tried": []}  # fmt: skip
        if abs(t - cpt["at"]) > 0.01:
            o["notes"].append("settled at %.2f s (asked %.2f s)" % (t, cpt["at"]))
        o["film"] = load_still(stills[t])
        sides = ("left", "right") if kind == "panel" else SIDES
        frac = cfg()["panel"]["w_fracs"][0] if kind == "panel" else None
        comp = compose(load_still(stills[round(DECLUTTER + t, 2)]),
                       boxes_at(stills_dir(film_dir), t), o["place"], sides, frac)  # fmt: skip
        o["comp"], o["img"] = comp, comp["img"]
        # the film's own logo already in the picture: it is not added a second time
        o["logo"] = st["logo"] if st["logo"] and wants_logo(i, logo) and not comp["logo"] else None
        hero, extras = heroes[i - 1]
        if hero and kind != "still" and o["words"]:
            # composed from the film's own pieces, on its own page: not a frame of it
            pages = stage_at(stills_dir(film_dir), t)
            v = poster_variant(seed, i)
            v["strips"] = bool(st["card"].get("strip")) and i == strips_n
            o["poster"] = {
                "pieces": pcs, "hero": hero, "extras": extras, "seed": seed, "pages": pages,
                "variant": v,
                "stage": staged(load_still(stills[round(STAGE + t, 2)]), stage_camera(pages)),
                "logo": st["logo"] if st["logo"] and wants_logo(i, logo) else None,
            }  # fmt: skip
            kind = o["requested"] = "poster"
        else:
            o["notes"].append(
                "words %s, subject by %s, push %.2fx" % (comp["side"], comp["how"], comp["zoom"])
            )
        o.update(first_layout(o, kind, st))
        if o["layout"] == "poster":
            o["notes"].append(poster_note(o))
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
            tag = o["layout"] + ("+glow" if o.get("glow") else "+alt" if o.get("alt") else "")
            o["notes"].append("%s failed: %s" % (tag, "; ".join(fails)))
            o["tried"].append(tag)
            lay = first_layout(o, _next(o), st)
            for k in DROP:
                o.pop(k, None)
            o.update(lay)
            if o["layout"] == "poster":
                o["notes"].append(poster_note(o))
            if o["layout"] == "still":
                o["words"] = ""
    for o in opts:
        if "final" not in o:  # out of rounds: the frame as the film drew it, which fails nothing
            for k in DROP:
                o.pop(k, None)
            o.update({"layout": "still", "words": "", "spec": {}})
            o["final"] = o["film"]
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
            "place": o.get("place"), "logo": bool((o.get("spec") or {}).get("logo")),
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
