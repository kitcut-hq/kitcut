"""A finished film, drawn again without the Free plan's mark and closing.

A film made on the Free plan carries "made with kitcut.ai" in its corner and ends with KitCut's
closing (agent.brand, outro.js). When its maker moves to a paid plan the site asks for the same
film without them, at the plan's frame rate:

    POST /api/films/<id>/unbrand        X-Fps: 30|60, X-Priority: 1   -> {"branded", "unbrand"}

Nothing is written or voiced again and Claude is not called: the film is deterministic code, its
voice takes and its mix are kept, and the branding is one manifest key (`tail`). So this is a
render, and it costs machine minutes only.

The film must stay what it is until the new one exists -- someone has it, and may be watching it.
So nothing here touches the film's state, its finish time, its costs or its log, and none of it
goes through agent.make_film (whose failure path marks a film failed and takes its files off its
page). The new film is made BESIDE the old one:

    sketch.clean.json    the film's manifest without its `tail`, at the asked frame rate, with
                         "work": "temp/unbrand" -- so every tool reads the film's own files and
                         writes into temp/unbrand/{audio,outputs,temp} (scripts/_sketch.py load)
    sound                the film's own un-mastered mix cut at the film's end and mastered again
                         (sketch-audio.py --from-mix): what its maker heard, minus the closing
    render               sketch-render.py, as the final render does it, on the server's pools
    online               under the next revision's names (media.blob_of: a film's files are served
                         as immutable for a year, so a changed film needs new ones)

and only then swapped in: the files moved over the old ones, then the record -- `branding` false,
the frame rate, the new addresses, `unbrand` done. A failure at any step leaves the film exactly
as it was and says so in `unbrand` ({"state": "failed", "error"}); it can be asked for again.

One film at a time (a final render takes every browser the machine has). A job lives in the
memory of the server running it; the record's `unbrand` names that server, and a small file in
<home>/unbrand/ marks every film asked for and not yet over, so the leader can pick up one whose
server went away (orphans, as server.adopt does for films) without reading every film's record.
"""

import os
import json
import time
import shutil
import asyncio
import contextlib
import subprocess
from datetime import datetime

import film as films
import media
import peers
import store
import tools as toolbox
import youtube

WORK = ("temp", "unbrand")  # inside the film: where the second render is made
SIDE = "sketch.clean.json"  # the manifest it is made from
MARKS = os.path.join(films.HOME, "unbrand")  # <film id>.json: asked for, not yet over
TRIES = 3  # how often one film's is started again after its server went away
SEND_WAIT_S = 1800  # the longest the swap waits for a YouTube send of the film to end
# what replaces the film's own, once the new film is whole: (folder, file); the video last, so a
# reader between two renames still finds a film that plays
SWAP = (
    ("outputs", "film_poster.png"),
    ("outputs", "card.jpg"),
    ("outputs", "film.html"),
    ("outputs", os.path.join("artifact", "film.html")),
    ("audio", "mix_pre.wav"),
    ("audio", "final.wav"),
    ("audio", "final.mp3"),
    ("outputs", "film_web.mp4"),
    ("outputs", "film.mp4"),
)

JOBS = {}  # film id -> {"film", "state", "fps", "priority", "task"}
_ONE = {}  # the running loop -> its one-at-a-time lock


class UnbrandError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _one():
    loop = asyncio.get_running_loop()
    if loop not in _ONE:
        _ONE.clear()  # a test's earlier loop
        _ONE[loop] = asyncio.Lock()
    return _ONE[loop]


def public(rec):
    """What a film's status says of its branding: whether it carries it, and how removing it
    stands (queued, running, done, failed), when it was ever asked for."""
    out = {"branded": bool(rec.get("branding"))}
    st = (rec.get("unbrand") or {}).get("state")
    if st:
        out["unbrand"] = st
    return out


def in_flight():
    """The films this server is drawing again (or has queued to), for its heartbeat."""
    return [fid for fid, j in JOBS.items() if j["task"] is not None and not j["task"].done()]


# ------------------------------------------------------------------ the marks
def _mark(fid):
    return os.path.join(MARKS, fid + ".json")


def _set_mark(fid):
    with contextlib.suppress(OSError):
        os.makedirs(MARKS, exist_ok=True)
        with open(_mark(fid), "w", encoding="utf-8") as f:
            json.dump({"film": fid, "server": peers.SERVER_ID, "t": time.time()}, f)


def _drop_mark(fid):
    with contextlib.suppress(OSError):
        os.remove(_mark(fid))


def orphans():
    """The films asked for whose server is gone: [(film, its record's unbrand)]. Marks whose
    film is over, or gone, are forgotten."""
    out = []
    with contextlib.suppress(OSError):
        for name in sorted(os.listdir(MARKS)):
            fid = name[: -len(".json")]
            f = films.Film.open(fid) if name.endswith(".json") else None
            u = (f.record().get("unbrand") or {}) if f is not None else {}
            if u.get("state") not in ("queued", "running"):
                _drop_mark(fid)
            elif fid not in JOBS and not peers.alive(u.get("server")):
                out.append((f, u))
    return out


# ------------------------------------------------------------------ asking
def start(film, sched, fps=60, priority=0, by=None):
    """Draw this finished, branded film again without its branding; its job (the one already
    going, when there is one). Raises UnbrandError for a film there is nothing to do for."""
    rec = film.record()
    if rec.get("state") != "done" or not rec.get("ok"):
        raise UnbrandError(409, "This film is not finished.")
    job = JOBS.get(film.id)
    if job is not None and job["task"] is not None and not job["task"].done():
        return job
    if not rec.get("branding"):
        raise UnbrandError(409, "This film carries no KitCut branding.")
    was = rec.get("unbrand") or {}
    carried = was.get("state") in ("queued", "running")  # picked up from a server that went
    tries = (was.get("tries") or 0) + 1 if carried else 1
    fps = 30 if fps == 30 else 60
    asked = was.get("asked") if carried else _now()
    film.update(
        unbrand={
            "state": "queued",
            "fps": fps,
            "priority": int(bool(priority)),
            "asked": asked,
            "by": by or was.get("by"),
            "server": peers.SERVER_ID,
            "tries": tries,
        }
    )
    _set_mark(film.id)
    job = {"film": film.id, "state": "queued", "fps": fps, "priority": int(bool(priority))}
    JOBS[film.id] = job
    job["task"] = asyncio.get_running_loop().create_task(_run(job, film, sched))
    return job


def resume(film, sched):
    """An orphan's (orphans): started again here, or given up after TRIES. One whose new film
    had already taken the old one's place when its server went is only recorded as done."""
    import agent  # as in _run

    rec = film.record()
    u = rec.get("unbrand") or {}
    loop = asyncio.get_running_loop()
    if not rec.get("branding"):  # swapped in (commit), and never said so
        u = dict(u, state="done", finished=u.get("finished") or _now(), server=None)
        film.update(unbrand=u)
        _drop_mark(film.id)
        fields = {"branding": False, "fps": rec.get("fps"), "unbrand": {"state": "done"}}
        if rec.get("media"):
            fields.update(media=rec["media"], media_rev=rec.get("media_rev"))
        loop.create_task(agent.save(film.id, fields, final=True))
        return None
    if (u.get("tries") or 0) >= TRIES:
        why = "the studio restarted %d times while it was being drawn again" % TRIES
        _fail(film, why)
        loop.create_task(
            agent.save(film.id, {"unbrand": {"state": "failed", "error": why}}, final=True)
        )
        return None
    with contextlib.suppress(UnbrandError):
        return start(film, sched, u.get("fps") or 60, u.get("priority") or 0, u.get("by"))
    _drop_mark(film.id)  # no longer a film this applies to
    return None


async def stop_all():
    """The server is stopping: its jobs go back to the queue for the next leader (orphans)."""
    tasks = [j["task"] for j in JOBS.values() if j["task"] is not None and not j["task"].done()]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=15)


# ------------------------------------------------------------------ the job
def _set(film, job, state, **more):
    job["state"] = state
    u = dict(film.record().get("unbrand") or {})
    u.update(state=state, **more)
    film.update(unbrand=u)
    return u


def _fail(film, why):
    u = dict(film.record().get("unbrand") or {})
    u.update(state="failed", error=str(why)[:500], finished=_now(), server=None)
    film.update(unbrand=u)
    _drop_mark(film.id)
    return u


async def _run(job, film, sched):
    import agent  # here, not at the top: agent imports this module's siblings as it loads

    fid = film.id
    await agent.save(fid, {"unbrand": {"state": "queued", "asked_at": store.now()}})
    try:
        async with _one():
            _set(film, job, "running", started=_now())
            await agent.save(fid, {"unbrand": {"state": "running", "asked_at": store.now()}})
            side = await redraw(film, sched, job["fps"], job["priority"])
            rev = (film.record().get("media_rev") or 0) + 1
            urls = await media.publish(film, out=os.path.join(side, "outputs"), rev=rev)
            if media.enabled() and "video" not in urls:
                raise UnbrandError(502, "the new film could not be copied online")
            await _sends_over(fid)
            before = commit(film, side, urls, rev, job["fps"])
        done = _set(film, job, "done", finished=_now(), server=None, before=before)
        _drop_mark(fid)
        rec = film.record()
        fields = {
            "branding": False,
            "fps": rec.get("fps"),
            "unbrand": {"state": "done", "finished_at": store.now(), "before": before},
        }
        if urls:
            fields.update(media=rec.get("media"), media_rev=rec.get("media_rev"))
        await agent.save(fid, fields, final=True)
        print("film %s: its branding is gone (%s)" % (fid, done.get("finished")), flush=True)
    except asyncio.CancelledError:
        # the server is stopping, not the film failing: back in the queue, for whoever leads next
        with contextlib.suppress(Exception):
            _set(film, job, "queued", server=None)
        raise
    except Exception as e:  # noqa: BLE001 -- whatever went wrong, the film itself is untouched
        why = getattr(e, "text", None) or str(e) or type(e).__name__
        print("film %s: its branding stays: %s" % (fid, why), flush=True)
        job["state"] = "failed"
        _fail(film, why)
        await agent.save(fid, {"unbrand": {"state": "failed", "error": str(why)[:500]}}, final=True)
    finally:
        shutil.rmtree(film.path(*WORK), ignore_errors=True)
        with contextlib.suppress(OSError):
            os.remove(film.path(SIDE))


def side_manifest(film, fps):
    """sketch.clean.json: the film's manifest with no `tail`, at `fps`, its tools writing into
    temp/unbrand. Its path."""
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m.pop("tail", None)
    m["fps"] = fps
    m["work"] = "/".join(WORK)
    path = film.path(SIDE)
    films._write_json(path, m)
    return path


async def redraw(film, sched, fps, priority=0):
    """The film without its tail, made in temp/unbrand: sound, render, the link-preview card.
    The folder it is in (with audio/ and outputs/). Raises when a step fails or the result is
    not the film it should be."""
    side = film.path(*WORK)
    shutil.rmtree(side, ignore_errors=True)
    out = os.path.join(side, "outputs")
    os.makedirs(out, exist_ok=True)
    manifest = side_manifest(film, fps)
    # its captions are the narration's, which does not change: copied, so the new master keeps
    # its soft subtitle track (sketch-render muxes outputs/film.srt when it is there)
    for name in ("film.srt", "film.vtt"):
        with contextlib.suppress(OSError):
            shutil.copyfile(film.path("outputs", name), os.path.join(out, name))
    t = toolbox.Tools(film, sched, lambda ev: None)
    t.priority = priority
    mix = "audio/mix_pre.wav"
    kept = ["--from-mix", mix] if os.path.isfile(film.path(*mix.split("/"))) else []
    await t._script("sound", "sketch-audio.py", kept, pools=[("cpu", 1)], manifest=manifest)
    await t._script(
        "render",
        "sketch-render.py",
        ["--jobs", str(toolbox.RENDER_JOBS), "--encode", toolbox.RENDER_ENCODE],
        pools=[("browser", toolbox.RENDER_JOBS)],
        manifest=manifest,
    )
    with open(manifest, encoding="utf-8") as f:
        length = float(json.load(f).get("duration") or film.length)
    bad = await asyncio.to_thread(check, os.path.join(out, "film.mp4"), length, fps)
    if bad:
        raise UnbrandError(500, bad)
    with contextlib.suppress(Exception):  # no card is no reason to keep the branding
        await asyncio.to_thread(media.ensure_card, out, length)
    return side


def check(mp4, length, fps):
    """Is this the film, whole: its length (no closing) and its frame rate? What is wrong, or
    None."""
    if not os.path.isfile(mp4) or os.path.getsize(mp4) < 10_000:
        return "the render left no film"
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate:format=duration",
            "-of",
            "json",
            mp4,
        ],
        capture_output=True,
        text=True,
    )
    try:
        j = json.loads(r.stdout)
        dur = float(j["format"]["duration"])
        a, b = j["streams"][0]["r_frame_rate"].split("/")
        rate = float(a) / float(b)
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        return "the new film cannot be read"
    if abs(dur - length) > 0.15:
        return "the new film is %.2f s, not the film's %.2f s" % (dur, length)
    if abs(rate - fps) > 0.5:
        return "the new film is %.3g frames a second, not %d" % (rate, fps)
    return None


async def _sends_over(fid):
    """A YouTube send reads the master in pieces (youtube._send): the swap waits for one to end."""
    t0 = time.monotonic()
    while any(j["film"] == fid and j["state"] == "sending" for j in youtube.SENDS.values()):
        if time.monotonic() - t0 > SEND_WAIT_S:
            raise UnbrandError(409, "the film was still being sent to YouTube")
        await asyncio.sleep(2)


def commit(film, side, urls, rev, fps):
    """The new film takes the old one's place: its files, then its record. Returns what the
    record said before ({media, media_rev, fps}: the old film's copy online stays there)."""
    rec = film.record()
    before = {"media": rec.get("media"), "media_rev": rec.get("media_rev"), "fps": rec.get("fps")}
    for folder, name in SWAP:
        src = os.path.join(side, folder, name)
        if os.path.isfile(src):
            dst = film.path(folder, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
    fields = {"branding": False, "fps": fps}
    if urls:
        fields.update(media=urls, media_rev=rev)
    film.update(**fields)
    return before
