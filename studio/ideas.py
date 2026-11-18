#!/usr/bin/env python
"""Three ideas for episode 2, written from a finished film: kitcut.ai's "Make it a series?".

When someone's one-off film ends, the site offers to make it the start of a series, and shows
three one-line ideas for its next episode, so the person has something to pick instead of a blank
idea box. The site asks here as the film's own client:

    POST /api/library/ideas {"film"}   starts writing the ideas in the background of this server
                                       (unless they are being written, or written already) and
                                       answers at once, with what GET answers.
    GET  /api/library/ideas?film=      how they stand: {"state": none|writing|done|failed,
                                       "ideas": [3 strings] when done, "error" when failed,
                                       "cast": [{"name", "about", "painted"}]}.

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

How it stands is kept in the film's own directory as series_ideas.json ({"state", "at",
"ideas"?, "error"?, "cost_usd"?}), so any server answers GET, and asking twice writes nothing
twice. One left "writing" by a server that went away reads as failed, and a POST then writes it
again.

    python studio/ideas.py --film <id> --plan     what Claude would be sent; calls nothing
    python studio/ideas.py --film <id>            the three ideas, printed (keeps nothing)
"""

import os
import re
import sys
import asyncio
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fromfilm  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import library  # noqa: E402
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

Answer with one JSON object and nothing else:
{{"ideas": ["...", "...", "..."]}}"""


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


def clean(d):
    """Claude's answer held to its shape: exactly IDEAS different one-line ideas, each at most
    IDEA_MAX characters (cut after a whole word), or ValueError."""
    got = (d or {}).get("ideas") if isinstance(d, dict) else None
    out, seen = [], set()
    for it in got if isinstance(got, list) else []:
        if not isinstance(it, str):
            continue
        s = _cut(LISTED.sub("", " ".join(it.split())).strip(QUOTES), IDEA_MAX)
        if s and s.casefold() not in seen:
            out.append(s)
            seen.add(s.casefold())
    if len(out) < IDEAS:
        raise ValueError("%d ideas, not %d" % (len(out), IDEAS))
    return out[:IDEAS]


# ------------------------------------------------------------------ how they stand
def state_path(film):
    return film.path(STATE)


def _standing(film, now=None):
    """The state file, read: {"state", "ideas"?, "error"?}. One left "writing" by a server that
    went away, and a "done" without its ideas, read as failed."""
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
            return {"state": "done", "ideas": ideas}
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
        out = clean(d)
        films._write_json(  # noqa: SLF001
            path, {"state": "done", "at": _now(), "ideas": out, "cost_usd": round(cost, 4)}
        )
    except Exception as e:  # noqa: BLE001 -- said to the person as "not written", and logged
        print("ideas %s: not written: %s" % (f.id, e), file=sys.stderr, flush=True)
        films._write_json(path, {"state": "failed", "at": _now(), "error": FAILED})  # noqa: SLF001


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
    for i in clean(d):
        print("- " + i)
    print("\n(%.4f USD)" % cost)


if __name__ == "__main__":
    main()
