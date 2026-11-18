#!/usr/bin/env python
"""Three ideas for a finished film's next episode, written from it, each with a picture painted in
its look: kitcut.ai's "Make it a series?".

When someone's one-off film ends, the site offers to make it the start of a series, and shows
three one-line ideas for its next episode, so the person has something to pick instead of a blank
idea box. The site asks here as the film's own client:

    POST /api/library/ideas {"film"}   starts writing the ideas in the background of this server
                                       (unless they are being written, or written already) and
                                       answers at once, with what GET answers.
    GET  /api/library/ideas?film=      how they stand: {"state": none|writing|done|failed,
                                       "ideas": [3 strings] when done, "error" when failed,
                                       "cast": [{"name", "about", "painted"}],
                                       "pictures": {"state": none|painting|done|failed,
                                       "urls": [one for each idea: its address, or null]}}.

"cast" needs no Claude and is always there: the characters that would carry over into a project
made from this film -- exactly the ones fromfilm.seed would copy: the members its code drew (with
the description their code gives) and its painted characters, each once, drawn first. The site
shows them beside the ideas ("Pip and Mom come along").

The ideas are one Claude call with no tools, at low effort, because the person is watching the
film's last seconds while it is written. It reads what fromfilm reads for a brief, less what an
idea does not need (the music, the colours, the lettering): the person's idea as they wrote it,
who the film was made for, its narration, its characters by their cast names, and as images the
sheet of the film's frames and the first few of its pictures. It is asked for new stories for
the same audience, characters and world -- never this film told again.

The same answer gives each idea a picture: one still from that episode in words, and one line
for the film's look. Once the ideas are written (the site shows them at once, on frames of the
film), Muse paints the three stills at once (paint(), about $0.01 each, a minute or less) with
two frames of the film as its style pictures and up to two of its painted characters as
references, small (PICTURE_W x PICTURE_H), and they go online beside the film's other files
(media.publish_one, under new names each time, as its files are cached for a year). Painting is a
step of its own (python ideas.py --paint <job>), handed only the painter's key, as stylekit's
proof is: this server's own environment carries no secret. A picture that does not come is null,
and the site keeps the frame of the film in its place. Where media copying is off (a laptop's
studio), nothing is painted: there is nowhere to show the pictures from.

How it stands is kept in the film's own directory as series_ideas.json ({"state", "at",
"ideas"?, "error"?, "cost_usd"?, "pictures"?: {"state", "at", "urls"?, "cost_usd"?}, "plan"?:
{"style", "stills"}}), so any server answers GET, and asking twice writes nothing twice. One left
"writing" (or "painting") by a server that went away reads as failed, and a POST then writes the
ideas again; pictures that failed are not painted again.

    python studio/ideas.py --film <id> --plan     what Claude would be sent; calls nothing
    python studio/ideas.py --film <id>            the three ideas, printed (keeps nothing)
    python studio/ideas.py --paint <job.json>     the server's painting step (paint())
"""

import os
import re
import sys
import json
import time
import asyncio
import hashlib
import argparse
import importlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fromfilm  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import library  # noqa: E402
import media  # noqa: E402
import procs  # noqa: E402
import ytdraft  # noqa: E402

MODEL = fromfilm.MODEL
EFFORT = "low"  # quick: the person is watching their film end while this is written
STATE = "series_ideas.json"  # in the film's own directory
WRITING_MAX_S = 300  # ideas still "writing" after this were lost with their server: failed
IDEAS = 3  # how many the site shows
IDEA_MAX = 160  # characters in one idea, as the person would type it
ABOUT_MAX = 120  # characters of a cast member's description, as the site shows it
PICTURES_MAX = 4  # of the film's pictures Claude sees (the sheet of frames says the most)
FAILED = "The ideas were not written."
QUOTES = "\"'\u201c\u201d\u201e\u00ab\u00bb "  # around an idea, which it should not have
LISTED = re.compile(r"^(?:\d{1,2}[.)]|[-*\u2022])\s+")  # a number or a bullet before one
TASKS = set()  # the ideas being written in this server, so none is collected half way
# the pictures (paint()): Muse, the studio's own painter, at its one quality
PAINTER = films.STYLE_ROUTES["words"]["model"]
PICTURES_DIR = "series"  # in the film's own directory: the job, the stills, the step's answer
PICTURE_W, PICTURE_H = 640, 360  # a card's picture: small, as the site shows it
STILL_MAX = 400  # characters of one still's description
STYLE_MAX = 300  # of the line on the film's look
STYLE_AT = (0.35, 0.7)  # where in the film its two style pictures are taken
REFS_MAX = 2  # of its painted characters, as references
PAINT_S = 240  # the step, all three at once (one took ~40 s when the proof was measured)
PAINTING_MAX_S = PAINT_S + 60  # pictures still "painting" after this were lost: failed

WRITER = (
    "You write a series of short animated films: you think up what its next episodes are about. "
    "You are given the finished film the series starts from. Answer only with the JSON object "
    "asked for."
)

ASK = """\
The person who made this film may make it the first of a series. Think up three ideas for the \
series' next episode, episode 2, for them to pick from.

Each idea:
- Is a new, concrete story or topic of its own, for the same audience as this film, with the \
same characters and world, in the same tone. Never this film told again, and never a sequel that \
only makes sense to someone who has watched this one.
- Is one sentence of at most {most} characters, written as the person would type it into the \
idea box of a film maker, for example: Pip finds a red umbrella and learns how wind works
- Names the characters by their cast names above, written as names (pip is Pip), where they \
appear. If the film has no characters, keep its world, its kind of subject and its narrator.
- Is written in the language the person wrote their idea in; if that is unclear, in the \
narration's language ({language}).
- Has no numbering, no quotes around it and no emoji, and is never in all capital letters.

The three differ from each other: three different topics, not one idea said three ways.

For each idea, also describe one still from that episode, to be painted as its thumbnail in this \
film's own look: one or two sentences in English saying who is in it (describe each character by \
how they look, never by their name), where they are and what is happening, as one wide shot. \
Nothing written in it: no words, letters, signs or numbers.

And describe in one sentence in English how this film looks, as its frames show it (the medium, \
the lines, the colours, the texture), for the painter of those stills.

Answer with one JSON object and nothing else:
{{"style": "...", "ideas": [{{"idea": "...", "still": "..."}}, {{"idea": "...", "still": "..."}}, \
{{"idea": "...", "still": "..."}}]}}"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _cut(text, most, more=""):
    """`text` on one line, at most `most` characters, cut after a whole word (with `more` after
    it when it was cut)."""
    s = " ".join(str(text or "").split())
    if len(s) <= most:
        return s
    room = most - len(more)
    head = s[: room + 1]
    head = head[: head.rfind(" ")] if " " in head else s[:room]
    return head.rstrip(" ,;:-\u2013\u2014") + more


# ------------------------------------------------------------------ the cast: at once, no Claude
def cast(film):
    """The film's characters that a project made from it would have, as fromfilm.seed copies
    them: the members its code drew (those with their own code in the film), then its painted
    characters, each name once. -> [{"name", "about", "painted"}]."""
    out, seen = [], set()
    for n in library.used(film):
        code = library._read(film.path("cast", n + ".js"))  # noqa: SLF001
        if not code or not library.NAME.match(n):
            continue  # a prop of the kit, not a member of the film's cast
        about = library._about(code)  # noqa: SLF001
        out.append({"name": n, "about": _cut(about, ABOUT_MAX, "\u2026"), "painted": False})
        seen.add(n)
    for n, _, about in fromfilm.painted_of(film):
        if n not in seen:
            out.append({"name": n, "about": _cut(about, ABOUT_MAX, "\u2026"), "painted": True})
            seen.add(n)
    return out


# ------------------------------------------------------------------ what Claude reads
def material(film):
    """fromfilm's material for a brief, with only the first PICTURES_MAX pictures, and its
    characters as cast() has them: only those a series would carry over (not a prop of the kit),
    each once."""
    mat = fromfilm.material(film)
    mat["pictures"] = mat["pictures"][:PICTURES_MAX]
    mat["characters"] = cast(film)
    return mat


def ask_text(mat):
    lines = [
        "# The film",
        "Its title: %s" % (mat["title"] or "(none)"),
        "Look: %s, %s s long" % (mat["look"], mat["length"]),
        "Language of its narration: %s" % mat["language"],
    ]
    if mat["audience"]:
        lines.append("Made for: %s" % mat["audience"])
    if mat["header"]:
        lines.append("Its maker's note: %s" % mat["header"])
    lines += ["", "## The person's idea, as they wrote it", mat["prompt"] or "(none)"]
    if mat["narration"]:
        lines += ["", "## Its narration, as said"] + ["- " + t for t in mat["narration"]]
    if mat["characters"]:
        lines += ["", "## Its characters, by their cast names"]
        lines += [
            "- %s: %s" % (c["name"], c["about"] or "(no description)") for c in mat["characters"]
        ]
    else:
        lines += ["", "## Its characters", "(none in its cast)"]
    if mat.get("sheet_image"):
        lines += ["", "Image %d is a sheet of the film's frames." % mat["sheet_image"]]
    seen = [str(p["image"]) for p in mat["pictures"] if p.get("image")]
    if seen:
        lines.append(
            "Image %s is the person's own picture, which the film used." % seen[0]
            if len(seen) == 1
            else "Images %s are the person's own pictures, which the film used." % ", ".join(seen)
        )
    lines += ["", "# What to write", ASK.format(most=IDEA_MAX, language=mat["language"])]
    return "\n".join(lines)


def _pairs(d):
    """[(idea, still)] from Claude's answer: each idea one line of at most IDEA_MAX characters
    (cut after a whole word), different from the others; its still ("" when it has none). An idea
    may come as a plain string."""
    got = (d or {}).get("ideas") if isinstance(d, dict) else None
    out, seen = [], set()
    for it in got if isinstance(got, list) else []:
        idea, still = (
            (it, "")
            if isinstance(it, str)
            else ((it.get("idea"), it.get("still")) if isinstance(it, dict) else (None, None))
        )
        if not isinstance(idea, str):
            continue
        s = _cut(LISTED.sub("", " ".join(idea.split())).strip(QUOTES), IDEA_MAX)
        if s and s.casefold() not in seen:
            out.append((s, _cut(still if isinstance(still, str) else "", STILL_MAX)))
            seen.add(s.casefold())
    if len(out) < IDEAS:
        raise ValueError("%d ideas, not %d" % (len(out), IDEAS))
    return out[:IDEAS]


def clean(d):
    """Claude's answer held to its shape: exactly IDEAS different one-line ideas, each at most
    IDEA_MAX characters (cut after a whole word), or ValueError."""
    return [i for i, _ in _pairs(d)]


def plan(d):
    """What the stills are painted from: {"style": the film's look in a line, "stills": one for
    each idea ("" for one Claude did not describe)}."""
    style = (d or {}).get("style") if isinstance(d, dict) else ""
    return {
        "style": _cut(style if isinstance(style, str) else "", STYLE_MAX),
        "stills": [s for _, s in _pairs(d)],
    }


# ------------------------------------------------------------------ how they stand
def state_path(film):
    return film.path(STATE)


def _age(at, now=None):
    try:
        return ((now or datetime.now()) - datetime.fromisoformat(at)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _pictures(s, now=None):
    """The pictures' part of the state file, as GET answers it: {"state", "urls"}."""
    p = s.get("pictures") if isinstance(s.get("pictures"), dict) else {}
    st = p.get("state") if p.get("state") in ("painting", "done", "failed") else "none"
    if st == "painting" and _age(p.get("at"), now) > PAINTING_MAX_S:
        st = "failed"
    urls = p.get("urls") if st == "done" and isinstance(p.get("urls"), list) else []
    urls = [u if isinstance(u, str) and u.startswith("https://") else None for u in urls]
    return {"state": st, "urls": (urls + [None] * IDEAS)[:IDEAS]}


def _standing(film, now=None):
    """The state file, read: {"state", "ideas"?, "error"?, "pictures"?}. One left "writing" by a
    server that went away, and a "done" without its ideas, read as failed."""
    s = fromfilm._read(state_path(film), True)  # noqa: SLF001
    if not isinstance(s, dict) or s.get("state") not in ("writing", "done", "failed"):
        return {"state": "none"}
    if s["state"] == "writing":
        try:
            age = ((now or datetime.now()) - datetime.fromisoformat(s.get("at"))).total_seconds()
        except (TypeError, ValueError):
            age = WRITING_MAX_S + 1
        return (
            {"state": "writing"} if age <= WRITING_MAX_S else {"state": "failed", "error": FAILED}
        )
    if s["state"] == "done":
        ideas = s.get("ideas")
        if (
            isinstance(ideas, list)
            and len(ideas) == IDEAS
            and all(isinstance(i, str) for i in ideas)
        ):
            return {"state": "done", "ideas": ideas, "pictures": _pictures(s, now)}
    return {"state": "failed", "error": str(s.get("error") or FAILED)}


def state(client, film_id, now=None):
    """How the ideas for the asker's finished film stand, with its cast (see the module's note).
    fromfilm.FromFilmError 404 for a film that is not theirs, 409 for one not finished."""
    f = fromfilm.source(client, film_id)
    return {**_standing(f, now), "cast": cast(f)}


async def write(client, film_id, auth="login", model=MODEL, effort=EFFORT):
    """Write the ideas, keeping how they stand in the film's series_ideas.json."""
    try:
        f = fromfilm.source(client, film_id)
    except fromfilm.FromFilmError as e:  # gone since it was asked: nowhere to keep the ideas
        print("ideas %s: not written: %s" % (film_id, e.text), file=sys.stderr, flush=True)
        return
    path = state_path(f)
    films._write_json(path, {"state": "writing", "at": _now()})  # noqa: SLF001
    try:
        mat = await asyncio.to_thread(material, f)
        seen = await asyncio.to_thread(fromfilm.images, f, mat)  # pictures decoded off the loop
        d, cost = await ytdraft.ask_json(
            ask_text(mat), seen, auth, f, model, effort, WRITER, "series-ideas-%s" % f.id
        )
        out, todo = clean(d), plan(d)
        painting = media.enabled() and any(todo["stills"])
        done = {"state": "done", "at": _now(), "ideas": out, "cost_usd": round(cost, 4)}
        if painting:
            done.update(plan=todo, pictures={"state": "painting", "at": _now()})
        films._write_json(path, done)  # noqa: SLF001
    except Exception as e:  # noqa: BLE001 -- said to the person as "not written", and logged
        print("ideas %s: not written: %s" % (f.id, e), file=sys.stderr, flush=True)
        films._write_json(path, {"state": "failed", "at": _now(), "error": FAILED})  # noqa: SLF001
        return
    if painting:
        await paint(f)


# ------------------------------------------------------------------ the pictures
def style_pictures(film):
    """Two frames of the film (STYLE_AT), as JPEGs in its series folder, else its poster: what
    Muse paints the stills to look like. [paths]"""
    d = film.path(PICTURES_DIR)
    os.makedirs(d, exist_ok=True)
    mp4 = film.path("outputs", "film.mp4")
    out = []
    if os.path.isfile(mp4):
        try:
            length = media._duration(mp4) or 0  # noqa: SLF001
        except Exception:  # noqa: BLE001 -- no length: the poster instead
            length = 0
        for i, at in enumerate(STYLE_AT if length else ()):
            im = media._frame(mp4, length * at)  # noqa: SLF001
            if im is not None:
                p = os.path.join(d, "style-%d.jpg" % (i + 1))
                im.thumbnail((1280, 1280))
                im.save(p, "JPEG", quality=88)
                out.append(p)
    poster = film.path("outputs", "film_poster.png")
    if not out and os.path.isfile(poster):
        out.append(poster)
    return out


def job(film, todo):
    """What the painting step paints: {"dir", "style", "stills", "style_pictures", "refs"}."""
    return {
        "dir": film.path(PICTURES_DIR),
        "style": todo.get("style") or "",
        "stills": list(todo.get("stills") or []),
        "style_pictures": style_pictures(film),
        "refs": [p for _, p, _ in fromfilm.painted_of(film)][:REFS_MAX],
    }


def _sp():
    return importlib.import_module("sketch-paint")


def paint_job(j, log=print):
    """The step: each still that has words painted by Muse at once, small, as
    <dir>/still-<i>-<hash>.jpg; the answer, also kept as <dir>/paint.json:
    {"files": [one for each still: its file's name, or null], "cost_usd"}."""
    sp = _sp()
    from io import BytesIO

    from PIL import Image

    def one(i):
        words = (j["stills"][i] or "").strip()
        if not words:
            return None, 0
        try:
            prompt = sp.full_prompt({"style": j.get("style") or ""}, {"prompt": words})
            data, meta = sp.paint_openrouter(
                prompt,
                PAINTER,
                ref=j.get("refs") or None,
                style_ref=j.get("style_pictures") or None,
            )
            im = Image.open(BytesIO(data)).convert("RGB")
            w, h = im.size
            want = PICTURE_W / PICTURE_H  # cut to 16:9, then made small
            if w / h > want:
                cw = int(h * want)
                im = im.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
            else:
                ch = int(w / want)
                im = im.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))
            im = im.resize((PICTURE_W, PICTURE_H), Image.LANCZOS)
            buf = BytesIO()
            im.save(buf, "JPEG", quality=84, optimize=True)
            name = "still-%d-%s.jpg" % (i + 1, hashlib.sha1(buf.getvalue()).hexdigest()[:10])
            with open(os.path.join(j["dir"], name), "wb") as f:
                f.write(buf.getvalue())
            return name, float(meta.get("cost_usd") or 0)
        except Exception as e:  # noqa: BLE001 -- one still failing leaves the others
            log("still %d: %s" % (i + 1, e))
            return None, 0

    with ThreadPoolExecutor(max_workers=IDEAS) as ex:
        got = list(ex.map(one, range(len(j["stills"]))))
    out = {"files": [n for n, _ in got], "cost_usd": round(sum(c for _, c in got), 4)}
    films._write_json(os.path.join(j["dir"], "paint.json"), out)  # noqa: SLF001
    return out


async def paint_step(j):
    """paint_job as a step of its own (python ideas.py --paint <job>), handed only the painter's
    key; its answer, or raises."""
    path = os.path.join(j["dir"], "job.json")
    films._write_json(path, j)  # noqa: SLF001
    answer = os.path.join(j["dir"], "paint.json")
    if os.path.exists(answer):
        os.remove(answer)
    env = {k: os.environ[k] for k in procs.BASICS if k in os.environ}
    env.update(PYTHONIOENCODING="utf-8", KITCUT_DOTENV="0")
    key = procs.secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        env["OPENROUTER_API_KEY"] = key
    p = await asyncio.create_subprocess_exec(
        sys.executable,
        "-X",
        "utf8",
        os.path.abspath(__file__),
        "--paint",
        path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(p.communicate(), PAINT_S)
    except TimeoutError:
        p.kill()
        raise RuntimeError("the stills took too long to paint") from None
    for line in (out or b"").decode("utf-8", "replace").splitlines()[-6:]:
        print("ideas paint: %s" % line, file=sys.stderr, flush=True)
    got = fromfilm._read(answer, True)  # noqa: SLF001
    if p.returncode or not isinstance(got, dict):
        raise RuntimeError("the painting step failed (%s)" % p.returncode)
    return got


async def paint(film):
    """Paint the ideas' stills (paint_step) and put them online (media.publish_one); keep their
    addresses in the state file. Never raises: pictures that did not come are said as failed, and
    the site keeps the frames of the film."""
    path = state_path(film)
    t = time.time()
    try:
        s = fromfilm._read(path, True) or {}  # noqa: SLF001
        j = await asyncio.to_thread(job, film, s.get("plan") or {})
        got = await paint_step(j)
        urls = []
        for name in got.get("files") or []:
            urls.append(
                await media.publish_one(film, name, "image/jpeg", out=j["dir"]) if name else None
            )
        pictures = {
            "state": "done" if any(urls) else "failed",
            "at": _now(),
            "urls": urls,
            "cost_usd": got.get("cost_usd"),
            "seconds": round(time.time() - t, 1),
        }
    except Exception as e:  # noqa: BLE001 -- the ideas stand without their pictures
        print("ideas %s: pictures not painted: %s" % (film.id, e), file=sys.stderr, flush=True)
        pictures = {"state": "failed", "at": _now()}
    s = fromfilm._read(path, True) or {}  # noqa: SLF001
    if s.get("state") == "done":  # written again meanwhile: those ideas' pictures are their own
        films._write_json(path, {**s, "pictures": pictures})  # noqa: SLF001


def start(client, film_id, auth="login"):
    """write() in the background of this server, unless the ideas are being written or are
    written already; how they stand is on disk at once. Nothing awaits between reading the state
    and writing "writing", so two asks at once start one."""
    f = fromfilm.source(client, film_id)
    if _standing(f)["state"] not in ("writing", "done"):
        films._write_json(state_path(f), {"state": "writing", "at": _now()})  # noqa: SLF001
        t = asyncio.get_running_loop().create_task(write(client, f.id, auth))
        TASKS.add(t)
        t.add_done_callback(TASKS.discard)
    return state(client, f.id)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--film", help="a finished film's id")
    ap.add_argument("--paint", metavar="JOB", help="paint a job's stills (the server's step)")
    ap.add_argument(
        "--plan", action="store_true", help="print what Claude would read; call nothing"
    )
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT)
    a = ap.parse_args()
    if a.paint:  # the server's step (paint_step): the job is written, the key is in env
        with open(a.paint, encoding="utf-8") as fh:
            got = paint_job(json.load(fh))
        print("stills: %s, $%s" % (got["files"], got["cost_usd"]))
        return
    if not a.film:
        ap.error("--film, or --paint")
    f = films.Film.open(a.film)
    if f is None:
        sys.exit("no such film: %s" % a.film)
    mat = material(f)
    seen = fromfilm.images(f, mat)
    text = ask_text(mat)
    if a.plan:
        print(text)
        print("\n(%d images)" % len(seen))
        print("\ncast: %s" % cast(f))
        return
    d, cost = asyncio.run(
        ytdraft.ask_json(text, seen, "login", f, a.model, a.effort, WRITER, "series-ideas")
    )
    for i, still in _pairs(d):
        print("- %s\n  still: %s" % (i, still))
    print("\nlook: %s" % plan(d)["style"])
    print("\n(%.4f USD)" % cost)


if __name__ == "__main__":
    main()
