#!/usr/bin/env python
"""Sketch Studio: one line of text in, a short sketch film out, written by Claude.

    python studio/agent.py --smoke [--auth login]      one-turn check: key source, model, cost
    python studio/agent.py --costs                     what the runs have cost (kitcut.studio_runs)
    python studio/agent.py --sync                      send runs the database missed (the outbox)
    python studio/agent.py --announce <url>|off        tell the public site where the tunnel is
    python studio/agent.py "a paper plane ..."         a whole film from the command line
    python studio/server.py                            the web page (http://127.0.0.1:8765)

Claude (Opus 5.5) runs through the Claude Agent SDK, Claude Code's agent loop as a library, inside
one film's sandbox (film.py): its working directory is the film's folder, it reads and writes only
there (guard.py), and it drives the pipeline through the studio's tools (tools.py) -- there is no
shell. It writes film.js, score.json and sfx.json (and the narration, and for a painted film the
paintings), renders review stills and looks at them, and fixes what it sees. The studio then mixes
the soundtrack and renders the video with the ordinary sketch scripts.

Several films are made at once: each waits for a free Claude slot, then shares the machine through
the scheduler (sched.py). Two ways to pay for Claude:
    --auth api     ANTHROPIC_API_KEY, a private config folder per film (the public site)
    --auth login   this machine's Claude Code login (local and internal runs only)
"""

import sys
import os
import re
import json
import time
import asyncio
import argparse
import contextlib
from datetime import datetime
from importlib import import_module

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

sys.path.insert(0, HERE)
import procs  # noqa: E402
import film as films  # noqa: E402

# the studio's keys, out of the environment before anything is started (procs.py)
procs.load_secrets(os.environ.get("STUDIO_ENV_FILE") or os.path.join(films.REPO, ".env"))

import store  # noqa: E402
from film import (  # noqa: E402
    HOME,
    KIT,
    LENGTHS,
    LOOKS,
    MADE,
    RELEASE,
    Film,
    limits,
)
from guard import _path, guard, pin_after, pin_paint, pin_vo  # noqa: E402
from sched import Clock, Sched, waiting_text  # noqa: E402
from tools import Tools  # noqa: E402

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

ROOT = KIT
# Opus only: the drawing is the product, and a smaller model's films are not worth the saving
MODEL = "claude-opus-5-5"
# how long Claude may work on a film, and what it may spend, grow with the film's length:
# film.limits() (15 min of working time for up to 15 s; waiting for the machine does not count)


# ------------------------------------------------------------------ the environment Claude runs in
def claude_env(film=None, auth="api"):
    """What Claude Code is started with, on top of the (already secret-free) environment.
    api: the key and a private config folder per film, so a run can pick up no local login,
    settings or memory; login: this machine's Claude Code login and its config folder."""
    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # an organisation without zero data retention (e.g. a HIPAA one) gets a 400 for the
        # context-management beta Claude Code sends by default; a short film never needs it
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        # every tool is listed up front (there are only a few), and none is deferred
        "ENABLE_TOOL_SEARCH": "false",
        # none of the account's claude.ai connectors: the studio's tools are the only ones
        "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
        # a studio tool may wait for the machine; the tools time out on their own
        "MCP_TOOL_TIMEOUT": str(30 * 60 * 1000),
    }
    if auth == "api":
        key = procs.secret("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY is not set (put it in the studio's .env)")
        cfg = film.claude_dir if film else os.path.join(HOME, "claude", "_smoke")
        os.makedirs(cfg, exist_ok=True)
        env.update(ANTHROPIC_API_KEY=key, CLAUDE_CONFIG_DIR=cfg)
    return env


def _read(*parts):
    with open(os.path.join(KIT, *parts), encoding="utf-8") as f:
        return f.read()


def system_prompt(look):
    """prompt.md with the engine, the cast, the example and the sound notation filled in, read
    fresh so it always matches the code. It depends only on the look -- the film's own facts
    (its length, the prompt) come in the first message -- so films made close together share
    Claude's prompt cache."""
    A = import_module("_sketchaudio")
    ref = _read("docs", "reference.md")
    a = ref.index("**Score notation**")
    b = ref.index("### The picture: `sketch-render.py`")
    audio = _read("scripts", "_sketchaudio.py")
    doc = audio.split('"""')[1]
    notation = doc[doc.index("Score notation") :].split("Not an entry script")[0].strip()
    fx = "\n".join(re.findall(r"^def fx_(\w+\(.*\)):", audio, re.MULTILINE))
    # the cache is shared by every film on the machine: only real instrument names are listed
    sf = os.path.join(KIT, "models", "soundfonts", "FluidR3_GM")
    inst = sorted(n for n in (os.listdir(sf) if os.path.isdir(sf) else []) if n in A.GM)
    vo_mod = import_module("sketch-vo")  # the voice list lives with the Gemini backend
    fill = {
        "VOICES": ", ".join(vo_mod.GEMINI_VOICES),
        "ENGINE": _read("sketch", "engine.js"),
        "PROPS": _read("sketch", "props.js"),
        "EXAMPLE_FILM": _read("config", "sketch", "example", "film.js"),
        "EXAMPLE_SCORE": _read("config", "sketch", "example", "score.json"),
        "EXAMPLE_SFX": _read("config", "sketch", "example", "sfx.json"),
        "NOTATION": ref[a:b].strip() + "\n\n```\n" + notation + "\n```",
        "FX": fx,
        "INSTRUMENTS": ", ".join(inst) or "(none yet)",
    }
    # the look's own sections (studio/looks/<look>.md, "## NAME" headed) go in first, since
    # they carry placeholders of their own
    sections = {}
    for part in _read("studio", "looks", look + ".md").split("\n## "):
        name, _, body = part.lstrip("#").strip().partition("\n")
        sections["LOOK_" + name.strip()] = body.strip() + (
            "\n" if name.strip() in ("FILES", "COMMANDS") and body.strip() else ""
        )
    text = re.sub(
        r"\{(LOOK_[A-Z]+)\}", lambda m: sections.get(m.group(1), ""), _read("studio", "prompt.md")
    )
    return re.sub(r"\{([A-Z_]+)\}", lambda m: fill.get(m.group(1), m.group(0)), text)


def ask(film):
    """The first message: the film's own facts, then the visitor's prompt."""
    n = film.length
    return (
        "Make the film.\n\nLength: %d seconds (fixed). Narration: about %d words, ending by "
        "about %d s.\n\nPrompt: %s"
        % (n, round(n * 2.2 - 3), n - 1, film.record().get("prompt", "").strip())
    )


def _describe(name, inp, film):
    """A one-line account of a tool call for the page."""
    rel = lambda p: os.path.relpath(_path(p, film), film.dir).replace("\\", "/")  # noqa: E731
    if name == "Write":
        n = str(inp.get("content", "")).count("\n") + 1
        return "wrote %s (%d lines)" % (rel(inp.get("file_path")), n)
    if name == "Edit":
        return "edited %s" % rel(inp.get("file_path"))
    if name == "Read":
        p = rel(inp.get("file_path"))
        if p.endswith("images/sheet.jpg"):
            return "looking at the paintings"
        return "looking at the review sheet" if p.endswith("sheet.png") else "read %s" % p
    tool = name.removeprefix("mcp__studio__")
    if tool == "check":
        return "checking film.js for syntax errors"
    if tool == "stills":
        return "rendering %d review stills" % len(inp.get("times") or [])
    if tool == "sound":
        return "rendering the soundtrack"
    if tool == "voice":
        if inp.get("retake_line") is not None:
            return "recording line %s again" % inp["retake_line"]
        return "recording the narration (Gemini TTS)"
    if tool == "paint":
        return (
            "repainting %s" % ", ".join(inp["retake"])
            if inp.get("retake")
            else ("painting the scenes (Muse)")
        )
    return name


def _result_text(block):
    c = block.content
    if isinstance(c, list):
        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


# ------------------------------------------------------------------ what it costs
# USD per million tokens, from the price table inside Claude Code 2.1.281 (the CLI this SDK
# bundles). Sonnet is here only to price a run already on record; the studio runs MODEL.
PRICES = {
    "claude-opus-5-5": {"in": 4, "out": 20, "w5m": 5, "w1h": 8, "read": 0.2},
    "claude-sonnet-5": {"in": 2, "out": 10, "w5m": 2.5, "w1h": 4, "read": 0.2},
}
# every run's record lives in kitcut's MongoDB (store.py); the outbox holds what could not be sent
STORE = store.MongoStore(uri=procs.secret("MONGODB_URI"), outbox=os.path.join(HOME, "outbox.jsonl"))


def _price(model, t):
    p = PRICES.get(model, PRICES[MODEL])
    return (
        t["input"] * p["in"]
        + t["output"] * p["out"]
        + t["cache_read"] * p["read"]
        + t["cache_write_5m"] * p["w5m"]
        + t["cache_write_1h"] * p["w1h"]
    ) / 1e6


def _tokens(u):
    w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    return {
        "input": u.get("input_tokens") or 0,
        "output": u.get("output_tokens") or 0,
        "cache_read": u.get("cache_read_input_tokens") or 0,
        "cache_write_5m": (u.get("cache_creation_input_tokens") or 0) - w1h,
        "cache_write_1h": w1h,
    }


class Meter:
    """Token counts per API response, priced as they arrive, so a run cut short (a timeout,
    a crash, a stop) is still costed. The SDK reports its own total only at the very end."""

    def __init__(self, model=MODEL):
        self.model, self.msgs = model, {}

    def add(self, msg_id, usage, model=None, at=None):
        if msg_id and usage:
            # one response arrives in parts; the last part carries the final counts
            first = self.msgs.get(msg_id, {}).get("at")
            self.msgs[msg_id] = {
                "usage": usage,
                "model": model or self.model,
                "at": first or at or store.now(),
            }

    def tokens(self):
        t = dict.fromkeys(("input", "output", "cache_read", "cache_write_5m", "cache_write_1h"), 0)
        for m in self.msgs.values():
            for k, v in _tokens(m["usage"]).items():
                t[k] += v
        return t

    def usd(self):
        return sum(_price(m["model"], _tokens(m["usage"])) for m in self.msgs.values())

    def calls(self):
        """One entry per Claude API response, for the run's record."""
        return [
            {"message_id": k, "at": m["at"], "model": m["model"], **_tokens(m["usage"])}
            | {"cost_usd": round(_price(m["model"], _tokens(m["usage"])), 6)}
            for k, m in self.msgs.items()
        ]


def runs():
    """Every run on record, oldest first."""
    return STORE.runs()


def spend_summary(rows=None):
    """Totals over the runs on record: all time, today, this month (local time), per source."""
    rows = runs() if rows is None else rows
    today, month = datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m")
    local = lambda r: (
        r["created_at"].astimezone().strftime("%Y-%m-%d") if r.get("created_at") else ""
    )  # noqa: E731
    films_ = [r for r in rows if r.get("kind") != "smoke"]
    ok = [r for r in films_ if r.get("ok")]
    total = lambda rs: round(sum(r.get("cost_usd") or 0 for r in rs), 4)  # noqa: E731
    return {
        "total_usd": total(rows),
        "today_usd": total([r for r in rows if local(r) == today]),
        "month_usd": total([r for r in rows if local(r).startswith(month)]),
        "runs": len(rows),
        "films_ok": len(ok),
        "films_failed": len(films_) - len(ok),
        "avg_usd_per_film": round(total(ok) / len(ok), 4) if ok else None,
        "by_source": {
            s: total([r for r in rows if r.get("source") == s])
            for s in sorted({r.get("source", "?") for r in rows})
        },
    }


def claude_cli():
    """The newest installed Claude Code (auth=login). A machine can have several (npm, WinGet,
    the desktop app), and an old one refuses new models ("version 2.1.280 or newer is
    required"). Only real executables: the SDK will not start a .cmd shim."""
    import shutil
    import subprocess

    found = [shutil.which("claude.exe"), shutil.which("claude")]
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout
        found.append(
            os.path.join(root.strip(), "@anthropic-ai", "claude-code", "bin", "claude.exe")
        )
    best = None
    for exe in {f for f in found if f and os.path.exists(f)}:
        if os.name == "nt" and not exe.lower().endswith(".exe"):
            continue
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
            ver = tuple(int(x) for x in re.findall(r"\d+", out.stdout)[:3])
        except (OSError, subprocess.TimeoutExpired, ValueError):
            continue
        if ver and (best is None or ver > best[0]):
            best = (ver, exe)
    if not best:
        sys.exit("the Claude Code CLI is not installed (npm i -g @anthropic-ai/claude-code)")
    return best[1]


async def run_claude(film, emit, meter, tools, auth="api"):
    """Claude's part: write, review and fix. Returns the SDK's ResultMessage (or None)."""
    pending, result = {}, None

    async def pre_tool(inp, tool_use_id, ctx):
        ok, why = guard(inp["tool_name"], inp["tool_input"], film)
        if not ok:
            emit({"type": "blocked", "text": why})
        out = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if ok else "deny"}
        if not ok:
            out["permissionDecisionReason"] = why
        return {"hookSpecificOutput": out}

    async def can_use(name, inp, ctx):  # backstop: the hook above decides first
        ok, why = guard(name, inp, film)
        return PermissionResultAllow() if ok else PermissionResultDeny(message=why)

    async def post_tool(inp, tool_use_id, ctx):
        # after a write: put back what the studio decides, and say what else is wrong
        note = pin_after((inp.get("tool_input") or {}).get("file_path"), film)
        if note:
            emit({"type": "blocked", "text": note})
            return {
                "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}
            }
        return {}

    # by file: with the engine and the cast inlined it is ~80 KB, more than twice the length
    # Windows allows a command line (the spawn then fails as "Claude Code not found")
    sp = film.path("temp", "system-prompt.md")
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(system_prompt(film.look))
    opts = ClaudeAgentOptions(
        model=MODEL,
        cwd=film.dir,
        system_prompt={"type": "file", "path": sp},
        tools=["Read", "Write", "Edit"],
        mcp_servers={"studio": tools.server()},
        strict_mcp_config=True,
        setting_sources=[],
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool])],
            "PostToolUse": [HookMatcher(matcher="Write|Edit", hooks=[post_tool])],
        },
        can_use_tool=can_use,
        max_turns=50,
        max_budget_usd=limits(film.length)["budget_usd"],
        # a review sheet of painted frames is a PNG of several MB, and it comes back to the SDK
        # as one message (the default limit, 1 MB, failed a painted film)
        max_buffer_size=64 * 1024 * 1024,
        env=claude_env(film, auth),
        cli_path=claude_cli() if auth == "login" else None,
    )
    async with ClaudeSDKClient(options=opts) as client:
        await client.query(ask(film))
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                d = msg.data
                emit(
                    {
                        "type": "init",
                        "model": d.get("model"),
                        "key": d.get("apiKeySource") or auth,
                        "tools": [t for t in d.get("tools", []) if t.startswith("mcp__")],
                    }
                )
            elif isinstance(msg, AssistantMessage):
                before = meter.usd()
                meter.add(msg.message_id or msg.uuid, msg.usage, msg.model)
                if meter.usd() != before:
                    emit({"type": "cost", "usd": round(meter.usd(), 4)})
                for b in msg.content:
                    if isinstance(b, TextBlock) and b.text.strip():
                        emit({"type": "say", "text": b.text.strip()})
                    elif isinstance(b, ToolUseBlock):
                        pending[b.id] = (b.name, b.input)
                        emit({"type": "tool", "text": _describe(b.name, b.input, film)})
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for b in msg.content:
                    if not isinstance(b, ToolResultBlock):
                        continue
                    pending.pop(b.tool_use_id, None)
                    text = _result_text(b)
                    if b.is_error and "hook error" not in text:  # denials were reported
                        emit({"type": "fail", "text": text.strip()[-400:]})
            elif isinstance(msg, ResultMessage):
                result = msg
    return result


async def _within(coro, clock, lim):
    """Run Claude's part, stopping it past its working time (the clock does not count waits for
    the machine) or its wall time (lim: film.limits)."""
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=2)
            if done:
                return task.result()
            if clock.active() > lim["claude_s"] or clock.wall() > lim["wall_s"]:
                raise TimeoutError()
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task


# ------------------------------------------------------------------ one film
def _spend(film, *parts):
    p = film.path(*parts)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


async def save(run_id, fields, final=False):
    """A record write off the event loop: MongoDB may take seconds to answer, and every film
    shares this loop."""
    return await asyncio.to_thread(STORE.save, run_id, fields, final)


async def make_film(film, emit=None, sched=None, auth="api", finish_only=False, control=None):
    """The whole film, from its Claude slot to the video. Every step is reported through
    emit(dict); returns the final summary. Whatever happens, the run's cost goes to
    kitcut.studio_runs (STORE) and studio.json.

    finish_only: Claude's part is already done (a film a restart interrupted while mixing or
    rendering); only the soundtrack and the video are made. control: a dict the server may set
    {"requeue": True} in before it cancels a film still waiting for its slot -- the film then
    stays queued for the next server instead of being marked cancelled."""
    emit = emit or (lambda ev: None)
    sched = sched or Sched()
    control = control if control is not None else {}
    rec = film.record()
    prompt, length, look = rec.get("prompt", ""), film.length, film.look
    fps = 60
    with contextlib.suppress(OSError, ValueError):
        with open(film.manifest, encoding="utf-8") as f:
            fps = json.load(f).get("fps", 60)
    t0, stages, meter, res = time.time(), {}, Meter(), None
    clock = Clock()
    tools = Tools(film, sched, emit, clock)
    billed = auth == "api"  # on the login, Claude's tokens are covered by the plan
    summary = {
        "prompt": prompt,
        "model": MODEL,
        "length": length,
        "look": look,
        "release": RELEASE,
        "auth": auth,
    }
    emit({"type": "job", "id": film.id, "model": MODEL, "length": length, "look": look})

    def price():
        # the SDK's own figure when the run reached its end; the meter's when it did not
        metered = round(meter.usd(), 4)
        sdk = res.total_cost_usd if res is not None else None
        claude = round(sdk, 4) if sdk is not None else metered
        tts_rows = _spend(film, "audio", "vo", "spend.jsonl")
        img_rows = _spend(film, "images", "spend.jsonl")
        tts = round(sum(r["cost_usd"] for r in tts_rows), 6)
        img = round(sum(r.get("cost_usd") or 0 for r in img_rows), 6)
        if finish_only and not meter.msgs:  # Claude's part was costed by the earlier server
            claude = rec.get("claude_cost_usd") or 0
        summary.update(
            # everything this film cost: Claude + the voice + the paintings
            cost_usd=round((claude if billed else 0) + tts + img, 4),
            claude_cost_usd=claude,
            claude_billed=billed,
            via="sdk" if billed else "login",
            image_cost_usd=img,
            images=len(img_rows),
            tts_cost_usd=tts,
            tts_tokens={
                "input": sum(r["input"] for r in tts_rows),
                "output": sum(r["output"] for r in tts_rows),
            },
            tts_model=tts_rows[-1]["model"] if tts_rows else None,
            cost_metered_usd=metered,
            tokens=meter.tokens(),
        )

    loop = asyncio.get_running_loop()
    saved_at = [time.time()]
    outer = emit

    def emit(ev):  # noqa: F811 -- the same emit, keeping the record's cost current as it grows
        outer(ev)
        if ev["type"] == "cost" and time.time() - saved_at[0] > 5:
            saved_at[0] = time.time()
            price()
            now = {
                "cost_usd": summary["cost_usd"],
                "tokens": meter.tokens(),
                "calls": meter.calls(),
            }
            loop.run_in_executor(None, STORE.save, film.id, now)

    tools.emit = emit

    def on_wait(pool, ahead):
        emit({"type": "wait", "pool": pool, "ahead": ahead, "text": waiting_text(pool, ahead)})

    state = "error"
    try:
        if not finish_only:
            async with sched["claude"].hold(1, film.id, on_wait, priority=rec.get("priority", 0)):
                clock.t0, clock.paused = time.time(), 0.0  # the queue was not Claude's time
                film.update(state="claude", started=datetime.now().isoformat(timespec="seconds"))
                await save(film.id, {"state": "running", "started_at": store.now()})
                emit(
                    {
                        "type": "stage",
                        "name": "claude",
                        "text": "Claude is writing and reviewing the film",
                    }
                )
                s = time.time()
                res = await _within(
                    run_claude(film, emit, meter, tools, auth), clock, limits(length)
                )
                stages["claude"] = time.time() - s
                stages["waited"] = clock.paused
            price()
            if res is not None:
                summary.update(turns=res.num_turns, claude_said=res.result, session=res.session_id)
                if res.is_error:
                    raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
            missing = [f for f in MADE if not os.path.exists(film.path(f))]
            if missing:
                raise RuntimeError("Claude finished without writing %s" % ", ".join(missing))
            film.update(state="finishing", **summary)
            await save(film.id, {"state": "finishing"})
        pin_vo(film)  # whatever Claude left there, the backends and models stay the studio's
        pin_paint(film)

        s = time.time()
        emit({"type": "stage", "name": "sound", "text": "Mixing the soundtrack"})
        wav = film.path("audio", "final.wav")
        deps = [film.path("audio", "vo", "timeline.json")] + [film.path(f) for f in film.editable()]
        if not _newer(wav, *deps):
            await tools.sound(log=True)
        stages["sound"] = time.time() - s

        s = time.time()
        emit(
            {"type": "stage", "name": "render", "text": "Rendering %d frames" % round(length * fps)}
        )
        await tools.render()
        stages["render"] = time.time() - s
        changed = film.engine_diff()
        summary.update(
            ok=True,
            video="film.mp4",
            poster="film_poster.png",
            engine_changed=changed,
            seconds=round(time.time() - t0, 1),
            stages={k: round(v, 1) for k, v in stages.items()},
        )
        state = "done"
        emit({"type": "done", **summary})
    except asyncio.CancelledError:
        tools.kill()
        if control.get("requeue") and film.state == "queued":
            state = "queued"  # the next server makes it; nothing was spent
            raise
        state = "cancelled"
        summary.update(ok=False, error="cancelled", seconds=round(time.time() - t0, 1))
        emit({"type": "error", "text": "The film was cancelled."})
        raise
    except Exception as e:  # noqa: BLE001 -- every failure goes to the page, not just the console
        text = str(e) or type(e).__name__
        if isinstance(e, TimeoutError):
            text = "Claude ran past the %d-minute limit" % (limits(length)["claude_s"] // 60)
        summary.update(ok=False, error=text, seconds=round(time.time() - t0, 1))
        emit({"type": "error", "text": text})
    finally:
        tools.kill()  # nothing of this film's keeps running
        if state != "queued":
            summary.setdefault("ok", False)
            if not summary["ok"]:
                summary.setdefault("error", "stopped before it finished")
                summary.setdefault("seconds", round(time.time() - t0, 1))
            price()
            film.update(
                state=state, **summary, finished=datetime.now().isoformat(timespec="seconds")
            )
            final = {
                "state": {"done": "done", "cancelled": "cancelled"}.get(state, "failed"),
                "ok": summary["ok"],
                "error": summary.get("error"),
                "calls": meter.calls(),
                "turns": summary.get("turns"),
                "seconds": summary.get("seconds"),
                "stages": {k: round(v, 1) for k, v in stages.items()} or None,
                "session_id": summary.get("session"),
                "engine_changed": summary.get("engine_changed"),
                "finished_at": store.now(),
            } | {
                k: summary[k]
                for k in (
                    "cost_usd",
                    "claude_cost_usd",
                    "claude_billed",
                    "via",
                    "image_cost_usd",
                    "images",
                    "tts_cost_usd",
                    "tts_tokens",
                    "tts_model",
                    "cost_metered_usd",
                    "tokens",
                    "release",
                    "auth",
                )
            }
            # shielded: a cancelled film's record must still be written
            await asyncio.shield(save(film.id, final, final=True))
    return summary


def _newer(a, *bs):
    """Does file a exist and postdate every existing b?"""
    if not os.path.exists(a):
        return False
    t = os.path.getmtime(a)
    return all(not os.path.exists(b) or os.path.getmtime(b) <= t for b in bs)


def first_record(film, source, client):
    """The run's record as it is when the film is asked for (state queued), so it counts toward
    the day's limits from the first moment."""
    rec = film.record()
    return {
        "kind": "film",
        "source": source,
        "client": client,
        "host": store.HOST,
        "prompt": rec.get("prompt"),
        "model": MODEL,
        "job": film.id,
        "length": rec.get("length"),
        "look": rec.get("look"),
        "release": RELEASE,
        "priority": rec.get("priority", 0),
        "auth": rec.get("auth", "api"),
        "state": "queued",
        "cost_usd": 0.0,
    }


# ------------------------------------------------------------------ command line
async def smoke(auth="api"):
    """One turn, no tools: proves the key (or the login), the model and where the bill goes."""
    opts = ClaudeAgentOptions(
        model=MODEL,
        cwd=HOME if os.path.isdir(HOME) else KIT,
        system_prompt="Reply with exactly: OK",
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=claude_env(None, auth),
        cli_path=claude_cli() if auth == "login" else None,
    )
    t, meter = time.time(), Meter()
    async for m in query(prompt="ping", options=opts):
        if isinstance(m, SystemMessage) and m.subtype == "init":
            print("  key source: %s" % m.data.get("apiKeySource"))
            print("  model:      %s" % m.data.get("model"))
            print("  mcp:        %s" % ([s.get("name") for s in m.data.get("mcp_servers", [])]))
        elif isinstance(m, AssistantMessage):
            meter.add(m.message_id or m.uuid, m.usage, m.model)
        elif isinstance(m, ResultMessage):
            print("  reply:      %r%s" % (m.result, "  (ERROR)" if m.is_error else ""))
            print("  cost:       $%.4f in %.1fs" % (m.total_cost_usd or 0, time.time() - t))
            saved = STORE.save(
                "smoke:%s" % m.session_id,
                {
                    "kind": "smoke",
                    "source": "smoke",
                    "client": "local",
                    "host": store.HOST,
                    "prompt": "ping",
                    "model": MODEL,
                    "auth": auth,
                    "state": "failed" if m.is_error else "done",
                    "ok": not m.is_error,
                    "error": m.result if m.is_error else None,
                    "cost_usd": round(m.total_cost_usd or 0, 6) if auth == "api" else 0.0,
                    "cost_metered_usd": round(meter.usd(), 6),
                    "tokens": meter.tokens(),
                    "calls": meter.calls(),
                    "turns": m.num_turns,
                    "seconds": round(time.time() - t, 1),
                    "session_id": m.session_id,
                    "finished_at": store.now(),
                },
                final=True,
            )
            print(
                "  logged:     %s"
                % ("kitcut.studio_runs" if saved else "outbox (MongoDB unreachable)")
            )


def print_costs(last=20):
    """The runs on record (kitcut.studio_runs): the latest, and the totals."""
    rows = runs()
    if not rows:
        print("no runs in kitcut.%s yet" % store.COLLECTION)
        return
    print(
        "  %-16s  %-8s  %-5s  %8s  %7s  %s" % ("time", "source", "ok", "cost", "seconds", "prompt")
    )
    for r in rows[-last:]:
        print(
            "  %-16s  %-8s  %-5s  %8s  %7s  %s"
            % (
                r["created_at"].astimezone().strftime("%Y-%m-%d %H:%M"),
                r.get("source", ""),
                "yes" if r.get("ok") else "NO",
                "$%.4f" % (r.get("cost_usd") or 0),
                r.get("seconds") if r.get("seconds") is not None else "",
                (r.get("prompt") or "")[:60],
            )
        )
    s = spend_summary(rows)
    print(
        "\n  total $%.2f over %d runs (%d films made, %d failed)   today $%.2f   this month $%.2f"
        % (
            s["total_usd"],
            s["runs"],
            s["films_ok"],
            s["films_failed"],
            s["today_usd"],
            s["month_usd"],
        )
    )
    if s["avg_usd_per_film"] is not None:
        print("  average per finished film: $%.2f" % s["avg_usd_per_film"])
    print("  by source: %s" % ", ".join("%s $%.2f" % kv for kv in s["by_source"].items()))
    print("  from MongoDB kitcut.%s" % store.COLLECTION)
    if STORE.outbox and os.path.exists(STORE.outbox):
        print("  NOT YET SENT: runs waiting in %s (python studio/agent.py --sync)" % STORE.outbox)


def _print(ev):
    k = ev["type"]
    if k == "log":
        print("      " + ev["text"])
    elif k == "say":
        print("  claude: " + ev["text"].replace("\n", "\n          "))
    elif k in ("tool", "stage", "blocked", "fail", "error", "wait"):
        print("  %-7s %s" % (k, ev.get("text")))
    elif k == "cost":
        print("  cost    $%.4f so far" % ev["usd"])
    elif k == "init":
        print("  init    model %s, key from %s, tools %s" % (ev["model"], ev["key"], ev["tools"]))
    elif k in ("job", "image"):
        print("  %-7s %s" % (k, ev.get("id") or ev.get("path")))
    elif k == "done":
        print(
            "\n  done in %.0fs  %s  $%.2f  %s turns"
            % (ev["seconds"], ev["stages"], ev.get("cost_usd") or 0, ev.get("turns"))
        )
    sys.stdout.flush()


def main():
    _env.utf8_stdio()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("prompt", nargs="?", help="what the film is about")
    ap.add_argument("--seconds", type=int, default=LENGTHS[0], choices=LENGTHS)
    ap.add_argument("--look", default=LOOKS[0], choices=LOOKS)
    ap.add_argument(
        "--auth",
        default="api",
        choices=("api", "login"),
        help="api: ANTHROPIC_API_KEY (billed per token); login: this machine's Claude Code login",
    )
    ap.add_argument("--smoke", action="store_true", help="a one-turn check, no film")
    ap.add_argument("--costs", action="store_true", help="print what the runs cost, and totals")
    ap.add_argument("--sync", action="store_true", help="send runs the database missed")
    ap.add_argument(
        "--announce",
        metavar="URL",
        help="record the tunnel URL the public site should use ('off' when stopping)",
    )
    args = ap.parse_args()
    if args.announce:
        url = None if args.announce == "off" else args.announce.rstrip("/")
        STORE.announce(url)
        print("kitcut.studio_hosts: studio -> %s" % (url or "offline"))
        return
    if args.sync:
        sent, left = STORE.sync()
        print("sent %d run(s) to kitcut.%s; %d still waiting" % (sent, store.COLLECTION, left))
        return
    if args.costs:
        print_costs()
        return
    if args.smoke:
        asyncio.run(smoke(args.auth))
        return
    if not args.prompt:
        ap.error("give a prompt, or --smoke")
    film = Film.create(args.prompt, args.seconds, args.look, client="local", source="cli")
    print("  film    %s" % film.dir)

    async def go():
        await save(film.id, first_record(film, "cli", "local"))
        return await make_film(film, _print, Sched(), auth=args.auth)

    r = asyncio.run(go())
    if r.get("ok"):
        print("  %s" % film.path("outputs", "film.mp4"))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
