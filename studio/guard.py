#!/usr/bin/env python
"""Sketch Studio's permission model: what Claude may read, write and run in a film's folder.

Imported by agent.py (the Agent SDK's PreToolUse / PostToolUse hooks call guard() and the pins),
and run as a hook command by the Claude Code CLI (agent.py --via cli):

    python studio/guard.py pre  <job>     reads the hook's JSON on stdin, prints its decision
    python studio/guard.py post <job>     after a write: puts back what the studio pins

Nothing here imports anything heavy: the CLI runs it once per tool call.
"""

import os
import re
import sys
import json
import shlex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITABLE = ("film.js", "score.json", "sfx.json", "vo.json")
MADE = ("film.js", "score.json", "sfx.json")  # what a finished film must have
LENGTHS = (5, 10, 15)  # seconds a visitor may ask for
# drawn: everything drawn in code; painted: an image model paints the scenes, the code animates
LOOKS = ("drawn", "painted")
# what Claude may not change in paint.json: the painter, and how many paintings a film may cost
PAINT_PINNED = {"backend": "muse", "model": "meta/muse-image", "max_images": 8}
# the voice: Google's Gemini text-to-speech. 3.8 needs the Gemini API enabled in the service
# account's project; STUDIO_TTS_MODEL in .env overrides it (e.g. gemini-3.1-flash-tts-preview)
TTS_MODEL = "gemini-3.8-flash-tts"
# what Claude may not change in vo.json: the studio decides the backend, model and take count
VO_PINNED = {"tts": "gemini", "takes": 1, "lead": 0.5, "gap": 0.35}


def tts_model():
    return os.environ.get("STUDIO_TTS_MODEL", "").strip() or TTS_MODEL


def look_of(job):
    return "painted" if os.path.exists(os.path.join(job, "paint.json")) else "drawn"


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
        mine = EDITABLE + (("paint.json",) if look_of(job) == "painted" else ())
        if os.path.dirname(p) == job and os.path.basename(p) in mine:
            return True, ""
        return False, "You can only write %s in your job folder." % ", ".join(mine)
    if tool == "Bash":
        return _bash_ok(inp.get("command", ""), job)
    return False, "%s is not available here: use Read, Write, Edit and the listed commands." % tool


def _bash_ok(cmd, job):
    usage = (
        "Only these commands run, one per call, from the working directory: "
        "`node --check <job>/film.js`, "
        "`python scripts/sketch-vo.py --manifest <job>/sketch.json [--only <n> --retake]`, "
        "`python scripts/sketch-paint.py --manifest <job>/sketch.json [--only <names> --retake]` "
        "(painted films), "
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
    if script == "scripts/sketch-paint.py" and look_of(job) == "painted":
        if rest in ([], ["--plan"]):
            return True, ""
        # repaint some: --only <name,name> --retake, in either order
        if len(rest) == 3 and "--only" in rest and "--retake" in rest:
            i = rest.index("--only")
            if i + 1 < len(rest) and re.fullmatch(r"[\w,-]+", rest[i + 1]):
                return True, ""
        return False, usage
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


def _pin(job, name, want):
    """Put back what Claude may not change in one of its files. Returns what it had to restore,
    or "" -- the PostToolUse hook tells Claude so."""
    p = os.path.join(job, name)
    if not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        return "%s is not valid JSON (%s); fix it" % (name, e)
    wrong = {k for k, v in want.items() if d.get(k) != v}
    if wrong:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d | want, f, indent=2, ensure_ascii=False)
        return "the studio sets %s in %s; restored %s" % (
            ", ".join(sorted(want)),
            name,
            ", ".join("%s=%r" % (k, want[k]) for k in sorted(wrong)),
        )
    return ""


def pin_vo(job):
    """vo.json: the voice backend, model and takes are the studio's."""
    return _pin(job, "vo.json", {**VO_PINNED, "model": tts_model()})


def pin_paint(job):
    """paint.json: the painter, its model and the cap on paintings are the studio's."""
    return _pin(job, "paint.json", PAINT_PINNED)


def pin_after(file_path, job):
    """After a write: pin the file if it is one the studio has a say in. Returns a note or ""."""
    p = str(file_path or "").replace("\\", "/")
    if p.endswith("vo.json"):
        return pin_vo(job)
    if p.endswith("paint.json"):
        return pin_paint(job)
    return ""


def hook(kind, job):
    """The Claude Code CLI's hook protocol: the event on stdin, the answer on stdout."""
    ev = json.load(sys.stdin)
    if kind == "pre":
        ok, why = guard(ev.get("tool_name", ""), ev.get("tool_input") or {}, job)
        out = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if ok else "deny"}
        if not ok:
            out["permissionDecisionReason"] = why
        print(json.dumps({"hookSpecificOutput": out}))
    else:
        note = pin_after((ev.get("tool_input") or {}).get("file_path"), job)
        if note:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": note,
                        }
                    }
                )
            )


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("pre", "post"):
        sys.exit("usage: guard.py pre|post <job folder>")
    hook(sys.argv[1], sys.argv[2])
