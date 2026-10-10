#!/usr/bin/env python
"""The Sketch Studio API end to end, with Claude stubbed out: no API calls, no cost.

    python studio/test_server.py

A stand-in for run_claude() writes the committed example film's files, then calls the studio's
real tools (check, stills) the way Claude would, and reports a known token count. Everything
else is real: films made side by side in their own folders, the scheduler, the soundtrack, the
renders, status polling, the files, the token checks, the per-client and daily limits, cancel,
the server leading on its own and adopting the films a dead server left (a film a live one is
making left alone), a stop that leaves its films for the next, a drain, and each run's cost
record (kept in memory, not written to MongoDB). Two servers handing over is test_bluegreen.py.
A few minutes, most of it rendering. Everything happens in a throwaway STUDIO_HOME, removed at
the end.
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import subprocess
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import film as films  # noqa: E402
import store  # noqa: E402
import validate  # noqa: E402
import resume  # noqa: E402
import peers  # noqa: E402
from sched import Sched  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

# no copy online: with the studio's .env present (a production checkout -- the Azure VM) the stub
# films were uploaded to the real films container, six of them before anyone noticed. The copy
# online has its own test against a stand-in (test_media.py).
os.environ.pop("STUDIO_MEDIA_BASE", None)
server.procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
server.procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
server.procs.SECRETS.pop("STUDIO_R2_SECRET", None)

TOKEN = "test-token"
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}
CLAUDE_USD = (1000 * 4 + 2000 * 20 + 100000 * 0.2) / 1e6  # Opus 5.5 prices: $0.064
TTS_USD = 0.002  # what the stub's narration "spent"
EXPECT_USD = CLAUDE_USD + TTS_USD
CALLED = []  # the films the stub was asked to write


async def fake_claude(
    film, emit, meter, tools, auth="api", prompt=None, resume=None, budget_usd=None
):
    CALLED.append(film.id)
    ex = os.path.join(films.KIT, "config", "sketch", "example")
    said = film.record().get("prompt", "")
    if "usage limit" in said and auth == "login" and not resume:
        # the login works and Claude has written part of the film on the plan, then the plan's
        # limit ends the turn (agent.PlanLimit): the session is there to pick up on the key
        film.update(claude_session="fake-session")
        meter.add("msg_login_" + film.id, USAGE)
        emit({"type": "cost", "usd": round(meter.usd(), 4)})
        raise agent.PlanLimit("Usage limit reached")
    if "never answers" in said or ("goes silent once" in said and not resume):
        # a reply that never comes (the stall watchdog's case): the session exists, the narration
        # is recorded, and then nothing at all -- no message, no event, no tool at work
        film.update(claude_session="fake-session")
        os.makedirs(film.path("audio", "vo"), exist_ok=True)
        with open(film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": []}, f)
        await asyncio.sleep(120)
        return
    if (
        resume
    ):  # the last turn after the time ran out, or a stopped film picked up: what was missing
        for f in films.MADE:
            if not os.path.exists(film.path(f)):
                shutil.copy(os.path.join(ex, f), film.dir)
        if prompt != agent.WRAP_UP:  # picked up (agent.RESUME): a turn that costs
            meter.add("msg_resume_" + film.id, USAGE)
            emit({"type": "cost", "usd": round(meter.usd(), 4)})
        return
    prompt = film.record().get("prompt", "")
    if "voice pauses" in prompt:
        # a person's own ElevenLabs account runs out of characters half-way through the
        # narration: two takes were made (their characters, not KitCut's cost), then the voice
        # tool paused the film (tools.voice sets tools.parked; run_claude raises Parked)
        film.update(claude_session="fake-session")
        os.makedirs(film.path("audio", "vo"), exist_ok=True)
        with open(film.path("audio", "vo", "spend.jsonl"), "w", encoding="utf-8") as f:
            for _ in range(2):
                row = {
                    "payer": "user",
                    "provider": "elevenlabs",
                    "model": "eleven_multilingual_v2",
                    "chars": 60,
                }
                f.write(json.dumps(row | {"cost_usd": 0, "input": 0, "output": 0}) + "\n")
        meter.add("msg_voice_" + film.id, USAGE)
        emit({"type": "cost", "usd": round(meter.usd(), 4)})
        tools.parked = {
            "reason": "el_quota",
            "status": 401,
            "detail": "quota_exceeded",
            "since": "2026-09-30T12:00:00",
        }
        raise agent.Parked(tools.parked)
    if "login gone" in prompt and auth == "login":  # what run_claude raises for a lost login
        raise agent.SignInError(NOT_LOGGED_IN)
    if "nothing written" in prompt:
        await asyncio.sleep(60)  # Claude past its time with no film: a failure
        return
    if "only the picture" in prompt:  # past its time with the music and the cues unwritten
        film.update(claude_session="fake-session")
        shutil.copy(os.path.join(ex, "film.js"), film.dir)
        os.makedirs(film.path("audio", "vo"), exist_ok=True)
        with open(film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": []}, f)
        await asyncio.sleep(60)
        return
    for f in films.MADE:
        shutil.copy(os.path.join(ex, f), film.dir)
    if "with a cast" in prompt:  # a member for the person's next films, and film.js using it
        with open(film.path("cast", "pip.js"), "w", encoding="utf-8") as f:
            f.write(
                "SK.cast.pip = { about: 'Pip, a fox', draw(x, y, o = {}) {\n"
                "  SK.wash(SK.S.ellC(x, y, 60, 80), '#e0782f'); } };\n"
            )
        with open(film.path("film.js"), "a", encoding="utf-8") as f:
            f.write("\n// draws SK.cast.pip\n")
        if "then fails" in prompt:
            raise RuntimeError("Claude stopped early: a stub failure")
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
    if "slow" in prompt:
        await asyncio.sleep(120)  # a film someone cancels, or that keeps a slot busy
    if "overtime" in prompt:  # the film written and its narration recorded, then a long last look
        with open(film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": []}, f)
        await asyncio.sleep(60)
    await tools.check()
    await tools.stills([0, 2.5], True)
    said = await tools.motion()  # the film a few times a second: its cuts and still stretches
    if not said.startswith("Motion, from frames every"):
        raise RuntimeError("motion said: %s" % said)
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


async def paused(c, auth, mem, check):
    """A film whose person's own ElevenLabs voice stops speaking waits for them (state waiting):
    not final, so the site keeps its credits held; its slot free; its characters theirs, not
    KitCut's cost. Continue picks its session up; a stranger cannot; Stop puts it down."""
    me = auth | {"X-Client-Ip": "o:voiced", "X-Member": "u:voiced"}
    r = await c.post(
        "/api/films", json={"prompt": "the voice pauses half-way", "seconds": 10}, headers=me
    )
    fid = (await r.json())["id"]
    st = await wait_for(c, auth, fid, states=("waiting", "done", "error"), limit=120)
    check(st["status"] == "waiting", "a film whose own voice stops speaking waits")
    f = films.Film.open(fid)
    rec, doc = f.record(), mem.docs.get(fid, {})
    check(
        rec.get("state") == "waiting" and doc.get("state") == "waiting" and fid not in mem.finals,
        "its record says waiting, and not as a final state (the site keeps its credits held)",
    )
    check((rec.get("waiting") or {}).get("reason") == "el_quota", "and why")
    check(
        rec.get("user_tts_chars") == 120 and rec.get("tts_cost_usd") == 0,
        "its person's characters are counted apart, not as KitCut's cost",
    )
    h = await (await c.get("/api/health", headers=auth)).json()
    check(h["running"] == 0, "a waiting film holds no slot")
    stranger = auth | {"X-Client-Ip": "o:stranger", "Cf-Ray": "t"}  # through the tunnel
    r = await c.post("/api/films/%s/continue" % fid, headers=stranger)
    check(r.status == 403, "only its person continues it")
    r = await c.post("/api/films/%s/continue" % fid, headers=me)
    check(r.status == 202, "Continue puts it back in the queue")
    st = await wait_for(c, auth, fid, limit=300)
    check(
        st["status"] == "done"
        and films.Film.open(fid).record().get("resume", {}).get("why") == "voice",
        "and it is made from where it stopped",
    )
    r = await c.post("/api/films/%s/continue" % fid, headers=me)
    check(r.status == 409, "a film that is not waiting is not continued")
    # one that waits, stopped by its person: put down, its credits given back
    r = await c.post(
        "/api/films", json={"prompt": "the voice pauses, then stop", "seconds": 10}, headers=me
    )
    fid2 = (await r.json())["id"]
    await wait_for(c, auth, fid2, states=("waiting", "done", "error"), limit=120)
    r = await c.post("/api/films/%s/cancel" % fid2, headers=me)
    check(
        r.status == 202 and mem.docs.get(fid2, {}).get("state") == "cancelled",
        "Stop on a waiting film puts it down as cancelled",
    )


async def projects(c, auth, mem, check):
    """A project's episodes: its pictures and cast, apart from the person's own; one film in the
    making per person across projects; nothing of the project in what anyone may see."""
    import io

    from PIL import Image

    P = "p-cccccccccc"
    me, other = auth | {"X-Client-Ip": "u:proj"}, auth | {"X-Client-Ip": "u:proj-other"}
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (30, 90, 200)).save(buf, "PNG")
    r = await c.post(
        "/api/uploads", data=buf.getvalue(), headers=me | {"Content-Type": "image/png"}
    )
    up = (await r.json()).get("id")
    check(r.status == 201 and up, "a picture uploaded for the project")
    r = await c.post(
        "/api/library/pictures", json={"project": P, "upload": up, "name": "logo"}, headers=other
    )
    check(r.status == 409, "nobody else can take it into their project")
    r = await c.post(
        "/api/library/pictures", json={"project": "p-x", "upload": up, "name": "logo"}, headers=me
    )
    check(r.status == 404, "nor into something that is not a project")
    r = await c.post(
        "/api/library/pictures", json={"project": P, "upload": up, "name": "logo"}, headers=me
    )
    check(r.status == 201 and (await r.json())["w"] == 640, "it joins the project")
    r = await c.get("/api/library/pictures/logo/thumb.png?project=" + P, headers=me)
    check(r.status == 200 and (await r.read())[:4] == b"\x89PNG", "with its thumbnail")
    r = await c.get("/api/library/pictures/logo/thumb.png?project=" + P, headers=other)
    check(r.status == 404, "its person's only")

    # an organisation's project: a member's own upload becomes the organisation's picture
    member = auth | {"X-Client-Ip": "u:tm-jo"}
    team = auth | {"X-Client-Ip": "o:tm-northwind", "X-Member": "u:tm-jo"}
    r = await c.post(
        "/api/uploads", data=buf.getvalue(), headers=member | {"Content-Type": "image/png"}
    )
    tup = (await r.json()).get("id")
    r = await c.post(
        "/api/library/pictures",
        json={"project": "p-tmtmtmtmtm", "upload": tup, "name": "brand"},
        headers=team,
    )
    check(r.status == 201, "a member's upload joins the organisation's project (X-Member)")
    r = await c.get("/api/library/pictures/brand/thumb.png?project=p-tmtmtmtmtm", headers=team)
    check(r.status == 200, "and is the organisation's")
    r = await c.get("/api/library/pictures/brand/thumb.png?project=p-tmtmtmtmtm", headers=member)
    check(r.status == 404, "not the member's own")

    project = {"id": P, "name": "Pip's Channel", "brief": "Short, funny, for kids."}
    r = await c.post("/api/films", json={"prompt": "x", "project": {"id": "nope"}}, headers=me)
    check(r.status == 400, "a film's project must be one")
    r = await c.post(
        "/api/films", json={"prompt": "x", "voice": {"source": "elsewhere"}}, headers=me
    )
    check(r.status == 400, "a narrator comes from a source this studio knows")
    r = await c.post(
        "/api/films",
        json={"prompt": "x", "voice": {"source": "kitcut", "voice": "Nobody"}},
        headers=me,
    )
    check(r.status == 400, "and is one of KitCut's voices")
    # the site asks as the workspace ("o:proj", the personal one: the same owner as "u:proj"),
    # says who asked, and sends the narrator the project set
    r = await c.post(
        "/api/films",
        json={
            "prompt": "episode one, with a cast",
            "project": project,
            "voice": {"source": "kitcut", "voice": "Puck"},
        },
        headers=auth | {"X-Client-Ip": "o:proj", "X-Member": "u:proj"},
    )
    ep = (await r.json())["id"]
    f = films.Film.open(ep)
    check(
        f.record()["project"]["brief"] == "Short, funny, for kids."
        and mem.docs[ep].get("project_id") == P
        and os.path.exists(f.path("inputs", "pic_logo.png")),
        "an episode knows its project, and has its pictures (asked for as the workspace)",
    )
    check(
        f.record().get("member") == "u:proj" and mem.docs[ep].get("member") == "u:proj",
        "the film and its run record who asked",
    )
    with open(f.path("vo.json"), encoding="utf-8") as vf:
        check(
            f.record().get("narrator") == {"source": "kitcut", "voice": "Puck"}
            and json.load(vf)["voice"] == "Puck",
            "the narrator the project set is the film's voice",
        )
    r = await c.get("/api/films/%s" % ep, headers=me)
    check(r.status == 200, "and the person's old name still owns it")
    lim = await (await c.get("/api/limits", headers=auth)).json()
    check(
        lim["voice"]["sources"] == ["kitcut"] and "Kore" in lim["voice"]["kitcut_voices"],
        "the limits say what a narrator can be",
    )
    r = await c.post(
        "/api/films",
        json={"prompt": "at the same time, elsewhere", "project": project | {"id": "p-dddddddddd"}},
        headers=me,
    )
    check(r.status == 429, "one film in the making per person, across projects")
    st = await wait_for(c, auth, ep)
    check(
        st.get("status") == "done" and "brief" not in json.dumps(st) and "project" not in st,
        "the film's status says nothing of the project",
    )
    check("title" in mem.docs[ep] and mem.docs[ep]["project_id"] == P, "the final record has both")
    lib = await (await c.get("/api/library?project=" + P, headers=me)).json()
    own = await (await c.get("/api/library", headers=me)).json()
    check(
        [m["name"] for m in lib["cast"]] == ["pip"]
        and lib["films"] == [ep]
        and [p["name"] for p in lib["pictures"]] == ["logo"],
        "the project's library has the episode's cast (%s)" % lib,
    )
    check(own["cast"] == [] and own["films"] == [], "and the person's own does not")
    r = await c.get("/api/library?project=p-bad", headers=me)
    check(r.status == 404, "a library route with a bad project")
    r = await c.delete("/api/library/pictures/logo?project=" + P, headers=other)
    check(r.status == 404, "only its person takes a picture out")
    r = await c.delete("/api/library/pictures/logo?project=" + P, headers=me)
    lib = await (await c.get("/api/library?project=" + P, headers=me)).json()
    check(r.status == 200 and lib["pictures"] == [], "and then it is gone")


REAL_RUN_CLAUDE = agent.run_claude


class FakeClient:
    """ClaudeSDKClient answering as Claude Code 2.1.284 did on 2026-09-28 (agent.SignInError):
    the messages come back, the SDK raises nothing."""

    script = []

    def __init__(self, options):
        self.options = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, prompt):
        pass

    async def receive_response(self):
        for m in FakeClient.script:
            yield m


def reply(error, text, status):
    """What the CLI sends when the turn ends on an API error: a synthetic assistant message
    carrying `error`, then an is_error result."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    return [
        AssistantMessage(content=[TextBlock(text=text)], model="<synthetic>", error=error),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=0,
            is_error=True,
            num_turns=1,
            session_id="s",
            result=text,
            api_error_status=status,
        ),
    ]


async def sign_in(check):
    """run_claude tells a lost login (SignInError) from every other failure."""
    real_client, real_cli = agent.ClaudeSDKClient, agent.claude_cli
    agent.ClaudeSDKClient, agent.claude_cli = FakeClient, lambda: "claude"
    had_key = "ANTHROPIC_API_KEY" in agent.procs.SECRETS
    agent.procs.SECRETS.setdefault("ANTHROPIC_API_KEY", "sk-test")  # never used: no real client
    film = films.Film.create("sign-in probe", 10, client="local", source="test")
    tools = agent.Tools(film, Sched(), lambda ev: None, agent.Clock())

    async def outcome(auth):
        try:
            r = await REAL_RUN_CLAUDE(film, lambda ev: None, agent.Meter(), tools, auth)
        except agent.SignInError as e:
            return "signin", e.why
        except agent.PlanLimit as e:
            return "limit", e.why
        return "result", r.result if r else None

    try:
        cases = [
            ("logged out", "login", reply("authentication_failed", NOT_LOGGED_IN, None), "signin"),
            (
                "a bad or expired token",
                "login",
                reply("authentication_failed", BAD_TOKEN, 401),
                "signin",
            ),
            ("a 401 on the result alone", "login", reply(None, "API Error: 401", 401), "signin"),
            (
                "the plan's usage limit",
                "login",
                reply("rate_limit", "Usage limit reached", 429),
                "limit",
            ),
            (
                "a billing error",
                "login",
                reply("billing_error", "Credit balance too low", 400),
                "limit",
            ),
            (
                "a rate limit on the key (nothing to fall back to)",
                "api",
                reply("rate_limit", "Rate limited", 429),
                "result",
            ),
            ("an overloaded API", "login", reply("server_error", "Overloaded", 529), "result"),
            (
                "the key refused (no login to fall back from)",
                "api",
                reply("authentication_failed", BAD_TOKEN, 401),
                "signin",
            ),
        ]
        for what, auth, script, want in cases:
            FakeClient.script = script
            got = await outcome(auth)
            check(got[0] == want, "sign-in: %s -> %s (%s)" % (what, want, got[1]))

        def no_cli():
            raise RuntimeError("the Claude Code CLI is not installed")

        agent.claude_cli = no_cli
        got = await outcome("login")
        check(got[0] == "signin", "sign-in: no Claude Code on the machine -> signin (%s)" % got[1])
    finally:
        agent.ClaudeSDKClient, agent.claude_cli = real_client, real_cli
        if not had_key:
            agent.procs.SECRETS.pop("ANTHROPIC_API_KEY", None)
        # the probe is a queued film on disk: left there, the server below would recover it
        shutil.rmtree(film.dir, ignore_errors=True)


NOT_LOGGED_IN = "Not logged in · Please run /login"
BAD_TOKEN = "Failed to authenticate. API Error: 401 Invalid bearer token"


def probe(mp4):
    """(seconds, frame rate as ffprobe writes it) of a video."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries"]
        + ["stream=r_frame_rate:format=duration", "-of", "json", mp4],
        capture_output=True,
        text=True,
    ).stdout
    j = json.loads(out or "{}")
    return float(j["format"]["duration"]), j["streams"][0]["r_frame_rate"]


async def unbranded(c, auth, mem, check, ids):
    """A finished Free-plan film drawn again without its mark and closing (unbrand.py): only for
    its own client; a failed render leaves the film exactly as it was; then the same film, 3 s
    shorter, at the paid frame rate, still the film it was (done, its finish time, its costs)."""
    unbrand = server.unbrand
    paid, free = ids[0], ids[1]
    f = films.Film.open(free)
    was = f.record()
    mp4 = f.path("outputs", "film.mp4")
    url = "/api/films/%s/unbrand"

    async def stands(want):
        for _ in range(600):
            s = await (await c.get("/api/films/%s?since=100000" % free, headers=auth)).json()
            if s.get("unbrand") in want:
                return s
            await asyncio.sleep(0.5)
        return s

    s = await (await c.get("/api/films/%s" % free, headers=auth)).json()
    check(
        s.get("branded") is True and "unbrand" not in s,
        "a Free-plan film's status says it is branded",
    )
    r = await c.post(url % free, headers=auth | {"Cf-Ray": "t", "X-Client-Ip": "u:test-0"})
    check(r.status == 403, "another client cannot take a film's branding off (%d)" % r.status)
    r = await c.post(url % paid, headers=auth | {"X-Client-Ip": "u:test-0"})
    b = await r.json()
    check(
        r.status == 200 and b.get("branded") is False and b.get("unbrand") == "done",
        "a film with no branding: nothing to do (%s)" % b,
    )

    # a render that comes out wrong: said, and the film is untouched
    real = unbrand.check
    unbrand.check = lambda *a: "forced: not the film"
    try:
        r = await c.post(url % free, headers=auth | {"Cf-Ray": "t", "X-Client-Ip": "u:test-1"})
        again = await c.post(url % free, headers=auth | {"Cf-Ray": "t", "X-Client-Ip": "u:test-1"})
        check(
            r.status == 202 and again.status == 202 and len(unbrand.JOBS) == 1,
            "asked for, and asked twice is the same job (%d, %d)" % (r.status, again.status),
        )
        s = await stands(("failed", "done"))
    finally:
        unbrand.check = real
    rec = f.record()
    secs, rate = probe(mp4)
    check(
        s.get("unbrand") == "failed"
        and s.get("status") == "done"
        and s.get("branded") is True
        and rec.get("state") == "done"
        and rec.get("ok") is True
        and rec.get("branding") is True
        and rec.get("finished") == was.get("finished")
        and abs(secs - 8) < 0.1
        and rate == "30/1"
        and mem.docs[free].get("state") == "done"
        and mem.docs[free].get("branding") is True
        and not os.path.exists(f.path("temp", "unbrand"))
        and not os.path.exists(f.path(unbrand.SIDE)),
        "a failed one leaves the film as it was: done, branded, 8 s (%s, %.2f s, %s)"
        % (s.get("unbrand"), secs, (rec.get("unbrand") or {}).get("error")),
    )

    # asked again: the same film without them
    r = await c.post(
        url % free, headers=auth | {"Cf-Ray": "t", "X-Client-Ip": "u:test-1", "X-Fps": "60"}
    )
    check(r.status == 202, "a failed one can be asked for again (%d)" % r.status)
    s = await stands(("done", "failed"))
    rec = f.record()
    secs, rate = probe(mp4)
    d = mem.docs[free]
    check(
        s.get("unbrand") == "done" and s.get("branded") is False and s.get("status") == "done",
        "its status: no branding left (%s, %s)"
        % (s.get("unbrand"), (rec.get("unbrand") or {}).get("error")),
    )
    check(
        abs(secs - 5) < 0.1 and rate == "60/1",
        "the same film without the closing, at the paid frame rate (%.2f s, %s)" % (secs, rate),
    )
    check(
        rec.get("branding") is False
        and rec.get("fps") == 60
        and rec.get("state") == "done"
        and rec.get("ok") is True
        and rec.get("finished") == was.get("finished")
        and rec.get("seconds") == was.get("seconds")
        and rec.get("cost_usd") == was.get("cost_usd")
        and (rec.get("unbrand") or {}).get("before", {}).get("fps") == 30,
        "its record: still the film it was, finished when it was, and what it was before",
    )
    check(
        d.get("branding") is False
        and d.get("fps") == 60
        and d.get("state") == "done"
        and (d.get("unbrand") or {}).get("state") == "done"
        and len(d.get("calls", [])) == 1,
        "the run's record says so too, with no new Claude call",
    )
    check(
        os.path.getsize(f.path("outputs", "film_poster.png")) > 1000
        and os.path.getsize(f.path("audio", "final.wav")) > 1000
        and not os.path.exists(f.path("temp", "unbrand"))
        and not os.path.exists(f.path(unbrand.SIDE))
        and not os.listdir(unbrand.MARKS),
        "its poster and sound are the new film's, and nothing of the second render is left",
    )
    r = await c.post(url % free, headers=auth | {"Cf-Ray": "t", "X-Client-Ip": "u:test-1"})
    b = await r.json()
    check(
        r.status == 200 and b.get("unbrand") == "done" and not unbrand.in_flight(),
        "asked once more: already done",
    )

    # a server that went away mid-way: the leader finds the film by its mark (orphans). One whose
    # new film was already in place is only recorded done; one tried too often is given up on,
    # and its film stays as it is
    gone = {"state": "running", "server": "gone.1", "tries": 1, "fps": 60}
    unbrand.JOBS.pop(free, None)
    f.update(unbrand=gone)
    unbrand._set_mark(free)
    found = [x.id for x, _ in unbrand.orphans()]
    unbrand.resume(f, server.SCHED)
    await asyncio.sleep(0.2)
    rec = f.record()
    check(
        found == [free]
        and rec["unbrand"]["state"] == "done"
        and not os.listdir(unbrand.MARKS)
        and mem.docs[free]["unbrand"]["state"] == "done"
        and not unbrand.orphans(),
        "an orphan whose new film was already in place is recorded done (%s)" % found,
    )
    f.update(branding=True, unbrand=gone | {"tries": unbrand.TRIES})
    unbrand._set_mark(free)
    unbrand.resume(f, server.SCHED)
    await asyncio.sleep(0.2)
    rec = f.record()
    check(
        rec["unbrand"]["state"] == "failed"
        and rec.get("state") == "done"
        and not os.listdir(unbrand.MARKS)
        and mem.docs[free]["unbrand"]["state"] == "failed"
        and not unbrand.in_flight(),
        "one whose server went away %d times is given up on, the film untouched" % unbrand.TRIES,
    )
    f.update(branding=False, unbrand=rec["unbrand"] | {"state": "done"})  # as it really is


async def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    agent.STORE = mem = store.MemoryStore()
    await sign_in(check)  # the real run_claude, before fake_claude replaces it
    agent.run_claude = fake_claude

    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        auth = {"Authorization": "Bearer " + TOKEN}
        check((await c.get("/api/health")).status == 200, "health needs no token")
        r = await c.get("/api/limits")
        lim = await r.json()
        check(r.status == 200, "the limits need no token (the site's docs are built from them)")
        check(
            lim["lengths"] == {"min": films.LENGTHS[0], "max": films.LENGTHS[-1], "step": 5}
            and lim["prompt"]["max_chars"] == server.PROMPT_MAX
            and lim["attachments"]["pictures_per_film"] == server.uploads.MAX_IMAGES
            and lim["films"]["per_account_per_day"] == server.PER_CLIENT_DAILY
            and lim["films"]["at_once_per_account_max"] == server.AT_ONCE_MAX,
            "the limits are the constants the studio enforces (%s)" % lim["lengths"],
        )
        # the films-a-day count, and the operator's own workspace it does not apply to
        per_day, exempt = server.PER_CLIENT_DAILY, server.DAILY_EXEMPT
        server.PER_CLIENT_DAILY, server.DAILY_EXEMPT = 0, {"o:owner1"}
        try:
            capped = await server.over_limit("u:someone1", 5)
            free = await server.over_limit("u:owner1", 5)  # "u:" and "o:" are one owner
        finally:
            server.PER_CLIENT_DAILY, server.DAILY_EXEMPT = per_day, exempt
        check(
            capped and "films today" in capped and free is None,
            "the films-a-day limit holds for everyone but the exempt workspace (%r, %r)"
            % (capped, free),
        )
        check(
            not any(k in json.dumps(lim) for k in ("usd", "budget", "reserve", "cost")),
            "the limits say nothing about money",
        )
        n = [films.limits(s)["images"] for s in films.LENGTHS]
        check(n == sorted(n), "a longer film never gets fewer paintings (8 ... %d)" % n[-1])
        vo = {"voice": validate.VOICES[0], "lines": [{"text": "Hi.", "start": 200}]}
        check(
            not validate._vo(vo, 12, 480) and validate._vo(vo, 12, 60),
            "a narration line may start anywhere in the film, and not past its end",
        )
        drums = {"bpm": 120, "events": [{"type": "drums", "bars": 240}]}
        check(
            not validate._score(drums, 480) and validate._score(drums, 60),
            "an 8-minute film's drums may run 240 bars; a minute's may not",
        )
        check(
            films.limits(480)["voice_runs"] > films.limits(60)["voice_runs"] == 6,
            "a long film gets more recordings than a short one (retakes and refusals)",
        )
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
        r = await c.post(
            "/api/films",
            json={"prompt": "x" * (server.PROMPT_MAX + 1), "seconds": 15},
            headers=auth,
        )
        said = await r.json()
        check(
            r.status == 400 and said.get("reason") == "prompt" and "Shorten" in said["error"],
            "a prompt longer than the studio reads is refused, not cut (it was cut at 12,000)",
        )

        # ------------------------------------------------ three films at once, three clients
        ids = []
        # film 0 is a priority plan's, and asks for the key from this machine (which otherwise
        # uses its login); film 1 is a Free plan's (branded), through the tunnel: on the login,
        # as server.site_auth() says by default; film 2 asks for the login from this machine, and
        # for the preview (the site's X-Preview)
        extra = [
            ({"X-Priority": "1"}, {"auth": "api"}),
            ({"Cf-Ray": "test", "X-Branding": "1", "X-Fps": "30"}, {"auth": "login"}),
            ({"X-Preview": "1"}, {"auth": "login"}),
        ]
        site_was = os.environ.pop("STUDIO_SITE_AUTH", None)
        for i in range(3):
            r = await c.post(
                "/api/films",
                json={"prompt": "film number %d, stubbed" % i, "seconds": 5} | extra[i][1],
                headers=auth | {"X-Client-Ip": "u:test-%d" % i} | extra[i][0],
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
        for i, (j, st) in enumerate(zip(ids, results, strict=True)):
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
            previews = [e for e in st["all_events"] if e["type"] == "preview"]
            check(
                bool(previews) == (i == 2)
                and bool(f.record().get("preview")) == (i == 2)
                and all(
                    "/files/%s/review/preview.html" % j in e["url"] and "sig=" in e["url"]
                    for e in previews
                ),
                "a film asked for with X-Preview gets its preview, signed; the others none (%d)"
                % len(previews),
            )
            want = TTS_USD if i else EXPECT_USD  # on the login, Claude is not billed
            check(
                abs((st.get("cost_usd") or 0) - want) < 1e-4,
                "its cost, Claude + voice ($%s)" % st.get("cost_usd"),
            )
            rec = f.record()
            check(
                (rec.get("priority"), rec.get("auth"))
                == [(1, "api"), (0, "login"), (0, "login")][i]
                and mem.docs[j].get("priority") == rec.get("priority"),
                "its priority and way to pay (%s, %s)" % (rec.get("priority"), rec.get("auth")),
            )
            with open(f.manifest, encoding="utf-8") as fh:
                tail = json.load(fh).get("tail")
            secs = float(
                subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "csv=p=0",
                        f.path("outputs", "film.mp4"),
                    ],
                    capture_output=True,
                    text=True,
                ).stdout
                or 0
            )
            branded = i == 1
            check(
                bool(rec.get("branding")) == branded
                and bool(tail) == branded
                and abs(secs - (5 + (3 if branded else 0))) < 0.1
                and mem.docs[j].get("branding") == branded,
                "%s: its video is %.2f s"
                % ("a Free-plan film: the closing, 3 s more" if branded else "no closing", secs),
            )
            with open(f.path("vo.json"), encoding="utf-8") as fh:
                vo = json.load(fh)
            check(vo["tts"] == "gemini" and vo["takes"] == 1, "its voice settings put back")
            rate = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries"]
                + ["stream=r_frame_rate", "-of", "csv=p=0", f.path("outputs", "film.mp4")],
                capture_output=True,
                text=True,
            ).stdout.strip()
            want_fps = "30/1" if branded else "60/1"
            check(
                rate == want_fps and rec.get("fps") == int(want_fps[:2]),
                "%s: renders at %s fps" % ("a Free-plan film" if branded else "a paid one", rate),
            )
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

        # ------------------------------------------------ the Free film, without its branding
        await unbranded(c, auth, mem, check, ids)

        pv = [e for e in results[2]["all_events"] if e["type"] == "preview"][-1]["url"]
        r = await c.get(pv[pv.index("/files/") :])
        page = await r.text()
        check(
            r.status == 200
            and r.headers.get("Content-Security-Policy") == "sandbox allow-scripts"
            and 'id="pv-cap"' in page
            and "__PREVIEW" not in page,
            "the preview is the player with its captions, and runs only in a sandbox of its own",
        )
        video = results[0].get("video_url", "")
        path = video[video.index("/files/") :]
        r = await c.get(path)
        check(r.status == 200 and len(await r.read()) > 100_000, "the signed URL plays")
        check((await c.get(path.replace("&sig=", "&sig=0"))).status == 401, "a tampered one not")
        dl = results[0].get("download_url", "")
        r = await c.get(dl[dl.index("/files/") :])
        await r.read()
        check(
            r.status == 200
            and r.headers.get("Content-Disposition", "").startswith("attachment;")
            and "Content-Disposition" not in (await c.get(path)).headers,
            "the download URL saves the film; the video URL plays it",
        )
        r = await c.get("/files/%s/card.jpg" % ids[0], headers=auth)
        body = await r.read()
        check(
            r.status == 200 and body[:3] == b"\xff\xd8\xff" and 20_000 < len(body) < 1_000_000,
            "its link preview, card.jpg, is made on first request (%d KB)" % (len(body) // 1024),
        )
        check(
            (await c.get("/files/%s/..%%2F..%%2F.env" % ids[0], headers=auth)).status == 404,
            "no path escape",
        )
        check((await c.get("/api/films/../etc", headers=auth)).status == 404, "no id escape")
        listed = await (await c.get("/api/films", headers=auth)).json()
        check({x["id"] for x in listed} >= set(ids), "the gallery lists them")
        r = await c.post(
            "/api/admin/films/%s/hidden" % ids[0],
            json={"hidden": True},
            headers=auth | {"Cf-Ray": "t"},
        )
        check(r.status == 403, "a visitor cannot hide a film")
        r = await c.post("/api/admin/films/%s/hidden" % ids[0], json={"hidden": True}, headers=auth)
        listed = await (await c.get("/api/films", headers=auth)).json()
        check(
            r.status == 200
            and ids[0] not in {x["id"] for x in listed}
            and mem.docs[ids[0]].get("hidden") is True,
            "a hidden film leaves the gallery, on record too",
        )
        st = await (await c.get("/api/films/%s" % ids[0], headers=auth)).json()
        check(st.get("status") == "done", "and its own page still works")

        # ------------------------------------------------ the site's films: the switch
        os.environ["STUDIO_SITE_AUTH"] = "api"
        on_key = server.site_auth()
        os.environ["STUDIO_SITE_AUTH"] = "login"
        on_login = server.site_auth()
        os.environ.pop("STUDIO_SITE_AUTH")
        check(
            (on_key, on_login, server.site_auth()) == ("api", "login", "login"),
            "STUDIO_SITE_AUTH=api puts the site's films back on the key; the login otherwise",
        )
        if site_was is not None:
            os.environ["STUDIO_SITE_AUTH"] = site_was

        # ------------------------------------------------ link-only: its maker's switch
        tunnel_as = auth | {"Cf-Ray": "t"}
        r = await c.post(
            "/api/films/%s/listed" % ids[1],
            json={"listed": False},
            headers=tunnel_as | {"X-Client-Ip": "u:test-2"},
        )
        check(r.status == 403, "someone else cannot make a film link-only")
        own = tunnel_as | {"X-Client-Ip": "u:test-1"}
        r = await c.post("/api/films/%s/listed" % ids[1], json={"listed": "no"}, headers=own)
        check(r.status == 400, "listed must be true or false")
        r = await c.post("/api/films/%s/listed" % ids[1], json={"listed": False}, headers=own)
        listed = await (await c.get("/api/films", headers=auth)).json()
        st = await (await c.get("/api/films/%s" % ids[1], headers=auth)).json()
        check(
            r.status == 200
            and ids[1] not in {x["id"] for x in listed}
            and st.get("listed") is False
            and st.get("status") == "done"
            and mem.docs[ids[1]].get("listed") is False,
            "its maker makes it link-only: out of the gallery, its page still works, on record",
        )
        await c.post("/api/films/%s/listed" % ids[1], json={"listed": True}, headers=own)
        listed = await (await c.get("/api/films", headers=auth)).json()
        check(ids[1] in {x["id"] for x in listed}, "and back in")
        check(
            (await (await c.get("/api/films/%s" % ids[2], headers=auth)).json()).get("listed")
            is True,
            "a film is listed unless it asks not to be",
        )

        # ------------------------------------------------ one film in the making per client
        # (asked for through an assistant: link-only, and the record says where it came from)
        r = await c.post(
            "/api/films",
            json={"prompt": "a slow one", "listed": False},
            headers=auth | {"X-Client-Ip": "u:busy", "X-Source": "mcp", "X-App": "Claude"},
        )
        body = await r.json()
        slow = body.get("id")
        rec = films.Film.open(slow).record()
        check(
            body.get("listed") is False
            and (rec.get("listed"), rec.get("source"), rec.get("app")) == (False, "mcp", "Claude")
            and (mem.docs[slow].get("listed"), mem.docs[slow].get("source")) == (False, "mcp")
            and mem.docs[slow].get("app") == "Claude",
            "a film from an assistant: link-only, its source and app on record",
        )
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

        # ------------------------------------------------ two at once, on a plan that allows it
        # (the site's X-At-Once: Pro), never past the studio's own ceiling. The same picture sent
        # with two films at the same moment: the first takes it, the second is told to add it again
        import io

        from PIL import Image

        pro = auth | {"X-Client-Ip": "u:pro", "X-At-Once": "2"}
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), (200, 90, 30)).save(buf, "PNG")
        r = await c.post(
            "/api/uploads", data=buf.getvalue(), headers=pro | {"Content-Type": "image/png"}
        )
        up = (await r.json()).get("id")
        both = await asyncio.gather(
            *(
                c.post(
                    "/api/films", json={"prompt": "a slow one", "attachments": [up]}, headers=pro
                )
                for _ in range(2)
            )
        )
        answers = sorted([(r.status, await r.json()) for r in both], key=lambda a: a[0])
        check(
            [a[0] for a in answers] == [202, 409] and answers[1][1].get("reason") == "attachment",
            "one picture sent with two films at once: the first takes it, the second is told",
        )
        two = [answers[0][1]["id"]]
        r = await c.post("/api/films", json={"prompt": "a slow one"}, headers=pro)
        two.append((await r.json()).get("id"))
        check(r.status == 202, "an account whose plan allows two has a second film in the making")
        r = await c.post(
            "/api/films", json={"prompt": "and a third"}, headers=pro | {"X-At-Once": "5"}
        )
        check(
            r.status == 429 and "2 films" in (await r.json())["error"],
            "a third waits, even when asked for more than the studio allows (%d)"
            % server.AT_ONCE_MAX,
        )
        for jid in two:
            r = await c.post(
                "/api/films/%s/cancel" % jid, headers=tunnel | {"X-Client-Ip": "u:pro"}
            )
            check(r.status == 202, "each can be stopped")
        for jid in two:
            await wait_for(c, auth, jid, limit=60)
        check(server.SCHED["claude"].used == 0, "and both Claude slots are free again")

        # ------------------------------------------------ the day's budget
        server.DAILY_USD = EXPECT_USD
        r = await c.post("/api/films", json={"prompt": "over budget"}, headers=auth)
        check(r.status == 429 and "budget" in (await r.json())["error"], "past the day's budget")
        server.DAILY_USD = 1000

        # ------------------------------------------------ the login fails: the key makes it
        was = os.environ.pop("STUDIO_LOCAL_AUTH", None)  # this machine's films on the login
        r1 = await c.post("/api/films", json={"prompt": "login gone"}, headers=auth)
        r2 = await c.post("/api/films", json={"prompt": "usage limit on the login"}, headers=auth)
        g, u = (await r1.json())["id"], (await r2.json())["id"]
        sg, su = await asyncio.gather(wait_for(c, auth, g), wait_for(c, auth, u))
        if was is not None:
            os.environ["STUDIO_LOCAL_AUTH"] = was
        rg, dg = films.Film.open(g).record(), mem.docs[g]
        check(
            sg.get("status") == "done"
            and rg.get("auth") == "api"
            and (rg.get("fallback") or {}).get("from") == "login"
            and "login" in rg["fallback"]["why"]
            and dg.get("auth") == "api"
            and dg.get("claude_billed") is True
            and dg.get("via") == "sdk"
            and dg.get("fallback") == rg["fallback"]
            and CALLED.count(g) == 2
            and any(e["type"] == "fallback" for e in sg["all_events"]),
            "a lost login: the film is made on the key, and its record says so (%s)"
            % (sg.get("error") or rg.get("fallback")),
        )
        check(
            abs(dg.get("cost_usd", 0) - EXPECT_USD) < 1e-3,
            "and it is billed as a film on the key ($%.4f)" % dg.get("cost_usd", 0),
        )
        check(
            server.JOBS[g]["auth"] == "api"
            and server.JOBS[g]["reserve"] == server.reserve(films.Film.open(g).length, "api"),
            "and held against the day's budget as one (%s)" % server.JOBS[g]["reserve"],
        )
        ru = films.Film.open(u).record()
        check(
            su.get("status") == "error"
            and ru.get("auth") == "login"
            and not ru.get("fallback")
            and CALLED.count(u) == 1,
            "a plan limit on a login with no token of its own: the session cannot move to the "
            "key, so the film fails (%s)" % su.get("error"),
        )

        # ------------------------------------------------ the plan runs out: on the key from there
        had_token = "CLAUDE_CODE_OAUTH_TOKEN" in agent.procs.SECRETS
        agent.procs.SECRETS.setdefault("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-test")
        os.environ.pop("STUDIO_LOCAL_AUTH", None)
        r = await c.post("/api/films", json={"prompt": "usage limit half-way"}, headers=auth)
        p = (await r.json())["id"]
        sp = await wait_for(c, auth, p)
        if was is not None:
            os.environ["STUDIO_LOCAL_AUTH"] = was
        if not had_token:
            agent.procs.SECRETS.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        rp, dp = films.Film.open(p).record(), mem.docs[p]
        check(
            sp.get("status") == "done"
            and rp.get("auth") == "api"
            and (rp.get("fallback") or {}).get("limit") is True
            and "Usage limit" in rp["fallback"]["why"]
            and dp.get("claude_billed") is True
            and CALLED.count(p) == 2
            and any(e["type"] == "fallback" for e in sp["all_events"]),
            "a plan limit half-way: the same session carries on on the key, on record (%s)"
            % (sp.get("error") or rp.get("fallback")),
        )
        check(
            abs(dp.get("cost_usd", 0) - CLAUDE_USD) < 1e-3
            and abs(dp.get("claude_cost_usd", 0) - 2 * CLAUDE_USD) < 1e-3,
            "and only what it spent on the key is billed ($%.4f of $%.4f)"
            % (dp.get("cost_usd", 0), dp.get("claude_cost_usd", 0)),
        )
        check(
            server.JOBS[p]["auth"] == "api"
            and server.JOBS[p]["reserve"] == server.reserve(films.Film.open(p).length, "api"),
            "and held against the day's budget as a film on the key from then",
        )

        # ------------------------------------------------ Claude past its time
        real_limits = agent.limits
        agent.limits = lambda n: real_limits(n) | ({"claude_s": 3} if n in (20, 25, 30) else {})
        r1 = await c.post(
            "/api/films",
            json={"prompt": "overtime, the film written", "seconds": 20},
            headers=auth | {"X-Client-Ip": "u:ot1"},
        )
        r2 = await c.post(
            "/api/films",
            json={"prompt": "overtime, nothing written", "seconds": 25},
            headers=auth | {"X-Client-Ip": "u:ot2"},
        )
        r3 = await c.post(
            "/api/films",
            json={"prompt": "overtime, only the picture", "seconds": 30},
            headers=auth | {"X-Client-Ip": "u:ot3"},
        )
        a, b = (await r1.json()).get("id"), (await r2.json()).get("id")
        w = (await r3.json()).get("id")
        sa, sb, sw = await asyncio.gather(
            wait_for(c, auth, a), wait_for(c, auth, b, limit=180), wait_for(c, auth, w)
        )
        agent.limits = real_limits
        check(
            sa.get("status") == "done"
            and films.Film.open(a).record().get("overtime") is True
            and mem.docs[a].get("overtime") is True,
            "past its time, a film Claude had written is finished (%s)"
            % (sa.get("error") or sa.get("status")),
        )
        check(
            sb.get("status") == "error" and "limit" in (sb.get("error") or ""),
            "past its time with nothing written, a film fails (%s)" % sb.get("error"),
        )
        check(
            sw.get("status") == "done"
            and any("finishing up" in (e.get("text") or "") for e in sw["all_events"]),
            "past its time with only the picture, one last turn writes the rest (%s)"
            % (sw.get("error") or sw.get("status")),
        )

        # ------------------------------------------------ a series: the person's cast comes back
        r1 = await c.post(
            "/api/films",
            json={"prompt": "episode one, with a cast"},
            headers=auth | {"X-Client-Ip": "u:series"},
        )
        r2 = await c.post(
            "/api/films",
            json={"prompt": "with a cast, then fails"},
            headers=auth | {"X-Client-Ip": "u:series-fail"},
        )
        e1, e2 = (await r1.json())["id"], (await r2.json())["id"]
        s1, s2 = await asyncio.gather(wait_for(c, auth, e1), wait_for(c, auth, e2))
        mine = await (
            await c.get("/api/library", headers=auth | {"X-Client-Ip": "u:series"})
        ).json()
        check(
            s1.get("status") == "done"
            and [m["name"] for m in mine["cast"]] == ["pip"]
            and mine["cast"][0]["thumb"]
            and mem.docs[e1].get("cast") == {"saved": ["pip"], "used": ["pip"]},
            "a finished film's cast is kept, drawn (%s)" % (s1.get("error") or mine),
        )
        r = await c.get("/api/library/pip/thumb.png", headers=auth | {"X-Client-Ip": "u:series"})
        check(r.status == 200 and (await r.read())[:4] == b"\x89PNG", "its picture, its person's")
        r = await c.get("/api/library/pip/thumb.png", headers=auth | {"X-Client-Ip": "u:other"})
        check(r.status == 404, "nobody else's")
        failed = await (
            await c.get("/api/library", headers=auth | {"X-Client-Ip": "u:series-fail"})
        ).json()
        check(s2.get("status") == "error" and failed["cast"] == [], "a failed film keeps nothing")
        r = await c.post(
            "/api/films", json={"prompt": "episode two"}, headers=auth | {"X-Client-Ip": "u:series"}
        )
        e3 = (await r.json())["id"]
        f3 = films.Film.open(e3)
        check(
            os.path.exists(f3.path("cast", "pip.js"))
            and "- pip: Pip, a fox (in 1 film)" in agent.ask(f3)
            and mem.docs[e3].get("library") == {"cast": 1, "films": 1},
            "the person's next film starts with it",
        )
        await wait_for(c, auth, e3)
        r = await c.delete("/api/library/pip", headers=auth | {"X-Client-Ip": "u:other"})
        check(r.status == 404, "only its person deletes a member")
        r = await c.delete("/api/library/pip", headers=auth | {"X-Client-Ip": "u:series"})
        mine = await (
            await c.get("/api/library", headers=auth | {"X-Client-Ip": "u:series"})
        ).json()
        check(r.status == 200 and mine["cast"] == [], "and then it is gone")

        await projects(c, auth, mem, check)
        await paused(c, auth, mem, check)

        # ------------------------------------------------ the leader adopts what a dead server left
        check(
            peers.leads() and server.LEADER.is_set(),
            "a server alone leads (it admits the films, and adopts what is left)",
        )
        gone = "old-release.4242"  # a server that is not running: nobody holds its lock
        q = films.Film.create("left queued", 5, "drawn", client="u:r1")
        q.update(server=gone)
        fin = films.Film.create("left mid-render", 5, "drawn", client="u:r2")
        ex = os.path.join(films.KIT, "config", "sketch", "example")
        for f in films.MADE:
            shutil.copy(os.path.join(ex, f), fin.dir)
        fin.update(state="finishing", claude_cost_usd=0.5, server=gone)
        mid = films.Film.create("left while Claude wrote", 5, "drawn", client="u:r3")
        mid.update(state="claude", server=gone)
        # one whose maker is alive (this process stands in for the other server) is not touched
        elsewhere = films.Film.create("made by another server", 5, "drawn", client="u:r6")
        elsewhere.update(state="claude", server=peers.SERVER_ID)
        before = len(CALLED)
        await server.adopt()
        check(
            q.record().get("server") == peers.SERVER_ID and q.id in server.JOBS,
            "an adopted film is the leader's now (its record names it)",
        )
        st_e = await (await c.get("/api/films/%s" % elsewhere.id, headers=auth)).json()
        check(
            elsewhere.state == "claude"
            and elsewhere.id not in server.JOBS
            and st_e.get("status") == "running",
            "a film a live server is making is left to it, and its page says running (%s)"
            % st_e.get("status"),
        )
        elsewhere.update(state="error")  # nobody is really making it
        st_q, st_f = await asyncio.gather(wait_for(c, auth, q.id), wait_for(c, auth, fin.id))
        check(st_q.get("status") == "done", "a queued film is made after a restart")
        check(
            st_f.get("status") == "done" and fin.id not in CALLED[before:],
            "a film left mid-render is finished, without Claude (%s%s)"
            % (st_f.get("status"), ": " + str(st_f.get("error")) if st_f.get("error") else ""),
        )
        check(abs(st_f.get("claude_cost_usd", 0) - 0.5) < 1e-9, "keeping Claude's earlier cost")
        check(
            mid.state == "interrupted" and mem.docs.get(mid.id, {}).get("state") == "interrupted",
            "a film left mid-Claude is marked interrupted",
        )

        # ------------------------------------------------ a stopped film picked up (resume.py)
        stopped = films.Film.create("stopped half-way by a restart", 5, "drawn", client="u:r4")
        shutil.copy(os.path.join(ex, "film.js"), stopped.dir)
        os.makedirs(stopped.path("audio", "vo"), exist_ok=True)
        with open(stopped.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": []}, f)
        earlier = dict.fromkeys(("input", "cache_write_5m", "cache_write_1h"), 0)
        earlier.update(output=20, cache_read=30)
        stopped.update(
            state="cancelled",
            ok=False,
            error="cancelled",
            claude_session="fake-session",
            claude_cost_usd=0.5,
            cost_metered_usd=0.5,
            tokens=earlier,
            seconds=100,
        )
        mem.save(stopped.id, {"state": "cancelled", "calls": [{"message_id": "msg_before"}]})
        check(
            "no saved Claude session" in (resume.refuse(stopped, False) or ""),
            "a film is not picked up without its saved session",
        )
        sess = os.path.join(stopped.claude_dir, "projects", "-film")
        os.makedirs(sess)
        open(os.path.join(sess, "fake-session.jsonl"), "w").close()
        p = resume.plan(stopped)
        check(
            resume.refuse(stopped, False) is None
            and p["missing"] == ["score.json", "sfx.json"]
            and p["working_minutes"] == round((films.limits(5)["claude_s"] - 100) / 60, 1),
            "its plan: the session found, the music and cues missing, what is left of its time",
        )
        r = await agent.make_film(stopped, lambda ev: None, server.SCHED, auth="api", resume=True)
        rec, doc = stopped.record(), mem.docs[stopped.id]
        check(
            r.get("ok") and stopped.state == "done" and rec.get("error") is None,
            "a stopped film picked up is done, its old verdict gone",
        )
        check(
            abs(rec["claude_cost_usd"] - (0.5 + CLAUDE_USD)) < 1e-6
            and rec["tokens"]["output"] == 20 + USAGE["output_tokens"]
            and rec["resumed"]["earlier_usd"] == 0.5
            and rec["seconds"] > 100,
            "what the stopped attempt spent, and the time it took, are carried (%s, %ss)"
            % (rec["claude_cost_usd"], rec["seconds"]),
        )
        check(
            doc["state"] == "done"
            and [x["message_id"] for x in doc["calls"]]
            == ["msg_before", "msg_resume_" + stopped.id],
            "the record keeps both attempts' calls",
        )
        check(resume.refuse(stopped, False) is not None, "a done film is not picked up again")

        # ------------------------------------------------ a reply that never comes (the watchdog)
        real_stall = agent.STALL_S
        agent.STALL_S = 2  # seconds here; 20 minutes in the studio
        try:
            quiet = films.Film.create(
                "goes silent once, then carries on", 5, "drawn", client="u:w1"
            )
            r = await agent.make_film(quiet, lambda ev: None, server.SCHED, auth="api")
            check(
                r.get("ok") and quiet.state == "done" and r.get("stalls") == 1,
                "a Claude that goes silent is cut off, picked up again in its session, and the "
                "film finishes (%s, %s stall)" % (quiet.state, r.get("stalls")),
            )
            check(
                mem.docs[quiet.id].get("stalls") == 1 and quiet.id in CALLED,
                "and the record says it stalled once",
            )
            mute = films.Film.create("never answers", 5, "drawn", client="u:w2")
            t0 = time.time()
            said = []
            r = await agent.make_film(mute, said.append, server.SCHED, auth="api")
            check(
                not r.get("ok")
                and mute.state == "error"
                and "stopped answering" in (r.get("error") or "")
                and r.get("stalls") == agent.STALL_RETRIES + 1
                and time.time() - t0 < 60,
                "one that never answers fails after %d pick-ups, in seconds not hours (%s)"
                % (agent.STALL_RETRIES, r.get("error")),
            )
            check(
                sum(
                    1
                    for e in said
                    if e.get("type") == "fail" and "not answered" in e.get("text", "")
                )
                == agent.STALL_RETRIES,
                "and its page says each time what the studio did",
            )
        finally:
            agent.STALL_S = real_stall

        # ------------------------------------------------ a long film's rules and its narration
        check(
            agent.closing_s(30) == 1 and agent.closing_s(480) == 4 and agent.closing_s(120) == 2,
            "the narration stops a beat before a short film ends, a few seconds before a long one",
        )

        def not_made(prompt, n):  # a film only asked about: never queued, so nothing adopts it
            f = films.Film.create(prompt, n, "drawn", client="u:w3")
            f.update(state="done")
            return f

        long_ask = agent.ask(not_made("a long one", 480))
        short_ask = agent.ask(not_made("a short one", 30))
        check(
            "work in parts" in long_ask
            and "work in parts" not in short_ask
            and "ending by about 476 s" in long_ask,
            "a long film is told to write its picture in parts, and to end its narration in time",
        )
        tl_film = not_made("a long narration", 480)
        os.makedirs(tl_film.path("audio", "vo"), exist_ok=True)
        lines = [
            {
                "i": i,
                "text": "line %d" % i,
                "start": i * 7.0,
                "end": i * 7.0 + 6.5,
                "acc": 0.98,
                "words": [{"text": "word", "s": i * 7.0 + k} for k in range(12)],
            }
            for i in range(67)
        ]
        with open(tl_film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": lines}, f)
        import tools as tools_mod  # noqa: PLC0415 -- the tools module, as the studio calls it

        every = tools_mod.timeline_text(tl_film)
        one = tools_mod.timeline_text(tl_film, retake=5)
        check(
            every.count("words:") == 0
            and one.count("words:") == 1
            and sum(x.startswith("line ") for x in every.splitlines()) == 67,
            "a long narration comes back as its lines' spans, words only for the line re-recorded "
            "(%d characters, not %d)" % (len(every), sum(len(json.dumps(x)) for x in lines)),
        )
        # a narration past the film's end is said to Claude, not only to sketch-vo.py's log (u3edgl)
        with open(tl_film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({"duration": 460, "lines": lines}, f)
        over = tools_mod.timeline_text(tl_film)
        check(
            "NOTE" not in every and over.startswith("NOTE: the narration ends at 468.50 s"),
            "a narration that runs past the film's end says so, and how much",
        )
        # ...and it may still be made to fit: a line that starts after the end fails the mix, so a
        # film at its recording limit gets FIT_RUNS more while it does not fit (ewwd6b)
        late_film = not_made("a narration past the end", 60)
        os.makedirs(late_film.path("audio", "vo"), exist_ok=True)

        def lay(*spans):
            tl = {
                "duration": 60,
                "lines": [
                    {"i": i, "text": "x", "start": s, "end": e} for i, (s, e) in enumerate(spans)
                ],
            }
            with open(late_film.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
                json.dump(tl, f)

        runs, fit = films.limits(60)["voice_runs"], tools_mod.FIT_RUNS
        lay((1, 50), (50.5, 59.5), (61, 66))
        late = tools_mod.narration_over(late_film)
        refused = tools_mod.recording_refused(late_film, runs + fit)
        check(
            late["ends"] == 66
            and [L["i"] for L in late["late"]] == [2]
            and tools_mod.recording_refused(late_film, runs) is None
            and tools_mod.recording_refused(late_film, runs + fit - 1) is None
            and "still ends at 66.00 s" in refused,
            "a narration past the end may be recorded %d more times than the limit, then not" % fit,
        )
        t = tools_mod.Tools(late_film, None, lambda e: None)
        t.voice_runs = runs
        try:
            await t.sound()
            said = ""
        except tools_mod.ToolError as e:
            said = str(e)
        check(
            "line 2 starts 61.00 s" in said and "(2 recordings left" in said,
            "the mix names the lines after the end, and the recordings left, before it runs: %r"
            % said,
        )
        lay((1, 50), (50.5, 59.5))
        check(
            tools_mod.narration_over(late_film) is None
            and "keep the narration you have" in tools_mod.recording_refused(late_film, runs),
            "a narration that fits has the film's limit, no more",
        )
        # ...and the length is a target, not a wall (2026-10-09): a narration that ends under the
        # closing fade, or a little past the end, lengthens the film instead of losing its words
        check(
            (films.may_run_to(240), films.may_run_to(15), films.may_run_to(60, "9:16"))
            == (300, 25, 75)
            and films.may_run_to(170, "9:16") == 180
            and films.may_run_to(170) == 212,
            "a film may run a quarter over what was asked (ten seconds at least), a Short to 180 s",
        )
        lay((1, 50), (50.5, 58))
        check(tools_mod.fit_length(late_film) is None, "a narration that fits changes nothing")
        lay((1, 50), (50.5, 60.58))
        got = tools_mod.fit_length(late_film)
        with open(late_film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            grown_tl = json.load(f)
        check(
            got == {"was": 60, "now": 63, "asked": 60, "ends": 60.58, "top": 75}
            and late_film.length == 63
            and late_film.asked == 60
            and late_film.record().get("length") == 60
            and late_film.record().get("runs") == 63
            and grown_tl["duration"] == 63
            and tools_mod.narration_over(late_film) is None
            and "the film is now 63 s long" in tools_mod.grown_note(got),
            "a last line past the end makes the film longer, and says so: %r" % (got,),
        )
        lay((1, 50), (50.5, 59.5))
        check(
            tools_mod.fit_length(late_film)["now"] == 61 and late_film.length == 61,
            "a last word under the closing fade gets its second and a half too",
        )
        lay((1, 50), (50.5, 58))
        back = tools_mod.fit_length(late_film)
        check(
            back["now"] == 60
            and late_film.length == 60
            and not late_film.record().get("runs")
            and "60 s long again" in tools_mod.grown_note(back),
            "a narration recorded shorter brings the film back to what was asked",
        )
        lay((1, 50), (50.5, 70), (71, 90))
        far = tools_mod.fit_length(late_film)
        over = tools_mod.narration_over(late_film)
        check(
            far["now"] == 75
            and late_film.length == 75
            and over["ends"] == 90
            and over["length"] == 75
            and "asked for at 60 s may run" in tools_mod.fit_advice(late_film, 0),
            "past what a film may run to, it is as long as it may be and the words are cut back",
        )
        lay((1, 50), (50.5, 58))
        tools_mod.fit_length(late_film)

        # ------------------------------------------------ the server stops: interrupted, not cancelled
        r = await c.post(
            "/api/films",
            json={"prompt": "slow, writing when the server stops"},
            headers=auth | {"X-Client-Ip": "u:s1"},
        )
        writing = films.Film.open((await r.json())["id"])
        rendering = films.Film.create("rendering when the server stops", 5, "drawn", client="u:s2")
        for f in films.MADE:
            shutil.copy(os.path.join(ex, f), rendering.dir)
        rendering.update(state="finishing", claude_cost_usd=0.25)
        server.start(rendering, finish_only=True)
        for _ in range(50):  # until the one is in Claude's part and the other past its start
            await asyncio.sleep(0.2)
            if writing.state == "claude":
                break
        await server.shutdown(None)  # what systemd's SIGTERM runs (app.on_shutdown)
        with open(writing.path("events.jsonl"), encoding="utf-8") as f:
            said = [json.loads(x).get("text") for x in f if x.strip()]
        check(
            writing.state == "interrupted"
            and mem.docs[writing.id]["state"] == "interrupted"
            and said[-1] == agent.INTERRUPTED,
            "a film being written when the server stops is interrupted, and its page says why",
        )
        check(
            rendering.state == "finishing"
            and mem.docs.get(rendering.id, {}).get("state") != "failed",
            "a film being rendered is left finishing, its record not closed (%s)" % rendering.state,
        )
        check(
            rendering.record().get("server") is None,
            "and it is nobody's: the next leader takes it",
        )
        for f in (writing, rendering):  # the next server's memory starts empty
            server.JOBS.pop(f.id, None)
        await server.adopt()
        st_r = await wait_for(c, auth, rendering.id)
        check(
            st_r.get("status") == "done" and abs(st_r.get("claude_cost_usd", 0) - 0.25) < 1e-9,
            "and the next server finishes it, keeping Claude's cost",
        )
        crashed = films.Film.create("left mid-Claude by a crash", 5, "drawn", client="u:s3")
        crashed.update(state="claude")
        with open(crashed.path("events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "tool", "text": "edited film.js", "t": 12.5}) + "\n")
        await server.recover(None)  # the old name: a record from before owners (no "server")
        last = json.loads(open(crashed.path("events.jsonl"), encoding="utf-8").readlines()[-1])
        check(
            crashed.state == "interrupted"
            and last
            == {
                "type": "error",
                "text": agent.INTERRUPTED,
                "t": 12.5,
            },
            "a crash's interrupted film says so on its page too",
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
