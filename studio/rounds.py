#!/usr/bin/env python
"""A round of changes to a finished film: its maker's notes, made by Claude into the film's next
version -- the same film, the same page, the same link.

    GET  /api/films/<id>/versions                the film's versions, and how a round stands
    POST /api/films/<id>/versions                {"key", "from", "notes": [...]}: make the next one
    POST /api/films/<id>/versions/stop           stop the round being made
    POST /api/films/<id>/versions/<n>/current    version n is the film again (no rendering)

    python studio/rounds.py <film-id> --notes notes.json [--plan]     a round by hand, beside the
                                                 server (on the VM: ops.sh notes <film-id> <file>)

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
MAX_NOTES = 20
NOTE_MAX = 500  # characters of a note, and of a line as it should be said
PER_DAY = int(os.environ.get("STUDIO_ROUNDS_PER_DAY") or 5)  # rounds a film may have in a day
TRIES = 2  # how often a round is started again after its server went away
KEEP = 3  # versions whose files are kept beside the film's own; older ones stay watchable online
EFFORT = "high"  # a round changes a film that exists: it reads more than it invents
STRIP = (24, 160)  # the filmstrip: tiles in a row, and a tile's width in px
STRIP_FILE = "strip.jpg"
RING = (217, 115, 63)  # the colour a note's spot is ringed in on its frame

JOBS = {}  # film id -> the round being made here
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
def limits(length, notes):
    """A round's allowance: Claude's working time by its notes, half the film's budget."""
    lim = films.limits(length)
    work = min(25 * 60, 8 * 60 + 60 * notes)
    return lim | {
        "claude_s": work,
        "wall_s": work + 20 * 60,
        "budget_usd": max(2.0, round(lim["budget_usd"] / 2, 2)),
        "reserve_usd": round(max(1.0, lim["reserve_usd"] / 2), 2),
    }


def reserve(film, notes, auth):
    """What a round may still spend, held against the day's budget (server.reserve, halved)."""
    lim = limits(film.length, notes)
    return lim["reserve_usd"] if auth == "api" else 0.005 * film.length


# ------------------------------------------------------------------ what the film's record says
def version_of(rec):
    return int(rec.get("version") or 1)


def words(rec):
    """May a round change what is said? Not in a person's own ElevenLabs voice yet (its pass to
    their account is for the film's making, and has run out), and not where nothing is said."""
    if (rec.get("narrator") or {}).get("source") == "elevenlabs":
        return {"can": False, "why": "own_voice"}
    if rec.get("narration") is False:
        return {"can": False, "why": "no_voice"}
    return {"can": True}


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
def clean_notes(film, notes):
    """The notes as the studio keeps them: [{id, kind, t, t2, x, y, line, was, words, text}],
    times inside the film. Raises RoundError for what cannot be a round."""
    rec = film.record()
    if not isinstance(notes, list) or not notes:
        raise RoundError(400, "Send the notes: a list of at least one.")
    if len(notes) > MAX_NOTES:
        raise RoundError(400, "That is %d notes; a round takes up to %d." % (len(notes), MAX_NOTES))
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
            if not words(rec)["can"]:
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
        await asyncio.to_thread(make_strip, out)
    fresh = entry_of(film, n)
    url = await media.publish_one(film, STRIP_FILE, "image/jpeg")
    if url:
        fresh["media"]["strip"] = url
    if cur is not None:  # what a round said of it stays
        fresh.update({k: cur[k] for k in ("at", "summary", "round") if cur.get(k) is not None})
    vs = sorted([v for v in vs if v.get("n") != n] + [fresh], key=lambda v: v["n"])
    rec = film.update(version=n, versions=vs)
    await agent.save(film.id, {"version": n, "versions": vs, "words": words(rec)})
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
    for parts in SPENT:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(d, *parts))
    work = films.Film(d)
    rec = dict(film.record())
    for k in ("server", "media", "media_rev", "share", "unbrand", "round", "versions", "version"):
        rec.pop(k, None)
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
        want = films.paint_pins(float(rec.get("length") or work.length), probe.caps)
        pins["paint"] = {k: paint.get(k, v) for k, v in want.items()}
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


def notes_text(notes, lines, frames):
    """The notes as Claude reads them (its first message, and notes/notes.md)."""
    out = []
    for i, n in enumerate(notes, 1):
        if n["kind"] == "film":
            head = "the whole film"
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
        if frames.get(n["id"]):
            ring = " (the orange ring is the spot)" if n["kind"] == "spot" else ""
            body.append("   The frame at %s: %s%s" % (_mmss(frame_time(n)), frames[n["id"]], ring))
        out.append("\n".join(body))
    return "\n\n".join(out)


ASK = """\
This film is finished, and its maker has watched it and left notes on it. Make the changes the \
notes ask for, and nothing else: the maker kept everything they did not mention.

The film is in this folder as it was made: film.js, vo.json (the narration's words), \
score.json, sfx.json%(extra)s, and the recording's timeline in audio/vo/timeline.json. Its own \
copy of the engine is in engine/ (when it differs from the reference above, the film's copy is \
what runs). Read film.js first.

Length: %(length)d seconds, fixed: the film still ends where it ends. Your working time: about \
%(minutes)d minutes (waiting for the machine is not counted).

The notes (also in notes/notes.md):

%(notes)s

How to work:
- Look at each note's frame first (Read it), then find in film.js what draws what the note \
points at, by its time and what is on the frame.
- Change only what a note asks for. Around it, the same scenes, timing, words and music.
- After changing the picture: `check`, then `stills` at the notes' moments, and look: is it \
what was asked, and is everything near it still right?
%(voice)s- After changing score.json, sfx.json or the narration: `sound`.
- Each note gets exactly one `note` call when you are done with it: its number, whether it is \
done, and one plain sentence for the maker saying what you changed (no file names, no code \
words). A note you could not or should not do -- unclear, or it would break the film, or the \
film cannot hold it -- gets `note` with done false and one sentence saying why and what would \
make it possible. Do not guess at a note you cannot read: say so.
- Last, `summary`: one short paragraph, in plain words, of what is different in this version.
- Do not render the film; the studio does that when you are done.
"""
VOICE = (
    "- A line that should be said differently: change that line's text in vo.json in place "
    "(never add, remove or reorder lines), keep it about as long as it was, then `voice` with "
    "retake_line. Cues placed on words follow the new recording; look at any cue on a word you "
    "changed.\n"
)
NO_VOICE = (
    "- The narration stays as recorded: this film's words cannot be changed in a round, and "
    "there is no `voice` tool. A note that asks for other words gets `note` with done false.\n"
)
ANSWER = (
    "Before you stop: these notes have no `note` yet: %s. Call `note` for each now (done or "
    "not, one sentence), then `summary` if you have not. Change nothing else."
)


def ask(work, notes, frames, lim):
    extra = "".join(", " + n for n in work.editable() if n not in films.EDITABLE)
    return ASK % {
        "extra": extra,
        "length": work.length,
        "minutes": lim["claude_s"] // 60,
        "notes": notes_text(notes, timeline(work), frames),
        "voice": VOICE if words(work.record())["can"] else NO_VOICE,
    }


class Round:
    """What a round adds to the film's tools (tools.Tools.round): `note` and `summary`, and the
    verdicts they collect."""

    def __init__(self, notes, can_voice, on_change):
        self.notes, self.on_change = notes, on_change
        self.verdicts, self.summary = {}, None  # note id -> {"state", "reply"}
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
    """notes/: each timed note's frame, drawn from the film's code at that moment (exact, where
    a frame cut from the video is a compressed neighbour), a spot ringed on it; and notes.md.
    Returns {note id: "notes/<n>.png"}."""
    from PIL import Image, ImageDraw

    os.makedirs(work.path("notes"), exist_ok=True)
    timed = [(i, n, frame_time(n)) for i, n in enumerate(notes, 1) if frame_time(n) is not None]
    timed = timed[: toolbox.MAX_STILLS]
    frames = {}
    if timed:
        await t.stills(sorted({ts for _, _, ts in timed}), sheet=False)
        for i, n, ts in timed:
            src = work.path("outputs", "review", "%06.2f.png" % ts)
            if not os.path.isfile(src):
                continue
            with Image.open(src) as im:
                im = im.convert("RGB")
                if n["kind"] == "spot":
                    d = ImageDraw.Draw(im)
                    cx, cy, r = n["x"] * im.width, n["y"] * im.height, max(18, im.width // 55)
                    for k, col in ((r + 5, (255, 255, 255)), (r, RING)):
                        d.ellipse((cx - k, cy - k, cx + k, cy + k), outline=col, width=5)
                im.thumbnail((1280, 1280))
                im.save(work.path("notes", "%d.png" % i))
            frames[n["id"]] = "notes/%d.png" % i
    with open(work.path("notes", "notes.md"), "w", encoding="utf-8") as f:
        f.write("# The maker's notes\n\n" + notes_text(notes, timeline(work), frames) + "\n")
    return frames


# ------------------------------------------------------------------ asking
def start(
    film, sched, notes, key=None, client="local", member=None, priority=0, auth="api", src=None
):
    """Make this finished film's next version from these notes; the round's job. Asked again
    with the same key, the round already asked for. Raises RoundError for what cannot be one.
    `src`: the version the notes were written on (it must be the film now)."""
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
    if rounds_today(rec) >= PER_DAY:
        raise RoundError(
            429, "This film has had its %d rounds of changes for today." % PER_DAY, "rounds"
        )
    notes = clean_notes(film, notes)
    return _begin(film, sched, notes, key, client, member, priority, auth)


def _begin(film, sched, notes, key, client, member, priority, auth, tries=1, asked=None, k=None):
    rec = film.record()
    k = k or (rec.get("rounds") or 0) + 1
    rid, n = (
        "%s.r%d" % (film.id, k),
        max([version_of(rec)] + [v.get("n", 0) for v in rec.get("versions") or []]) + 1,
    )
    asked = asked or _now()
    days = list(rec.get("round_days") or [])[-20:] + ([asked] if tries == 1 else [])
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
        },
    )
    _set_mark(film.id)
    job = {
        "film": film.id,
        "rid": rid,
        "n": n,
        "state": "queued",
        "client": client,
        "reserve": reserve(film, len(notes), auth),
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
    notes, auth = r0.get("notes") or [], r0.get("auth") or "api"
    lim = limits(film.length, len(notes))
    log = film.path(KEPT, "r%s.events.jsonl" % rid.rsplit(".r", 1)[-1])
    os.makedirs(os.path.dirname(log), exist_ok=True)
    t0, meter, clock = time.time(), agent.Meter(), Clock()
    said = {"at": 0.0, "now": None}
    state = Round(notes, words(film.record())["can"], lambda text: tell_now(text, force=True))
    work = None

    def verdicts():
        return [
            {"id": x["id"], **(state.verdicts.get(x["id"]) or {"state": "sent", "reply": None})}
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
            "host": store.HOST,
            "model": agent.MODEL,
            "effort": EFFORT,
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
        async with sched["claude"].hold(1, rid, on_wait, priority=r0.get("priority", 0)):
            clock.t0, clock.paused = time.time(), 0.0  # the queue was not Claude's time
            _set(film, job, "running", started=_now(), started_at=_now(), now="Reading your notes")
            await _tell(
                agent,
                film,
                rid,
                {"state": "running", "started_at": store.now(), "now": "Reading your notes"},
            )
            emit({"type": "stage", "name": "claude", "text": "Reading your notes"})
            before = await asyncio.to_thread(digest, film)
            work = await asyncio.to_thread(copy_of, film, rid, notes)
            t = toolbox.Tools(work, sched, emit, clock)
            t.priority, t.round, t.pulse = r0.get("priority", 0), state, agent.Pulse()
            try:
                await t.check()  # a film from before today's studio may not run on it
                frames = await pack(work, t, notes)
            except toolbox.ToolError as e:
                raise RoundError(
                    409, "This film cannot be changed here: %s" % str(e)[:300]
                ) from None
            say = {
                "prompt": ask(work, notes, frames, lim),
                "system": agent.system_prompt(work.look, work.caps),
                "effort": EFFORT,
                "budget_usd": lim["budget_usd"],
            }
            res = None
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
                    job["reserve"] = reserve(film, len(notes), auth)
                    emit({"type": "fallback", "from": "login", "to": "api", "why": str(e)})
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
                    break  # past its time: what it changed and answered so far is judged below
            if res is not None and res.is_error:
                raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
            if state.missing() and t.session:  # one short turn for the notes left unanswered
                last = {
                    "prompt": ANSWER % ", ".join(map(str, state.missing())),
                    "resume": t.session,
                    "effort": "low",
                    "system": say["system"],
                    "budget_usd": 1.0,
                }
                with contextlib.suppress(Exception):
                    await agent._within(
                        agent.run_claude(work, emit, meter, t, auth, **last),
                        Clock(),
                        {"claude_s": 180, "wall_s": 600},
                        None,
                    )
            for i in state.missing():
                state.verdicts[notes[i - 1]["id"]] = {
                    "state": "cannot",
                    "reply": "Claude ran out of time before it reached this note.",
                }
            after = await asyncio.to_thread(digest, work)
        if after == before:
            await over(
                "unchanged",
                "Claude read the notes and changed nothing in the film.",
                summary=state.summary,
            )
            return
        if not any(v["state"] == "done" for v in state.verdicts.values()):
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
        await unbrand._sends_over(fid)
        bill = cost()  # read from the copy, which the swap is about to make the film
        entry = await asyncio.to_thread(commit, film, work, urls, rev, n, state.summary, rid)
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
                "rev": entry["rev"],
                **bill,
                "seconds": round(time.time() - t0, 1),
            },
            final=True,
        )
        print("film %s: version %d (%s)" % (fid, n, rid), flush=True)
        _after(film)
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
    lim = limits(film.length, len(notes))
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
    ap.add_argument("--notes", required=True, help='a JSON file: [{"kind", "t", "text", ...}]')
    ap.add_argument("--plan", action="store_true", help="say what it would do; spend nothing")
    ap.add_argument(
        "--auth", choices=("api", "login"), default="api", help="how Claude is paid for"
    )
    asyncio.run(_by_hand(ap.parse_args()))


if __name__ == "__main__":
    main()
