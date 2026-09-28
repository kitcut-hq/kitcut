#!/usr/bin/env python
"""media.py against a stand-in for Azure blob storage: no network, no cost, seconds.

    python studio/test_media.py

A finished film's files go up as Put Blob calls with the SAS, the type and the cache header; the
answer names their lasting URLs; a refused video means no copy at all (the film then plays from
the tunnel as before); delete removes them; and with no settings nothing is attempted.
"""

import os
import sys
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-media-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402,F401 -- imports _env first
import film as films  # noqa: E402
import media  # noqa: E402
import procs  # noqa: E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestServer  # noqa: E402

SAS = "sv=2023-11-03&sr=c&sp=cwd&sig=test"
BLOBS = {}  # name -> (headers, body)
REFUSE = set()


async def put(req):
    name = req.match_info["name"]
    if req.query_string != SAS:
        return web.Response(status=403, text="AuthenticationFailed")
    if name.split("/")[-1] in REFUSE:
        return web.Response(status=500, text="InternalError")
    BLOBS[name] = (dict(req.headers), await req.read())
    return web.Response(status=201)


async def delete(req):
    name = req.match_info["name"]
    if req.query_string != SAS:
        return web.Response(status=403)
    return web.Response(status=202 if BLOBS.pop(name, None) else 404)


def master(path, srt=None, heavy=True):
    """A 2 s film.mp4: heavy (1080p60 noise, near-lossless mpeg4 -- far over the web cap) with
    sound and a soft subtitle track, as sketch-render makes them; or light (a small still)."""
    import subprocess

    size, rate = ("1920x1080", 60) if heavy else ("320x180", 30)
    src = "testsrc2=size=%s:rate=%d" % (size, rate) + (",noise=alls=12:allf=t" if heavy else "")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-f", "lavfi"]
    cmd += ["-i", "sine=frequency=440:sample_rate=48000"]
    cmd += ["-i", srt] if srt else []
    cmd += ["-map", "0:v", "-map", "1:a"] + (["-map", "2:s", "-c:s", "mov_text"] if srt else [])
    cmd += ["-t", "2", "-c:v", "mpeg4", "-q:v", "5" if heavy else "20", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", path]
    subprocess.run(cmd, check=True)


def probe_streams(path):
    import subprocess

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    return r.stdout.split()


def poster(path):
    from PIL import Image

    Image.new("RGB", (1920, 1080), (240, 230, 210)).save(path)


async def main():
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  %s" % (detail,)))
        if not ok:
            bad.append(what)

    app = web.Application(client_max_size=64 * 2**20)
    app.add_routes([web.put("/films/{name:.+}", put), web.delete("/films/{name:.+}", delete)])
    srv = TestServer(app, host="127.0.0.1")
    await srv.start_server()
    try:
        os.environ.pop("STUDIO_MEDIA_BASE", None)
        procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
        f = films.Film.create("a film for the copy", 5, "drawn", client="u:m")
        out = f.path("outputs")
        os.makedirs(out)
        poster(os.path.join(out, "film_poster.png"))
        with open(os.path.join(out, "film.vtt"), "w", encoding="utf-8") as fh:
            fh.write("WEBVTT\n\n00:00.000 --> 00:02.000\nHello\n")
        with open(os.path.join(out, "film.srt"), "w", encoding="utf-8") as fh:
            fh.write("1\n00:00:00,000 --> 00:00:02,000\nHello\n")
        master(os.path.join(out, "film.mp4"), os.path.join(out, "film.srt"), heavy=True)

        check(not media.enabled() and await media.publish(f) == {}, "no settings, nothing tried")

        os.environ["STUDIO_MEDIA_BASE"] = "http://127.0.0.1:%d/films/" % srv.port
        procs.SECRETS["STUDIO_MEDIA_SAS"] = "?" + SAS
        check(media.enabled(), "enabled with both settings")
        urls = await media.publish(f)
        base = "http://127.0.0.1:%d/films/%s/" % (srv.port, f.id)
        check(
            urls
            == {
                "web": base + "film_web.mp4",
                "video": base + "film.mp4",
                "poster": base + "film_poster.png",
                "card": base + "card.jpg",
                "subtitles": base + "film.vtt",
            },
            "the answer names each file's lasting URL",
            urls,
        )
        h, body = BLOBS.get("%s/film.mp4" % f.id, ({}, b""))
        with open(os.path.join(out, "film.mp4"), "rb") as fh:
            same = body == fh.read()
        check(same, "the video arrives whole", len(body))
        check(
            h.get("x-ms-blob-type") == "BlockBlob"
            and h.get("x-ms-blob-content-type") == "video/mp4"
            and "immutable" in h.get("x-ms-blob-cache-control", ""),
            "as a block blob, with its type and a lasting cache",
            h,
        )
        ch, card = BLOBS.get("%s/card.jpg" % f.id, ({}, b""))
        check(
            card[:3] == b"\xff\xd8\xff" and ch.get("x-ms-blob-content-type") == "image/jpeg",
            "the link-preview card is made and sent",
        )
        check(
            BLOBS.get("%s/film.vtt" % f.id, ({}, b""))[0].get("x-ms-blob-content-type")
            == "text/vtt",
            "the subtitles too",
        )
        web_path = os.path.join(out, "film_web.mp4")
        m_size, w_size = os.path.getsize(os.path.join(out, "film.mp4")), os.path.getsize(web_path)
        check(
            BLOBS.get("%s/film_web.mp4" % f.id, ({}, b""))[1] == open(web_path, "rb").read()
            and w_size < m_size / 2,
            "the web copy is made, much lighter, and sent (%d KB from %d KB)"
            % (w_size // 1024, m_size // 1024),
        )
        kinds = probe_streams(web_path)
        check(
            kinds == ["video", "audio", "subtitle"] and abs(media._duration(web_path) - 2) < 0.2,
            "it keeps the sound and the soft subtitles, and the length",
            kinds,
        )
        light = films.Film.create("a light one", 5, "drawn", client="u:m")
        os.makedirs(light.path("outputs"))
        lp = light.path("outputs", "film.mp4")
        master(lp, None, heavy=False)
        media.make_web(light)
        with open(lp, "rb") as a, open(light.path("outputs", "film_web.mp4"), "rb") as b:
            check(a.read() == b.read(), "a master already light enough is copied as it is")

        REFUSE.add("film.mp4")
        BLOBS.clear()
        check(await media.publish(f) == {}, "a refused video: no copy at all")
        REFUSE.clear()
        procs.SECRETS["STUDIO_MEDIA_SAS"] = "sv=wrong"
        check(await media.publish(f) == {}, "a wrong SAS: no copy, no exception")
        procs.SECRETS["STUDIO_MEDIA_SAS"] = SAS

        await media.publish(f)
        n = await media.delete(f.id)
        check(n == 5 and not BLOBS, "delete removes them all", (n, list(BLOBS)))
        check(await media.delete(f.id) == 0, "deleting again finds nothing, and says so")
    finally:
        await srv.close()
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
