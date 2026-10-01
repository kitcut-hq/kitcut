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
through the public site, so the day's spend is capped (STUDIO_DAILY_USD, default 100, counting
a reserve for every film still being made, by its length), and each client -- the workspace the
site forwards as X-Client-Ip "o:<id>" ("u:<id>" before workspaces: the same one, clients.py),
else the IP -- may have one film in the making (more when
its plan allows: X-At-Once, up to STUDIO_AT_ONCE_MAX, default 2) and STUDIO_PER_CLIENT_DAILY
(default 5) a day -- except the workspaces in STUDIO_DAILY_EXEMPT (the operator's own), which
the day's budget still holds.

    POST /api/films              {"prompt", "seconds", "look", "attachments", "listed",
                                  "people": [{"upload", "name"}], "character_style"}  ->  202
                                 {"id", "status", "position"}. X-Priority: 1 (from the site, for
                                 a plan with priority): the film goes ahead of the others in every
                                 queue. X-At-Once: N (from the site, for a plan that allows it):
                                 the account may have N films in the making instead of one.
                                 "listed": false keeps it out of the gallery (link-only).
                                 X-Source: mcp and X-App: <name> (from the site): it was asked for
                                 through an assistant. {"auth": "login"} (this machine only):
                                 Claude runs on its Claude Code login. X-Preview: 1 (from the
                                 site; {"preview": true} from this machine): the film's log gets
                                 "preview" events, a signed review/preview.html to watch while it
                                 is made (tools.py PREVIEW).
                                 "project": {id, name, brief, from_account_cast}: an episode of
                                 the site's project, with the project's library (library.py)
    GET  /api/library            the asker's cast and films; ?project=<id>: that project's, and
                                 its pictures and voice lines. Also GET /api/library/{name}/
                                 thumb.png, DELETE /api/library/{name} (a cast member), each
                                 with ?project=
    POST /api/library/pictures   {"project", "upload", "name"}: an upload becomes a picture every
                                 episode of the project gets; GET .../pictures/{name}/thumb.png
                                 and DELETE .../pictures/{name}, with ?project=
    POST /api/library/voice      {"project", "film", "line"}: approve line i of one of the
                                 asker's finished episodes as the project's voice line: the
                                 next episodes play that recording for the same words and voice
                                 (docs/studio-voice-lines.md); GET .../voice/{key}.mp3 and
                                 DELETE .../voice/{key}, with ?project=
    GET  /api/films/{id}/lines   the asker's finished film's narration lines, each with its key
                                 and whether its project has it approved; .../lines/{i}.mp3
    GET  /api/films/{id}         ?since=N  ->  {"status": queued|running|done|error|cancelled,
                                 "stage", "wait", "events": [...from N], "next", "video_url",
                                 "listed", ...}; a film copied online (media.py) has its lasting
                                 URLs there instead of signed ones
    POST /api/films/{id}/cancel  the film's own client (or this machine) stops it
    POST /api/films/{id}/listed  {"listed": true|false}: the film's own client shows it in the
                                 gallery or keeps it link-only
    GET  /api/uploads            the asker's pictures, voice notes and documents no film has taken
    POST /api/films/{id}/youtube {"to": <YouTube upload session>, "key"}: the film's own client
                                 sends the finished film into a session the site opened (youtube.py)
    GET  /api/films/{id}/youtube/{key}  how that send is going, and YouTube's answer
    POST /api/films/{id}/youtube/draft {"channel": {"id", "title", "handle"}, "recent": [...]}:
                                 the film's own client has its YouTube title, description and
                                 tags written from the film, in the voice of the channel's latest
                                 uploads (ytdraft.py); 202 while writing, 200 with the draft
    GET  /api/films/{id}/youtube/draft/{channel}  that draft: writing, done or failed
    GET  /api/films              the finished films, newest first
    GET  /api/costs              the spend: total, today, this month, per film, latest runs
    GET  /files/{id}/film.mp4    the film (also film_poster.png, review/sheet.png, and card.jpg:
                                 its 1200x628 link preview, made on first request)
    GET  /api/health             {"ok", "busy", "running", "queued", "active", "slots", "draining",
                                 "release", "server", "instances"}   (no token). running, queued
                                 and active count every live server's films; release is the
                                 leader's; instances: [{"id", "release", "mode", "leader",
                                 "running"}], this server first
    POST /api/admin/films/<id>/hidden  (this machine) {"hidden": true|false}: out of the gallery
                                 (its page and link still work), or back in
    POST /api/admin/drain        (this machine) take no new films, let the running ones finish:
                                 serve.ps1 restarts the server once "active" reaches 0. Films
                                 still queued stay queued, and the next server makes them.

Poll the status; there is no push, because Cloudflare quick tunnels do not carry server-sent
events.

Several servers share one STUDIO_HOME during a ship (peers.py): each release runs as a server of
its own (systemd kitcut-studio@<instance>), all on 127.0.0.1:<port> with SO_REUSEPORT on Linux.
The one `current` names takes the new films; the one it replaces hands over (handoff()) -- its
films still waiting for a Claude slot go back to the queue for the new one, it stops listening,
finishes the films it is making and exits by itself. Nothing waits and nothing is killed: a ship
on 2026-09-28 restarted the studio under a paying film 28 minutes in (docs/known-issues.md
KI-031). Only the leader (leader.lock) admits films; every server answers for every film -- one
another server is making is read from its record and events.jsonl, and a Stop for it is passed on
(peers.request_cancel) -- and the limits count every live server's films. A film's record names
the server making it ("server"). The leader adopts (adopt()) what nobody alive is making: queued
films are made, ones left being mixed or rendered are finished, and ones Claude was writing when
their server died are marked interrupted.

A server that stops (SIGTERM: a reboot, systemctl stop) tells its films so before it cancels
them (shutdown()): one Claude was writing is recorded interrupted, one being mixed or rendered is
left finishing, a queued one stays queued -- only a person's Stop records cancelled -- and the
leader, this server's successor or the next one, adopts what it left. An interrupted film can be
picked up again: studio/resume.py.
"""

import os
import re
import sys
import hmac
import json
import time
import errno
import signal
import socket
import asyncio
import secrets
import argparse
import contextlib
from collections import OrderedDict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402
import clients  # noqa: E402 -- imports _env first, which re-execs into .venv; then the secrets
import film as films  # noqa: E402
import library  # noqa: E402
import media  # noqa: E402
import peers  # noqa: E402
import procs  # noqa: E402
import store  # noqa: E402
import templates  # noqa: E402
import validate  # noqa: E402
import thumbs  # noqa: E402
import uploads  # noqa: E402
import youtube  # noqa: E402
import ytdraft  # noqa: E402
import share  # noqa: E402
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
PROMPT_MAX = 12000  # characters of a prompt: a long pasted brief with its narration fits (the page caps it too)
# the public site makes this reachable by anyone: a day's spend, and each client's films, are
# capped. It must hold at least one film of the longest length's reserve (8 minutes: ~$29,
# film.limits)
DAILY_USD = float(os.environ.get("STUDIO_DAILY_USD") or 100)
PER_CLIENT_DAILY = int(os.environ.get("STUDIO_PER_CLIENT_DAILY") or 5)
# workspaces the films-a-day count does not apply to ("o:<id>" or "u:<id>", comma separated): the
# operator's own account, named in the machine's .env and never in the code. The day's budget
# (DAILY_USD) and the films-at-once limit still hold for them.
DAILY_EXEMPT = {
    clients.canon(c.strip())
    for c in (os.environ.get("STUDIO_DAILY_EXEMPT") or "").split(",")
    if c.strip()
}
# where a film's narrator may come from (narrator_of): KitCut's own voices, pinned or chosen by
# Claude; and, once STUDIO_OWN_VOICE=1, a person's own ElevenLabs voice through the site's relay
OWN_VOICE = os.environ.get("STUDIO_OWN_VOICE", "").strip() == "1"
VOICE_SOURCES = ("kitcut", "elevenlabs") if OWN_VOICE else ("kitcut",)
EL_MODELS = ("eleven_multilingual_v2", "eleven_v3", "eleven_turbo_v2_5", "eleven_flash_v2_5")
EL_JOBS_MAX = int(os.environ.get("STUDIO_EL_JOBS_MAX") or 4)  # one account's lines at once
EL_VOICE = re.compile(r"^[A-Za-z0-9]{16,32}$")
EL_GRANT = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
# how long a film waits for its person to fix their voice before it is put down (and refunded)
WAITING_DAYS = float(os.environ.get("STUDIO_WAITING_DAYS") or 7)
# films in the making per account: one, or what its plan allows (the site's X-At-Once; Pro: 2),
# never more than this
AT_ONCE_MAX = int(os.environ.get("STUDIO_AT_ONCE_MAX") or 2)
KEEP_S = 3600  # a finished film's events stay in memory this long; then they come from disk
# how long a stopping server waits for its films to write their records (shutdown()): well inside
# the unit's TimeoutStopSec, after which systemd kills whatever is left
SHUTDOWN_WAIT_S = 20

# ------------------------------------------------------------------ several servers (peers.py)
TICK_S = 1.0  # a server's beat: its heartbeat, the Stops meant for it, a successor to hand to
ADOPT_S = 30  # how often the leader looks for films nobody alive is making, and reaps the dead
LEAD_WAIT_S = 30  # how long a new film waits for a leader (a handover takes a second or two)
# A film whose record names no server at all is from before records named one: the one-time move
# to several servers. The server that made it lets go of the port before its shutdown() has put
# its films down (up to SHUTDOWN_WAIT_S), so such a film is adopted only once this server has
# been serving this long -- not raced for while its old server is still recording it.
LEGACY_GRACE_S = SHUTDOWN_WAIT_S + 10
MODE = "starting"  # this server's, as its heartbeat says: peers.MODES
LEADER = asyncio.Event()  # set while this server leads and has adopted what it found
MANAGED = False  # run by serve(), which begins once it is listening (else by a test harness)
# serve()'s and the tick's moving parts: the tick task, the event that ends serve(), the runner
# and its site, when serving began (monotonic), when the leader last adopted
LIFE = {"ticker": None, "stop": None, "runner": None, "site": None, "since": None, "adopted": 0.0}
# EADDRINUSE; Windows says WSAEADDRINUSE
BUSY = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)}


# ------------------------------------------------------------------ the token
def ensure_token():
    """STUDIO_TOKEN from the studio's .env, created and saved there on first start (never
    printed). The file is the working tree's, never a release's. Under systemd (STUDIO_INSTANCE
    set) it is never created: two instances starting together would each append a token of their
    own, and the site would hold neither."""
    tok = procs.secret("STUDIO_TOKEN")
    if not tok and os.environ.get("STUDIO_INSTANCE", "").strip():
        sys.exit(
            "STUDIO_TOKEN is not set: put it in the studio's .env once (see studio/deploy/README.md);"
            " a server started by systemd never writes one"
        )
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
    """Who asks: the workspace (or the person, or the IP) the public site forwards (trusted: the
    request carries the token), else the IP Cloudflare saw, else this machine. A workspace and
    its person's old name are one owner: compare with clients.same, never ==."""
    return (
        req.headers.get("X-Client-Ip", "")[:64]
        or req.headers.get("Cf-Connecting-Ip")
        or ("local" if from_this_machine(req) else req.remote)
    )


def narrator_of(v):
    """A film request's `voice`, checked: (narrator or None, error or None). The sources this
    studio knows are in limits_doc()["voice"], so the site offers no other."""
    if v is None:
        return None, None
    if not isinstance(v, dict) or v.get("source") not in VOICE_SOURCES:
        return None, "voice: the source must be one of %s" % ", ".join(VOICE_SOURCES)
    if v["source"] == "elevenlabs":
        if not (
            EL_VOICE.match(str(v.get("voice") or ""))
            and v.get("model") in EL_MODELS
            and EL_GRANT.match(str(v.get("grant") or ""))
        ):
            return None, "voice: an ElevenLabs voice needs its voice id, a model and its grant"
        try:
            jobs = max(1, min(int(v.get("jobs") or 2), EL_JOBS_MAX))
            chars = max(0, int(v.get("chars") or 0))
        except (TypeError, ValueError):
            return None, "voice: jobs and chars are numbers"
        return {
            "source": "elevenlabs",
            "voice": v["voice"],
            "model": v["model"],
            "jobs": jobs,
            "chars": chars,
            "grant": v["grant"],
        }, None
    if v.get("voice") is None:
        return None, None  # KitCut chooses
    if v["voice"] not in validate.VOICES:
        return None, "voice: not one of KitCut's voices"
    return {"source": "kitcut", "voice": v["voice"]}, None


def uploader_of(req):
    """Whose uploads a request sees: the person who asked (X-Member), else the client -- so the
    members of one workspace never see each other's voice notes, and an upload made before the
    site sent workspaces is still its person's after."""
    return clients.member_of(req.headers) or client_of(req)


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
async def bye(req, handler):
    """A server that has handed over (handoff()) answers what still reaches it on a connection the
    tunnel already holds, and tells the client to close that connection after the reply, so its
    next request opens a new one and reaches the new server. Closing the connections from this
    side instead (aiohttp's pre_shutdown) can cut a request already in flight on one: seen at
    every switch on 2026-09-28 as a single request hanging ~5 s through the tunnel, while 398
    requests straight to the port in the same switch all answered in 2 ms."""
    try:
        resp = await handler(req)
    except web.HTTPException as e:
        if MODE == "handed_off":
            e.force_close()
        raise
    if MODE == "handed_off":
        resp.force_close()
    return resp


@web.middleware
async def need_token(req, handler):
    p = req.path
    guarded = p.startswith(("/api/", "/files/")) and p not in ("/api/health", "/api/limits")
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


def site_auth():
    """How the films asked for through the tunnel (the site, the MCP server) pay for Claude:
    STUDIO_SITE_AUTH, "login" by default (this machine's Claude login; a film that runs out of
    the plan carries on on the key, agent.PlanLimit) or "api" (the key, per token). Read per
    film, so the switch needs no restart."""
    return "api" if os.environ.get("STUDIO_SITE_AUTH", "").strip() == "api" else "login"


def reserve(seconds, auth="api"):
    """What a film being made may still spend, held against the day's budget: all of it on the
    key; on this machine's login only the voice and the paintings are paid for."""
    return films.limits(seconds)["reserve_usd"] if auth == "api" else 0.01 * seconds


def live(status=("queued", "running")):
    """This server's films in the making. One a drain sent back to the queue says queued but has
    ended here: the next server makes it."""
    return [j for j in JOBS.values() if j["status"] in status and not j.get("ended")]


def prune():
    """Forget finished films' events after a while (the page then reads them from disk), and
    the uploads no film took within a day."""
    now = time.time()
    for jid in [k for k, j in JOBS.items() if j.get("ended") and now - j["ended"] > KEEP_S]:
        JOBS.pop(jid, None)
    uploads.prune(now)


# ------------------------------------------------------------------ the other servers
def mine():
    """This server's films in the making, as its heartbeat tells the others (peers.heartbeat)."""
    return [
        {
            "id": jid,
            "client": J["client"],
            "status": J["status"],
            "reserve": J["reserve"],
            "cost_usd": J.get("cost_usd") or 0,
        }
        for jid, J in JOBS.items()
        if J["status"] in ("queued", "running") and not J.get("ended")
    ]


def everyone(status=("queued", "running"), others=None):
    """The films in the making on this server and on every live peer (their heartbeats, a tick
    old at most): a person's films at once, the queue and the day's budget are the machine's, not
    one server's. A handed-off peer counts too -- it is still making its films."""
    out = {}
    for b in peers.peers() if others is None else others:
        for j in b.get("jobs") or []:
            if isinstance(j, dict) and j.get("id") and j.get("status") in status:
                out[j["id"]] = j
    for jid in JOBS:  # what this server knows of its own films wins over any heartbeat
        out.pop(jid, None)
    out.update((j["id"], j) for j in mine() if j["status"] in status)
    return list(out.values())


def usage():
    """The machine slots this server holds, and wants next, for its heartbeat."""
    u = getattr(SCHED, "usage", None)
    if u is not None:
        return u()
    # a scheduler without usage() (sched.py before peer capacity): the same, read off its pools
    return {
        name: {"used": p.used, "want": p.waiting[0][0] if p.waiting else 0}
        for name, p in SCHED.pools.items()
    }


def transcribing():
    """The voice notes this server is writing out (uploads.py), for its heartbeat."""
    f = getattr(uploads, "in_flight", None)
    if f is not None:
        return list(f())
    return [uid for uid, t in uploads.TASKS.items() if not t.done()]


def beat():
    """This server's heartbeat (peers.heartbeat): what the others count and wait for."""
    peers.heartbeat(
        MODE,
        leader=peers.leads(),
        jobs=mine(),
        slots=usage(),
        sends=youtube.in_flight(),
        drafts=ytdraft.in_flight(),
        transcribing=transcribing(),
    )


async def feed(others):
    """What the peers hold of the machine, for this server's scheduler (sched.Sched.set_peers):
    every live peer's slots in use, and the next wants only of the peers that started before this
    one -- so the old server's last renders go first, and two servers never each wait for the
    other."""
    set_peers = getattr(SCHED, "set_peers", None)
    if set_peers is None:
        return
    me = (peers.STARTED, os.getpid())
    total = {name: {"used": 0, "want": 0} for name in SCHED.pools}
    for b in others:
        older = (b.get("started") or "", b.get("pid") or 0) < me
        for name, s in (b.get("slots") or {}).items():
            if name in total and isinstance(s, dict):
                total[name]["used"] += int(s.get("used") or 0)
                if older:
                    total[name]["want"] += int(s.get("want") or 0)
    await set_peers(total)


def peer_has(kind, key):
    """Is a live peer in the middle of this -- a YouTube send ("sends", its key) or a draft
    ("drafts", [film, channel]) -- by its heartbeat? Both live in the memory of the server that
    started them, so another must not start the same one over."""
    return any(key in (b.get(kind) or []) for b in peers.peers())


def idle():
    """Nothing of this server's own is left: no film, send, draft or voice note in progress."""
    return (
        not any(J.get("task") is not None and not J["task"].done() for J in JOBS.values())
        and not youtube.in_flight()
        and not ytdraft.in_flight()
        and not share.in_flight()
        and not transcribing()
    )


def waiting_for_slot(jid, J):
    """Is this film still waiting for its Claude slot -- nothing started, nothing spent? Its
    record says queued until the moment it has the slot: make_film writes "claude" before it next
    yields, so a film cancelled while its record says queued stays queued (make_film's
    CancelledError branch). The scheduler's own line would miss a film whose task has yet to run."""
    if J["status"] != "queued" or J.get("ended") or J.get("task") is None or J["task"].done():
        return False
    f = Film.open(jid)
    return f is not None and f.state == "queued"


# ------------------------------------------------------------------ running a film
def start(film, finish_only=False, resume=None):
    """Make the film in the background; its events go to memory and its events.jsonl. The film's
    record names this server as its maker from now on (peers.owner_alive)."""
    peers.hold_own()
    film.update(server=peers.SERVER_ID)
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
        elif ev["type"] == "fallback":
            # the login failed and the film is being made on the key (agent.make_film): from here
            # it is held against the day's budget as a film on the key
            J["auth"], J["reserve"] = "api", reserve(film.length, "api")

    async def run():
        ok = False
        try:
            # done/error only once make_film returns: by then studio.json and
            # kitcut.studio_runs hold the final cost
            # a film that waited for its person's voice (continue_film) picks its session up
            again = {}
            if resume == "voice" and film.mode != "scenes":
                again = {"resume": True, "resume_prompt": agent.RESUME_VOICE}
            r = await agent.make_film(
                film,
                emit,
                SCHED,
                auth=J["auth"],
                finish_only=finish_only,
                control=J["control"],
                **again,
            )
            ok = r.get("ok")
            J["status"] = "waiting" if r.get("waiting") else "done" if ok else "error"
            if ok:  # its moments sheet now, so a YouTube draft does not wait for it
                thumbs.premake(film)
                share.premake(film)  # its share page's title and picture (never raises)
        except asyncio.CancelledError:
            c = J["control"]  # drain() requeued it; shutdown() stopped it; else its person did
            J["status"] = (
                "queued" if c.get("requeue") else "error" if c.get("shutdown") else "cancelled"
            )
        except Exception as e:  # noqa: BLE001 -- make_film reports its own; this is the backstop
            emit({"type": "error", "text": str(e)})
            J["status"] = "error"
        J["ended"] = time.time()

    def over(task):
        # cancelled before it ever ran (a handover or a shutdown right after it was started):
        # run() never began, so nothing above said where the film stands
        if J["ended"] is None:
            c = J["control"]
            J["status"] = "queued" if c.get("requeue") or c.get("shutdown") else "cancelled"
            J["ended"] = time.time()

    J["task"] = asyncio.create_task(run())
    J["task"].add_done_callback(over)
    return J


def orphans():
    """The films nobody alive is making, oldest first (so the queue keeps its order): (film,
    record) of each one queued, being finished or being written whose record names no live
    server. Forgets the Stops meant for films that are over. Reads every film's record, so it
    runs off the event loop."""
    young = time.monotonic() - (LIFE["since"] or 0) < LEGACY_GRACE_S
    flags = set()
    with contextlib.suppress(OSError):
        flags = set(os.listdir(peers.CANCELS))
    out = []
    for f in reversed(Film.all()):
        if f.legacy:
            continue
        rec = f.record()
        if rec.get("state") not in films.ACTIVE:
            if f.id in flags:  # pressed as it ended: nothing left to stop
                peers.drop_cancel(f.id)
            continue
        if peers.owner_alive(rec):
            continue
        if "server" not in rec and young:  # LEGACY_GRACE_S
            continue
        out.append((f, rec))
    return out


async def adopt(app=None):
    """The leader's: the films nobody alive is making (in this home only) -- a crashed server's,
    the ones a handover or a shutdown sent back to the queue, the ones left from before several
    servers. A queued one is made, one left being mixed or rendered is finished, one Claude was
    writing when its server died is marked interrupted, and one its person asked to stop meanwhile
    is recorded cancelled. Replaces the start-up recover() of a single server; runs when this
    server takes the lead, then every ADOPT_S. Under ADMIT: create() cannot be half-way through
    making a film (on disk, not yet started) while this looks."""
    if not peers.leads() or DRAINING or MODE != "serving":
        return
    async with ADMIT:
        for f, _ in await asyncio.to_thread(orphans):
            # read again here, on the loop: the scan ran beside it, and a record it read may have
            # moved on since (a film being set up, a maker that has just taken it)
            rec = f.record()
            st = rec.get("state")
            if f.id in JOBS or st not in films.ACTIVE or peers.owner_alive(rec):
                continue
            if peers.cancel_requested(f.id):
                await put_down(f, "cancelled", "cancelled", "The film was cancelled.")
                peers.drop_cancel(f.id)
            elif st == "queued":
                # Continued from waiting, and not started before this server went: it picks up
                start(f, resume=(rec.get("resume") or {}).get("why"))
            elif st == "finishing":
                start(f, finish_only=True)
            elif st == "claude" and f.mode == "scenes" and rec.get("carried_on", 0) < 3:
                # a film made in scenes keeps its finished passes (scenes.py): it goes on from the
                # first one not done, and only the pass that was under way is written again
                f.update(carried_on=rec.get("carried_on", 0) + 1)
                last_word(
                    f,
                    {
                        "type": "fail",
                        "text": "The studio restarted; it carries on from the scene it was on.",
                    },
                )
                start(f)
            elif st == "claude":
                why = "the studio restarted while Claude was working on it"
                await put_down(f, "interrupted", why, agent.INTERRUPTED)

    # the films that waited too long for their person's voice: put down, their credits back
    for f in await asyncio.to_thread(overdue):
        await put_down(
            f,
            "error",
            "waited %g days for its narrator's voice" % WAITING_DAYS,
            "This film waited %g days for its narrator's voice and was stopped. Its credits are "
            "back; make it again once the voice works." % WAITING_DAYS,
        )


def overdue():
    """The films waiting for their person's voice (state waiting) for more than WAITING_DAYS."""
    out, now = [], datetime.now()
    for f in Film.all():
        if f.legacy or f.state != "waiting":
            continue
        since = (f.record().get("waiting") or {}).get("since")
        with contextlib.suppress(TypeError, ValueError):
            if (now - datetime.fromisoformat(since)).total_seconds() > WAITING_DAYS * 86400:
                out.append(f)
    return out


recover = adopt  # its name before several servers


async def put_down(f, state, why, said):
    """The end of a film no server is making: its record (studio.json and kitcut.studio_runs,
    where the site settles its credits) and a last line on its page, which otherwise shows its log
    stopping mid-sentence."""
    f.update(
        state=state, ok=False, error=why, finished=datetime.now().isoformat(timespec="seconds")
    )
    last_word(f, {"type": "error", "text": said})
    # the site settles on its own names (sketch-studio lib/credits.js): an error is "failed"
    settled = {"error": "failed"}.get(state, state)
    await agent.save(
        f.id, {"state": settled, "ok": False, "error": why, "finished_at": store.now()}, final=True
    )


def last_word(film, ev):
    """One more line on the log of a film no server is making (its time: the log's last)."""
    log = film.path("events.jsonl")
    t = 0.0
    with contextlib.suppress(OSError, ValueError, IndexError, KeyError):
        with open(log, encoding="utf-8") as f:
            t = json.loads([x for x in f if x.strip()][-1])["t"]
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({**ev, "t": t}, ensure_ascii=False) + "\n")


async def shutdown(app):
    """systemd is stopping the server (a restart, a ship, a reboot): every film being made is told
    why before it is cancelled, so it is recorded interrupted, or left finishing for the next
    server to mix and render, or left queued -- not cancelled, which is its person pressing Stop.
    Until 2026-09-29 a restart and a Stop were the same bare cancel, and a ship's restart recorded
    a paying film as cancelled by its person (docs/known-issues.md KI-031). The films' own records
    are written before this returns (make_film's finally), inside the unit's TimeoutStopSec."""
    tasks = []
    for J in live(("queued", "running")):
        J["control"]["shutdown"] = True
        J["task"].cancel()
        tasks.append(J["task"])
    if tasks:
        await asyncio.wait(tasks, timeout=SHUTDOWN_WAIT_S)


# ------------------------------------------------------------------ a server's life among others
async def tick():
    """One beat (every TICK_S): the heartbeat; the peers' hold on the machine for the scheduler;
    the Stops pressed for this server's films on pages another server answered; the lead, when
    this server is current, serving and nobody holds it (then everything left is adopted); every
    ADOPT_S while leading, what died since; a handover once the current instance serves; and,
    handed over, leaving once nothing of its own is left."""
    others = peers.peers()
    beat()
    await feed(others)
    for jid in peers.take_cancels([j["id"] for j in mine()]):
        print("film %s: stopped from another server's page" % jid, flush=True)
        JOBS[jid]["task"].cancel()  # as the cancel route does: its person's Stop
    if MODE == "serving" and peers.is_current() and not peers.leads():
        if peers.try_lead():
            print("studio %s leads" % peers.SERVER_ID, flush=True)
            await adopt()
            LIFE["adopted"] = time.monotonic()
            LEADER.set()
            beat()
    elif peers.leads() and time.monotonic() - LIFE["adopted"] > ADOPT_S:
        LIFE["adopted"] = time.monotonic()
        await adopt()
        await asyncio.to_thread(peers.reap)
    if MODE == "serving" and peers.successor() is not None:
        await handoff()
    elif MODE == "handed_off" and idle() and LIFE["stop"] is not None:
        print("studio %s: handed over, its films made; leaving" % peers.SERVER_ID, flush=True)
        LIFE["stop"].set()


async def ticker():
    while True:
        try:
            await tick()
        except Exception as e:  # noqa: BLE001 -- a bad beat must not stop the next one
            print("tick: %s: %s" % (type(e).__name__, e), file=sys.stderr, flush=True)
        await asyncio.sleep(TICK_S)


async def handoff():
    """The instance `current` names is serving: this server takes no more films. Those still
    waiting for a Claude slot go back to the queue with no maker, for the new leader (a film that
    has its slot keeps it: cancelling it would record it cancelled); this server's heartbeat says
    so at once, so the new leader's limits count exactly what is left here; then it lets go of
    the lead and of the port, and has bye() close each connection after its next reply so the tunnel's requests reach
    the new server (bye()). The films it is making it finishes; then tick() sees it idle and it exits."""
    global MODE
    async with ADMIT:
        MODE = "handed_off"
        LEADER.clear()
        moved = [jid for jid, J in JOBS.items() if waiting_for_slot(jid, J)]
        for jid in moved:
            JOBS[jid]["control"]["requeue"] = True
            JOBS[jid]["task"].cancel()
        if moved:
            await asyncio.wait([JOBS[jid]["task"] for jid in moved], timeout=SHUTDOWN_WAIT_S)
        for jid in moved:
            f = Film.open(jid)
            if f is not None and f.state == "queued":
                f.update(server=None)
            JOBS.pop(jid, None)  # the new leader's now: counted twice otherwise
        beat()
        peers.resign()
        beat()
    print(
        "studio %s handed over to %s: %d film(s) back in the queue, %d still being made here"
        % (peers.SERVER_ID, peers.current(), len(moved), len(live())),
        flush=True,
    )
    site, LIFE["site"] = LIFE["site"], None
    if site is not None:
        await site.stop()
    # the connections the tunnel holds stay open here until their next request, which bye() answers
    # and then closes (or aiohttp's keep-alive timeout does): none is cut with a request on it


def begin():
    """This server is listening: from now on it beats, and leads when it may (tick())."""
    global MODE
    peers.hold_own()
    MODE = "serving"
    LIFE["since"] = time.monotonic()
    beat()
    if LIFE["ticker"] is None:
        LIFE["ticker"] = asyncio.create_task(ticker())


async def on_start(app):
    # serve() begins once it has the port; a test harness (aiohttp's TestServer, which listens
    # on a free port straight after) begins here, as a single server
    if not MANAGED:
        begin()


async def end(app=None):
    """The app is cleaned up (the server is exiting, or a test harness closed it): the beat stops
    and this server leaves the others' view (peers.leave)."""
    t, LIFE["ticker"] = LIFE["ticker"], None
    if t is not None and t is not asyncio.current_task():
        t.cancel()
        await asyncio.wait([t])
    LEADER.clear()
    peers.leave()


async def bind(runner, port, stop):
    """Listen on 127.0.0.1:port -- beside the other servers there with SO_REUSEPORT (Linux; the
    kernel spreads new connections over every listener) -- or wait while a server that did not
    ask for it holds the port, trying every 0.2 s for as long as it takes: a server from before
    several servers, which the one-time move replaces. The site, or None when stopped first."""
    reuse = hasattr(socket, "SO_REUSEPORT") and sys.platform != "win32"
    told = False
    while not stop.is_set():
        site = web.TCPSite(runner, "127.0.0.1", port, reuse_port=reuse or None)
        try:
            await site.start()
        except OSError as e:
            with contextlib.suppress(RuntimeError):
                await site.stop()  # it joined the runner's sites before it failed
            if e.errno not in BUSY:
                raise
            if not told:
                print("port %d is taken; waiting for it" % port, flush=True)
                told = True
            await asyncio.sleep(0.2)
            continue
        LIFE["site"] = site
        return site
    return None


async def serve(port, token):
    """One server's life: its lock and a heartbeat saying it is starting, the port (bind()),
    serving and the tick, until SIGTERM (Linux; Ctrl-C on Windows) or, handed over, until its own
    films are made. Then it stops listening, tells its films why they stop (shutdown()), stops
    the beat and leaves (end()). Returns the exit status."""
    global MANAGED, MODE
    MANAGED = True
    peers.hold_own()
    MODE = "starting"
    beat()
    stop = LIFE["stop"] = asyncio.Event()
    # a short wait for open requests (page polls) at the end, so the films' records are written
    # well inside the unit's TimeoutStopSec rather than cut off by its SIGKILL
    runner = LIFE["runner"] = web.AppRunner(make_app(token), shutdown_timeout=5)
    await runner.setup()
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    try:
        if await bind(runner, port, stop):
            print(
                "Sketch Studio on http://127.0.0.1:%d  (code %s, home %s, server %s)"
                % (port, films.RELEASE, films.HOME, peers.SERVER_ID),
                flush=True,
            )
            begin()
            await stop.wait()
    except asyncio.CancelledError:  # Ctrl-C on Windows: asyncio.run cancels this task
        task = asyncio.current_task()
        if task is not None and hasattr(task, "uncancel"):
            task.uncancel()
    MODE = "stopping"
    LEADER.clear()
    peers.resign()  # a successor, or the next server, may lead and adopt what this one leaves
    with contextlib.suppress(Exception):
        beat()
    # the site, the idle connections, shutdown() (the films told why), then end() (the beat)
    await runner.cleanup()
    return 0


# ------------------------------------------------------------------ routes
async def index(req):
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        page = f.read()
    page = page.replace("__TOKEN__", TOKEN if from_this_machine(req) else "")
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


async def people_row(req):
    """The People row index.html draws with (the site's people-row.js, mirrored here beside it)."""
    return web.FileResponse(
        os.path.join(HERE, "people-row.js"), headers={"Cache-Control": "no-cache"}
    )


async def font(req):
    name = req.match_info["name"]
    if name not in ("Caveat.woff2", "PatrickHand-400.woff2", "Inter.woff2"):
        raise web.HTTPNotFound()
    return web.FileResponse(os.path.join(films.KIT, "fonts", name))


async def health(req):
    """The studio as a whole: every live server's films (with SO_REUSEPORT either server may
    answer, and both answer the same), and the release of the one that leads -- the one taking
    the new films."""
    others = peers.peers()
    making = everyone(others=others)
    running = sum(1 for j in making if j["status"] == "running")
    queued = len(making) - running
    lead = next((b for b in others if b.get("leader")), None)
    release = films.RELEASE if peers.leads() or lead is None else lead.get("release")
    own = sum(1 for j in mine() if j["status"] == "running")
    instances = [
        {"id": peers.SERVER_ID, "release": films.RELEASE, "mode": MODE}
        | {"leader": peers.leads(), "running": own}
    ] + [
        {k: b.get(k) for k in ("id", "release", "mode", "leader")}
        | {"running": sum(1 for j in b.get("jobs") or [] if j.get("status") == "running")}
        for b in others
    ]
    return web.json_response(
        {
            "ok": True,
            "busy": running >= SCHED["claude"].capacity,
            "running": running,
            "queued": queued,
            "active": running + (0 if DRAINING else queued),
            "slots": SCHED.snapshot(),
            "draining": DRAINING,
            "release": release,
            "server": peers.SERVER_ID,
            "instances": instances,
        }
    )


def limits_doc():
    """What a person can meet, in numbers: the site's docs are built from it (sketch-studio
    scripts/docs.mjs). Nothing about money: no budgets, reserves or costs."""
    sample = (10, 30, 60, 120, 240, 480)
    return {
        "release": films.RELEASE,
        "lengths": {"min": films.LENGTHS[0], "max": films.LENGTHS[-1], "step": 5},
        "looks": list(films.LOOKS),
        "prompt": {"max_chars": PROMPT_MAX, "min_chars": 3},
        # people drawn as talking characters (film.CAPS "people"): how many, and in what styles
        "people": {
            "per_film": films.MAX_PEOPLE,
            "styles": ["auto", *films.people_styles()],
            "auto": dict(films.PEOPLE_AUTO),
            "name_max_chars": films.PERSON_NAME_MAX,
        },
        "films": {
            "at_once_per_account": 1,
            "at_once_per_account_max": AT_ONCE_MAX,  # what a plan may allow (X-At-Once)
            "per_account_per_day": PER_CLIENT_DAILY,
            "waiting_max": MAX_QUEUE,
            "made_at_once": SCHED["claude"].capacity,
        },
        "attachments": {
            "pictures_per_film": uploads.MAX_IMAGES,
            "voice_notes_per_film": uploads.MAX_NOTES,
            "picture_types": ["jpeg", "png", "webp"],
            "voice_note_types": ["webm", "ogg", "mp4", "m4a", "wav", "mp3"],
            "picture_max_bytes": uploads.MAX_BYTES["image"],
            "picture_max_pixels": uploads.MAX_PIXELS,
            "voice_note_max_bytes": uploads.MAX_BYTES["audio"],
            "voice_note_max_seconds": uploads.MAX_AUDIO_S,
            "documents_per_film": uploads.MAX_DOCS,
            "document_types": ["txt", "md"],
            "document_max_bytes": uploads.MAX_BYTES["text"],
            "document_max_chars": uploads.MAX_TEXT_CHARS,
            "unused_kept_hours": uploads.KEEP_S // 3600,
            "per_account_per_day": {"files": uploads.DAY_FILES, "bytes": uploads.DAY_BYTES},
        },
        # what a narrator can be (the site's voice setting): the sources, and KitCut's voices
        "voice": {
            "sources": list(VOICE_SOURCES),
            "kitcut_voices": list(validate.VOICES),
            "elevenlabs": {
                "models": list(EL_MODELS),
                "jobs_max": EL_JOBS_MAX,
                "chars_per_second": 16,  # one full recording; the site adds its margin
                "waiting_days": WAITING_DAYS,
            },
        },
        "library": {
            "characters_per_new_film": library.SEEDED,
            "earlier_films_remembered": library.MEMORY,
            "versions_kept": library.KEEP,
            "project_pictures": library.PICTURES,
            "project_voice_lines": library.VOICE_LINES,
        },
        "by_length": {
            str(n): {
                "claude_minutes": films.limits(n)["claude_s"] // 60,
                "paintings": films.limits(n)["images"],
                "cutouts": films.limits(n)["cutouts"],  # a collage film's (film.CAPS)
                "narration_lines": films.limits(n)["lines"],
            }
            for n in sample
        },
        "output": {
            "width": 1920,
            "height": 1080,
            "fps": 60,  # a paid plan's; a Free film renders at fps_free (X-Fps from the site)
            "fps_free": 30,
            "video": "H.264 (MP4)",
            "audio": "AAC, stereo, -14 LUFS",
            "subtitles": "a soft track, off by default; also film.srt and film.vtt",
            "free_closing_seconds": 3,
        },
    }


async def limits_route(req):
    return web.json_response(limits_doc())


def at_once_of(req):
    """How many films the asker may have in the making at once: its plan's (the site sends
    X-At-Once, trusted like X-Client-Ip), else one; never more than AT_ONCE_MAX."""
    try:
        n = int(req.headers.get("X-At-Once", "").strip() or 1)
    except ValueError:
        n = 1
    return max(1, min(n, AT_ONCE_MAX))


async def over_limit(client, seconds, auth="api", at_once=1, others=None):
    """Why this request must wait (for now, or until tomorrow), or None. Today is local time.
    Nothing is refused to this machine itself except by the budget. The films being made count
    on every live server (others: their heartbeats, else read now)."""
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = await asyncio.to_thread(agent.STORE.runs, None, midnight)
    except Exception:  # noqa: BLE001 -- no record, no public spending
        if client == "local":
            return None
        return "The studio cannot check today's budget right now; please try again later."
    making_all = everyone(others=others)
    # a film still being made may spend its reserve (by its length: film.limits) beyond what its
    # record shows so far; the new one is held at its own
    reserved = sum(max(0.0, (j.get("reserve") or 0) - (j.get("cost_usd") or 0)) for j in making_all)
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    if spent + reserved + reserve(seconds, auth) > DAILY_USD:
        return "Today's budget ($%.0f) is used up. Please try again tomorrow." % DAILY_USD
    if client == "local":
        return None
    making = sum(1 for j in making_all if clients.same(j.get("client"), client))
    if making >= at_once:
        if making == 1:
            return "You already have a film in the making; wait for it to finish (or cancel it)."
        return (
            "You already have %d films in the making; wait for one to finish (or cancel it)."
            % making
        )
    mine = sum(1 for r in rows if clients.same(r.get("client"), client) and r.get("kind") == "film")
    if mine >= PER_CLIENT_DAILY and clients.canon(client) not in DAILY_EXEMPT:
        return "That is %d films today, the limit for now. Please try again tomorrow." % mine
    return None


RESTARTING = "The studio is restarting; try again in a minute."


async def leading():
    """Whether this server may admit a film: it leads, and has adopted what it found. A server
    not (yet) leading waits up to LEAD_WAIT_S for it -- a handover takes a second or two -- and a
    handed-over or stopping one never will."""
    if MODE != "serving" or DRAINING:
        return False
    if not LEADER.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(LEADER.wait(), LEAD_WAIT_S)
    return LEADER.is_set() and peers.leads() and MODE == "serving" and not DRAINING


def template_of(body, local):
    """A film asked for from a template: {"template": {"id", "version"}, "prompt": "...",
    "attachments": [...], "frame": "16:9"} -- what the person wants in their own words, the
    template its example. Returns (template, frame, None) or (None, None, (error body, status)).
    A draft is this machine's to try; the rest is live versions only."""
    want = body.get("template")
    if not isinstance(want, dict) or not isinstance(want.get("id"), str):
        return None, None, ({"error": "template must be {id, version}"}, 400)
    status = ("live", "draft") if local else ("live",)
    t = templates.load(want["id"], want.get("version"), status)
    if t is None:
        latest = templates.load(want["id"], None, status)
        if latest is not None:  # an older version, retired: the page must be loaded again
            return (
                None,
                None,
                (
                    {"error": "template changed", "version": latest["version"]},
                    409,
                ),
            )
        return None, None, ({"error": "no such template"}, 404)
    if body.get("people") or body.get("project"):  # music only, and the template's own film
        return None, None, ({"error": "a template's film takes a prompt and attachments"}, 400)
    frame = body.get("frame") or t["frames"][0]
    if frame not in t["frames"]:
        return None, None, ({"error": "frame is one of %s" % ", ".join(t["frames"])}, 400)
    return t, frame, None


async def create(req):
    if DRAINING or MODE != "serving":
        return web.json_response({"error": RESTARTING}, status=503)
    try:
        body = await req.json()
    except ValueError:
        return web.json_response({"error": 'send JSON: {"prompt": "..."}'}, status=400)
    prompt = str(body.get("prompt", "")).strip()[:PROMPT_MAX]
    tpl = frame = None
    if body.get("template") is not None:  # a remake of a template, as asked (templates.py)
        tpl, frame, err = template_of(body, from_this_machine(req))
        if err:
            return web.json_response(err[0], status=err[1])
        body = dict(body, seconds=tpl["seconds"], look=tpl.get("look"))
    ids = body.get("attachments") or []
    # people to draw as talking characters: [{"upload": "up-...", "name": "Alex"}] (photos
    # uploaded first, like pictures), and the style they are drawn in ("auto": the look's own)
    people = body.get("people") or []
    if (
        not isinstance(people, list)
        or len(people) > films.MAX_PEOPLE
        or not all(isinstance(p, dict) and isinstance(p.get("upload"), str) for p in people)
        or len({p["upload"] for p in people}) != len(people)
    ):
        return web.json_response(
            {"error": 'people must be at most %d of {"upload", "name"}' % films.MAX_PEOPLE},
            status=400,
        )
    style = body.get("character_style") or "auto"
    if style != "auto" and style not in films.people_styles():
        return web.json_response(
            {
                "error": "character_style must be auto or one of %s"
                % ", ".join(films.people_styles())
            },
            status=400,
        )
    if len(prompt) < 3 and not ids and not people:
        return web.json_response({"error": "write a prompt"}, status=400)
    try:
        seconds = int(body.get("seconds") or films.LENGTHS[0])
    except (TypeError, ValueError):
        seconds = 0
    if seconds not in films.LENGTHS and not tpl:  # a template's own length may be any
        return web.json_response(
            {"error": "seconds must be one of %s" % ", ".join(map(str, films.LENGTHS))},
            status=400,
        )
    look = body.get("look") or films.LOOKS[0]
    if look not in films.LOOKS:
        return web.json_response(
            {"error": "look must be one of %s" % ", ".join(films.LOOKS)}, status=400
        )
    # the site's project the film is an episode of: {id, name, brief, from_account_cast}. The
    # site checks it is the person's (trusted like X-Client-Ip); its library is theirs anyway
    project = body.get("project")
    if project is not None:
        if not isinstance(project, dict) or not films.PROJECT_ID.match(str(project.get("id"))):
            return web.json_response({"error": "project must be {id, name, brief}"}, status=400)
        project = {
            "id": project["id"],
            "name": " ".join(str(project.get("name") or "").split())[:80] or "Untitled",
            "brief": str(project.get("brief") or "").strip()[: films.BRIEF_MAX],
            "from_account_cast": project.get("from_account_cast") is True,
        }
    # the narrator the person picked (the site's voice setting, kitcut.ai lib/narrator.js):
    # {"source": "kitcut", "voice": <a Gemini voice>} pins that voice (film.vo_pins); none, or
    # no voice in it, and Claude picks as ever
    narrator, err = narrator_of(body.get("voice"))
    if err:
        return web.json_response({"error": err}, status=400)
    client = client_of(req)
    # who asked (a member of the client's workspace), and whose uploads it may attach: a person's
    # own, so a team's members never see each other's voice notes (clients.py)
    member = clients.member_of(req.headers)
    uploader = member or client
    # a plan whose films go first (the site sends it, trusted like X-Client-Ip)
    priority = 1 if req.headers.get("X-Priority", "").strip() == "1" else 0
    # a plan that lets an account make more than one film at a time (Pro: 2)
    at_once = at_once_of(req)
    # this machine's own films (tests, internal runs) are made on its Claude Code login unless
    # they ask for the key ("auth": "api"); anyone through the tunnel as site_auth() says. A
    # machine with no login of its own sets STUDIO_LOCAL_AUTH=api.
    local = "api" if body.get("auth") == "api" else os.environ.get("STUDIO_LOCAL_AUTH") or "login"
    auth = local if from_this_machine(req) else site_auth()
    # a Free-plan film gets KitCut's watermark and closing (the site sends it, trusted like
    # X-Priority; this machine may ask for it to try it)
    branding = req.headers.get("X-Branding", "").strip() == "1" or (
        body.get("branding") is True and from_this_machine(req)
    )
    # link-only: kept out of the gallery (and the site's sitemap), still watchable by its link
    listed = body.get("listed") is not False
    # the preview: the film as it stands, to watch while it is made (tools.py PREVIEW; the site
    # sends it, trusted like X-Priority; this machine may ask for it to try it)
    preview = req.headers.get("X-Preview", "").strip() == "1" or (
        body.get("preview") is True and from_this_machine(req)
    )
    # where the request came from: the site's own page, or an assistant through its MCP server
    # (the site sends both, trusted like X-Priority)
    source = "mcp" if req.headers.get("X-Source", "").strip() == "mcp" else "web"
    app = req.headers.get("X-App", "").strip()[:40] or None
    # the frame rate the film renders at: the plan's (the site sends it, trusted like X-Priority:
    # Free films are 30 fps, paid ones 60); 60 unless it says 30
    fps = 30 if req.headers.get("X-Fps", "").strip() == "30" else 60
    prune()
    # only the leader admits films (peers.py): during a handover this waits the second or two it
    # takes for the new server to lead
    if not await leading():
        return web.json_response({"error": RESTARTING}, status=503)
    # pictures and voice notes uploaded first (uploads.py): this client's own, and every voice
    # note written out -- which may take a moment, so before the lock
    try:
        # a template's film may take its own number of pictures (a line-up of speakers)
        cap = tpl["limits"]["images"] if tpl else None
        attached = await uploads.take(uploader, ids, cap) if ids else []
        faces = await uploads.take(uploader, [p["upload"] for p in people]) if people else []
    except uploads.UploadError as e:
        return web.json_response(e.body(), status=e.status)
    for a in attached + faces:
        a["src"] = uploads.file_of(uploader, a)
    for a, p in zip(faces, people, strict=True):
        if a["kind"] != "image":
            return web.json_response(
                {"error": "a person must be a photo", "id": a["id"]}, status=400
            )
        a["person"] = " ".join(str(p.get("name") or "").split())[: films.PERSON_NAME_MAX]
    # the check and the taking happen under one lock: two requests at the same moment cannot
    # both slip under a limit that has room for one
    async with ADMIT:
        if not peers.leads() or MODE != "serving" or DRAINING:  # handed over while it waited
            return web.json_response({"error": RESTARTING}, status=503)
        others = peers.peers()  # the films the other live servers are making count too
        if len(everyone(("queued",), others)) >= MAX_QUEUE:
            return web.json_response({"error": "the queue is full; try again later"}, status=429)
        refused = await over_limit(client, seconds, auth, at_once, others)
        if refused:
            return web.json_response({"error": refused}, status=429)
        # an account that may make two at once can send the same upload twice: the film admitted
        # first takes it (release, below), and this one must not start without it
        gone = next((a for a in attached + faces if uploads.get(uploader, a["id"]) is None), None)
        if gone:
            e = uploads.UploadError(
                409, "attachment", "An attachment is no longer here; add it again.", gone["id"]
            )
            return web.json_response(e.body(), status=e.status)
        f = Film.create(
            prompt,
            seconds,
            look,
            client=client,
            source=source,
            priority=priority,
            auth=auth,
            branding=branding,
            attachments=attached,
            project=project,
            listed=listed,
            app=app,
            fps=fps,
            people=faces,
            character_style=style,
            member=member,
            narrator=narrator,
            template=tpl,
            frame=frame,
        )
        if preview:
            f.update(preview=True)
        if tpl:  # its code and its own sample, the starting point (templates.seed)
            await asyncio.to_thread(templates.seed, f, tpl)
        uploads.release(uploader, attached + faces)  # the film has its own copies now
        try:  # the person's cast and earlier films (library.py); a film goes ahead without
            if not tpl:  # a remake keeps to its template, not to the person's other films
                await asyncio.to_thread(library.seed, f)
        except Exception as e:  # noqa: BLE001
            print("film %s: no library: %s" % (f.id, e), file=sys.stderr, flush=True)
        await agent.save(f.id, agent.first_record(f, source, client))
        if faces:  # the people are drawn while Claude plans; its picture tools wait for them
            agent.draw_people_soon(f)
        start(f)
    await asyncio.sleep(0)  # let it take a free slot now, so the answer says whether it waits
    ahead = SCHED["claude"].ahead(f.id)
    return web.json_response(
        {
            "id": f.id,
            "status": "queued" if ahead is not None else "running",
            "position": (ahead + 1) if ahead is not None else 0,
            "status_url": "%s/api/films/%s" % (base_url(req), f.id),
            "attachments": [a["kind"] for a in attached],
            "people": len(faces),
            "listed": listed,
            **({"template": {"id": tpl["id"], "version": tpl["version"]}} if tpl else {}),
        },
        status=202,
    )


# ------------------------------------------------------------------ templates (templates.py)
PREVIEW_NAME = re.compile(r"sheet\.png|\d{3}\.\d{2}\.png")


def template_view(req, t):
    """A template as anyone may see it, with the addresses of its preview sheets."""
    out = templates.public(t)
    out["preview"] = {
        fr: "%s/api/templates/%s/%d/preview/%s/sheet.png"
        % (base_url(req), t["id"], t["version"], templates.fdir(fr))
        for fr in t["frames"]
    }
    return out


async def template_list(req):
    """Every live template, newest version of each."""
    return web.json_response({"templates": [template_view(req, t) for t in templates.live()]})


async def template_get(req):
    """One template's form: the latest live version, or ?version=N (a draft: this machine's)."""
    v = req.query.get("version")
    status = ("live", "draft") if from_this_machine(req) else ("live",)
    t = templates.load(req.match_info["id"], int(v) if v and v.isdigit() else None, status)
    if t is None:
        return web.json_response({"error": "no such template"}, status=404)
    return web.json_response(template_view(req, t))


async def template_preview(req):
    """A version's preview still or sheet (preview/<frame>/<name>.png): public once it is live."""
    status = ("live", "draft") if from_this_machine(req) else ("live",)
    m = req.match_info
    t = templates.load(m["id"], int(m["v"]) if m["v"].isdigit() else -1, status)
    if t is None or m["frame"] not in {templates.fdir(f) for f in t["frames"]}:
        return web.json_response({"error": "not found"}, status=404)
    if not PREVIEW_NAME.fullmatch(m["name"]):
        return web.json_response({"error": "not found"}, status=404)
    p = os.path.join(t["_dir"], "preview", m["frame"], m["name"])
    if not os.path.isfile(p):
        return web.json_response({"error": "not found"}, status=404)
    return web.FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


async def upload(req):
    """One picture, voice note or document, as raw bytes (uploads.py; a document may add
    ?name=): its id, kind and state."""
    if DRAINING or MODE == "stopping":
        return web.json_response({"error": RESTARTING}, status=503)
    try:
        meta = await uploads.receive(req, uploader_of(req))
    except uploads.UploadError as e:
        return web.json_response(e.body(), status=e.status)
    return web.json_response(uploads.public(meta), status=201)


async def upload_status(req):
    """An upload as it is now -- a voice note's words, once written out. Its uploader's only."""
    meta = uploads.get(uploader_of(req), req.match_info["id"])
    if meta is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(uploads.public(meta))


async def upload_list(req):
    """The asker's uploads no film has taken yet, newest first (each gone after a day)."""
    prune()
    return web.json_response({"uploads": uploads.listing(uploader_of(req))})


async def youtube_send(req):
    """Send a finished film into a YouTube upload session the site opened (youtube.py). The
    film's owner only; asking again with the same key answers the first send -- on whichever
    server it is running (a send another server is making is answered as going on)."""
    # a handed-over server still answers a request that reaches it on an old connection: it
    # stays until the send (or the draft) is done
    if DRAINING or MODE == "stopping":
        return web.json_response({"error": RESTARTING}, status=503)
    f = film_of(req.match_info["id"])
    rec = f.record()
    client = client_of(req)
    if not (from_this_machine(req) or clients.same(rec.get("client"), client)):
        return web.json_response({"error": "only whoever made a film can publish it"}, status=403)
    if not rec.get("ok"):
        return web.json_response({"error": "This film is not finished."}, status=409)
    try:
        body = await req.json()
        key = body.get("key")
        if isinstance(key, str) and youtube.get(key) is None and peer_has("sends", key):
            return web.json_response({"key": key, "film": f.id, "state": "sending"}, status=202)
        job = youtube.start(f, client, body.get("to"), key)
    except (ValueError, AttributeError):
        return web.json_response({"error": "expected JSON"}, status=400)
    except youtube.SendError as e:
        return web.json_response({"error": e.text}, status=e.status)
    return web.json_response(youtube.public(job), status=202)


async def youtube_sent(req):
    """How a send is going: bytes sent, and YouTube's answer once it has the whole film -- from
    this server's memory, from the outcome written beside the film, or (a send another server is
    making) "sending"."""
    f = film_of(req.match_info["id"])
    key = req.match_info["key"]
    job = youtube.get(key, f)
    if job is None and peer_has("sends", key):
        if not (from_this_machine(req) or clients.same(f.record().get("client"), client_of(req))):
            return web.json_response({"error": "no such send"}, status=404)
        return web.json_response({"key": key, "film": f.id, "state": "sending"})
    if job is None or job["film"] != f.id:
        return web.json_response({"error": "no such send"}, status=404)
    if not (from_this_machine(req) or clients.same(job["client"], client_of(req))):
        return web.json_response({"error": "no such send"}, status=404)
    return web.json_response(youtube.public(job))


async def youtube_draft(req):
    """Have the film's YouTube title, description and tags written (ytdraft.py): from the film,
    in the voice of the channel's latest uploads, which the site read with its grant and sends.
    The film's owner only; the same film, channel and uploads answer the draft already written,
    and one another server is writing is answered as being written."""
    # a handed-over server still answers a request that reaches it on an old connection: it
    # stays until the send (or the draft) is done
    if DRAINING or MODE == "stopping":
        return web.json_response({"error": RESTARTING}, status=503)
    f = film_of(req.match_info["id"])
    rec = f.record()
    client = client_of(req)
    if not (from_this_machine(req) or clients.same(rec.get("client"), client)):
        return web.json_response({"error": "only whoever made a film can publish it"}, status=403)
    if not rec.get("ok"):
        return web.json_response({"error": "This film is not finished."}, status=409)
    try:
        channel, recent = ytdraft.parse_request(await req.json())
    except ValueError as e:
        return web.json_response({"error": str(e) or "expected JSON"}, status=400)
    writing = {"film": f.id, "channel": channel["id"], "state": "writing"}
    if ytdraft.get(f.id, channel["id"]) is None and peer_has("drafts", [f.id, channel["id"]]):
        return web.json_response(writing, status=202)  # another server is writing it
    # as for a film: this machine's own asks on its login, anyone through the tunnel site_auth()
    auth = (
        (os.environ.get("STUDIO_LOCAL_AUTH") or "login") if from_this_machine(req) else site_auth()
    )
    try:
        job = await ytdraft.start(f, client, channel, recent, auth)
    except ytdraft.DraftError as e:
        return web.json_response({"error": e.text}, status=e.status)
    return web.json_response(ytdraft.public(job), status=200 if job["state"] == "done" else 202)


async def youtube_drafted(req):
    """The draft for one channel: writing, done (title, description, tags, language) or failed."""
    f = film_of(req.match_info["id"])
    channel = req.match_info["channel"]
    job = ytdraft.get(f.id, channel)
    if job is not None:
        if not (from_this_machine(req) or clients.same(job["client"], client_of(req))):
            return web.json_response({"error": "no such draft"}, status=404)
        return web.json_response(ytdraft.public(job))
    # another server's, or written before this server started: its heartbeat, or the disk
    if not (from_this_machine(req) or clients.same(f.record().get("client"), client_of(req))):
        return web.json_response({"error": "no such draft"}, status=404)
    if peer_has("drafts", [f.id, channel]):
        return web.json_response({"film": f.id, "channel": channel, "state": "writing"})
    d = ytdraft.cached(f, {"id": channel}) if ytdraft.CHANNEL.match(channel) else None
    if d is None:
        return web.json_response({"error": "no such draft"}, status=404)
    # its thumbnails as they were made; none on disk reads "none", and the page asks for the
    # draft again (POST), which makes them
    th = thumbs.saved(f, channel, d.get("key"))
    return web.json_response(
        ytdraft.public(
            {"film": f.id, "channel": channel, "state": "done", "draft": d, "thumbs": th}
        )
    )


async def cancel(req):
    """Its person's Stop (or this machine's). A film another server is making -- or one waiting
    for the leader to pick it up -- gets the Stop passed on (peers.request_cancel): its maker
    obeys within a tick, the leader records it cancelled if nobody is making it."""
    f = film_of(req.match_info["id"])
    J = JOBS.get(f.id)
    if J is not None and J["status"] in ("queued", "running") and not J.get("ended"):
        if not (from_this_machine(req) or clients.same(J["client"], client_of(req))):
            return web.json_response(
                {"error": "only whoever asked for a film can stop it"}, status=403
            )
        J["task"].cancel()
        return web.json_response({"id": f.id, "status": "cancelling"}, status=202)
    rec = f.record()
    if rec.get("state") == "waiting":  # nobody is making it: stopping it is putting it down
        if not (from_this_machine(req) or clients.same(rec.get("client"), client_of(req))):
            return web.json_response(
                {"error": "only whoever asked for a film can stop it"}, status=403
            )
        await put_down(f, "cancelled", "cancelled", "The film was cancelled.")
        return web.json_response({"id": f.id, "status": "cancelled"}, status=202)
    if rec.get("state") not in films.ACTIVE or rec.get("server") == peers.SERVER_ID:
        return web.json_response({"error": "that film is not being made"}, status=409)
    if not (from_this_machine(req) or clients.same(rec.get("client"), client_of(req))):
        return web.json_response({"error": "only whoever asked for a film can stop it"}, status=403)
    peers.request_cancel(f.id, by=client_of(req))
    return web.json_response({"id": f.id, "status": "cancelling"}, status=202)


async def continue_film(req):
    """Its person's Continue, for a film that waited for their own voice (state waiting, after
    tools.voice paused it): it goes back in the queue and picks its Claude session up where it
    stopped (agent.RESUME_VOICE; a film made in scenes carries on from its pass). The site checks
    the voice works first, and may send a new one ({voice}: the narrator, with a new grant)."""
    f = film_of(req.match_info["id"])
    rec = f.record()
    if not (from_this_machine(req) or clients.same(rec.get("client"), client_of(req))):
        return web.json_response(
            {"error": "only whoever asked for a film can continue it"}, status=403
        )
    if rec.get("state") != "waiting":
        J = JOBS.get(f.id)
        if rec.get("state") in films.ACTIVE:  # continued already: where it is now
            return web.json_response(
                {"id": f.id, "status": (J or {}).get("status") or "queued"}, status=202
            )
        return web.json_response({"error": "that film is not waiting"}, status=409)
    body = {}
    with contextlib.suppress(ValueError):
        body = await req.json() if req.can_read_body else {}
    narrator, err = narrator_of(body.get("voice")) if isinstance(body, dict) else (None, None)
    if err:
        return web.json_response({"error": err}, status=400)
    if not await leading():
        return web.json_response({"error": RESTARTING}, status=503)
    async with ADMIT:
        if not peers.leads() or MODE != "serving" or DRAINING:
            return web.json_response({"error": RESTARTING}, status=503)
        others = peers.peers()
        refused = await over_limit(
            client_of(req), f.length, rec.get("auth", "api"), at_once_of(req), others
        )
        if refused:
            return web.json_response({"error": refused}, status=429)
        if narrator and narrator.get("source") == "elevenlabs":  # a new voice, or a new grant
            p = f.path("temp", "voice.json")
            with open(
                os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8"
            ) as vf:
                json.dump({"grant": narrator["grant"]}, vf)
            f.update(narrator={k: v for k, v in narrator.items() if k != "grant"})
        f.update(state="queued", waiting=None, resume={"why": "voice"}, server=None)
        last_word(
            f,
            {
                "type": "stage",
                "name": "queue",
                "text": "Continued: the narrator's voice works again",
            },
        )
        await agent.save(f.id, {"state": "queued", "waiting": None})
        start(f, resume="voice")
    return web.json_response({"id": f.id, "status": "queued"}, status=202)


async def drain(req):
    """Take no more films; let the running ones finish; leave the queued ones for the next
    server (serve.ps1 then restarts). Only from this machine."""
    global DRAINING
    if not from_this_machine(req):
        raise web.HTTPForbidden()
    DRAINING = True
    for jid, J in JOBS.items():
        if waiting_for_slot(jid, J):  # one that just got its slot is running: it finishes
            J["control"]["requeue"] = True
            J["task"].cancel()
    return web.json_response({"draining": True, "running": len(live(("running",)))})


def project_of(req):
    """?project=<id>: which of the asker's libraries a library route means (None: their own).
    Raises 404 for one that is not a project id."""
    p = req.query.get("project")
    if p is None:
        return None
    if not films.PROJECT_ID.match(p):
        raise web.HTTPNotFound()
    return p


async def library_list(req):
    """The asker's own library (library.py): their cast and the films it remembers; with
    ?project=, that project's, with its pictures."""
    return web.json_response(library.listing(client_of(req), project_of(req)))


async def library_thumb(req):
    """A cast member's picture, the asker's own."""
    p = library.thumb_of(client_of(req), req.match_info["name"], project_of(req))
    if p is None:
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "private, no-cache"})


async def library_delete(req):
    """Leave a cast member out of the asker's next films (or their project's)."""
    name, project = req.match_info["name"], project_of(req)
    if not await asyncio.to_thread(library.delete, client_of(req), name, project):
        return web.json_response({"error": "no such cast member"}, status=404)
    return web.json_response({"name": name, "deleted": True})


async def picture_add(req):
    """Put one of the asker's uploads into their project as a picture its episodes get:
    {"project": id, "upload": "up-...", "name": "logo"}. The upload goes; the picture stays. The
    upload is the person's (uploader_of: X-Member), the project the workspace's (the client)."""
    try:
        body = await req.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return web.json_response({"error": 'send {"project", "upload", "name"}'}, status=400)
    client, project = client_of(req), str(body.get("project") or "")
    if not films.PROJECT_ID.match(project) or not library.owner(client, project):
        return web.json_response({"error": "No such project."}, status=404)
    uploader = uploader_of(req)
    meta = uploads.get(uploader, body.get("upload"))
    if meta is None:
        return web.json_response(
            {"error": "That upload is no longer here; add it again.", "reason": "attachment"},
            status=409,
        )
    if meta["kind"] != "image":
        return web.json_response({"error": "A project's pictures are pictures."}, status=400)
    try:
        entry = await asyncio.to_thread(
            library.add_picture,
            client,
            project,
            str(body.get("name") or ""),
            uploads.file_of(uploader, meta),
            meta["ext"],
        )
    except library.PictureError as e:
        return web.json_response({"error": e.text}, status=e.status)
    uploads.release(uploader, [meta])
    return web.json_response(entry, status=201)


async def picture_delete(req):
    """Take a picture out of the asker's project: ?project=<id>."""
    name, project = req.match_info["name"], project_of(req)
    if not project or not await asyncio.to_thread(
        library.delete_picture, client_of(req), project, name
    ):
        return web.json_response({"error": "no such picture"}, status=404)
    return web.json_response({"name": name, "deleted": True})


async def picture_thumb(req):
    """A project picture, small: ?project=<id>. The asker's own."""
    project = project_of(req)
    p = project and library.picture_thumb(client_of(req), project, req.match_info["name"])
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "private, no-cache"})


async def voice_add(req):
    """Approve a line of one of the asker's finished episodes as a voice line of its project:
    {"project": id, "film": id, "line": i}. The next episodes play that recording for the same
    words in the same voice (library.py, docs/studio-voice-lines.md)."""
    try:
        body = await req.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return web.json_response({"error": 'send {"project", "film", "line"}'}, status=400)
    project = str(body.get("project") or "")
    if not films.PROJECT_ID.match(project):
        return web.json_response({"error": "No such project."}, status=404)
    try:
        entry = await asyncio.to_thread(
            library.add_voice_from_film,
            client_of(req),
            project,
            body.get("film"),
            body.get("line"),
        )
    except library.VoiceError as e:
        return web.json_response({"error": e.text}, status=e.status)
    return web.json_response(entry, status=201)


async def voice_delete(req):
    """Take a voice line out of the asker's project: ?project=<id>."""
    key, project = req.match_info["key"], project_of(req)
    if not project or not await asyncio.to_thread(
        library.delete_voice, client_of(req), project, key
    ):
        return web.json_response({"error": "no such voice line"}, status=404)
    return web.json_response({"key": key, "deleted": True})


async def voice_audio(req):
    """A voice line to listen to, as MP3: ?project=<id>. The asker's own."""
    project = project_of(req)
    p = project and library.voice_audio(client_of(req), project, req.match_info["key"])
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(
        p, headers={"Cache-Control": "private, no-cache", "Content-Type": "audio/mpeg"}
    )


def own_film(req):
    """The film of this route, when the asker made it (or this machine asks); else 404, so a
    stranger learns nothing about a film's narration."""
    f = film_of(req.match_info["id"])
    if not (from_this_machine(req) or clients.same(f.record().get("client"), client_of(req))):
        raise web.HTTPNotFound()
    return f


async def film_lines(req):
    """A finished film's narration lines, for its person to listen to and approve: {"lines":
    [{i, text, start, dur, key, approved, played_approved}], "project"}."""
    f = own_film(req)
    rec = f.record()
    lines = await asyncio.to_thread(library.film_lines, f) if f.state == "done" else []
    return web.json_response({"lines": lines, "project": (rec.get("project") or {}).get("id")})


async def film_line_audio(req):
    """One line of the asker's finished film, as MP3."""
    f = own_film(req)
    try:
        i = int(req.match_info["i"])
    except ValueError:
        raise web.HTTPNotFound() from None
    p = await asyncio.to_thread(library.film_line_audio, f, i) if f.state == "done" else None
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(
        p, headers={"Cache-Control": "private, no-cache", "Content-Type": "audio/mpeg"}
    )


async def hide(req):
    """Take a film out of the gallery, or put it back: {"hidden": true|false}. Its page and its
    link keep working. Only from this machine (the operator's call, not a visitor's)."""
    if not from_this_machine(req):
        raise web.HTTPForbidden()
    f = film_of(req.match_info["id"])
    try:
        hidden = bool((await req.json()).get("hidden", True))
    except ValueError:
        hidden = True
    f.update(hidden=hidden)
    await agent.save(f.id, {"hidden": hidden})
    return web.json_response({"id": f.id, "hidden": hidden})


async def set_listed(req):
    """Show a film in the gallery, or keep it link-only: {"listed": true|false}. The film's own
    client (or this machine) only. Separate from hidden, which is the operator's: a film the
    operator hid stays out of the gallery whatever its maker asks."""
    f = film_of(req.match_info["id"])
    rec = f.record()
    if not (from_this_machine(req) or clients.same(rec.get("client"), client_of(req))):
        return web.json_response({"error": "only whoever made a film can change that"}, status=403)
    try:
        listed = (await req.json()).get("listed")
    except ValueError:
        listed = None
    if not isinstance(listed, bool):
        return web.json_response({"error": 'send JSON: {"listed": true|false}'}, status=400)
    f.update(listed=listed)
    await agent.save(f.id, {"listed": listed})
    return web.json_response({"id": f.id, "listed": listed})


def film_urls(req, jid, rec):
    """A finished film's video and poster: its copy online (media.py) when there is one --
    lasting, and playing when this machine is off -- else signed URLs through the tunnel."""
    m = rec.get("media") or {}
    if m.get("video"):
        # the web copy plays (media.make_web); the master is the download
        out = {"video_url": m.get("web") or m["video"], "download_url": m["video"]}
        out["poster_url"] = m.get("poster")
        if m.get("card"):
            out["card_url"] = m["card"]
        if m.get("subtitles"):
            out["subtitles_url"] = m["subtitles"]
        if not out["poster_url"]:
            out["poster_url"] = signed(req, jid, "film_poster.png")
        return out
    f = Film.open(jid)
    web = f is not None and os.path.isfile(f.path("outputs", "film_web.mp4"))
    return {
        "video_url": signed(req, jid, "film_web.mp4" if web else "film.mp4"),
        "download_url": signed(req, jid, "film.mp4") + "&dl=1",
        "poster_url": signed(req, jid, "film_poster.png"),
    }


# What has been read of the events.jsonl of films this server is not making (read_log), so a
# poll reads only what was added since the last one: film id -> {"end": bytes read, "at": each
# event's byte offset, and what the events said}. The films polled most recently.
LOGS = OrderedDict()
LOGS_MAX = 64


def read_log(film, since=0):
    """A film's events from its events.jsonl, from event number `since` on: (events, how many
    there are, what they said: stage, wait, ahead (in the queue for Claude), cost, t -- the last
    event's time into the run -- and mtime, the file's). Whole lines only: the server making the
    film may be half-way through writing one. Kept in step with what start()'s emit() does, so a
    page moving from one server to another sees the same numbers."""
    path = film.path("events.jsonl")
    c = LOGS.pop(film.id, None)
    try:
        st = os.stat(path)
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        size, mtime = 0, 0.0
    if c is None or size < c["end"]:
        c = {"end": 0, "at": [], "stage": None, "wait": None, "ahead": None, "cost": None}
        c["t"] = 0.0
    LOGS[film.id] = c
    while len(LOGS) > LOGS_MAX:
        LOGS.popitem(last=False)
    c["mtime"] = mtime
    if size > c["end"]:
        with open(path, "rb") as fh:
            fh.seek(c["end"])
            chunk = fh.read(size - c["end"])
        whole = chunk[: chunk.rfind(b"\n") + 1]
        at = c["end"]
        for raw in whole.split(b"\n")[:-1]:
            ev = _event(raw)
            if ev is not None:
                c["at"].append(at)
                kind = ev.get("type")
                if kind == "stage":
                    c["stage"], c["wait"], c["ahead"] = ev.get("name"), None, None
                elif kind == "wait":
                    c["wait"] = ev.get("text")
                    c["ahead"] = ev.get("ahead") if ev.get("pool") == "claude" else None
                elif kind in ("tool", "say"):
                    c["wait"] = None
                elif kind == "cost":
                    c["cost"] = ev.get("usd")
                c["t"] = ev.get("t", c["t"]) or 0.0
            at += len(raw) + 1
        c["end"] += len(whole)
    n = len(c["at"])
    events = []
    if since < n:
        with open(path, "rb") as fh:
            fh.seek(c["at"][since])
            rest = fh.read(c["end"] - c["at"][since])
        events = [ev for ev in map(_event, rest.split(b"\n")) if ev is not None]
    return events, n, c


def _event(raw):
    """One line of an events.jsonl, or None for a blank (or broken) one."""
    if not raw.strip():
        return None
    try:
        ev = json.loads(raw)
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


async def status(req):
    jid = req.match_info["id"]
    f = film_of(jid)  # 404 unless it exists
    J = JOBS.get(f.id)
    since = max(0, int(req.query.get("since") or 0))

    def with_urls(events):
        # a review sheet and a preview get a signed URL, so a browser can show them without the
        # token
        return [
            ev | {"url": signed(req, jid, ev["path"]) + "&v=%d" % ev["v"]}
            if ev["type"] in ("image", "preview")
            else ev
            for ev in events
        ]

    r = f.record()
    st = f.state
    # another server is making it (or it waits for the leader to pick it up: queued, or left
    # being finished): its record and its log say how it goes, in the same shape as this
    # server's own. A film Claude was writing when its server died is lost -- the leader marks
    # it interrupted -- and never one whose maker is alive.
    elsewhere = J is None and st in films.ACTIVE and (st != "claude" or peers.owner_alive(r))
    if elsewhere:
        events, n, said = read_log(f, since)
        out = {
            "id": jid,
            "status": "queued" if st == "queued" else "running",
            "stage": said["stage"] or "queue",
            "elapsed_s": round(said["t"] + max(0.0, time.time() - said["mtime"]), 1)
            if said["mtime"]
            else 0.0,
            "events": with_urls(events),
            "next": n,
        }
        if said["wait"]:
            out["wait"] = said["wait"]
        if out["status"] == "queued" and said["ahead"] is not None:
            out["position"] = said["ahead"] + 1
        if said["cost"] is not None:
            out["cost_usd"] = said["cost"]  # so far
        r = {k: r.get(k) for k in ("prompt", "title", "look", "length", "listed")}
    # over, made before this server started, or since replaced by a remade film (ops.sh
    # replace): what is on disk is all there is
    elif J is None or (J["status"] == "done" and r.get("replaced")):
        st = {
            "done": "done",
            "cancelled": "cancelled",
            "error": "error",
            "interrupted": "error",
            "waiting": "waiting",  # paused for its person's voice: Continue picks it up
        }.get(st, "lost")
        events, n, _ = read_log(f, since)
        out = {
            "id": jid,
            "status": st,
            "events": with_urls(events),
            "next": n,
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
            r = {k: r.get(k) for k in ("prompt", "title", "look", "length", "listed")}
    if out["status"] == "waiting":  # paused for its person's voice: why and since when, in words
        w = f.record().get("waiting") or {}
        out["waiting"] = {
            "reason": w.get("reason"),
            "since": w.get("since"),
            "text": agent.waiting_words(w),
        }
    if out["status"] == "done":
        out.update(film_urls(req, jid, r))
    out["listed"] = r.get("listed") is not False  # a film from before the switch was listed
    made_from = f.record().get("template")  # a remake of a template: its "Made from" line
    if made_from:
        out["template"] = {k: made_from.get(k) for k in ("id", "version", "title")}
        out["frame"] = f.record().get("frame")
    keys = (
        "prompt",
        "title",
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
    sh = share.public(r)  # the share page's title, description and pictures (share.py)
    if sh:
        out["share"] = sh
    return web.json_response(out)


async def files(req):
    d = os.path.join(film_of(req.match_info["id"]).dir, "outputs")
    p = os.path.normcase(os.path.realpath(os.path.join(d, req.match_info["path"])))
    if not p.startswith(os.path.normcase(os.path.realpath(d)) + os.sep):
        raise web.HTTPNotFound()
    # a finished film's link preview is made the first time someone (the site) asks for it
    if req.match_info["path"] == "card.jpg" and not os.path.isfile(p):
        if os.path.isfile(os.path.join(d, "film_poster.png")):
            f = film_of(req.match_info["id"])
            await asyncio.to_thread(media.make_card, d, f.record().get("length") or f.length)
    if not os.path.isfile(p):
        raise web.HTTPNotFound()
    headers = {"Cache-Control": "no-cache"}
    if p.endswith(".html"):
        # a page of the film's (the preview, the player) runs code Claude wrote: always in a
        # sandbox of its own, never as this origin -- opened on its own as well as framed
        headers["Content-Security-Policy"] = "sandbox allow-scripts"
    if req.query.get("dl") == "1":  # the download_url: saved, not played (as media.py's copy)
        f = film_of(req.match_info["id"])
        headers["Content-Disposition"] = media.download_name(f)
    return web.FileResponse(p, headers=headers)


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
    """Every finished film, newest first (no cap: the gallery lists them all)."""
    out = []
    for f in Film.all():
        r = f.record()
        # a link-only film (its maker's choice) and a hidden one (the operator's) stay out
        if r.get("ok") and not r.get("hidden") and r.get("listed") is not False:
            out.append(
                {
                    k: r.get(k)
                    for k in (
                        "prompt",
                        "title",
                        "look",
                        "length",
                        "seconds",
                        "cost_usd",
                        "turns",
                        "stages",
                    )
                }
                | {"id": f.id}
                | film_urls(req, f.id, r)
            )
    return web.json_response(out)


def make_app(token):
    global TOKEN
    TOKEN = token
    app = web.Application(middlewares=[bye, need_token], client_max_size=64 * 1024)
    app.add_routes(
        [
            web.get("/", index),
            web.get("/film/{id}", index),  # one film's page: the page reads the id from the path
            web.get("/fonts/{name}", font),
            web.get("/people-row.js", people_row),
            web.get("/api/health", health),
            web.get("/api/limits", limits_route),
            web.get("/api/films", list_films),
            web.get("/api/templates", template_list),
            web.get("/api/templates/{id}", template_get),
            web.get("/api/templates/{id}/{v}/preview/{frame}/{name}", template_preview),
            web.get("/api/costs", costs),
            web.post("/api/films", create),
            web.post("/api/uploads", upload),
            web.get("/api/uploads", upload_list),
            web.get("/api/uploads/{id}", upload_status),
            web.get("/api/library", library_list),
            web.post("/api/library/pictures", picture_add),
            web.get("/api/library/pictures/{name}/thumb.png", picture_thumb),
            web.delete("/api/library/pictures/{name}", picture_delete),
            web.post("/api/library/voice", voice_add),
            web.get("/api/library/voice/{key}.mp3", voice_audio),
            web.delete("/api/library/voice/{key}", voice_delete),
            web.get("/api/library/{name}/thumb.png", library_thumb),
            web.delete("/api/library/{name}", library_delete),
            web.get("/api/films/{id}", status),
            web.get("/api/films/{id}/lines", film_lines),
            web.get("/api/films/{id}/lines/{i}.mp3", film_line_audio),
            web.post("/api/films/{id}/cancel", cancel),
            web.post("/api/films/{id}/continue", continue_film),
            web.post("/api/films/{id}/listed", set_listed),
            web.post("/api/films/{id}/youtube", youtube_send),
            web.post("/api/films/{id}/youtube/draft", youtube_draft),
            web.get("/api/films/{id}/youtube/draft/{channel}", youtube_drafted),
            web.get("/api/films/{id}/youtube/{key}", youtube_sent),
            web.post("/api/admin/drain", drain),
            web.post("/api/admin/films/{id}/hidden", hide),
            web.get("/files/{id}/{path:.+}", files),
        ]
    )
    app.on_startup.append(on_start)
    app.on_shutdown.append(shutdown)
    app.on_cleanup.append(end)
    return app


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if not procs.secret("ANTHROPIC_API_KEY"):  # fail now, not on the first request
        sys.exit("ANTHROPIC_API_KEY is not set (put it in the studio's .env)")
    peers.hold_own()
    if not peers.is_current():
        # a unit started for a release that is no longer the one to serve (a switch moved on, or
        # a restart of an old instance): it must not take films, nor the port
        print(
            "studio %s: not starting -- the current instance is %s"
            % (peers.INSTANCE, peers.current()),
            flush=True,
        )
        peers.leave()
        sys.exit(0)
    # the steps' cgroups, before any child exists: set up lazily at the first step, a Claude Code
    # child already in the unit's cgroup made it fail (EBUSY) and every step ran uncapped
    procs.cgroup_root()
    token = ensure_token()
    sys.exit(asyncio.run(serve(args.port, token)))


if __name__ == "__main__":
    main()
