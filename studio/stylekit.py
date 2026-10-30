#!/usr/bin/env python
"""A project's style: one to three pictures of one look, read into a style card that every
episode's pictures, colours and lettering follow (the Style tab on kitcut.ai; the plan and what
six style pictures measured: specs/features/style-tab.md in the site's repo).

The Brand tab is who is speaking (a brand book read into rules); the Style tab is how the
pictures look. Where both say something, the brand wins: its faces, colours and logo stay on
titles, captions and the end card, and the style is used for what the brand leaves open.

    <project library>/style/                     (library.dir_of: never in git, never public)
        files/<sid>.json  files/<sid>.bin        what the person sent, in parts (as brandkit)
        pictures/<sid>.jpg  pictures/<sid>.t.jpg each picture as a JPEG, long side 2048 (AVIF,
                                                 PNG, WebP, a GIF's first frame: on arrival)
        card.json                                Claude's reading (read), then the person's
                                                 corrections (edit)
        fonts/l<i>.jpg  fonts/l<i>-<k>.png       each line of lettering cut out of its picture,
                                                 and its words set in each free face that comes
                                                 close (Google Fonts, fetched into standin/)
        proof/<route>.jpg  proof.json            one subject painted each way (ROUTES): the
                                                 person picks the one that looks like the picture
        assets/                                  what an episode gets: style.jpg (the main
                                                 picture), fonts/, style.js (SK.STYLE), used.json
        state.json                               {state, step, error, at, reads, proofs, cost_usd}

Reading: the pictures' colours are measured here (k-means), then ONE Claude call with no tools
sees the pictures and writes the card -- a style line that names no thing (a noun in it gets
painted: a bust beside a bridge, bottles in a bakery), the things it did see, how the pictures
are laid out, the look that suits them, each line of lettering with free faces that come close,
and a subject from the project's brief for the proof. Then the faces are fetched and set, and
the proof is painted. Gemini is the team's alone (`team`, from the site's X-Team) and the card
says so: it costs about seven times Muse a picture.

An episode of the project gets the assets (seed: the picture in style/, the faces in its
manifest, style.js before film.js) and its record's paint_route, from which film.paint_pins
sets the painter, the style picture or the style line; and a note (note) saying what to do.

    python studio/stylekit.py --pictures a.jpg b.png --out <dir> --plan    convert and measure,
                                                                          no Claude, no painting
    python studio/stylekit.py --pictures a.jpg --out <dir> [--brief ".."] [--team]   read, set the
                                                                          faces, paint the proof
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import secrets
import argparse
import importlib
import contextlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image, ImageDraw, ImageFont, ImageOps  # noqa: E402

import brandkit  # noqa: E402
import locks  # noqa: E402
from film import STYLE_ROUTES, _write_json, paint_kinds, paint_pins  # noqa: E402

# ------------------------------------------------------------------ limits
PART = brandkit.PART  # the most one part may carry (the site sends ~3.8 MB)
MAX_FILE = 25 * 1024 * 1024  # one picture or font file
MAX_PICTURES = 3  # of one style: Claude reads them all, the painter gets the main one
MAX_FONT_FILES = 4  # the person's own faces, used only with their tick (fonts_consent)
LONG = 2048  # a picture's long side once converted
ASK_LONG = 1568  # the long side Claude sees
READS_A_DAY = 6
PROOFS_A_DAY = 10  # a read paints one proof; Paint again paints another
STALE_S = 20 * 60
STYLE_MAX = 300  # the style line
LAYOUT_MAX = 300
SUBJECT_MAX = 300
MAX_LINES = 6  # lines of lettering matched
MAX_CANDIDATES = 3
FONT_ROLES = ("title", "body", "accent")
PALETTE_ROLES = ("ground", "ink", "accent", "other")
LOOKS = ("drawn", "painted", "collage")
KINDS = ("script", "sans", "serif", "slab", "display", "handwriting", "typewriter", "mono")
SID = re.compile(r"^s-[a-z2-7]{10}$")
FAMILY = brandkit.FAMILY
_B32 = "abcdefghijklmnopqrstuvwxyz234567"
# the routes the proof paints, in the order the page shows them (film.STYLE_ROUTES says how)
ROUTES = ("gpt", "words", "gemini")
ROUTE_NAMES = {
    "gpt": "GPT Image, given your picture",
    "words": "Muse, from the style line",
    "gemini": "Gemini, given your picture",
}
# USD a picture as measured on 2026-10-15 (the proof's own prices replace them once it has run):
# what the team's Gemini note says until then. Never shown to anyone outside the team.
MEASURED_USD = {"gpt": 0.015, "words": 0.01, "gemini": 0.068}
PAINTINGS_30S = 8  # a 30-second painted film's paintings (film.limits)


class StyleError(Exception):
    """Why a style request was refused: an HTTP status and words for a person."""

    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ where a style lives
def dir_of(lib):
    import library  # noqa: PLC0415 -- library imports this module for seed and note

    return os.path.join(library.dir_of(lib), "style")


@contextlib.contextmanager
def _lock(d):
    os.makedirs(d, exist_ok=True)
    with locks.locked(os.path.join(d, ".lock")):
        yield


def state_of(d):
    st = _read_json(os.path.join(d, "state.json"), {}) or {}
    if not st.get("state"):
        st["state"] = "files" if pictures(d) else "empty"
    return st


def _set_state(d, **fields):
    st = _read_json(os.path.join(d, "state.json"), {}) or {}
    st.update(fields, at=_now())
    _write_json(os.path.join(d, "state.json"), st)
    return st


# ------------------------------------------------------------------ what the person sends
def _files(d):
    out, fd = [], os.path.join(d, "files")
    for n in sorted(os.listdir(fd)) if os.path.isdir(fd) else []:
        if n.endswith(".json"):
            m = _read_json(os.path.join(fd, n))
            if isinstance(m, dict) and SID.match(m.get("id", "")):
                out.append(m)
    return sorted(out, key=lambda m: (m.get("added", ""), m.get("seq", 0)))


def pictures(d):
    """The pictures, done and converted, in the order they were sent."""
    return [m for m in _files(d) if m.get("done") and m.get("kind") == "image"]


def font_files(d):
    return [m for m in _files(d) if m.get("done") and m.get("kind") == "font"]


def add_file(d, name, size):
    """Start a file of `size` bytes: its id, for put_part."""
    if not isinstance(size, int) or size <= 0:
        raise StyleError(400, "Say how big the file is.")
    if size > MAX_FILE:
        raise StyleError(413, "That file is over %d MB." % (MAX_FILE // 1048576))
    with _lock(d):
        if len(_files(d)) >= MAX_PICTURES + MAX_FONT_FILES:
            raise StyleError(
                409,
                "A style takes up to %d pictures and %d font files."
                % (MAX_PICTURES, MAX_FONT_FILES),
            )
        sid = "s-" + "".join(secrets.choice(_B32) for _ in range(10))
        m = {"id": sid, "name": brandkit.clean_name(name), "size": size, "got": 0, "done": False}
        m["added"], m["seq"] = _now(), time.time_ns()  # seq: two sent in the same second
        os.makedirs(os.path.join(d, "files"), exist_ok=True)
        open(os.path.join(d, "files", sid + ".bin"), "wb").close()
        _write_json(os.path.join(d, "files", sid + ".json"), m)
    return m


def put_part(d, sid, offset, data):
    """One part of a file at its offset (in order; a part sent again is taken as there)."""
    if not SID.match(sid or ""):
        raise StyleError(404, "No such file.")
    if len(data) > PART:
        raise StyleError(413, "A part is at most %d MB." % (PART // 1048576))
    meta_p = os.path.join(d, "files", sid + ".json")
    with _lock(d):
        m = _read_json(meta_p)
        if not m:
            raise StyleError(404, "No such file.")
        if m["done"]:
            raise StyleError(409, "That file is complete.")
        if offset + len(data) <= m["got"]:
            return m
        if offset != m["got"]:
            raise StyleError(409, "Part out of order: the file has %d bytes." % m["got"])
        if m["got"] + len(data) > m["size"]:
            raise StyleError(413, "That is more than the file's size.")
        with open(os.path.join(d, "files", sid + ".bin"), "ab") as f:
            f.write(data)
        m["got"] += len(data)
        _write_json(meta_p, m)
    return m


def sniff(head, name=""):
    """ "image", "font" or None. An AVIF is a picture (Pillow reads it); a HEIC is not one we can
    open, and is refused with how to send it instead."""
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "image"
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
            return "heic"
    kind = brandkit.sniff(head, name)
    return kind if kind in ("image", "font") else None


def convert(src, out, long_side=LONG):
    """A sent picture as an RGB JPEG of at most `long_side` (its first frame; its EXIF turn
    applied; transparency on white), and a thumbnail beside it. Its (w, h)."""
    with Image.open(src) as im:
        im.seek(0)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.split()[3])
            im = bg
        im = im.convert("RGB")
        im.thumbnail((long_side, long_side))
        im.save(out, "JPEG", quality=90, optimize=True)
        size = im.size
        im.thumbnail((360, 360))
        im.save(out[: -len(".jpg")] + ".t.jpg", "JPEG", quality=82)
    return size


def finish(d, sid):
    """The file is whole: a picture is converted, a face read; anything else is refused."""
    meta_p = os.path.join(d, "files", (sid or "") + ".json")
    with _lock(d):
        m = _read_json(meta_p) if SID.match(sid or "") else None
        if not m:
            raise StyleError(404, "No such file.")
        if m["got"] != m["size"]:
            raise StyleError(409, "The file has %d of its %d bytes." % (m["got"], m["size"]))
        binp = os.path.join(d, "files", sid + ".bin")
        with open(binp, "rb") as f:
            kind = sniff(f.read(64), m["name"])

        def refuse(status, text):
            for ext in (".json", ".bin"):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(d, "files", sid + ext))
            raise StyleError(status, text)

        if kind == "heic":
            refuse(415, "An iPhone photo (HEIC) cannot be read here: share it as a JPEG.")
        if kind == "image":
            if len(pictures(d)) >= MAX_PICTURES:
                refuse(409, "A style takes up to %d pictures." % MAX_PICTURES)
            os.makedirs(os.path.join(d, "pictures"), exist_ok=True)
            try:
                m["w"], m["h"] = convert(binp, os.path.join(d, "pictures", sid + ".jpg"))
            except Exception:  # noqa: BLE001 -- anything Pillow cannot open
                refuse(415, "That picture could not be opened: send it as a JPEG or a PNG.")
        elif kind == "font":
            if len(font_files(d)) >= MAX_FONT_FILES:
                refuse(409, "A style takes up to %d font files." % MAX_FONT_FILES)
            try:
                m.update(read_font(binp, os.path.join(d, "files", sid + ".ttf")))
            except Exception:  # noqa: BLE001
                refuse(415, "That font file could not be read.")
        else:
            refuse(415, "A style takes pictures (JPEG, PNG, WebP, AVIF, GIF) and font files.")
        m.update(done=True, kind=kind)
        _write_json(meta_p, m)
        st = state_of(d)
        if st["state"] in ("empty", "ready", "failed"):
            _set_state(d, state="files", stale=st["state"] == "ready")
    return m


def read_font(src, out):
    """A face the person sent, unpacked to a TrueType/OpenType file: {family, style, weight,
    italic, embedding}."""
    from fontTools.ttLib import TTCollection, TTFont  # noqa: PLC0415

    with open(src, "rb") as f:
        head = f.read(4)
    ft = TTCollection(src).fonts[0] if head == b"ttcf" else TTFont(src)
    ft.flavor = None  # woff/woff2 unpacked
    ft.save(out)
    return brandkit.font_info(ft)


def remove_file(d, sid):
    with _lock(d):
        p = os.path.join(d, "files", (sid or "") + ".json")
        if not SID.match(sid or "") or not os.path.exists(p):
            return False
        for ext in (".json", ".bin", ".ttf"):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(d, "files", sid + ext))
        for ext in (".jpg", ".t.jpg"):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(d, "pictures", sid + ext))
        if state_of(d)["state"] == "ready":
            _set_state(d, stale=True)
    return True


def remove(d):
    """The whole style: pictures, card, faces, proof, assets."""
    with _lock(d):
        for n in os.listdir(d) if os.path.isdir(d) else []:
            if n == ".lock":
                continue
            p = os.path.join(d, n)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


# ------------------------------------------------------------------ the colours, measured
def palette_of(paths, k=8, keep=6):
    """The colours the pictures share, measured (k-means over all of them): [{hex, share}],
    biggest first, near-twins merged."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    px = []
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((160, 160))
            px.append(np.asarray(im).reshape(-1, 3))
    if not px:
        return []
    data = np.concatenate(px).astype(np.float32)
    k = max(1, min(k, len(data)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(7)  # the same pictures give the same colours
    _c, labels, centres = cv2.kmeans(data, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    out = []
    for i in order:
        c = centres[i]
        if any(np.linalg.norm(c - np.array(o["_rgb"])) < 28 for o in out):
            twin = min(out, key=lambda o: np.linalg.norm(c - np.array(o["_rgb"])))
            twin["share"] += counts[i] / len(data)
            continue
        out.append({"_rgb": c.tolist(), "share": counts[i] / len(data)})
    out = [o for o in out if o["share"] >= 0.01][:keep]
    return [
        {
            "hex": "#%02X%02X%02X" % tuple(int(round(v)) for v in o["_rgb"]),
            "share": round(o["share"], 3),
        }
        for o in out
    ]


# ------------------------------------------------------------------ Claude's reading
WRITER = (
    "You read style pictures for a video studio. From one to three pictures that share a look, "
    "you write the style card its films follow: how the pictures are made, never what is in "
    "them. Answer with one JSON object and nothing else."
)

CARD_SHAPE = """{"style": ONE line, at most 300 characters, an image model's style line for
   painting anything in this look: the medium, the palette in plain colour words, the texture,
   the line, the light, the finish and the mood the pictures share. NEVER name a thing, person,
   animal, object, place, garment or word that appears in them (a style line's nouns get painted
   into every picture): "glossy cut-out studio photography" is a style, "a woman in an orange
   coat" is a thing,
 "objects": [the things, people, animals, places and words you see in the pictures, a word or two
   each], at most 20,
 "layout": how the pictures arrange things, one sentence (empty space, scattered objects, a frame,
   where words sit, grounds), naming no thing,
 "look": {"pick": "drawn" | "painted" | "collage", "why": one sentence}: drawn is drawn in code
   with a pen (line art, flat colour); painted is whole scenes painted by an image model; collage
   is cut-out pictures on paper pages built in code (photo cut-outs, type, stripes, stamps),
 "mixed": null, or one sentence when the pictures are not one style,
 "palette": [{"hex": one of the measured colours below, "role": "ground" | "ink" | "accent" |
   "other"}] for each measured colour,
 "lettering": [{"picture": its number (1-NPICS), "box": [x0, y0, x1, y1] as fractions of that
   picture, tight round ONE line of words, "text": the line's words exactly, "kind": one of KINDS,
   "case": "upper" | "lower" | "mixed", "spacing": letter-spacing in em (0 normal, 0.2 wide),
   "weight": 100-900, "role": "title" | "body" | "accent", "candidates": [2 or 3 families on Google
   Fonts that come closest, best first]}] -- the most telling lines, at most MAX_LINES, [] when the
   pictures have no lettering,
 "subject": one scene to paint as a proof of the style, taken from the project's brief below (or
   an everyday scene when there is no brief): what to paint, the framing, the moment -- no style,
   medium or colour words, no lettering, one sentence}"""


def ask_text(pics, palette, brief, look):
    shape = (
        CARD_SHAPE.replace("NPICS", str(len(pics)))
        .replace("MAX_LINES", str(MAX_LINES))
        .replace("KINDS", " | ".join('"%s"' % k for k in KINDS))
    )
    return "\n\n".join(
        [
            "%d picture%s of one style, shown above in order (1 to %d)."
            % (len(pics), "" if len(pics) == 1 else "s", len(pics)),
            "Their colours, measured (share of the pictures): "
            + ", ".join("%s %d%%" % (c["hex"], round(c["share"] * 100)) for c in palette),
            "The project's look today: %s." % look,
            "The project's brief:\n<<<\n%s\n>>>" % ((brief or "").strip()[:1500] or "(none)"),
            "Write the style card:\n" + shape,
        ]
    )


async def _claude(content, system, auth="login", effort="medium", session="style"):
    """One Claude call with no tools: what it said, and the cost."""
    from claude_agent_sdk import (  # noqa: PLC0415
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    import agent  # noqa: PLC0415

    async def prompt():
        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
            "session_id": session,
        }

    opts = ClaudeAgentOptions(
        model=agent.MODEL,
        effort=effort,
        system_prompt=system,
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=agent.claude_env(None, auth),
        **({"cli_path": agent.claude_cli()} if auth == "login" else {}),
    )
    said, cost, err = "", 0.0, None
    async for m in query(prompt=prompt(), options=opts):
        if isinstance(m, AssistantMessage):
            said += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        elif isinstance(m, ResultMessage):
            cost = m.total_cost_usd or 0.0
            err = m.result if m.is_error else None
    j = re.search(r"\{.*\}", said, re.S)
    try:
        d = json.loads(j.group(0)) if j else None
    except ValueError:
        d = None
    if err or not isinstance(d, dict):
        raise StyleError(502, "Claude could not read the pictures: %s" % (err or said[:200]))
    return d, cost


def _jpeg_for_claude(path):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((ASK_LONG, ASK_LONG))
        import io  # noqa: PLC0415

        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


async def ask(paths, palette, brief, look, auth="login"):
    content = []
    for i, p in enumerate(paths, 1):
        content += [
            {"type": "text", "text": "Picture %d:" % i},
            brandkit._img(_jpeg_for_claude(p)),  # noqa: SLF001
        ]
    content.append({"type": "text", "text": ask_text(paths, palette, brief, look)})
    return await _claude(content, WRITER, auth)


def leaks(style, objects):
    """The things seen in the pictures that the style line names (each would be painted)."""
    low = " %s " % re.sub(r"[^a-z0-9]+", " ", (style or "").lower())
    out = []
    for o in objects or []:
        words = [w for w in re.sub(r"[^a-z0-9]+", " ", str(o).lower()).split() if len(w) > 2]
        if words and all(" %s " % w in low or " %ss " % w in low for w in words):
            out.append(str(o))
    return out


async def rewrite_style(style, named, auth="login"):
    """The style line again, without the things it named."""
    text = (
        "This style line names things that are in the pictures (%s); an image model would paint "
        "them into every picture. Write it again without naming any thing, person, animal, "
        "object, place, garment or word: only the medium, palette, texture, line, light, finish "
        'and mood. At most %d characters. Answer {"style": "..."}.\n\n%s'
        % (", ".join(named), STYLE_MAX, style)
    )
    d, cost = await _claude([{"type": "text", "text": text}], WRITER, auth, effort="low")
    return str(d.get("style") or ""), cost


# ------------------------------------------------------------------ the card
_t = brandkit._t  # noqa: SLF001
_hex = brandkit._hex  # noqa: SLF001
_box = brandkit._box  # noqa: SLF001


def clean_card(d, pics, measured, fonts_sent=()):
    """A card held to its shape: a style line, colours that are colours, lettering with boxes and
    faces that exist, picks that point at something. On Claude's reading and on every edit."""
    d = d if isinstance(d, dict) else {}
    ids = [p["id"] for p in pics]
    card = {
        "style": _t(d.get("style"), STYLE_MAX),
        "objects": brandkit._list(d.get("objects"), 20, 40),  # noqa: SLF001
        "layout": _t(d.get("layout"), LAYOUT_MAX),
        "mixed": _t(d.get("mixed"), 200) or None,
        "subject": _t(d.get("subject"), SUBJECT_MAX),
    }
    look = d.get("look") if isinstance(d.get("look"), dict) else {}
    card["look"] = {
        "pick": look.get("pick") if look.get("pick") in LOOKS else "painted",
        "why": _t(look.get("why"), 200),
    }
    known = {c["hex"] for c in measured}
    roles = {}
    for c in d.get("palette") if isinstance(d.get("palette"), list) else []:
        h = _hex(c.get("hex")) if isinstance(c, dict) else None
        if h and (h in known or d.get("_edited")):
            roles[h] = c.get("role") if c.get("role") in PALETTE_ROLES else "other"
    palette = [{"hex": c["hex"], "role": roles.get(c["hex"], "other")} for c in measured]
    palette += [{"hex": h, "role": r} for h, r in roles.items() if h not in known]
    card["palette"] = palette[:10]
    lines = []
    for ln in d.get("lettering") if isinstance(d.get("lettering"), list) else []:
        if not isinstance(ln, dict) or len(lines) >= MAX_LINES:
            continue
        n = ln.get("picture") or 1  # Claude's number, or the card's own picture id on an edit
        if n in ids:
            n = ids.index(n) + 1
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        box = _box(ln.get("box"))
        if not (1 <= n <= len(ids)) or not box:
            continue
        cands = [
            c
            for c in (" ".join(str(x or "").split()) for x in ln.get("candidates") or [])
            if FAMILY.match(c)
        ]
        lines.append(
            {
                "picture": ids[n - 1],
                "box": box,
                "text": _t(ln.get("text"), 60) or "Aa",
                "kind": ln.get("kind") if ln.get("kind") in KINDS else "sans",
                "case": ln.get("case")
                if ln.get("case") in ("upper", "lower", "mixed")
                else "mixed",
                "spacing": _num(ln.get("spacing"), 0, -0.1, 0.6),
                "weight": int(_num(ln.get("weight"), 400, 100, 900) // 100 * 100),
                "role": ln.get("role") if ln.get("role") in FONT_ROLES else "accent",
                "candidates": list(dict.fromkeys(cands))[:MAX_CANDIDATES],
            }
        )
    card["lettering"] = lines
    sent = {f["family"] for f in fonts_sent}
    picks = d.get("fonts") if isinstance(d.get("fonts"), dict) else None
    if picks is None:  # Claude's reading: each role's first line, its best face
        picks = {}
        for ln in lines:
            if ln["role"] not in picks and ln["candidates"]:
                picks[ln["role"]] = {"family": ln["candidates"][0], "weight": ln["weight"]}
    offered = {c for ln in lines for c in ln["candidates"]} | sent
    card["fonts"] = {}
    for role in FONT_ROLES:
        p = picks.get(role) if isinstance(picks.get(role), dict) else None
        if p and p.get("family") in offered:
            card["fonts"][role] = {
                "family": p["family"],
                "weight": int(_num(p.get("weight"), 400, 100, 900) // 100 * 100),
                "sent": p["family"] in sent,
            }
    card["fonts_consent"] = bool(d.get("fonts_consent"))
    card["main"] = d.get("main") if d.get("main") in ids else (ids[0] if ids else None)
    card["route"] = d.get("route") if d.get("route") in STYLE_ROUTES else "words"
    card["route_team"] = bool(d.get("route_team")) and card["route"] == "gemini"
    return card


def _num(v, default, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, x))


# ------------------------------------------------------------------ the lettering, matched
def set_line(font_path, text, h, spacing=0.0, case="mixed"):
    """`text` set in a face on white, `h` px tall, letter-spaced `spacing` em (PIL)."""
    text = text.upper() if case == "upper" else text.lower() if case == "lower" else text
    size = max(8, int(h * 0.72))  # fills a line h px tall
    f = ImageFont.truetype(font_path, size)
    gap = spacing * size
    w = int(sum(f.getlength(c) for c in text) + gap * max(0, len(text) - 1)) + 24
    im = Image.new("RGB", (max(w, 40), h), "white")
    dr, x = ImageDraw.Draw(im), 12
    for c in text:
        dr.text((x, h * 0.12), c, font=f, fill="#14171f")
        x += f.getlength(c) + gap
    return im


def letter_sheets(d, card, log=print):
    """fonts/l<i>.jpg (each line cut out of its picture) and fonts/l<i>-<k>.png (its words in
    each candidate); a candidate that cannot be fetched is dropped from the card. The card."""
    out = os.path.join(d, "fonts")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for i, ln in enumerate(card["lettering"]):
        src = os.path.join(d, "pictures", ln["picture"] + ".jpg")
        try:
            with Image.open(src) as im:
                w, h = im.size
                x0, y0, x1, y1 = ln["box"]
                crop = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).convert("RGB")
        except OSError as e:
            log("lettering %d: %s" % (i, e))
            continue
        H = 110
        crop = crop.resize((max(1, int(crop.width * H / max(1, crop.height))), H))
        crop.save(os.path.join(out, "l%d.jpg" % i), quality=88)
        kept = []
        for fam in ln["candidates"]:
            got = brandkit.standin(d, fam, sorted({400, 700, ln["weight"]}), log)
            if not got:
                continue
            path = min(got, key=lambda g: abs(g[1] - ln["weight"]))[0]
            k = len(kept)
            set_line(path, ln["text"], H, ln["spacing"], ln["case"]).save(
                os.path.join(out, "l%d-%d.png" % (i, k))
            )
            kept.append(fam)
        ln["candidates"] = kept
    offered = {c for ln in card["lettering"] for c in ln["candidates"]}
    card["fonts"] = {
        r: f for r, f in card["fonts"].items() if f.get("sent") or f["family"] in offered
    }
    return card


# ------------------------------------------------------------------ the proof
def _sp():
    return importlib.import_module("sketch-paint")


def paint_one(route, subject, style_line, style_jpg, out):
    """One proof picture: (path, {cost_usd, seconds}) or raises. Always wide (16:9): it shows
    the style, not a film, so a tall project's proof is wide too."""
    sp = _sp()
    r = STYLE_ROUTES[route]
    t = time.time()
    if r["picture"]:
        prompt = sp.full_prompt({"style": ""}, {"prompt": subject})
        data, meta = sp.paint_openrouter(prompt, r["model"], style_ref=style_jpg)
    else:
        prompt = sp.full_prompt({"style": style_line}, {"prompt": subject})
        data, meta = sp.paint_openrouter(prompt, r["model"])
    sp.to_jpeg(data, out)
    return out, {"cost_usd": meta.get("cost_usd"), "seconds": round(time.time() - t, 1)}


def routes_for(team):
    return [r for r in ROUTES if team or not STYLE_ROUTES[r].get("team")]


def paint_proof(d, card, team, log=print):
    """proof/<route>.jpg for each route this person may pick, painted at once; proof.json."""
    pd = os.path.join(d, "proof")
    os.makedirs(pd, exist_ok=True)
    main = os.path.join(d, "pictures", (card.get("main") or "") + ".jpg")
    subject = card.get("subject") or "A quiet street corner in the morning, a wide shot."
    results = {}

    def run(route):
        new = os.path.join(pd, route + ".new.jpg")
        try:
            _p, meta = paint_one(route, subject, card.get("style") or "", main, new)
            os.replace(new, os.path.join(pd, route + ".jpg"))
            return route, {**meta, "at": _now()}
        except Exception as e:  # noqa: BLE001 -- one painter failing leaves the others
            log("proof %s: %s" % (route, e))
            return route, {"error": str(e)[:200], "at": _now()}

    with ThreadPoolExecutor(max_workers=3) as ex:
        for route, got in ex.map(run, routes_for(team)):
            results[route] = got
    before = _read_json(os.path.join(pd, "proof.json"), {}) or {}
    keep = {k: v for k, v in (before.get("routes") or {}).items() if k not in results}
    proof = {"subject": subject, "routes": {**keep, **results}, "at": _now()}
    _write_json(os.path.join(pd, "proof.json"), proof)
    return proof


PROOF_S = 300  # the proof's painters all at once: the slowest took ~40 s when measured


async def paint_proof_step(d, team, log=print):
    """The proof painted as a step of its own (python stylekit.py --proof <d>), handed only the
    painter's key: the server's own environment carries no secret (procs.load_secrets). The proof
    it wrote."""
    import procs  # noqa: PLC0415

    env = {k: os.environ[k] for k in procs.BASICS if k in os.environ}
    env.update(PYTHONIOENCODING="utf-8", KITCUT_DOTENV="0")
    key = procs.secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        env["OPENROUTER_API_KEY"] = key
    argv = [sys.executable, "-X", "utf8", os.path.abspath(__file__), "--proof", d]
    p = await asyncio.create_subprocess_exec(
        *argv + (["--team"] if team else []),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(p.communicate(), PROOF_S)
    except TimeoutError:
        p.kill()
        raise StyleError(504, "The proof took too long to paint: paint it again.") from None
    for line in (out or b"").decode("utf-8", "replace").splitlines()[-6:]:
        log(line)
    proof = _read_json(os.path.join(d, "proof", "proof.json"))
    if p.returncode or not proof:
        raise StyleError(502, "The proof could not be painted.")
    return proof


def prices(proof):
    """USD a picture for each route: the proof's own, else what was measured."""
    out = dict(MEASURED_USD)
    for r, got in ((proof or {}).get("routes") or {}).items():
        if isinstance(got.get("cost_usd"), (int, float)) and got["cost_usd"] > 0:
            out[r] = round(got["cost_usd"], 4)
    return out


def gemini_note(proof):
    """What the team is told every time Gemini is on the table: it costs more."""
    p = prices(proof)
    times = p["gemini"] / max(p["words"], 1e-6)
    return (
        "Team only. Gemini costs about %d times as much per picture as Muse (a 30-second painted "
        "film: about $%.2f in pictures, against $%.2f with Muse or $%.2f with GPT Image)."
        % (
            round(times),
            p["gemini"] * PAINTINGS_30S,
            p["words"] * PAINTINGS_30S,
            p["gpt"] * PAINTINGS_30S,
        )
    )


# ------------------------------------------------------------------ assets
STYLE_JS = """// The project's style (studio/stylekit.py): SK.STYLE, and the kit writing in its body face.
// A project's brand (brand.js, loaded after this) wins wherever it says something too.
SK.STYLE = %s;
if (SK.KIT && SK.STYLE.fonts.body) SK.KIT.font = SK.STYLE.fonts.body;
"""


def build_assets(d, card, log=print):
    """assets/: the main picture as style.jpg, the faces picked (a sent one only with the
    person's tick, else its free stand-in or nothing), style.js, used.json. What an episode
    gets: {"faces": [...], "fonts": {role: family}, "palette", "route"}."""
    out = os.path.join(d, "assets.new")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "fonts"))
    main = os.path.join(d, "pictures", (card.get("main") or "") + ".jpg")
    if os.path.exists(main):
        shutil.copyfile(main, os.path.join(out, "style.jpg"))
    sent = {f["family"]: f for f in font_files(d)}
    faces, families = [], {}
    for role in FONT_ROLES:
        pick = card["fonts"].get(role)
        if not pick:
            continue
        fam, wt = pick["family"], pick["weight"]
        if pick.get("sent") and fam in sent:
            if not card.get("fonts_consent"):
                continue  # the person's own face: only with their tick
            for f in font_files(d):
                if f["family"] == fam:
                    dst = "fonts/%s.ttf" % f["id"]
                    if not any(x["file"] == dst for x in faces):
                        shutil.copyfile(
                            os.path.join(d, "files", f["id"] + ".ttf"), os.path.join(out, dst)
                        )
                        faces.append({"file": dst, "family": fam, "weight": str(f["weight"])})
            families[role] = {"family": fam, "weight": wt, "sent": True}
            continue
        got = brandkit.standin(d, fam, sorted({400, 700, wt}), log)
        if not got:
            continue
        for p, w in got:
            dst = "fonts/" + os.path.basename(p)
            if not any(x["file"] == dst for x in faces):
                shutil.copyfile(p, os.path.join(out, dst))
                faces.append({"file": dst, "family": fam, "weight": str(w)})
        families[role] = {"family": fam, "weight": wt, "sent": False}
    colors = {}
    for c in card["palette"]:
        colors.setdefault(c["role"], c["hex"])
    style = {
        "line": card["style"],
        "layout": card["layout"],
        "palette": card["palette"],
        "colors": colors,
        "fonts": {
            role: families[role]["family"] if role in families else None for role in FONT_ROLES
        }
        | {role + "Weight": (families.get(role) or {}).get("weight") for role in FONT_ROLES},
    }
    with open(os.path.join(out, "style.js"), "w", encoding="utf-8") as f:
        f.write(STYLE_JS % json.dumps(style, ensure_ascii=False))
    used = {"faces": faces, "families": families, "style": style, "route": card["route"]}
    _write_json(os.path.join(out, "used.json"), used)
    brandkit._swap(out, os.path.join(d, "assets"))  # noqa: SLF001
    return used


# ------------------------------------------------------------------ reading, as a job
TASKS = set()


def in_flight():
    return [t for t in TASKS if not t.done()]


def _busy(st):
    if st.get("state") != "reading" and not st.get("step"):
        return False
    try:
        at = datetime.fromisoformat(st.get("at") or "")
    except ValueError:
        return False
    return (datetime.now() - at).total_seconds() < STALE_S


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(coro)
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return t


def _count(st, key, limit, what):
    now = time.time()
    done = [r for r in st.get(key) or [] if now - r < 86400]
    if len(done) >= limit:
        raise StyleError(429, "%s at most %d times a day." % (what, limit))
    return done + [now]


def start(d, auth="login", look="painted", brief="", team=False, log=print):
    """Begin reading the style in the background: the state as it is now."""
    with _lock(d):
        st = state_of(d)
        if _busy(st):
            raise StyleError(409, "The style is being read already.")
        if not pictures(d):
            raise StyleError(409, "Add a picture first.")
        reads = _count(st, "reads", READS_A_DAY, "A style is read")
        st = _set_state(
            d,
            state="reading",
            step="measuring",
            error=None,
            reads=reads,
            started=_now(),
            server=brandkit._server(),  # noqa: SLF001
        )
    _spawn(read(d, auth, look if look in LOOKS else "painted", brief, team, log))
    return st


async def read(d, auth="login", look="painted", brief="", team=False, log=print):
    """The read (start() runs it): measure, ask, set the faces, paint the proof, the assets.
    Never raises: a failure is the state's, in words."""
    try:
        pics = pictures(d)
        paths = [os.path.join(d, "pictures", p["id"] + ".jpg") for p in pics]
        measured = await asyncio.to_thread(palette_of, paths)
        _set_state(d, step="looking", palette=measured)
        raw, cost = await ask(paths, measured, brief, look, auth)
        before = _read_json(os.path.join(d, "card.json"), {}) or {}
        keep = {
            k: before[k] for k in ("fonts_consent", "main", "route", "route_team") if k in before
        }
        card = clean_card({**raw, **keep, "fonts": None}, pics, measured, font_files(d))
        named = leaks(card["style"], card["objects"])
        if named:
            log("style line names %s: asked again" % ", ".join(named))
            again, more = await rewrite_style(card["style"], named, auth)
            cost += more
            if again and not leaks(again, card["objects"]):
                card["style"] = _t(again, STYLE_MAX)
        card["leaks"] = leaks(card["style"], card["objects"])
        _set_state(d, step="fonts")
        card = await asyncio.to_thread(letter_sheets, d, card, log)
        card["read_at"] = _now()
        _write_json(os.path.join(d, "card.json"), card)
        _set_state(d, step="proof")
        st = _read_json(os.path.join(d, "state.json"), {}) or {}
        proofs = [r for r in st.get("proofs") or [] if time.time() - r < 86400]
        proof = await paint_proof_step(d, team, log)
        spent = sum(g.get("cost_usd") or 0 for g in proof["routes"].values() if isinstance(g, dict))
        await asyncio.to_thread(build_assets, d, card, log)
        st = state_of(d)
        _set_state(
            d,
            state="ready",
            step=None,
            stale=False,
            read_at=card["read_at"],
            proofs=proofs + [time.time()],
            cost_usd=round((st.get("cost_usd") or 0) + cost + spent, 4),
        )
    except Exception as e:  # noqa: BLE001 -- the page shows why
        why = e.text if isinstance(e, StyleError) else (str(e) or type(e).__name__)
        log("style read failed: %s" % why)
        _set_state(d, state="failed", step=None, error=why[:300])


def proof_again(d, team=False, subject=None, log=print):
    """Paint the proof again (a new subject, or the same), in the background."""
    with _lock(d):
        st = state_of(d)
        card = _read_json(os.path.join(d, "card.json"))
        if not card or st.get("state") != "ready":
            raise StyleError(409, "The style is not read yet.")
        if _busy(st):
            raise StyleError(409, "The proof is being painted already.")
        proofs = _count(st, "proofs", PROOFS_A_DAY, "The proof is painted")
        if subject is not None:
            card["subject"] = _t(subject, SUBJECT_MAX) or card.get("subject")
            _write_json(os.path.join(d, "card.json"), card)
        st = _set_state(d, step="proof", proofs=proofs)

    async def go():
        try:
            proof = await paint_proof_step(d, team, log)
            spent = sum(g.get("cost_usd") or 0 for g in proof["routes"].values())
            cur = state_of(d)
            _set_state(d, step=None, cost_usd=round((cur.get("cost_usd") or 0) + spent, 4))
        except Exception as e:  # noqa: BLE001
            _set_state(d, step=None, error=str(e)[:300])

    _spawn(go())
    return st


EDITABLE = ("style", "layout", "palette", "fonts", "fonts_consent", "main", "route", "subject")


def edit(d, patch, team=False, log=print):
    """The person's corrections: the card with these fields replaced, held to its shape, its
    assets made again. Gemini is picked only by the team; anyone else's change to a card on the
    Gemini route moves it to GPT Image, and the card says why. The card."""
    if not isinstance(patch, dict):
        raise StyleError(400, "Send the fields to change.")
    if patch.get("route") == "gemini" and not team:
        raise StyleError(403, "Gemini is for the KitCut team only.")
    with _lock(d):
        card = _read_json(os.path.join(d, "card.json"))
        if not card or state_of(d).get("state") == "reading":
            raise StyleError(409, "The style is not read yet.")
        measured = (state_of(d).get("palette")) or [
            {"hex": c["hex"], "share": 0} for c in card["palette"]
        ]
        merged = {**card, **{k: v for k, v in patch.items() if k in EDITABLE}, "_edited": True}
        if "route" in patch:
            merged["route_team"] = patch["route"] == "gemini" and team
        note = None
        if merged.get("route") == "gemini" and not team:
            merged.update(route="gpt", route_team=False)
            note = "Gemini is for the KitCut team only: this style now uses GPT Image."
        new = clean_card(merged, pictures(d), measured, font_files(d))
        for k in ("objects", "lettering", "look", "mixed", "read_at", "leaks"):
            if k in card:
                new[k] = card[k]
        if "style" in patch:
            new["leaks"] = leaks(new["style"], card.get("objects"))
        new.update(edited_at=_now(), route_note=note)
        _write_json(os.path.join(d, "card.json"), new)
    build_assets(d, new, log)
    return new


# ------------------------------------------------------------------ what the page sees
def public(d, team=False):
    st = state_of(d)
    if st.get("state") == "reading" and not _busy(st):
        st = _set_state(d, state="failed", step=None, error="The read was interrupted: read again.")
    elif st.get("step") and not _busy(st):
        st = _set_state(d, step=None)
    card = _read_json(os.path.join(d, "card.json"))
    proof = _read_json(os.path.join(d, "proof", "proof.json"), {}) or {}
    shown = routes_for(team)
    routes = []
    for r in shown:
        got = (proof.get("routes") or {}).get(r) or {}
        row = {
            "id": r,
            "name": ROUTE_NAMES[r],
            "team": bool(STYLE_ROUTES[r].get("team")),
            "painted": os.path.exists(os.path.join(d, "proof", r + ".jpg")),
            "at": got.get("at"),
            "error": got.get("error"),
        }
        if team:  # what each costs: the team's alone, never a customer's page
            row["usd"] = prices(proof)[r]
        routes.append(row)
    used = _read_json(os.path.join(d, "assets", "used.json"), {}) or {}
    return {
        "state": st["state"],
        "step": st.get("step"),
        "error": st.get("error"),
        "stale": bool(st.get("stale")),
        "files": [
            {k: m.get(k) for k in ("id", "name", "size", "done", "kind", "w", "h", "family")}
            for m in _files(d)
        ],
        "card": card,
        "proof": {"subject": proof.get("subject"), "routes": routes, "at": proof.get("at")},
        "gemini_note": gemini_note(proof) if team else None,
        "team": bool(team),
        "in_use": {"fonts": used.get("families") or {}},
        "limits": {"pictures": MAX_PICTURES, "font_files": MAX_FONT_FILES},
        "read_at": st.get("read_at"),
    }


ASSET = re.compile(r"^(picture|thumb|crop|face|proof)/([a-z0-9_\-]{1,40})$")


def asset(d, kind, name):
    """A file the page shows: (path, content type), or None."""
    if not ASSET.match("%s/%s" % (kind, name)):
        return None
    p, ct = {
        "picture": (os.path.join(d, "pictures", name + ".jpg"), "image/jpeg"),
        "thumb": (os.path.join(d, "pictures", name + ".t.jpg"), "image/jpeg"),
        "crop": (os.path.join(d, "fonts", name + ".jpg"), "image/jpeg"),
        "face": (os.path.join(d, "fonts", name + ".png"), "image/png"),
        "proof": (os.path.join(d, "proof", name + ".jpg"), "image/jpeg"),
    }[kind]
    return (p, ct) if os.path.exists(p) else None


# ------------------------------------------------------------------ an episode's style
def route_of(card):
    """The route an episode is painted on: Gemini only when a team member picked it."""
    r = card.get("route") if card.get("route") in STYLE_ROUTES else "words"
    if r == "gemini" and not card.get("route_team"):
        return "gpt"
    return r


def seed(film, lib):
    """A ready style into a new episode: its assets in style/, its faces in the manifest,
    style.js before film.js (and before a brand's brand.js, which wins), the record's
    paint_route, and paint.json pinned to it. What it got, or None."""
    d = dir_of(lib)
    used = _read_json(os.path.join(d, "assets", "used.json"))
    card = _read_json(os.path.join(d, "card.json"))
    if not used or not card:
        return None
    dst = film.path("style")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(d, "assets"), dst, ignore=shutil.ignore_patterns("used.json"))
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    fonts = [f for f in m.get("fonts") or [] if not str(f.get("file", "")).startswith("style/")]
    m["fonts"] = fonts + [dict(f, file="style/" + f["file"]) for f in used["faces"]]
    head = [s for s in (m.get("head") or {}).get("scripts", []) if s != "style/style.js"]
    m["head"] = {**(m.get("head") or {}), "scripts": ["style/style.js", *head]}
    _write_json(film.manifest, m)
    route = route_of(card)
    picture = STYLE_ROUTES[route]["picture"] and os.path.exists(film.path("style", "style.jpg"))
    pr = {
        "route": route if picture or route == "words" else "words",
        "ref": "style/style.jpg" if picture else None,
        "line": card.get("style") or "",
    }
    film.update(paint_route=pr)
    if paint_kinds(film.caps) and os.path.exists(film.path("paint.json")):
        p = _read_json(film.path("paint.json"), {}) or {}
        _write_json(film.path("paint.json"), p | paint_pins(film.length, film.caps, pr))
    return {"route": pr["route"], "fonts": used["families"], "picture": bool(picture)}


def note(film, lib):
    """What an episode is told of its project's style ("" without one)."""
    d = dir_of(lib)
    card = _read_json(os.path.join(d, "card.json"))
    used = _read_json(os.path.join(d, "assets", "used.json"))
    if not card or not used or not os.path.exists(film.path("style", "style.js")):
        return ""
    pr = film.record().get("paint_route") or {}
    fam = used.get("families") or {}
    colours = "; ".join("%s %s" % (c["role"], c["hex"]) for c in card["palette"])
    lines = [
        "This project has a style, from its person's own pictures: every picture, colour and "
        "line of lettering in this film follows it. Read style/style.jpg to see it.",
        "- The style: %s" % card["style"],
        "- How its pictures are laid out: %s" % (card.get("layout") or "(not said)"),
        "- Its colours (SK.STYLE.colors, SK.STYLE.palette): %s. Grounds, ink and accents come "
        "from these; bring in no new hues." % colours,
    ]
    if fam:
        lines.append(
            "- Its lettering, matched with free faces: %s. Set titles, captions and words on "
            "screen in these (SK.STYLE.fonts; the kit writes in the body face already)."
            % "; ".join(
                "%s in '%s' %s" % (role, f["family"], f.get("weight") or "")
                for role, f in fam.items()
            )
        )
    if paint_kinds(film.caps):
        if pr.get("ref"):
            lines.append(
                "- Its pictures are painted FROM the style picture: the studio gives it to the "
                "painter with every picture (paint.json's painter, style and style_ref are the "
                "studio's; this overrides the look's words that the painter works from words alone "
                "and that a ref changes nothing). "
                "So each image's prompt says ONLY what to draw -- the subject, the framing, the "
                "moment -- with no medium, style, palette or colour words: a colour word beats "
                'the picture ("pink roses" came back pink from a black-ink style). A `ref` '
                "works now too: it keeps a character the same from picture to picture, and "
                '`"ref": "pic_<name>"` paints from one of the project\'s own pictures (a cast '
                'sheet of its people, then each scene with `"ref"` naming the sheet).'
            )
        else:
            lines.append(
                "- Its pictures are painted from the style line above, which the studio sets as "
                "paint.json's style (yours to leave). Each image's prompt says what to draw and "
                "adds no other style."
            )
    if os.path.exists(film.path("brand", "brand.js")):
        lines.append(
            "- The project has a brand too, and the brand wins where both speak: its faces, "
            "colours and logo on titles, captions and the end card; the style for the pictures "
            "and whatever the brand leaves open."
        )
    return "\n".join(lines)


# ------------------------------------------------------------------ the command line
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pictures", nargs="+", help="1-3 pictures of one style")
    ap.add_argument("--out", help="a folder to read into (a style's own layout)")
    ap.add_argument("--proof", metavar="DIR", help="paint the proof of a read style (a step)")
    ap.add_argument("--brief", default="", help="the project's brief, for the proof's subject")
    ap.add_argument("--look", default="painted", choices=LOOKS)
    ap.add_argument("--team", action="store_true", help="paint Gemini's proof too")
    ap.add_argument("--plan", action="store_true", help="convert and measure; no Claude, no paint")
    ap.add_argument("--auth", default="login", choices=("login", "api"))
    a = ap.parse_args()
    if a.proof:  # the server's step (paint_proof_step): the card is there, the key is in env
        card = _read_json(os.path.join(a.proof, "card.json"))
        if not card:
            sys.exit("no card.json in %s" % a.proof)
        proof = paint_proof(a.proof, card, a.team)
        print(
            "proof: %s"
            % ", ".join(
                "%s %s" % (r, "ok" if not g.get("error") else g["error"])
                for r, g in proof["routes"].items()
            )
        )
        return
    if not a.pictures or not a.out:
        ap.error("--pictures and --out, or --proof")
    import procs  # noqa: PLC0415 -- the studio's keys, as the server reads them

    procs.load_secrets(
        os.environ.get("STUDIO_ENV_FILE") or os.path.join(os.path.dirname(HERE), ".env")
    )
    if len(a.pictures) > MAX_PICTURES:
        sys.exit("at most %d pictures" % MAX_PICTURES)
    d = os.path.abspath(a.out)
    remove(d)
    for p in a.pictures:
        size = os.path.getsize(p)
        m = add_file(d, os.path.basename(p), size)
        with open(p, "rb") as f:
            off = 0
            while chunk := f.read(PART):
                put_part(d, m["id"], off, chunk)
                off += len(chunk)
        finish(d, m["id"])
    paths = [os.path.join(d, "pictures", p["id"] + ".jpg") for p in pictures(d)]
    measured = palette_of(paths)
    print("pictures: %s" % ", ".join("%s %dx%d" % (p["name"], p["w"], p["h"]) for p in pictures(d)))
    print("colours: %s" % ", ".join("%s %d%%" % (c["hex"], c["share"] * 100) for c in measured))
    if a.plan:
        print("--plan: no Claude, nothing painted; Claude would be asked:\n")
        print(ask_text(paths, measured, a.brief, a.look))
        return

    async def go():
        st = start(d, a.auth, a.look, a.brief, a.team)
        print("reading (%s)" % st["state"])
        while in_flight():
            await asyncio.sleep(2)

    asyncio.run(go())
    pub = public(d, a.team)
    print(
        json.dumps(
            {k: pub[k] for k in ("state", "error", "card", "proof", "gemini_note")}, indent=1
        )
    )


if __name__ == "__main__":
    main()
