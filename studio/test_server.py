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
from sched import Sched  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

# no copy online: with the studio's .env present (a production checkout -- the Azure VM) the stub
# films were uploaded to the real films container, six of them before anyone noticed. The copy
# online has its own test against a stand-in (test_media.py).
os.environ.pop("STUDIO_MEDIA_BASE", None)
server.procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)

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
    if "login gone" in prompt and auth == "login":  # what run_claude raises for a lost login
        raise agent.SignInError(NOT_LOGGED_IN)
    if "usage limit" in prompt and auth == "login":  # the login works; the plan is spent
        raise RuntimeError("Claude stopped early: Usage limit reached")
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

    project = {"id": P, "name": "Pip's Channel", "brief": "Short, funny, for kids."}
    r = await c.post("/api/films", json={"prompt": "x", "project": {"id": "nope"}}, headers=me)
    check(r.status == 400, "a film's project must be one")
    r = await c.post(
        "/api/films",
        json={"prompt": "episode one, with a cast", "project": project},
        headers=me,
    )
    ep = (await r.json())["id"]
    f = films.Film.open(ep)
    check(
        f.record()["project"]["brief"] == "Short, funny, for kids."
        and mem.docs[ep].get("project_id") == P
        and os.path.exists(f.path("inputs", "pic_logo.png")),
        "an episode knows its project, and has its pictures",
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
                "result",
            ),
            (
                "a billing error",
                "login",
                reply("billing_error", "Credit balance too low", 400),
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

        # ------------------------------------------------ three films at once, three clients
        ids = []
        # film 0 is a priority plan's, and asks for the key from this machine (which otherwise
        # uses its login); film 1 is a Free plan's (branded), and asks for the login through the
        # tunnel (refused: api); film 2 asks for the login from this machine
        extra = [
            ({"X-Priority": "1"}, {"auth": "api"}),
            ({"Cf-Ray": "test", "X-Branding": "1", "X-Fps": "30"}, {"auth": "login"}),
            ({}, {"auth": "login"}),
        ]
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
            want = TTS_USD if i == 2 else EXPECT_USD  # on the login, Claude is not billed
            check(
                abs((st.get("cost_usd") or 0) - want) < 1e-4,
                "its cost, Claude + voice ($%s)" % st.get("cost_usd"),
            )
            rec = f.record()
            check(
                (rec.get("priority"), rec.get("auth")) == [(1, "api"), (0, "api"), (0, "login")][i]
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

        video = results[0].get("video_url", "")
        path = video[video.index("/files/") :]
        r = await c.get(path)
        check(r.status == 200 and len(await r.read()) > 100_000, "the signed URL plays")
        check((await c.get(path.replace("&sig=", "&sig=0"))).status == 401, "a tampered one not")
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
            "any other failure on the login is not retried on the key (%s)" % su.get("error"),
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
            and rec["resumed"]["earlier_usd"] == 0.5,
            "what the stopped attempt spent is carried, not replaced (%s)" % rec["claude_cost_usd"],
        )
        check(
            doc["state"] == "done"
            and [x["message_id"] for x in doc["calls"]]
            == ["msg_before", "msg_resume_" + stopped.id],
            "the record keeps both attempts' calls",
        )
        check(resume.refuse(stopped, False) is not None, "a done film is not picked up again")

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
        for f in (writing, rendering):  # the next server's memory starts empty
            server.JOBS.pop(f.id, None)
        await server.recover(None)
        st_r = await wait_for(c, auth, rendering.id)
        check(
            st_r.get("status") == "done" and abs(st_r.get("claude_cost_usd", 0) - 0.25) < 1e-9,
            "and the next server finishes it, keeping Claude's cost",
        )
        crashed = films.Film.create("left mid-Claude by a crash", 5, "drawn", client="u:s3")
        crashed.update(state="claude")
        with open(crashed.path("events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "tool", "text": "edited film.js", "t": 12.5}) + "\n")
        await server.recover(None)
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
