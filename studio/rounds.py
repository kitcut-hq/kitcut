#!/usr/bin/env python
"""A round of changes to a finished film: its maker's notes, made by Claude into the film's next
version -- the same film, the same page, the same link.

    GET  /api/films/<id>/versions                the film's versions, and how a round stands
    POST /api/films/<id>/versions                {"key", "from", "notes": [...]}: make the next one
    POST /api/films/<id>/versions/stop           stop the round being made
    POST /api/films/<id>/versions/<n>/current    version n is the film again (no rendering)

    python studio/rounds.py <film-id> --notes notes.json [--plan]     a round by hand, beside the
                                                 server (on the VM: ops.sh notes <film-id> <file>)
    python studio/rounds.py <film-id> --where    its version and what that version is made of
                                                 (digest), for files taken to be changed by hand

A note points at a moment, a spot in the picture, a stretch, a line of the narration (described,
or rewritten) or the whole film. Claude gets them all at once, each with the frame it points at
and what is being said there, answers every one in a sentence (done, or not changed and why),
and the studio then mixes, renders and puts the new version online.

The film must stay what it is until the new version exists -- someone has it, and may be
watching it. So a round never works in the film's folder and never goes through
agent.make_film (whose failure path marks a film failed and takes its files off its page):

    <home>/rounds/<rid>/    a COPY of the film, where Claude changes what the notes ask for and
                            the studio mixes and renders; rid is <film id>.r<k>, k counting every
                            round asked of that film. A round that fails, is stopped or changes
                            nothing is that folder deleted: the film was never touched.
    online                  under the next revision's names (media.blob_of), before the swap
    the swap                the copy's files take the film's place and the film's own go to
                            versions/v<n>/ (renames, under a marker a restart can undo: heal);
                            then the record -- `version`, `versions`, the new addresses.

A version's files are in one place only: the film's folder while it is the film, versions/v<n>/
when it is not. So going back (use) is the same swap the other way, with nothing rendered, and
the master YouTube is sent is always the version on the page.

The film's record keeps `state: "done"` throughout. The round has its own document in
kitcut.studio_runs (`_id` rid, `kind: "round"`), which is what the site settles its credits on:
done, failed, cancelled, interrupted, or unchanged (Claude changed no file: no version).

Files changed by hand are a round too (`hand` in the POST, from this machine only: ops.sh take
and put). They are laid over the same copy, with no Claude, and become the next version by the
same swap -- so a hand's fix can be gone back from like any other, and never replaces a film it
was not made from. Two things hold that: the files say what they were taken from (the film's
digest then), and it must be what the film is when they come back; and no round, a hand's or
Claude's, swaps its copy in when the film's own files are not what its copy was made from. Until
2026-10-08 a hand wrote into the film's folder and rendered it there (resume.py --patched), and a
copy taken at version 1 erased its maker's version 2 while the page went on saying "version 2"
(KI-061).

A round lives in the memory of the server running it, as a redraw does (unbrand.py): the film's
record names that server in `round`, and a small file in <home>/rounds/_asked/ marks every film
with a round not yet over, so the leader can pick up one whose server went away (orphans).
"""

import os
import sys
import json
import stat
import time
import shutil
import asyncio
import hashlib
import contextlib
import subprocess
from datetime import datetime

import film as films
import live
import media
import peers
import store
import tools as toolbox
import unbrand
import youtube

ROOT = os.path.join(films.HOME, "rounds")  # <rid>/: the copy a round works on
MARKS = os.path.join(ROOT, "_asked")  # <film id>.json: a round asked for, not yet over
HAND = os.path.join(ROOT, "_hand")  # <film id>/: files changed by hand, sent to be a version
KEPT = "versions"  # in the film: v<n>/, the files of a version that is not the film now
SWAP = ".swap.json"  # in versions/: a swap under way, for heal()
# what is the film's own whatever version it shows: never copied for a round, never swapped
OWN = (
    "studio.json",
    "events.jsonl",
    "temp",
    "notes",
    KEPT,
    "library",
    "share",
    "youtube",
    "project.json",
    "journal.md",
)
# what each round spends is the round's (its own budget and its own cost), not the film's again
SPENT = (("audio", "vo", "spend.jsonl"), ("images", "spend.jsonl"), ("rigs", "spend.jsonl"))
ACTIVE = ("queued", "running", "finishing")
KINDS = ("moment", "spot", "stretch", "line", "film")
MAX_NOTES = None  # a round takes as many notes as its maker has (it took 20 until 2026-11-24)
NOTE_MAX = None  # a note, and a line as it should be said, as long as its maker writes it (500 until 2026-11-24)
PER_DAY = int(os.environ.get("STUDIO_ROUNDS_PER_DAY") or 5)  # rounds a film may have in a day
TRIES = 2  # how often a round is started again after its server went away
KEEP = 3  # versions whose files are kept beside the film's own; older ones stay watchable online
SUMMARY_MAX = 600  # characters of what a hand says its files change
STALE = (
    "The film is not what these files were taken from: it has changed since (it is at version "
    "%d). Take it again and put your changes on top of it."
)
MOVED = (
    "The film's own files changed while this version was being made, so it was not put in "
    "their place. The film is as it was found; make the version again from it."
)
EFFORT = "high"  # a round changes a film that exists: it reads more than it invents
WHOLE_S = 10 * 60  # working time a note on the whole film adds to what every note has
NOTE_S = 2 * 60  # ... what every note has
# ... and what a note adds for each second of the film it covers, up to REACH_MAX_S: a note on a
# 69-second stretch that needed a head turn drawn for four cats had the same one minute as a note
# on a two-second paw, and came back "I ran out of working time" (ch7tno.r2, 2026-11-24)
REACH_S, REACH_MAX_S = 8, 10 * 60
MORE = 2  # further passes a round gets for notes its first left unanswered
# the frames a note comes with: its own moment, and for a stretch one about every FRAME_EVERY
# seconds from its start to its end (a moment: LEAD seconds before and after as well)
LEAD, FRAME_EVERY, FRAMES_MAX, FRAMES_ALL = 0.5, 8.0, 8, 72
HISTORY = "history.jsonl"  # in versions/: every round's notes and what was answered, a line each
EARLIER = 3  # rounds of them the next round is told
CHECK_NOTES, CHECK_ROWS, CHECK_S = 5, 3, 240  # the second look: notes a call, rows a note, its time
STRIP = (24, 160)  # the filmstrip: tiles in a row, and a tile's width in px
STRIP_FILE = "strip.jpg"
RING = (217, 115, 63)  # the colour a note's spot is ringed in on its frame
AREA_MIN = 0.02  # a boxed area is at least this much of the picture each way

JOBS = {}  # film id -> the round being made here
# A round asked for with `refresh` (the project's Scenes and Cast: "Update episodes") has no notes
# of its maker's: the project's newest versions of the members named are laid over the round's
# copy (lay_over), and this one note of the studio's asks Claude to make the film use them and
# change nothing else. An episode keeps its own copy of the cast (library.seed copies by value),
# so this is how a scene or character changed in the project reaches an episode already made.
REFRESH_NOTE = "refresh"
# a round on an episode whose series changed some of its cast since: the newest are in its copy
BROUGHT = (
    "\n\nSince this episode was made, its series changed some of what it draws. This round's copy "
    "already has their newest versions, in place of the ones it had:\n%s\n"
    "They are part of this version whatever the notes say. After the notes, `stills` of every "
    "shot each is in, and look: does it sit right (where characters stand on a changed scene, "
    "their size, what they lean on)? Fix the staging in film.js where it does not; never put an "
    "old version back. Say in your summary, in a short sentence, that the episode now has them.\n"
)
# after library.BODY_RULES, in a round: its changes to the cast do not stay in this film
BODY_ROUND = (
    "\nWhat you change in cast/ (a character's file or the body) is saved to the series when "
    "this round is done, and every later episode gets it: so a fix a note asks for that is true "
    "of the character everywhere (how it looks, how it moves) belongs there, and one that is "
    "only this shot's (where it stands, what it does now) belongs in film.js.\n"
)
REFRESH = (
    "The project's maker changed %(what)s since this film was made, and wants this film to use "
    "%(them)s as %(they)s now. The new %(versions)s already in this folder%(where)s. Make the "
    "film show %(them)s as %(they)s now, and change nothing else: the same scenes, timing, "
    "words and music.%(drawn)s%(painted)s Then `stills` of every shot %(they_in)s in, and look: "
    "is it the new one, does it sit right, and is everything around it as it was?"
)
REFRESH_DRAWN = (
    " A drawn one: film.js must draw it through SK.cast.<name>; where the film drew its own "
    "copy of it inline, draw the cast member there instead, at the same place and size."
)
REFRESH_PAINTED = (
    " A painted one: every painting whose ref names it is painted again from the new picture "
    "(`paint` with retake, those paintings only); the other paintings stay."
)
# what Claude is doing, as the round's person reads it: the log's own lines (agent._describe)
# name files and tools, which mean nothing to them
PLAIN = (
    ("read notes/", "Looking at your notes"),
    ("read ", "Reading the film"),
    ("edited film.js", "Changing the picture"),
    ("wrote film.js", "Changing the picture"),
    ("edited vo.json", "Changing the words"),
    ("wrote vo.json", "Changing the words"),
    ("edited score.json", "Changing the music"),
    ("wrote score.json", "Changing the music"),
    ("edited sfx.json", "Changing the sounds"),
    ("wrote sfx.json", "Changing the sounds"),
    ("edited paint.json", "Changing a painting"),
    ("edited ", "Changing the film"),
    ("wrote ", "Changing the film"),
    ("checking film.js", "Checking the film still runs"),
    ("rendering the soundtrack", "Listening to the new mix"),
    ("rendering ", "Looking at the changed frames"),
    ("looking at ", "Looking at the changed frames"),
    ("checking the cuts", "Checking the motion"),
    ("recording ", "Recording the new line"),
    ("repainting ", "Painting a picture again"),
    ("searching the web", "Looking something up"),
    ("reading http", "Looking something up"),
)


def plain(text):
    """A log line as a sentence for the round's person, or None to keep the one before."""
    return next((say for head, say in PLAIN if str(text or "").startswith(head)), None)


class RoundError(Exception):
    def __init__(self, status, text, reason=None):
        super().__init__(text)
        self.status, self.text, self.reason = status, text, reason


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _mmss(t):
    t = max(0.0, round(float(t), 1))
    return "%d:%04.1f" % (t // 60, t % 60)


# ------------------------------------------------------------------ what a round may spend
def wide(notes):
    """How many of the notes are about the whole film: each is a change to every shot it
    touches, and every one of those shots has to be looked at again."""
    return sum(1 for n in notes if n.get("kind") == "film")


def lay_over(work, names):
    """The project's newest versions of these members into a round's copy, over the film's own:
    a drawn one as cast/<name>.js, a painted one as inputs/cast_<name>.<ext> (and the manifest's
    images). -> {"drawn": [names], "painted": [names]}; a member the project no longer has is
    left as the film has it."""
    import library

    lib = library.lib_of(work.record())
    got = {"drawn": [], "painted": []}
    if not lib:
        return got
    idx, d = library.load(lib), library.dir_of(lib)
    man = None
    for n in names:
        e = idx["cast"].get(n)
        if not e or e.get("deleted"):
            continue
        if e.get("painted"):
            src = os.path.join(d, "cast", n, "v%d.%s" % (e["version"], e.get("ext")))
            if not os.path.exists(src):
                continue
            os.makedirs(work.path("inputs"), exist_ok=True)
            for x in library.PICTURE_EXT:
                with contextlib.suppress(OSError):
                    os.remove(work.path("inputs", "cast_%s.%s" % (n, x)))
            rel = "inputs/cast_%s.%s" % (n, e["ext"])
            shutil.copyfile(src, work.path(*rel.split("/")))
            if man is None:
                with open(work.manifest, encoding="utf-8") as f:
                    man = json.load(f)
            man.setdefault("images", {})["cast_" + n] = rel
            got["painted"].append(n)
        else:
            src = os.path.join(d, "cast", n, "v%d.js" % e["version"])
            if not os.path.exists(src):
                continue
            os.makedirs(work.path("cast"), exist_ok=True)
            shutil.copyfile(src, work.path("cast", n + ".js"))
            got["drawn"].append(n)
    if man is not None:
        films._write_json(work.manifest, man)
    return got


def bring_up(work):
    """The members a round's copy draws in an older version than its series has now (library.
    behind), laid over with the newest -- the ones the episode never changed itself (have: None
    is its own copy, kept). [{name, have, now}] as brought."""
    import library

    got = [b for b in library.behind(work) if b["have"] is not None]
    if got:
        lay_over(work, [b["name"] for b in got])
    return got


def refresh_notes(film, names):
    """The one note of a refresh round, for these members of the film's project; raises
    RoundError when the film is no episode, or names nothing its project has."""
    import library

    rec = film.record()
    lib = library.lib_of(rec) if (rec.get("project") or {}).get("id") else None
    if not lib:
        raise RoundError(409, "This film is not an episode of a project.", "project")
    if not isinstance(names, list) or not names or len(names) > 8:
        raise RoundError(400, "refresh is a list of up to 8 names.")
    cast = library.load(lib)["cast"]
    have = [
        n for n in dict.fromkeys(str(x) for x in names) if n in cast and not cast[n].get("deleted")
    ]
    if len(have) != len(set(map(str, names))):
        raise RoundError(404, "The project has no such scene or character.", "member")
    drawn = [n for n in have if not cast[n].get("painted")]
    painted = [n for n in have if cast[n].get("painted")]
    one = len(have) == 1
    where = []
    if drawn:
        where.append("cast/<name>.js for %s" % ", ".join(drawn))
    if painted:
        where.append("inputs/cast_<name>.* for %s" % ", ".join(painted))
    text = REFRESH % {
        "what": ", ".join("@" + n for n in have),
        "them": "it" if one else "them",
        "they": "it is" if one else "they are",
        "they_in": "it is" if one else "they are",
        "versions": "version is" if one else "versions are",
        "where": " (%s)" % "; ".join(where),
        "drawn": REFRESH_DRAWN if drawn else "",
        "painted": REFRESH_PAINTED if painted else "",
    }
    return have, [{"id": REFRESH_NOTE, "kind": "film", "text": text}]


def weight(notes):
    """The working time the notes' reach adds, in seconds: a note on a long stretch is a change
    to every shot in it."""
    s = 0.0
    for n in notes:
        if n.get("kind") in ("stretch", "line") and n.get("t2") is not None:
            s += min(REACH_MAX_S, max(0.0, float(n["t2"]) - float(n.get("t") or 0)) * REACH_S)
    return int(round(s))


def limits(length, notes, whole=0, model=None, reach=0):
    """A round's allowance: Claude's working time by its notes (how many, and `reach`: what
    they cover, weight), half the film's budget. A note on the whole film (`whole` of them) is
    not one change but one in every shot: 12 minutes for four notes, one of them "keep Dad out
    of the wide views and do not jump between close and far", reframed a 210-second film and
    stopped before the last shots were looked at; the version went out with a character blinking
    out of one of them (fhkoaw.r1, 2026-10-09). The time is what a careful change takes, not a
    price: its maker's own time, sending a note twice, costs more than Claude's."""
    lim = films.limits(length, model)  # the round's own model: a Fable round may spend twice
    work = min(
        (60 + (10 if whole else 0)) * 60, 8 * 60 + NOTE_S * notes + int(reach) + WHOLE_S * whole
    )
    return lim | {
        "claude_s": work,
        "wall_s": work + 30 * 60,
        "budget_usd": max(2.0, round(lim["budget_usd"] / 2, 2)),
        "reserve_usd": round(max(1.0, lim["reserve_usd"] / 2), 2),
    }


def claude_of(rec):
    """The Claude model and effort a round was asked with (kitcut.ai's Edit film menus, paid
    plans): {"model"?, "effort"?}, only what is valid; {} for the studio's own."""
    c = (rec.get("round") or {}).get("claude") or {}
    return {
        **({"model": c["model"]} if c.get("model") in films.CLAUDE_MODELS else {}),
        **({"effort": c["effort"]} if c.get("effort") in films.EFFORTS else {}),
    }


def reserve(film, notes, auth, model=None):
    """What a round may still spend, held against the day's budget (server.reserve, halved)."""
    lim = limits(film.length, notes, model=model)
    return lim["reserve_usd"] if auth == "api" else 0.005 * film.length


# ------------------------------------------------------------------ what the film's record says
def version_of(rec):
    return int(rec.get("version") or 1)


def words(rec, fresh=False):
    """May a round change what is said, or record a line again? Not where nothing is said. In a
    person's own ElevenLabs voice only with a fresh pass to it (`fresh`: the site mints one, as
    for a translation, and sends it as the round's `voice`; the film's making's has run out):
    without one the answer is own_voice with `with_pass`, so the site knows to send one."""
    if rec.get("narration") is False:
        return {"can": False, "why": "no_voice"}
    if (rec.get("narrator") or {}).get("source") == "elevenlabs" and not fresh:
        return {"can": False, "why": "own_voice", "with_pass": True}
    return {"can": True}


VOICE_PASS = "round-voice.json"  # in the film's temp/: the pass a round was asked with (0600)


def keep_pass(film, narrator):
    """Keep the fresh pass to the film's own ElevenLabs voice a round was asked with in the
    film's temp/ (never in the record), for copy_of to give the round's copy. Raises RoundError
    when the film is not told in that voice."""
    own = film.record().get("narrator") or {}
    if own.get("source") != "elevenlabs":
        raise RoundError(
            409, "This film is not told in an ElevenLabs voice of its own.", "own_voice"
        )
    if (narrator or {}).get("voice") != own.get("voice"):
        raise RoundError(
            409, "The voice asked with is not the one this film is told in.", "own_voice"
        )
    os.makedirs(film.path("temp"), exist_ok=True)
    p = film.path("temp", VOICE_PASS)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump({"grant": narrator["grant"]}, f)


def can_voice(work):
    """Whether a round's copy may record: its record allows it, with the pass it was given."""
    return words(work.record(), fresh=work.own_voice() is not None)["can"]


def rounds_today(rec):
    today = datetime.now().date().isoformat()
    return sum(1 for t in rec.get("round_days") or [] if str(t).startswith(today))


def public(rec):
    """What the site is told of a film's versions (GET .../versions, and the film's document in
    studio_runs carries the same `version`, `versions` and `words`)."""
    r = rec.get("round") or {}
    return {
        "version": version_of(rec),
        "versions": rec.get("versions") or [],
        "round": {k: r.get(k) for k in ("id", "n", "state", "now", "started_at")}
        if r.get("state") in ACTIVE
        else None,
        "words": words(rec),
        "limits": {"rounds_left": max(0, PER_DAY - rounds_today(rec))},
        # the round last asked for, however it ended, with Claude's answer to each note
        "last": {k: r.get(k) for k in ("id", "n", "state", "error", "summary", "answers")}
        if r.get("id")
        else None,
    }


def in_flight():
    """The films with a round being made (or queued) on this server, for its heartbeat."""
    return [fid for fid, j in JOBS.items() if j["task"] is not None and not j["task"].done()]


def mine():
    """This server's rounds as its films are told to the others (server.mine): each takes one of
    its person's films-at-once places and holds its reserve against the day's budget."""
    return [
        {
            "id": j["rid"],
            "client": j["client"],
            "status": "queued" if j["state"] == "queued" else "running",
            "reserve": j["reserve"],
            "cost_usd": j.get("cost_usd") or 0,
        }
        for fid, j in JOBS.items()
        if fid in in_flight()
    ]


# ------------------------------------------------------------------ the marks
def _mark(fid):
    return os.path.join(MARKS, fid + ".json")


def _set_mark(fid):
    with contextlib.suppress(OSError):
        os.makedirs(MARKS, exist_ok=True)
        with open(_mark(fid), "w", encoding="utf-8") as f:
            json.dump({"film": fid, "server": peers.SERVER_ID, "t": time.time()}, f)


def _drop_mark(fid):
    for p in (_mark(fid), _mark(fid) + ".stop"):
        with contextlib.suppress(OSError):
            os.remove(p)


def orphans():
    """The films whose round's server is gone: [film]. Marks whose round is over are forgotten."""
    out = []
    with contextlib.suppress(OSError):
        for name in sorted(os.listdir(MARKS)):
            if not name.endswith(".json"):
                continue
            fid = name[: -len(".json")]
            f = films.Film.open(fid)
            r = (f.record().get("round") or {}) if f is not None else {}
            if r.get("state") not in ACTIVE:
                _drop_mark(fid)
            elif fid not in in_flight() and not peers.alive(r.get("server")):
                out.append(f)
    return out


# ------------------------------------------------------------------ the notes, checked
def clean_notes(film, notes, fresh=False):
    """The notes as the studio keeps them: [{id, kind, t, t2, x, y, w, h, line, was, words, text}],
    times inside the film. Raises RoundError for what cannot be a round. `fresh`: the round
    comes with a pass to the film's own ElevenLabs voice (words)."""
    rec = film.record()
    if not isinstance(notes, list) or not notes:
        raise RoundError(400, "Send the notes: a list of at least one.")
    length, lines = float(film.length), timeline(film)
    out, seen = [], set()
    for raw in notes:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            raise RoundError(400, "A note has a kind: %s." % ", ".join(KINDS))
        nid = str(raw.get("id") or "")[:64]
        if not nid or nid in seen:
            raise RoundError(400, "Every note has its own id.")
        seen.add(nid)
        n = {"id": nid, "kind": raw["kind"], "text": str(raw.get("text") or "").strip()[:NOTE_MAX]}
        if n["kind"] in ("moment", "spot", "stretch"):
            try:
                n["t"] = round(min(length, max(0.0, float(raw["t"]))), 2)
            except (KeyError, TypeError, ValueError):
                raise RoundError(400, "A note at a moment says when: t, in seconds.") from None
        if n["kind"] == "spot":
            try:
                n["x"] = round(min(1.0, max(0.0, float(raw["x"]))), 3)
                n["y"] = round(min(1.0, max(0.0, float(raw["y"]))), 3)
            except (KeyError, TypeError, ValueError):
                raise RoundError(400, "A note on a spot says where: x and y, 0 to 1.") from None
            # an area boxed on the picture: its width and height around that spot (both, or it
            # is a point)
            try:
                w, h = float(raw["w"]), float(raw["h"])
            except (KeyError, TypeError, ValueError):
                w = h = 0.0
            if w > 0 and h > 0:
                n["w"] = round(min(1.0, max(AREA_MIN, w)), 3)
                n["h"] = round(min(1.0, max(AREA_MIN, h)), 3)
        if n["kind"] == "stretch":
            try:
                n["t2"] = round(min(length, max(n["t"], float(raw["t2"]))), 2)
            except (KeyError, TypeError, ValueError):
                raise RoundError(400, "A note on a stretch says where it ends: t2.") from None
        if n["kind"] == "line":
            ln = next((x for x in lines if x.get("i") == raw.get("line")), None)
            if ln is None:
                raise RoundError(409, "The film has no such line now.", "stale")
            n.update(line=ln["i"], was=ln["text"], t=ln["start"], t2=ln["end"])
            said = str(raw.get("words") or "").strip()[:NOTE_MAX]
            if said and said != ln["text"]:
                n["words"] = said
            if not words(rec, fresh)["can"]:
                raise RoundError(
                    409, "The words of this film cannot be changed in a round yet.", "words"
                )
        if not n["text"] and not n.get("words"):
            raise RoundError(400, "A note says what should change.")
        out.append(n)
    return out


def timeline(film):
    """The narration's lines as recorded: [{i, text, start, end, words: [{text, s, e}]}]."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            return [x for x in json.load(f).get("lines") or [] if isinstance(x, dict)]
    except (OSError, ValueError):
        return []


def lines_of(film):
    """A version's narration for the page: each line's words and when it is said."""
    return [
        {
            "i": x.get("i", i),
            "text": str(x.get("text") or ""),
            "start": round(float(x.get("start") or 0), 2),
            "end": round(float(x.get("end") or 0), 2),
        }
        for i, x in enumerate(timeline(film))
    ]


# ------------------------------------------------------------------ a version's entry
def _probe(mp4):
    """(seconds, width, height, frames a second) of a video, or None."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0"]
        + ["-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", mp4],
        capture_output=True,
        text=True,
    )
    try:
        j = json.loads(r.stdout)
        a, b = j["streams"][0]["r_frame_rate"].split("/")
        s = j["streams"][0]
        return (
            float(j["format"]["duration"]),
            int(s["width"]),
            int(s["height"]),
            float(a) / float(b),
        )
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        return None


def make_strip(outputs):
    """outputs/strip.jpg: the film from end to end as one row of STRIP[0] small frames, for the
    notes' filmstrip (the page may not read a video's pixels off another host, so it cannot make
    its own). Each frame is sought, not the whole film decoded: two seconds for any length.
    Returns {"count", "w", "h"}, or None when there is no video to cut it from."""
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image

    src = next(
        (
            p
            for p in (os.path.join(outputs, n) for n in ("film_web.mp4", "film.mp4"))
            if os.path.isfile(p)
        ),
        None,
    )
    got = _probe(src) if src else None
    if not got:
        return None
    secs, w, h, _ = got
    count, tw = STRIP
    th = max(2, round(tw * h / w / 2) * 2)

    def frame(i):
        t = (i + 0.5) / count * secs
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", src, "-frames:v", "1"]
            + ["-vf", "scale=%d:%d" % (tw, th), "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True,
        )
        return r.stdout if r.returncode == 0 else b""

    import io

    with ThreadPoolExecutor(max_workers=6) as pool:
        frames = list(pool.map(frame, range(count)))
    row = Image.new("RGB", (tw * count, th), (20, 16, 12))
    for i, data in enumerate(frames):
        if data:
            with contextlib.suppress(Exception):
                row.paste(Image.open(io.BytesIO(data)).convert("RGB"), (i * tw, 0))
    tmp = os.path.join(outputs, STRIP_FILE + ".%d.tmp" % os.getpid())
    row.save(tmp, "JPEG", quality=80, optimize=True)
    os.replace(tmp, os.path.join(outputs, STRIP_FILE))
    return {"count": count, "w": tw, "h": th}


def entry_of(film, n, outputs=None, urls=None, rev=None, summary=None, rid=None):
    """What `versions` says of version n, from the film's files (or a round's copy of them)."""
    rec = film.record()
    outputs = outputs or film.path("outputs")
    got = _probe(os.path.join(outputs, "film.mp4")) or (float(film.length), 16, 9, 60.0)
    strip = None
    if os.path.isfile(os.path.join(outputs, STRIP_FILE)):
        from PIL import Image

        with Image.open(os.path.join(outputs, STRIP_FILE)) as im:
            strip = {"count": STRIP[0], "w": im.width // STRIP[0], "h": im.height}
    return {
        "n": n,
        "at": _now(),
        "rev": (rec.get("media_rev") or 0) if rev is None else rev,
        "duration": float(film.length),
        "video_s": round(got[0], 2),
        "fps": round(got[3]),
        "frame": rec.get("frame") or "16:9",
        "media": dict(rec.get("media") or {}) if urls is None else dict(urls),
        "strip": strip,
        "lines": lines_of(film),
        "summary": summary,
        "round": rid,
        "kept": True,
    }


async def prepare(film):
    """Make sure the film's current version has its entry in `versions` -- a film made before
    rounds has none -- with its filmstrip, online when copying is on. The record, as public()
    reads it. The entry follows the film's files when they were drawn again (unbrand.py)."""
    import agent  # here, not at the top: agent imports this module's siblings as it loads

    rec = film.record()
    n, vs = version_of(rec), list(rec.get("versions") or [])
    cur = next((v for v in vs if v.get("n") == n), None)
    rev = rec.get("media_rev") or 0
    if cur is not None and cur.get("rev") == rev and cur.get("strip"):
        return rec
    out = film.path("outputs")
    if not os.path.isfile(os.path.join(out, STRIP_FILE)) or (
        cur is not None and cur.get("rev") != rev
    ):
        if not any(os.path.isfile(os.path.join(out, x)) for x in media.LOCAL):
            await asyncio.to_thread(media.bring_back, film, "film_web.mp4")
        await asyncio.to_thread(make_strip, out)
    fresh = entry_of(film, n)
    url = await media.publish_one(film, STRIP_FILE, "image/jpeg")
    if url:
        fresh["media"]["strip"] = url
    if cur is not None:  # what a round said of it stays
        fresh.update({k: cur[k] for k in ("at", "summary", "round") if cur.get(k) is not None})
    vs = sorted([v for v in vs if v.get("n") != n] + [fresh], key=lambda v: v["n"])
    rec = film.update(version=n, versions=vs)
    # the film's document says what its pages need without asking: its words
    told = {"version": n, "versions": vs, "words": words(rec)}
    await agent.save(film.id, told)
    return rec


# ------------------------------------------------------------------ the copy a round works on
def work_dir(rid):
    return os.path.join(ROOT, rid)


def copy_of(film, rid, notes):
    """<home>/rounds/<rid>/: the film as it stands, for the round to change. Everything a version
    is made of is copied (not its master: the round renders its own); what each tool spent so
    far is left behind, so the round's allowance and its cost are its own. Its record is the
    film's, with what must not move pinned to what the film was made with (`pins`): the voice's
    model and the painter's, which are today's for a new film and this film's for a round --
    or a changed default would record every line again in another voice."""
    d = work_dir(rid)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for name in sorted(os.listdir(film.dir)):
        # library/: what the film was given to read (its person's cast and earlier films), the
        # film's own and never swapped, but there for Claude as it was when the film was made
        if (name in OWN and name != "library") or name == "outputs":
            continue
        src, dst = film.path(name), os.path.join(d, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    os.makedirs(os.path.join(d, "outputs"))
    for name in ("film.srt", "film.vtt"):  # the captions: the narration's, kept when it is
        with contextlib.suppress(OSError):
            shutil.copy2(film.path("outputs", name), os.path.join(d, "outputs", name))
    _ours(d)
    if (film.record().get("round") or {}).get("voice"):  # asked with a pass to its own voice
        with contextlib.suppress(OSError):
            os.makedirs(os.path.join(d, "temp"), exist_ok=True)
            shutil.copy2(film.path("temp", VOICE_PASS), os.path.join(d, "temp", "voice.json"))
    for parts in SPENT:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(d, *parts))
    work = films.Film(d)
    rec = dict(film.record())
    chosen = claude_of(rec)  # the round's own model and effort, never the film's
    for k in ("server", "media", "media_rev", "share", "unbrand", "round", "versions", "version"):
        rec.pop(k, None)
    for k in ("model", "effort"):  # the film's own (made with Fable): not the round's to inherit
        rec.pop(k, None)
    rec.update(chosen)
    for k in ("claude_session", "session", "waiting", "resume", "listed", "hidden"):
        rec.pop(k, None)
    rec.update(
        state="claude",
        prompt=rec.get("prompt") or "(a round of changes)",  # never asked to name the film
        round_of={"film": film.id, "rid": rid, "notes": len(notes)},
        pins=_pins(work, rec),
    )
    films._write_json(work.path("studio.json"), rec)
    # the Free plan's closing comes back for the final render (finish): Claude's frames are the film's
    with open(work.manifest, encoding="utf-8") as f:
        m = json.load(f)
    if m.pop("tail", None) is not None:
        films._write_json(work.manifest, m)
    return work


def _ours(d):
    """Everything under `d` may be written by this user. A copy keeps its source's permissions,
    and a film can carry read-only files (one scaffolded from a release, whose files are): the
    round's copy is the round's to change, and to remove."""
    for root, dirs, files in os.walk(d):
        for n in dirs:
            p = os.path.join(root, n)
            with contextlib.suppress(OSError):
                os.chmod(p, os.stat(p).st_mode | stat.S_IRWXU)
        for n in files:
            p = os.path.join(root, n)
            with contextlib.suppress(OSError):
                os.chmod(p, os.stat(p).st_mode | stat.S_IRUSR | stat.S_IWUSR)


def _pins(work, rec):
    """What the film's own vo.json and paint.json say where the studio decides (Film.vo_pins,
    film.paint_pins): frozen for the round."""

    def read(name):
        try:
            with open(work.path(name), encoding="utf-8") as f:
                got = json.load(f)
            return got if isinstance(got, dict) else {}
        except (OSError, ValueError):
            return {}

    probe = films.Film(work.dir)
    probe.record = lambda: rec  # the pins as a new film of this record would get them
    vo, paint = read("vo.json"), read("paint.json")
    pins = {"vo": {k: vo.get(k, v) for k, v in probe.vo_pins().items()}}
    if films.paint_kinds(probe.caps):
        want = films.paint_pins(
            float(rec.get("length") or work.length),
            probe.caps,
            rec.get("paint_route"),
            rec.get("paint_quality"),
        )
        pins["paint"] = {
            k: paint.get(k, v)
            for k, v in want.items()
            # a film painted before its route had a quality keeps painting without one: with it,
            # every picture's fingerprint would change and a round would repaint them all
            if k != "quality" or k in paint or not paint
        }
    return pins


def digest(film):
    """A fingerprint of what a version is made of (what Claude may write, and the narration as
    recorded): the same before and after a round means it changed nothing."""
    h = hashlib.sha256()
    names = list(film.editable()) + ["sketch.json"]
    for sub in ("cast", "engine", "scenes"):
        if os.path.isdir(film.path(sub)):
            names += [sub + "/" + n for n in sorted(os.listdir(film.path(sub)))]
    for name in sorted(set(names)):
        with contextlib.suppress(OSError):
            with open(film.path(*name.split("/")), "rb") as f:
                h.update(name.encode() + b"\0" + f.read())
    for ln in timeline(film):
        h.update(
            ("%s|%s|%.2f\n" % (ln.get("i"), ln.get("text"), float(ln.get("end") or 0))).encode()
        )
    return h.hexdigest()


def where(film):
    """Where a film stands, for whoever takes its files to change by hand: the version it is
    at, and what that version is made of."""
    rec = film.record()
    r = rec.get("round") or {}
    return {
        "film": film.id,
        "state": rec.get("state"),
        "version": version_of(rec),
        "digest": digest(film),
        "round": r.get("state") if r.get("state") in ACTIVE else None,
    }


# ------------------------------------------------------------------ files changed by hand
def _hand_files(d):
    """The files under `d`, as paths from it with forward slashes."""
    out = []
    for root, _dirs, names in os.walk(d):
        rel = os.path.relpath(root, d).replace(os.sep, "/")
        out += [n if rel == "." else rel + "/" + n for n in names]
    return sorted(out)


def clean_hand(film, hand):
    """Files changed by hand, checked before they may be a round: {dir, base, summary, files}.
    The files are where ops.sh put leaves them, HAND/<film id>/, as they lie in a film (the
    place is the studio's to name: no path is taken from the request); `base` is the film's digest when they were taken, and must be the film's now -- the
    comparison is of what the film is made of, not of a version's number, so a film rendered
    again in place is caught as one changed from notes is. Raises RoundError."""
    if not isinstance(hand, dict):
        raise RoundError(400, 'hand is {"base", "summary"}.')
    d = os.path.join(HAND, film.id)
    files = _hand_files(d) if os.path.isdir(d) else []
    if not files:
        raise RoundError(400, "No changed files were sent (%s is empty)." % d)
    own = sorted({n.split("/")[0] for n in files} & (set(OWN) | {"outputs"}))
    if own:
        raise RoundError(
            400,
            "Not a version's to change: %s (the film's own, whatever it shows)." % ", ".join(own),
        )
    summary = " ".join(str(hand.get("summary") or "").split())[:SUMMARY_MAX]
    if not summary:
        raise RoundError(400, "Say what is different in this version: its maker reads it.")
    base = str(hand.get("base") or "")
    if base != digest(film):
        raise RoundError(409, STALE % version_of(film.record()), "stale")
    return {"dir": d, "base": base, "summary": summary, "files": files}


def overlay(work, d):
    """The hand's files laid over the round's copy of the film, each where it lies."""
    for name in _hand_files(d):
        dst = work.path(*name.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(d, *name.split("/")), dst)
    _ours(work.dir)


def _said_differently(film, work):
    """Whether the copy's narration script is not the film's: its lines are recorded again."""

    def read(f):
        try:
            with open(f.path("vo.json"), "rb") as fh:
                return fh.read()
        except OSError:
            return b""

    return read(film) != read(work)


# ------------------------------------------------------------------ the notes, for Claude
def _where(x, y):
    col = "left" if x < 0.33 else "right" if x > 0.66 else "centre"
    row = "top" if y < 0.33 else "bottom" if y > 0.66 else "middle"
    spot = "the centre" if (row, col) == ("middle", "centre") else "the %s %s" % (row, col)
    return "%s of the picture (%d%% from the left, %d%% from the top)" % (
        spot,
        round(x * 100),
        round(y * 100),
    )


def _area(n):
    """A boxed area in words: where its middle is, and how much of the picture it takes."""
    return "the box around %s, %d%% of the picture wide and %d%% tall" % (
        _where(n["x"], n["y"]),
        round(n["w"] * 100),
        round(n["h"] * 100),
    )


def _box(n, width, height):
    """A boxed area's corners on a frame of this size, kept inside it."""
    x0, x1 = (n["x"] - n["w"] / 2) * width, (n["x"] + n["w"] / 2) * width
    y0, y1 = (n["y"] - n["h"] / 2) * height, (n["y"] + n["h"] / 2) * height
    return max(0, x0), max(0, y0), min(width - 1, x1), min(height - 1, y1)


def said_at(lines, t, t2=None):
    """What is being said at t (or between t and t2), in a sentence for the notes, or ""."""
    t2 = t if t2 is None else t2
    on = [x for x in lines if float(x.get("start") or 0) <= t2 and float(x.get("end") or 0) >= t]
    if not on:
        return "Nothing is being said there."
    parts = []
    for ln in on[:3]:
        word = ""
        if t2 == t:
            w = next(
                (
                    w
                    for w in ln.get("words") or []
                    if float(w.get("s") or 0) <= t <= float(w.get("e") or 0) + 0.15
                ),
                None,
            )
            word = ', at the word "%s"' % w["text"] if w and w.get("text") else ""
        parts.append('line %s ("%s")%s' % (ln.get("i"), ln.get("text"), word))
    return "Being said: " + "; ".join(parts) + "."


def frame_time(n):
    """The moment of the film a note's frame is drawn at, or None for a note on the whole film."""
    if n["kind"] == "film":
        return None
    return round((n["t"] + n["t2"]) / 2, 2) if n.get("t2") is not None else n["t"]


def frame_times(n, length):
    """Every moment a note's frames are drawn at, its own (frame_time) first: a moment with one
    a little before and after it, a stretch from its start to its end. A note's time is where its
    maker saw the thing, and one frame from the middle of a stretch showed neither where it
    begins nor that it is the same in every shot."""
    main = frame_time(n)
    if main is None:
        return []
    t, t2 = n["t"], n.get("t2")
    if t2 is None or t2 - t < 2 * LEAD:
        ts = [main - LEAD, main + LEAD]
    else:
        k = min(FRAMES_MAX, max(3, int((t2 - t) // FRAME_EVERY) + 2))
        ts = [t + (t2 - t) * i / (k - 1) for i in range(k)]
    out = [main]
    for x in ts:
        x = round(min(float(length), max(0.0, x)), 2)
        if all(abs(x - y) > 0.05 for y in out):
            out.append(x)
    return out


def _thin(per, cap=FRAMES_ALL):
    """[[times]] a note, cut to `cap` frames in all: every note keeps its own moment, and the
    longest lists lose their last frames first."""
    per = [list(ts) for ts in per]
    while sum(map(len, per)) > cap:
        longest = max(per, key=len)
        if len(longest) <= 1:
            break
        longest.pop()
    return per


def _frames_of(got):
    """A note's frames as [(seconds or None, path)], its own first: what pack returns, or the
    one path it returned before a note had several."""
    if isinstance(got, str):
        return [(None, got)]
    return [(x[0], x[1]) for x in got or []]


def notes_text(notes, lines, frames):
    """The notes as Claude reads them (its first message, and notes/notes.md)."""
    out = []
    for i, n in enumerate(notes, 1):
        if n["kind"] == "film":
            head = "the whole film"
        elif n["kind"] == "spot" and n.get("w"):
            head = "at %s, an area: %s" % (_mmss(n["t"]), _area(n))
        elif n["kind"] == "spot":
            head = "at %s, a spot: %s" % (_mmss(n["t"]), _where(n["x"], n["y"]))
        elif n["kind"] == "stretch":
            head = "from %s to %s" % (_mmss(n["t"]), _mmss(n["t2"]))
        elif n["kind"] == "line":
            head = "the words of line %s, said from %s to %s" % (
                n["line"],
                _mmss(n["t"]),
                _mmss(n["t2"]),
            )
        else:
            head = "at %s" % _mmss(n["t"])
        body = ["%d. [%s]" % (i, head)]
        if n.get("words"):
            body.append('   Say this instead: "%s"' % n["words"])
            body.append('   It says now: "%s"' % n["was"])
        if n["text"]:
            body.append("   " + n["text"].replace("\n", "\n   "))
        if n["kind"] in ("moment", "spot", "stretch"):
            body.append("   " + said_at(lines, n["t"], n.get("t2")))
        elif n["kind"] == "line" and not n.get("words"):
            body.append('   The line: "%s"' % n["was"])
        got = _frames_of(frames.get(n["id"]))
        if got:
            ring = (
                " (the orange box is the area)"
                if n["kind"] == "spot" and n.get("w")
                else " (the orange ring is the spot)"
                if n["kind"] == "spot"
                else ""
            )
            body.append("   The frame at %s: %s%s" % (_mmss(frame_time(n)), got[0][1], ring))
            if len(got) > 1:
                body.append(
                    "   Around it: "
                    + ", ".join("%s at %s" % (p, _mmss(ts)) for ts, p in sorted(got[1:]))
                )
        out.append("\n".join(body))
    return "\n\n".join(out)


ASK = """\
This film is finished, and its maker has watched it and left notes on it. Make the changes the \
notes ask for, and nothing else: the maker kept everything they did not mention.

The film is in this folder as it was made: film.js, vo.json (the narration's words), \
score.json, sfx.json%(extra)s, and the recording's timeline in audio/vo/timeline.json. Its own \
copy of the engine is in engine/ (when it differs from the reference above, the film's copy is \
what runs). Read film.js first.

Length: %(length)d seconds: the film still ends where it ends (if a line you change needs a \
little more, the studio lengthens the film and says so). Your working time: about \
%(minutes)d minutes (waiting for the machine is not counted).

The notes (also in notes/notes.md):

%(notes)s
%(earlier)s%(project)s
How to work:
- Read every note before you change anything, and decide the order: the words first (they are \
the scarce part), then one change at a time. Finish it, look at it, answer its notes, and only \
then start the next -- when your time runs out, the film must hold only whole, looked-at changes.
- Notes can belong together: the same character or thing, the same shot, the same cause (three \
hops drawn flat are one hop drawn wrong; two forelegs that stretch are one way of reaching). \
After reading them all, write notes/plan.md: the notes in groups, and the order. Notes that \
depend on each other (where somebody stands, then what they do from there) go in that order. \
Make each group as ONE change -- one drawing, one function, used everywhere its notes point -- \
and then answer each of its notes.
- A note's time is where its maker saw the thing, not a fence. Find the whole shot or action \
the note is about and change it from where it begins to where it ends, also where that is \
before or after the time given. Where the same fault shows elsewhere in the film (the same pose \
used again, the same drawing in another shot), fix it there too and say where in the `note`: \
that is the note's own change, not something more.
- Never answer a note "not changed" because time is short. Leave it without a `note`: when \
this time is up, the studio gives you more for the notes left.
- Look at each note's frame first (Read it), then find in film.js what draws what the note \
points at, by its time and what is on the frame.
- Change only what a note asks for. Around it, the same scenes, timing, words and music.
- A note is done whole. What a note takes out of the picture goes out of the words too, and \
out of every other shot it is in; what it takes out of the words goes out of the picture. If \
you cannot finish one half (no recording left, no room for the line), put the other half back \
as it was and answer the note with done false: never leave the narration naming something the \
picture no longer shows, or the picture showing what the words no longer say.
- After changing the picture: `check`, then `stills` at the notes' moments, and look: is it \
what was asked, and is everything near it still right?
- A note about the camera, the framing, or where somebody stands changes every shot it \
touches, not one moment. After it, `stills` of EVERY shot you changed (several calls: the \
start, the middle and the end of each), and look at each for what such a change breaks:
  - somebody or something now in front of a character, a face or the thing the words are \
about, that was clear before;
  - somebody missing from a shot who is in the shot before and the shot after. A character \
who should not be in a view is out of it for the whole shot, or walks out of it: nobody blinks \
out and back;
  - a character cut by the frame's edge, or grown or shrunk against the others;
  - two shots in a row that differ in closeness by more than about double, where the story \
does not ask for the jump. When the note is about jumps between close and wide, write down \
each shot's zoom in order first, change the ones that jump, and read the list again after.
  Fix what you find before you answer the note. A change you have not looked at is not done: \
put it back, or say in its `note` which shots you did not see again.
%(voice)s- After changing score.json, sfx.json or the narration: `sound`.
- Each note gets exactly one `note` call when you are done with it: its number, whether it is \
done, and one plain sentence for the maker saying what you changed (no file names, no code \
words). A note you could not or should not do -- unclear, or it would break the film, or the \
film cannot hold it -- gets `note` with done false and one sentence saying why and what would \
make it possible. Do not guess at a note you cannot read: say so.
- Before `summary`: `stills` once more at every note's own moment, all of them, and look. A \
later change can break an earlier one: fix what broke. When you stop, somebody who has not seen \
your work compares each note's frames as they were with the same moments now, and what does \
not show what was asked comes back to you. So judge by the frame, not by the code.
- Last, `summary`: one short paragraph, in plain words, of what is different in this version.
- Do not render the film; the studio does that when you are done.
"""
VOICE = (
    "- A line that should be said differently: change that line's text in vo.json in place "
    "(never add, remove or reorder lines), keep it about as long as it was, then `voice` with "
    "retake_line. Cues placed on words follow the new recording; look at any cue on a word you "
    "changed.\n"
    "- A line whose words stay but whose recording is wrong (bad sound, a noise, a slip, the "
    "wrong tone or pace): leave vo.json as it is and `voice` with retake_line -- a new take of "
    "the same words in the same voice. That is a change: answer the note done.\n"
    "- This round has %(runs)d recordings, and every `voice` call is one. Before the first, count "
    "the lines the notes need said differently -- a note that removes or renames something "
    "needs every line that names it -- and keep a recording for each of them. A line fits its "
    "place when it has about as many words as the line it replaces: words the maker wrote that "
    "are much longer than the old line are shortened BEFORE recording, keeping their meaning "
    "(say so in the `note`), never recorded to find out.\n"
)
NO_VOICE = (
    "- The narration stays as recorded: this film's words cannot be changed in a round, and "
    "there is no `voice` tool. A note that asks for other words, or for a line to be recorded "
    "again, gets `note` with done false.\n"
)
CONTINUE = (
    "Your time for this round was up with these notes not yet answered: %s. Here is more: about "
    "%d minutes. This is the same session, and everything you changed is on disk as you left it. "
    "First `check` and look at the last thing you were changing (`stills`): finish it or put it "
    "back. Then the notes left, one change at a time as before, each with its `note`; then "
    "`summary` if you have not."
)
AGAIN = (
    "Somebody who did not make these changes compared each note's frames as they were with the "
    "same moments as they are now. These notes are answered done, and the frames do not show "
    "what was asked:\n\n%s\n\nFor each: Read the frames named and look as they did. If they "
    "are right, the change is not there yet: make it so that the frame shows it, in another way "
    "than before where that way did not read. Then `stills` at those moments and look again. "
    "Call `note` again for each (its number, done, one sentence). Change nothing else. About %d "
    "minutes."
)
UNSURE = "A second look at the frames was not sure of this one: %s"
EARLIER_TEXT = (
    "\nEarlier rounds of notes on this film, oldest first (also in notes/earlier.md). A note "
    "now that asks again for what an earlier one asked means that change was not good enough as "
    "its maker sees it: look at what was done then, and do it another way, not the same again."
    "\n\n%s\n"
)
PROJECT = (
    "\nThis film keeps its own copies of its project's scenes and characters, from the day it "
    "was made. The project's own, where they differ now, are in notes/project/:\n%s\nThe film "
    "keeps its own unless a note asks otherwise. Where a note names one with @name, asks for "
    "the new one, or asks for a scene or character the film does not have and the project does, "
    "use the project's: a drawn one by copying notes/project/cast/<name>.js to cast/<name>.js "
    "and drawing it through SK.cast.<name>; a painted one by copying its picture over the "
    "film's in inputs/ and painting again every painting whose ref names it (`paint` with "
    "retake, those only). Then `stills` of every shot it is in, and look.\n"
)
RULES = (
    "\nThe series' standing rules, from the person who runs it. Each is a note they left on an "
    "episode and must not have to leave again. Whatever you draw or change in this round "
    "follows every one of them; a note that asks for the opposite of a rule wins, for that "
    "note. Do not go through the rest of the film for them: the notes say what to change.\n%s\n"
)
CHECK_RULES = (
    "\n\nThe series has standing rules. Where a right-hand frame, in what this note changed, "
    "plainly breaks one of them, ok is false too, and why names the rule:\n%s"
)
CHECK_SYSTEM = (
    "You check changes made to an animated film against what its maker asked for. You see the "
    "request and frames of the film; you did not make the change and you cannot see how it was "
    "made. Answer with one JSON object and nothing else."
)
CHECK = (
    "Each picture is one note the film's maker left, in the order below: rows of the same "
    "moments of the film, as it was (left) and as it is now (right). Whoever changed the film "
    "says each of these notes is done. For each, look at the right-hand frames and say whether "
    "they show what the note asked for.\n\n%s\n\n"
    "Judge what a still frame can show: what is drawn, where, how big, whether it reads at a "
    "glance as the thing asked for, whether what should be gone is gone. ok is false when the "
    "frames plainly do not show it: nothing is different; it still reads as what the maker "
    "complained of; or the change broke something beside it that was right on the left. Be "
    "exact about what you see (a note asking for a cat's paw is not done by a grey pole with a "
    "knob). A note about sound, music, words, speed, or how something moves between these "
    "frames cannot be judged from them: ok true, sure false.\n\n"
    '{"notes": [{"number": 1, "ok": true, "sure": true, "why": "one plain sentence: what the '
    'frames show now"}]}'
)
ANSWER = (
    "Before you stop: these notes have no `note` yet: %s. Call `note` for each now (done or "
    "not, one sentence), then `summary` if you have not. Change nothing else."
)


def ask(work, notes, frames, lim, earlier="", project=""):
    extra = "".join(", " + n for n in work.editable() if n not in films.EDITABLE)
    return ASK % {
        "earlier": earlier,
        "project": project,
        "extra": extra,
        "length": work.length,
        "minutes": lim["claude_s"] // 60,
        "notes": notes_text(notes, timeline(work), frames),
        "voice": (VOICE % {"runs": lim["voice_runs"]}) if can_voice(work) else NO_VOICE,
    }


class Round:
    """What a round adds to the film's tools (tools.Tools.round): `note` and `summary`, and the
    verdicts they collect."""

    def __init__(self, notes, can_voice, on_change):
        self.notes, self.on_change = notes, on_change
        self.verdicts, self.summary = {}, None  # note id -> {"state", "reply"}
        self.checks = {}  # note id -> {"ok", "sure", "why"}: the second look (looked)
        self.proofs = {}  # note id -> the address of its before and after (proofs)
        self.brought = []  # members the series changed since, brought up to date (bring_up)
        self.without = ("name_film",) + (() if can_voice else ("voice",))

    def missing(self):
        return [i for i, n in enumerate(self.notes, 1) if n["id"] not in self.verdicts]

    async def note(self, number, done, what):
        try:
            n = self.notes[int(number) - 1]
        except (TypeError, ValueError, IndexError):
            raise toolbox.ToolError(
                "number is a note's number, 1 to %d" % len(self.notes)
            ) from None
        if int(number) < 1:
            raise toolbox.ToolError("number is a note's number, 1 to %d" % len(self.notes))
        what = " ".join(str(what or "").split())[:400]
        if not what:
            raise toolbox.ToolError("what: one sentence for the film's maker")
        self.verdicts[n["id"]] = {"state": "done" if done else "cannot", "reply": what}
        self.on_change("Note %d %s" % (int(number), "done" if done else "not changed"))
        left = self.missing()
        return "Noted." + (
            " Still without a `note`: %s." % ", ".join(map(str, left)) if left else ""
        )

    async def say_summary(self, text):
        text = " ".join(str(text or "").split())[:700]
        if not text:
            raise toolbox.ToolError("text: a short paragraph for the film's maker")
        self.summary = text
        self.on_change("Wrapping up")
        return "Kept."

    def tools(self, tool, wrap):
        return [
            tool(
                "note",
                "Answer one of the maker's notes, once you are done with it: its number, done "
                "(true: changed as asked; false: not changed), and what -- one plain sentence "
                "for the maker: what you changed, or why not and what would make it possible.",
                {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "done": {"type": "boolean"},
                        "what": {"type": "string"},
                    },
                    "required": ["number", "done", "what"],
                },
            )(wrap(lambda a: self.note(a.get("number"), bool(a.get("done")), a.get("what")))),
            tool(
                "summary",
                "Say what is different in this version: one short paragraph in plain words.",
                {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )(wrap(lambda a: self.say_summary(a.get("text")))),
        ]


async def pack(work, t, notes):
    """notes/: each timed note's frames, drawn from the film's code at those moments (exact,
    where a frame cut from the video is a compressed neighbour), a spot ringed on its own; the
    same frames untouched in notes/before/, for the second look (looked); and notes.md.
    Returns {note id: [(seconds, "notes/<file>.png"), ...]}, the note's own moment first."""
    from PIL import Image, ImageDraw

    os.makedirs(work.path("notes", "before"), exist_ok=True)
    timed = [(i, n) for i, n in enumerate(notes, 1) if frame_time(n) is not None]
    per = _thin([frame_times(n, work.length) for _, n in timed])
    frames = {}
    every = sorted({ts for one in per for ts in one})
    for k in range(0, len(every), toolbox.MAX_STILLS):
        await t.stills(every[k : k + toolbox.MAX_STILLS], sheet=False)
        for ts in every[k : k + toolbox.MAX_STILLS]:  # the next call draws over review/
            src = work.path("outputs", "review", "%06.2f.png" % ts)
            if os.path.isfile(src):
                shutil.copyfile(src, work.path("notes", "before", "%06.2f.png" % ts))
    for (i, n), times in zip(timed, per):
        got = []
        for j, ts in enumerate(times):
            src = work.path("notes", "before", "%06.2f.png" % ts)
            if not os.path.isfile(src):
                continue
            name = "%d.png" % i if j == 0 else "%d-%06.2f.png" % (i, ts)
            with Image.open(src) as im:
                im = im.convert("RGB")
                if j == 0:
                    _ring(n, im, ImageDraw.Draw(im))
                im.thumbnail((1280, 1280))
                im.save(work.path("notes", name))
            got.append((ts, "notes/" + name))
        if got and got[0][0] == times[0]:  # its own moment was drawn
            frames[n["id"]] = got
    with open(work.path("notes", "notes.md"), "w", encoding="utf-8") as f:
        f.write("# The maker's notes\n\n" + notes_text(notes, timeline(work), frames) + "\n")
    return frames


def _ring(n, im, d):
    """A spot note's ring, or its area's box, on a frame."""
    if n["kind"] == "spot" and n.get("w"):  # an area: its box, as it was drawn
        x0, y0, x1, y1 = _box(n, im.width, im.height)
        for k, col in ((5, (255, 255, 255)), (0, RING)):
            d.rectangle((x0 - k, y0 - k, x1 + k, y1 + k), outline=col, width=5)
    elif n["kind"] == "spot":
        cx, cy, r = n["x"] * im.width, n["y"] * im.height, max(18, im.width // 55)
        for k, col in ((r + 5, (255, 255, 255)), (r, RING)):
            d.ellipse((cx - k, cy - k, cx + k, cy + k), outline=col, width=5)


# ------------------------------------------------------------------ what was asked before
def history(film):
    """Every round of notes this film has had, oldest first: [{rid, n, state, at, summary,
    notes: [{kind, t, t2, text, words, state, reply}]}] (versions/history.jsonl)."""
    out = []
    with contextlib.suppress(OSError):
        with open(film.path(KEPT, HISTORY), encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError):
                    got = json.loads(line)
                    if isinstance(got, dict):
                        out.append(got)
    return out


def keep_history(film, rid, n, state, notes, verdicts, summary=None):
    """A round that is over, kept for the rounds after it: its notes and what was answered. The
    record holds only the latest round's, and the next round was told nothing of them: a paw
    asked for twice was drawn the second time with no word of the first (ch7tno, 2026-11-24)."""
    mine = [x for x in notes if x.get("id") != REFRESH_NOTE]
    if not mine or any(x.get("rid") == rid for x in history(film)):
        return
    said = {v.get("id"): v for v in verdicts or []}
    keys = ("kind", "t", "t2", "x", "y", "line", "was", "words", "text")
    row = {
        "rid": rid,
        "n": n,
        "state": state,
        "at": _now(),
        "summary": summary,
        "notes": [
            {
                **{k: x[k] for k in keys if x.get(k) is not None},
                "state": (said.get(x["id"]) or {}).get("state"),
                "reply": (said.get(x["id"]) or {}).get("reply"),
            }
            for x in mine
        ],
    }
    os.makedirs(film.path(KEPT), exist_ok=True)
    with open(film.path(KEPT, HISTORY), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _backfill(film, rec):
    """The round the record still holds, into the history, before the next one takes its place
    there (a film whose last round was made before the history was kept)."""
    r = rec.get("round") or {}
    if r.get("id") and r.get("notes") and not r.get("hand") and r.get("state") not in ACTIVE:
        with contextlib.suppress(Exception):
            keep_history(
                film,
                r["id"],
                r.get("n"),
                r.get("state"),
                r["notes"],
                r.get("answers"),
                r.get("summary"),
            )


def _when(n):
    if n.get("kind") == "film" or n.get("t") is None:
        return "the whole film"
    if n.get("kind") == "line":
        return "the words of line %s" % n.get("line")
    if n.get("t2") is not None:
        return "from %s to %s" % (_mmss(n["t"]), _mmss(n["t2"]))
    return "at %s" % _mmss(n["t"])


def earlier(film, work=None):
    """The last rounds of notes on this film, for the round being made: "" when there were
    none; also written to the copy's notes/earlier.md."""
    rows = history(film)[-EARLIER:]
    out = []
    for r in rows:
        made = "made version %s" % r.get("n") if r.get("state") == "done" else "made no version"
        body = ["Round of %s, %s:" % (str(r.get("at") or "")[:10], made)]
        for x in r.get("notes") or []:
            asked = x.get("text") or ""
            if x.get("words"):
                asked = ('Say "%s" instead of "%s". %s' % (x["words"], x.get("was"), asked)).strip()
            body.append("- [%s] %s" % (_when(x), asked))
            if x.get("reply"):
                done = "Done" if x.get("state") == "done" else "Not changed"
                body.append("  Answered: %s. %s" % (done, x["reply"]))
        out.append("\n".join(body))
    if not out:
        return ""
    text = "\n\n".join(out)[-6000:]
    if work is not None:
        with contextlib.suppress(OSError):
            os.makedirs(work.path("notes"), exist_ok=True)
            with open(work.path("notes", "earlier.md"), "w", encoding="utf-8") as f:
                f.write("# Earlier rounds of notes on this film\n\n" + text + "\n")
    return EARLIER_TEXT % text


# ------------------------------------------------------------------ the project, as it is now
def _same(a, b):
    try:
        with open(a, "rb") as f, open(b, "rb") as g:
            return f.read() == g.read()
    except OSError:
        return False


def project_now(work):
    """notes/project/: the scenes and characters of the film's project that are not what the
    film has -- changed there since, or new -- for a note that asks for one. An episode keeps
    its own copies (library.seed copies by value), so a round knew nothing of a scene made
    after the episode. -> what the round is told of them, or "". Nothing in the film changes
    here: Claude copies one in only where a note asks."""
    import library

    rec = work.record()
    lib = library.lib_of(rec) if (rec.get("project") or {}).get("id") else None
    if not lib:
        return ""
    idx, d = library.load(lib), library.dir_of(lib)
    rows = []
    for n, e in sorted(idx["cast"].items()):
        if e.get("deleted") or len(rows) >= 24:
            continue
        what = "a scene" if e.get("kind") == "place" else "a character"
        about = " ".join(str(e.get("about") or "").split())[:120]
        if e.get("painted"):
            src = os.path.join(d, "cast", n, "v%s.%s" % (e.get("version"), e.get("ext")))
            mine = next(
                (
                    p
                    for p in (
                        work.path("inputs", "cast_%s.%s" % (n, x)) for x in library.PICTURE_EXT
                    )
                    if os.path.isfile(p)
                ),
                None,
            )
            if not os.path.isfile(src) or mine is None or _same(src, mine):
                continue  # a painted one the film never had is not a round's to bring in
            rel, new = "notes/project/cast_%s.%s" % (n, e.get("ext")), False
            how = "painted; the film's is inputs/%s" % os.path.basename(mine)
        else:
            src = os.path.join(d, "cast", n, "v%s.js" % e.get("version"))
            mine = work.path("cast", n + ".js")
            if not os.path.isfile(src) or _same(src, mine):
                continue
            rel, new = "notes/project/cast/%s.js" % n, not os.path.isfile(mine)
            how = "drawn"
        dst = work.path(*rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        rows.append(
            "- @%s (%s, %s%s): %s -- %s"
            % (
                n,
                what,
                how,
                "; " + about if about else "",
                "new: this film does not have it" if new else "changed since this film's copy",
                rel,
            )
        )
    return PROJECT % "\n".join(rows) if rows else ""


# ------------------------------------------------------------------ the second look
def _picked(notes, frames, want):
    """[(number, note, its own moment, the moments shown)] of the notes `want` takes that have
    frames: each note's own moment, and the first and last of the others."""
    todo = []
    for i, n in enumerate(notes, 1):
        got = [x for x in _frames_of(frames.get(n["id"])) if x[0] is not None]
        if not got or not want(n):
            continue
        rest = sorted(got[1:])
        pick = [got[0]] + rest[:1] + (rest[-1:] if len(rest) > 1 else [])
        todo.append((i, n, got[0][0], sorted(x[0] for x in pick[:CHECK_ROWS])))
    return todo


async def _draw_now(work, t, todo):
    """notes/after/<t>.png: the moments of `todo` (_picked) as the copy draws them now."""
    os.makedirs(work.path("notes", "after"), exist_ok=True)
    every = sorted({ts for _, _, _, times in todo for ts in times})
    for k in range(0, len(every), toolbox.MAX_STILLS):
        await t.stills(every[k : k + toolbox.MAX_STILLS], sheet=False)
        for ts in every[k : k + toolbox.MAX_STILLS]:
            src = work.path("outputs", "review", "%06.2f.png" % ts)
            if os.path.isfile(src):
                shutil.copyfile(src, work.path("notes", "after", "%06.2f.png" % ts))


def _sheet(work, i, n, main, times):
    """notes/after/<i>.jpg: note i's moments as they were (left) beside as they are now, a row
    each, a spot's place ringed on both. Its path, or None when no moment has both."""
    from PIL import Image, ImageDraw

    import review

    pairs = []
    for ts in times:
        a = work.path("notes", "before", "%06.2f.png" % ts)
        b = work.path("notes", "after", "%06.2f.png" % ts)
        if not (os.path.isfile(a) and os.path.isfile(b)):
            continue
        if ts == main and n["kind"] == "spot":  # the place pointed at, on both
            both = []
            for side, src in (("was", a), ("now", b)):
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    _ring(n, im, ImageDraw.Draw(im))
                    dst = work.path("notes", "after", "%d-%s.png" % (i, side))
                    im.save(dst)
                both.append(dst)
            a, b = both
        pairs.append((ts, a, b))
    if not pairs:
        return None
    return review.pairs_sheet(pairs, work.path("notes", "after", "%d.jpg" % i))


PROOF = "proof-%d.jpg"  # a note's before and after, online beside the version it was made for


async def proofs(work, t, notes, frames):
    """Every timed note's before and after as one picture, drawn from the copy as the round
    leaves it: {note id: file name in notes/after/}. Its maker checked 13 changes by watching
    285 seconds of film again; a picture a note shows each at a glance, the ones not made too."""
    todo = _picked(notes, frames, lambda n: True)
    if not todo:
        return {}
    await _draw_now(work, t, todo)
    out = {}
    for i, n, main, times in todo:
        p = await asyncio.to_thread(_sheet, work, i, n, main, times)
        if p:
            shutil.copyfile(p, work.path("notes", "after", PROOF % i))
            out[n["id"]] = PROOF % i
    return out


async def looked(work, t, notes, verdicts, frames, ask, only=None, rules=None):
    """Whether the film now shows what each note answered done asked for, as somebody who did
    not make the change sees it: each note's frames as they were (pack kept them) beside the
    same moments drawn now, read by a Claude call with no tools that knows only the note.
    Claude judged its own change from its own stills, and answered done for a paw that still
    read as a grey pole with a knob (ch7tno.r1): its maker found out by watching, and sent the
    note again. ask: async (text, [jpeg bytes]) -> (dict, cost). only: these note ids.
    -> {note id: {"ok", "sure", "why"}} for the notes it could look at (a note on the words, or
    on the whole film, has no frames to compare)."""
    import review

    todo = _picked(
        notes,
        frames,
        lambda n: (
            (verdicts.get(n["id"]) or {}).get("state") == "done"
            and n["kind"] != "line"
            and (only is None or n["id"] in only)
        ),
    )
    if not todo:
        return {}
    await _draw_now(work, t, todo)

    def sheet(i, n, main, times):
        p = _sheet(work, i, n, main, times)
        return review.jpeg(p) if p else None

    out = {}
    for k in range(0, len(todo), CHECK_NOTES):
        said, images, ids = [], [], {}
        for i, n, main, times in todo[k : k + CHECK_NOTES]:
            img = await asyncio.to_thread(sheet, i, n, main, times)
            if img is None:
                continue
            images.append(img)
            ids[i] = n["id"]
            mark = " (the orange mark is the place)" if n["kind"] == "spot" else ""
            said.append(
                "Picture %d -- note %d [%s]%s: %s" % (len(images), i, _when(n), mark, n["text"])
            )
        if not images:
            continue
        text = CHECK % "\n".join(said)
        if rules:
            text += CHECK_RULES % "\n".join("- " + r for r in rules)
        d, _cost = await asyncio.wait_for(ask(text, images), CHECK_S)
        for x in (d or {}).get("notes") or []:
            try:
                nid = ids[int(x.get("number"))]
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            out[nid] = {
                "ok": x.get("ok") is not False or x.get("sure") is False,
                "sure": x.get("sure") is not False,
                "why": " ".join(str(x.get("why") or "").split())[:300],
            }
    return out


def again_text(notes, bad, seen):
    """The notes the second look did not pass, for the turn that makes them again."""
    out = []
    for i in bad:
        n = notes[i - 1]
        ts = frame_time(n)
        out.append(
            "%d. [%s] %s\n   What they saw: %s\n   As it is now: notes/after/%06.2f.png; as it "
            "was: notes/before/%06.2f.png; both side by side: notes/after/%d.jpg"
            % (i, _when(n), n["text"], seen[n["id"]]["why"] or "it does not show it", ts, ts, i)
        )
    return "\n\n".join(out)


# ------------------------------------------------------------------ asking
def start(
    film,
    sched,
    notes,
    key=None,
    client="local",
    member=None,
    priority=0,
    auth="api",
    src=None,
    hand=None,
    voice=None,
    claude=None,
    refresh=None,
    rules=None,
):
    """Make this finished film's next version from these notes; the round's job. `rules`: its
    project's standing rules as they are now (the film's record has them as they were when it
    was made). `refresh`:
    instead of notes, the names of its project's scenes and characters to bring the film up to
    (refresh_notes, lay_over). Asked again
    with the same key, the round already asked for. Raises RoundError for what cannot be one.
    `src`: the version the notes were written on (it must be the film now). `hand`: files
    changed by hand instead of notes (clean_hand), which are not one of its maker's rounds of
    the day. `voice`: a fresh pass to the film's own ElevenLabs voice (server.narrator_of), so the
    round may record (words): kept in the film's temp/, never in the record."""
    rec = film.record()
    if rec.get("state") != "done" or not rec.get("ok"):
        raise RoundError(409, "This film is not finished.", "state")
    r = rec.get("round") or {}
    if key and r.get("key") == key:
        job = JOBS.get(film.id)
        return (
            job
            if job is not None
            else {"rid": r.get("id"), "n": r.get("n"), "state": r.get("state")}
        )
    if film.id in in_flight() or (r.get("state") in ACTIVE and peers.alive(r.get("server"))):
        raise RoundError(409, "A round of changes to this film is already being made.", "round")
    if film.mode == "scenes":
        raise RoundError(
            409, "This film was made in scenes; it cannot be changed here yet.", "scenes"
        )
    cur = version_of(rec)
    if src is not None and int(src) != cur:
        raise RoundError(
            409, "The film has moved on to version %d since these notes." % cur, "stale"
        )
    if hand is not None:
        return _begin(
            film, sched, [], key, client, member, priority, auth, hand=clean_hand(film, hand)
        )
    if rounds_today(rec) >= PER_DAY:
        raise RoundError(
            429, "This film has had its %d rounds of changes for today." % PER_DAY, "rounds"
        )
    if refresh is not None:
        refresh, notes = refresh_notes(film, refresh)
    else:
        notes = clean_notes(film, notes, fresh=voice is not None)
    if voice is not None:
        keep_pass(film, voice)
    return _begin(
        film,
        sched,
        notes,
        key,
        client,
        member,
        priority,
        auth,
        voice=voice is not None,
        claude=claude,
        refresh=refresh,
        rules=rules,
    )


def _begin(
    film,
    sched,
    notes,
    key,
    client,
    member,
    priority,
    auth,
    tries=1,
    asked=None,
    k=None,
    hand=None,
    voice=False,
    claude=None,
    refresh=None,
    rules=None,
):
    rec = film.record()
    k = k or (rec.get("rounds") or 0) + 1
    # the round's own Claude model and effort ({"model"?, "effort"?}; claude_of reads them back)
    claude = {
        k2: v
        for k2, v in (claude or {}).items()
        if (k2 == "model" and v in films.CLAUDE_MODELS) or (k2 == "effort" and v in films.EFFORTS)
    }
    rid, n = (
        "%s.r%d" % (film.id, k),
        max([version_of(rec)] + [v.get("n", 0) for v in rec.get("versions") or []]) + 1,
    )
    asked = asked or _now()
    if tries == 1:
        _backfill(film, rec)
    days = list(rec.get("round_days") or [])[-20:] + (
        [asked] if tries == 1 and hand is None else []
    )
    film.update(
        rounds=k,
        round_days=days,
        round={
            "id": rid,
            "n": n,
            "state": "queued",
            "key": key,
            "client": client,
            "member": member,
            "priority": int(bool(priority)),
            "auth": auth,
            "asked": asked,
            "server": peers.SERVER_ID,
            "tries": tries,
            "notes": notes,
            "now": "Waiting for a free studio",
            **({"hand": hand} if hand else {}),
            **({"voice": True} if voice else {}),
            **({"claude": claude} if claude else {}),
            **({"refresh": list(refresh)} if refresh else {}),
            **({"rules": films.clean_rules(rules)} if rules else {}),
        },
    )
    _set_mark(film.id)
    job = {
        "film": film.id,
        "rid": rid,
        "n": n,
        "state": "queued",
        "client": client,
        "reserve": reserve(film, len(notes), auth, claude.get("model")),
        "cost_usd": 0,
        "stopped": False,
        "task": None,
    }
    JOBS[film.id] = job
    job["task"] = asyncio.get_running_loop().create_task(_run(job, film, sched))
    return job


def resume(film, sched):
    """An orphan's round (orphans): what a swap left half-way is undone, then the round is
    started again from its notes, or given up after TRIES. One whose version had already taken
    the film's place when its server went is only recorded as done."""
    import agent

    heal(film)
    rec = film.record()
    r = rec.get("round") or {}
    loop = asyncio.get_running_loop()
    if version_of(rec) == r.get("n"):  # swapped in (commit), and never said so
        film.update(round=dict(r, state="done", finished=_now(), server=None))
        _drop_mark(film.id)
        loop.create_task(_tell(agent, film, r.get("id"), {"state": "done"}, final=True))
        return None
    shutil.rmtree(work_dir(str(r.get("id"))), ignore_errors=True)
    if (r.get("tries") or 0) >= TRIES:
        why = "The studio restarted while this version was being made."
        film.update(round=dict(r, state="interrupted", error=why, finished=_now(), server=None))
        _drop_mark(film.id)
        loop.create_task(
            _tell(agent, film, r.get("id"), {"state": "interrupted", "error": why}, final=True)
        )
        return None
    return _begin(
        film,
        sched,
        r.get("notes") or [],
        r.get("key"),
        r.get("client") or "local",
        r.get("member"),
        r.get("priority") or 0,
        r.get("auth") or "api",
        tries=(r.get("tries") or 0) + 1,
        asked=r.get("asked"),
        k=rec.get("rounds"),
        hand=r.get("hand"),
        voice=bool(r.get("voice")),
        claude=r.get("claude"),
        refresh=r.get("refresh"),
    )


_ORDER = {}  # rid -> the lock its document's writes queue on


async def _tell(agent, film, rid, fields, final=False):
    """The round's own document in studio_runs (what the site reads, and settles on). Its writes
    land in the order they were asked for: each waits for the one before, so an answer saved
    half-way never overwrites the final record."""
    r = film.record().get("round") or {}
    doc = {"kind": "round", "film": film.id, "n": r.get("n"), "job": rid}
    lock = _ORDER.setdefault(rid, asyncio.Lock())
    async with lock:
        await _save(agent, rid, doc, fields, final)
    if final:
        _ORDER.pop(rid, None)


async def _save(agent, rid, doc, fields, final):
    await agent.save(
        rid, {**doc, **fields, "finished_at": store.now()} if final else {**doc, **fields}, final
    )


def stop(film):
    """Stop the round being made: here at once; on another server by a flag its job looks for
    (a ship has two servers for a few minutes); one nobody is making is ended in the record."""
    rec = film.record()
    r = rec.get("round") or {}
    if r.get("state") not in ACTIVE:
        raise RoundError(409, "No round of changes is being made.", "none")
    job = JOBS.get(film.id)
    if job is not None and job["task"] is not None and not job["task"].done():
        job["stopped"] = True
        job["task"].cancel()
        return dict(r, state="cancelled")
    if peers.alive(r.get("server")):
        with contextlib.suppress(OSError):
            os.makedirs(MARKS, exist_ok=True)
            with open(_mark(film.id) + ".stop", "w", encoding="utf-8") as f:
                f.write(_now())
        return dict(r, state="cancelled")
    heal(film)
    film.update(round=dict(r, state="cancelled", finished=_now(), server=None))
    _drop_mark(film.id)
    return dict(r, state="cancelled")


async def stop_all():
    """The server is stopping: its rounds go back to the queue for the next leader (orphans)."""
    tasks = [j["task"] for j in JOBS.values() if j["task"] is not None and not j["task"].done()]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=20)


# ------------------------------------------------------------------ the job
def _set(film, job, state=None, **more):
    """The round's state and anything else, in the film's record (`round`)."""
    if state:
        job["state"] = state
    r = dict(film.record().get("round") or {})
    r.update(more)
    if state:
        r["state"] = state
    film.update(round=r)
    return r


async def _run(job, film, sched):
    import agent
    from guard import pin_paint, pin_vo
    from sched import Clock, waiting_text

    fid, rid, n = film.id, job["rid"], job["n"]
    r0 = film.record().get("round") or {}
    notes, auth, hand = r0.get("notes") or [], r0.get("auth") or "api", r0.get("hand")
    first = "Taking the changed files" if hand else "Reading your notes"
    lim = limits(
        film.length,
        len(notes),
        wide(notes),
        model=claude_of(film.record()).get("model"),
        reach=weight(notes),
    )
    log = film.path(KEPT, "r%s.events.jsonl" % rid.rsplit(".r", 1)[-1])
    os.makedirs(os.path.dirname(log), exist_ok=True)
    t0, meter, clock = time.time(), agent.Meter(), Clock()
    said = {"at": 0.0, "now": None}
    can = words(film.record(), fresh=bool(r0.get("voice")))["can"]
    state = Round(notes, can, lambda text: tell_now(text, force=True))
    work = None

    def verdicts():
        return [
            {
                "id": x["id"],
                **(state.verdicts.get(x["id"]) or {"state": "sent", "reply": None}),
                **({"proof": state.proofs[x["id"]]} if state.proofs.get(x["id"]) else {}),
            }
            for x in notes
        ]

    # the round's one line in the database (live.py), as a film being made keeps its own
    told = live.of(
        rid, lambda r, fields: agent.STORE.save(r, {"kind": "round", "film": fid, **fields})
    )

    def tell_now(text, force=False):
        """What the round is doing, for its person: its line at once (live.py writes each
        change once); the notes' answers and the film's own record at most every few seconds
        (every film shares this loop, and the page asks every 1.5 s)."""
        said["now"] = text
        told.say(text, ahead=None)
        if not force and time.time() - said["at"] < 4:
            return
        said["at"] = time.time()
        with contextlib.suppress(Exception):
            _set(film, job, now=text)
            fields = {
                "notes": verdicts(),
                "cost_usd": round(meter.usd(), 4) if auth == "api" else 0,
            }
            asyncio.get_running_loop().create_task(_tell(agent, film, rid, fields))

    def emit(ev):
        ev = {**ev, "t": round(time.time() - t0, 1)}
        with contextlib.suppress(OSError):
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        kind = ev.get("type")
        if kind == "cost":
            job["cost_usd"] = ev["usd"] if auth == "api" else 0
        elif kind == "wait":  # for its turn with Claude, or for the machine: said as it is
            told.event(ev)
            if job["state"] == "queued":
                with contextlib.suppress(Exception):
                    _set(film, job, now=ev.get("text"))
        elif kind == "stage":
            tell_now(ev.get("text") or "Working", force=True)
        elif kind == "tool":
            told.event(ev)  # it has the machine again
            if plain(ev.get("text")):
                tell_now(plain(ev.get("text")))

    def on_wait(pool, ahead):
        emit({"type": "wait", "pool": pool, "ahead": ahead, "text": waiting_text(pool, ahead)})

    def cost():
        tts = (
            sum(x.get("cost_usd") or 0 for x in agent._spend(work, "audio", "vo", "spend.jsonl"))
            if work
            else 0
        )
        img = (
            sum(x.get("cost_usd") or 0 for x in agent._spend(work, "images", "spend.jsonl"))
            if work
            else 0
        )
        claude = round(meter.usd(), 4)
        return {
            "cost_usd": round((claude if auth == "api" else 0) + tts + img, 4),
            "claude_cost_usd": claude,
            "claude_billed": auth == "api",
            "tts_cost_usd": round(tts, 6),
            "image_cost_usd": round(img, 6),
            "tokens": meter.tokens(),
            "seconds": round(time.time() - t0, 1),
            "auth": auth,
            "release": films.RELEASE,
        }

    async def over(st, error=None, **more):
        """The round ended without a version: the film is as it was."""
        _set(film, job, st, error=error, finished=_now(), server=None, now=None, answers=verdicts())
        _drop_mark(fid)
        if not hand:
            with contextlib.suppress(Exception):
                keep_history(film, rid, n, st, notes, verdicts(), state.summary)
        emit({"type": "error" if st != "unchanged" else "done", "text": error or st})
        await _tell(
            agent,
            film,
            rid,
            {"state": st, "error": error, "notes": verdicts(), **cost(), **more},
            final=True,
        )

    rec0 = film.record()
    await agent.save(
        rid,
        {
            "kind": "round",
            "film": fid,
            "n": n,
            "job": rid,
            "source": rec0.get("source"),
            "client": r0.get("client"),
            **({"member": r0["member"]} if r0.get("member") else {}),
            "key": r0.get("key"),
            **({"by": "hand"} if hand else {}),
            "host": store.HOST,
            "model": claude_of(rec0).get("model") or agent.MODEL,
            "effort": claude_of(rec0).get("effort") or EFFORT,
            "length": rec0.get("length"),
            "look": rec0.get("look"),
            "release": films.RELEASE,
            "auth": auth,
            "state": "queued",
            "now": "Waiting for a free studio",
            "notes": verdicts(),
            "cost_usd": 0.0,
        },
    )
    watch = asyncio.get_running_loop().create_task(_watch(job, fid))
    try:
        peers.hold_own()
        # a hand's files take no turn with Claude: they wait only for the machine, as a render does
        turn = (
            contextlib.nullcontext()
            if hand
            else sched["claude"].hold(1, rid, on_wait, priority=r0.get("priority", 0))
        )
        async with turn:
            clock.t0, clock.paused = time.time(), 0.0  # the queue was not Claude's time
            _set(film, job, "running", started=_now(), started_at=_now(), now=first)
            await _tell(
                agent,
                film,
                rid,
                {"state": "running", "started_at": store.now(), "now": first},
            )
            emit(
                {
                    "type": "stage",
                    "name": "hand" if hand else "claude",
                    "text": first,
                }
            )
            before = await asyncio.to_thread(digest, film)
            if hand and before != hand["base"]:  # it changed between the asking and its turn
                raise RoundError(409, STALE % version_of(film.record()), "stale")
            work = await asyncio.to_thread(copy_of, film, rid, notes)
            # the copy as it starts, not the film: a copy differs from its film where the studio
            # itself made it differ (the Free plan's closing is taken off its manifest)
            fresh = await asyncio.to_thread(digest, work)
            if r0.get("refresh"):  # after `fresh`: the members laid over are this round's change
                await asyncio.to_thread(lay_over, work, r0["refresh"])
            elif not hand:  # what the series changed since: the newest is this version's too
                state.brought = await asyncio.to_thread(bring_up, work)
            t = toolbox.Tools(work, sched, emit, clock)
            t.priority, t.round, t.pulse = r0.get("priority", 0), state, agent.Pulse()
            if hand:
                await asyncio.to_thread(overlay, work, hand["dir"])
                state.summary = hand["summary"]
                try:
                    await t.check()  # the changed film.js runs, on today's studio
                    if await asyncio.to_thread(_said_differently, film, work):
                        emit({"type": "stage", "name": "voice", "text": "Recording the new words"})
                        await t.voice()
                except toolbox.ToolError as e:
                    raise RoundError(
                        409, "These files do not make a film: %s" % str(e)[:300]
                    ) from None
            else:
                try:
                    await t.check()  # a film from before today's studio may not run on it
                    frames = await pack(work, t, notes)
                except toolbox.ToolError as e:
                    raise RoundError(
                        409, "This film cannot be changed here: %s" % str(e)[:300]
                    ) from None
                past = await asyncio.to_thread(earlier, film, work)
                theirs = "" if r0.get("refresh") else await asyncio.to_thread(project_now, work)
                # the project's rules as the site sent them with the round, else as the film has them
                rules = films.clean_rules(r0.get("rules")) or films.rules_of(rec0)
                if rules:
                    theirs = RULES % "\n".join("- " + x for x in rules) + theirs
                if state.brought:
                    theirs = BROUGHT % "\n".join(
                        "- @%s: version %s, was %s" % (b["name"], b["now"], b["have"]) for b in state.brought
                    ) + theirs
                import library  # noqa: PLC0415

                shared = await asyncio.to_thread(library.body_rules, work)
                if shared:  # where each kind of change goes, and that the cast's reaches the series
                    theirs = "\n\n" + shared + BODY_ROUND + theirs
                else:  # no body: that the cast's changes reach the series all the same
                    theirs = await asyncio.to_thread(library.cast_rules, work) + theirs
                say = {
                    "prompt": ask(work, notes, frames, lim, past, theirs),
                    "system": agent.system_prompt(work.look, work.caps),
                    "effort": EFFORT,
                    "budget_usd": lim["budget_usd"],
                }
                res, late = None, False
                for attempt in (1, 2):
                    try:
                        res = await agent._within(
                            agent.run_claude(work, emit, meter, t, auth, **say), clock, lim, t.pulse
                        )
                        break
                    except (agent.SignInError, agent.PlanLimit) as e:
                        # this machine's Claude plan is gone or spent: the round starts over on the key
                        if auth != "login" or attempt == 2:
                            raise RuntimeError("Claude could not be reached: %s" % e) from None
                        auth = "api"
                        job["reserve"] = reserve(
                            film, len(notes), auth, claude_of(film.record()).get("model")
                        )
                        emit({"type": "fallback", "from": "login", "to": "api", "why": str(e)})
                    except agent.apikey.CreditOut as e:
                        # the credit key's month ran out: the round starts over on the paid key
                        if attempt == 2:
                            raise RuntimeError("Claude could not be reached: %s" % e) from None
                    except agent.Stalled:
                        if attempt == 2 or not t.session:
                            raise RuntimeError("Claude stopped answering") from None
                        left = max(180, lim["claude_s"] - clock.active())
                        say = {
                            "prompt": agent.STALLED % (agent.STALL_S // 60, round(left / 60)),
                            "resume": t.session,
                            "effort": EFFORT,
                            "system": say["system"],
                            "budget_usd": max(1.0, lim["budget_usd"] - meter.usd()),
                        }
                    except TimeoutError:
                        late = True  # past its time: more of it below for the notes left
                        break
                if res is not None and res.is_error:
                    raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))

                async def turn(prompt, secs, effort=None, budget=None):
                    """One more turn of the round's own session, in a time of its own. Never
                    raises: what it changed and answered is judged with the rest."""
                    clock.t0, clock.paused = time.time(), 0.0
                    with contextlib.suppress(Exception):
                        await agent._within(
                            agent.run_claude(
                                work,
                                emit,
                                meter,
                                t,
                                auth,
                                prompt=prompt,
                                resume=t.session,
                                effort=effort or EFFORT,
                                system=say["system"],
                                budget_usd=budget or max(1.0, lim["budget_usd"] / 2),
                            ),
                            clock,
                            {"claude_s": secs, "wall_s": secs + 20 * 60},
                            None,
                        )

                # notes its time ran out on get more of it, sized by them: never "no time"
                for _ in range(MORE if late else 0):
                    left = [notes[i - 1] for i in state.missing()]
                    if not left or not t.session:
                        break
                    more = limits(film.length, len(left), wide(left), reach=weight(left))
                    tell_now("Taking more time for %d of your notes" % len(left), force=True)
                    emit({"type": "log", "text": "more time: notes %s" % state.missing()})
                    await turn(
                        CONTINUE % (", ".join(map(str, state.missing())), more["claude_s"] // 60),
                        more["claude_s"],
                    )
                if state.missing() and t.session:  # one short turn for the notes left unanswered
                    await turn(ANSWER % ", ".join(map(str, state.missing())), 180, "low", 1.0)
                for i in state.missing():
                    state.verdicts[notes[i - 1]["id"]] = {
                        "state": "cannot",
                        "reply": "Claude ran out of time before it reached this note.",
                    }
                # the second look: what is answered done, against its frames, by other eyes; what
                # does not show comes back once. It can be wrong and it can break: neither fails
                # a round, and a note it still doubts says so to its maker.
                import review  # noqa: PLC0415 -- it imports agent, as this function does

                if frames and not r0.get("refresh") and review.enabled():
                    try:
                        import ytdraft  # noqa: PLC0415

                        async def eyes(text, images):
                            return await ytdraft.ask_json(
                                text,
                                images,
                                auth,
                                work,
                                ytdraft.MODEL,
                                review.EFFORT,
                                CHECK_SYSTEM,
                                "round-check",
                            )

                        tell_now("Checking each change against your notes", force=True)
                        seen = await looked(
                            work, t, notes, state.verdicts, frames, eyes, rules=rules
                        )
                        bad = [
                            i
                            for i, x in enumerate(notes, 1)
                            if (seen.get(x["id"]) or {}).get("ok") is False
                        ]
                        for i in bad:
                            why = seen[notes[i - 1]["id"]]["why"]
                            emit({"type": "log", "text": "the second look, note %d: %s" % (i, why)})
                        if bad and t.session:
                            tell_now("Doing %d again that did not show yet" % len(bad), force=True)
                            secs = min(25 * 60, 4 * 60 + 4 * 60 * len(bad))
                            await turn(AGAIN % (again_text(notes, bad, seen), secs // 60), secs)
                            tell_now("Checking them again", force=True)
                            ids = {notes[i - 1]["id"] for i in bad}
                            seen.update(
                                await looked(
                                    work, t, notes, state.verdicts, frames, eyes, ids, rules
                                )
                            )
                        state.checks = seen
                        for x in notes:
                            c, v = seen.get(x["id"]), state.verdicts.get(x["id"])
                            if c and c["ok"] is False and v and v["state"] == "done":
                                v["reply"] = (v["reply"] + " " + UNSURE % c["why"])[:600]
                    except Exception as e:  # noqa: BLE001 -- never fails a round
                        emit({"type": "log", "text": "the second look did not run: %s" % e})
                shown = {}
                if frames and not r0.get("refresh"):
                    try:  # each note's before and after, for its maker: never fails a round
                        shown = await proofs(work, t, notes, frames)
                    except Exception as e:  # noqa: BLE001
                        emit({"type": "log", "text": "no before and after: %s" % e})
            after = await asyncio.to_thread(digest, work)
        if after == fresh:
            await over(
                "unchanged",
                "The files sent are the film's own: nothing is different."
                if hand
                else "Claude read the notes and changed nothing in the film.",
                summary=state.summary,
            )
            return
        if not hand and not any(v["state"] == "done" for v in state.verdicts.values()):
            await over(
                "unchanged",
                "Claude could not make any of the changes asked for.",
                summary=state.summary,
            )
            return
        _set(film, job, "finishing", now="Mixing the soundtrack")
        await _tell(
            agent,
            film,
            rid,
            {"state": "finishing", "now": "Mixing the soundtrack", "notes": verdicts()},
        )
        pin_vo(work)
        pin_paint(work)
        if agent.unvoiced(work):
            raise RuntimeError("the narration was left unrecorded")
        missing = [f for f in films.MADE if not os.path.exists(work.path(f))]
        if missing:
            raise RuntimeError("the film lost %s" % ", ".join(missing))
        # the film as its record says: the Free plan's mark and closing, or none, at its frame rate
        work.update(fps=rec0.get("fps"), branding=bool(rec0.get("branding")))
        if rec0.get("branding"):
            agent.brand(work)
        else:
            agent.debrand(work)
        if await asyncio.to_thread(digest, film) != before:  # before the minutes of drawing
            raise RuntimeError(MOVED)
        emit({"type": "stage", "name": "sound", "text": "Mixing the soundtrack"})
        await t.sound(log=True)
        emit({"type": "stage", "name": "render", "text": "Drawing version %d" % n})
        tell_now("Drawing version %d" % n, force=True)
        await t.render()
        out = work.path("outputs")
        with open(work.manifest, encoding="utf-8") as f:
            m = json.load(f)
        want = float(m.get("duration") or film.length) + float(
            (m.get("tail") or {}).get("secs") or 0
        )
        bad = await asyncio.to_thread(
            unbrand.check, os.path.join(out, "film.mp4"), want, m.get("fps", 60)
        )
        if bad:
            raise RuntimeError(bad)
        emit({"type": "stage", "name": "online", "text": "Putting version %d online" % n})
        tell_now("Putting version %d online" % n, force=True)
        rev = (film.record().get("media_rev") or 0) + 1
        urls = await media.publish(film, out=out, rev=rev)
        if media.enabled() and "video" not in urls:
            raise RuntimeError("the new version could not be copied online")
        await asyncio.to_thread(make_strip, out)
        strip = await media.publish_one(film, STRIP_FILE, "image/jpeg", out=out, rev=rev)
        if strip:
            urls["strip"] = strip
        for nid, name in (shown if not hand else {}).items():
            url = await media.publish_one(
                film, name, "image/jpeg", out=work.path("notes", "after"), rev=rev
            )
            if url:
                state.proofs[nid] = url
        await unbrand._sends_over(fid)
        bill = cost()  # read from the copy, which the swap is about to make the film
        # the film must still be what this copy was made from: whatever wrote into its folder
        # meanwhile would be swapped out under a version that never saw it (KI-061)
        if await asyncio.to_thread(digest, film) != before:
            raise RuntimeError(MOVED)
        entry = await asyncio.to_thread(commit, film, work, urls, rev, n, state.summary, rid)
        if hand:
            await asyncio.to_thread(shutil.rmtree, hand["dir"], True)
        work = None  # its files are the film's now
        _set(
            film,
            job,
            "done",
            finished=_now(),
            server=None,
            now=None,
            summary=state.summary,
            answers=verdicts(),
        )
        _drop_mark(fid)
        if not hand:
            with contextlib.suppress(Exception):
                keep_history(film, rid, n, "done", notes, verdicts(), state.summary)
        rec = film.record()
        await agent.save(
            fid,
            {
                "version": n,
                "versions": rec.get("versions"),
                "words": words(rec),
                "media_rev": rec.get("media_rev"),
                **({"media": rec.get("media")} if urls else {}),
            },
            final=True,
        )
        # the round's document last: by now the film's own says the version exists
        emit({"type": "done", "text": "Version %d" % n})
        await _tell(
            agent,
            film,
            rid,
            {
                "state": "done",
                "error": None,
                "now": None,
                "notes": verdicts(),
                "summary": state.summary,
                "checks": [{"id": k, **v} for k, v in state.checks.items()],
                "rev": entry["rev"],
                **bill,
                "seconds": round(time.time() - t0, 1),
            },
            final=True,
        )
        print("film %s: version %d (%s)" % (fid, n, rid), flush=True)
        _after(film)
        # what the round changed in the cast is the series' now, as a film's is when it finishes:
        # until 2026-11 it stayed in this episode's copy, and no other episode ever had it
        with contextlib.suppress(Exception):
            await agent.keep_cast(film, toolbox.Tools(film, sched, lambda ev: None), lambda ev: None)
        import who  # noqa: PLC0415

        who.ensure(film, sched)  # who is on screen and speaking in it, for its notes page
    except asyncio.CancelledError:
        if job["stopped"] or os.path.exists(_mark(fid) + ".stop"):
            with contextlib.suppress(Exception):
                await over("cancelled", "stopped")
        else:  # the server is stopping, not the round failing: back in the queue for the leader
            with contextlib.suppress(Exception):
                _set(film, job, "queued", server=None, now="Waiting for the studio to restart")
        raise
    except Exception as e:  # noqa: BLE001 -- whatever went wrong, the film itself is untouched
        why = getattr(e, "text", None) or str(e) or type(e).__name__
        if isinstance(e, TimeoutError):
            why = "Claude ran past the %d-minute limit" % (lim["claude_s"] // 60)
        print("film %s: round %s failed: %s" % (fid, rid, why), file=sys.stderr, flush=True)
        with contextlib.suppress(Exception):
            heal(film)
        await over("failed", str(why)[:500])
    finally:
        watch.cancel()
        told.end()
        if work is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(shutil.rmtree, work.dir, True)
        with contextlib.suppress(Exception):
            shutil.rmtree(os.path.join(films.HOME, "claude", rid), ignore_errors=True)


async def _watch(job, fid):
    """A Stop that reached another server (stop): its flag ends this server's job."""
    flag = _mark(fid) + ".stop"
    while True:
        await asyncio.sleep(2)
        if os.path.exists(flag) and job["task"] is not None and not job["task"].done():
            job["stopped"] = True
            job["task"].cancel()
            return


def _after(film):
    """What follows a new version, never the round's to fail: the film's moments for a YouTube
    draft, its link preview's picture, and the thumbnails made for the version before."""
    import share
    import thumbs

    with contextlib.suppress(Exception):
        for name in os.listdir(film.path("youtube")):
            if name.startswith("thumbs-") and name.endswith(".json"):
                os.remove(film.path("youtube", name))
    with contextlib.suppress(Exception):
        thumbs.premake(film)
    with contextlib.suppress(Exception):
        asyncio.get_running_loop().create_task(_reshare(film, share))


async def _reshare(film, share):
    """The share page's pictures drawn from the new version; its words stay (its address is
    made from its title)."""
    try:
        draft = share.cached(film)
        if not draft or not share.enabled():
            return
        got = await share.make(film, draft)
        s = dict(film.record().get("share") or {})
        s.update({k: got[k] for k in ("image", "thumb") if got.get(k)})
        s["at"] = share.utc_now()
        await share.save(film, s)
    except Exception as e:  # noqa: BLE001 -- the version is made; its link preview is a nicety
        print("film %s: its share picture stays the old one: %s" % (film.id, e), flush=True)


# ------------------------------------------------------------------ the swap
def _move(src, dst):
    """One rename; on Windows a file someone has open makes it fail for a moment."""
    for attempt in range(12):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(0.5)


def _gone(p):
    """Remove a file or a tree, read-only files included (Windows refuses those until they are
    made writable; a version kept from a film with read-only files has them)."""

    def again(fn, path, _exc):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        fn(path)

    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, onexc=again)
    elif os.path.lexists(p):
        try:
            os.remove(p)
        except PermissionError as e:
            again(os.remove, p, e)


def _swap(film, src, cur, to):
    """The film's files go to versions/v<cur>/ and the ones in `src` take their place. A marker
    (versions/.swap.json) names the swap until the record has it, so heal() can undo one a
    restart cut short. Returns the names moved in."""
    kept = film.path(KEPT)
    os.makedirs(kept, exist_ok=True)
    out = os.path.join(kept, "v%d" % cur)
    names = sorted(
        {n for n in os.listdir(film.dir) if n not in OWN}
        | {n for n in os.listdir(src) if n not in OWN}
    )
    films._write_json(os.path.join(kept, SWAP), {"cur": cur, "to": to, "src": src, "names": names})
    _gone(out)
    os.makedirs(out)
    for name in names:
        if os.path.lexists(film.path(name)):
            _move(film.path(name), os.path.join(out, name))
    for name in names:
        if os.path.lexists(os.path.join(src, name)):
            _move(os.path.join(src, name), film.path(name))
    return names


def heal(film):
    """Undo a swap a restart cut short (the marker is still there): what came in goes back
    where it came from and the film's own files return. Nothing to do once the record has the
    swap. Returns True when it undid one."""
    mark = film.path(KEPT, SWAP)
    try:
        with open(mark, encoding="utf-8") as f:
            sw = json.load(f)
    except (OSError, ValueError):
        return False
    undone = False
    if version_of(film.record()) != sw.get("to"):
        out = film.path(KEPT, "v%d" % int(sw["cur"]))
        src = sw.get("src") or ""
        for name in sw.get("names") or []:
            old = os.path.join(out, name)
            if not os.path.lexists(old):
                continue  # never moved out: the film's own is still in place
            if os.path.lexists(film.path(name)):  # what had come in: back, or gone with its round
                if os.path.isdir(src):
                    _gone(os.path.join(src, name))
                    _move(film.path(name), os.path.join(src, name))
                else:
                    _gone(film.path(name))
            _move(old, film.path(name))
        with contextlib.suppress(OSError):
            os.rmdir(out)
        undone = True
    with contextlib.suppress(OSError):
        os.remove(mark)
    return undone


def _done(film):
    with contextlib.suppress(OSError):
        os.remove(film.path(KEPT, SWAP))


def commit(film, work, urls, rev, n, summary, rid):
    """The round's version takes the film's place: its files, then the record. The film's own
    go to versions/v<cur>/. Returns the new version's entry."""
    rec = film.record()
    cur = version_of(rec)
    vs = list(rec.get("versions") or [])
    if not any(v.get("n") == cur for v in vs):  # a film whose notes were never opened on the site
        vs.append(entry_of(film, cur))
    # what each tool spent on the film so far goes on in its file, the round's after it
    for parts in SPENT:
        old, new = film.path(*parts), work.path(*parts)
        if os.path.isfile(old):
            os.makedirs(os.path.dirname(new), exist_ok=True)
            with open(old, encoding="utf-8") as a:
                before = a.read()
            after = ""
            if os.path.isfile(new):
                with open(new, encoding="utf-8") as b:
                    after = b.read()
            with open(new, "w", encoding="utf-8") as b:
                b.write(before + after)
    for junk in ("studio.json", "notes", "temp", "events.jsonl"):  # the copy's own, not a version's
        _gone(work.path(junk))
    _swap(film, work.dir, cur, n)
    shutil.rmtree(work.dir, ignore_errors=True)
    entry = entry_of(
        film,
        n,
        urls=urls or {},
        rev=rev if urls else (rec.get("media_rev") or 0),
        summary=summary,
        rid=rid,
    )
    vs = sorted([v for v in vs if v.get("n") != n] + [entry], key=lambda v: v["n"])
    fields = {"version": n, "versions": prune(film, vs, n), "direction": film.direction()}
    if urls:
        fields.update(media={k: v for k, v in urls.items() if k != "strip"}, media_rev=rev)
    film.update(**fields)
    _done(film)
    return entry


def prune(film, vs, cur):
    """Keep the files of the last KEEP versions that are not the film; an older one's go (it
    still plays from its copy online, and can no longer be made the film again)."""
    old = sorted((v["n"] for v in vs if v["n"] != cur and v.get("kept", True)), reverse=True)
    for n in old[KEEP:]:
        with contextlib.suppress(OSError):
            _gone(film.path(KEPT, "v%d" % n))
    drop = set(old[KEEP:])
    return [dict(v, kept=False) if v["n"] in drop else v for v in vs]


def use(film, n):
    """Version n is the film again: its files come back from versions/v<n>/ and the film's go
    to versions/v<cur>/. Nothing is rendered. Raises RoundError when it cannot be."""
    rec = film.record()
    cur = version_of(rec)
    vs = list(rec.get("versions") or [])
    want = next((v for v in vs if v.get("n") == n), None)
    if want is None:
        raise RoundError(404, "This film has no version %s." % n)
    if n == cur:
        return rec
    if (rec.get("round") or {}).get("state") in ACTIVE or film.id in in_flight():
        raise RoundError(409, "A round of changes to this film is being made.", "round")
    if any(j["film"] == film.id and j["state"] == "sending" for j in youtube.SENDS.values()):
        raise RoundError(
            409, "The film is being sent to YouTube; try again in a few minutes.", "sending"
        )
    if film.id in unbrand.in_flight():
        raise RoundError(
            409, "The film is being drawn again; try again in a few minutes.", "unbrand"
        )
    src = film.path(KEPT, "v%d" % n)
    if not want.get("kept", True) or not os.path.isfile(os.path.join(src, "film.js")):
        raise RoundError(
            404, "Version %d's files are no longer kept; it can still be watched." % n, "gone"
        )
    heal(film)
    _swap(film, src, cur, n)
    with contextlib.suppress(OSError):
        os.rmdir(src)
    fields = {"version": n, "media_rev": want.get("rev") or 0}
    m = {k: v for k, v in (want.get("media") or {}).items() if k != "strip"}
    if m:
        fields["media"] = m
    rec = film.update(**fields)
    _done(film)
    return rec


# ------------------------------------------------------------------ by hand
async def _by_hand(args):
    import agent
    from sched import Sched

    film = films.Film.open(args.film)
    if film is None:
        sys.exit("no film %s in %s" % (args.film, films.HOME))
    with open(args.notes, encoding="utf-8") as f:
        notes = json.load(f)
    notes = notes.get("notes") if isinstance(notes, dict) else notes
    for i, n in enumerate(notes, 1):
        n.setdefault("id", "n%d" % i)
    rec = film.record()
    lim = limits(
        film.length,
        len(notes),
        wide(notes),
        model=claude_of(film.record()).get("model"),
        reach=weight(notes),
    )
    plan = {
        "film": film.id,
        "version": version_of(rec),
        "makes": version_of(rec) + 1,
        "notes": len(notes),
        "claude_minutes": lim["claude_s"] // 60,
        "budget_usd": lim["budget_usd"],
        "words": words(rec),
        "rounds_today": rounds_today(rec),
    }
    print(json.dumps(plan, indent=2))
    try:
        clean_notes(film, notes)
    except RoundError as e:
        sys.exit("not a round: " + e.text)
    if args.plan:
        return
    agent.procs.cgroup_root()
    await prepare(film)
    job = start(film, Sched(), notes, auth=args.auth, src=version_of(rec))
    with contextlib.suppress(asyncio.CancelledError):
        await job["task"]
    r = film.record().get("round") or {}
    print(json.dumps({k: r.get(k) for k in ("id", "n", "state", "error", "summary")}, indent=2))
    doc = await asyncio.to_thread(agent.STORE.get, job["rid"])
    for v in (doc or {}).get("notes") or []:
        print("  %s: %s  %s" % (v.get("id"), v.get("state"), v.get("reply") or ""))
    sys.exit(0 if r.get("state") == "done" else 1)


def main():
    import argparse

    import agent

    agent._env.utf8_stdio()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("film", help="the film's id (studio-YYYYMMDD-HHMMSS-xxxxxx)")
    ap.add_argument("--notes", help='a JSON file: [{"kind", "t", "text", ...}]')
    ap.add_argument(
        "--where", action="store_true", help="print the film's version and digest, as JSON"
    )
    ap.add_argument("--plan", action="store_true", help="say what it would do; spend nothing")
    ap.add_argument(
        "--auth", choices=("api", "login"), default="api", help="how Claude is paid for"
    )
    args = ap.parse_args()
    if args.where:
        film = films.Film.open(args.film)
        if film is None:
            sys.exit("no film %s in %s" % (args.film, films.HOME))
        print(json.dumps(where(film)))
        return
    if not args.notes:
        ap.error("--notes <file>, or --where")
    asyncio.run(_by_hand(args))


if __name__ == "__main__":
    main()
