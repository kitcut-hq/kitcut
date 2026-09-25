#!/usr/bin/env python
"""Sketch Studio's web page: a prompt box that turns into a 5-second film.

    python studio/server.py [--port 8765]      then open http://127.0.0.1:8765

One film is made at a time (the render needs the GPU and a headless browser); a second request
waits its turn. Progress streams to the page as server-sent events. Local only: it listens on
127.0.0.1, has no accounts, and spends the API key in .env on every film.
"""

import os
import sys
import json
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first, which re-execs into .venv

from aiohttp import web  # noqa: E402

ROOT, HERE = agent.ROOT, agent.HERE
PROJECTS = os.path.join(ROOT, "projects")
JOBS = {}  # id -> {"events": [...], "tick": asyncio.Event, "done": bool}
LOCK = asyncio.Lock()


def job_dir(jid):
    if not jid.startswith("studio-") or os.sep in jid or "/" in jid or ".." in jid:
        raise web.HTTPNotFound()
    d = os.path.join(PROJECTS, jid)
    if not os.path.isdir(d):
        raise web.HTTPNotFound()
    return d


async def index(req):
    return web.FileResponse(os.path.join(HERE, "index.html"), headers={"Cache-Control": "no-cache"})


async def font(req):
    name = req.match_info["name"]
    if name not in ("Caveat.woff2", "PatrickHand-400.woff2", "Inter.woff2"):
        raise web.HTTPNotFound()
    return web.FileResponse(os.path.join(ROOT, "fonts", name))


async def create(req):
    body = await req.json()
    prompt = str(body.get("prompt", "")).strip()[:600]
    if len(prompt) < 3:
        raise web.HTTPBadRequest(text="write a prompt")
    d = agent.new_job(prompt)
    jid = os.path.basename(d)
    J = JOBS[jid] = {"events": [], "tick": asyncio.Event(), "done": False}

    def emit(ev):
        J["events"].append(ev)
        J["tick"].set()
        J["tick"] = asyncio.Event()

    async def run():
        if LOCK.locked():
            emit({"type": "stage", "name": "queue", "text": "Waiting for the film before this one"})
        async with LOCK:
            try:
                await agent.make_film(prompt, emit, d)
            except Exception as e:  # noqa: BLE001 -- make_film reports its own; this is the backstop
                emit({"type": "error", "text": str(e)})
        J["done"] = True
        emit({"type": "end"})

    asyncio.create_task(run())
    return web.json_response({"id": jid})


async def events(req):
    jid = req.match_info["id"]
    J = JOBS.get(jid)
    if J is None:
        job_dir(jid)  # 404 unless it exists
        raise web.HTTPGone(text="this film was made before the server restarted")
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
    await resp.prepare(req)
    i = 0
    try:
        while True:
            tick = J["tick"]
            while i < len(J["events"]):
                await resp.write(("data: %s\n\n" % json.dumps(J["events"][i])).encode("utf-8"))
                i += 1
            if J["done"]:
                break
            try:
                await asyncio.wait_for(tick.wait(), 15)
            except TimeoutError:
                await resp.write(b": keep-alive\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return resp


async def files(req):
    d = os.path.join(job_dir(req.match_info["id"]), "outputs")
    p = os.path.normcase(os.path.abspath(os.path.join(d, req.match_info["path"])))
    if not p.startswith(os.path.normcase(os.path.abspath(d)) + os.sep) or not os.path.isfile(p):
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "no-cache"})


async def films(req):
    """The finished films, newest first."""
    out = []
    for jid in sorted(os.listdir(PROJECTS), reverse=True):
        rec = os.path.join(PROJECTS, jid, "studio.json")
        if not jid.startswith("studio-") or not os.path.exists(rec):
            continue
        with open(rec, encoding="utf-8") as f:
            r = json.load(f)
        if r.get("ok"):
            out.append(
                {k: r.get(k) for k in ("prompt", "model", "seconds", "cost_usd", "turns", "stages")}
                | {"id": jid}
            )
        if len(out) >= 12:
            break
    return web.json_response(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    agent.child_env()  # fail now, not on the first click, if the key is missing
    app = web.Application()
    app.add_routes(
        [
            web.get("/", index),
            web.get("/fonts/{name}", font),
            web.get("/api/films", films),
            web.post("/api/films", create),
            web.get("/api/films/{id}/events", events),
            web.get("/files/{id}/{path:.+}", files),
        ]
    )
    print("Sketch Studio on http://127.0.0.1:%d" % args.port, flush=True)
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
