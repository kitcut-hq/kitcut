#!/usr/bin/env python
"""Looking at and listening to a finished film's versions (studio/look.py; kitcut.ai's
get_film_frames and get_film_audio): small real films made by ffmpeg, in a throwaway STUDIO_HOME.
No model and no network. A few seconds.

    python studio/test_look.py

Covers: the moments a sheet shows (a count spread end to end, one every n seconds, capped, never
past the film's end, a backwards range refused); which video a version is (the film's own files,
a kept version's, a version only online read from its copy there) and its narration lines; a
contact sheet of the right shape with each time stamped on it; one frame at full size; the sound's
loudness a window (a tone loud, silence at the floor) with the lines said in each; and the routes:
another person's film not found, an unfinished film refused, a bad number a 400, a version that
is not there a 404, the headers saying what a sheet shows.
"""

import os
import io
import sys
import json
import asyncio
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-look-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import look  # noqa: E402
from film import Film  # noqa: E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402

TOKEN = "test-token"
ALICE, BOB = "u:" + "a" * 24, "u:" + "b" * 24
PASSED = []
LINES = [
    {"i": 0, "text": "A tone to start.", "start": 0.5, "end": 2.5},
    {"i": 1, "text": "Then nothing at all.", "start": 5.0, "end": 6.0},
]


def ok(cond, what):
    if not cond:
        raise AssertionError(what)
    PASSED.append(what)


def video(path, color, seconds=8):
    """A little film: a flat colour, a tone for its first half and silence after."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    half = seconds // 2
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i"]
        + ["color=c=%s:s=640x360:r=30:d=%d" % (color, seconds), "-f", "lavfi", "-i"]
        + ["sine=frequency=440:duration=%d,apad=whole_dur=%d" % (half, seconds)]
        + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac"]
        + ["-t", str(seconds), path],
        check=True,
    )


def finished(client=ALICE):
    """A finished film at version 2 (blue), its version 1 (red) kept beside it."""
    f = Film.create("A tone and a colour", 8, "drawn", client=client)
    video(f.path("outputs", "film.mp4"), "blue")
    os.makedirs(f.path("audio", "vo"), exist_ok=True)
    with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as o:
        json.dump({"lines": LINES}, o)
    video(f.path("versions", "v1", "outputs", "film.mp4"), "red")
    vs = [
        {"n": 1, "video_s": 8.0, "lines": LINES[:1], "media": {}, "kept": True},
        {"n": 2, "video_s": 8.0, "lines": LINES, "media": {}, "kept": True},
    ]
    f.update(state="done", ok=True, version=2, versions=vs)
    return f


def rules():
    ts, step = look.times(10, count=5)
    ok(
        len(ts) == 5 and ts[0] == 0.0 and ts[-1] == 9.95 and step > 2.4,
        "a count is spread from end to end",
    )
    ts, step = look.times(10, 2, 4, every=0.5)
    ok(ts == [2.0, 2.5, 3.0, 3.5, 4.0] and step == 0.5, "one every half second from 2 s to 4 s")
    ts, step = look.times(600, every=1)
    ok(len(ts) <= look.MAX_FRAMES and step > 1, "a step giving too many frames is widened")
    ts, _ = look.times(10, count=500)
    ok(len(ts) == look.MAX_FRAMES, "a count is capped")
    ts, _ = look.times(10, 3, 3)
    ok(ts == [3.0], "a range of one moment is one frame")
    ok(max(look.times(10, 0, 50, count=3)[0]) < 10, "never past the film's end")
    try:
        look.times(10, 6, 2)
        raise AssertionError("a backwards range was taken")
    except look.LookError as e:
        ok(e.status == 400, "a backwards range is refused")


def versions(f):
    v = look.version(f)
    ok(
        v["n"] == 2 and v["current"] and v["src"].endswith(os.path.join("outputs", "film.mp4")),
        "the film's own version is its own files",
    )
    ok(
        [x["i"] for x in v["lines"]] == [0, 1] and v["versions"] == [1, 2],
        "its lines, its versions",
    )
    v1 = look.version(f, 1)
    ok("v1" in v1["src"] and not v1["current"], "a kept version is read from its kept files")
    try:
        look.version(f, 7)
        raise AssertionError("version 7 was found")
    except look.LookError as e:
        ok(e.status == 404 and "1, 2" in e.text, "a version not there says which there are")
    return v, v1


def frames(v, v1):
    ts, _ = look.times(v["duration"], count=6)
    data, got = look.sheet(v, ts)
    im = Image.open(io.BytesIO(data))
    ok(im.format == "JPEG" and im.width <= look.SHEET_W and got == ts, "a sheet of six frames")
    ok(im.height < im.width, "six frames in three columns, two rows")
    px = im.convert("RGB")
    ok(px.getpixel((3, 3)) == (0, 0, 0), "each frame has its time on a dark box")
    tile = (look.SHEET_W - 2 * 6) // 3
    r, g, b = px.getpixel((tile // 2, im.height // 4 + 20))
    ok(b > 150 and r < 80, "the current version's frames are its own (blue)")
    data, got = look.sheet(v1, [1.0], "png")
    r, g, b = Image.open(io.BytesIO(data)).convert("RGB").getpixel((400, 300))
    ok(r > 150 and b < 80, "version 1's frames are its own (red)")
    data, t = look.still(v, 3.0)
    ok(Image.open(io.BytesIO(data)).size == (640, 360) and t == 3.0, "one frame at its full size")


def sound(v):
    got = look.levels(v, 0, 8, 2)
    w = got["windows"]
    ok(len(w) == 4 and got["audio"] and got["window"] == 2.0, "four windows of two seconds")
    ok(w[0]["mean_db"] > -30 and w[0]["peak_db"] > -20, "the tone is loud")
    ok(w[3]["mean_db"] <= -80, "the silence is at the floor")
    ok(w[0]["lines"] == [0] and w[1]["lines"] == [0] and w[2]["lines"] == [1], "lines by window")
    ok(w[3]["lines"] == [], "no line in the last window")
    got = look.levels(v, 5, 8, 0.1)
    ok(
        got["window"] == look.MIN_WINDOW and [x["i"] for x in got["lines"]] == [1],
        "a window too short is widened; only the range's lines",
    )


async def online(f):
    """A version not kept on this disk, played from its copy online (here a local server)."""
    folder = tempfile.mkdtemp(prefix="online-", dir=HOME)
    video(os.path.join(folder, "web.mp4"), "green")
    app = web.Application()
    app.router.add_static("/", folder)
    srv = TestServer(app, host="127.0.0.1")
    await srv.start_server()
    try:
        rec = f.record()
        vs = rec["versions"] + [
            {
                "n": 3,
                "video_s": 8.0,
                "lines": LINES,
                "kept": False,
                "media": {"web": str(srv.make_url("/web.mp4"))},
            }
        ]
        f.update(versions=vs)
        v3 = await asyncio.to_thread(look.version, f, 3)
        ok(v3["src"].startswith("http://127.0.0.1:"), "a version only online is read from there")
        data, _ = await asyncio.to_thread(look.still, v3, 2.0)
        r, g, b = Image.open(io.BytesIO(data)).convert("RGB").getpixel((100, 100))
        ok(g > 80 and r < 60, "its frame is sought in the copy online")
        got = await asyncio.to_thread(look.levels, v3, 0, 4, 2)
        ok(got["windows"][0]["mean_db"] > -30, "its sound is read from the copy online")
    finally:
        await srv.close()
        f.update(versions=f.record()["versions"][:2])


async def api(f):
    client = TestClient(TestServer(server.make_app(TOKEN)))
    await client.start_server()

    def get(path, who=ALICE):
        return client.get(
            path, headers={"Authorization": "Bearer " + TOKEN, "X-Client-Ip": who, "Cf-Ray": "t"}
        )

    try:
        r = await get("/api/films/%s/frames?count=4" % f.id, BOB)
        ok(r.status == 404, "another person's film is not found")
        r = await get("/api/films/%s/frames?from=1&to=5&count=4" % f.id)
        ok(r.status == 200 and r.headers["Content-Type"] == "image/jpeg", "a sheet comes back")
        ok(r.headers["X-Version"] == "2" and r.headers["X-Current"] == "1", "of the film's version")
        ok(
            r.headers["X-Times"] == "1,2.33,3.67,5" and r.headers["X-Versions"] == "1,2",
            "the headers say its times and the versions",
        )
        r = await get("/api/films/%s/frames?version=1&at=2&format=png" % f.id)
        ok(r.status == 200 and r.headers["Content-Type"] == "image/png", "a full frame as PNG")
        ok(Image.open(io.BytesIO(await r.read())).size == (640, 360), "at its full size")
        r = await get("/api/films/%s/frames?version=9" % f.id)
        ok(r.status == 404 and (await r.json())["reason"] == "version", "no version 9")
        r = await get("/api/films/%s/frames?every=abc" % f.id)
        ok(r.status == 400 and "every" in (await r.json())["error"], "a bad number is a 400")
        r = await get("/api/films/%s/audio?from=0&to=8&window=4" % f.id)
        body = await r.json()
        ok(r.status == 200 and len(body["windows"]) == 2 and body["version"] == 2, "the sound")
        ok(body["lines"][0]["text"] == "A tone to start.", "with the lines said")
        making = finished()
        making.update(state="claude")
        r = await get("/api/films/%s/audio" % making.id)
        ok(r.status == 409, "a film being made is not looked at yet")
    finally:
        await client.close()


def main():
    rules()
    f = finished()
    v, v1 = versions(f)
    frames(v, v1)
    sound(v)
    asyncio.run(online(f))
    asyncio.run(api(f))
    print("ok: %d checks" % len(PASSED))


if __name__ == "__main__":
    main()
