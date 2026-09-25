#!/usr/bin/env python
"""Sketch Studio: one line of text in, a 5-second sketch film out, written by Claude.

    python studio/agent.py --smoke                  one-turn API check: key source, model, cost
    python studio/agent.py --costs                  what the runs have cost (MongoDB kitcut.studio_runs)
    python studio/agent.py --sync                   send runs the database missed (the outbox)
    python studio/agent.py --announce <url>|off     tell the public site where the tunnel is
    python studio/agent.py "a paper plane ..."      a whole film from the command line
    python studio/server.py                         the web page (http://127.0.0.1:8765)

Claude (Opus 5.5) runs through the Claude Agent SDK, Claude Code's agent loop as a library. It
writes film.js, score.json and sfx.json into projects/studio-<stamp>/, renders review stills and
looks at them, and fixes what it sees. This script then renders the soundtrack and the video with the
ordinary sketch scripts.

It runs on ANTHROPIC_API_KEY from .env and a private Claude config folder (temp/studio-claude/),
so it never uses a local Claude Code login or its settings. guard() is the whole permission
model: Claude can read the repo (never .env), write three files in its own job folder, and run
four exact commands.
"""

import sys
import os
import re
import json
import time
import shlex
import shutil
import asyncio
import argparse
from datetime import datetime
from importlib import import_module

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

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

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))
# Opus only: the drawing is the product, and a smaller model's films are not worth the saving
MODEL = "claude-opus-5-5"
EDITABLE = ("film.js", "score.json", "sfx.json", "vo.json")
MADE = ("film.js", "score.json", "sfx.json")  # what a finished film must have
LENGTHS = (5, 10, 15)  # seconds a visitor may ask for
AGENT_TIMEOUT = 15 * 60
# the voice: Google's Gemini text-to-speech. 3.8 needs the Gemini API enabled in the service
# account's project; STUDIO_TTS_MODEL in .env overrides it (e.g. gemini-3.1-flash-tts-preview)
TTS_MODEL = "gemini-3.8-flash-tts"
# what Claude may not change in vo.json: the studio decides the backend, model and take count
VO_PINNED = {"tts": "gemini", "takes": 1, "lead": 0.5, "gap": 0.35}


def tts_model():
    return os.environ.get("STUDIO_TTS_MODEL", "").strip() or TTS_MODEL


# ------------------------------------------------------------------ the permission model
def _path(p):
    """A tool's path argument, absolute: relative to the repo root, posix or git-bash (/c/...)."""
    p = str(p or "").strip().strip("\"'")
    m = re.match(r"^/([a-zA-Z])/(.*)$", p) if os.name == "nt" else None
    if m:
        p = m.group(1) + ":/" + m.group(2)
    return os.path.normcase(os.path.abspath(os.path.join(ROOT, p)))


def _inside(p, base):
    base = os.path.normcase(os.path.abspath(base))
    return p == base or p.startswith(base + os.sep)


SECRET = re.compile(r"(^|[\\/])\.env[^\\/]*$|[\\/]\.(git|venv)([\\/]|$)", re.IGNORECASE)
SHELL_META = re.compile(r"[;&|<>`$\n]")
TIMES = re.compile(r"^\d+(\.\d+)?(,\d+(\.\d+)?)*$")


def guard(tool, inp, job):
    """(allowed, reason) for one tool call by Claude working in the job folder `job`."""
    job = os.path.normcase(os.path.abspath(job))
    if tool == "Read":
        p = _path(inp.get("file_path"))
        if _inside(p, ROOT) and not SECRET.search(p):
            return True, ""
        return False, "Read is limited to the kitcut repo, and never .env, .git or .venv."
    if tool in ("Write", "Edit"):
        p = _path(inp.get("file_path"))
        if os.path.dirname(p) == job and os.path.basename(p) in EDITABLE:
            return True, ""
        return False, "You can only write %s in your job folder." % ", ".join(EDITABLE)
    if tool == "Bash":
        return _bash_ok(inp.get("command", ""), job)
    return False, "%s is not available here: use Read, Write, Edit and the listed commands." % tool


def _bash_ok(cmd, job):
    usage = (
        "Only these commands run, one per call, from the working directory: "
        "`node --check <job>/film.js`, "
        "`python scripts/sketch-vo.py --manifest <job>/sketch.json [--only <n> --retake]`, "
        "`python scripts/sketch-render.py --manifest <job>/sketch.json --stills <t,t,...> [--sheet]`, "
        "`python scripts/sketch-render.py --manifest <job>/sketch.json --automation`, "
        "`python scripts/sketch-audio.py --manifest <job>/sketch.json [--levels]`."
    )
    if SHELL_META.search(cmd):
        return False, "No ;, &&, |, redirection or $(...). " + usage
    try:
        argv = shlex.split(cmd.strip())
    except ValueError:
        return False, usage
    if len(argv) == 3 and argv[:2] == ["node", "--check"]:
        ok = _path(argv[2]) == os.path.join(job, "film.js")
        return (True, "") if ok else (False, usage)
    if len(argv) < 4 or argv[0] not in ("python", "python3", "py") or argv[2] != "--manifest":
        return False, usage
    script = argv[1].replace("\\", "/").removeprefix("./")
    if _path(argv[3]) != os.path.join(job, "sketch.json"):
        return False, "Use your own manifest, %s. " % os.path.relpath(job, ROOT) + usage
    rest = argv[4:]
    if script == "scripts/sketch-audio.py":
        return (True, "") if set(rest) <= {"--levels", "--plan"} else (False, usage)
    if script == "scripts/sketch-vo.py":
        if rest in ([], ["--plan"]):
            return True, ""
        # one line again: --only <n> --retake, in either order
        if sorted(a for a in rest if not a.isdigit()) == ["--only", "--retake"] and len(rest) == 3:
            i = rest.index("--only")
            if i + 1 < len(rest) and rest[i + 1].isdigit():
                return True, ""
        return False, usage
    if script == "scripts/sketch-render.py":
        if rest == ["--automation"]:
            return True, ""
        flags = [a for a in rest if a != "--sheet"]
        if (
            len(flags) == 2
            and flags[0] == "--stills"
            and TIMES.match(flags[1])
            and rest.count("--sheet") <= 1
        ):
            return True, ""
    return False, usage


# ------------------------------------------------------------------ the environment Claude runs in
def child_env():
    """ANTHROPIC_API_KEY from .env and a private config folder: an API-billed run that cannot pick
    up a local Claude Code login, its settings or its memory.
    """
    _env.load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set (put it in .env)")
    # a Claude Code session that launches this passes its own CLAUDE_* variables down: drop them
    for k in list(os.environ):
        if k.startswith(("CLAUDE", "ANTHROPIC_")) and k not in (
            "ANTHROPIC_API_KEY",
            "CLAUDE_CODE_GIT_BASH_PATH",
        ):
            os.environ.pop(k)
    cfg = os.path.join(ROOT, "temp", "studio-claude")
    os.makedirs(cfg, exist_ok=True)
    return {
        "ANTHROPIC_API_KEY": key,
        "CLAUDE_CONFIG_DIR": cfg,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # an organisation without zero data retention (e.g. a HIPAA one) gets a 400 for the
        # context-management beta Claude Code sends by default; a 5-second film never needs it
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    }


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def system_prompt(job):
    """prompt.md with the engine, the cast, the example and the sound notation filled in, read
    fresh each run so the prompt always matches the code.
    """
    ref = _read("docs", "reference.md")
    a = ref.index("**Score notation**")
    b = ref.index("### The picture: `sketch-render.py`")
    audio = _read("scripts", "_sketchaudio.py")
    doc = audio.split('"""')[1]
    notation = doc[doc.index("Score notation") :].split("Not an entry script")[0].strip()
    fx = "\n".join(re.findall(r"^def fx_(\w+\(.*\)):", audio, re.MULTILINE))
    inst = sorted(os.listdir(os.path.join(ROOT, "models", "soundfonts", "FluidR3_GM")))
    with open(os.path.join(job, "sketch.json"), encoding="utf-8") as f:
        seconds = round(float(json.load(f)["duration"]))
    vo_mod = import_module("sketch-vo")  # the voice list lives with the Gemini backend
    fill = {
        "SECONDS": str(seconds),
        "WORDS": str(round(seconds * 2.2 - 3)),  # unhurried narration, with room to breathe
        "VOICES": ", ".join(vo_mod.GEMINI_VOICES),
        "JOB": os.path.relpath(job, ROOT).replace("\\", "/"),
        # what Claude's shell calls Python: macOS and many Linux systems only have python3
        "PY": "python" if shutil.which("python") else "python3",
        "ENGINE": _read("sketch", "engine.js"),
        "PROPS": _read("sketch", "props.js"),
        "EXAMPLE_FILM": _read("config", "sketch", "example", "film.js"),
        "EXAMPLE_SCORE": _read("config", "sketch", "example", "score.json"),
        "EXAMPLE_SFX": _read("config", "sketch", "example", "sfx.json"),
        "NOTATION": ref[a:b].strip() + "\n\n```\n" + notation + "\n```",
        "FX": fx,
        "INSTRUMENTS": ", ".join(inst),
    }
    text = _read("studio", "prompt.md")
    return re.sub(r"\{([A-Z_]+)\}", lambda m: fill.get(m.group(1), m.group(0)), text)


# ------------------------------------------------------------------ one film
def new_job(prompt, seconds=5):
    """projects/studio-<stamp>/ with the manifest (its length set) and an empty narration."""
    seconds = seconds if seconds in LENGTHS else LENGTHS[0]
    job = os.path.join(ROOT, "projects", "studio-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(job)
    with open(os.path.join(HERE, "template", "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    words = re.sub(r"\s+", " ", prompt).strip()
    m["title"] = (words[:60] + "...") if len(words) > 60 else words
    m["duration"], m["poster_t"] = float(seconds), round(seconds - 0.4, 2)
    with open(os.path.join(job, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    vo = {**VO_PINNED, "model": tts_model(), "voice": "Kore", "style": "", "language": "en"}
    with open(os.path.join(job, "vo.json"), "w", encoding="utf-8") as f:
        json.dump(vo | {"lines": []}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(job, "studio.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "prompt": prompt,
                "length": seconds,  # the film's; "seconds" is later how long making it took
                "started": datetime.now().isoformat(timespec="seconds"),
            },
            f,
            indent=2,
        )
    return job


def pin_vo(job):
    """Put back what Claude may not change in vo.json (backend, model, takes). Returns what it
    had to restore, or "" -- the PostToolUse hook tells Claude so."""
    p = os.path.join(job, "vo.json")
    try:
        with open(p, encoding="utf-8") as f:
            vo = json.load(f)
    except (OSError, ValueError) as e:
        return "vo.json is not valid JSON (%s); fix it" % e
    want = {**VO_PINNED, "model": tts_model()}
    wrong = {k: vo.get(k) for k, v in want.items() if vo.get(k) != v}
    if wrong:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(vo | want, f, indent=2, ensure_ascii=False)
        return "the studio sets %s in vo.json; restored %s" % (
            ", ".join(sorted(want)),
            ", ".join("%s=%r" % (k, want[k]) for k in sorted(wrong)),
        )
    return ""


def _describe(name, inp, job):
    """A one-line account of a tool call for the page."""
    rel = lambda p: os.path.relpath(_path(p), job).replace("\\", "/")  # noqa: E731
    if name == "Write":
        n = str(inp.get("content", "")).count("\n") + 1
        return "wrote %s (%d lines)" % (rel(inp.get("file_path")), n)
    if name == "Edit":
        return "edited %s" % rel(inp.get("file_path"))
    if name == "Read":
        p = rel(inp.get("file_path"))
        return "looking at the review sheet" if p.endswith("sheet.png") else "read %s" % p
    if name == "Bash":
        c = inp.get("command", "")
        if c.startswith("node --check"):
            return "checking film.js for syntax errors"
        m = re.search(r"--stills\s+(\S+)", c)
        if m:
            return "rendering %d review stills" % len(m.group(1).split(","))
        if "--automation" in c:
            return "tracing motion for the sound of air"
        if "sketch-audio" in c:
            return "rendering the soundtrack"
        if "sketch-vo" in c:
            return "recording the narration (Gemini TTS)"
        return c
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
STORE = store.MongoStore(outbox=os.path.join(ROOT, "projects", "studio-runs-outbox.jsonl"))


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
    films = [r for r in rows if r.get("kind") != "smoke"]
    ok = [r for r in films if r.get("ok")]
    total = lambda rs: round(sum(r.get("cost_usd") or 0 for r in rs), 4)  # noqa: E731
    return {
        "total_usd": total(rows),
        "today_usd": total([r for r in rows if local(r) == today]),
        "month_usd": total([r for r in rows if local(r).startswith(month)]),
        "runs": len(rows),
        "films_ok": len(ok),
        "films_failed": len(films) - len(ok),
        "avg_usd_per_film": round(total(ok) / len(ok), 4) if ok else None,
        "by_source": {
            s: total([r for r in rows if r.get("source") == s])
            for s in sorted({r.get("source", "?") for r in rows})
        },
    }


async def run_claude(prompt, job, emit, meter):
    """Claude's part: write, review and fix. Returns the SDK's ResultMessage (or None)."""
    pending, result, sheet_v = {}, None, [0]

    async def pre_tool(inp, tool_use_id, ctx):
        ok, why = guard(inp["tool_name"], inp["tool_input"], job)
        if not ok:
            emit({"type": "blocked", "text": why})
        out = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if ok else "deny"}
        if not ok:
            out["permissionDecisionReason"] = why
        return {"hookSpecificOutput": out}

    async def can_use(name, inp, ctx):  # backstop: the hook above decides first
        ok, why = guard(name, inp, job)
        return PermissionResultAllow() if ok else PermissionResultDeny(message=why)

    async def post_tool(inp, tool_use_id, ctx):
        # after any write to vo.json: put back the voice backend, model and take count
        p = str((inp.get("tool_input") or {}).get("file_path", ""))
        if not p.replace("\\", "/").endswith("vo.json"):
            return {}
        note = pin_vo(job)
        if note:
            emit({"type": "blocked", "text": note})
            return {
                "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}
            }
        return {}

    # by file: with the engine and the cast inlined it is ~80 KB, more than twice the length
    # Windows allows a command line (the spawn then fails as "Claude Code not found")
    sp = os.path.join(job, "temp", "system-prompt.md")
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(system_prompt(job))
    opts = ClaudeAgentOptions(
        model=MODEL,
        cwd=ROOT,
        system_prompt={"type": "file", "path": sp},
        tools=["Read", "Write", "Edit", "Bash"],
        setting_sources=[],
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool])],
            "PostToolUse": [HookMatcher(matcher="Write|Edit", hooks=[post_tool])],
        },
        can_use_tool=can_use,
        max_turns=50,
        max_budget_usd=float(os.environ.get("STUDIO_MAX_USD") or 5),
        env=child_env(),
    )
    with open(os.path.join(job, "sketch.json"), encoding="utf-8") as f:
        seconds = round(float(json.load(f)["duration"]))
    ask = "Make the film (%d seconds): %s" % (seconds, prompt.strip())
    async with ClaudeSDKClient(options=opts) as client:
        await client.query(ask)
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                d = msg.data
                emit({"type": "init", "model": d.get("model"), "key": d.get("apiKeySource")})
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
                        emit({"type": "tool", "text": _describe(b.name, b.input, job)})
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for b in msg.content:
                    if not isinstance(b, ToolResultBlock):
                        continue
                    name, inp = pending.pop(b.tool_use_id, ("", {}))
                    text = _result_text(b)
                    if b.is_error:
                        if "hook error" not in text:  # a guard denial was already reported
                            emit({"type": "fail", "text": text.strip()[-400:]})
                    elif name == "Bash" and "--stills" in inp.get("command", ""):
                        if os.path.exists(os.path.join(job, "outputs", "review", "sheet.png")):
                            sheet_v[0] += 1
                            emit({"type": "image", "path": "review/sheet.png", "v": sheet_v[0]})
            elif isinstance(msg, ResultMessage):
                result = msg
    return result


async def _step(argv, emit, label):
    """One pipeline script, its output streamed as log lines. Raises on failure."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-X",
        "utf8",
        *argv,
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    tail = []
    async for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip()
        if line.strip():
            tail = (tail + [line])[-12:]
            emit({"type": "log", "text": line})
    if await proc.wait() != 0:
        raise RuntimeError("%s failed:\n%s" % (label, "\n".join(tail)))


def _newer(a, *bs):
    """Does file a exist and postdate every existing b?"""
    if not os.path.exists(a):
        return False
    t = os.path.getmtime(a)
    return all(not os.path.exists(b) or os.path.getmtime(b) <= t for b in bs)


async def make_film(prompt, emit=None, job=None, source="cli", client="local"):
    """The whole film. Every step is reported through emit(dict); returns the final summary.
    Whatever happens, the run's cost goes to kitcut.studio_runs (STORE) and studio.json."""
    emit = emit or (lambda ev: None)
    job = job or new_job(prompt)
    rel = os.path.relpath(job, ROOT).replace("\\", "/")
    manifest = rel + "/sketch.json"
    t0, stages, meter, res = time.time(), {}, Meter(), None
    with open(os.path.join(job, "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    length, frames = round(float(m["duration"])), round(float(m["duration"]) * m.get("fps", 60))
    emit({"type": "job", "id": os.path.basename(job), "dir": rel, "model": MODEL, "length": length})
    summary = {"prompt": prompt, "model": MODEL, "dir": rel, "length": length}

    def tts_spend():
        # every sketch-vo run Claude made for this film appends what it spent (Gemini TTS)
        p = os.path.join(job, "audio", "vo", "spend.jsonl")
        rows = []
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                rows = [json.loads(x) for x in f if x.strip()]
        tok = {"input": sum(r["input"] for r in rows), "output": sum(r["output"] for r in rows)}
        return (
            round(sum(r["cost_usd"] for r in rows), 6),
            tok,
            (rows[-1]["model"] if rows else None),
        )

    def price():
        # the SDK's own figure when the run reached its end; the meter's when it did not
        metered = round(meter.usd(), 4)
        sdk = res.total_cost_usd if res is not None else None
        claude = round(sdk, 4) if sdk is not None else metered
        tts, tts_tok, tts_model_used = tts_spend()
        summary.update(
            cost_usd=round(claude + tts, 4),  # everything this film cost: Claude + the voice
            claude_cost_usd=claude,
            tts_cost_usd=tts,
            tts_tokens=tts_tok,
            tts_model=tts_model_used,
            cost_metered_usd=metered,
            tokens=meter.tokens(),
        )

    run_id, loop = os.path.basename(job), asyncio.get_running_loop()
    record = {
        "kind": "film",
        "source": source,
        "client": client,
        "host": store.HOST,
        "prompt": prompt,
        "model": MODEL,
        "job": rel,
        "length": length,
        "state": "running",
        "cost_usd": 0.0,
    }
    # on record before the first token is spent, and kept current while it runs
    await asyncio.to_thread(STORE.save, run_id, record)
    saved_at = [time.time()]
    outer = emit

    def emit(ev):
        outer(ev)
        if ev["type"] == "cost" and time.time() - saved_at[0] > 5:
            saved_at[0] = time.time()
            now = {
                "cost_usd": round(ev["usd"] + tts_spend()[0], 4),
                "tokens": meter.tokens(),
                "calls": meter.calls(),
            }
            loop.run_in_executor(None, STORE.save, run_id, now)

    try:
        emit(
            {"type": "stage", "name": "claude", "text": "Claude is writing and reviewing the film"}
        )
        s = time.time()
        res = await asyncio.wait_for(run_claude(prompt, job, emit, meter), AGENT_TIMEOUT)
        stages["claude"] = time.time() - s
        price()
        if res is not None:
            summary.update(turns=res.num_turns, claude_said=res.result, session=res.session_id)
            if res.is_error:
                raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
        missing = [f for f in MADE if not os.path.exists(os.path.join(job, f))]
        if missing:
            raise RuntimeError("Claude finished without writing %s" % ", ".join(missing))
        pin_vo(job)  # whatever Claude left there, the backend and model stay the studio's

        s = time.time()
        emit({"type": "stage", "name": "sound", "text": "Mixing the soundtrack"})
        with open(os.path.join(job, "sfx.json"), encoding="utf-8") as f:
            air = any(c.get("fx") == "air" for c in json.load(f))
        if air and not os.path.exists(os.path.join(job, "temp", "automation.json")):
            await _step(
                ["scripts/sketch-render.py", "--manifest", manifest, "--automation"],
                emit,
                "automation",
            )
        wav = os.path.join(job, "audio", "final.wav")
        timeline = os.path.join(job, "audio", "vo", "timeline.json")
        if not _newer(wav, timeline, *(os.path.join(job, f) for f in EDITABLE)):
            await _step(["scripts/sketch-audio.py", "--manifest", manifest], emit, "the soundtrack")
        stages["sound"] = time.time() - s

        s = time.time()
        emit({"type": "stage", "name": "render", "text": "Rendering %d frames" % frames})
        await _step(["scripts/sketch-render.py", "--manifest", manifest], emit, "the render")
        stages["render"] = time.time() - s

        summary.update(
            ok=True,
            video="film.mp4",
            poster="film_poster.png",
            seconds=round(time.time() - t0, 1),
            stages={k: round(v, 1) for k, v in stages.items()},
        )
        emit({"type": "done", **summary})
    except Exception as e:  # noqa: BLE001 -- every failure goes to the page, not just the console
        text = str(e) or type(e).__name__
        if isinstance(e, TimeoutError):
            text = "Claude ran past the %d-minute limit" % (AGENT_TIMEOUT // 60)
        summary.update(ok=False, error=text, seconds=round(time.time() - t0, 1))
        emit({"type": "error", "text": text})
    finally:  # also on a cancelled run (the server stopping): the tokens were still spent
        summary.setdefault("ok", False)
        if not summary["ok"]:
            summary.setdefault("error", "stopped before it finished")
            summary.setdefault("seconds", round(time.time() - t0, 1))
        price()
        with open(os.path.join(job, "studio.json"), encoding="utf-8") as f:
            rec = json.load(f)
        rec.update(summary, finished=datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(job, "studio.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        STORE.save(
            run_id,
            record
            | {
                "state": "done" if summary["ok"] else "failed",
                "ok": summary["ok"],
                "error": summary.get("error"),
                "cost_usd": summary["cost_usd"],
                "claude_cost_usd": summary["claude_cost_usd"],
                "tts_cost_usd": summary["tts_cost_usd"],
                "tts_tokens": summary["tts_tokens"],
                "tts_model": summary["tts_model"],
                "cost_metered_usd": summary["cost_metered_usd"],
                "tokens": summary["tokens"],
                "calls": meter.calls(),
                "turns": summary.get("turns"),
                "seconds": summary.get("seconds"),
                "stages": {k: round(v, 1) for k, v in stages.items()} or None,
                "session_id": summary.get("session"),
                "finished_at": store.now(),
            },
            final=True,
        )
    return summary


# ------------------------------------------------------------------ command line
async def smoke():
    """One turn, no tools: proves the key, the model and where the bill goes."""
    opts = ClaudeAgentOptions(
        model=MODEL,
        cwd=ROOT,
        system_prompt="Reply with exactly: OK",
        tools=[],
        setting_sources=[],
        max_turns=1,
        env=child_env(),
    )
    t, meter = time.time(), Meter()
    async for m in query(prompt="ping", options=opts):
        if isinstance(m, SystemMessage) and m.subtype == "init":
            print("  key source: %s" % m.data.get("apiKeySource"))
            print("  model:      %s" % m.data.get("model"))
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
                    "state": "failed" if m.is_error else "done",
                    "ok": not m.is_error,
                    "error": m.result if m.is_error else None,
                    "cost_usd": round(m.total_cost_usd or 0, 6),
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
    elif k in ("tool", "stage", "blocked", "fail", "error"):
        print("  %-7s %s" % (k, ev.get("text")))
    elif k == "cost":
        print("  cost    $%.4f so far" % ev["usd"])
    elif k == "init":
        print("  init    model %s, key from %s" % (ev["model"], ev["key"]))
    elif k in ("job", "image"):
        print("  %-7s %s" % (k, ev.get("dir") or ev.get("path")))
    elif k == "done":
        print(
            "\n  done in %.0fs  %s  $%.2f  %s turns"
            % (ev["seconds"], ev["stages"], ev.get("cost_usd") or 0, ev.get("turns"))
        )
        print("  %s/outputs/%s" % (ev["dir"], ev["video"]))
    sys.stdout.flush()


def main():
    _env.utf8_stdio()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("prompt", nargs="?", help="what the film is about")
    ap.add_argument("--seconds", type=int, default=LENGTHS[0], choices=LENGTHS)
    ap.add_argument("--smoke", action="store_true", help="a one-turn API check, no film")
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
        asyncio.run(smoke())
        return
    if not args.prompt:
        ap.error("give a prompt, or --smoke")
    r = asyncio.run(make_film(args.prompt, _print, new_job(args.prompt, args.seconds)))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
