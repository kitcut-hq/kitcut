#!/usr/bin/env python
"""A finished film cut into a vertical Short (studio/shortcut.py, kitcut.ai's film_to_short): the
rules, the words on the Short's clock, the refusals through the API, and one real cut.

    python studio/test_shortcut.py

Covers: the seconds kept (in order, inside the film, at most 180 s, a result over it told to pass
segments); subtitles moved to the Short's clock across a join; a caption that is only a number kept;
a headline's braces never read as instructions; who may ask, and for which film (another's, not
finished, already vertical, too long); asking twice with one key is one film; and a real ffmpeg cut
of a small 16:9 film: 1080x1920, its length, its sound, the headline and captions on the picture,
done in both records, with what thumbnails need beside it.
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-shortcut-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import media  # noqa: E402
import shortcut  # noqa: E402
import store  # noqa: E402
from film import Film  # noqa: E402
from sched import Sched  # noqa: E402

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _thumb  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402

TOKEN = "test-token"
ALICE, BOB = "u:" + "a" * 24, "u:" + "b" * 24
VTT = """WEBVTT

00:00:00.500 --> 00:00:02.500
The first words of the film

00:00:03.000 --> 00:00:05.000
2026

00:00:07.000 --> 00:00:09.000
The words after the cut
"""
PASSED = []


def ok(cond, what):
    if not cond:
        raise AssertionError(what)
    PASSED.append(what)


def refused(reason, fn, *a):
    try:
        fn(*a)
    except shortcut.Refused as e:
        ok(e.reason == reason, "refused as %s (%s)" % (reason, e.error))
        return e
    raise AssertionError("not refused: %s" % reason)


def finished(client=ALICE, frame=None, seconds=10, size="1920x1080"):
    """A finished film with a real little master and its subtitles."""
    f = Film.create("How bees make honey", 10, "drawn", client=client)
    os.makedirs(f.path("outputs"), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i"]
        + ["testsrc2=size=%s:rate=30:duration=%d" % (size, seconds), "-f", "lavfi", "-i"]
        + ["sine=frequency=440:duration=%d" % seconds, "-c:v", "libx264", "-preset", "ultrafast"]
        + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", f.path("outputs", "film.mp4")],
        check=True,
    )
    with open(f.path("outputs", "film.vtt"), "w", encoding="utf-8") as o:
        o.write(VTT)
    f.update(state="done", title="How bees make honey", **({"frame": frame} if frame else {}))
    return f


def rules():
    ok(shortcut.parts_of(None, 40.0) == [(0.0, 40.0)], "no segments keeps the whole film")
    ok(
        shortcut.parts_of([{"start": 0, "end": 22}, {"start": 140, "end": 159}], 159.0)
        == [(0.0, 22.0), (140.0, 159.0)],
        "segments are kept as asked",
    )
    ok(shortcut.parts_of([{"start": 5, "end": 10.1}], 10.0) == [(5.0, 10.0)], "the end is the end")
    e = refused("long", shortcut.parts_of, None, 181.0)
    ok("Pass segments" in e.error and "180" in e.error, "a long result is told to pass segments")
    ok(e.status == 409, "too long is a refusal of the film, not a bad request")
    refused("long", shortcut.parts_of, [{"start": 0, "end": 100}, {"start": 110, "end": 200}], 300)
    ok(len(shortcut.parts_of([{"start": 0, "end": 180}], 300)) == 1, "exactly 180 s is a Short")
    two = [{"start": 10, "end": 20}, {"start": 5, "end": 8}]
    refused("segments", shortcut.parts_of, two, 60)
    refused("segments", shortcut.parts_of, [{"start": 0, "end": 70}], 60)
    refused("segments", shortcut.parts_of, [{"start": 3, "end": 3.1}], 60)
    refused("segments", shortcut.parts_of, [{"start": "0", "end": 3}], 60)
    refused("segments", shortcut.parts_of, [{"start": float("nan"), "end": 3}], 60)
    refused("segments", shortcut.parts_of, [{"start": i, "end": i + 1} for i in range(13)], 60)


def words():
    cues = shortcut.read_vtt(VTT)
    ok(len(cues) == 3 and cues[1][2] == "2026", "a caption that is only a number is kept")
    moved = shortcut.retime(cues, [(0.0, 4.0), (6.0, 10.0)])
    ok(moved[0] == (0.5, 2.5, "The first words of the film"), "the first part keeps its times")
    ok(moved[1] == (3.0, 4.0, "2026"), "a caption is cut where its part ends")
    ok(moved[2] == (5.0, 7.0, "The words after the cut"), "the next part follows the first")
    text = shortcut.ass("Bees {\\b1} win|Line two", moved, 8.0)
    ok("{\\b1}" not in text and "(/b1)" in text, "a headline's braces are not instructions")
    ok("win\\NLine two" in text, "| breaks the headline's line")
    ok(text.count("Cap,,") == 3, "every caption is on the picture")
    ok("Head,," not in shortcut.ass("", moved, 8.0), "no headline, no empty line")
    argv = shortcut.command("in.mp4", [(0.0, 4.0), (6.0, 10.0)], "out.mp4", 1)
    fc = argv[argv.index("-filter_complex") + 1]
    ok("concat=n=2:v=1:a=1" in fc and "boxblur=30:2" in fc, "two parts joined, over the blur")
    ok("scale=1080:-2" in fc and "crop=1080:1920" in fc, "the film whole, the blur cropped")


async def api():
    started = []
    real_start = server.start
    server.start = lambda f, finish_only=False, resume=None: started.append(f.id)
    agent.STORE = store.MemoryStore()
    client = TestClient(TestServer(server.make_app(TOKEN)))
    await client.start_server()

    async def ask(short, who=ALICE):
        h = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": who}
        return await client.post("/api/films", json={"short": short, "listed": False}, headers=h)

    try:
        src = finished()
        r = await ask({"from": src.id, "key": "k1", "segments": [{"start": 0, "end": 4}]}, BOB)
        ok(r.status == 404, "another person's film is not found")
        tall = finished(frame="9:16", size="1080x1920")
        r = await ask({"from": tall.id, "key": "k2"})
        ok(r.status == 409 and (await r.json())["reason"] == "frame", "a vertical film is refused")
        making = finished()
        making.update(state="claude")
        r = await ask({"from": making.id, "key": "k3"})
        ok(r.status == 409 and (await r.json())["reason"] == "state", "an unfinished film refused")
        r = await ask({"from": src.id, "key": "k4", "segments": [{"start": 0, "end": 40}]})
        ok(r.status == 400 and (await r.json())["reason"] == "segments", "past the film's end")
        ok(not started, "nothing was started for a refusal")
        want = {
            "from": src.id,
            "key": "k5",
            "headline": "Bees|make honey",
            "segments": [{"start": 0, "end": 4}, {"start": 6, "end": 10}],
        }
        r = await ask(want)
        body = await r.json()
        ok(r.status == 202 and started == [body["id"]], "the Short is started")
        f = Film.open(body["id"])
        rec = f.record()
        ok(rec["short_of"]["from"] == src.id and rec["length"] == 8, "its record says what it is")
        ok(rec["frame"] == "9:16" and rec["listed"] is False, "tall, and link-only")
        ok(not rec.get("project"), "never an episode: the next one must not start from it")
        again = await ask(want)
        ok((await again.json())["id"] == body["id"] and len(started) == 1, "one key is one film")
        return f
    finally:
        await client.close()
        server.start = real_start


async def real_cut(film):
    media.enabled = lambda: False
    told = []
    r = await shortcut.make(film, told.append, Sched(), {})
    ok(r["ok"], "the cut is done: %s" % r.get("error"))
    got = shortcut.probe(film.path("outputs", "film.mp4"))
    ok((got["w"], got["h"]) == (1080, 1920), "the Short is 1080x1920")
    ok(abs(got["duration"] - 8) < 0.2, "the Short is as long as the parts kept")
    ok(got["audio"], "the Short keeps the film's sound")
    ok(film.record()["state"] == "done", "the film's record says done")
    saved = agent.STORE.get(film.id)
    ok(saved["state"] == "done" and saved["frame"] == "9:16", "the database says done, and tall")
    ok(saved["short_of"]["key"] == "k5", "the site finds the Short by its key")
    for p in ("film.js", "outputs/film_poster.png", "images/f00.jpg", "audio/vo/timeline.json"):
        ok(os.path.exists(film.path(*p.split("/"))), "a finished film's %s is there" % p)
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    ok(m["frame"] == [1080, 1920] and m["duration"] == 8.0, "its manifest is the Short's")
    with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"]
    ok(lines[-1]["text"] == "The words after the cut", "its words are the film's own")
    # what its thumbnails are made from: the stand-in film.js, drawn by the real renderer
    still = _thumb.render_stills(film.dir, [2.0])[2.0]
    im = Image.open(still).convert("L")
    ok(im.size == (1080, 1920), "its stills are the Short's own frame")
    ok(im.getextrema()[1] - im.getextrema()[0] > 60, "its stills show the picture, not a blank")


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on this machine")
    rules()
    words()
    film = asyncio.run(api())
    asyncio.run(real_cut(film))
    shutil.rmtree(HOME, ignore_errors=True)
    print("test_shortcut: %d checks passed" % len(PASSED))


if __name__ == "__main__":
    main()
