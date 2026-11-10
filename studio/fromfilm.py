#!/usr/bin/env python
"""A finished film made the start of a project: kitcut.ai's "Create project from this video".

The site makes the project (named after the film, with its look, length and frame) and asks here
as the project's workspace: POST /api/library/from-film {"project", "film"}. Two things happen:

    seed()   at once, no Claude. What the film used becomes the project's, as if the person had
             put it in by hand: the pictures (what was attached to the film, and an episode's own
             pic_ pictures) become the project's Pictures with the roles they had; the cast
             members its code drew join the project's cast (their latest code and picture); its
             painted characters (an episode's cast_ pictures, and the paintings it kept) join the
             painted cast; and the film itself heads the project's earlier films, so every
             episode reads its film.js, vo.json and score.json -- its lettering, colours, music,
             the narrator's pace -- as it reads an earlier episode's. Nothing already in the
             project is replaced, so asking twice copies nothing twice.
    write()  in the background, one Claude call with no tools: the project's brief, from what
             the film is -- the person's idea, who it was made for, its narration, its narrator,
             music, colours and lettering, its cast with their descriptions, its pictures -- only
             what every episode should share, never this film's own story, facts or numbers.

What write() is doing is kept in <project library>/from_film.json, which any server answers
(GET /api/library/from-film?project=): writing, done ({brief, name}) or failed. The brief is the
site's: it saves it into the project when it reads "done".

    python studio/fromfilm.py --film <id> --plan     what Claude would be sent; calls nothing
    python studio/fromfilm.py --film <id>            the brief, printed (copies nothing)
"""

import os
import re
import sys
import json
import shutil
import asyncio
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import agent  # noqa: E402 -- imports _env first
import clients  # noqa: E402
import film as films  # noqa: E402
import library  # noqa: E402
import ytdraft  # noqa: E402
import _sketch  # noqa: E402

MODEL = agent.MODEL
EFFORT = "medium"
STATE = "from_film.json"  # in the project's library
WRITING_MAX_S = 600  # a brief still "writing" after this was lost with its server: failed
PROMPT_MAX = 8000  # of the person's idea, as Claude reads it
LINES_MAX = 40  # narration lines Claude reads
NAME_MAX = 80  # the site's project name (lib/projects.js NAME_MAX)
# what the person attached (upload<n>) or an episode got from its project (pic_<name>)
PICTURE_FILE = re.compile(r"^(?:upload(\d{1,2})|pic_([a-z][a-z0-9_]{0,30}))\.(png|jpe?g|webp)$")
TASKS = set()  # the briefs being written in this server, so none is collected half way

WRITER = (
    "You write the brief of a series of short animated films -- its bible, which Claude reads "
    "before making every episode. You are given one finished film the series starts from. Answer "
    "only with the JSON object asked for."
)

ASK = """\
This film is the first of a series: a project whose next episodes will each be about something \
new, and must look and sound as if they belong with it. Write the project's brief from it: \
everything an episode should share with this film, and nothing that belongs only to this film.

Put in, as far as the film shows it:
- Who the series is for, and its language.
- The tone, and how the narrator speaks (the voice, the pace, how lines open, the words they use \
or avoid). Give a sentence or two of the way they talk.
- The music and sound.
- The look: the ground and its colours (hex where they are given), the drawing or painting style, \
how a frame is laid out, what recurs on screen.
- The lettering: the typefaces named below, and what each is used for.
- The characters: each by their cast name, with how they look and who they are, so an episode \
can bring them back. The places and things that recur.
- The pictures: each by its name (pic_<name>), what it shows, and how an episode uses it.
- What always happens and what never does (how an episode opens and ends, things to avoid).

Leave out this film's own topic, story, facts, numbers and dates: the next episode is about \
something else. Where the person's idea mixes the two, keep only the part that holds for every \
episode. Say nothing the film does not show or say.

Write it in plain sentences under short headings, in English (the episodes' language is named in \
it), at most {most} characters. Also name the series in a few words (at most {name_max} \
characters): what a channel of these films would be called, not this film's title.

Answer with one JSON object and nothing else:
{{"name": "...", "brief": "..."}}"""


class FromFilmError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read(p, as_json=False):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) if as_json else f.read()
    except (OSError, ValueError):
        return None


def project_lib(client, project):
    """The project's library, or FromFilmError 404."""
    lib = library.owner(client, project) if isinstance(project, str) else None
    if not lib or not lib[1]:
        raise FromFilmError(404, "No such project.")
    return lib


def source(client, film_id):
    """The asker's finished film, or FromFilmError: 404 for anyone else's (a stranger learns
    nothing), 409 for one not finished."""
    f = films.Film.open(str(film_id or "")) if film_id else None
    if f is None or not clients.same(f.record().get("client"), client):
        raise FromFilmError(404, "No such film.")
    if f.state != "done":
        raise FromFilmError(409, "This film is not finished.")
    return f


# ------------------------------------------------------------------ what the film used
def pictures_of(film):
    """The film's pictures that a project keeps: [(name in the project, file, ext, role)]. What
    was attached keeps its order (upload1 -> picture1); an episode's own pic_<name> its name."""
    d = film.path("inputs")
    roles = _sketch.picture_roles(film.dir)
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in names:
        m = PICTURE_FILE.match(fn)
        if not m:
            continue
        stem = fn.rsplit(".", 1)[0]
        name = "picture%s" % m.group(1) if m.group(1) else m.group(2)
        ext = "jpg" if m.group(3) == "jpeg" else m.group(3)
        out.append((name, os.path.join(d, fn), ext, roles.get(stem)))
    # attached pictures first, in the order they were attached
    out.sort(key=lambda x: (not x[0].startswith("picture"), len(x[0]), x[0]))
    return out


def painted_of(film):
    """The film's painted characters a project keeps: [(name, file, about)] -- the ones its
    project gave it (inputs/cast_<name>.*) that it used, and the paintings it marked to keep."""
    rec = film.record()
    about = {
        c.get("name"): c.get("about") or ""
        for c in (rec.get("library") or {}).get("painted") or []
        if isinstance(c, dict)
    }
    used = set(library.painted_used(film))
    out, seen = [], set()
    for c in (rec.get("library") or {}).get("painted") or []:
        n = c.get("name") if isinstance(c, dict) else None
        f = c.get("file") if isinstance(c, dict) else None
        if not (n in used and library.NAME.match(n or "") and f):
            continue
        p = film.path(*str(f).split("/"))
        if os.path.exists(p):
            out.append((n, p, about.get(n, "")))
            seen.add(n)
    for k in library.kept_paintings(film):
        if k["name"] not in seen:
            out.append((k["name"], k["path"], k["about"] or ""))
            seen.add(k["name"])
    return out


def fonts_of(film):
    """The typefaces the film's manifest loads, by family, in order."""
    m = _read(film.manifest, True) or {}
    fams = [str(f.get("family") or "") for f in m.get("fonts") or [] if isinstance(f, dict)]
    return list(dict.fromkeys(f for f in fams if f))


def voice_of(film):
    """The narrator's voice (one of the studio's, by name), or None: a person's own voice
    (ElevenLabs) stays theirs, and a film with no narration has none."""
    if (film.record().get("narrator") or {}).get("source") == "elevenlabs":
        return None
    vo = _read(film.path("vo.json"), True) or {}
    v = vo.get("voice") if isinstance(vo, dict) else None
    return v if isinstance(v, str) and re.match(r"^[A-Za-z][A-Za-z0-9_-]{1,40}$", v) else None


# ------------------------------------------------------------------ seed: copied at once
def seed(client, project, film_id):
    """Copy what the film used into the project (see the module's note). Returns what the project
    has from the film (asked twice, the same names again): {"film", "pictures": [names], "cast":
    [names], "painted": [names], "voice", "fonts", "skipped": [{"name", "why"}]}."""
    lib = project_lib(client, project)
    f = source(client, film_id)
    got = {"film": f.id, "pictures": [], "cast": [], "painted": [], "skipped": []}

    # its pictures, through the same door as an upload (the cap, the thumbnail, the role)
    for name, path, ext, role in pictures_of(f):
        if name in library.load(lib)["pictures"]:
            got["pictures"].append(name)  # asked before: the project has it already
            continue
        try:
            library.add_picture(client, project, name, path, ext, role=role)
            got["pictures"].append(name)
        except library.PictureError as e:
            got["skipped"].append({"name": name, "why": e.text})

    src_lib = library.lib_of(f.record())
    src_dir = library.dir_of(src_lib) if src_lib else None
    now = _now()
    with library._lock(lib):  # noqa: SLF001
        idx = library.load(lib)
        d = library.dir_of(lib)
        # its drawn cast: the film's own copy of each member it drew
        for n in library.used(f):
            code = library._read(f.path("cast", n + ".js"))  # noqa: SLF001
            e = idx["cast"].get(n)
            if e and not e.get("deleted"):
                if e.get("from_film") == f.id:
                    got["cast"].append(n)  # asked before
                continue
            if not code or not library.NAME.match(n):
                continue
            md = os.path.join(d, "cast", n)
            os.makedirs(md, exist_ok=True)
            with open(os.path.join(md, "v1.js"), "w", encoding="utf-8") as fh:
                fh.write(code)
            thumb = src_dir and os.path.join(src_dir, "cast", n, "thumb.png")
            if thumb and os.path.exists(thumb):
                shutil.copyfile(thumb, os.path.join(md, "thumb.png"))
            idx["cast"][n] = {
                "version": 1,
                "hash": library._hash(code),  # noqa: SLF001
                "about": library._about(code),  # noqa: SLF001
                "kind": library._kind(code),  # noqa: SLF001
                "films": [],
                "created": now,
                "updated": now,
                "from_film": f.id,
                "thumb": bool(thumb and os.path.exists(thumb)),
                "brought": True,  # not drawn by an episode yet (seed() says so to Claude)
            }
            got["cast"].append(n)
        # its painted characters
        for n, path, about in painted_of(f):
            e = idx["cast"].get(n)
            if e and not e.get("deleted"):
                if e.get("from_film") == f.id and e.get("painted"):
                    got["painted"].append(n)  # asked before
                continue  # a member of that name is there already
            if len(library._live_painted(idx)) >= library.CHARACTERS:  # noqa: SLF001
                got["skipped"].append({"name": n, "why": "the project's painted cast is full"})
                continue
            try:
                library._put_painted(lib, idx, n, path, about, now, from_film=f.id)  # noqa: SLF001
                got["painted"].append(n)
            except library.PictureError as e:
                got["skipped"].append({"name": n, "why": e.text})
        # the film itself, first among the project's earlier films
        if f.id not in idx["films"]:
            idx["films"] = [f.id, *idx["films"]][: library.LISTED]
        library._save(lib, idx)  # noqa: SLF001
        if got["cast"] or got["painted"]:
            library._contact(lib, idx)  # noqa: SLF001
    got["voice"] = voice_of(f)
    got["fonts"] = fonts_of(f)
    return got


# ------------------------------------------------------------------ write: the brief
def material(film, got=None):
    """What the brief is written from, on the film's side."""
    rec = film.record()
    dr = film.direction()
    vo = _read(film.path("vo.json"), True) or {}
    js = _read(film.path("film.js")) or ""
    paint = _read(film.path("paint.json"), True) or {}
    cast = []
    for n in library.used(film):
        about = library._about(library._read(film.path("cast", n + ".js")) or "")  # noqa: SLF001
        cast.append({"name": n, "about": about})
    painted = [{"name": n, "about": a} for n, _, a in painted_of(film)]
    pictures = [{"name": "pic_" + n, "role": r} for n, _, _, r in pictures_of(film)]
    return {
        "prompt": str(rec.get("prompt") or "")[:PROMPT_MAX],
        "title": rec.get("title") or "",
        "look": film.look,
        "frame": rec.get("frame") or "16:9",
        "length": rec.get("length") or 0,
        "language": vo.get("language") or "en",
        "audience": dr.get("audience") or "",
        "header": ytdraft._header(js),  # noqa: SLF001
        "voice": None if dr.get("voice") == "own" else dr.get("voice"),
        "voice_style": dr.get("voice_style") or "",
        "music": {"instruments": dr.get("instruments") or [], "bpm": dr.get("bpm")},
        "direction": {
            k: dr[k]
            for k in ("ground", "style", "paint_style", "faces", "newsprint", "character_style")
            if dr.get(k)
        },
        "colours": {"%s colour" % k: dr[k] for k in ("paper", "accent") if dr.get(k)},
        "paint_style": str(paint.get("style") or "")[:300] if isinstance(paint, dict) else "",
        "fonts": fonts_of(film),
        "narration": [t for _, _, t in ytdraft._narration(film)][:LINES_MAX],  # noqa: SLF001
        "cast": cast,
        "painted": painted,
        # the ones the project got, when it has been seeded (a full project skips some)
        "pictures": [p for p in pictures if got is None or p["name"][4:] in got["pictures"]],
    }


def ask_text(mat):
    lines = [
        "# The film",
        "Its title: %s" % (mat["title"] or "(none)"),
        "Look: %s, frame %s, %s s long" % (mat["look"], mat["frame"], mat["length"]),
        "Language of its narration: %s" % mat["language"],
    ]
    if mat["audience"]:
        lines.append("Made for: %s" % mat["audience"])
    if mat["header"]:
        lines.append("Its maker's note: %s" % mat["header"])
    lines += ["", "## The person's idea, as they wrote it", mat["prompt"] or "(none)", ""]
    lines.append("## How it looks and sounds")
    if mat["voice"]:
        lines.append(
            "Narrator: the voice %s%s"
            % (mat["voice"], "; " + mat["voice_style"] if mat["voice_style"] else "")
        )
    m = mat["music"]
    if m["instruments"] or m["bpm"]:
        lines.append(
            "Music: %s%s"
            % (", ".join(m["instruments"]) or "-", ", %s bpm" % m["bpm"] if m["bpm"] else "")
        )
    for k, v in {**mat["direction"], **mat["colours"]}.items():
        lines.append("%s: %s" % (k.replace("_", " ").capitalize(), v))
    if mat["paint_style"]:
        lines.append("Painting style: %s" % mat["paint_style"])
    if mat["fonts"]:
        lines.append("Typefaces it loads: %s" % ", ".join(mat["fonts"]))
    if mat["narration"]:
        lines += ["", "## Its narration, as said"] + ["- " + t for t in mat["narration"]]
    if mat["cast"] or mat["painted"]:
        lines += ["", "## Its characters (now the project's cast, by these names)"]
        lines += ["- %s: %s" % (c["name"], c["about"] or "(no description)") for c in mat["cast"]]
        lines += [
            "- %s (a painted character): %s" % (c["name"], c["about"] or "(no description)")
            for c in mat["painted"]
        ]
    if mat["pictures"]:
        lines += ["", "## Its pictures (now the project's, by these names)"]
        lines += [
            "- %s%s" % (p["name"], library.role_line(p["role"], mat["look"] != "drawn"))
            for p in mat["pictures"]
        ]
    lines += ["", "# What to write", ASK.format(most=films.BRIEF_MAX - 500, name_max=NAME_MAX)]
    return "\n".join(lines)


def clean(d):
    """Claude's answer held to its shape: {"name", "brief"}, or ValueError."""
    brief = str((d or {}).get("brief") or "").replace("\r\n", "\n").strip()
    if not brief:
        raise ValueError("no brief")
    name = " ".join(str((d or {}).get("name") or "").split())[:NAME_MAX].strip()
    return {"name": name, "brief": brief[: films.BRIEF_MAX]}


def state_path(lib):
    return os.path.join(library.dir_of(lib), STATE)


def state(client, project, now=None):
    """How the brief stands: {"state": "none"|"writing"|"done"|"failed", "film", "brief"?,
    "name"?, "error"?}. One left "writing" by a server that went away reads as failed."""
    lib = project_lib(client, project)
    s = _read(state_path(lib), True)
    if not isinstance(s, dict):
        return {"state": "none"}
    if s.get("state") == "writing":
        try:
            age = ((now or datetime.now()) - datetime.fromisoformat(s.get("at"))).total_seconds()
        except (TypeError, ValueError):
            age = WRITING_MAX_S + 1
        if age > WRITING_MAX_S:
            s = {**s, "state": "failed", "error": "The brief was not finished."}
    return {k: s[k] for k in ("state", "film", "brief", "name", "error", "at") if k in s}


async def write(client, project, film_id, got=None, auth="login", model=MODEL, effort=EFFORT):
    """Write the brief, keeping how it stands in the project's from_film.json."""
    lib = project_lib(client, project)
    path = state_path(lib)
    films._write_json(path, {"state": "writing", "film": film_id, "at": _now()})  # noqa: SLF001
    try:
        f = source(client, film_id)
        text = ask_text(material(f, got))
        sheet = ytdraft._sheet(f)  # noqa: SLF001
        d, cost = await ytdraft.ask_json(
            text, sheet, auth, f, model, effort, WRITER, "from-film-%s" % project
        )
        out = clean(d)
        films._write_json(  # noqa: SLF001
            path,
            {"state": "done", "film": film_id, "at": _now(), "cost_usd": round(cost, 4), **out},
        )
    except Exception as e:  # noqa: BLE001 -- said to the person as "not written", and logged
        print("fromfilm %s: brief not written: %s" % (project, e), file=sys.stderr, flush=True)
        films._write_json(  # noqa: SLF001
            path,
            {
                "state": "failed",
                "film": film_id,
                "at": _now(),
                "error": "The brief was not written.",
            },
        )


def start(client, project, film_id, got=None, auth="login"):
    """write() in the background of this server; how it stands is on disk at once."""
    lib = project_lib(client, project)
    films._write_json(state_path(lib), {"state": "writing", "film": film_id, "at": _now()})  # noqa: SLF001
    t = asyncio.get_running_loop().create_task(write(client, project, film_id, got, auth))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return state(client, project)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--film", required=True, help="a finished film's id")
    ap.add_argument(
        "--plan", action="store_true", help="print what Claude would read; call nothing"
    )
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT)
    a = ap.parse_args()
    f = films.Film.open(a.film)
    if f is None:
        sys.exit("no such film: %s" % a.film)
    text = ask_text(material(f))
    if a.plan:
        print(text)
        return
    d, cost = asyncio.run(
        ytdraft.ask_json(
            text, ytdraft._sheet(f), "login", f, a.model, a.effort, WRITER, "from-film"
        )  # noqa: SLF001
    )
    out = clean(d)
    print("# %s\n\n%s\n\n(%.4f USD)" % (out["name"], out["brief"], cost))


if __name__ == "__main__":
    main()
