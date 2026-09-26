#!/usr/bin/env python
"""The Sketch Studio API end to end, with Claude stubbed out: no API calls, no cost.

    python studio/test_server.py

A stand-in for run_claude() writes the committed example film's files, then calls the studio's
real tools (check, stills) the way Claude would, and reports a known token count. Everything
else is real: films made side by side in their own folders, the scheduler, the soundtrack, the
renders, status polling, the files, the token checks, the per-client and daily limits, cancel,
a restart that picks up the films the last server left, a drain, and each run's cost record (kept
in memory, not written to MongoDB). A few minutes, most of it rendering. Everything happens in a
throwaway STUDIO_HOME, removed at the end.
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import film as films  # noqa: E402
import store  # noqa: E402
from sched import Sched  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}
CLAUDE_USD = (1000 * 4 + 2000 * 20 + 100000 * 0.2) / 1e6  # Opus 5.5 prices: $0.064
TTS_USD = 0.002  # what the stub's narration "spent"
EXPECT_USD = CLAUDE_USD + TTS_USD
CALLED = []  # the films the stub was asked to write


async def fake_claude(film, emit, meter, tools, auth="api"):
    CALLED.append(film.id)
    ex = os.path.join(films.KIT, "config", "sketch", "example")
    for f in films.MADE:
        shutil.copy(os.path.join(ex, f), film.dir)
    # a vo.json with what Claude may not change changed (the studio must put it back), and the
    # spend a voice run would have logged
    with open(film.path("vo.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "tts": "elevenlabs",
                "model": "wrong",
                "takes": 9,
                "voice": "Kore",
                "language": "en",
                "lines": [],
            },
            f,
        )
    os.makedirs(film.path("audio", "vo"), exist_ok=True)
    with open(film.path("audio", "vo", "spend.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"model": "m", "cost_usd": TTS_USD, "input": 20, "output": 100}) + "\n")
    meter.add("msg_" + film.id, USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    if "slow" in film.record().get("prompt", ""):
        await asyncio.sleep(120)  # a film someone cancels, or that keeps a slot busy
    await tools.check()
    await tools.stills([0, 2.5], True)
    emit({"type": "tool", "text": "wrote film.js (stub)"})


async def wait_for(c, auth, jid, states=("done", "error", "cancelled"), limit=600):
    since, st, t0 = 0, {"events": []}, time.time()
    events = []
    while time.time() - t0 < limit:
        st = await (await c.get("/api/films/%s?since=%d" % (jid, since), headers=auth)).json()
        since = st.get("next", since)
        events += st.get("events", [])
        if st.get("status") in states:
            break
        await asyncio.sleep(1)
    st["all_events"] = events
    return st


async def main():
    agent.run_claude = fake_claude
    agent.STORE = mem = store.MemoryStore()
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        auth = {"Authorization": "Bearer " + TOKEN}
        check((await c.get("/api/health")).status == 200, "health needs no token")
        check(
            (await c.get("/api/films")).status == 401, "the API refuses a request without a token"
        )
        r = await c.get("/api/films", headers={"Authorization": "Bearer nope"})
        check(r.status == 401, "the API refuses a wrong token")
        page = await (await c.get("/")).text()
        check(TOKEN in page, "the page opened on this machine carries the token")
        page = await (
            await c.get("/", headers={"Cf-Ray": "abc", "Cf-Connecting-Ip": "203.0.113.9"})
        ).text()
        check(TOKEN not in page, "the page relayed by the tunnel does not")
        r = await c.post("/api/films", json={"prompt": "x" * 10, "seconds": 7}, headers=auth)
        check(r.status == 400 and "seconds" in (await r.json())["error"], "a length off the list")

        # ------------------------------------------------ three films at once, three clients
        ids = []
        for i in range(3):
            r = await c.post(
                "/api/films",
                json={"prompt": "film number %d, stubbed" % i, "seconds": 5},
                headers=auth | {"X-Client-Ip": "u:test-%d" % i},
            )
            ids.append((await r.json()).get("id"))
            check(r.status == 202, "film %d accepted" % i)
        check(
            len(set(ids)) == 3
            and all(re.match(r"^studio-\d{8}-\d{6}-[a-z2-7]{6}$", j or "") for j in ids),
            "three unguessable, distinct ids",
        )
        h = await (await c.get("/api/health")).json()
        check(h["running"] + h["queued"] == 3, "health counts them (%s)" % h)
        results = await asyncio.gather(*(wait_for(c, auth, j) for j in ids))
        for j, st in zip(ids, results, strict=True):
            f = films.Film.open(j)
            check(
                st.get("status") == "done",
                "%s finishes (%s)" % (j[-6:], st.get("error") or st.get("status")),
            )
            check(
                os.path.getsize(f.path("outputs", "film.mp4")) > 100_000
                and f.dir.startswith(os.path.join(HOME, "projects")),
                "its video is in its own folder",
            )
            sheets = [e for e in st["all_events"] if e["type"] == "image"]
            check(
                sheets and all("/files/%s/" % j in e["url"] and "sig=" in e["url"] for e in sheets),
                "its review sheet is its own, signed",
            )
            check(
                abs((st.get("cost_usd") or 0) - EXPECT_USD) < 1e-4,
                "its cost, Claude + voice ($%s)" % st.get("cost_usd"),
            )
            with open(f.path("vo.json"), encoding="utf-8") as fh:
                vo = json.load(fh)
            check(vo["tts"] == "gemini" and vo["takes"] == 1, "its voice settings put back")
            d = mem.docs.get(j, {})
            check(
                d.get("state") == "done"
                and d.get("client", "").startswith("u:test-")
                and d.get("release") == films.RELEASE
                and len(d.get("calls", [])) == 1,
                "its record: done, its client, the release, one Claude call",
            )
        waits = [e for st in results for e in st["all_events"] if e["type"] == "wait"]
        check(bool(waits), "films queued for the renderer (%d waits)" % len(waits))

        video = results[0].get("video_url", "")
        path = video[video.index("/files/") :]
        r = await c.get(path)
        check(r.status == 200 and len(await r.read()) > 100_000, "the signed URL plays")
        check((await c.get(path.replace("&sig=", "&sig=0"))).status == 401, "a tampered one not")
        check(
            (await c.get("/files/%s/..%%2F..%%2F.env" % ids[0], headers=auth)).status == 404,
            "no path escape",
        )
        check((await c.get("/api/films/../etc", headers=auth)).status == 404, "no id escape")
        listed = await (await c.get("/api/films", headers=auth)).json()
        check({x["id"] for x in listed} >= set(ids), "the gallery lists them")

        # ------------------------------------------------ one film in the making per client
        r = await c.post(
            "/api/films", json={"prompt": "a slow one"}, headers=auth | {"X-Client-Ip": "u:busy"}
        )
        slow = (await r.json()).get("id")
        r = await c.post(
            "/api/films", json={"prompt": "and another"}, headers=auth | {"X-Client-Ip": "u:busy"}
        )
        check(
            r.status == 429 and "already" in (await r.json())["error"],
            "a second film from the same client waits for the first",
        )
        # through the tunnel, as the public site's requests come (this machine may cancel any)
        tunnel = auth | {"Cf-Ray": "test"}
        r = await c.post("/api/films/%s/cancel" % slow, headers=tunnel | {"X-Client-Ip": "u:else"})
        check(r.status == 403, "someone else cannot cancel it")
        r = await c.post("/api/films/%s/cancel" % slow, headers=tunnel | {"X-Client-Ip": "u:busy"})
        check(r.status == 202, "its own client can")
        st = await wait_for(c, auth, slow, limit=60)
        check(
            st.get("status") == "cancelled" and mem.docs[slow]["state"] == "cancelled",
            "and it is cancelled, on record too",
        )
        check(server.SCHED["claude"].used == 0, "its Claude slot is free again")

        # ------------------------------------------------ the day's budget
        server.DAILY_USD = EXPECT_USD
        r = await c.post("/api/films", json={"prompt": "over budget"}, headers=auth)
        check(r.status == 429 and "budget" in (await r.json())["error"], "past the day's budget")
        server.DAILY_USD = 1000

        # ------------------------------------------------ a restart finds what was left
        q = films.Film.create("left queued", 5, "drawn", client="u:r1")
        fin = films.Film.create("left mid-render", 5, "drawn", client="u:r2")
        ex = os.path.join(films.KIT, "config", "sketch", "example")
        for f in films.MADE:
            shutil.copy(os.path.join(ex, f), fin.dir)
        fin.update(state="finishing", claude_cost_usd=0.5)
        mid = films.Film.create("left while Claude wrote", 5, "drawn", client="u:r3")
        mid.update(state="claude")
        before = len(CALLED)
        await server.recover(None)
        st_q, st_f = await asyncio.gather(wait_for(c, auth, q.id), wait_for(c, auth, fin.id))
        check(st_q.get("status") == "done", "a queued film is made after a restart")
        check(
            st_f.get("status") == "done" and fin.id not in CALLED[before:],
            "a film left mid-render is finished, without Claude",
        )
        check(abs(st_f.get("claude_cost_usd", 0) - 0.5) < 1e-9, "keeping Claude's earlier cost")
        check(
            mid.state == "interrupted" and mem.docs.get(mid.id, {}).get("state") == "interrupted",
            "a film left mid-Claude is marked interrupted",
        )

        # ------------------------------------------------ drain: running ones finish, queued stay
        server.SCHED = Sched(claude=1)
        r1 = await c.post(
            "/api/films",
            json={"prompt": "slow, holding the only slot"},
            headers=auth | {"X-Client-Ip": "u:d1"},
        )
        r2 = await c.post(
            "/api/films",
            json={"prompt": "waiting behind it"},
            headers=auth | {"X-Client-Ip": "u:d2"},
        )
        d1, d2 = (await r1.json())["id"], (await r2.json())["id"]
        await asyncio.sleep(0.5)
        r = await c.post("/api/admin/drain", headers=auth)
        check(r.status == 200, "drain")
        r = await c.post("/api/films", json={"prompt": "too late"}, headers=auth)
        check(r.status == 503, "a draining server takes no new films")
        await asyncio.sleep(0.5)
        check(
            films.Film.open(d2).state == "queued" and d2 not in CALLED,
            "the queued film stays queued for the next server",
        )
        await c.post("/api/films/%s/cancel" % d1, headers=auth)
        h = await (await c.get("/api/health")).json()
        await asyncio.sleep(1)
        h = await (await c.get("/api/health")).json()
        check(h["draining"] and h["running"] == 0, "and then nothing is running (%s)" % h)
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
