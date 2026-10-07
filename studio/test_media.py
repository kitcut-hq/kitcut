#!/usr/bin/env python
"""media.py against a stand-in for Azure blob storage: no network, no cost, seconds.

    python studio/test_media.py

A finished film's files go up as Put Blob calls with the SAS, the type and the cache header; the
answer names their lasting URLs; a refused video means no copy at all (the film then plays from
the tunnel as before); delete removes them; and with no settings nothing is attempted.

The same against a stand-in for Cloudflare R2 (the three STUDIO_R2_ settings): signed S3 calls,
each signature worked out again here from the secret, and refused when it differs.
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
import store  # noqa: E402

agent.STORE = store.MemoryStore()  # never the real database: move_records writes to it

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestServer  # noqa: E402

SAS = "sv=2023-11-03&sr=c&sp=cwd&sig=test"
BLOBS = {}  # name -> (headers, body)
REFUSE = set()


async def put(req):
    name = req.match_info["name"]
    if req.query_string == "comp=properties&" + SAS:  # Set Blob Properties: all x-ms-blob-* anew
        if name not in BLOBS:
            return web.Response(status=404, text="BlobNotFound")
        h = {k: v for k, v in BLOBS[name][0].items() if not k.lower().startswith("x-ms-blob-")}
        h |= {k: v for k, v in req.headers.items() if k.lower().startswith("x-ms-blob-")}
        BLOBS[name] = (h, BLOBS[name][1])
        return web.Response(status=200)
    if req.query_string != SAS:
        return web.Response(status=403, text="AuthenticationFailed")
    if name.split("/")[-1] in REFUSE:
        return web.Response(status=500, text="InternalError")
    BLOBS[name] = (dict(req.headers), await req.read())
    return web.Response(status=201)


async def get(req):  # anonymous read, as the public container gives (HEAD too)
    h, body = BLOBS.get(req.match_info["name"], (None, b""))
    if h is None:
        return web.Response(status=404)
    out = {"Content-Type": h.get("x-ms-blob-content-type", "application/octet-stream")}
    for mine, theirs in (
        ("Cache-Control", "cache-control"),
        ("Content-Disposition", "content-disposition"),
    ):
        if h.get("x-ms-blob-" + theirs):
            out[mine] = h["x-ms-blob-" + theirs]
    return web.Response(body=body, headers=out)


async def delete(req):
    name = req.match_info["name"]
    if req.query_string != SAS:
        return web.Response(status=403)
    return web.Response(status=202 if BLOBS.pop(name, None) else 404)


R2_KEY, R2_SECRET = "r2keyid", "r2secret"
OBJECTS = {}  # key -> (headers, body)
UNSIGNED = []  # requests whose signature did not check out


def r2_signed(req):
    """The request's AWS Signature V4, worked out again from the secret (not media.py's code)."""
    import hmac
    import hashlib

    auth = req.headers.get("Authorization", "")
    try:
        cred, names, sig = (x.split("=", 1)[1] for x in auth.split(" ", 1)[1].split(", "))
    except (IndexError, ValueError):
        return False
    kid, day, region, service, _ = cred.split("/")
    names = names.split(";")
    amz = req.headers.get("x-amz-date", "")
    canon = "%s\n%s\n\n%s\n%s\nUNSIGNED-PAYLOAD" % (
        req.method,
        req.raw_path,
        "".join("%s:%s\n" % (n, req.headers[n].strip()) for n in names),
        ";".join(names),
    )
    text = "AWS4-HMAC-SHA256\n%s\n%s/auto/s3/aws4_request\n%s" % (
        amz,
        day,
        hashlib.sha256(canon.encode()).hexdigest(),
    )
    k = ("AWS4" + R2_SECRET).encode()
    for part in (day, "auto", "s3", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    ok = (
        kid == R2_KEY
        and (region, service) == ("auto", "s3")
        and amz.startswith(day)
        and "host" in names
        and all(n in names for n in req.headers if n.lower().startswith("x-amz-"))
        and hmac.new(k, text.encode(), hashlib.sha256).hexdigest() == sig
    )
    if not ok:
        UNSIGNED.append((req.method, req.raw_path))
    return ok


async def r2_put(req):
    name = req.match_info["name"]
    if not r2_signed(req):
        return web.Response(status=403, text="SignatureDoesNotMatch")
    if name.split("/")[-1] in REFUSE:
        return web.Response(status=500, text="InternalError")
    source = req.headers.get("x-amz-copy-source")
    if source:  # CopyObject onto itself, its headers replaced
        key = source[len("/bucket/films/") :]
        if key not in OBJECTS or req.headers.get("x-amz-metadata-directive") != "REPLACE":
            return web.Response(status=404, text="NoSuchKey")
        OBJECTS[name] = (dict(req.headers), OBJECTS[key][1])
        return web.Response(status=200)
    OBJECTS[name] = (dict(req.headers), await req.read())
    return web.Response(status=200)


async def r2_head(req):
    if not r2_signed(req):
        return web.Response(status=403)
    h, body = OBJECTS.get(req.match_info["name"], (None, b""))
    if h is None:
        return web.Response(status=404)
    return web.Response(status=200, headers={"Content-Length": str(len(body))})


async def r2_delete(req):
    if not r2_signed(req):
        return web.Response(status=403)
    OBJECTS.pop(req.match_info["name"], None)
    return web.Response(status=204)  # S3: the same answer whether it was there or not


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
    app.add_routes(
        [
            web.put("/bucket/films/{name:.+}", r2_put),
            web.head("/bucket/films/{name:.+}", r2_head),
            web.delete("/bucket/films/{name:.+}", r2_delete),
            web.put("/bucket/new/films/{name:.+}", r2_put),
            web.head("/bucket/new/films/{name:.+}", r2_head),
            web.get("/films/{name:.+}", get),
        ]
    )
    srv = TestServer(app, host="127.0.0.1")
    await srv.start_server()
    try:
        os.environ.pop("STUDIO_MEDIA_BASE", None)
        procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
        os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
        procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
        procs.SECRETS.pop("STUDIO_R2_SECRET", None)
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
        check(
            h.get("x-ms-blob-content-disposition")
            == 'attachment; filename="a-film-for-the-copy.mp4"'
            and "x-ms-blob-content-disposition"
            not in BLOBS.get("%s/film_web.mp4" % f.id, ({}, b""))[0],
            "the master is a download, named after the film; the web copy plays",
            h.get("x-ms-blob-content-disposition"),
        )
        f.update(title="Кіт і Café")
        check(
            media.download_name(f)
            == "attachment; filename=\"caf.mp4\"; filename*=UTF-8''%s.mp4"
            % media.quote("кіт-і-café", safe=""),
            "a title in any language: an ASCII name, and the whole one as filename*",
            media.download_name(f),
        )
        f.update(title=None)
        # a film copied before: its master is marked, and keeps its type and cache
        f.update(media=urls)
        BLOBS["%s/film.mp4" % f.id] = (
            {"x-ms-blob-content-type": "video/mp4", "x-ms-blob-cache-control": media.CACHE},
            body,
        )
        import aiohttp

        async with aiohttp.ClientSession() as s:
            await media.mark_download(s, f)
        mh = BLOBS["%s/film.mp4" % f.id][0]
        check(
            mh.get("x-ms-blob-content-disposition", "").startswith("attachment;")
            and mh.get("x-ms-blob-content-type") == "video/mp4"
            and mh.get("x-ms-blob-cache-control") == media.CACHE,
            "--download-backfill marks an old copy, keeping its type and cache",
            mh,
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

        # a film rendered again after a hand patch (resume.py --patched): new names, since the
        # old ones are cached as immutable; delete takes every revision
        await media.publish(f)
        f.update(media_rev=1)
        urls = await media.publish(f)
        check(
            urls.get("video") == base + "r1/film.mp4", "a patched film's copy has new names", urls
        )
        check("%s/r1/film_web.mp4" % f.id in BLOBS, "the web copy too", list(BLOBS))
        n = await media.delete(f.id)
        check(n == 10 and not BLOBS, "delete removes both revisions", (n, list(BLOBS)))

        # a film whose picture was replaced (ops.sh replace: media.py --revision bumps media_rev):
        # every file under new URLs, and a delete given its record's URLs finds them there
        await media.publish(f)
        f.update(media_rev=2)
        urls = await media.publish(f)
        check(
            all("/%s/r2/" % f.id in u for u in urls.values()) and len(urls) == 5,
            "a revision: every file under <id>/r2/",
            urls,
        )
        n = await media.delete(f.id, urls=urls.values())
        check(n == 10 and not BLOBS, "delete with the record's URLs removes both", (n, list(BLOBS)))

        # Cloudflare R2: the public address stays STUDIO_MEDIA_BASE, the files go to the
        # bucket's S3 address, signed; its three settings win over the SAS
        f.update(media_rev=None, media=None, title="Кіт і Café")
        os.environ["STUDIO_R2_ENDPOINT"] = "http://127.0.0.1:%d/bucket/" % srv.port
        procs.SECRETS["STUDIO_R2_KEY_ID"] = R2_KEY
        check(media.r2() is None and media.enabled(), "R2 needs all three settings")
        procs.SECRETS["STUDIO_R2_SECRET"] = R2_SECRET
        urls = await media.publish(f)
        check(
            len(urls) == 5 and urls.get("video") == base + "film.mp4" and not BLOBS,
            "R2: the same public URLs, and nothing goes to Azure",
            (urls, list(BLOBS)),
        )
        h, body = OBJECTS.get("%s/film.mp4" % f.id, ({}, b""))
        with open(os.path.join(out, "film.mp4"), "rb") as fh:
            same = body == fh.read()
        check(
            same
            and h.get("Content-Type") == "video/mp4"
            and h.get("Cache-Control") == media.CACHE
            and h.get("Content-Disposition") == media.download_name(f)
            and "Content-Disposition" not in OBJECTS.get("%s/film_web.mp4" % f.id, ({},))[0],
            "R2: the video whole, with its type, a lasting cache, and the master a download",
            h,
        )
        check(not UNSIGNED, "R2: every call's signature checks out", UNSIGNED)
        f.update(media=urls, title="Another name")
        async with aiohttp.ClientSession() as s:
            await media.mark_download(s, f)
        mh, mbody = OBJECTS["%s/film.mp4" % f.id]
        check(
            mh.get("Content-Disposition") == 'attachment; filename="another-name.mp4"'
            and mh.get("Content-Type") == "video/mp4"
            and mh.get("Cache-Control") == media.CACHE
            and mbody == body
            and not UNSIGNED,
            "R2: --download-backfill copies the master onto itself with the new name",
            mh,
        )
        REFUSE.add("film.mp4")
        check(await media.publish(f) == {}, "R2: a refused video: no copy at all")
        REFUSE.clear()
        procs.SECRETS["STUDIO_R2_SECRET"] = "wrong"
        check(
            await media.publish(f) == {} and UNSIGNED, "R2: a wrong secret: no copy, no exception"
        )
        procs.SECRETS["STUDIO_R2_SECRET"] = R2_SECRET
        UNSIGNED.clear()
        # moving house: what is in Azure copied to R2 under the same names, then the records
        procs.SECRETS.pop("STUDIO_R2_SECRET")
        await media.publish(f)  # to the stand-in for Azure
        procs.SECRETS["STUDIO_R2_SECRET"] = R2_SECRET
        old = "http://127.0.0.1:%d/films" % srv.port
        os.environ["STUDIO_MEDIA_BASE"] = "http://127.0.0.1:%d/new/films" % srv.port
        OBJECTS.clear()
        names = sorted(BLOBS) + ["%s/never.mp4" % f.id]
        got = await media.move_files(old, names, dry=True, say=lambda _: None)
        check(got[:3] == (5, 0, 1) and not OBJECTS, "move --dry-run: counts, copies nothing", got)
        got = await media.move_files(old, names, say=lambda _: None)
        vh, vbody = OBJECTS.get("%s/film.mp4" % f.id, ({}, b""))
        check(
            got[:3] == (5, 0, 1)
            and sorted(OBJECTS) == sorted(BLOBS)
            and vbody == BLOBS["%s/film.mp4" % f.id][1]
            and vh.get("Content-Type") == "video/mp4"
            and vh.get("Cache-Control") == media.CACHE
            and vh.get("Content-Disposition", "").startswith("attachment;")
            and not UNSIGNED,
            "move: every file copied whole with its type, cache and download name; one missing said",
            (got, vh),
        )
        got = await media.move_files(old, sorted(BLOBS), say=lambda _: None)
        check(got[:3] == (0, 5, 0), "move again: all already there", got)
        f.update(
            media={"video": old + "/%s/film.mp4" % f.id},
            share={"image": old + "/%s/share-1.jpg" % f.id, "v": "1"},
            versions=[{"n": 1, "media": {"web": old + "/%s/r1/film_web.mp4" % f.id}}],
            prompt="see %s/x" % old,
        )
        check(await media.move_records(old, dry=True) == 1, "records --dry-run: one to change")
        check(f.record()["media"]["video"].startswith(old), "and it is not changed")
        n = await media.move_records(old)
        rec, new = f.record(), os.environ["STUDIO_MEDIA_BASE"]
        check(
            n == 1
            and rec["media"]["video"] == new + "/%s/film.mp4" % f.id
            and rec["share"] == {"image": new + "/%s/share-1.jpg" % f.id, "v": "1"}
            and rec["versions"][0]["media"]["web"] == new + "/%s/r1/film_web.mp4" % f.id
            and rec["prompt"] == "see %s/x" % old
            and agent.STORE.get(f.id)["media"] == rec["media"],
            "records: every URL under the old base moved, here and in the database; words left",
            rec,
        )
        check(await media.move_records(old) == 0, "records again: nothing left to change")
        gone = "studio-20260101-000000-nofldr"  # its folder is gone: only the database has it
        agent.STORE.save(gone, {"media": {"video": old + "/%s/film.mp4" % gone}, "state": "done"})
        said = []
        check(
            await media.move_records(old, dry=True, say=said.append) == 1
            and gone in said[0]
            and agent.STORE.get(gone)["media"]["video"].startswith(old + "/"),
            "records --dry-run: one only the database has, named and not changed",
            said,
        )
        check(
            await media.move_records(old) == 1
            and agent.STORE.get(gone)["media"]["video"] == new + "/%s/film.mp4" % gone
            and agent.STORE.get(gone)["state"] == "done"
            and await media.move_records(old) == 0,
            "records: a film only the database has is moved there too",
            agent.STORE.get(gone),
        )
        agent.STORE.forget(gone)
        os.environ["STUDIO_MEDIA_BASE"] = old
        f.update(media=urls, share=None, versions=None, prompt="a film for the copy")
        OBJECTS.clear()
        BLOBS.clear()
        await media.publish(f)
        n = await media.delete(f.id)
        check(
            n == 5 and not OBJECTS and not UNSIGNED,
            "R2: delete removes them all",
            (n, list(OBJECTS)),
        )
        check(await media.delete(f.id) == 0, "R2: deleting again finds nothing, and says so")
        os.environ.pop("STUDIO_R2_ENDPOINT", None)
        procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
        procs.SECRETS.pop("STUDIO_R2_SECRET", None)
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
