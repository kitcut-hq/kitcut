"""A finished kitcut.ai film made into a template, stage by stage, and a template proved by a film.

kitcut.ai's templates (studio/templates.py) are finished films others remake. Turning one film into
a template used to be an afternoon of hand work in two repos; this is that work as commands, each a
stage you can run again, and each with --plan to say what it would do and change nothing:

    pull   the film from the studio VM into projects/<slug>/: its code, cast, engine, narration and
           sound, the pictures its code draws, its manifest without the closing brand; its facts
           moved into content.json when the film keeps them in one object at the top of film.js
           (const FACTS = {...}, as the studio's brief asks since 2026-10-02) -- else it writes the
           brief for the refactor (temp/refactor-brief.md) for an agent to do by hand
    prove  the template draws the film it was made from: stills of both at the same moments,
           compared pixel by pixel (the bar: no more than 2 levels off anywhere)
    alt    stills with other content (a made-up party, a longer name) -- for reading by eye
    check  the sample's own words left in the code (the studio's leftovers check would stop every
           remake on them): film.js and cast/ must say nothing of the sample
    spec   the two specs, filled from the film: the studio's (config/templates/<slug>.json) and the
           site's (<site>/specs/templates/<slug>.json); what only a person can write is listed
    make   templates.py make in a scratch home (temp/studio-home), the preview drawn; --push puts
           it on the VM as a draft and --publish makes it live
    site   the site's template from its spec: created (or updated), --publish to make it public
    test   a film made from the live template on the VM from one sentence, pulled and graded
           blind (bakeoff's grader: how professional it looks; how closely it keeps the template),
           with a sheet to look at. It passes at professional >= 4 and fidelity >= 4 -- the bar
           the conference templates met -- and fails loudly otherwise: a template is not done
           until a stranger's sentence makes a good film from it

    find   someone's films on kitcut.ai by their email (the site's prod.mjs films)

The order, and what is a person's (the film-to-template skill walks it):
    find -> pull -> (refactor by an agent if pull asked for one) -> prove -> alt -> check -> spec
    -> (write the brief, the example, the page's words) -> make --push --publish -> site
    --publish -> test (twice: words only, and words with pictures)

Invoke as:
    python studio/template_from_film.py find <email>
    python studio/template_from_film.py pull <film-id> --slug <slug> [--facts FACTS] [--plan]
    python studio/template_from_film.py prove --slug <slug> [--times 1,5,9]
    python studio/template_from_film.py alt --slug <slug> --content <content.alt.json>
    python studio/template_from_film.py check --slug <slug>
    python studio/template_from_film.py spec --slug <slug> [--site ../sketch-studio]
    python studio/template_from_film.py make --slug <slug> [--push] [--publish]
    python studio/template_from_film.py site --slug <slug> [--site ../sketch-studio] [--publish]
    python studio/template_from_film.py test --slug <slug> --prompt "<a sentence>" [--attach f]
"""

import os
import re
import sys
import json
import shutil
import argparse
import subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(KIT, "scripts"))
import _env  # noqa: E402, F401 -- re-execs into .venv; before any 3rd-party import

sys.path.insert(0, HERE)
OPS = os.path.join(HERE, "deploy", "ops.sh")
PULLED = os.path.join(KIT, "temp", "vm-films")
SCRATCH = os.path.join(KIT, "temp", "studio-home")
OWNER = "alex@botmakers.net"  # the account KitCut's own templates and test films belong to
SITE_URL = "https://kitcut.ai"
BAR = {"professional": 4, "fidelity": 4}  # a test film's blind grades a template must reach
PROVE_LEVELS = 2  # a still of the template may differ from the film's by this much (render noise)
FACT_NAMES = ("FACTS", "EVENT", "CONTENT", "PARTY", "DATA")


class Stop(Exception):
    pass


def say(*a):
    print(*a, flush=True)


def read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, d):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")


def project(slug):
    return os.path.join(KIT, "projects", slug)


def bash(*args, check=True):
    """ops.sh through Git Bash on Windows (it is a bash script), plain bash elsewhere."""
    git_bash = os.path.join(os.environ.get("ProgramFiles", ""), "Git", "bin", "bash.exe")
    # not WSL's System32 bash, which shutil.which finds first on Windows
    exe = git_bash if os.path.isfile(git_bash) else shutil.which("bash") or "bash"
    args = [x.replace("\\", "/") if os.path.isabs(x) else x for x in args]
    r = subprocess.run(
        [exe, OPS.replace("\\", "/"), *args], capture_output=True, text=True, encoding="utf-8"
    )
    if check and r.returncode != 0:
        raise Stop("ops.sh %s failed:\n%s" % (" ".join(args), (r.stdout + r.stderr)[-1500:]))
    return r.stdout


def render(manifest, times, into, sheet=True):
    argv = [sys.executable, os.path.join(KIT, "scripts", "sketch-render.py"), "--manifest"]
    argv += [manifest, "--stills", ",".join("%g" % t for t in times), "--into", into]
    r = subprocess.run(argv + (["--sheet"] if sheet else []), capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop("sketch-render failed:\n" + (r.stdout + r.stderr)[-1500:])
    return os.path.join(os.path.dirname(manifest), into)


# ------------------------------------------------------------------ the facts object in film.js
def find_object(code, names=FACT_NAMES):
    """(name, start, end) of the first `const NAME = {...};` among names: the literal's span,
    braces balanced and strings and comments skipped. None when the film keeps no such object."""
    for name in names:
        m = re.search(r"\bconst\s+%s\s*=\s*\{" % re.escape(name), code)
        if not m:
            continue
        i, depth, quote = m.end() - 1, 0, None
        while i < len(code):
            ch = code[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "'\"`":
                quote = ch
            elif code.startswith("//", i):
                i = code.find("\n", i)
                if i < 0:
                    return None
            elif code.startswith("/*", i):
                i = code.find("*/", i) + 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return name, m.end() - 1, i + 1
            i += 1
    return None


def object_json(literal):
    """A plain-data JS object literal as a Python dict, through node: the literal is evaluated on
    its own, so one that reads anything but its own values fails here rather than in a remake."""
    node = shutil.which("node")
    if not node:
        raise Stop("node is not installed: it reads the film's facts object")
    r = subprocess.run(
        [node, "-e", "process.stdout.write(JSON.stringify((%s)))" % literal],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        raise Stop("the facts object is not plain data:\n" + r.stderr[-800:])
    return json.loads(r.stdout)


def strings(x, out=None):
    out = [] if out is None else out
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for v in x.values():
            strings(v, out)
    elif isinstance(x, list):
        for v in x:
            strings(v, out)
    return out


def rename_values(x, old, new):
    if isinstance(x, str):
        return new if x == old else x
    if isinstance(x, dict):
        return {k: rename_values(v, old, new) for k, v in x.items()}
    if isinstance(x, list):
        return [rename_values(v, old, new) for v in x]
    return x


REFACTOR_BRIEF = """Make this finished kitcut.ai film template-ready, in {proj} (a copy of the film; the
original is {src}, never write there). Work only in {proj}.

1. Move every fact of the sample into content.json, read as SK.DATA.content (the manifest already
   says "data": {{"content": "content.json"}}): names, people, ages, places, addresses, dates,
   times, links, hashtags, the headline words, the pictures' keys, and the palette if it is
   cleanly separable. Atomic fields (child: {{name, age, photo}}, when: {{date, time}} ...), so
   another sample is a data edit. Put a short "_about" at the top of content.json naming every
   field and its length limit. Generic words of the film's theme may stay in film.js.
2. film.js and cast/*.js must then hold NONE of the sample's words, in code or comments (the
   studio flags them in every remake). Rename cast members named after the sample generically.
   Comments should describe the film's structure (scenes, clock, which narration line each scene
   hangs on): the next Claude remaking it reads them.
3. Long names must be fitted (measured and scaled), never overflow; counts that vary (one host or
   three, two lines or five) must lay out.
4. Prove it: python studio/template_from_film.py prove --slug {slug}  (must say "same").
5. Write content.alt.json (other content: a long name, other counts, a missing optional field)
   and look at: python studio/template_from_film.py alt --slug {slug} --content content.alt.json
   Fix what breaks, then prove again.
6. python studio/template_from_film.py check --slug {slug}  must find nothing.
Report the content.json schema, the prove numbers and what you fixed.
"""


# ------------------------------------------------------------------ find
def stage_find(a):
    """Someone's films on kitcut.ai, newest first, with their projects (the site's prod.mjs)."""
    site = os.path.abspath(a.site)
    argv = [shutil.which("node"), os.path.join(site, "scripts", "prod.mjs"), "films", a.film]
    if a.plan:
        say("would run: " + " ".join(argv))
        return
    r = subprocess.run(argv, cwd=site, capture_output=True, text=True, encoding="utf-8")
    say((r.stdout + r.stderr).strip())


# ------------------------------------------------------------------ pull
def stage_pull(a):
    src = os.path.join(PULLED, a.film)
    dst = project(a.slug)
    if a.plan:
        say("would pull %s (ops.sh pull --all) into %s" % (a.film, src))
        say(
            "would make %s: film.js, cast/, engine/, narration, sound, pictures, content.json" % dst
        )
        return
    if os.path.exists(dst) and not a.force:
        raise Stop("%s exists: --force to make it again (it is overwritten)" % dst)
    if not os.path.isfile(os.path.join(src, "sketch.json")):
        say("pulling %s from the VM..." % a.film)
        bash("pull", a.film, PULLED, "--all")
    m = read_json(os.path.join(src, "sketch.json"))
    rec = read_json(os.path.join(src, "studio.json"), {})
    if rec.get("state") not in (None, "done"):
        raise Stop("%s is %s, not done" % (a.film, rec.get("state")))
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    for name in ("film.js", "score.json", "sfx.json"):
        shutil.copyfile(os.path.join(src, name), os.path.join(dst, name))
    shutil.copytree(os.path.join(src, m.get("engine") or "engine"), os.path.join(dst, "engine"))
    if os.path.isdir(os.path.join(src, "cast")):
        shutil.copytree(os.path.join(src, "cast"), os.path.join(dst, "cast"))
    for fnt in m.get("fonts") or ():  # a face the film fetched for itself (web/fonts/...)
        f_src = os.path.join(src, *fnt["file"].split("/"))
        if os.path.isfile(f_src):
            os.makedirs(os.path.dirname(os.path.join(dst, *fnt["file"].split("/"))), exist_ok=True)
            shutil.copyfile(f_src, os.path.join(dst, *fnt["file"].split("/")))
    vo = read_json(os.path.join(src, "vo.json"), {}) or {}
    tl = os.path.join(src, "audio", "vo", "timeline.json")
    narrated = bool(vo.get("lines")) and os.path.isfile(tl)
    if vo.get("lines") and not narrated:
        raise Stop("its narration was never recorded (no timeline): not a template's source")
    if narrated:
        shutil.copyfile(os.path.join(src, "vo.json"), os.path.join(dst, "vo.json"))
        os.makedirs(os.path.join(dst, "audio", "vo"))
        shutil.copyfile(tl, os.path.join(dst, "audio", "vo", "timeline.json"))
    code = open(os.path.join(dst, "film.js"), encoding="utf-8").read()
    cast_code = ""
    for n in (
        sorted(os.listdir(os.path.join(dst, "cast")))
        if os.path.isdir(os.path.join(dst, "cast"))
        else []
    ):
        cast_code += open(os.path.join(dst, "cast", n), encoding="utf-8").read()
    # the facts: one object at the top of film.js becomes content.json
    names = (a.facts,) if a.facts else FACT_NAMES
    found = find_object(code, names)
    content = None
    if found:
        name, s, e = found
        content = object_json(code[s:e])
    # the pictures the film draws: those its code or its facts name; an attached one (upload1)
    # is renamed sample1..., so a remake's own upload1 never takes its place by accident
    images, keep = m.get("images") or {}, {}
    said = code + cast_code + json.dumps(content or {})
    bare = (code[: found[1]] + code[found[2] :] if found else code) + cast_code  # outside the facts
    for key, rel in images.items():
        if not re.search(r"['\"`]%s['\"`]" % re.escape(key), said):
            continue
        new = key
        if re.fullmatch(r"upload\d+", key):
            new = "sample" + key[len("upload") :]
            if content is not None:
                content = rename_values(content, key, new)
            if re.search(r"['\"`]%s['\"`]" % re.escape(key), bare):
                say("  note: the code itself names %r: renamed there too" % key)
            code = re.sub(r"(['\"`])%s\1" % re.escape(key), r"\g<1>%s\1" % new, code)
        ext = os.path.splitext(rel)[1]
        os.makedirs(os.path.join(dst, "inputs"), exist_ok=True)
        shutil.copyfile(os.path.join(src, *rel.split("/")), os.path.join(dst, "inputs", new + ext))
        keep[new] = "inputs/%s%s" % (new, ext)
    if found:
        code = code[: found[1]] + "SK.DATA.content" + code[found[2] :]
        content = {
            "_about": "The sample's facts (%s): every field the film draws." % a.film
        } | content
        write_json(os.path.join(dst, "content.json"), content)
    with open(os.path.join(dst, "film.js"), "w", encoding="utf-8") as f:
        f.write(code)
    man = {k: v for k, v in m.items() if k not in ("tail", "images")}
    man.update(title=a.slug.replace("-", " ").capitalize(), images=keep)
    man["data"] = dict(man.get("data") or {}, content="content.json")
    if not narrated:
        man.pop("vo", None)
        man.pop("captions", None)
    write_json(os.path.join(dst, "sketch.json"), man)
    write_json(
        os.path.join(dst, "template-source.json"),
        {
            "film": a.film,
            "pulled": src,
            "narrated": narrated,
            "facts": found[0] if found else None,
            "look": rec.get("look"),
            "caps": rec.get("caps"),
            "prompt": rec.get("prompt"),
            "when": datetime.now().isoformat(timespec="seconds"),
        },
    )
    say(
        "made %s (%s, %s)"
        % (dst, "narrated" if narrated else "music only", ", ".join(keep) or "no pictures")
    )
    if found:
        say(
            "  facts: const %s -> content.json (%d strings); film.js reads SK.DATA.content"
            % (found[0], len(strings(content)))
        )
        say("  next: prove --slug %s" % a.slug)
    else:
        brief = os.path.join(dst, "temp", "refactor-brief.md")
        os.makedirs(os.path.dirname(brief), exist_ok=True)
        with open(brief, "w", encoding="utf-8") as f:
            f.write(REFACTOR_BRIEF.format(proj=dst, src=src, slug=a.slug))
        write_json(os.path.join(dst, "content.json"), {"_about": "to fill: the refactor"})
        say("  the film keeps its facts in its code: hand %s to an agent (the refactor)" % brief)


# ------------------------------------------------------------------ prove / alt / check
def moments(slug, src=None):
    """The source film's own review moments, else 12 spread over its length."""
    srcinfo = read_json(os.path.join(project(slug), "template-source.json"), {})
    review = os.path.join(src or srcinfo.get("pulled") or "", "outputs", "review")
    got = (
        sorted({float(n[:-4]) for n in os.listdir(review) if re.fullmatch(r"\d+\.\d+\.png", n)})
        if os.path.isdir(review)
        else []
    )
    if len(got) >= 6:
        return got
    dur = float(read_json(os.path.join(project(slug), "sketch.json"))["duration"])
    return [round((i + 0.5) * dur / 12, 2) for i in range(12)]


def preview_moments(slug, n=12):
    """The preview's moments: the film's review moments past its first second, none closer than a
    second to the one before (the studio retakes a moment it fixed: 19.6 and 19.8), at most n."""
    picked = []
    for t in moments(slug):
        if t >= 1.0 and (not picked or t - picked[-1] >= 1.0):
            picked.append(t)
    if len(picked) > n:
        picked = [picked[round(i * (len(picked) - 1) / (n - 1))] for i in range(n)]
    return picked


def diff(a_png, b_png):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    a = np.asarray(Image.open(a_png).convert("RGB")).astype(int)
    b = np.asarray(Image.open(b_png).convert("RGB")).astype(int)
    if a.shape != b.shape:
        return 255, 100.0
    d = np.abs(a - b)
    return int(d.max()), float((d.max(axis=2) > 0).mean() * 100)


def stage_prove(a):
    info = read_json(os.path.join(project(a.slug), "template-source.json"))
    if not info:
        raise Stop("no template-source.json in %s: pull first" % project(a.slug))
    times = [float(x) for x in a.times.split(",")] if a.times else moments(a.slug)
    if a.plan:
        say("would draw the film and the template at %s and compare them" % times)
        return
    src = info["pulled"]
    m = read_json(os.path.join(src, "sketch.json"))
    m.pop("tail", None)  # the film's closing brand is the studio's, not the template's
    orig = os.path.join(src, "sketch.prove.json")
    write_json(orig, m)
    say("drawing %d moments of the film and of the template..." % len(times))
    o = render(orig, times, "temp/prove-film", sheet=False)
    t = render(os.path.join(project(a.slug), "sketch.json"), times, "temp/prove-template")
    worst, rows = 0, []
    for x in times:
        n = "%06.2f.png" % x
        mx, pct = diff(os.path.join(o, n), os.path.join(t, n))
        worst = max(worst, mx)
        rows.append("  %7.2f s  max %3d  %.4f%% of pixels" % (x, mx, pct))
    say("\n".join(rows))
    if worst > PROVE_LEVELS:
        raise Stop("NOT the same: the template draws differently (worst %d levels)" % worst)
    say(
        "same: every moment within %d levels (sheet: %s)"
        % (PROVE_LEVELS, os.path.join(t, "sheet.png"))
    )


def stage_alt(a):
    p = project(a.slug)
    content = os.path.abspath(a.content if os.path.isabs(a.content) else os.path.join(p, a.content))
    if not os.path.isfile(content):
        raise Stop("no %s" % content)
    m = read_json(os.path.join(p, "sketch.json"))
    m["data"] = dict(m.get("data") or {}, content=os.path.relpath(content, p).replace("\\", "/"))
    name = os.path.splitext(os.path.basename(content))[0]
    alt = os.path.join(p, "sketch.%s.json" % name)
    times = [float(x) for x in a.times.split(",")] if a.times else moments(a.slug)
    if a.plan:
        say("would draw %s at %s" % (content, times))
        return
    write_json(alt, m)
    d = render(alt, times, "temp/stills-%s" % name)
    say("read it by eye: %s" % os.path.join(d, "sheet.png"))


def code_leftovers(slug, spec=None):
    """The sample's words (content.json's strings of 4 or more characters, and the spec's watched
    short words) still in film.js or cast/*.js."""
    p = project(slug)
    content = read_json(os.path.join(p, "content.json"), {})
    spec = spec or read_json(os.path.join(KIT, "config", "templates", slug + ".json"), {}) or {}
    generic = set(spec.get("generic") or ())
    images = set((read_json(os.path.join(p, "sketch.json"), {}) or {}).get("images") or {})
    code = open(os.path.join(p, "film.js"), encoding="utf-8").read()
    for n in (
        sorted(os.listdir(os.path.join(p, "cast")))
        if os.path.isdir(os.path.join(p, "cast"))
        else []
    ):
        code += "\n" + open(os.path.join(p, "cast", n), encoding="utf-8").read()
    low = code.lower()
    words = {
        s.strip()
        for k, v in content.items()
        if k != "_about"
        for s in strings(v)
        if len(s.strip()) >= 4
        and s.strip() not in generic
        and s.strip() not in images
        and not re.fullmatch(r"[\d\W_]+|#[0-9A-Fa-f]{3,8}|[a-z-]+", s.strip())
    }
    left = sorted(w for w in words if w.lower() in low)
    for path in spec.get("watch") or ():
        v = content
        for k in path.split("."):
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, str) and re.search(r"(?<!\w)%s(?!\w)" % re.escape(v), code):
            left.append(v)
    return left


def stage_check(a):
    left = code_leftovers(a.slug)
    if left:
        raise Stop("the sample is still in the code (every remake would stop on it): %s" % left)
    say("the code says nothing of the sample")


# ------------------------------------------------------------------ the specs
def stage_spec(a):
    p = project(a.slug)
    info = read_json(os.path.join(p, "template-source.json"), {})
    m = read_json(os.path.join(p, "sketch.json"))
    code = open(os.path.join(p, "film.js"), encoding="utf-8").read()
    studio = os.path.join(KIT, "config", "templates", a.slug + ".json")
    site = os.path.join(os.path.abspath(a.site), "specs", "templates", a.slug + ".json")
    frame = {(1920, 1080): "16:9", (1080, 1080): "1:1", (1080, 1920): "9:16"}.get(
        tuple((m.get("frame") or [1920, 1080])[:2]), "16:9"
    )
    sound_code = bool(re.search(r"SK\.film\(\{[\s\S]*?\bsound\s*:", code))
    s1 = read_json(studio) or {
        "_about": "The spec of kitcut.ai's %s template (studio/templates.py make --spec). Its film "
        "is projects/%s (local), made from kitcut.ai film %s." % (a.slug, a.slug, info.get("film")),
        "title": a.slug.replace("-", " ").capitalize(),
        "description": "",
        "author": "KitCut",
        "look": info.get("look") or "drawn",
        "frames": [frame],
        "caps": [c for c in info.get("caps") or [] if c not in ("kit", "template")],
        "limits": {"images": 6},
        "moments": preview_moments(a.slug),
        "narration": bool(info.get("narrated")),
        "sound": "code" if sound_code else "files",
        "keep": ["_about"],
        "generic": [],
        "watch": [],
        "identity": [],
        "example": "",
        "brief": "",
    }
    s2 = read_json(site) or {
        "_about": "The words of the '%s' template's page (npm run templates -- create --spec this "
        "--author %s). Its preview is the source film %s." % (a.slug, OWNER, info.get("film")),
        "id": "t-" + a.slug,
        "slug": a.slug,
        "category": "",
        "title": s1["title"],
        "h1": s1["title"] + " video template",
        "summary": "",
        "made_from": "",
        "source_film": info.get("film"),
        "by_kitcut": True,
        "ready_minutes": None,
        "tags": [],
        "description": [],
        "faq": [],
        "example": "",
    }
    if a.plan:
        say("would write %s and %s" % (studio, site))
        return
    write_json(studio, s1)
    if os.path.isdir(os.path.dirname(site)):
        write_json(site, s2)
    todo = [k for k in ("description", "example", "brief") if not s1.get(k)]
    todo += [
        "site:" + k
        for k in ("category", "summary", "made_from", "description", "faq", "example")
        if not s2.get(k)
    ]
    say("specs: %s\n       %s" % (studio, site))
    if todo:
        say("to write (a person's words, the skill says how): " + ", ".join(todo))


# ------------------------------------------------------------------ make / site
def stage_make(a):
    spec = os.path.join(KIT, "config", "templates", a.slug + ".json")
    tid = "t-" + a.slug
    env = dict(os.environ, STUDIO_HOME=SCRATCH)
    argv = [sys.executable, os.path.join(HERE, "templates.py"), "make", "--folder", project(a.slug)]
    argv += ["--id", tid, "--spec", spec]
    if a.plan:
        subprocess.run(argv + ["--plan"], env=env, check=False)
        return
    if code_leftovers(a.slug):
        raise Stop("check first: the sample is still in the code")
    r = subprocess.run(argv, env=env, capture_output=True, text=True)
    say(r.stdout[-1200:])
    if r.returncode != 0:
        raise Stop(r.stderr[-1500:])
    v = max(
        int(n[1:]) for n in os.listdir(os.path.join(SCRATCH, "templates", tid)) if n[1:].isdigit()
    )
    vd = os.path.join(SCRATCH, "templates", tid, "v%d" % v)
    say("version %s v%d: %s (preview: %s)" % (tid, v, vd, os.path.join(vd, "preview")))
    if a.push or a.publish:
        say(bash("template", "push", vd).strip().splitlines()[-1])
    if a.publish:
        bash("template", "publish", tid, str(v))
        say("live on the studio: %s v%d" % (tid, v))


def site_cmd(a, *args, env_file):
    node = shutil.which("node")
    site = os.path.abspath(a.site)
    argv = [
        node,
        "--env-file=" + os.path.join(site, ".env"),
        os.path.join(site, "scripts", "templates.mjs"),
    ]
    r = subprocess.run(
        argv + list(args), cwd=site, capture_output=True, text=True, encoding="utf-8"
    )
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        raise Stop(out[-1500:])
    return out


def stage_site(a):
    site_spec = os.path.join(os.path.abspath(a.site), "specs", "templates", a.slug + ".json")
    studio_env = os.path.join(KIT, ".env")
    spec = read_json(site_spec)
    if not spec:
        raise Stop("no %s: spec first" % site_spec)
    slug = spec["slug"]
    say(site_cmd(a, "check", "--spec", site_spec, env_file=None).splitlines()[-1])
    listed = site_cmd(a, "list", env_file=None)
    exists = re.search(r"\s/templates/%s\s" % re.escape(slug), listed + " ") or spec["id"] in listed
    verb = "update" if exists else "create"
    args = [verb] + ([slug] if exists else []) + ["--spec", site_spec, "--studio-env", studio_env]
    args += [] if exists else ["--author", OWNER]
    if a.plan:
        args.append("--dry-run")
    say(site_cmd(a, *args, env_file=None).splitlines()[-1])
    if a.publish and not a.plan:
        say(site_cmd(a, "publish", slug, env_file=None).splitlines()[-1])
        say("%s/templates/%s" % (SITE_URL, slug))


# ------------------------------------------------------------------ test: a stranger's film
def pairs(film_mp4, remake_mp4, seconds, out, n=6):
    """n moments side by side, the template's film left and the remake right: the fidelity read."""
    from PIL import Image  # noqa: PLC0415

    tmp = os.path.join(os.path.dirname(out), "pairs")
    os.makedirs(tmp, exist_ok=True)
    rows = []
    for i in range(n):
        t = (i + 0.5) * seconds / n
        pair = []
        for k, mp4 in enumerate((film_mp4, remake_mp4)):
            png = os.path.join(tmp, "%d-%d.png" % (i, k))
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t, "-i", mp4, "-frames:v", "1"]
                + ["-vf", "scale=480:-2", png],
                check=True,
            )
            pair.append(Image.open(png).convert("RGB"))
        rows.append(pair)
    w, h = rows[0][0].size
    sheet = Image.new("RGB", (w * 4 + 20, h * (n // 2)), "white")
    for i, (l, r) in enumerate(rows):
        x0, y = (i % 2) * (2 * w + 20), (i // 2) * h
        sheet.paste(l, (x0, y))
        sheet.paste(r, (x0 + w, y))
    sheet.save(out)


def stage_test(a):
    import asyncio  # noqa: PLC0415

    import bakeoff  # noqa: PLC0415

    tid = "t-" + a.slug
    info = read_json(os.path.join(project(a.slug), "template-source.json"), {})
    argv = ["film", a.prompt, "--template", tid, "--unlisted"]
    for f in a.attach or ():
        argv += ["--attach", f]
    if a.plan:
        say(
            "would make a film on the VM: ops.sh %s, then pull, grade and judge it" % " ".join(argv)
        )
        return
    if a.film:
        fid = a.film
    else:
        say("making a film from %s on the VM (it waits; ~10-25 min)..." % tid)
        out = bash(*argv, check=False)
        m = re.search(r"film (studio-\S+)", out)
        if not m:
            raise Stop("ops.sh film said:\n" + out[-1500:])
        fid = m.group(1)
        if '"status": "done"' not in out:
            raise Stop("%s did not finish:\n%s" % (fid, out[-1500:]))
    bash("pull", fid, PULLED)
    d = os.path.join(PULLED, fid)
    rep = os.path.join(project(a.slug), "temp", "tests", fid)
    os.makedirs(rep, exist_ok=True)
    seconds = float(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                os.path.join(d, "outputs", "film.mp4"),
            ],
            capture_output=True,
            text=True,
        ).stdout
        or 0
    )
    sheet = os.path.join(rep, "sheet.png")
    bakeoff.frames_sheet(d, seconds, sheet)
    g = asyncio.run(bakeoff.ask_blind(sheet, bakeoff.GRADE_ASK % (bakeoff.FRAMES, "")))
    src_mp4 = os.path.join(info.get("pulled") or "", "outputs", "film.mp4")
    if os.path.isfile(src_mp4):
        pp = os.path.join(rep, "pairs.png")
        pairs(src_mp4, os.path.join(d, "outputs", "film.mp4"), seconds, pp)
        g["fidelity"] = asyncio.run(bakeoff.ask_blind(pp, bakeoff.FIDELITY_ASK))
    fid_score = (g.get("fidelity") or {}).get("fidelity")
    ok = (g.get("professional") or 0) >= BAR["professional"] and (fid_score or 0) >= BAR["fidelity"]
    report = {
        "film": fid,
        "prompt": a.prompt,
        "attach": a.attach or [],
        "grade": g,
        "pass": ok,
        "link": "%s/film/%s" % (SITE_URL, fid),
        "sheet": sheet,
    }
    write_json(os.path.join(rep, "report.json"), report)
    say(
        "%s  professional %s  fidelity %s  (%s)"
        % (fid, g.get("professional"), fid_score, g.get("why"))
    )
    say("look at it: %s\n           %s" % (sheet, report["link"]))
    if not ok:
        raise Stop(
            "FAIL: under the bar %s -- improve the brief or the code, make a new version" % BAR
        )
    say("PASS")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "stage", choices=("find", "pull", "prove", "alt", "check", "spec", "make", "site", "test")
    )
    ap.add_argument("film", nargs="?", help="pull: the studio film id; find: an email")
    ap.add_argument("--slug", default="", help="the template's name: projects/<slug>, t-<slug>")
    ap.add_argument(
        "--facts", help="pull: the name of film.js's facts object (default: FACTS, EVENT...)"
    )
    ap.add_argument("--force", action="store_true", help="pull: make the project again")
    ap.add_argument("--times", help="prove/alt: comma list of moments (default: the film's review)")
    ap.add_argument("--content", help="alt: another content file")
    ap.add_argument(
        "--site", default=os.path.join(KIT, "..", "sketch-studio"), help="the site's checkout"
    )
    ap.add_argument(
        "--push", action="store_true", help="make: put the version on the VM as a draft"
    )
    ap.add_argument("--publish", action="store_true", help="make/site: make it live")
    ap.add_argument("--prompt", help="test: what a stranger types")
    ap.add_argument("--attach", action="append", help="test: a picture they attach")
    ap.add_argument("--film-id", dest="film_id", help="test: grade a film already made instead")
    ap.add_argument("--plan", action="store_true", help="say what it would do; do nothing")
    a = ap.parse_args()
    if a.stage == "test":
        a.film = a.film_id
        if not (a.prompt or a.film):
            ap.error("test needs --prompt")
    if a.stage in ("pull", "find") and not a.film:
        ap.error("%s needs %s" % (a.stage, "the film id" if a.stage == "pull" else "an email"))
    if a.stage != "find" and not a.slug:
        ap.error("--slug is needed")
    try:
        {
            "find": stage_find,
            "pull": stage_pull,
            "prove": stage_prove,
            "alt": stage_alt,
            "check": stage_check,
            "spec": stage_spec,
            "make": stage_make,
            "site": stage_site,
            "test": stage_test,
        }[a.stage](a)
    except Stop as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
