"""Templates: a finished film that others remake with their own content (kitcut.ai's templates).

    STUDIO_HOME\\templates\\<id>\\
        index.json                  {"latest": N, "versions": {"N": "draft"|"live"|"retired"}}
        v<N>\\                      read-only once built (make): a version never changes
            template.json           what it is, an example of what to ask, its author's brief
            film.js                 the film's code; it reads its words and people from
                                    content.json (SK.DATA.content) and writes its own sound
            content.sample.json     the author's content: the preview's, never seeded
            engine\\*.js            the engine it was drawn with, frozen
            sample\\                the sample's pictures (its logo, its people): the preview and
                                    the health check only, never seeded
            sketch.json             the preview's manifest (the sample, the frozen engine)
            preview\\<frame>\\       stills at its moments and their sheet, per frame

A template is an example, not a form: a film made from one starts from the template's own code
and its sample content (seed), and the person says what they want in their own words, with
whatever they attach -- an event's name, its website, its speakers, or anything else to change.
Claude remakes the film for that (ask): what they ask to change it changes, what they do not
mention it keeps, and what it needs it finds -- in their words and pictures, and on the web when
it decides to. Pictures become the film's own with the template_pictures tool (a logo on dark and
light grounds, people cut out of their photos: cut_people). leftovers() names any of the sample's
own words still in the film, which stops the final render. A film never gets the author's
conversation, uploads, voice or project: make() copies only what is listed here.

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


class TemplateError(ValueError):
    pass


# ------------------------------------------------------------------ where they are
def root():
    """Where the templates live: STUDIO_HOME/templates, or STUDIO_TEMPLATES (a bake-off's films
    each have a home of their own, and are all made from one folder of templates)."""
    return os.environ.get("STUDIO_TEMPLATES") or os.path.join(HOME, "templates")


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
            "example",
            "moments",
            "limits",  # how many pictures a film from it may take: the site's prompt box says so
        )
    }


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
def seed(film, t):
    """Lay the template into a new film's folder (Film.create made it, template=t): its code as the
    film's own starting code, its sample content as content.json (the starting point Claude
    remakes), and a read-only template/ folder to compare against: what the template is, its
    sample, its sheet in the film's frame."""
    d = t["_dir"]
    shutil.copyfile(os.path.join(d, "film.js"), film.path("film.js"))
    shutil.copyfile(os.path.join(d, "content.sample.json"), film.path("content.json"))
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
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
    # the sample's own pictures, for the film to draw until the person's replace them
    for name in (
        os.listdir(os.path.join(d, "sample")) if os.path.isdir(os.path.join(d, "sample")) else []
    ):
        os.makedirs(film.path("template", "sample"), exist_ok=True)
        shutil.copyfile(os.path.join(d, "sample", name), film.path("template", "sample", name))
        m.setdefault("images", {}).setdefault(os.path.splitext(name)[0], "template/sample/" + name)
    _write_json(film.manifest, m)


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
    """The first message of a film made from a template: what the person asked, what the template
    is, what to keep and what to find -- instead of the narration a film of its own gets. (Their
    attachments follow it: agent.attached_note.)"""
    rec = film.record()
    tr = rec.get("template") or {}
    t = load(tr.get("id"), tr.get("version"), ("live", "draft", "retired")) or {}
    from film import limits  # noqa: PLC0415

    n = film.length
    asked = (rec.get("prompt") or "").strip()
    parts = [
        'Make the film: the template "%s", remade for what this person asks.'
        % t.get("title", tr.get("id")),
        "Length: %d seconds (fixed). No narration: the music carries it -- there is no vo.json "
        "and no voice tool. Your working time: about %d minutes (waiting for the machine is not "
        "counted)." % (n, limits(n)["claude_s"] // 60),
        "What they asked:\n<<<\n%s\n>>>"
        % (asked or "(nothing typed: what they want is in what they attached)"),
        "The template is a finished film -- an example, not a form. Its code is already your "
        "film.js, and its words, colours, logo and people are in content.json "
        "(SK.DATA.content) -- for now still the template's own sample, which template/sheet.png "
        "shows. Both are yours to edit.",
        "Do what they ask. Whatever they ask to change, change: the content, and the film itself "
        "where they want something different. Whatever they do not mention, keep as the template "
        "has it: its scenes and their order, the camera, the motion and the clock, the type, the "
        "colour roles and the sound. The sound is written by the film itself (SK.film({sound}): "
        "score() and sfx() work it out from the clock and the content); the studio writes "
        "score.json and sfx.json from it before the mix, so never write those two by hand.",
        "Find what the film needs yourself. Their words and what they attached come first. For "
        "the rest -- whatever the film shows that they did not give: names, dates, places, people "
        "and their photos, a logo and colours -- look it up when it exists (WebSearch, WebFetch, "
        "the page and picture tools); whether that is needed is yours to decide. Never invent a "
        "fact: what you cannot find, leave out, and say so at the end. Keep within what the "
        "film's places hold (the author's notes below say where they are tight).",
        "Pictures -- a logo, people's photos -- attached (upload1...) or brought in with the "
        "picture tool (web_...) become the film's own with template_pictures: it cuts the people "
        "out of their photos and makes the logo readable on dark and light grounds, and answers "
        "with the keys to put in content.json.",
        "Replace the whole sample: none of the template's own event, people, places, addresses, "
        "marks or pictures (template/content.sample.json) may stay unless they asked for them. "
        "The studio checks, and stops the film while any are left.",
        "Its words are in the language they ask for -- when they do not say, the one they wrote "
        "in -- names as they are, and every face the film draws them in must have their letters "
        "(a face without them falls back to the browser's own).",
    ]
    if t.get("brief"):
        parts.append("The template's author on what makes it work:\n" + t["brief"].strip())
    parts.append("When it is right, stop with one or two sentences: what you made of it.")
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
    do not also hold -- and its pictures still in the content. [] when none, and when the person
    asked for the sample's own event (its "identity", named in their words)."""
    rec = film.record()
    t_ = rec.get("template") or {}
    t = load(t_.get("id"), t_.get("version"), ("live", "draft", "retired"))
    if not t:
        return []
    sample = _read(os.path.join(t["_dir"], "content.sample.json"), {})
    asked = (rec.get("prompt") or "").lower()
    for path in t.get("identity") or ():
        v = sample
        for k in path.split("."):
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, str) and len(v) >= 3 and v.lower() in asked:
            return []
    kept = set(_strings({k: sample.get(k) for k in t.get("keep") or ()}))
    # the template's own words for everyone ("BOOK TICKETS"), not the sample's
    kept |= set(t.get("generic") or ())
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
    mine = json.dumps(mine, ensure_ascii=False)
    low = (text + "\n" + mine).lower()
    # a word the person asked for is theirs, even when the sample has it (the same city)
    left = sorted(w for w in words if w.lower() in low and w.lower() not in asked)
    # the sample's pictures (its logo, its people) are seeded for a first draw, never to stay: a key
    # still pointing at template/sample/ -- the same key made the film's own ("logo", by
    # template_pictures) is the person's picture
    pics = (t.get("manifest") or {}).get("images") or {}
    have = (_read(film.manifest, {}) or {}).get("images") or {}
    return left + sorted(
        "the picture %s" % k
        for k in pics
        if '"%s"' % k in mine and str(have.get(k, "template/")).startswith("template/")
    )


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
        "example": spec.get("example", ""),
        "generic": spec.get("generic") or [],
        "identity": spec.get("identity") or [],
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
    mk.add_argument(
        "--spec", required=True, help="the template's spec: title, example, brief, keep..."
    )
    mk.add_argument("--plan", action="store_true", help="list what would be copied; copy nothing")
    ck = sub.add_parser("check", help="re-draw the samples with this release; compare")
    ck.add_argument("--id")
    for name in ("publish", "retire", "draft"):
        p = sub.add_parser(name)
        p.add_argument("id")
        p.add_argument("version", type=int)
    pv = sub.add_parser("preview", help="draw a draft's preview again with this machine's renderer")
    pv.add_argument("id")
    pv.add_argument("version", type=int)
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
    elif a.cmd == "preview":  # a version copied in from another machine is drawn here first
        preview(a.id, a.version)
        print("  preview: %s" % os.path.join(vdir(a.id, a.version), "preview"))
    elif a.cmd in ("publish", "retire", "draft"):
        status = {"publish": "live", "retire": "retired", "draft": "draft"}[a.cmd]
        print(json.dumps(set_status(a.id, a.version, status), indent=1))
    else:
        for n in sorted(os.listdir(root())) if os.path.isdir(root()) else []:
            if ID.match(n):
                print("  %s  %s" % (n, json.dumps(index(n).get("versions"))))


if __name__ == "__main__":
    main()
