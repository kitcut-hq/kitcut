#!/usr/bin/env python
"""A finished film sent to YouTube (youtube.py), end to end through the API, against a stand-in
for YouTube's resumable upload endpoint: no Google, no network, no cost, seconds.

    python studio/test_youtube.py

Covers: only the film's owner may send it, and only a finished one; only to YouTube's upload
endpoint; the bytes arrive whole and in order; a piece YouTube half-received and answered 503 is
resumed from where YouTube says it stopped; asking twice with one key sends once; a send cut off
by a restart carries on from what the session already has; an expired session is a plain failure;
and a send is invisible to anyone but its owner. Everything happens in a throwaway STUDIO_HOME.
"""

import os
import re
import sys
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-youtube-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402
import youtube  # noqa: E402
from film import Film  # noqa: E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"


class FakeYouTube:
    """YouTube's resumable upload protocol, as far as a sender can see it: 308 with the Range
    kept so far, 201 with the video once the last byte is in, 404 for a session it never made."""

    def __init__(self):
        self.got = {}  # upload_id -> bytearray
        self.size = {}
        self.puts = 0
        self.flaky = set()  # upload ids whose next piece is half-kept and answered 503

    async def put(self, req):
        self.puts += 1
        uid = req.query.get("upload_id", "")
        if uid.startswith("gone"):
            return web.json_response({"error": {"message": "Not found"}}, status=404)
        got = self.got.setdefault(uid, bytearray())
        rng = req.headers.get("Content-Range", "")
        body = await req.read()
        m = re.match(r"bytes (\d+)-(\d+)/(\d+)$", rng)
        if m:
            a, _, size = map(int, m.groups())
            self.size[uid] = size
            if a != len(got):
                return self.where(uid)
            if uid in self.flaky:
                self.flaky.discard(uid)
                got.extend(body[: len(body) // 2])
                return web.Response(status=503)
            got.extend(body)
        else:
            self.size[uid] = int(rng.rsplit("/", 1)[1])
        return self.where(uid)

    def where(self, uid):
        got = self.got[uid]
        if len(got) == self.size.get(uid):
            st = {"privacyStatus": "public", "uploadStatus": "uploaded"}
            return web.json_response({"id": "vid-" + uid, "status": st}, status=201)
        head = {"Range": "bytes=0-%d" % (len(got) - 1)} if got else {}
        return web.Response(status=308, headers=head)


async def main():
    agent.STORE = store.MemoryStore()
    youtube.CHUNK = 256 * 1024
    youtube.PAUSE = lambda tries: 0.05
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    yt = FakeYouTube()
    fake = web.Application()
    fake.router.add_put("/upload/youtube/v3/videos", yt.put)
    async with TestServer(fake) as gs, TestClient(TestServer(server.make_app(TOKEN))) as c:
        youtube.HOSTS = (str(gs.make_url("/upload/youtube/v3/videos")) + "?",)
        session = lambda uid: youtube.HOSTS[0] + "uploadType=resumable&upload_id=" + uid  # noqa: E731
        # as the public site reaches it: through the tunnel, not from this machine (which may
        # do anything)
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:alice", "Cf-Ray": "t"}
        other = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:bob", "Cf-Ray": "t"}

        f = Film.create("A paper plane", 10, client="u:alice")
        os.makedirs(f.path("outputs"), exist_ok=True)
        movie = os.urandom(700 * 1024 + 123)  # three whole pieces and a short last one
        with open(f.path("outputs", "film.mp4"), "wb") as fh:
            fh.write(movie)

        async def send(uid, key, who=me, to=None):
            r = await c.post(
                "/api/films/%s/youtube" % f.id,
                json={"to": to or session(uid), "key": key},
                headers=who,
            )
            return r.status, await r.json()

        async def until_done(key, who=me):
            for _ in range(200):
                r = await c.get("/api/films/%s/youtube/%s" % (f.id, key), headers=who)
                j = await r.json()
                if r.status != 200 or j.get("state") != "sending":
                    return r.status, j
                await asyncio.sleep(0.02)
            return r.status, j

        st, j = await send("u1", "post-00000001")
        check(st == 409, "an unfinished film is not sent", j)
        f.update(ok=True, state="done")

        st, j = await send("u1", "post-00000001", who=other)
        check(st == 403, "only its owner may send it", j)
        st, j = await send("u1", "post-00000001", to="https://evil.example/upload?upload_id=x")
        check(st == 400, "only to YouTube's upload endpoint", j)
        st, j = await send("u1", "no")
        check(st == 400, "a send needs a proper key", j)

        yt.flaky.add("u1")
        st, j = await send("u1", "post-00000001")
        check(st == 202 and j["state"] == "sending" and j["size"] == len(movie), "sending", j)
        st, j = await until_done("post-00000001")
        check(
            j.get("state") == "done" and j["video"]["id"] == "vid-u1" and j["sent"] == len(movie),
            "sent, and YouTube's answer kept",
            j,
        )
        check(bytes(yt.got["u1"]) == movie, "every byte arrived, in order, after a 503 mid-piece")
        check(j["video"]["privacy"] == "public", "the privacy YouTube gave it is reported", j)

        puts = yt.puts
        st, j = await send("u1", "post-00000001")
        check(st == 202 and j["state"] == "done" and yt.puts == puts, "asked twice, sent once", j)

        r = await c.get("/api/films/%s/youtube/post-00000001" % f.id, headers=other)
        check(r.status == 404, "no one else can see a send")

        # a send cut off by a restart: the session already holds 300 KB of the film
        yt.got["u2"] = bytearray(movie[: 300 * 1024])
        yt.size["u2"] = len(movie)
        puts = yt.puts
        st, j = await send("u2", "post-00000002")
        st, j = await until_done("post-00000002")
        check(
            j.get("state") == "done" and bytes(yt.got["u2"]) == movie,
            "a cut-off send carries on from what YouTube has",
            j,
        )
        check(yt.puts - puts == 1 + 2, "and sends only the rest", yt.puts - puts)

        st, j = await send("gone1", "post-00000003")
        st, j = await until_done("post-00000003")
        check(
            j.get("state") == "failed" and "expired" in j.get("error", ""),
            "an expired session fails plainly",
            j,
        )
        st, j = await send("u3", "post-00000003")
        st, j = await until_done("post-00000003")
        check(j.get("state") == "done", "a failed send can be tried again", j)

    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
