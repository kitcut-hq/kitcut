#!/usr/bin/env python
"""The Sketch Studio API end to end, with Claude stubbed out: no API calls, no cost.

    python studio/test_server.py

A stand-in for run_claude() writes the committed example film's files and reports a known token
count. Everything after that is real: the queue, the soundtrack, the 5-second render, status
polling, the files, the token checks and the run's cost record (kept in memory, not written to
MongoDB). About a minute, most of it the render. The job folder is removed at the end.
"""

import os
import sys
import time
import shutil
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}
EXPECT_USD = (1000 * 4 + 2000 * 20 + 100000 * 0.2) / 1e6  # Opus 5.5 prices: $0.064


async def fake_claude(prompt, job, emit, meter):
    ex = os.path.join(agent.ROOT, "config", "sketch", "example")
    for f in agent.EDITABLE:
        shutil.copy(os.path.join(ex, f), job)
    meter.add("msg_1", USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    emit({"type": "tool", "text": "wrote film.js (stub)"})


async def main():
    agent.run_claude = fake_claude
    agent.STORE = mem = store.MemoryStore()
    bad, job = [], None

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
        check(
            (await c.get("/api/costs", headers={"X-Studio-Token": TOKEN})).status == 200,
            "X-Studio-Token works",
        )
        page = await (await c.get("/")).text()
        check(TOKEN in page, "the page opened on this machine carries the token")
        page = await (
            await c.get("/", headers={"Cf-Ray": "abc", "Cf-Connecting-Ip": "203.0.113.9"})
        ).text()
        check(TOKEN not in page, "the page relayed by the tunnel does not")

        r = await c.post("/api/films", json={"prompt": "the example film, stubbed"}, headers=auth)
        body = await r.json()
        job = body.get("id")
        check(
            r.status == 202 and job and body["status_url"].endswith(job),
            "POST /api/films queues a film",
        )
        since, st, t0 = 0, {}, time.time()
        while time.time() - t0 < 240:
            st = await (await c.get("/api/films/%s?since=%d" % (job, since), headers=auth)).json()
            since = st["next"]
            if st["status"] in ("done", "error"):
                break
            await asyncio.sleep(1)
        check(
            st.get("status") == "done",
            "the film finishes (%s)" % (st.get("error") or st.get("status")),
        )
        check(
            abs((st.get("cost_usd") or 0) - EXPECT_USD) < 1e-6,
            "status reports the cost $%s" % st.get("cost_usd"),
        )
        check(st.get("tokens", {}).get("cache_read") == 100000, "status reports the tokens")
        video = st.get("video_url", "")
        check(
            "/files/%s/film.mp4?exp=" % job in video and "&sig=" in video,
            "status gives a signed video URL",
        )
        path = video[video.index("/files/") :]
        r = await c.get(path)
        check(
            r.status == 200 and len(await r.read()) > 100_000,
            "the signed URL plays without the token",
        )
        check(
            (await c.get(path.replace("&sig=", "&sig=0"))).status == 401,
            "a tampered signature does not",
        )
        other = path.replace("film.mp4", "film_poster.png")
        check((await c.get(other)).status == 401, "nor does one signature open another file")
        sheets = [e for e in st.get("events", []) if e.get("type") == "image"]
        r = await c.get("/files/%s/film.mp4" % job, headers=auth)
        check(r.status == 200 and len(await r.read()) > 100_000, "the MP4 downloads with the token")
        check((await c.get("/files/%s/film.mp4" % job)).status == 401, "and not without it")
        r = await c.get("/files/%s/film.mp4?token=%s" % (job, TOKEN))
        check(r.status == 200, "?token= works (for <video src>)")
        check(
            (await c.get("/files/%s/..%%2F..%%2F.env" % job, headers=auth)).status == 404,
            "no path escape",
        )

        costs = await (await c.get("/api/costs", headers=auth)).json()
        check(abs(costs["total_usd"] - EXPECT_USD) < 1e-6, "/api/costs totals the runs")
        d = mem.docs.get(job, {})
        check(
            d.get("source") == "web" and d.get("client") == "local" and d.get("state") == "done",
            "one run record: source web, client local, state done",
        )
        check(
            len(d.get("calls", [])) == 1 and d["calls"][0]["cost_usd"] == round(EXPECT_USD, 6),
            "the record lists each Claude API call with its cost",
        )
        check(
            bool(d.get("created_at") and d.get("finished_at")),
            "with UTC created_at and finished_at",
        )
        check(
            not sheets or all("sig=" in e.get("url", "") for e in sheets),
            "review sheets come signed",
        )

        # the public limits: a visitor's films per day, and the day's budget
        server.PER_CLIENT_DAILY = 0
        r = await c.post(
            "/api/films",
            json={"prompt": "over the limit"},
            headers=auth | {"X-Client-Ip": "198.51.100.7"},
        )
        check(
            r.status == 429 and "limit" in (await r.json())["error"],
            "a visitor over the limit gets a 429",
        )
        server.DAILY_USD = EXPECT_USD / 2
        r = await c.post("/api/films", json={"prompt": "over budget"}, headers=auth)
        check(
            r.status == 429 and "budget" in (await r.json())["error"], "past the day's budget: 429"
        )
        check(len(mem.docs) == 1, "and neither refused request started a run")
    if job:
        shutil.rmtree(os.path.join(agent.ROOT, "projects", job), ignore_errors=True)
    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
