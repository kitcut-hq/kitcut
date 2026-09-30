"""A film's YouTube thumbnail options: four moments of the film itself, each with a few big words.

The draft (ytdraft.py) picks them: Claude, which already writes the title and description from
the film, is shown the film's moments -- a sheet of clean stills with their times, made here --
and answers with four {at, words, layout, place}, the first the video's main message. The
options are then made from the film with scripts/_thumb.py, drawn by the film itself in its own
look (its title type and outline, colours, labels, logo) the way YouTube thumbnails are made: the
frame near each moment that is not mid-transition, the film's own words left out of it, its
subject pushed in on one side and the words large on the other, checked to be legible at
YouTube's smallest size, in contrast, and clear of its duration stamp. An option that fails a
check falls back (a glow of the film's paper, one of its cards, the frame alone) before anyone
sees it. Options saved under an older design (_thumb.DESIGN) are made again.

    outputs/youtube/<channel>/thumb-<n>.jpg   the options (served by /files, token or signed)
    youtube/thumbs-<channel>.json             what they are, keyed by the draft they came from
    temp/thumbs/                              the stills, the moments sheet (per film, cached)

Nothing here spends: the stills and the options are this machine's CPU and a headless browser,
at most JOBS at a time. The site picks one option and sets it on the video with its own grant.
"""

import os
import sys
import json
import time
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _thumb  # noqa: E402 -- imports _env first

JOBS = int(os.environ.get("STUDIO_THUMB_JOBS", "2"))  # films making stills or options at once
_GATE = None


def gate():
    """The browser runs thumbnails may hold at once (the films' own renders need theirs)."""
    global _GATE
    if _GATE is None:
        _GATE = asyncio.Semaphore(JOBS)
    return _GATE


def length(film):
    try:
        return float(film.length)
    except (OSError, ValueError, KeyError, TypeError):
        return _thumb.film_length(film.dir)


def moments(film):
    """The times the draft picks thumbnails from (cheap: the voice timeline and the length)."""
    return _thumb.moment_times(_thumb.narration(film.dir), length(film))


def sheet_path(film):
    return film.path("temp", "thumbs", "moments-%s.jpg" % _thumb.film_key(film.dir))


def sheet_now(film):
    """The moments sheet as JPEG bytes, made once per film (a finished film does not change)."""
    p = sheet_path(film)
    if not os.path.exists(p):
        stills = _thumb.render_stills(film.dir, moments(film))
        _thumb.moments_sheet(stills, p + ".tmp.jpg")
        os.replace(p + ".tmp.jpg", p)
    with open(p, "rb") as f:
        return f.read()


_SHEETS = {}  # film id -> asyncio.Lock: one film's sheet is made once, however many ask at once


async def sheet(film):
    """sheet_now, off the event loop and through the gate; None when the film will not draw (the
    draft then sees its review sheet or poster instead, as it did before thumbnails). A second
    ask while the first is making it waits for that one, then reads what it made."""
    async with _SHEETS.setdefault(film.id, asyncio.Lock()):
        try:
            if os.path.exists(sheet_path(film)):
                return await asyncio.to_thread(sheet_now, film)  # made already: just read
            async with gate():
                return await asyncio.to_thread(sheet_now, film)
        except Exception as e:  # noqa: BLE001 -- a draft without the sheet is still a draft
            print("thumbs: no moments sheet for %s: %s" % (film.id, e), flush=True)
            return None


def premake(film):
    """Make a finished film's moments sheet now, in the background, so the draft finds it made:
    the sheet is ~10-20 s of browser, and a draft that had to make it first took 25-35 s instead
    of the 10-16 s the dialog had before thumbnails (the first real publish, 2026-09-29)."""
    try:
        return asyncio.get_running_loop().create_task(sheet(film))
    except RuntimeError:  # no loop (a script): the draft makes it when it is asked for
        return None


def out_dir(film, channel):
    return film.path("outputs", "youtube", channel)


def record_path(film, channel):
    return film.path("youtube", "thumbs-%s.json" % channel)


def saved(film, channel, key=None):
    """The options made for this channel's draft `key` (any draft when key is None), or None."""
    try:
        with open(record_path(film, channel), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or (key is not None and rec.get("key") != key):
        return None
    if rec.get("design") != _thumb.DESIGN:  # made under an older design: made again
        return None
    if not all(os.path.exists(film.path("outputs", o["path"])) for o in rec.get("options") or []):
        return None
    return rec


def make_now(film, channel, draft, want=4):
    """The `want` options for a draft -- four for YouTube (blocking: stills, layout, one browser
    shot, checks). Fewer concepts than that are made up from the film; more are cut."""
    t0 = time.time()
    concepts = (draft.get("thumbnails") or [])[:want]
    if len(concepts) < want:
        concepts = _thumb.fill_concepts(concepts, moments(film), length(film), n=want)
    d = out_dir(film, channel)
    opts = _thumb.make_options(film.dir, concepts, d, log=lambda *_: None)
    rec = {
        "key": draft.get("key"),
        "design": _thumb.DESIGN,
        "channel": channel,
        "options": [
            {
                "n": o["n"],
                "path": "youtube/%s/thumb-%d.jpg" % (channel, o["n"]),
                "layout": o["layout"],
                "requested": o["requested"],
                "words": _thumb.plain(o["words"]),
                "logo": o.get("logo", False),
                "at": o["at"],
                "t": o["t"],
                "checks": {k: v for k, v in o["checks"].items() if k != "ink_box"},
                "notes": o["notes"],
            }
            for o in opts
        ],
        "seconds": round(time.time() - t0, 1),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    os.makedirs(os.path.dirname(record_path(film, channel)), exist_ok=True)
    tmp = record_path(film, channel) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False)
    os.replace(tmp, record_path(film, channel))
    return rec


async def make(film, channel, draft, want=4):
    """make_now off the event loop and through the gate; the saved options when they already
    match this draft."""
    hit = saved(film, channel, draft.get("key"))
    if hit:
        return hit
    async with gate():
        return await asyncio.to_thread(make_now, film, channel, draft, want)


def public(rec, state=None):
    """What the site is told: the state and, when done, each option's picture and words."""
    if rec is None:
        return {"state": state or "none"}
    if rec.get("state") in ("making", "failed"):
        return {k: rec[k] for k in ("state", "error") if rec.get(k)}
    return {
        "state": "done",
        "v": rec.get("key"),
        "options": [
            {k: o[k] for k in ("n", "path", "layout", "words", "at", "t")}
            for o in rec.get("options") or []
        ],
    }
