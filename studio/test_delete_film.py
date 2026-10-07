#!/usr/bin/env python
"""delete_film.py against a stand-in for Azure blob storage and a record store in memory: no
network, no cost, seconds.

    python studio/test_delete_film.py

A deleted film is gone everywhere -- its copy online (every revision, every version, the share
pictures), its record and its rounds', its place in its library and its project's episode log,
its sessions, a round's copy, its backups, its folder -- and the film beside it is untouched. A
plan removes nothing. A film being made, changed, drawn again or sent is refused. Storage that
refuses leaves the film whole; a database that cannot be reached leaves its folder, and asking
again finishes. The endpoint answers its own client and this machine, and nobody else.
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-delete-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import delete_film  # noqa: E402
import film as films  # noqa: E402
import library  # noqa: E402
import media  # noqa: E402
import procs  # noqa: E402
import rounds  # noqa: E402
import store  # noqa: E402
import unbrand  # noqa: E402
import youtube  # noqa: E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

SAS = "sv=2023-11-03&sr=c&sp=cwd&sig=test"
TOKEN = "test-token"
BLOBS = set()
REFUSE = set()  # blob names the stand-in will not delete
PROJECT = {"id": "p-abcdefghij", "name": "Duchess", "brief": "A deadpan cat."}
ALICE, BOB = "u:" + "a" * 24, "u:" + "b" * 24


async def blob_delete(req):
    name = req.match_info["name"]
    if req.query_string != SAS:
        return web.Response(status=403, text="AuthenticationFailed")
    if name.rsplit("/", 1)[-1] in REFUSE:
        return web.Response(status=403, text="AuthorizationFailure")
    if name not in BLOBS:
        return web.Response(status=404, text="BlobNotFound")
    BLOBS.discard(name)
    return web.Response(status=202)


def touch(p, body="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def episode(title, base, mem):
    """A finished episode as a round and a replace would have left it: two revisions online, an
    earlier version's files, share pictures, a place in its library, and things beside its folder."""
    f = films.Film.create(title, 5, "drawn", client=ALICE, project=PROJECT)
    u = lambda name: "%s/%s/%s" % (base, f.id, name)  # noqa: E731
    names = [n for _, n, _ in media.FILES]
    mine = names + ["r1/" + n for n in names] + ["strip.jpg", "r1/strip.jpg", "share-abc123.jpg"]
    BLOBS.update("%s/%s" % (f.id, n) for n in mine)
    f.update(
        state="done",
        ok=True,
        title=title,
        media_rev=1,
        media={"video": u("r1/film.mp4"), "web": u("r1/film_web.mp4")},
        versions=[
            {"n": 1, "media": {"video": u("film.mp4"), "strip": u("strip.jpg")}},
            {"n": 2, "media": {"video": u("r1/film.mp4"), "strip": u("r1/strip.jpg")}},
        ],
        share={"image": u("share-abc123.jpg")},
        round={"id": f.id + ".r1", "state": "done"},
    )
    touch(f.path("outputs", "film.mp4"))
    touch(f.path("versions", "v1", "outputs", "film.mp4"))
    mem.save(f.id, {"kind": "film", "state": "done"}, final=True)
    mem.save(f.id + ".r1", {"kind": "round", "state": "done"}, final=True)
    lib = library.lib_of(f.record())
    library.put_canon(lib, {"film": f.id, "made": title, "title": title})
    with library._lock(lib):
        idx = library.load(lib)
        idx["films"] = [f.id] + idx["films"]
        idx["cast"].setdefault("duchess", {"version": 1, "films": []})["films"].insert(0, f.id)
        library._save(lib, idx)
    touch(os.path.join(library.dir_of(lib), "films", f.id + ".jpg"))
    touch(os.path.join(f.claude_dir, "session.jsonl"))
    touch(os.path.join(films.HOME, "claude", f.id + ".r1", "session.jsonl"))
    touch(os.path.join(rounds.ROOT, f.id + ".r1", "film.js"))
    touch(os.path.join(delete_film.BACKUPS, f.id + "-20261005-120000.tar.gz"))
    return f


def beside(f):
    """Is everything of this film still where it was?"""
    lib = library.lib_of(f.record())
    idx = library.load(lib)
    return all(
        (
            os.path.isfile(f.path("studio.json")),
            os.path.isfile(f.path("versions", "v1", "outputs", "film.mp4")),
            "%s/film.mp4" % f.id in BLOBS and "%s/r1/strip.jpg" % f.id in BLOBS,
            f.id in idx["films"] and f.id in idx["cast"]["duchess"]["films"],
            any(e["film"] == f.id for e in library.canon_of(lib)),
            os.path.isfile(os.path.join(library.dir_of(lib), "films", f.id + ".jpg")),
            os.path.isdir(f.claude_dir),
            os.path.isdir(os.path.join(rounds.ROOT, f.id + ".r1")),
            os.path.isfile(os.path.join(delete_film.BACKUPS, f.id + "-20261005-120000.tar.gz")),
        )
    )


class Offline:
    """A record store whose database cannot be reached."""

    def forget(self, run_id):
        raise RuntimeError("no primary")


class Col:
    """As much of a pymongo collection as MongoStore.forget asks of one."""

    def __init__(self, ids):
        self.ids = set(ids)

    def delete_many(self, q):
        import re

        pat = re.compile(q["_id"]["$regex"])
        gone = {i for i in self.ids if pat.search(i)}
        self.ids -= gone
        return type("R", (), {"deleted_count": len(gone)})()


async def main():
    bad = []

    def check(ok, what, got=None):
        print(
            "%s  %s" % ("ok  " if ok else "FAIL", what)
            + ("" if ok or got is None else "  %r" % (got,))
        )
        if not ok:
            bad.append(what)

    app = web.Application()
    app.router.add_delete("/films/{name:.+}", blob_delete)
    srv = TestServer(app)
    await srv.start_server()
    base = "http://127.0.0.1:%d/films" % srv.port
    os.environ["STUDIO_MEDIA_BASE"] = base
    procs.SECRETS["STUDIO_MEDIA_SAS"] = SAS
    os.environ.pop("STUDIO_R2_ENDPOINT", None)  # the stand-in is Azure's, whatever the .env says
    os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
    procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
    procs.SECRETS.pop("STUDIO_R2_SECRET", None)
    agent.STORE = mem = store.MemoryStore()
    try:
        a = episode("One", base, mem)
        await asyncio.sleep(1.1)  # a film's id is its second
        b = episode("Two", base, mem)
        check(a.id != b.id and beside(a) and beside(b), "two finished episodes, each whole")

        # ---- a plan says what would go and removes nothing
        p = delete_film.plan(a)
        check(
            p["online"] == 6
            and p["versions"] == 2
            and len(p["sides"]) == 5
            and p["library"] == {"index": True, "cast": ["duchess"], "canon": True},
            "a plan names the copy online, the versions, the sides and the library",
            p,
        )
        check(beside(a) and mem.get(a.id) is not None, "and removes nothing")

        # ---- refused while something is being done with the film
        for change, reason, undo in (
            (lambda: a.update(state="claude"), "making", lambda: a.update(state="done")),
            (lambda: a.update(state="waiting"), "making", lambda: a.update(state="done")),
            (
                lambda: a.update(round={"id": a.id + ".r2", "state": "running"}),
                "round",
                lambda: a.update(round={"id": a.id + ".r1", "state": "done"}),
            ),
            (
                lambda: touch(os.path.join(unbrand.MARKS, a.id + ".json")),
                "unbrand",
                lambda: os.remove(os.path.join(unbrand.MARKS, a.id + ".json")),
            ),
            (
                lambda: youtube.SENDS.update(k={"film": a.id, "state": "sending"}),
                "youtube",
                lambda: youtube.SENDS.clear(),
            ),
        ):
            change()
            try:
                await delete_film.delete(a)
                got = None
            except delete_film.DeleteError as e:
                got = (e.status, e.reason)
            undo()
            check(got == (409, reason) and beside(a), "refused, the film whole: %s" % reason, got)

        # ---- storage that refuses: nothing else is touched
        REFUSE.add("card.jpg")
        try:
            await delete_film.delete(a)
            got = None
        except delete_film.DeleteError as e:
            got = (e.status, e.reason)
        REFUSE.clear()
        check(
            got == (502, "storage")
            and os.path.isfile(a.path("studio.json"))
            and mem.get(a.id) is not None
            and os.path.isdir(a.claude_dir),
            "storage that refuses a file: the record, the folder and the sides stay",
            got,
        )

        # ---- a database that cannot be reached: the folder stays, and asking again finishes
        try:
            await delete_film.delete(a, store=Offline())
            got = None
        except delete_film.DeleteError as e:
            got = (e.status, e.reason)
        check(
            got == (503, "record") and films.Film.open(a.id) is not None,
            "a database that cannot be reached: the film is still there to ask again",
            got,
        )
        gone = await delete_film.delete(a)
        check(gone["records"] == 2 and not gone["left"], "asked again, it finishes", gone)

        # ---- gone everywhere, and the film beside it untouched
        lib = library.lib_of(b.record())
        idx = library.load(lib)
        check(films.Film.open(a.id) is None and not os.path.exists(a.dir), "the folder is gone")
        check(
            not [x for x in BLOBS if x.startswith(a.id + "/")], "its copy online, all of it", BLOBS
        )
        check(mem.get(a.id) is None and mem.get(a.id + ".r1") is None, "its record and its round's")
        check(
            a.id not in idx["films"]
            and a.id not in idx["cast"]["duchess"]["films"]
            and "duchess" in idx["cast"],
            "its library forgets it, and keeps the cast member",
            idx,
        )
        check(
            [e["film"] for e in library.canon_of(lib)] == [b.id],
            "its project's episode log too",
        )
        check(
            not os.path.exists(a.claude_dir)
            and not os.path.exists(os.path.join(films.HOME, "claude", a.id + ".r1"))
            and not os.path.exists(os.path.join(rounds.ROOT, a.id + ".r1"))
            and not os.path.exists(os.path.join(library.dir_of(lib), "films", a.id + ".jpg"))
            and not os.listdir(delete_film.BACKUPS)[1:],
            "its sessions, its round's copy, its cached poster and its backup",
        )
        check(
            not os.listdir(delete_film.TRASH),
            "nothing is left in tmp/",
            os.listdir(delete_film.TRASH),
        )
        check(
            beside(b) and mem.get(b.id) and mem.get(b.id + ".r1"), "the other episode is untouched"
        )

        # ---- the outbox: a record waiting there would come back with the next sync
        box = os.path.join(HOME, "outbox.jsonl")
        with open(box, "w", encoding="utf-8") as f:
            for i in (a.id, a.id + ".r1", b.id):
                f.write(json.dumps({"_id": i, "state": "done"}) + "\n")
        ms = store.MongoStore(uri="mongodb://unused", outbox=box)
        ms._col = Col([a.id, a.id + ".r1", a.id + ".r12", b.id, a.id + "x"])
        n = ms.forget(a.id)
        with open(box, encoding="utf-8") as f:
            left = [json.loads(x)["_id"] for x in f]
        check(
            n == 3 and ms._col.ids == {b.id, a.id + "x"} and left == [b.id],
            "the store forgets the film and its rounds, in the database and the outbox, only",
            (n, ms._col.ids, left),
        )

        # ---- the endpoint
        async with TestClient(TestServer(server.make_app(TOKEN))) as c:
            auth = {"Authorization": "Bearer " + TOKEN}
            stranger = auth | {"Cf-Ray": "1", "X-Client-Ip": BOB}
            owner = auth | {"Cf-Ray": "1", "X-Client-Ip": ALICE}
            url = "/api/films/%s/delete" % b.id
            check((await c.post(url, json={})).status == 401, "the endpoint needs the token")
            r = await c.post(url, json={}, headers=stranger)
            check(r.status == 403 and beside(b), "another client is refused", r.status)
            r = await c.post(url, json={"plan": True}, headers=owner)
            d = await r.json()
            check(
                r.status == 200 and d["online"] == 6 and d["refused"] is None and beside(b),
                "its own client's plan: what would go, nothing removed",
                d,
            )
            b.update(state="finishing")
            r = await c.post(url, json={}, headers=owner)
            d = await r.json()
            check(
                r.status == 409 and d["reason"] == "making" and beside(b), "refused while made", d
            )
            b.update(state="done")
            r = await c.post(url, json={}, headers=owner)
            d = await r.json()
            check(
                r.status == 200
                and d["deleted"]
                and films.Film.open(b.id) is None
                and not BLOBS
                and mem.get(b.id) is None,
                "its own client deletes it",
                d,
            )
            r = await c.post(url, json={}, headers=owner)
            check(r.status == 404, "asked again: there is no such film", r.status)
            r = await c.get("/api/films/%s" % b.id, headers=owner)
            check(r.status == 404, "and its status says so too", r.status)
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
