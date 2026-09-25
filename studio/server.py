#!/usr/bin/env python
"""Sketch Studio's server: a JSON API and a page that turn one prompt into a 5-second film.

    python studio/server.py [--port 8765]          then open http://127.0.0.1:8765
    powershell studio/serve.ps1                    the same, plus a public Cloudflare quick tunnel

It listens on 127.0.0.1 only; the outside world reaches it through the tunnel, normally via the
public site (kitcut-hq/sketch-studio on Vercel), which finds the tunnel's current URL in MongoDB
and adds the token server-side. Every /api and /files route (except /api/health) needs the token
from .env (STUDIO_TOKEN, created on first start) as `Authorization: Bearer <token>`,
`X-Studio-Token: <token>` or `?token=<token>`; the file URLs the API hands out are signed for 12
hours instead, so a browser can load them without it. The page gets the token filled in only when
opened on this machine; through the tunnel it asks.

Anyone can reach it through the public site, so each day's spend is capped (STUDIO_DAILY_USD,
default 25) and so is each visitor's number of films (STUDIO_PER_CLIENT_DAILY, default 5); the
visitor is the X-Client-Ip the site forwards.

    POST /api/films            {"prompt": "..."}  ->  202 {"id", "status", "position", "status_url"}
    GET  /api/films/{id}       ?since=N  ->  {"status": queued|running|done|error, "stage",
                               "events": [...from N], "next", "video_url", "cost_usd", ...}
    GET  /api/films            the finished films, newest first
    GET  /api/costs            the spend: total, today, this month, per film, latest runs
    GET  /files/{id}/film.mp4  the film (also film_poster.png, review/sheet.png)
    GET  /api/health           {"ok", "busy", "queued"}   (no token)

Poll the status; there is no push, because Cloudflare quick tunnels do not carry server-sent
events. One film is made at a time (the render needs the GPU and a headless browser); up to
STUDIO_MAX_QUEUE (default 5) more wait, and the next one gets a 429.
"""

import os
import sys
import hmac
import json
import time
import asyncio
import secrets
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first, which re-execs into .venv

from aiohttp import web  # noqa: E402

ROOT, HERE = agent.ROOT, agent.HERE
PROJECTS = os.path.join(ROOT, "projects")
JOBS = {}  # id -> {"events": [...], "status", "stage", "t0", "prompt"}
WAITING = []  # ids queued behind the running film, in order
LOCK = asyncio.Lock()
TOKEN = ""
MAX_QUEUE = int(os.environ.get("STUDIO_MAX_QUEUE") or 5)
# the public site makes this reachable by anyone: a day's spend, and each visitor's films, are capped
DAILY_USD = float(os.environ.get("STUDIO_DAILY_USD") or 25)
PER_CLIENT_DAILY = int(os.environ.get("STUDIO_PER_CLIENT_DAILY") or 5)


# ------------------------------------------------------------------ the token
def ensure_token():
    """STUDIO_TOKEN from .env, created and saved there on first start (never printed)."""
    tok = os.environ.get("STUDIO_TOKEN", "").strip()
    if not tok:
        tok = secrets.token_urlsafe(32)
        with open(os.path.join(ROOT, ".env"), "a", encoding="utf-8") as f:
            f.write("\n# Sketch Studio API token (studio/server.py)\nSTUDIO_TOKEN=%s\n" % tok)
        print("created STUDIO_TOKEN in .env", flush=True)
    return tok


def from_this_machine(req):
    """A request straight from this machine, not one relayed by the tunnel (which also connects
    from 127.0.0.1, but adds Cloudflare's headers and keeps the public host name)."""
    if req.remote not in ("127.0.0.1", "::1"):
        return False
    if any(h in req.headers for h in ("Cf-Ray", "Cf-Connecting-Ip", "Cf-Visitor")):
        return False
    return req.host.split(":")[0] in ("127.0.0.1", "localhost")


def token_of(req):
    auth = req.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return req.headers.get("X-Studio-Token") or req.query.get("token") or ""


# A file URL the API hands out carries its own short-lived signature instead of the token, so a
# browser on the public site can load the video straight from here without ever seeing the token.
SIGNED_FOR = 12 * 3600


def sign(path, exp):
    return hmac.new(TOKEN.encode(), b"%s:%d" % (path.encode(), exp), "sha256").hexdigest()[:32]


def signed(req, jid, rel):
    path = "/files/%s/%s" % (jid, rel)
    exp = int(time.time()) + SIGNED_FOR
    return "%s%s?exp=%d&sig=%s" % (base_url(req), path, exp, sign(path, exp))


def signature_ok(req):
    try:
        exp = int(req.query.get("exp", "0"))
    except ValueError:
        return False
    return exp > time.time() and hmac.compare_digest(req.query.get("sig", ""), sign(req.path, exp))


@web.middleware
async def need_token(req, handler):
    p = req.path
    guarded = p.startswith(("/api/", "/files/")) and p != "/api/health"
    ok = hmac.compare_digest(token_of(req).encode(), TOKEN.encode())
    if guarded and not ok and not (p.startswith("/files/") and signature_ok(req)):
        return web.json_response({"error": "missing or wrong token"}, status=401)
    return await handler(req)


# ------------------------------------------------------------------ helpers
def job_dir(jid):
    if not jid.startswith("studio-") or os.sep in jid or "/" in jid or ".." in jid:
        raise web.HTTPNotFound()
    d = os.path.join(PROJECTS, jid)
    if not os.path.isdir(d):
        raise web.HTTPNotFound()
    return d


def base_url(req):
    """The URL the caller used: through the tunnel that is https://<name>.trycloudflare.com."""
    proto = req.headers.get("X-Forwarded-Proto", req.scheme)
    return "%s://%s" % (proto, req.host)


def record(jid):
    with open(os.path.join(job_dir(jid), "studio.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ routes
async def index(req):
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        page = f.read()
    page = page.replace("__TOKEN__", TOKEN if from_this_machine(req) else "")
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


async def font(req):
    name = req.match_info["name"]
    if name not in ("Caveat.woff2", "PatrickHand-400.woff2", "Inter.woff2"):
        raise web.HTTPNotFound()
    return web.FileResponse(os.path.join(ROOT, "fonts", name))


async def health(req):
    return web.json_response({"ok": True, "busy": LOCK.locked(), "queued": len(WAITING)})


async def over_limit(client):
    """Why this request must wait until tomorrow, or None. Today is local time. Nothing is
    refused to this machine itself except by the budget."""
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = await asyncio.to_thread(agent.STORE.runs, None, midnight)
    except Exception:  # noqa: BLE001 -- no record, no public spending
        if client == "local":
            return None
        return "The studio cannot check today's budget right now; please try again later."
    if sum(r.get("cost_usd") or 0 for r in rows) >= DAILY_USD:
        return "Today's budget ($%.0f) is used up. Please try again tomorrow." % DAILY_USD
    if client == "local":
        return None
    mine = sum(1 for r in rows if r.get("client") == client and r.get("kind") == "film")
    mine += sum(1 for j in JOBS.values() if j.get("client") == client and j["status"] == "queued")
    if mine >= PER_CLIENT_DAILY:
        return "That is %d films today, the limit for now. Please try again tomorrow." % mine
    return None


async def create(req):
    try:
        body = await req.json()
    except ValueError:
        return web.json_response({"error": 'send JSON: {"prompt": "..."}'}, status=400)
    prompt = str(body.get("prompt", "")).strip()[:600]
    if len(prompt) < 3:
        return web.json_response({"error": "write a prompt"}, status=400)
    if len(WAITING) >= MAX_QUEUE:
        return web.json_response({"error": "the queue is full; try again later"}, status=429)
    # who asked: the visitor's IP as the public site forwards it (trusted: this request carries
    # the token), else as Cloudflare saw it, else this machine
    client = (
        req.headers.get("X-Client-Ip", "")[:64]
        or req.headers.get("Cf-Connecting-Ip")
        or ("local" if from_this_machine(req) else req.remote)
    )
    refused = await over_limit(client)
    if refused:
        return web.json_response({"error": refused}, status=429)
    d = agent.new_job(prompt)
    jid = os.path.basename(d)
    J = JOBS[jid] = {
        "events": [],
        "status": "queued",
        "stage": "queue",
        "t0": time.time(),
        "client": client,
    }
    WAITING.append(jid)

    def emit(ev):
        # t: seconds into the run, so a page reloaded half-way shows the same times
        J["events"].append({**ev, "t": round(time.time() - J["t0"], 1)})
        if ev["type"] == "stage":
            J["stage"] = ev["name"]
        elif ev["type"] == "cost":
            J["cost_usd"] = ev["usd"]

    async def run():
        async with LOCK:
            WAITING.remove(jid)
            J["status"] = "running"
            ok = False
            try:
                # done/error only once make_film returns: by then studio.json and
                # kitcut.studio_runs hold the final cost
                ok = (await agent.make_film(prompt, emit, d, source="web", client=client)).get("ok")
            except Exception as e:  # noqa: BLE001 -- make_film reports its own; this is the backstop
                emit({"type": "error", "text": str(e)})
            J["status"] = "done" if ok else "error"

    asyncio.create_task(run())
    return web.json_response(
        {
            "id": jid,
            "status": "queued",
            "position": len(WAITING) - (0 if LOCK.locked() else 1),
            "status_url": "%s/api/films/%s" % (base_url(req), jid),
        },
        status=202,
    )


async def status(req):
    jid = req.match_info["id"]
    job_dir(jid)  # 404 unless it exists
    J = JOBS.get(jid)
    if J is None:  # made before this server started: the record on disk is all there is
        r = record(jid)
        st = "done" if r.get("ok") else ("error" if "finished" in r else "lost")
        out = {"id": jid, "status": st, "prompt": r.get("prompt"), "events": [], "next": 0}
    else:
        since = max(0, int(req.query.get("since") or 0))
        r = record(jid) if J["status"] in ("done", "error") else {}
        out = {
            "id": jid,
            "status": J["status"],
            "stage": J["stage"],
            "elapsed_s": round(time.time() - J["t0"], 1),
            # a review sheet gets a signed URL, so a browser can show it without the token
            "events": [
                ev | {"url": signed(req, jid, ev["path"]) + "&v=%d" % ev["v"]}
                if ev["type"] == "image"
                else ev
                for ev in J["events"][since:]
            ],
            "next": len(J["events"]),
        }
        if J["status"] == "queued":
            out["position"] = WAITING.index(jid) + 1
        if J.get("cost_usd") is not None:
            out["cost_usd"] = J["cost_usd"]  # so far; the final figure replaces it below
    if out["status"] == "done":
        out.update(
            video_url=signed(req, jid, "film.mp4"), poster_url=signed(req, jid, "film_poster.png")
        )
    for k in ("prompt", "seconds", "cost_usd", "tokens", "turns", "stages", "error", "claude_said"):
        if r.get(k) is not None:
            out[k] = r[k]
    return web.json_response(out)


async def files(req):
    d = os.path.join(job_dir(req.match_info["id"]), "outputs")
    p = os.path.normcase(os.path.abspath(os.path.join(d, req.match_info["path"])))
    if not p.startswith(os.path.normcase(os.path.abspath(d)) + os.sep) or not os.path.isfile(p):
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "no-cache"})


async def costs(req):
    """The spend, from kitcut.studio_runs: totals, and the latest runs (?last=N, default 50)."""
    try:
        rows = await asyncio.to_thread(agent.runs)
    except Exception as e:  # noqa: BLE001 -- say why, rather than a bare 500
        return web.json_response({"error": "the cost records are unreachable: %s" % e}, status=503)
    last = max(1, min(500, int(req.query.get("last") or 50)))
    body = agent.spend_summary(rows) | {"runs_latest": rows[-last:][::-1]}
    return web.json_response(body, dumps=lambda o: json.dumps(o, default=str))


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
                {k: r.get(k) for k in ("prompt", "seconds", "cost_usd", "turns", "stages")}
                | {
                    "id": jid,
                    "video_url": signed(req, jid, "film.mp4"),
                    "poster_url": signed(req, jid, "film_poster.png"),
                }
            )
        if len(out) >= 12:
            break
    return web.json_response(out)


def make_app(token):
    global TOKEN
    TOKEN = token
    app = web.Application(middlewares=[need_token], client_max_size=64 * 1024)
    app.add_routes(
        [
            web.get("/", index),
            web.get("/film/{id}", index),  # one film's page: the page reads the id from the path
            web.get("/fonts/{name}", font),
            web.get("/api/health", health),
            web.get("/api/films", films),
            web.get("/api/costs", costs),
            web.post("/api/films", create),
            web.get("/api/films/{id}", status),
            web.get("/files/{id}/{path:.+}", files),
        ]
    )
    return app


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    agent.child_env()  # fail now, not on the first request, if the key is missing
    app = make_app(ensure_token())
    print("Sketch Studio on http://127.0.0.1:%d" % args.port, flush=True)
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
