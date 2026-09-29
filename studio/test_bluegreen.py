#!/usr/bin/env python
"""Two studio servers handing over, end to end, with Claude stubbed out: no API calls, no cost.

    python studio/test_bluegreen.py

What a ship does on the VM (one kitcut-studio@<instance> per release, peers.py), on a throwaway
STUDIO_HOME: an "old" server runs as a child process (this file with --child), a "new" one in
this process. Windows has no SO_REUSEPORT, so each listens on a port of its own and is called
directly. The old one leads and is making a slow film with another waiting behind it for its one
Claude slot; `current` then names the new one, which starts. Checked: the old one hands over
within seconds and stops listening, and the new one leads; the waiting film goes back to the
queue and the new one makes it; the old film's page, answered by the new server, shows it running
with the old server's events and is never "lost"; its person is still refused a second film; a
Stop pressed through the new server reaches the old one (and someone else's is refused); the old
server exits by itself once its film is over, its files gone. And adoption: of the films whose
server is dead, a queued one is made, one left being finished is finished without Claude, one
Claude was writing is marked interrupted, one stopped meanwhile is recorded cancelled, one from
before records named their server waits out LEGACY_GRACE_S -- and one a live server is making is
left to it. Last, a YouTube send or draft another server has in flight is not started again. A
minute or two, most of it rendering.
"""

import os
import sys
import json
import time
import shutil
import socket
import asyncio
import tempfile
import subprocess

CHILD = "--child" in sys.argv
if not CHILD:
    os.environ["STUDIO_HOME"] = tempfile.mkdtemp(prefix="studio-bluegreen-")
    os.environ["STUDIO_INSTANCE"] = "new"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import film as films  # noqa: E402
import peers  # noqa: E402
import store  # noqa: E402
import youtube  # noqa: E402
import ytdraft  # noqa: E402

import aiohttp  # noqa: E402

# no copy online: a checkout with the studio's .env would upload the stub films (test_server.py)
os.environ.pop("STUDIO_MEDIA_BASE", None)
server.procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)

HERE = os.path.abspath(__file__)
TOKEN = "test-token"
AUTH = {"Authorization": "Bearer " + TOKEN}
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}
EXAMPLE = os.path.join(films.KIT, "config", "sketch", "example")
CALLED = []  # the films this process's stub was asked to write


async def fake_claude(
    film, emit, meter, tools, auth="api", prompt=None, resume=None, budget_usd=None
):
    """Claude's part, stubbed: the example film's files, a known token count; a "slow" film then
    keeps its Claude slot until it is stopped."""
    CALLED.append(film.id)
    for f in films.MADE:
        shutil.copy(os.path.join(EXAMPLE, f), film.dir)
    meter.add("msg_" + film.id, USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    if "slow" in film.record().get("prompt", ""):
        emit({"type": "say", "text": "Drawing it slowly."})
        await asyncio.sleep(600)


def child(port):
    """The old server: the same stub for Claude, its own memory for the run records, and one
    Claude slot (STUDIO_PARALLEL=1, from its environment), so a second film waits."""
    agent.STORE = store.MemoryStore()
    agent.run_claude = fake_claude
    server.ADOPT_S = 3600  # the films the test leaves for adoption are the new server's
    sys.exit(asyncio.run(server.serve(port, TOKEN)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            return True
    except OSError:
        return False


async def until(fn, limit, every=0.2):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        v = fn()
        if v:
            return v
        await asyncio.sleep(every)
    return None


def old_beat():
    return next((b for b in peers.peers() if b.get("instance") == "old"), None)


def lines(film):
    """A film's events as on disk (a line its server is half-way through writing is left out)."""
    out = []
    try:
        with open(film.path("events.jsonl"), encoding="utf-8") as f:
            for x in f:
                try:
                    out.append(json.loads(x))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def exited(p, limit):
    try:
        return p.wait(limit)
    except subprocess.TimeoutExpired:
        return None


def left(ex, prompt, client, **fields):
    """A film on disk as a server left it."""
    f = films.Film.create(prompt, 5, "drawn", client=client)
    if fields.get("state") == "finishing":
        for name in films.MADE:
            shutil.copy(os.path.join(ex, name), f.dir)
    f.update(**fields)
    return f


async def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what), flush=True)
        if not ok:
            bad.append(what)

    agent.STORE = mem = store.MemoryStore()
    agent.run_claude = fake_claude
    server.LEGACY_GRACE_S = 8
    p_old, p_new = free_port(), free_port()
    log = open(os.path.join(films.HOME, "old-server.log"), "w", encoding="utf-8")
    env = dict(os.environ, STUDIO_INSTANCE="old", STUDIO_PARALLEL="1")
    old = subprocess.Popen(
        [sys.executable, "-u", HERE, "--child", str(p_old)],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    new_task = None
    old_url, new_url = "http://127.0.0.1:%d" % p_old, "http://127.0.0.1:%d" % p_new
    tunnel = {"Cf-Ray": "test"}  # as the public site's requests come (this machine may do anything)
    try:
        async with aiohttp.ClientSession() as http:

            async def call(base, method, path, headers=None, **kw):
                h = AUTH | (headers or {})
                async with http.request(method, base + path, headers=h, **kw) as r:
                    return r.status, await r.json(content_type=None)

            # ------------------------------------------------ the old server leads, and is busy
            b = await until(lambda: (old_beat() or {}).get("leader") and old_beat(), 120)
            check(bool(b) and b["mode"] == "serving", "the old server serves and leads")
            if not b:
                return 1
            old_sid = b["id"]
            st, j = await call(
                old_url,
                "POST",
                "/api/films",
                json={"prompt": "slow, on the old server", "seconds": 5},
                headers={"X-Client-Ip": "u:bg"},
            )
            slow = films.Film.open(j.get("id"))
            st2, j2 = await call(
                old_url,
                "POST",
                "/api/films",
                json={"prompt": "waiting behind it", "seconds": 5},
                headers={"X-Client-Ip": "u:bg2"},
            )
            waiting = films.Film.open(j2.get("id"))
            check(
                st == 202 and st2 == 202 and j2.get("status") == "queued",
                "the old server takes a slow film, and one waits behind it for its Claude slot",
            )
            if slow is None or waiting is None:
                return 1
            await until(lambda: any(e.get("type") == "say" for e in lines(slow)), 60)
            check(
                slow.state == "claude" and slow.record().get("server") == old_sid,
                "the slow film's record names the old server as its maker",
            )

            # what dead servers left, for whoever leads next (the old one adopted already)
            gone = "gone-release.4242"
            g_q = left(EXAMPLE, "left queued by a dead server", "u:g1", server=gone)
            g_fin = left(EXAMPLE, "left mid-render", "u:g2", state="finishing", server=gone)
            g_fin.update(claude_cost_usd=0.25)
            g_mid = left(EXAMPLE, "left while Claude wrote", "u:g3", state="claude", server=gone)
            with open(g_mid.path("events.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "tool", "text": "edited film.js", "t": 7.0}) + "\n")
            g_stop = left(EXAMPLE, "stopped while nobody made it", "u:g4", server=gone)
            peers.request_cancel(g_stop.id, by="u:g4")
            legacy = left(EXAMPLE, "left from before owners", "u:g5", state="claude")
            rec = legacy.record()
            rec.pop("server", None)
            films._write_json(legacy.path("studio.json"), rec)

            # ------------------------------------------------ the new release goes current
            seen = {}  # film id -> every status the new server answered for it

            async def poll():
                while True:
                    for f in (slow, waiting):
                        try:
                            s, got = await call(new_url, "GET", "/api/films/%s" % f.id)
                        except aiohttp.ClientError:
                            continue  # not listening yet
                        if s == 200:
                            seen.setdefault(f.id, []).append(got.get("status"))
                    await asyncio.sleep(0.3)

            poller = asyncio.create_task(poll())
            # a connection the tunnel holds open to the old server (keep-alive), idle
            held = aiohttp.ClientSession()
            async with held.get(old_url + "/api/health") as r0:
                await r0.read()
            peers.set_current("new")
            t0 = time.monotonic()
            new_task = asyncio.create_task(server.serve(p_new, TOKEN))
            b = await until(
                lambda: (old_beat() or {}).get("mode") == "handed_off" and old_beat(), 15
            )
            handed = time.monotonic() - t0
            check(
                bool(b) and not b["leader"] and handed < 5,
                "the old server hands over within seconds (%.1f s)" % handed,
            )
            led = await until(lambda: peers.leads() and server.LEADER.is_set(), 15)
            check(bool(led), "and the new one leads (%.1f s)" % (time.monotonic() - t0))
            check(
                not await asyncio.to_thread(listening, p_old),
                "the old server no longer listens: new connections reach the new one",
            )

            # its next request on that held connection is answered, and the connection closed
            # after the reply -- not cut from this side with a request possibly on it
            try:
                async with held.get(old_url + "/api/health") as r1:
                    body = await r1.json()
                    check(
                        r1.status == 200
                        and body.get("server", "").startswith("old.")
                        and r1.headers.get("Connection", "").lower() == "close",
                        "a request on a connection held to the old server is answered, "
                        "and the connection told to close",
                    )
            except aiohttp.ClientError as e:
                check(False, "a request on a held connection to the old server failed: %r" % e)
            await held.close()

            # ------------------------------------------------ what the new leader adopted
            check(
                waiting.id in server.JOBS and waiting.record().get("server") == peers.SERVER_ID,
                "the film that was waiting for the old server's slot is the new server's now",
            )
            check(
                slow.id not in server.JOBS and slow.state == "claude",
                "the film the old server is making is left to it",
            )
            check(
                g_q.id in server.JOBS and g_fin.id in server.JOBS,
                "a dead server's queued film is made, and its film left mid-render finished",
            )
            last = lines(g_mid)[-1]
            check(
                g_mid.state == "interrupted"
                and last == {"type": "error", "text": agent.INTERRUPTED, "t": 7.0}
                and mem.docs.get(g_mid.id, {}).get("state") == "interrupted",
                "one Claude was writing when its server died is interrupted, and says so",
            )
            check(
                g_stop.state == "cancelled"
                and lines(g_stop)[-1]["text"] == "The film was cancelled."
                and mem.docs.get(g_stop.id, {}).get("state") == "cancelled"
                and not peers.cancel_requested(g_stop.id)
                and g_stop.id not in server.JOBS,
                "one its person stopped while nobody was making it is recorded cancelled",
            )
            check(
                legacy.state == "claude" and legacy.id not in server.JOBS,
                "one from before records named their server waits (its old server may still be"
                " putting it down)",
            )

            # ------------------------------------------------ the old film, through the new server
            st, j = await call(new_url, "GET", "/api/films/%s" % slow.id)
            n = len(lines(slow))
            check(
                st == 200
                and j.get("status") == "running"
                and j.get("stage") == "claude"
                and j.get("next") == n
                and any(e.get("text") == "Drawing it slowly." for e in j.get("events", []))
                and j.get("elapsed_s", 0) > 0
                and abs(j.get("cost_usd", 0) - 0.064) < 1e-3,
                "the old film's page, answered by the new server: running, with the old one's"
                " events and cost (%s)" % {k: j.get(k) for k in ("status", "stage", "next")},
            )
            st, j = await call(new_url, "GET", "/api/films/%s?since=%d" % (slow.id, n - 1))
            check(
                len(j.get("events", [])) == 1 and j.get("next") == n,
                "and a poll reads only what is new",
            )
            st, j = await call(
                new_url,
                "POST",
                "/api/films",
                json={"prompt": "another, meanwhile"},
                headers={"X-Client-Ip": "u:bg"},
            )
            check(
                st == 429 and "already" in j.get("error", ""),
                "its person is refused a second film: the old server's count (%s)" % j,
            )
            st, h = await call(new_url, "GET", "/api/health")
            modes = sorted((i["mode"], i["leader"]) for i in h.get("instances", []))
            check(
                h.get("running", 0) >= 2
                and modes == [("handed_off", False), ("serving", True)]
                and h.get("release") == films.RELEASE,
                "health counts both servers' films, and names each (%s)" % modes,
            )

            # ------------------------------------------------ a Stop pressed on the new server
            st, j = await call(
                new_url,
                "POST",
                "/api/films/%s/cancel" % slow.id,
                headers=tunnel | {"X-Client-Ip": "u:else"},
            )
            check(st == 403, "someone else cannot stop the old server's film")
            t1 = time.monotonic()
            st, j = await call(
                new_url,
                "POST",
                "/api/films/%s/cancel" % slow.id,
                headers=tunnel | {"X-Client-Ip": "u:bg"},
            )
            done = await until(lambda: slow.state == "cancelled", 10, every=0.1)
            check(
                st == 202 and bool(done) and time.monotonic() - t1 < 3,
                "its person can: the old server obeys (%.1f s)" % (time.monotonic() - t1),
            )
            check(
                lines(slow)[-1].get("text") == "The film was cancelled.",
                "and its page says so",
            )
            code = await asyncio.to_thread(exited, old, 30)
            check(code == 0, "the old server exits by itself once its film is over (%s)" % code)
            check(
                not [x for x in os.listdir(peers.DIR) if x.startswith(old_sid)],
                "leaving nothing of its own in servers/",
            )
            poller.cancel()
            s_slow, s_wait = seen.get(slow.id, []), seen.get(waiting.id, [])
            check(
                "running" in s_slow and "lost" not in s_slow + s_wait,
                "the new server never answered lost (%d polls: %s)"
                % (len(s_slow) + len(s_wait), sorted(set(s_slow + s_wait))),
            )

            # ------------------------------------------------ a film from before owners, later
            await asyncio.sleep(max(0.0, server.LEGACY_GRACE_S + 1 - (time.monotonic() - t0)))
            await server.adopt()
            check(
                legacy.state == "interrupted",
                "and after LEGACY_GRACE_S it is adopted like any other",
            )

            # ------------------------------------------------ the new server makes what it took
            for f, what in (
                (waiting, "the film that waited on the old server is made by the new one"),
                (g_q, "the dead server's queued film is made"),
                (g_fin, "its film left mid-render is finished"),
            ):
                j = {}
                for _ in range(600):
                    st, j = await call(new_url, "GET", "/api/films/%s" % f.id)
                    if j.get("status") in ("done", "error", "cancelled", "lost"):
                        break
                    await asyncio.sleep(1)
                check(
                    j.get("status") == "done", "%s (%s)" % (what, j.get("error") or j.get("status"))
                )
            check(
                g_fin.id not in CALLED
                and abs(g_fin.record().get("claude_cost_usd", 0) - 0.25) < 1e-9,
                "the one left mid-render without Claude, keeping Claude's earlier cost",
            )

            # ------------------------------------------------ YouTube: another server's in flight
            real = peers.peers
            key, ch = "post-00000009", "UCchannel0001"
            other = {"id": "x.1", "instance": "x", "mode": "handed_off", "leader": False}
            other |= {"jobs": [], "sends": [key], "drafts": [[g_q.id, ch]], "transcribing": []}
            peers.peers = lambda: [other]
            try:
                mine = {"X-Client-Ip": "u:g1"} | tunnel
                to = youtube.HOSTS[0] + "uploadType=resumable&upload_id=u1"
                st, j = await call(
                    new_url,
                    "POST",
                    "/api/films/%s/youtube" % g_q.id,
                    json={"to": to, "key": key},
                    headers=mine,
                )
                check(
                    st == 202 and j.get("state") == "sending" and key not in youtube.SENDS,
                    "a send another server is making is not started again (%s)" % j,
                )
                st, j = await call(
                    new_url, "GET", "/api/films/%s/youtube/%s" % (g_q.id, key), headers=mine
                )
                check(st == 200 and j.get("state") == "sending", "and is answered as going on")
                st, j = await call(
                    new_url,
                    "GET",
                    "/api/films/%s/youtube/%s" % (g_q.id, key),
                    headers=tunnel | {"X-Client-Ip": "u:else"},
                )
                check(st == 404, "to its film's person only")
                body = {"channel": {"id": ch, "title": "A channel"}, "recent": []}
                st, j = await call(
                    new_url, "POST", "/api/films/%s/youtube/draft" % g_q.id, json=body, headers=mine
                )
                check(
                    st == 202 and j.get("state") == "writing" and not ytdraft.JOBS,
                    "a draft another server is writing is not written again (%s)" % j,
                )
                st, j = await call(
                    new_url, "GET", "/api/films/%s/youtube/draft/%s" % (g_q.id, ch), headers=mine
                )
                check(st == 200 and j.get("state") == "writing", "and is answered as being written")
            finally:
                peers.peers = real
            youtube._save(
                g_q,
                {"key": "post-00000010", "film": g_q.id, "client": "u:g1", "state": "done"}
                | {"sent": 10, "size": 10, "video": {"id": "vid-1"}},
            )
            st, j = await call(
                new_url, "GET", "/api/films/%s/youtube/post-00000010" % g_q.id, headers=mine
            )
            check(
                st == 200 and (j.get("video") or {}).get("id") == "vid-1",
                "a send another server finished is answered from beside the film",
            )

            # ------------------------------------------------ the new server stops
            server.LIFE["stop"].set()
            code = await asyncio.wait_for(new_task, 60)
            new_task = None
            check(
                code == 0
                and not os.path.exists(os.path.join(peers.DIR, peers.SERVER_ID + ".json")),
                "a server stopping leaves the others' view",
            )
    finally:
        if new_task is not None:
            server.LIFE["stop"].set()
            await asyncio.wait([new_task], timeout=60)
        if old.poll() is None:
            old.kill()
            old.wait()
        log.close()
        if bad:
            with open(os.path.join(films.HOME, "old-server.log"), encoding="utf-8") as f:
                print("--- the old server said:\n" + f.read()[-4000:])
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    if CHILD:
        child(int(sys.argv[sys.argv.index("--child") + 1]))
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(os.environ["STUDIO_HOME"], ignore_errors=True)
    sys.exit(code)
