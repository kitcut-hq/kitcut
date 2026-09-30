"""Templates: a finished film that others remake with their own content (kitcut.ai's templates).

    STUDIO_HOME\\templates\\<id>\\
        index.json                  {"latest": N, "versions": {"N": "draft"|"live"|"retired"}}
        v<N>\\                      read-only once built (make): a version never changes
            template.json           what it is, its form (fields) and its author's brief
            film.js                 the film's code; it reads its words and people from
                                    content.json (SK.DATA.content) and writes its own sound
            content.sample.json     the author's content: the preview's, never seeded
            engine\\*.js            the engine it was drawn with, frozen
            sample\\                the sample's pictures (its logo, its people): the preview and
                                    the health check only, never seeded
            sketch.json             the preview's manifest (the sample, the frozen engine)
            preview\\<frame>\\       stills at its moments and their sheet, per frame

A film made from one starts from the template's code, its score and cues, and a content.json built
from the person's form (build_content); its pictures are the person's (people are cut out of their
photos first, cut_people). Claude is told to keep everything but the content (ask), and leftovers()
names any of the sample's own words still in the film, which stops the final render. A film never
gets the author's conversation, uploads, voice or project: make() copies only what is listed here.

check() re-draws a version's sample with this release's renderer and compares it to the stills
the version was made with: an engine change that would break a live template stops the ship.

Invoke as:
    python studio/templates.py make --folder projects/<id> --id t-<slug> --spec <spec.json> [--plan]
    python studio/templates.py check [--id t-<slug>]
    python studio/templates.py publish t-<slug> <N> | retire t-<slug> <N> | list
"""

import os
import re
import sys
import json
import stat
import shutil
import hashlib
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from film import ENGINE, HOME, KIT, RELEASE, _write_json  # noqa: E402

ID = re.compile(r"^t-[a-z0-9][a-z0-9-]{2,40}$")
FRAMES = {"16:9": [1920, 1080], "1:1": [1080, 1080], "9:16": [1080, 1920]}
KINDS = ("text", "lines", "url", "colour", "daterange", "image", "logo", "people", "select")
MAX_PEOPLE = 30  # a people field's rows, at most
TEXT_MAX = 200  # a text field's characters, at most, whatever its own max says
# what a version's folder holds besides template.json: nothing else is ever copied into one
CODE = ("film.js",)
MONTHS = (
    "JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER".split()
)


class TemplateError(ValueError):
    pass


# ------------------------------------------------------------------ where they are
def root():
    return os.path.join(HOME, "templates")


def vdir(tid, v):
    return os.path.join(root(), tid, "v%d" % int(v))


def _read(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def index(tid):
    return _read(os.path.join(root(), tid, "index.json"), {"latest": 0, "versions": {}})


def load(tid, version=None, status=("live",)):
    """A version's template.json (with "_dir"), or None: the latest one in status when no version
    is named; a named one only in status."""
    if not isinstance(tid, str) or not ID.match(tid):
        return None
    idx = index(tid)
    vs = idx.get("versions") or {}
    if version is None:
        ok = [int(v) for v, s in vs.items() if s in status]
        if not ok:
            return None
        version = max(ok)
    if vs.get(str(int(version))) not in status:
        return None
    t = _read(os.path.join(vdir(tid, version), "template.json"))
    if t:
        t["_dir"] = vdir(tid, version)
    return t


def live():
    """The latest live version of every template."""
    d = root()
    names = sorted(os.listdir(d)) if os.path.isdir(d) else []
    return [t for t in (load(n) for n in names if ID.match(n)) if t]


def public(t):
    """What anyone may see of a template: never its author's brief to Claude or its sample."""
    return {
        k: t.get(k)
        for k in (
            "id",
            "version",
            "title",
            "description",
            "author",
            "seconds",
            "frames",
            "look",
            "narration",
            "fields",
            "moments",
        )
    }


# ------------------------------------------------------------------ the form
def _text(v, f, upper=None):
    s = " ".join(str(v).split())
    mx = min(int(f.get("max") or TEXT_MAX), TEXT_MAX)
    if len(s) > mx:
        raise TemplateError("%s: at most %d characters" % (f["label"], mx))
    return s.upper() if (f.get("upper") if upper is None else upper) else s


def _date(s):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    if not m:
        raise TemplateError("dates are YYYY-MM-DD")
    y, mo, d = map(int, m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        raise TemplateError("dates are YYYY-MM-DD")
    return y, mo, d


def dates_words(a, b):
    """("NOV 9–12", "NOVEMBER 9–12, 2026", "2026") for a date range: the short one fits a
    10-cell split-flap row whenever the range stays in one month."""
    (y1, m1, d1), (y2, m2, d2) = _date(a), _date(b)
    if (y2, m2, d2) < (y1, m1, d1):
        raise TemplateError("the end date is before the start")
    M1, M2 = MONTHS[m1 - 1], MONTHS[m2 - 1]
    if (y1, m1, d1) == (y2, m2, d2):
        return "%s %d" % (M1[:3], d1), "%s %d, %d" % (M1, d1, y1), str(y1)
    if (y1, m1) == (y2, m2):
        return "%s %d–%d" % (M1[:3], d1, d2), "%s %d–%d, %d" % (M1, d1, d2, y1), str(y1)
    if y1 == y2:
        return (
            "%s%d–%s%d" % (M1[:3], d1, M2[:3], d2),
            "%s %d – %s %d, %d" % (M1, d1, M2, d2, y1),
            str(y1),
        )
    return (
        "%s%d–%s%d" % (M1[:3], d1, M2[:3], d2),
        "%s %d, %d – %s %d, %d" % (M1, d1, y1, M2, d2, y2),
        str(y2),
    )


def validate_fields(t, values):
    """The person's form, checked against the template's fields: {key: clean value} (an image is
    its upload id), or TemplateError naming the first field that is wrong. Unknown keys are
    dropped; a value that is too long is refused, never cut."""
    if not isinstance(values, dict):
        raise TemplateError("fields must be an object")
    out = {}
    for f in t["fields"]:
        k, kind, v = f["key"], f["kind"], values.get(f["key"])
        empty = v is None or v == "" or v == [] or v == {}
        if empty:
            if f.get("required"):
                raise TemplateError("%s is required" % f["label"])
            continue
        if kind in ("text", "url", "select"):
            if not isinstance(v, str):
                raise TemplateError("%s: text" % f["label"])
            s = _text(v, f)
            if kind == "url":
                s = s.lower() if f.get("lower", True) else s
                if not re.fullmatch(r"(https?://)?[a-z0-9.-]+\.[a-z]{2,}(/\S*)?", s, re.I):
                    raise TemplateError("%s: a web address" % f["label"])
            if kind == "select" and s not in (f.get("options") or ()):
                raise TemplateError("%s: one of %s" % (f["label"], ", ".join(f["options"])))
            if f.get("min_len") and len(s) < f["min_len"]:
                raise TemplateError("%s: at least %d characters" % (f["label"], f["min_len"]))
            out[k] = s
        elif kind == "lines":
            lines = v.splitlines() if isinstance(v, str) else v
            if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
                raise TemplateError("%s: lines of text" % f["label"])
            lines = [_text(x, f) for x in lines if x.strip()]
            if not lines or len(lines) > int(f.get("lines") or 3):
                raise TemplateError("%s: 1 to %d lines" % (f["label"], int(f.get("lines") or 3)))
            out[k] = lines
        elif kind == "colour":
            if not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                raise TemplateError("%s: a colour like #0C1439" % f["label"])
            out[k] = v.upper()
        elif kind == "daterange":
            if not isinstance(v, dict):
                raise TemplateError("%s: {from, to}" % f["label"])
            dates_words(v.get("from"), v.get("to") or v.get("from"))
            out[k] = {"from": v["from"], "to": v.get("to") or v["from"]}
        elif kind in ("image", "logo"):
            if not isinstance(v, str) or not v.startswith("up-"):
                raise TemplateError("%s: an uploaded picture" % f["label"])
            out[k] = v
        elif kind == "people":
            if not isinstance(v, list):
                raise TemplateError("%s: a list of people" % f["label"])
            mx, mn = min(int(f.get("max") or MAX_PEOPLE), MAX_PEOPLE), int(f.get("min") or 1)
            if not mn <= len(v) <= mx:
                raise TemplateError("%s: %d to %d people" % (f["label"], mn, mx))
            rows, photos = [], set()
            for i, p in enumerate(v, 1):
                if not isinstance(p, dict) or not str(p.get("photo") or "").startswith("up-"):
                    raise TemplateError("%s: person %d needs a photo" % (f["label"], i))
                if p["photo"] in photos:
                    raise TemplateError("%s: person %d's photo is used twice" % (f["label"], i))
                photos.add(p["photo"])
                row = {"photo": p["photo"]}
                for item in f.get("item") or ():
                    if p.get(item["key"]):
                        row[item["key"]] = _text(p[item["key"]], item)
                rows.append(row)
            named = sum(1 for r in rows if r.get("name"))
            need = int((f.get("featured") or {}).get("min") or 0)
            if named < need:
                raise TemplateError(
                    "%s: give at least %d of them a name (the featured)" % (f["label"], need)
                )
            out[k] = rows
        else:
            raise TemplateError("%s: a field of an unknown kind" % f["label"])
    return out


def upload_ids(t, clean):
    """Every upload the form names, in order: the pictures, then each person's photo."""
    ids = []
    for f in t["fields"]:
        v = clean.get(f["key"])
        if f["kind"] in ("image", "logo") and v:
            ids.append(v)
        elif f["kind"] == "people" and v:
            ids += [p["photo"] for p in v]
    return ids


def _set(obj, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        obj = obj.setdefault(p, {})
    obj[parts[-1]] = value


def _get(obj, path):
    for p in path.split("."):
        if not isinstance(obj, dict) or p not in obj:
            return None
        obj = obj[p]
    return obj


def build_content(t, clean):
    """content.json for a film from this template and the person's form: the sample's parts the
    template keeps (its UI words), then every field at its path. A picture is named by the image
    key the film draws it with ("logo", "sp-3"); the files come from seed(). Returns (content,
    pictures): {image key: upload id}."""
    sample = _read(os.path.join(t["_dir"], "content.sample.json"), {})
    content = {k: json.loads(json.dumps(sample[k])) for k in t.get("keep") or () if k in sample}
    pictures = {}
    for f in t["fields"]:
        v, kind, path = clean.get(f["key"]), f["kind"], f.get("path")
        if v is None or not (path or f.get("paths")):
            continue
        if kind == "daterange":
            short, long_, year = dates_words(v["from"], v["to"])
            for key, val in (("short", short), ("long", long_), ("year", year)):
                if (f.get("paths") or {}).get(key):
                    _set(content, f["paths"][key], val)
        elif kind == "logo":
            pictures["logo"] = v
            _set(content, path, {"image": "logo", "light": "logo-light"})
        elif kind == "image":
            key = f.get("image") or f["key"]
            pictures[key] = v
            _set(content, path, key)
        elif kind == "people":
            rows = []
            for i, p in enumerate(v, 1):
                key = "sp-%d" % i
                pictures[key] = p["photo"]
                rows.append({k: p[k] for k in ("name", "role", "org") if p.get(k)} | {"image": key})
            _set(content, path, rows)
        else:
            _set(content, path, v)
    # a field left empty that has a default takes it (the button's words)
    for f in t["fields"]:
        if f.get("default") is not None and f.get("path") and _get(content, f["path"]) is None:
            _set(content, f["path"], f["default"])
    # what the film can work out when the form leaves it out (the template's "derive")
    for path, how in (t.get("derive") or {}).items():
        if _get(content, path) is None:
            src = _get(content, how["from"])
            if isinstance(src, str):
                val = src[: how["first"]] if how.get("first") else src
                _set(content, path, val.upper() if how.get("upper") else val)
    return content, pictures


# ------------------------------------------------------------------ a logo on dark and on light
def logo_variants(src, out_dir):
    """The logo as two transparent PNGs: logo.png for a light ground (the opening's card) and
    logo-light.png for a dark one (the pass, the poster). A picture with no transparency has its
    flat background keyed out first; whichever of the two the logo is not, is made as a
    silhouette. Returns their paths."""
    from PIL import Image  # noqa: PLC0415 -- only a template film's seed needs it
    import numpy as np  # noqa: PLC0415

    im = Image.open(src).convert("RGBA")
    im.thumbnail((1600, 1600))
    a = np.asarray(im).astype(np.float32)
    if a[..., 3].min() > 250:  # no transparency: key out the colour of its border
        edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])[:, :3]
        bg = np.median(edge, axis=0)
        dist = np.abs(a[..., :3] - bg).max(axis=2)
        a[..., 3] = np.clip((dist - 18) * 12, 0, 255)
    rgb, alpha = a[..., :3], a[..., 3] / 255
    lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) / 255
    mean = float((lum * alpha).sum() / max(1.0, alpha.sum()))
    base = np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8)
    os.makedirs(out_dir, exist_ok=True)

    def silhouette(rgb_hex):
        c = [int(rgb_hex[i : i + 2], 16) for i in (1, 3, 5)]
        s = np.zeros_like(base)
        s[..., :3], s[..., 3] = c, base[..., 3]
        return Image.fromarray(s, "RGBA")

    dark_logo = mean < 0.55
    p_light, p_dark = os.path.join(out_dir, "logo.png"), os.path.join(out_dir, "logo-light.png")
    if dark_logo:  # reads on the card as it is; a light silhouette for the dark grounds
        Image.fromarray(base, "RGBA").save(p_light)
        silhouette("#F4F1EC").save(p_dark)
    else:
        silhouette("#0C1439").save(p_light)
        Image.fromarray(base, "RGBA").save(p_dark)
    return p_light, p_dark


# ------------------------------------------------------------------ a film made from one
def seed(film, t, content, files):
    """Lay the template into a new film's folder (Film.create made it, template=t): its code as
    the film's own starting code, the person's content, their pictures, and a read-only template/
    folder to compare against. files: {image key: upload meta with "src"}. The film's score and
    cues are written from its own code before Claude starts (agent.template_ready)."""
    d = t["_dir"]
    shutil.copyfile(os.path.join(d, "film.js"), film.path("film.js"))
    _write_json(film.path("content.json"), content)
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    images = m.setdefault("images", {})
    people = []
    for key, meta in files.items():
        if key == "logo":
            p1, p2 = logo_variants(meta["src"], film.path("images"))
            images["logo"] = os.path.relpath(p1, film.dir).replace("\\", "/")
            images["logo-light"] = os.path.relpath(p2, film.dir).replace("\\", "/")
        elif key.startswith("sp-"):
            os.makedirs(film.path("inputs", "people"), exist_ok=True)
            rel = "inputs/people/%s.%s" % (key, meta["ext"])
            shutil.copyfile(meta["src"], film.path(*rel.split("/")))
            people.append({"key": key, "photo": rel})
            images[key] = "images/people/%s.webp" % key  # cut out before Claude starts
        else:
            rel = "inputs/%s.%s" % (key, meta["ext"])
            os.makedirs(film.path("inputs"), exist_ok=True)
            shutil.copyfile(meta["src"], film.path(*rel.split("/")))
            images[key] = rel
    _write_json(film.manifest, m)
    ref = film.path("template")
    os.makedirs(ref, exist_ok=True)
    _write_json(os.path.join(ref, "template.json"), public(t) | {"brief": t.get("brief", "")})
    shutil.copyfile(
        os.path.join(d, "content.sample.json"), os.path.join(ref, "content.sample.json")
    )
    frame = frame_name(m)
    have = frame if frame in t["frames"] else t["frames"][0]
    sheet = os.path.join(d, "preview", fdir(have), "sheet.png")
    if os.path.exists(sheet):
        shutil.copyfile(sheet, os.path.join(ref, "sheet.png"))
    film.update(people_cutouts=people)
    return people


def fdir(frame):
    """A frame's folder name (16x9): a colon is no part of a Windows path."""
    return frame.replace(":", "x")


def frame_name(m):
    w, h = (m.get("frame") or [1920, 1080])[:2]
    return next((k for k, v in FRAMES.items() if v == [w, h]), "16:9")


def cut_list(film):
    """The people photos still to cut out, [(key, photo path, out path)], after taking every one
    this machine has cut before from the cache (cache/cutouts/<sha256>.webp: the same photo,
    model and settings always cut the same)."""
    t = film.record().get("template") or {}
    spec = (load(t.get("id"), t.get("version"), ("live", "draft")) or {}).get("portraits") or {}
    todo = []
    cache = os.path.join(HOME, "cache", "cutouts")
    os.makedirs(film.path("images", "people"), exist_ok=True)
    for p in film.record().get("people_cutouts") or []:
        src = film.path(*p["photo"].split("/"))
        out = film.path("images", "people", p["key"] + ".webp")
        if os.path.exists(out):
            continue
        with open(src, "rb") as f:
            key = hashlib.sha256(f.read() + json.dumps(spec, sort_keys=True).encode()).hexdigest()
        hit = os.path.join(cache, key + ".webp")
        if os.path.exists(hit):
            shutil.copyfile(hit, out)
        else:
            todo.append((p["key"], src, out, hit))
    return todo, spec


def cut_args(spec):
    """portrait-cutout.py's settings for a template's people (its "portraits")."""
    args = []
    if spec.get("frame", True):
        args.append("--frame")
    if spec.get("tone"):
        args += ["--tone", spec["tone"]]
    if spec.get("px"):
        args += ["--px", str(int(spec["px"]))]
    return args


def ask(film):
    """The first message of a film made from a template: what it is, what stays, what changes,
    what the person gave -- instead of the narration and the prompt a film of its own gets."""
    rec = film.record()
    tr = rec.get("template") or {}
    t = load(tr.get("id"), tr.get("version"), ("live", "draft", "retired")) or {}
    from film import limits  # noqa: PLC0415

    n = film.length
    given = rec.get("fields") or {}
    shown = {
        k: (
            "(a picture: %s)" % ("images/logo.png" if k == "logo" else "their upload")
            if isinstance(v, str) and v.startswith("up-")
            else [{kk: vv for kk, vv in p.items() if kk != "photo"} for p in v]
            if isinstance(v, list) and v and isinstance(v[0], dict)
            else v
        )
        for k, v in given.items()
    }
    empty = [f["label"] for f in t.get("fields") or () if f["key"] not in given]
    lang = rec.get("language") or "en"
    parts = [
        'Make the film: a remake of the template "%s" with this person\'s own content.'
        % t.get("title", tr.get("id")),
        "Length: %d seconds (fixed). No narration: the music carries it -- there is no vo.json "
        "and no voice tool. Your working time: about %d minutes (waiting for the machine is not "
        "counted)." % (n, limits(n)["claude_s"] // 60),
        "The template is a finished film. Its code is already your film.js, and its words, "
        "colours, logo and people are in content.json (SK.DATA.content), built from the person's "
        "form -- both are yours to edit. The film already runs with the new content: "
        "template/mine/sheet.png shows it at the template's own moments, and template/sheet.png "
        "shows the template as its author made it. Read both first.",
        "What stays: the scenes and their order, the camera, the motion and the clock (every time "
        "in film.js), the type, the colour roles and the sound. The sound is written by the film "
        "itself (SK.film({sound}): score() and sfx() work it out from the clock and the content); "
        "the studio writes score.json and sfx.json from it before the mix, so never write those "
        "two by hand -- change score()/sfx() in film.js if the sound must change.",
        "What changes: the content. Make it look as good with this content as the template looks "
        "with its own: fix what the new content breaks -- a name or a city too long for its place, "
        "a logo that reads badly on its ground, colours that clash or lose contrast, fewer people "
        "than a layout expects, another language. Change film.js only where the content needs it.",
        "Never show anything of the template's own sample (template/content.sample.json): none of "
        "its event, people, places, addresses or marks may appear in this film. The studio checks "
        "the code and stops the film while any of its words are left.",
        "Every word on screen comes from content.json or the person's form; invent no facts.",
        "The person's form:\n" + json.dumps(shown, ensure_ascii=False, indent=1),
    ]
    if empty:
        parts.append(
            "Left empty: %s. The film works these out or leaves them out (content.json shows "
            "what it has); do not invent them." % ", ".join(empty)
        )
    if lang != "en":
        parts.append(
            "The film is in %s: translate content.json's copy (the labels) into it, and keep "
            "names as given." % lang
        )
    if t.get("brief"):
        parts.append("The template's author on what makes it work:\n" + t["brief"].strip())
    parts.append(
        "When it is right, stop with one or two sentences: what you changed for this content."
    )
    return "\n\n".join(parts)


def _strings(content):
    """Every string in a content object, and the words of each."""
    out = []

    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(content)
    return out


def leftovers(film):
    """The template sample's own words still in the film's code or content: its event, people,
    places, addresses -- every string of the sample that the template's kept parts (the labels)
    do not also hold. [] when none."""
    t_ = film.record().get("template") or {}
    t = load(t_.get("id"), t_.get("version"), ("live", "draft", "retired"))
    if not t:
        return []
    sample = _read(os.path.join(t["_dir"], "content.sample.json"), {})
    kept = set(_strings({k: sample.get(k) for k in t.get("keep") or ()}))
    words = {
        s.strip()
        for s in _strings({k: v for k, v in sample.items() if k not in (t.get("keep") or ())})
        if len(s.strip()) >= 4 and s.strip() not in kept and not re.fullmatch(r"[\d\W_]+", s)
    }
    # an image key or a colour is not a word anyone reads
    words = {w for w in words if not re.fullmatch(r"#[0-9A-Fa-f]{6}|sp-[a-z0-9-]+|[a-z-]+", w)}
    mine = _read(film.path("content.json"), {})
    text = ""
    for name in ("film.js",):
        try:
            with open(film.path(name), encoding="utf-8") as f:
                text += f.read()
        except OSError:
            pass
    text += "\n" + json.dumps(mine, ensure_ascii=False)
    low = text.lower()
    # what the person's own form holds is theirs, even when it matches the sample (the same city)
    theirs = {s.lower() for s in _strings(film.record().get("fields") or {})}
    return sorted(w for w in words if w.lower() in low and w.lower() not in theirs)


def onscreen(film):
    """The words a film with no narration shows (its content.json's strings), for the writers of
    its title, description and share card (ytdraft, share) -- [] for other films."""
    c = _read(film.path("content.json"), None)
    if not isinstance(c, dict):
        return []
    keep = {"_about"}
    return [s for s in _strings({k: v for k, v in c.items() if k not in keep}) if len(s) > 1]


# ------------------------------------------------------------------ making a version
def _readonly(d):
    for top, _, names in os.walk(d):
        for n in names:
            p = os.path.join(top, n)
            os.chmod(p, os.stat(p).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def plan(folder, spec):
    """What make() would copy from a finished film or a project folder: [(from, to)]. Only the
    film's code, its sample content, the engine it ran on, and the pictures that content names."""
    m = _read(os.path.join(folder, "sketch.json"))
    if not m:
        raise TemplateError("%s has no sketch.json" % folder)
    content_rel = (m.get("data") or {}).get("content")
    if not content_rel:
        raise TemplateError('the film keeps no content in "data" -- it is not a template yet')
    out = [(os.path.join(folder, "film.js"), "film.js")]
    out.append((os.path.join(folder, content_rel), "content.sample.json"))
    eng = os.path.join(folder, m.get("engine") or "", "")
    for n in ENGINE + tuple(x + ".js" for x in m.get("modules") or ()):
        src = os.path.join(eng, n) if m.get("engine") else ""
        out.append(
            (src if src and os.path.exists(src) else os.path.join(KIT, "sketch", n), "engine/" + n)
        )
    sample = _read(os.path.join(folder, content_rel), {})
    # the pictures the sample names: any of its strings that is one of the manifest's images
    named = {x for x in _strings(sample) if x in (m.get("images") or {})}
    for key in sorted(named):
        rel = m["images"][key]
        ext = os.path.splitext(rel)[1]
        out.append((os.path.join(folder, rel), "sample/%s%s" % (key, ext)))
    for src, _ in out:
        if not os.path.isfile(src):
            raise TemplateError("missing: %s" % src)
    return out


def make(folder, tid, spec, owner="kitcut"):
    """A new version of template tid from a finished film's folder (or a project's), as a draft:
    the files plan() lists, template.json from spec, and the preview stills per frame. Returns
    its folder."""
    if not ID.match(tid):
        raise TemplateError("a template id is t- and a slug: %r" % tid)
    files = plan(folder, spec)
    m = _read(os.path.join(folder, "sketch.json"))
    for f in spec.get("fields") or ():
        if f.get("kind") not in KINDS:
            raise TemplateError("field %s: kind is one of %s" % (f.get("key"), ", ".join(KINDS)))
    frames = spec.get("frames") or ["16:9"]
    if any(fr not in FRAMES for fr in frames):
        raise TemplateError("frames are among %s" % ", ".join(FRAMES))
    idx = index(tid)
    v = int(idx.get("latest") or 0) + 1
    d = vdir(tid, v)
    os.makedirs(d)
    for src, rel in files:
        dst = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    sample_images = (
        {
            os.path.splitext(n)[0]: "sample/" + n
            for n in sorted(os.listdir(os.path.join(d, "sample")))
        }
        if os.path.isdir(os.path.join(d, "sample"))
        else {}
    )
    keep_keys = ("fonts", "player", "audio", "render", "poster_t", "fps", "modules")
    man = {k: m[k] for k in keep_keys if k in m}
    man.update(
        title=spec.get("title") or m.get("title"),
        slug="template",
        duration=float(m["duration"]),
        film="film.js",
        engine="engine",
        data={"content": "content.sample.json"},
        images=sample_images,
    )
    _write_json(os.path.join(d, "sketch.json"), man)
    t = {
        "id": tid,
        "version": v,
        "title": spec["title"],
        "description": spec.get("description", ""),
        "author": spec.get("author") or owner,
        "source_film": spec.get("source_film"),
        "release": RELEASE,
        "created": datetime.now().isoformat(timespec="seconds"),
        "seconds": round(float(m["duration"])),
        "fps": m.get("fps", 60),
        "frames": frames,
        "look": spec.get("look", "drawn"),
        "caps": spec.get("caps") or [],
        "narration": False,
        "moments": spec.get("moments") or [],
        "limits": spec.get("limits") or {"images": 32},
        "portraits": spec.get("portraits") or {},
        "keep": spec.get("keep") or ["_about", "copy"],
        "derive": spec.get("derive") or {},
        "fields": spec["fields"],
        "brief": spec.get("brief", ""),
        "manifest": man,
    }
    _write_json(os.path.join(d, "template.json"), t)
    idx.setdefault("versions", {})[str(v)] = "draft"
    idx["latest"] = v
    os.makedirs(os.path.join(root(), tid), exist_ok=True)
    _write_json(os.path.join(root(), tid, "index.json"), idx)
    return d


def set_status(tid, v, status):
    """A version's status: draft, live or retired. A version folder copied in from another
    machine (ops.sh template push) joins the index here."""
    idx = index(tid)
    known = str(int(v)) in (idx.get("versions") or {})
    if not known and not os.path.isfile(os.path.join(vdir(tid, v), "template.json")):
        raise TemplateError("%s has no version %s" % (tid, v))
    idx.setdefault("versions", {})[str(int(v))] = status
    idx["latest"] = max(int(idx.get("latest") or 0), int(v))
    _write_json(os.path.join(root(), tid, "index.json"), idx)
    return idx


def _scratch(t, frame):
    """A working copy of a version to draw it from, with its manifest in this frame: the renderer
    writes its bundle, temp and audio beside the manifest, and a version is read-only."""
    d = os.path.join(
        HOME,
        "cache",
        "template-render",
        "%s-v%d-%s" % (t["id"], t["version"], frame.replace(":", "x")),
    )
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(
        t["_dir"],
        d,
        ignore=shutil.ignore_patterns("preview", "outputs", "temp", "audio", "sketch*.json"),
    )
    for top, dirs, names in os.walk(d):  # the copy is ours to write, whatever the version's modes
        for n in dirs + names:
            os.chmod(
                os.path.join(top, n),
                stat.S_IWUSR | stat.S_IRUSR | (stat.S_IXUSR if n in dirs else 0),
            )
    p = os.path.join(d, "sketch.json")
    _write_json(p, dict(t["manifest"], frame=FRAMES[frame]))
    return d, p


def _render_stills(t, frame, into):
    """Stills of the version's sample at its moments in this frame, copied into `into` with their
    sheet. Raises TemplateError when the render fails."""
    import subprocess  # noqa: PLC0415

    import procs  # noqa: PLC0415

    d, manifest = _scratch(t, frame)
    argv = [procs.python(), "-X", "utf8", os.path.join(KIT, "scripts", "sketch-render.py")]
    argv += ["--manifest", manifest, "--stills", ",".join("%g" % x for x in t["moments"])]
    argv += ["--into", "stills", "--sheet"]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise TemplateError("the render failed:\n" + (r.stdout + r.stderr)[-2000:])
    shutil.rmtree(into, ignore_errors=True)
    shutil.copytree(os.path.join(d, "stills"), into)
    shutil.rmtree(d, ignore_errors=True)


def preview(tid, v):
    """Stills of the sample at the template's moments, per frame: preview/<frame>/, the sheet the
    site and the remakes are shown, and what check() compares against."""
    t = load(tid, v, ("draft",))
    if not t:
        raise TemplateError("%s v%s is not a draft" % (tid, v))
    for fr in t["frames"]:
        _render_stills(t, fr, os.path.join(t["_dir"], "preview", fdir(fr)))
    return t


def _ssim(a, b):
    import numpy as np  # noqa: PLC0415
    import cv2  # noqa: PLC0415

    x, y = (np.asarray(i, dtype=np.float64) for i in (a, b))
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda z: cv2.GaussianBlur(z, (11, 11), 1.5)  # noqa: E731
    mx, my = blur(x), blur(y)
    sxx, syy, sxy = blur(x * x) - mx * mx, blur(y * y) - my * my, blur(x * y) - mx * my
    return float(
        (
            ((2 * mx * my + c1) * (2 * sxy + c2)) / ((mx * mx + my * my + c1) * (sxx + syy + c2))
        ).mean()
    )


def check(tid=None, bar=0.99):
    """Draw every live (and draft) version's sample with this release's renderer and compare it
    to its preview: [(template, version, frame, worst SSIM, the moment)] of those under bar."""
    from PIL import Image  # noqa: PLC0415

    bad = []
    names = (
        [tid]
        if tid
        else sorted(n for n in os.listdir(root()) if ID.match(n))
        if os.path.isdir(root())
        else []
    )
    for name in names:
        for v, s in (index(name).get("versions") or {}).items():
            if s not in ("live", "draft"):
                continue
            t = load(name, int(v), (s,))
            for fr in t["frames"]:
                was = os.path.join(t["_dir"], "preview", fdir(fr))
                if not os.path.isdir(was):
                    continue
                into = os.path.join(HOME, "cache", "template-check", name, v, fdir(fr))
                _render_stills(t, fr, into)
                worst = (2.0, 0.0)
                for m_ in t["moments"]:
                    n = "%06.2f.png" % m_
                    a = (
                        Image.open(os.path.join(was, n))
                        .convert("L")
                        .resize((480, 270 if fr == "16:9" else 480))
                    )
                    b = Image.open(os.path.join(into, n)).convert("L").resize(a.size)
                    worst = min(worst, (_ssim(a, b), m_))
                print("  %s v%s %s: worst SSIM %.4f at %s s" % (name, v, fr, worst[0], worst[1]))
                if worst[0] < bar:
                    bad.append((name, int(v), fr, worst[0], worst[1]))
    return bad


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="a new draft version from a finished film or project folder")
    mk.add_argument("--folder", help="the film's folder (a project's, or STUDIO_HOME's)")
    mk.add_argument("--film", help="a studio film id (its folder under STUDIO_HOME/projects)")
    mk.add_argument("--id", required=True)
    mk.add_argument("--spec", required=True, help="template.json's fields, title, brief...")
    mk.add_argument("--plan", action="store_true", help="list what would be copied; copy nothing")
    ck = sub.add_parser("check", help="re-draw the samples with this release; compare")
    ck.add_argument("--id")
    for name in ("publish", "retire", "draft"):
        p = sub.add_parser(name)
        p.add_argument("id")
        p.add_argument("version", type=int)
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "make":
        folder = a.folder or os.path.join(HOME, "projects", a.film or "")
        with open(a.spec, encoding="utf-8") as f:
            spec = json.load(f)
        files = plan(folder, spec)
        for src, rel in files:
            print("  %-28s <- %s" % (rel, os.path.relpath(src)))
        if a.plan:
            print("\n  --plan: nothing copied")
            return
        d = make(folder, a.id, spec)
        v = int(os.path.basename(d)[1:])
        print("  made %s v%d (draft) in %s; drawing its preview..." % (a.id, v, d))
        preview(a.id, v)
        _readonly(d)
        print("  preview: %s" % os.path.join(d, "preview"))
    elif a.cmd == "check":
        bad = check(a.id)
        if bad:
            sys.exit("templates drawn differently by this release: %s" % bad)
        print("  every template draws as it did")
    elif a.cmd in ("publish", "retire", "draft"):
        status = {"publish": "live", "retire": "retired", "draft": "draft"}[a.cmd]
        print(json.dumps(set_status(a.id, a.version, status), indent=1))
    else:
        for n in sorted(os.listdir(root())) if os.path.isdir(root()) else []:
            if ID.match(n):
                print("  %s  %s" % (n, json.dumps(index(n).get("versions"))))


if __name__ == "__main__":
    main()
