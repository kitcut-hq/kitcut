#!/usr/bin/env python
"""Pictures, voice notes and documents attached to a film request (uploads.py), end to end through the API,
with the speech-to-text stubbed and no film made: no API calls, no cost, seconds.

    python studio/test_uploads.py

Covers: an upload's kind read off its bytes (never its name), a picture measured, a voice note
written out in the background, only its uploader seeing it, a film asked for with pictures and no
words, the files landing in the film's inputs/ and its manifest, the brief Claude gets, an
unknown or foreign id refused, a silent note refused, a picture the film does not draw dropped
before the render, and a day-old upload deleted. Everything happens in a throwaway STUDIO_HOME.
"""

import os
import io
import sys
import json
import time
import shutil
import asyncio
import subprocess
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-uploads-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402
import uploads  # noqa: E402
from film import Film  # noqa: E402

import _stt  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402

TOKEN = "test-token"
HEARD = {"text": "Make a warm film about my bakery, Sunny Crumbs."}


def fake_transcribe(path, engine, hints=(), env=None, timeout=90, gate=True):
    time.sleep(0.2)
    return {"text": HEARD["text"], "lang": "en", "seconds": 0.2, "cost_usd": 0.0, "engine": engine}


def png(w, h, alpha=False):
    b = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (w, h), (200, 120, 60, 0 if alpha else 255)).save(
        b, "PNG"
    )
    return b.getvalue()


def webm(secs):
    out = os.path.join(HOME, "note-%s.webm" % secs)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=%s" % secs,
        ]
        + ["-c:a", "libopus", "-b:a", "32k", out],
        check=True,
    )
    with open(out, "rb") as f:
        return f.read()


async def main():
    agent.STORE = store.MemoryStore()
    server.start = lambda f, finish_only=False: None  # the film itself is test_server.py's job
    _stt.transcribe = fake_transcribe
    uploads.STT = ("stub:model",)
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:alice"}
        other = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:bob"}

        async def up(data, who=me, ctype="image/png"):
            r = await c.post("/api/uploads", data=data, headers={**who, "Content-Type": ctype})
            return r.status, await r.json()

        check(
            (await c.post("/api/uploads", data=png(8, 8))).status == 401,
            "an upload needs the token",
        )
        st, pic = await up(png(1600, 900))
        check(st == 201 and pic["kind"] == "image" and pic["w"] == 1600, "a picture, measured", pic)
        st, logo = await up(png(400, 200, alpha=True))
        check(st == 201 and logo["state"] == "ready", "a see-through logo", logo)
        st, j = await up(b"<html><script>alert(1)</script></html>", ctype="image/png")
        check(st == 415 and j["reason"] == "type", "a page called a picture is refused", j)
        st, j = await up(png(8, 8)[:40])
        check(st == 400 and j["reason"] == "unreadable", "a broken picture is refused", j)
        st, note = await up(webm(2), ctype="audio/webm")
        check(
            st == 201 and note["state"] == "transcribing" and note["secs"] >= 1.9,
            "a voice note",
            note,
        )
        await asyncio.sleep(0.6)
        r = await c.get("/api/uploads/" + note["id"], headers=me)
        got = await r.json()
        check(
            got.get("state") == "ready" and "Sunny Crumbs" in got.get("transcript", ""),
            "written out",
            got,
        )
        r = await c.get("/api/uploads/" + note["id"], headers=other)
        check(r.status == 404, "another account cannot see it")
        r = await c.get("/api/uploads/../../studio.json", headers=me)
        check(r.status == 404, "an id cannot name a path")
        mine = (await (await c.get("/api/uploads", headers=me)).json())["uploads"]
        check(
            [m["id"] for m in mine] == [note["id"], logo["id"], pic["id"]]
            and all(0 < m["expires_in"] <= 86400 for m in mine)
            and mine[0].get("transcript"),
            "the list: newest first, with the time left and a note's words",
            mine,
        )
        theirs = (await (await c.get("/api/uploads", headers=other)).json())["uploads"]
        check(theirs == [], "another account's list is its own (empty)", theirs)

        # a film from a picture and a voice note, nothing typed
        body = {"prompt": "", "seconds": 10, "attachments": [pic["id"], note["id"], logo["id"]]}
        r = await c.post("/api/films", json=body, headers=other)
        j = await r.json()
        check(r.status == 409 and j.get("reason") == "attachment", "someone else's uploads", j)
        r = await c.post("/api/films", json={"prompt": "", "seconds": 10}, headers=me)
        check(r.status == 400, "no words and nothing attached is refused")
        r = await c.post("/api/films", json=body, headers=me)
        j = await r.json()
        check(
            r.status == 202 and j.get("attachments") == ["image", "audio", "image"],
            "a film from them",
            j,
        )
        f = Film.open(j.get("id"))
        rec = f.record() if f else {}
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        check(
            m.get("images") == {"upload1": "inputs/upload1.png", "upload2": "inputs/upload2.png"},
            "pictures in the manifest by name",
            m.get("images"),
        )
        check(
            all(
                os.path.exists(f.path("inputs", n))
                for n in ("upload1.png", "upload2.png", "voice1.webm")
            ),
            "files in inputs/",
            os.listdir(f.path("inputs")) if os.path.isdir(f.path("inputs")) else None,
        )
        check(f.readable(f.path("inputs", "upload1.png")), "Claude may read them")
        check(not f.writable(f.path("inputs", "upload1.png")), "and may not change them")
        voice = [a for a in rec.get("attachments", []) if a["kind"] == "audio"]
        check(
            voice and "Sunny Crumbs" in voice[0]["transcript"],
            "the words in the record",
            rec.get("attachments"),
        )
        brief = agent.ask(f)
        check(
            "Sunny Crumbs" in brief and "SK.image('upload1'" in brief,
            "the brief names both",
            brief[-600:],
        )
        check(
            "name_film" in brief and "nothing typed" in brief, "and asks for a title", brief[-300:]
        )
        first = agent.first_record(f, "web", "u:alice")
        check(
            "transcript" not in json.dumps(first),
            "the run record keeps no words",
            first.get("attachments"),
        )
        r = await c.get("/api/uploads/" + pic["id"], headers=me)
        check(r.status == 404, "a film's upload leaves the upload shelf")
        mine = (await (await c.get("/api/uploads", headers=me)).json())["uploads"]
        check(mine == [], "and the list", mine)

        # a typed film is not asked for a title
        st, p2 = await up(png(300, 300))
        r = await c.post(
            "/api/films",
            json={"prompt": "Our new logo", "seconds": 10, "attachments": [p2["id"]]},
            headers=me,
        )
        f2 = Film.open((await r.json()).get("id"))
        check("name_film" not in agent.ask(f2), "a typed film needs no title")

        # a voice note with no words cannot make a film
        HEARD["text"] = ""
        st, silent = await up(webm(1.5), ctype="audio/webm")
        await asyncio.sleep(0.6)
        r = await c.post(
            "/api/films",
            json={"prompt": "", "seconds": 10, "attachments": [silent["id"]]},
            headers=me,
        )
        j = await r.json()
        check(r.status == 422 and j.get("reason") == "silent", "a silent note is refused", j)

        # the picture film.js does not draw is dropped before the render
        with open(f.path("film.js"), "w", encoding="utf-8") as fh:
            fh.write("SK.image('upload1', 960, 540, 800);")
        gone = agent.drop_unused_uploads(f)
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        check(
            gone == ["upload2"] and list(m["images"]) == ["upload1"],
            "an undrawn picture is dropped",
            gone,
        )

        # the name_film tool
        from tools import Tools

        t = Tools(f, server.SCHED, lambda ev: None)
        said = await t.name_film("  The   Bakery at Dawn ")
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        check(
            f.record().get("title") == "The Bakery at Dawn" and m["title"] == "The Bakery at Dawn",
            "named",
            said,
        )

        # documents: a .txt or .md, read off its bytes as text
        brief_md = "# Sunny Crumbs\r\n\r\nOpen 7am. Sourdough is **$6**.\r\n"
        r = await c.post(
            "/api/uploads?name=C:%5Cfakepath%5Cbrief.md",
            data=brief_md.encode(),
            headers={**me, "Content-Type": "text/markdown"},
        )
        md = await r.json()
        check(
            r.status == 201 and md["kind"] == "text" and md["name"] == "brief.md",
            "a markdown brief, its name cleaned",
            md,
        )
        r = await c.post(
            "/api/uploads",
            data="Сценарій: пекарня".encode("utf-16"),
            headers={**me, "Content-Type": "text/plain"},
        )
        u16 = await r.json()
        check(r.status == 201 and u16["kind"] == "text", "a UTF-16 text file (Notepad)", u16)
        st, j = await up(b"\x00\x01\x02binary\x00", ctype="text/plain")
        check(st == 415 and j["reason"] == "type", "binary called text is refused", j)
        st, j = await up(b"caf\xe9 latin-1 " * 3, ctype="text/plain")
        check(st == 415 and j["reason"] == "type", "a text file not in UTF-8 is refused", j)
        st, j = await up(b" \n\t\n ", ctype="text/plain")
        check(st == 400 and j["reason"] == "empty", "a blank text file is refused", j)
        st, j = await up(b"word " * (uploads.MAX_TEXT_CHARS // 5 + 10), ctype="text/plain")
        check(st == 413 and j["reason"] == "long", "a book is refused", j)
        st, big = await up(("A long script. " * 600).encode(), ctype="text/plain")
        body = {"prompt": "", "seconds": 10, "attachments": [md["id"], u16["id"], big["id"]]}
        r = await c.post("/api/films", json=body, headers=me)
        j = await r.json()
        check(r.status == 202 and j.get("attachments") == ["text"] * 3, "a film from documents", j)
        f3 = Film.open(j.get("id"))
        with open(f3.path("inputs", "doc1.md"), encoding="utf-8") as fh:
            kept = fh.read()
        check(
            kept == brief_md.replace("\r\n", "\n").strip() + "\n"
            and os.path.exists(f3.path("inputs", "doc2.txt")),
            "documents in inputs/, as plain UTF-8",
            os.listdir(f3.path("inputs")),
        )
        check(f3.readable(f3.path("inputs", "doc3.txt")), "Claude may read them")
        brief = agent.ask(f3)
        check(
            'Document 1 "brief.md"' in brief
            and "Sourdough is **$6**" in brief
            and "Сценарій" in brief
            and "Read inputs/doc3.txt" in brief
            and "A long script" not in brief
            and "name_film" in brief,
            "the brief quotes the short ones and names the long one",
            brief[-1500:],
        )
        first = agent.first_record(f3, "web", "u:alice")
        check(
            "Sourdough" not in json.dumps(first) and first["attachments"][0].get("chars"),
            "the run record keeps no words",
            first.get("attachments"),
        )
        ids = [
            (await up(b"note %d" % i, ctype="text/plain"))[1]["id"]
            for i in range(uploads.MAX_DOCS + 1)
        ]
        r = await c.post(
            "/api/films", json={"prompt": "x" * 10, "seconds": 10, "attachments": ids}, headers=me
        )
        check(r.status == 400, "too many documents for one film")

        # a day later, what no film took is gone
        st, stale = await up(png(50, 50))
        meta = uploads._meta_path("u:alice", stale["id"])
        old = time.time() - uploads.KEEP_S - 60
        os.utime(meta, (old, old))
        check(
            uploads.prune() >= 1 and uploads.get("u:alice", stale["id"]) is None,
            "a day-old upload is deleted",
        )

    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
