#!/usr/bin/env python
"""A finished film's YouTube title, description, tags and four thumbnails, from what the film is.

The site (kitcut-hq/sketch-studio, api/youtube.js) knows the channel: it reads the channel's
latest uploads with the grant it already holds, and sends them here. The studio knows the film:
its narration and when each line is said, who it was made for, what Claude said it made and
what it could not confirm, the pages its facts came from, a sheet of its moments (clean stills
with their times, thumbs.py). Two Claude calls with no tools, made at the same time, put the two
together: the words -- the title, description and tags this channel's owner would have written
for this film -- and the thumbnails' picks (four moments, a few words each, a layout, where the
words go). The words are shown as soon as they are written (about 8-14 s), and never wait for the
render queue the stills and thumbnails share: they see the moments sheet when it is made already,
else the film's review sheet. Before 2026-10-01 one call wrote both, after the sheet had been
made, so a draft could wait a minute or more behind other films' thumbnails before a word showed.
check() then holds the words to what YouTube takes and to what they were given: no link nobody
gave, no chapter past the end; check_thumbs() holds the picks to
_thumb's rules, with the title once it is known. Once picked, the job makes the thumbnail options
(thumbs.py) and the draft's answer carries them.

    python studio/ytdraft.py --film <id|folder> --sample-from @instafill_ai --plan
    python studio/ytdraft.py --film <id|folder> --sample sample.json [--model M] [--effort E]
    python studio/ytdraft.py --film <id|folder> --thumbs      (and make the thumbnail options)

--plan prints what Claude would be sent and what it would cost, and calls nothing. A draft is
kept in the film's youtube/ folder, keyed by everything it was written from, so asking again
costs nothing until the film or the channel's uploads change. The channel's uploads themselves
are never written down.
"""

import os
import re
import sys
import json
import time
import base64
import asyncio
import hashlib
import argparse
import subprocess
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import agent  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import thumbs  # noqa: E402
import _thumb  # noqa: E402
import _ytchapters  # noqa: E402

MODEL = agent.MODEL
EFFORT = "medium"
SAMPLE_MAX = 8  # the channel's latest uploads Claude reads
SAMPLE_DESC = 1500  # of each one's description
TITLE_MAX = 100  # YouTube's
DESC_MAX = 4500  # bytes: YouTube takes 5000, and the site adds its credit line after
TAGS_MAX = 500  # YouTube's, counted its way (a tag with a space costs its quotes too)
PER_FILM = 12  # drafts one film may have written, all channels together
KEEP_S = 3600  # a finished job is remembered this long (the draft itself stays on disk)
CHANNEL = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
URL = re.compile(r"https?://[^\s<>\"'()\[\]{}]+")

WRITER = (
    "You write the title and description a finished video goes onto YouTube with, and choose "
    "its thumbnails. You are given the film -- its narration as spoken, with times; who it was "
    "made for; what its maker said about it; the pages its facts came from; a sheet of its "
    "frames -- and the channel it is going to, through that channel's latest uploads. Answer "
    "only with the JSON object asked for."
)

ASK = """\
Write the title and description this channel's owner would have written for this film, had they \
made it and posted it themselves. The channel's latest uploads show how its owner writes: match \
them -- the shape and length of their titles, how their descriptions open, the sections they use, \
the links they give, whether and how they use hashtags and tags. The film is the subject: say what \
it shows and says, for the people it was made for, so the right viewer clicks and knows what they \
will get.

Hold it to the film:
- Every fact comes from the narration, the pages listed, or what the maker said. Name no number, \
feature, date or claim the film does not make, and where the maker says something is unconfirmed, \
do not state more than the film does. Do not say the video was asked for or generated.
- Give a link only if it appears above: in the channel's own descriptions, or among the pages the \
film's facts came from. Never make one up.
- Chapters only if the film is long enough to have real parts (about a minute or more): each \
timestamp taken from the narration's times, the first at 0:00, every one inside the film's length.
- Write in the film's language ({language}).
- If there are no uploads to learn from, write the way a good channel for this film's audience \
would.
- Leave out any credit for the tool that made the film; one is added after your description.

YouTube's limits: the title at most 100 characters, the description at most 4500, the tags at \
most 500 characters together.

Answer with one JSON object and nothing else:
{{"title": "...", "description": "...", "tags": ["...", "..."]}}"""

ASK_THUMBS = """\
Choose four thumbnails for this film's video on YouTube, made the way YouTube thumbnails are: one \
moment of the film, its subject pushed in large on one side, and a few big words on the other -- \
the only words on the picture (the film's own titles and labels are left out of it), set in the \
film's own title type and colours, with its logo:
- "at": the moment, in seconds, from the sheet of its moments (the time is printed on every \
frame) -- one where the film's subject is on screen, large and fully drawn: a character, an \
object, a chart. Four different moments.
- "layout": "headline" (the words large over the picture) for the first and the fourth, "card" \
(the words on the film's own label or card) and "panel" (the picture on one side, the words on a \
panel of the film's colour on the other) for the second and third.
- "words": at most 4 words and 32 characters, in the film's language ({language}). The first \
thumbnail says the video's main message -- {main}, in fewer words; the others each say one of \
the film's main points. Words a viewer reads at a glance and wants to click on, and \
they hold to the film -- no number or claim it does not show or say. \
Star one word to colour it (write it as *word*).
- "place": the side the words go on, so they leave the subject clear: left, right, top or \
bottom.
Put first the one you would choose yourself.

Answer with one JSON object and nothing else:
{{"thumbnails": [{{"at": 0.0, "layout": "headline", "words": "...", "place": "top"}}, ...]}}"""

# A film that shows pictures (cut-outs, prints) gets posters composed from them (_thumb.py
# layout_poster), so its writer names the picture each is built on rather than a layout.
ASK_POSTERS = """\
Choose four thumbnails for this film's video on YouTube. Each is a poster composed from the \
film's own pictures -- not a frame of it: one picture set large (somebody from the waist up, or \
an object whole) on the film's own coloured ground, at most one more tucked in beside it, and a \
few big words -- the only words on the picture -- in the film's own title type, with its logo:
- "hero": the picture the poster is built on, by its name from the list below. A face is what \
a viewer looks at first: when the film has characters, a character is the hero of at least \
three of the four -- the one whose face and pose show what the words say (worried, delighted, \
saying stop) -- and an object is the hero only where no character fits the words. Four \
different pictures (another pose of the same character is a different picture).
- "with": at most one more picture, by name -- beside a character, the thing the words are \
about (what they are afraid of, holding, tempted by), or a second character when the words are \
about the two of them -- or [] for none.
- "at": a moment of the film, in seconds, from the sheet of its moments (the time is printed on \
every frame), where that hero is on screen: the poster takes that moment's ground and colours. \
Four different moments.
- "words": at most 4 words and 32 characters, in the film's language ({language}); fewer and \
shorter words are set larger. The first thumbnail says the video's main message -- {main}, in \
fewer words; the others each say one of the film's main points. Words a viewer reads at a \
glance and wants to click on, and they hold to the film -- no number or claim it does not show \
or say. Star one word to colour it (write it as *word*).
Put first the one you would choose yourself.

The film's pictures (name: what it shows):
{pieces}

Answer with one JSON object and nothing else:
{{"thumbnails": [{{"at": 0.0, "hero": "name", "with": [], "words": "..."}}, ...]}}"""
PIECES_MAX = 60  # pictures listed for the writer

# (film id, channel id) -> {"film", "channel", "client", "state", "draft", "error", "t", "task"}
JOBS = {}


class DraftError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


# ------------------------------------------------------------------ what the film is
def _read(p, as_json=False):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) if as_json else f.read()
    except (OSError, ValueError):
        return None


def _header(js):
    """The maker's note at the top of film.js: the comment after the "// For:" line."""
    lines = (js or "").splitlines()[1:40]
    out, block = [], False
    for L in lines:
        s = L.strip()
        if block or s.startswith("/*"):
            block = "*/" not in s
            out.append(s.strip("/* ").strip())
            if not block:
                break
        elif s.startswith("//"):
            out.append(s[2:].strip())
        elif s:
            break
    return " ".join(x for x in out if x)[:1500]


def _narration(film):
    """[(start, end, text)] as spoken: the timeline when there is one, else the script."""
    tl = _read(film.path("audio", "vo", "timeline.json"), True) or {}
    lines = [
        (float(L.get("start") or 0), float(L.get("end") or 0), str(L.get("text") or ""))
        for L in tl.get("lines") or []
        if isinstance(L, dict)
    ]
    if lines:
        return lines
    vo = _read(film.path("vo.json"), True) or {}
    lines = [(None, None, str(L.get("text") or "")) for L in vo.get("lines") or []]
    if lines:
        return lines
    import templates  # noqa: PLC0415 -- a film with no narration: the words it shows

    return [(None, None, s) for s in templates.onscreen(film)]


def _sources(film, events=None):
    """The pages the film's facts came from: read in a browser by the page tool (web/), or
    opened with WebFetch (only the address is kept, and a site may have refused it)."""
    out, seen = [], set()
    for name, s in (_read(film.path("web", "sources.json"), True) or {}).items():
        if not isinstance(s, dict) or s.get("kind") != "page":
            continue
        facts = _read(film.path("web", name.removeprefix("web_") + ".json"), True) or {}
        url = s.get("final") or s.get("url")
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "title": facts.get("title") or "", "how": "read"})
    path = events or film.path("events.jsonl")
    for line in (_read(path) or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        text = ev.get("text") or "" if isinstance(ev, dict) else ""
        if ev.get("type") == "tool" and text.startswith("reading http"):
            url = text.split(" ", 1)[1].strip()
            if url not in seen:
                seen.add(url)
                out.append({"url": url, "title": "", "how": "fetched"})
    return out


def _sheet(film):
    """The film's frames as one JPEG when its moments sheet cannot be made (the review sheet,
    else the poster), or None."""
    for p in (film.path("outputs", "review", "sheet.png"), film.path("outputs", "film_poster.png")):
        if os.path.exists(p):
            from io import BytesIO

            from PIL import Image

            im = Image.open(p).convert("RGB")
            im.thumbnail((1568, 1568))
            buf = BytesIO()
            im.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    return None


def material(film, events=None, sheet=False):
    """Everything the draft is written from, on the film's side. The sheet of the film's moments
    (thumbs.py) takes a browser to make, so it is left out unless asked for: write() adds it in
    the background. The draft's key names the film itself (film_key), not the sheet's bytes."""
    rec = film.record()
    vo = _read(film.path("vo.json"), True) or {}
    js = _read(film.path("film.js")) or ""
    paint = _read(film.path("paint.json"), True) or {}
    project = rec.get("project") or {}
    try:
        length = film.length
    except (OSError, ValueError, KeyError):
        length = rec.get("length") or 0
    return {
        "length": length,
        "language": vo.get("language") or "en",
        "audience": ((films.FOR_LINE.search(js) or [None, ""])[1] or "").strip()[:300],
        "header": _header(js),
        "narration": _narration(film),
        "pictures": films.paint_words(film.caps)[1],  # paintings, cut-outs
        "scenes": [
            str(i.get("prompt") or "")[:400]
            for i in paint.get("images") or []
            if isinstance(i, dict)
        ],
        "said": (rec.get("claude_said") or "").strip()[:4000],
        "sources": _sources(film, events),
        "project": {"name": project.get("name")} if project else None,
        "film_key": _thumb.film_key(film.dir),
        "moments": thumbs.moments(film) if os.path.exists(film.manifest) else [],
        "sheet": thumbs.sheet_now(film) if sheet else None,
        "moments_sheet": bool(sheet),
    }


# ------------------------------------------------------------------ the channel
def sample(recent):
    """The channel's latest uploads as the site sends them, cut to what Claude needs."""
    out = []
    for v in (recent or [])[:SAMPLE_MAX]:
        if not isinstance(v, dict) or not str(v.get("title") or "").strip():
            continue
        tags = v.get("tags") if isinstance(v.get("tags"), list) else []
        out.append(
            {
                "title": str(v["title"]).strip()[:TITLE_MAX],
                "description": str(v.get("description") or "").strip()[:SAMPLE_DESC],
                "tags": [str(t)[:60] for t in tags[:30]],
            }
        )
    return out


def parse_request(body):
    """The site's ask: {channel: {id, title, handle}, recent: [...]} -> (channel, recent)."""
    if not isinstance(body, dict) or not isinstance(body.get("channel"), dict):
        raise ValueError('send {"channel": {"id", "title", "handle"}, "recent": [...]}')
    c = body["channel"]
    if not CHANNEL.match(str(c.get("id") or "")):
        raise ValueError("channel.id is not a channel id")
    channel = {
        "id": c["id"],
        "title": " ".join(str(c.get("title") or "").split())[:100],
        "handle": " ".join(str(c.get("handle") or "").split())[:100],
    }
    recent = body.get("recent") or []
    if not isinstance(recent, list):
        raise ValueError("recent must be a list")
    return channel, sample(recent)


# ------------------------------------------------------------------ the ask
def ask_text(mat, channel, recent, part="words", title=None):
    """The message Claude gets (the sheet goes with it as an image): for the words, or for the
    thumbnails (part "thumbs": no uploads to match, and the title once it is known)."""
    if part == "thumbs":
        main = 'its title, "%s"' % title if title else "what the video promises or asks"
        ask = ASK_THUMBS.format(language=mat["language"], main=main)
        if mat.get("pieces"):
            ask = ASK_POSTERS.format(language=mat["language"], main=main, pieces=mat["pieces"])
        return "\n".join(
            [
                "# The channel",
                channel.get("title") or "(untitled)",
                "",
                *film_text(mat),
                "",
                "# What to choose",
                ask,
            ]
        )
    parts = [
        "# The channel",
        "%s%s"
        % (
            channel.get("title") or "(untitled)",
            " (%s)" % channel["handle"] if channel.get("handle") else "",
        ),
    ]
    if recent:
        parts.append("Its latest uploads, newest first:")
        for v in recent:
            parts.append("## %s\n%s" % (v["title"], v["description"] or "(no description)"))
            if v["tags"]:
                parts.append("Tags: " + ", ".join(v["tags"]))
    else:
        parts.append("(No uploads to learn from.)")
    parts += ["", *film_text(mat), "", "# What to write", ASK.format(language=mat["language"])]
    return "\n".join(parts)


def film_text(mat):
    """The film's half of the ask, as lines: what it is and says, and the
    sheet. share.py sends it too."""
    parts = [
        "# The film",
        "Length: %d seconds. Language: %s." % (mat["length"], mat["language"]),
    ]
    if mat["audience"]:
        parts.append("Made for: " + mat["audience"])
    if mat["header"]:
        parts.append("Its maker's note in the film's code: " + mat["header"])
    parts.append("\nThe narration, as spoken:")
    for s, e, text in mat["narration"]:
        parts.append(("%5.1f-%5.1f s  %s" % (s, e, text)) if s is not None else "  " + text)
    if mat["scenes"]:
        parts.append("\nThe %s it is made of:" % mat.get("pictures", "paintings"))
        parts += ["- " + p for p in mat["scenes"]]
    if mat["sources"]:
        parts.append("\nThe pages its facts came from:")
        for s in mat["sources"]:
            how = "read in full" if s["how"] == "read" else "opened (it may have refused)"
            parts.append("- %s%s (%s)" % (s["title"] + " -- " if s["title"] else "", s["url"], how))
    if mat["said"]:
        parts.append("\nWhat its maker said when it was finished:\n" + mat["said"])
    if mat.get("project"):
        p = mat["project"]
        parts.append('\nIt is an episode of the series "%s".' % p["name"])
    if mat["sheet"] and mat.get("moments_sheet"):
        parts.append(
            "\nThe image is the film's moments, in order: clean stills, each with its time "
            "printed on it (%s s)." % ", ".join("%.1f" % t for t in mat["moments"])
        )
    elif mat["sheet"]:
        parts.append(
            "\nThe image is a sheet of frames from the film, in order. Choose the thumbnails' "
            "moments from these times: %s s." % ", ".join("%.1f" % t for t in mat["moments"])
        )
    return parts


def key_of(mat, channel, recent, model, effort):
    """What a draft was written from: a new film, other uploads or another model is a new one."""
    h = hashlib.sha256()
    for part in (
        WRITER,
        ASK,
        model,
        effort,
        json.dumps(channel, sort_keys=True),
        json.dumps(recent, sort_keys=True),
        # the sheet is drawn from the film, which film_key names: its bytes are not part of it
        json.dumps(
            {k: v for k, v in mat.items() if k not in ("sheet", "moments_sheet")},
            sort_keys=True,
            default=str,
        ),
    ):
        h.update(part.encode("utf-8") + b"\0")
    return h.hexdigest()[:24]


# ------------------------------------------------------------------ holding it to the film
def _norm_url(u):
    p = urlsplit(u.rstrip(".,;:!?"))
    return (p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), p.query)


def title_clean(t):
    """One line, at most 100 characters, cut at a word: the site's cleanTitle."""
    t = " ".join(str(t or "").replace("<", "").replace(">", "").split())
    if len(t) <= TITLE_MAX:
        return t
    cut = t[: TITLE_MAX - 1]
    sp = cut.rfind(" ")
    if sp > 60:
        cut = cut[:sp]
    return cut.rstrip(" ,.;:-|\u2013\u2014") + "\u2026"


def tags_clean(tags):
    out, seen, total = [], set(), 0
    for t in tags if isinstance(tags, list) else []:
        t = " ".join(str(t).replace("<", " ").replace(">", " ").replace(",", " ").split())
        t = t.lstrip("#")[:100]
        if not t or t.lower() in seen:
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if total + cost > TAGS_MAX:
            break
        seen.add(t.lower())
        out.append(t)
        total += cost
    return out


def check(d, mat, recent):
    """The draft held to YouTube's limits and to its inputs: (clean draft, notes)."""
    notes = []
    title = title_clean(d.get("title"))
    desc = str(d.get("description") or "").replace("\r\n", "\n").replace("<", "").replace(">", "")
    # links: only ones it was given
    given = {_norm_url(u) for v in recent for u in URL.findall(v["description"])}
    given |= {_norm_url(s["url"]) for s in mat["sources"]}
    lines = []
    for L in desc.split("\n"):
        bad = [u for u in URL.findall(L) if _norm_url(u) not in given]
        for u in bad:
            notes.append("removed a link it was not given: %s" % u.rstrip(".,;:!?"))
            L = L.replace(u.rstrip(".,;:!?"), "")
        if bad and (not L.strip() or (len(L.strip()) < 50 and L.strip().endswith(":"))):
            continue
        lines.append(L.rstrip())
    desc = "\n".join(lines)
    # chapters: from 0:00, in order, inside the film -- or none
    marks = _ytchapters.parse_marks(desc)
    if marks:
        times = [t for t, _ in marks]
        why = (
            _ytchapters.fatal(marks)
            or (["the first is not at 0:00"] if times[0] != 0 else [])
            or (["out of order"] if times != sorted(times) else [])
            or (["past the film's end"] if mat["length"] and times[-1] >= mat["length"] else [])
        )
        if why:
            notes.append("removed the chapters: %s" % why[0])
            ls = desc.split("\n")
            first = next(i for i, L in enumerate(ls) if _ytchapters.CHAPTER_LINE.match(L))
            drop = {i for i, L in enumerate(ls) if _ytchapters.CHAPTER_LINE.match(L)}
            j = first - 1
            while j >= 0 and not ls[j].strip():
                j -= 1
            if j >= 0 and len(ls[j].strip()) <= 40 and not URL.search(ls[j]):
                drop.add(j)  # its heading ("CHAPTERS", "Timestamps:")
            desc = "\n".join(L for i, L in enumerate(ls) if i not in drop)
    desc = re.sub(r"\n{3,}", "\n\n", desc).strip()
    raw = desc.encode("utf-8")
    if len(raw) > DESC_MAX:
        desc = raw[:DESC_MAX].decode("utf-8", "ignore").rsplit("\n", 1)[0].rstrip()
        notes.append("cut the description to %d bytes" % DESC_MAX)
    out = {"title": title, "description": desc, "tags": tags_clean(d.get("tags"))}
    if not out["title"]:
        raise ValueError("no title")
    return out, notes


def check_thumbs(d, mat, title, n=4, layouts=None):
    """The draft's four thumbnails (or `n`, of `layouts`) held to _thumb's rules: (concepts,
    notes, problems). A problem is something only the writer can put right; it is asked once,
    then repair() decides."""
    return _thumb.check_concepts(
        d.get("thumbnails"), mat["length"] or 0, title, n, layouts, mat.get("piece_names")
    )


def pieces_text(film_dir):
    """(the film's pictures as lines for the writer, their names) -- ("", None) for a film with
    none it can be told about, whose writer then picks moments and each poster takes its moment's
    own pieces. Listed: the pictures that were painted for the film, by what each was painted as
    (paint.json). A picture somebody gave it has no such words, so the writer cannot know what it
    shows and is not asked to choose it; a brand's mark is left off too."""
    try:
        pcs = _thumb.film_pieces(film_dir)
    except Exception as e:  # noqa: BLE001 -- the picks are then made the way they were before posters
        print("youtube draft: no pictures listed for %s: %s" % (film_dir, e), flush=True)
        return "", None
    rows = []
    for name, p in pcs.items():
        about = " ".join(p["about"].split())[:160]
        if not about or p["lettered"] or p["mark"]:
            continue
        rows.append("- %s: %s" % (name, about))
    if not rows:
        return "", None
    return "\n".join(rows[:PIECES_MAX]), [r.split(":", 1)[0][2:] for r in rows[:PIECES_MAX]]


def repair(concepts, problems, mat, n=4):
    """What is left of a second answer that still broke the rules: a thumbnail whose words were
    the problem becomes the picture alone, and missing or crowded moments are made up from the
    film's own, to `n` of them. (concepts, note)."""
    bad = {p["n"] for p in problems if p.get("n")}
    out = [dict(c, words="", layout="still") if i in bad else c for i, c in enumerate(concepts, 1)]
    out = _thumb.fill_concepts(out, mat.get("moments") or [], mat["length"] or 0, n=n)
    return out, "thumbnails put right from the film: %s" % "; ".join(p["text"] for p in problems)


# ------------------------------------------------------------------ writing it
async def _call(
    mat, channel, recent, auth, film, model, effort, note=None, part="words", title=None
):
    """One Claude call, for the words or the thumbnails: (the parsed JSON, cost in USD)."""
    text = ask_text(mat, channel, recent, part, title) + ("\n\n" + note if note else "")
    return await ask_json(text, mat["sheet"], auth, film, model, effort, WRITER, "youtube-draft")


async def ask_json(text, sheet, auth, film, model, effort, system, session):
    """One Claude call with no tools -- the text, and the sheet (JPEG bytes, or a list of them,
    in order) as images before it -- on the film's key (auth "api") or this machine's login: (the
    parsed JSON object, cost in USD). share.py, canon.py and review.py ask through it too. It has
    no time limit of its own: a caller that must not wait wraps it (asyncio.wait_for)."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock
    from claude_agent_sdk import query

    content = [{"type": "text", "text": text}]
    sheets = [sheet] if isinstance(sheet, (bytes, bytearray)) else list(sheet or [])
    for n, one in enumerate(sheets):
        img = base64.b64encode(one).decode("ascii")
        content.insert(
            n,
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img},
            },
        )

    async def ask():
        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
            "session_id": session,
        }

    opts = ClaudeAgentOptions(
        model=model,
        effort=effort,
        system_prompt=system,
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=agent.claude_env(film if auth == "api" else None, auth),
        **({"cli_path": agent.claude_cli()} if auth == "login" else {}),
    )
    said, cost, err = "", 0.0, None
    async for m in query(prompt=ask(), options=opts):
        if isinstance(m, AssistantMessage):
            said += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        elif isinstance(m, ResultMessage):
            cost = m.total_cost_usd or 0.0
            err = m.result if m.is_error else None
    j = re.search(r"\{.*\}", said, re.DOTALL)
    try:
        d = json.loads(j.group(0)) if j else None
    except ValueError:
        d = None
    if err or not isinstance(d, dict):
        raise RuntimeError("no draft: %s" % (err or said[:300]))
    return d, cost


def cache_path(film, channel):
    return film.path("youtube", "draft-%s.json" % channel["id"])


def cached(film, channel, key=None):
    """The last draft for this channel -- only if it was written from the same things, when a
    key is given."""
    d = _read(cache_path(film, channel), True)
    if isinstance(d, dict) and (key is None or d.get("key") == key):
        return d
    return None


async def write(
    film,
    channel,
    recent,
    auth="api",
    model=MODEL,
    effort=EFFORT,
    events=None,
    record=True,
    mat=None,
    on_words=None,
):
    """The draft for this film on this channel: from the cache, else two calls made at the same
    time -- the words (and one more if they were not the JSON asked for) and
    the thumbnails' picks (and one more if they broke the rules). on_words(draft) is called with
    the words as soon as they are written, before the thumbnails are picked, so the site can show
    them. Records what it cost on the film and in the run log, unless record is False (a draft
    tried by hand)."""
    mat = mat or await asyncio.to_thread(material, film, events)
    key = key_of(mat, channel, recent, model, effort)
    hit = cached(film, channel, key)
    if hit:
        return hit
    t0 = time.time()
    picks = asyncio.create_task(_pick(film, mat, channel, auth, model, effort))
    try:
        words, spent, notes = await _words(film, mat, channel, recent, auth, model, effort, record)
    except BaseException:
        picks.cancel()
        raise
    draft = words | {
        "thumbnails": None,
        "language": mat["language"],
        "notes": notes,
        "model": model,
        "effort": effort,
        "key": key,
        "channel": channel["id"],
        "cost_usd": round(spent, 4),
        "seconds": round(time.time() - t0, 1),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if on_words:
        on_words(draft)
    concepts, tnotes, more = await _thumbnails(
        film, picks, mat, channel, auth, model, effort, draft["title"]
    )
    spent += more
    draft = draft | {
        "thumbnails": concepts,
        "notes": notes + tnotes,
        "cost_usd": round(spent, 4),
        "seconds_thumbnails": round(time.time() - t0, 1),
    }
    os.makedirs(film.path("youtube"), exist_ok=True)
    films._write_json(cache_path(film, channel), draft)
    if record:
        await _spent(film, spent, auth)
    return draft


async def _words(film, mat, channel, recent, auth, model, effort, record):
    """The title, description and tags: one call, and one more if the first was not the JSON asked
    for. (words, cost, notes). Shown the film's moments when that sheet is
    made already, else its review sheet or poster: the words never wait for the render queue."""
    if mat.get("sheet") is None:
        got = await asyncio.to_thread(thumbs.sheet_made, film)
        mat = (
            dict(mat, sheet=got, moments_sheet=True)
            if got
            else dict(mat, sheet=_sheet(film), moments_sheet=False)
        )
    spent, note = 0.0, None
    for attempt in (1, 2):
        try:
            d, cost = await _call(mat, channel, recent, auth, film, model, effort, note)
        except RuntimeError:
            if attempt == 2:
                raise
            note = "Your last answer was not the JSON object asked for. Answer with it alone."
            continue
        spent += cost
        try:
            out, notes = check(d, mat, recent)
        except ValueError as e:
            if attempt == 2:
                raise RuntimeError("no draft: %s" % e) from None
            note = "Your last answer had no title. Answer with the whole JSON object."
            continue
        return out, spent, notes
    raise RuntimeError("no draft")


async def _pick(film, mat, channel, auth, model, effort):
    """The thumbnails' picks, asked at the same time as the words: shown the film's moments, made
    now through the render queue when they are not made yet. (answer, cost, what it was shown)."""
    if mat.get("sheet") is not None and mat.get("moments_sheet"):
        m = mat
    else:
        got = await thumbs.sheet(film)
        m = (
            dict(mat, sheet=got, moments_sheet=True)
            if got
            else dict(mat, sheet=_sheet(film), moments_sheet=False)
        )
    # a film with pictures is asked for posters built on them (not part of the draft's key: a
    # draft written before posters keeps its picks, and its posters take each moment's own pieces)
    text, names = await asyncio.to_thread(pieces_text, film.dir)
    m = dict(m, pieces=text, piece_names=names)
    d, cost = await _call(m, channel, [], auth, film, model, effort, part="thumbs")
    return d, cost, m


async def _thumbnails(film, picks, mat, channel, auth, model, effort, title):
    """The picks held to the rules, the title now known: asked once more, with why, when they break
    them, then put right from the film. (concepts, notes, cost). Picks that could not be had at
    all are made up from the film's own moments."""
    try:
        d, spent, m = await picks
    except Exception as e:  # noqa: BLE001 -- a draft without picks still has its thumbnails
        n = _thumb.fill_concepts([], mat.get("moments") or [], mat["length"] or 0, n=4)
        return n, ["thumbnails made up from the film: %s" % str(e)[:160]], 0.0
    concepts, notes, problems = check_thumbs(d, m, title)
    if problems:
        try:
            d2, more = await _call(
                m,
                channel,
                [],
                auth,
                film,
                model,
                effort,
                "Your last answer's thumbnails broke the rules: %s. Answer with the whole JSON "
                "object again, the thumbnails put right." % "; ".join(p["text"] for p in problems),
                part="thumbs",
                title=title,
            )
            spent += more
            concepts, notes, problems = check_thumbs(d2, m, title)
        except RuntimeError:
            pass
        if problems:
            concepts, fixed = repair(concepts, problems, m)
            notes = notes + [fixed]
    return concepts, notes, spent


async def _spent(film, usd, auth):
    """A draft's cost on the film's record, and in the run log (so the day's budget sees it):
    counted in cost_usd only when it was paid for on the key."""
    rec = film.record()
    fields = {
        "youtube_drafts": (rec.get("youtube_drafts") or 0) + 1,
        "youtube_draft_cost_usd": round((rec.get("youtube_draft_cost_usd") or 0) + usd, 4),
    }
    if auth == "api":
        fields["cost_usd"] = round((rec.get("cost_usd") or 0) + usd, 4)
    film.update(**fields)
    await asyncio.to_thread(agent.STORE.save, film.id, fields)


# ------------------------------------------------------------------ the site's jobs
def public(job):
    out = {k: job[k] for k in ("film", "channel", "state", "error") if job.get(k) is not None}
    d = job.get("draft") or {}
    out.update({k: d[k] for k in ("title", "description", "tags", "language") if k in d})
    if job.get("state") == "done":
        out["thumbs"] = thumbs.public(job.get("thumbs"))
    return out


def get(film_id, channel_id):
    return JOBS.get((film_id, channel_id))


def busy(job):
    """Still at work: the draft being written, or its thumbnails being made."""
    return job["state"] == "writing" or (job.get("thumbs") or {}).get("state") == "making"


def in_flight():
    """The drafts being written (or their thumbnails made), as [film, channel], for this
    server's heartbeat (peers.py)."""
    return [list(k) for k, j in JOBS.items() if busy(j)]


def prune():
    now = time.time()
    for k, j in list(JOBS.items()):
        if not busy(j) and now - j["t"] > KEEP_S:
            del JOBS[k]


def chain_thumbs(job, film):
    """A written draft's thumbnails onto its job: the saved ones at once, else "making" at once
    (so the answer that goes out now already says so) and made in the background."""
    hit = thumbs.saved(film, job["channel"], (job.get("draft") or {}).get("key"))
    if hit:
        job["thumbs"] = hit
        return
    job["thumbs"] = {"state": "making"}
    job["task"] = asyncio.get_running_loop().create_task(make_thumbs(job, film))


async def make_thumbs(job, film):
    """The draft's thumbnail options (thumbs.py), onto the job: the ones already made for this
    draft, else made now. A failure leaves the draft standing: the site then offers none."""
    d = job.get("draft") or {}
    hit = thumbs.saved(film, job["channel"], d.get("key"))
    if hit:
        job["thumbs"] = hit
        return
    job["thumbs"] = {"state": "making"}
    try:
        job["thumbs"] = await thumbs.make(film, job["channel"], d)
    except Exception as e:  # noqa: BLE001 -- a publish without a thumbnail is still a publish
        job["thumbs"] = {"state": "failed", "error": str(e)[:300]}
        print("youtube thumbs %s/%s failed: %s" % (film.id, job["channel"], e), flush=True)
    finally:
        job["t"] = time.time()


async def start(film, client, channel, recent, auth="api"):
    """Write the draft in the background (one at a time per film and channel). Returns the job;
    its state is "done" at once when the same draft is already on disk."""
    prune()
    k = (film.id, channel["id"])
    job = JOBS.get(k)
    if job and busy(job):
        return job
    mat = await asyncio.to_thread(material, film)
    job = {
        "film": film.id,
        "channel": channel["id"],
        "client": client,
        "state": "done",
        "draft": cached(film, channel, key_of(mat, channel, recent, MODEL, EFFORT)),
        "error": None,
        "t": time.time(),
    }
    if job["draft"] is not None:  # written before: its thumbnails too, else make them now
        chain_thumbs(job, film)
    if job["draft"] is None:
        if (film.record().get("youtube_drafts") or 0) >= PER_FILM:
            job["draft"] = cached(film, channel)  # the last one written, if any
            if job["draft"] is None:
                raise DraftError(429, "This film has had all the drafts it can have written.")
            chain_thumbs(job, film)
        else:
            job["state"] = "writing"

            def shown(words):  # the words, while the thumbnails are still being picked
                job["draft"], job["state"], job["t"] = words, "done", time.time()
                job["thumbs"] = {"state": "making"}

            async def run():
                try:
                    job["draft"] = await write(film, channel, recent, auth, mat=mat, on_words=shown)
                    job["state"] = "done"
                except Exception as e:  # noqa: BLE001 -- the site falls back to its own defaults
                    if job["state"] == "done":  # the words were out: only the thumbnails are lost
                        job["thumbs"] = {"state": "failed", "error": str(e)[:300]}
                        print(
                            "youtube thumbs %s/%s failed: %s" % (film.id, channel["id"], e),
                            flush=True,
                        )
                        return
                    job["state"], job["error"] = "failed", str(e)[:300]
                    print(
                        "youtube draft %s/%s failed: %s" % (film.id, channel["id"], e), flush=True
                    )
                    return
                finally:
                    job["t"] = time.time()
                await make_thumbs(job, film)

            job["task"] = asyncio.get_running_loop().create_task(run())
    JOBS[k] = job
    return job


# ------------------------------------------------------------------ trying it by hand
def sample_from(handle, n=SAMPLE_MAX):
    """A public channel's latest uploads, read with yt-dlp -- for trying drafts by hand; the
    site reads them through the person's own grant."""
    url = "https://www.youtube.com/%s/videos" % (handle if handle.startswith("@") else "@" + handle)
    ytdlp = [sys.executable, "-m", "yt_dlp", "--quiet", "--no-warnings"]
    ids = subprocess.run(
        [*ytdlp, "--flat-playlist", "--playlist-end", str(n), "--print", "id", url],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    out = []
    for vid in ids:
        r = subprocess.run(
            [*ytdlp, "--skip-download", "-J", "https://www.youtube.com/watch?v=" + vid],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            j = json.loads(r.stdout)
            out.append(
                {
                    "title": j.get("title"),
                    "description": j.get("description"),
                    "tags": j.get("tags") or [],
                }
            )
    return out


def estimate(mat, text, model):
    """What one call costs, roughly: 4 characters a token, a sheet ~1,600, ~1,500 written."""
    t = {
        "input": len(text) // 4 + (1600 if mat["sheet"] else 0) + len(WRITER) // 4,
        "output": 1500,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    return t, agent._price(model, t)


async def _main(a):
    f = films.Film(a.film) if os.path.isdir(a.film) else films.Film.open(a.film)
    if f is None:
        sys.exit("no such film: %s" % a.film)
    if a.sample:
        with open(a.sample, encoding="utf-8") as fh:
            raw = json.load(fh)
        channel = raw.get("channel") or {"id": "sample", "title": os.path.basename(a.sample)}
        recent = sample(raw.get("recent") if isinstance(raw, dict) else raw)
    elif a.sample_from:
        channel = {
            "id": re.sub(r"[^A-Za-z0-9_-]", "", a.sample_from) or "sample",
            "title": a.sample_from,
            "handle": a.sample_from,
        }
        recent = sample(sample_from(a.sample_from))
    else:
        channel, recent = {"id": "none", "title": "(a new channel)"}, []
    if a.save_sample:
        with open(a.save_sample, "w", encoding="utf-8") as fh:
            json.dump({"channel": channel, "recent": recent}, fh, indent=1, ensure_ascii=False)
    mat = material(f, a.events, sheet=True)
    if a.plan:
        shown = dict(mat, pieces=pieces_text(f.dir)[0])  # as _pick() asks it
        print(
            ask_text(shown, channel, [], "thumbs") + "\n\n=== and, at the same time, the words:\n"
        )
        text = ask_text(mat, channel, recent)
        t, usd = estimate(mat, text, a.model)
        print(text)
        print(
            "\n--- %d uploads, %d narration lines, %d sources, sheet %s; ~%d tokens in, ~$%.3f"
            % (
                len(recent),
                len(mat["narration"]),
                len(mat["sources"]),
                "yes" if mat["sheet"] else "no",
                t["input"],
                usd,
            )
        )
        return
    d = await write(f, channel, recent, a.auth, a.model, a.effort, a.events, record=False, mat=mat)
    if a.out:
        films._write_json(a.out, d)
    print("TITLE: %s\n\n%s\n\nTAGS: %s" % (d["title"], d["description"], ", ".join(d["tags"])))
    for t in d.get("thumbnails") or []:
        print(
            "THUMB: %6.2f s  %-8s %-11s %s"
            % (t["at"], t["layout"], t.get("place") or "-", t["words"])
        )
    if a.thumbs:
        rec = await thumbs.make(f, channel["id"], d)
        for o in rec["options"]:
            print("  %s  %s" % (f.path("outputs", o["path"]), "; ".join(o["notes"])))
    print(
        "\n--- %s effort %s: %.1f s, $%.4f%s"
        % (
            d["model"],
            d["effort"],
            d.get("seconds") or 0,
            d.get("cost_usd") or 0,
            ("; " + "; ".join(d["notes"])) if d["notes"] else "",
        )
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--film", required=True, help="a film id, or a film's folder")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sample", help='a JSON file: {"channel": {...}, "recent": [...]}')
    g.add_argument("--sample-from", help="a public channel's handle, read with yt-dlp")
    ap.add_argument("--save-sample", help="write the sample used to this JSON file")
    ap.add_argument("--events", help="the film's events, when not its own events.jsonl")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT)
    ap.add_argument("--auth", choices=("login", "api"), default="login")
    ap.add_argument("--out", help="also write the draft to this JSON file")
    ap.add_argument("--plan", action="store_true", help="print the ask and its price; call nothing")
    ap.add_argument("--thumbs", action="store_true", help="also make the thumbnail options")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
