#!/usr/bin/env python
"""Sketch Studio's server: a JSON API and a page that turn a prompt into a short film -- many
films at once, each in a sandbox of its own.

    python studio/server.py [--port 8765]          then open http://127.0.0.1:8765
    powershell studio/serve.ps1                    the same, plus a public Cloudflare quick tunnel

It listens on 127.0.0.1 only; the outside world reaches it through the tunnel, normally via the
public site (kitcut-hq/sketch-studio on Vercel), which finds the tunnel's current URL in MongoDB
and adds the token server-side. Every /api and /files route (except /api/health) needs the token
(STUDIO_TOKEN in the studio's .env, created on first start) as `Authorization: Bearer <token>`,
`X-Studio-Token: <token>` or `?token=<token>`; the file URLs the API hands out are signed for 12
hours instead, so a browser can load them without it. The page gets the token filled in only when
opened on this machine; through the tunnel it asks.

Films run side by side (STUDIO_PARALLEL Claude sessions, default 3), each in its own folder under
STUDIO_HOME with its own Claude session, and share the machine through the scheduler (sched.py);
the rest wait their turn, up to STUDIO_MAX_QUEUE (default 5) of them. Anyone can reach this
through the public site, so the day's spend is capped (STUDIO_DAILY_USD, default 25, counting
a reserve for every film still being made, by its length), and each client -- the account the site
forwards as X-Client-Ip "u:<id>", else the IP -- may have one film in the making and
STUDIO_PER_CLIENT_DAILY (default 5) a day.

    POST /api/films              {"prompt", "seconds", "look"}  ->  202 {"id", "status", "position"}
                                 X-Priority: 1 (from the site, for a plan with priority): the
                                 film goes ahead of the others in every queue. {"auth": "login"}
                                 (this machine only): Claude runs on its Claude Code login.
    GET  /api/films/{id}         ?since=N  ->  {"status": queued|running|done|error|cancelled,
                                 "stage", "wait", "events": [...from N], "next", "video_url", ...}
    POST /api/films/{id}/cancel  the film's own client (or this machine) stops it
    GET  /api/films              the finished films, newest first
    GET  /api/costs              the spend: total, today, this month, per film, latest runs
    GET  /files/{id}/film.mp4    the film (also film_poster.png, review/sheet.png)
    GET  /api/health             {"ok", "running", "queued", "slots", "draining"}   (no token)
    POST /api/admin/drain        (this machine) take no new films, let the running ones finish:
                                 serve.ps1 restarts the server once "active" reaches 0. Films
                                 still queued stay queued, and the next server makes them.

Poll the status; there is no push, because Cloudflare quick tunnels do not carry server-sent
events. A server that starts finds the films the last one left: queued ones are made, ones that
were being mixed or rendered are finished, and ones Claude was still writing are marked
interrupted.
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
import agent  # noqa: E402 -- imports _env first, which re-execs into .venv; then the secrets
import film as films  # noqa: E402
import procs  # noqa: E402
import store  # noqa: E402
from film import Film  # noqa: E402
from sched import Sched  # noqa: E402

from aiohttp import web  # noqa: E402

HERE = agent.HERE
SCHED = Sched()
JOBS = {}  # id -> {"events", "status", "stage", "wait", "t0", "client", "task", "control"}
ADMIT = asyncio.Lock()  # one admission at a time: the limits are checked and taken together
DRAINING = False
TOKEN = ""
MAX_QUEUE = int(os.environ.get("STUDIO_MAX_QUEUE") or 5)
# the public site makes this reachable by anyone: a day's spend, and each client's films, are capped
DAILY_USD = float(os.environ.get("STUDIO_DAILY_USD") or 25)
PER_CLIENT_DAILY = int(os.environ.get("STUDIO_PER_CLIENT_DAILY") or 5)
KEEP_S = 3600  # a finished film's events stay in memory this long; then they come from disk


# ------------------------------------------------------------------ the token
def ensure_token():
    """STUDIO_TOKEN from the studio's .env, created and saved there on first start (never
    printed). The file is the working tree's, never a release's."""
    tok = procs.secret("STUDIO_TOKEN")
    if not tok:
        tok = secrets.token_urlsafe(32)
        path = os.environ.get("STUDIO_ENV_FILE") or os.path.join(films.REPO, ".env")
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n# Sketch Studio API token (studio/server.py)\nSTUDIO_TOKEN=%s\n" % tok)
        procs.SECRETS["STUDIO_TOKEN"] = tok
        print("created STUDIO_TOKEN in %s" % path, flush=True)
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


def client_of(req):
    """Who asks: the account (or IP) the public site forwards (trusted: the request carries the
    token), else the IP Cloudflare saw, else this machine."""
    return (
        req.headers.get("X-Client-Ip", "")[:64]
        or req.headers.get("Cf-Connecting-Ip")
        or ("local" if from_this_machine(req) else req.remote)
    )


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
def film_of(jid):
    f = Film.open(jid)
    if f is None:
        raise web.HTTPNotFound()
    return f


def base_url(req):
    """The URL the caller used: through the tunnel that is https://<name>.trycloudflare.com."""
    proto = req.headers.get("X-Forwarded-Proto", req.scheme)
    return "%s://%s" % (proto, req.host)


def reserve(seconds, auth="api"):
    """What a film being made may still spend, held against the day's budget: all of it on the
    key; on this machine's login only the voice and the paintings are paid for."""
    return films.limits(seconds)["reserve_usd"] if auth == "api" else 0.01 * seconds


def live(status=("queued", "running")):
    return [j for j in JOBS.values() if j["status"] in status]


def prune():
    """Forget finished films' events after a while (the page then reads them from disk)."""
    now = time.time()
    for jid in [k for k, j in JOBS.items() if j.get("ended") and now - j["ended"] > KEEP_S]:
        JOBS.pop(jid, None)


# ------------------------------------------------------------------ running a film
def start(film, finish_only=False):
    """Make the film in the background; its events go to memory and its events.jsonl."""
    log = film.path("events.jsonl")
    before = []
    if os.path.exists(log):  # a film picked up again after a restart keeps its log
        with open(log, encoding="utf-8") as f:
            before = [json.loads(x) for x in f if x.strip()]
    J = JOBS[film.id] = {
        "events": before,
        "status": "running" if finish_only else "queued",
        "stage": "queue",
        "wait": None,
        "t0": time.time() - (before[-1]["t"] if before else 0),
        "client": film.record().get("client", "local"),
        "auth": film.record().get("auth", "api"),
        "reserve": reserve(film.length, film.record().get("auth", "api")),
        "control": {},
        "ended": None,
    }

    def emit(ev):
        # t: seconds into the run, so a page reloaded half-way shows the same times
        ev = {**ev, "t": round(time.time() - J["t0"], 1)}
        J["events"].append(ev)
        # and on disk, so the film's page still has its log after this server restarts
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if ev["type"] == "stage":
            J["stage"], J["wait"], J["status"] = ev["name"], None, "running"
        elif ev["type"] == "wait":
            J["wait"] = ev["text"]
        elif ev["type"] in ("tool", "say"):
            J["wait"] = None
        elif ev["type"] == "cost":
            J["cost_usd"] = ev["usd"]

    async def run():
        ok = False
        try:
            # done/error only once make_film returns: by then studio.json and
            # kitcut.studio_runs hold the final cost
            r = await agent.make_film(
                film, emit, SCHED, auth=J["auth"], finish_only=finish_only, control=J["control"]
            )
            ok = r.get("ok")
            J["status"] = "done" if ok else "error"
        except asyncio.CancelledError:
            J["status"] = "queued" if J["control"].get("requeue") else "cancelled"
        except Exception as e:  # noqa: BLE001 -- make_film reports its own; this is the backstop
            emit({"type": "error", "text": str(e)})
            J["status"] = "error"
        J["ended"] = time.time()

    J["task"] = asyncio.create_task(run())
    return J


async def recover(app):
    """The films the last server left behind (in this home only)."""
    for f in reversed(Film.all()):  # oldest first, so the queue keeps its order
        if f.legacy or f.id in JOBS:
            continue
        st = f.state
        if st == "queued":
            start(f)
        elif st == "finishing":
            start(f, finish_only=True)
        elif st == "claude":
            why = "the studio restarted while Claude was working on it"
            f.update(
                state="interrupted",
                ok=False,
                error=why,
                finished=datetime.now().isoformat(timespec="seconds"),
            )
            await agent.save(
                f.id,
                {"state": "interrupted", "ok": False, "error": why, "finished_at": store.now()},
                final=True,
            )


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
    return web.FileResponse(os.path.join(films.KIT, "fonts", name))


async def health(req):
    running, queued = len(live(("running",))), len(live(("queued",)))
    return web.json_response(
        {
            "ok": True,
            "busy": running >= SCHED["claude"].capacity,
            "running": running,
            "queued": queued,
            "active": running + (0 if DRAINING else queued),
            "slots": SCHED.snapshot(),
            "draining": DRAINING,
            "release": films.RELEASE,
        }
    )


async def over_limit(client, seconds, auth="api"):
    """Why this request must wait (for now, or until tomorrow), or None. Today is local time.
    Nothing is refused to this machine itself except by the budget."""
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = await asyncio.to_thread(agent.STORE.runs, None, midnight)
    except Exception:  # noqa: BLE001 -- no record, no public spending
        if client == "local":
            return None
        return "The studio cannot check today's budget right now; please try again later."
    # a film still being made may spend its reserve (by its length: film.limits) beyond what its
    # record shows so far; the new one is held at its own
    reserved = sum(max(0.0, j["reserve"] - (j.get("cost_usd") or 0)) for j in live())
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    if spent + reserved + reserve(seconds, auth) > DAILY_USD:
        return "Today's budget ($%.0f) is used up. Please try again tomorrow." % DAILY_USD
    if client == "local":
        return None
    if any(j["client"] == client for j in live()):
        return "You already have a film in the making; wait for it to finish (or cancel it)."
    mine = sum(1 for r in rows if r.get("client") == client and r.get("kind") == "film")
    if mine >= PER_CLIENT_DAILY:
        return "That is %d films today, the limit for now. Please try again tomorrow." % mine
    return None


async def create(req):
    if DRAINING:
        return web.json_response(
            {"error": "The studio is restarting; try again in a minute."}, status=503
        )
    try:
        body = await req.json()
    except ValueError:
        return web.json_response({"error": 'send JSON: {"prompt": "..."}'}, status=400)
    prompt = str(body.get("prompt", "")).strip()[:600]
    if len(prompt) < 3:
        return web.json_response({"error": "write a prompt"}, status=400)
    try:
        seconds = int(body.get("seconds") or films.LENGTHS[0])
    except (TypeError, ValueError):
        seconds = 0
    if seconds not in films.LENGTHS:
        return web.json_response(
            {"error": "seconds must be one of %s" % ", ".join(map(str, films.LENGTHS))},
            status=400,
        )
    look = body.get("look") or films.LOOKS[0]
    if look not in films.LOOKS:
        return web.json_response(
            {"error": "look must be one of %s" % ", ".join(films.LOOKS)}, status=400
        )
    client = client_of(req)
    # a plan whose films go first (the site sends it, trusted like X-Client-Ip)
    priority = 1 if req.headers.get("X-Priority", "").strip() == "1" else 0
    # this machine may have a film made on its own Claude Code login (internal runs); never
    # anyone through the tunnel
    auth = "login" if body.get("auth") == "login" and from_this_machine(req) else "api"
    prune()
    # the check and the taking happen under one lock: two requests at the same moment cannot
    # both slip under a limit that has room for one
    async with ADMIT:
        if len(live(("queued",))) >= MAX_QUEUE:
            return web.json_response({"error": "the queue is full; try again later"}, status=429)
        refused = await over_limit(client, seconds, auth)
        if refused:
            return web.json_response({"error": refused}, status=429)
        f = Film.create(
            prompt, seconds, look, client=client, source="web", priority=priority, auth=auth
        )
        await agent.save(f.id, agent.first_record(f, "web", client))
        start(f)
    await asyncio.sleep(0)  # let it take a free slot now, so the answer says whether it waits
    ahead = SCHED["claude"].ahead(f.id)
    return web.json_response(
        {
            "id": f.id,
            "status": "queued" if ahead is not None else "running",
            "position": (ahead + 1) if ahead is not None else 0,
            "status_url": "%s/api/films/%s" % (base_url(req), f.id),
        },
        status=202,
    )


async def cancel(req):
    f = film_of(req.match_info["id"])
    J = JOBS.get(f.id)
    if J is None or J["status"] not in ("queued", "running"):
        return web.json_response({"error": "that film is not being made"}, status=409)
    if not (from_this_machine(req) or J["client"] == client_of(req)):
        return web.json_response({"error": "only whoever asked for a film can stop it"}, status=403)
    J["task"].cancel()
    return web.json_response({"id": f.id, "status": "cancelling"}, status=202)


async def drain(req):
    """Take no more films; let the running ones finish; leave the queued ones for the next
    server (serve.ps1 then restarts). Only from this machine."""
    global DRAINING
    if not from_this_machine(req):
        raise web.HTTPForbidden()
    DRAINING = True
    for J in live(("queued",)):
        J["control"]["requeue"] = True
        J["task"].cancel()
    return web.json_response({"draining": True, "running": len(live(("running",)))})


async def status(req):
    jid = req.match_info["id"]
    f = film_of(jid)  # 404 unless it exists
    J = JOBS.get(f.id)
    since = max(0, int(req.query.get("since") or 0))

    def with_urls(events):
        # a review sheet gets a signed URL, so a browser can show it without the token
        return [
            ev | {"url": signed(req, jid, ev["path"]) + "&v=%d" % ev["v"]}
            if ev["type"] == "image"
            else ev
            for ev in events
        ]

    r = f.record()
    if J is None:  # made before this server started: what is on disk is all there is
        st = f.state
        st = {
            "done": "done",
            "cancelled": "cancelled",
            "error": "error",
            "interrupted": "error",
        }.get(st, "lost")
        log = f.path("events.jsonl")
        events = []
        if os.path.exists(log):
            with open(log, encoding="utf-8") as fh:
                events = [json.loads(x) for x in fh if x.strip()]
        out = {
            "id": jid,
            "status": st,
            "events": with_urls(events[since:]),
            "next": len(events),
        }
    else:
        out = {
            "id": jid,
            "status": J["status"],
            "stage": J["stage"],
            "elapsed_s": round(time.time() - J["t0"], 1),
            "events": with_urls(J["events"][since:]),
            "next": len(J["events"]),
        }
        if J["wait"]:
            out["wait"] = J["wait"]
        ahead = SCHED["claude"].ahead(f.id)
        if J["status"] == "queued" and ahead is not None:
            out["position"] = ahead + 1
        if J.get("cost_usd") is not None:
            out["cost_usd"] = J["cost_usd"]  # so far; the final figure replaces it below
        if J["status"] not in ("done", "error", "cancelled"):
            r = {k: r.get(k) for k in ("prompt", "look", "length")}
    if out["status"] == "done":
        out.update(
            video_url=signed(req, jid, "film.mp4"), poster_url=signed(req, jid, "film_poster.png")
        )
    keys = (
        "prompt",
        "look",
        "length",
        "image_cost_usd",
        "images",
        "seconds",
        "cost_usd",
        "claude_cost_usd",
        "tts_cost_usd",
        "tokens",
        "turns",
        "stages",
        "error",
        "claude_said",
    )
    for k in keys:
        if r.get(k) is not None:
            out[k] = r[k]
    return web.json_response(out)


async def files(req):
    d = os.path.join(film_of(req.match_info["id"]).dir, "outputs")
    p = os.path.normcase(os.path.realpath(os.path.join(d, req.match_info["path"])))
    if not p.startswith(os.path.normcase(os.path.realpath(d)) + os.sep) or not os.path.isfile(p):
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


async def list_films(req):
    """The finished films, newest first."""
    out = []
    for f in Film.all():
        r = f.record()
        if r.get("ok"):
            out.append(
                {
                    k: r.get(k)
                    for k in ("prompt", "look", "length", "seconds", "cost_usd", "turns", "stages")
                }
                | {
                    "id": f.id,
                    "video_url": signed(req, f.id, "film.mp4"),
                    "poster_url": signed(req, f.id, "film_poster.png"),
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
            web.get("/api/films", list_films),
            web.get("/api/costs", costs),
            web.post("/api/films", create),
            web.get("/api/films/{id}", status),
            web.post("/api/films/{id}/cancel", cancel),
            web.post("/api/admin/drain", drain),
            web.get("/files/{id}/{path:.+}", files),
        ]
    )
    app.on_startup.append(recover)
    return app


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if not procs.secret("ANTHROPIC_API_KEY"):  # fail now, not on the first request
        sys.exit("ANTHROPIC_API_KEY is not set (put it in the studio's .env)")
    app = make_app(ensure_token())
    print(
        "Sketch Studio on http://127.0.0.1:%d  (code %s, home %s)"
        % (args.port, films.RELEASE, films.HOME),
        flush=True,
    )
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
