#!/usr/bin/env python
"""What two studio servers share on one home, across real processes: python studio/test_shared.py

During a ship the new release runs beside the old one on one STUDIO_HOME (peers.py; a ship that
restarted the studio killed a paying film: docs/known-issues.md KI-031). Each file both may write
is checked here with real processes racing through it (a child is this file run with --child):

    a film's record    two processes updating one studio.json, 100 fields each: all 200 there
    the cost outbox    two processes appending 100 rows each while a sync sends and rewrites the
                       file: every row sent once or still waiting, none lost, none doubled
    a library          two processes keeping 10 films each into one person's library: versions
                       1..20 with none written twice, and every film in the index
    a voice note       one server writing a note out, another taking it into a film: the taker
                       waits for the live one, and writes it out itself when that one is dead

No network, no renders, a few seconds; a throwaway STUDIO_HOME, removed at the end.
--nolock runs the children with the file locks switched off, to see the checks fail without them.
"""

import os
import sys
import json
import time
import shutil
import asyncio
import tempfile
import contextlib
import subprocess

if "--child" not in sys.argv:
    os.environ["STUDIO_HOME"] = tempfile.mkdtemp(prefix="studio-shared-")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import film  # noqa: E402 -- film.HOME is read from STUDIO_HOME as it is imported
import locks  # noqa: E402
import library  # noqa: E402
import peers  # noqa: E402
import store  # noqa: E402
import uploads  # noqa: E402
from film import Film  # noqa: E402

HERE = os.path.abspath(__file__)
N = 100  # record fields and outbox rows, per process
FILMS = 10  # films kept into the library, per process (two: within library.LISTED)
CLIENT = "u:alice"


# ---------------------------------------------------------------- the children
def child(what, args):
    if os.environ.get("TEST_SHARED_NOLOCK"):  # --nolock: what the code would do without locks
        locks.locked = lambda *a, **k: contextlib.nullcontext()
        Film._temp = lambda self: False
    go, args = args[0], args[1:]
    out = None
    if what == "update":  # N fields of one film's record, named <prefix><i>
        f, prefix = Film(args[0]), args[1]
        ready(go)
        for i in range(N):
            f.update(**{"%s%d" % (prefix, i): i})
    elif what == "append":  # N final saves that cannot reach the database: the outbox

        class Down(store.MongoStore):
            def col(self):
                raise RuntimeError("MongoDB is unreachable (the test)")

        s, prefix = Down(uri="mongodb://unreachable", outbox=args[0]), args[1]
        ready(go)
        # save() says where each row went: not into the pipe, which nobody reads until the end
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet):
            for i in range(N):
                s.save("%s-%d" % (prefix, i), {"state": "done", "cost_usd": i}, final=True)
    elif what == "keep":  # FILMS films, each changing the same cast member
        films = [
            Film.create("%s %d" % (args[0], i), 5, "drawn", client=CLIENT) for i in range(FILMS)
        ]
        ready(go)
        out = []
        for f in films:
            code = "SK.cast.pip = { about: 'Pip, as film %s drew him', draw() {} };\n" % f.id
            items = [{"name": "pip", "code": code, "hash": library._hash(code), "about": ""}]
            out.append([f.id, library.keep(f, items)["saved"]])
    elif what == "stt":  # a server writing a voice note out: done after args[1] s (0: never)
        peers.hold_own()
        uid, after = args[0], float(args[1])
        path = uploads._meta_path(CLIENT, uid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        meta = {"id": uid, "kind": "audio", "ext": "webm", "created": time.time()}
        meta.update(state="transcribing", server=peers.SERVER_ID, stt_started=time.time())
        uploads._write(path, meta)
        ready(go)
        if not after:
            while True:
                time.sleep(1)
        time.sleep(after)
        meta.update(state="ready", transcript="written out by the other server")
        uploads._write(path, meta)
    print(json.dumps(out), flush=True)


def ready(go):
    """Tell the parent this child is set up, then wait for every child to be told to go: the
    point is that they run at the same moment."""
    print("ready", flush=True)
    if go != "-":
        while not os.path.exists(go):
            time.sleep(0.002)


def spawn(what, *args, nolock=False):
    env = dict(os.environ)
    if nolock:
        env["TEST_SHARED_NOLOCK"] = "1"
    p = subprocess.Popen(
        [sys.executable, HERE, "--child", what, *map(str, args)],
        env=env,
        stdout=subprocess.PIPE,
        text=True,
    )
    line = p.stdout.readline().strip()
    if line != "ready":
        raise RuntimeError("child %s did not start: %r" % (what, line))
    return p


def race(what, runs, nolock=False):
    """Start a child per run, let them go together; returns the processes (still running)."""
    go = os.path.join(film.HOME, "go-%s-%d" % (what, time.monotonic_ns()))
    ps = [spawn(what, go, *args, nolock=nolock) for args in runs]
    open(go, "w").close()
    return ps


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def result(p):
    out, _ = p.communicate(timeout=120)
    if p.returncode:
        raise RuntimeError("a child failed (exit %d)" % p.returncode)
    return json.loads(out.strip().splitlines()[-1])


# ---------------------------------------------------------------- the checks
def main(nolock):
    bad = []

    def expect(what, ok):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    # a film's record: the owner's writes and another server's, into one studio.json
    f = Film.create("a record two servers write", 5, "drawn", client=CLIENT)
    t0 = time.monotonic()
    for p in race("update", [(f.dir, "a"), (f.dir, "b")], nolock):
        result(p)
    rec = f.record()
    got = [k for k in rec if k[:1] in "ab" and k[1:].isdigit()]
    expect(
        "two processes, %d updates each to one record: every field kept (%d, %.1f s)"
        % (N, len(got), time.monotonic() - t0),
        len(got) == 2 * N and rec.get("state") == "queued" and rec.get("id") == f.id,
    )

    # the outbox: two servers appending while a sync sends and rewrites it
    class Col:  # the database, for sync: it takes every row but those it refuses
        sent = []

        def update_one(self, q, update, upsert=False):
            if q["_id"].endswith("7"):
                raise RuntimeError("refused (the test)")
            self.sent.append(q["_id"])

    outbox = os.path.join(film.HOME, "outbox.jsonl")
    s = store.MongoStore(uri="mongodb://unused", outbox=outbox)
    s._col = Col()
    ps = race("append", [(outbox, "a"), (outbox, "b")], nolock)
    syncs = 0
    while any(p.poll() is None for p in ps):
        s.sync()
        syncs += 1
        time.sleep(0.005)
    for p in ps:
        result(p)
    s.sync()
    rows = [json.loads(x) for x in s._rows()]
    ids = ["%s-%d" % (x, i) for x in "ab" for i in range(N)]
    want_sent = sorted(i for i in ids if not i.endswith("7"))
    left = sorted(r["_id"] for r in rows)
    expect(
        "every row appended while %d syncs ran was sent, once (%d of %d)"
        % (syncs, len(Col.sent), len(want_sent)),
        sorted(Col.sent) == want_sent,
    )
    expect(
        "the rows the database refused are still waiting, once each (%d)" % len(left),
        left == sorted(i for i in ids if i.endswith("7")),
    )

    # a library: two servers keeping films into one person's library at once
    ps = race("keep", [("alice a",), ("alice b",)], nolock)
    kept = [x for p in ps for x in result(p)]
    idx = library.load(CLIENT)
    pip = idx["cast"].get("pip") or {}
    d = os.path.join(library.dir_of(CLIENT), "cast", "pip")
    on_disk = sorted(int(n[1:-3]) for n in os.listdir(d) if n.endswith(".js"))
    drawn_by = {read(os.path.join(d, "v%d.js" % v)).split("as film ")[-1][:30] for v in on_disk}
    expect(
        "two processes, %d films each: a version per film (%s)" % (FILMS, pip.get("version")),
        all(saved == ["pip"] for _, saved in kept) and pip.get("version") == 2 * FILMS,
    )
    expect(
        "the last %d versions on disk, each from a different film (%s)" % (library.KEEP, on_disk),
        on_disk == list(range(2 * FILMS - library.KEEP + 1, 2 * FILMS + 1))
        and len(drawn_by) == library.KEEP,
    )
    expect(
        "the index names the latest, and every film",
        library._hash(read(os.path.join(d, "v%d.js" % pip.get("version", 0)))) == pip.get("hash")
        and sorted(idx["films"]) == sorted(fid for fid, _ in kept),
    )

    if not nolock:
        voice_notes(expect)
    print("%d failed" % len(bad))
    return 1 if bad else 0


def voice_notes(expect):
    """A voice note one server is writing out, taken into a film on the other."""
    here = []

    def transcribe(path, engine, hints=(), env=None, timeout=90, gate=True):
        here.append(path)
        time.sleep(0.3)
        return {"text": "written out here", "lang": "en", "seconds": 0.3, "engine": engine}

    uploads._stt.transcribe = transcribe
    uploads.STT = ("stub:model",)

    async def take(uid):
        t0 = time.monotonic()
        try:
            meta = (await uploads.take(CLIENT, [uid]))[0]
        except uploads.UploadError as e:
            meta = {"error": e.reason}
        return meta, time.monotonic() - t0

    # the other server is alive and at it: wait for it, write nothing out here
    p = race("stt", [("up-aaaaaaaaaaaa", 1.5)])[0]
    meta, waited = asyncio.run(take("up-aaaaaaaaaaaa"))
    result(p)
    expect(
        "a note another live server is writing out is waited for (%.1f s), not written out twice"
        % waited,
        meta.get("transcript") == "written out by the other server" and not here and waited > 1,
    )

    # the server writing it out died: write it out here, at once
    p = race("stt", [("up-bbbbbbbbbbbb", 0)])[0]
    p.kill()
    p.wait()

    async def dead():
        t = asyncio.create_task(take("up-bbbbbbbbbbbb"))
        await asyncio.sleep(0.1)
        busy = uploads.in_flight()
        meta, waited = await t
        return meta, waited, busy, uploads.in_flight()

    meta, waited, busy, after = asyncio.run(dead())
    expect(
        "a note whose server died is written out here (%.1f s)" % waited,
        meta.get("transcript") == "written out here" and len(here) == 1,
    )
    expect(
        "in_flight names it while it is being written out, and not after",
        busy == ["up-bbbbbbbbbbbb"] and after == [],
    )
    expect(
        "and the meta names this server as the one that wrote it out",
        uploads.get(CLIENT, "up-bbbbbbbbbbbb").get("server") == peers.SERVER_ID,
    )

    # a note from a release before servers were named: waited for while fresh, then taken over
    path = uploads._meta_path(CLIENT, "up-cccccccccccc")
    meta = {"id": "up-cccccccccccc", "kind": "audio", "ext": "webm", "state": "transcribing"}
    uploads._write(path, meta | {"created": time.time()})
    uploads.WAIT_S = 1.5
    got, waited = asyncio.run(take("up-cccccccccccc"))
    expect(
        "an unnamed fresh note is waited for, and a take that runs out says so",
        got.get("error") == "voice" and len(here) == 1,
    )
    uploads._write(path, meta | {"created": time.time() - uploads.FRESH_S - 1})
    got, waited = asyncio.run(take("up-cccccccccccc"))
    expect(
        "an unnamed stale one is written out here",
        got.get("transcript") == "written out here" and len(here) == 2,
    )


if __name__ == "__main__":
    if "--child" in sys.argv:
        i = sys.argv.index("--child")
        child(sys.argv[i + 1], sys.argv[i + 2 :])
        sys.exit(0)
    try:
        code = main("--nolock" in sys.argv)
    finally:
        shutil.rmtree(os.environ["STUDIO_HOME"], ignore_errors=True)
    sys.exit(code)
