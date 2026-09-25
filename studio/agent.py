#!/usr/bin/env python
"""Sketch Studio: one line of text in, a 5-second sketch film out, written by Claude.

    python studio/agent.py --smoke                  one-turn API check: key source, model, cost
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
import asyncio
import argparse
from datetime import datetime

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

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
EDITABLE = ("film.js", "score.json", "sfx.json")
AGENT_TIMEOUT = 12 * 60


# ------------------------------------------------------------------ the permission model
def _path(p):
    """A tool's path argument, absolute: relative to the repo root, posix or git-bash (/c/...)."""
    p = str(p or "").strip().strip("\"'")
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)
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
    fill = {
        "JOB": os.path.relpath(job, ROOT).replace("\\", "/"),
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
def new_job(prompt):
    """projects/studio-<stamp>/ with the 5-second manifest in it."""
    job = os.path.join(ROOT, "projects", "studio-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(job)
    with open(os.path.join(HERE, "template", "sketch.json"), encoding="utf-8") as f:
        m = json.load(f)
    words = re.sub(r"\s+", " ", prompt).strip()
    m["title"] = (words[:60] + "...") if len(words) > 60 else words
    with open(os.path.join(job, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    with open(os.path.join(job, "studio.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"prompt": prompt, "started": datetime.now().isoformat(timespec="seconds")}, f, indent=2
        )
    return job


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
        return c
    return name


def _result_text(block):
    c = block.content
    if isinstance(c, list):
        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


async def run_claude(prompt, job, emit):
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
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool])]},
        can_use_tool=can_use,
        max_turns=40,
        max_budget_usd=float(os.environ.get("STUDIO_MAX_USD") or 5),
        env=child_env(),
    )
    ask = "Make the film: %s" % prompt.strip()
    async with ClaudeSDKClient(options=opts) as client:
        await client.query(ask)
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                d = msg.data
                emit({"type": "init", "model": d.get("model"), "key": d.get("apiKeySource")})
            elif isinstance(msg, AssistantMessage):
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


async def make_film(prompt, emit=None, job=None):
    """The whole film. Every step is reported through emit(dict); returns the final summary."""
    emit = emit or (lambda ev: None)
    job = job or new_job(prompt)
    rel = os.path.relpath(job, ROOT).replace("\\", "/")
    manifest = rel + "/sketch.json"
    t0, stages = time.time(), {}
    emit({"type": "job", "id": os.path.basename(job), "dir": rel, "model": MODEL})
    summary = {"prompt": prompt, "model": MODEL, "dir": rel}
    try:
        emit(
            {"type": "stage", "name": "claude", "text": "Claude is writing and reviewing the film"}
        )
        s = time.time()
        res = await asyncio.wait_for(run_claude(prompt, job, emit), AGENT_TIMEOUT)
        stages["claude"] = time.time() - s
        if res is not None:
            summary.update(
                cost_usd=res.total_cost_usd,
                turns=res.num_turns,
                claude_said=res.result,
                usage=res.usage,
            )
            if res.is_error:
                raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
        missing = [f for f in EDITABLE if not os.path.exists(os.path.join(job, f))]
        if missing:
            raise RuntimeError("Claude finished without writing %s" % ", ".join(missing))

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
        if not _newer(wav, *(os.path.join(job, f) for f in EDITABLE)):
            await _step(["scripts/sketch-audio.py", "--manifest", manifest], emit, "the soundtrack")
        stages["sound"] = time.time() - s

        s = time.time()
        emit({"type": "stage", "name": "render", "text": "Rendering 300 frames"})
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
        stages.setdefault("failed_after", time.time() - t0)
        summary.update(ok=False, error=str(e), seconds=round(time.time() - t0, 1))
        emit({"type": "error", "text": str(e)})
    with open(os.path.join(job, "studio.json"), encoding="utf-8") as f:
        rec = json.load(f)
    rec.update(summary, finished=datetime.now().isoformat(timespec="seconds"))
    with open(os.path.join(job, "studio.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
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
    t = time.time()
    async for m in query(prompt="ping", options=opts):
        if isinstance(m, SystemMessage) and m.subtype == "init":
            print("  key source: %s" % m.data.get("apiKeySource"))
            print("  model:      %s" % m.data.get("model"))
        elif isinstance(m, ResultMessage):
            print("  reply:      %r%s" % (m.result, "  (ERROR)" if m.is_error else ""))
            print("  cost:       $%.4f in %.1fs" % (m.total_cost_usd or 0, time.time() - t))


def _print(ev):
    k = ev["type"]
    if k == "log":
        print("      " + ev["text"])
    elif k == "say":
        print("  claude: " + ev["text"].replace("\n", "\n          "))
    elif k in ("tool", "stage", "blocked", "fail", "error"):
        print("  %-7s %s" % (k, ev.get("text")))
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
    ap.add_argument("--smoke", action="store_true", help="a one-turn API check, no film")
    args = ap.parse_args()
    if args.smoke:
        asyncio.run(smoke())
        return
    if not args.prompt:
        ap.error("give a prompt, or --smoke")
    r = asyncio.run(make_film(args.prompt, _print))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
