"""The studio's tools: what Claude calls instead of a shell.

Each one runs a kitcut script on the film's own manifest, and nothing else:

    check()                  node --check on film.js and the engine copy
    voice(retake_line?)      sketch-vo.py: records the narration and times every word
    paint(retake?)           sketch-paint.py (painted films): paints the scenes, tiles a sheet
    stills(times, sheet?)    sketch-render.py --stills: review frames, tiled into a sheet
    sound(levels?)           sketch-audio.py (after --automation when a cue needs it)

and the studio's own final step, render(), which Claude cannot call.

They run inside the server, not in Claude Code, so every one goes through the scheduler (sched.py)
before it touches the machine, with the film's scrubbed environment (procs.step_env), a timeout
and its whole process tree killed if the film is cancelled. Before anything runs, the film's files
are pinned and checked (validate.gate). Two steps of one film never run at once, even when Claude
asks for them together. What a tool returns is short: the problem to fix, or what to look at next.
"""

import os
import json
import shutil
import asyncio
import contextlib

from claude_agent_sdk import create_sdk_mcp_server, tool

import procs
import validate
from film import HOME, KIT, REPO, limits
from guard import pin_paint, pin_vo
from sched import waiting_text

SCRIPTS = os.path.join(KIT, "scripts")
# the machine-wide GPU lock lives in the working tree, so a release's scripts queue behind the
# same card as a developer's (scripts/_gpulock.py)
LOCKS = os.path.join(REPO, "temp", "locks")
# seconds a step may run; the voice, the mix and the render get longer for a longer film
TIMEOUT = {"check": 30, "stills": 120, "paint": 300, "automation": 180}
MAX_VOICE_RUNS = 6  # recordings per film, retakes included
MAX_STILLS = 12


class ToolError(Exception):
    """A tool's failure, in words for Claude."""


def _tts_spent(film):
    p = film.path("audio", "vo", "spend.jsonl")
    if not os.path.exists(p):
        return 0.0
    with open(p, encoding="utf-8") as f:
        return sum(json.loads(x).get("cost_usd") or 0 for x in f if x.strip())


def timeline_text(film):
    """The narration's timing as Claude needs it for cues: each line's span and every word."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            tl = json.load(f)
    except (OSError, ValueError):
        return "(no timeline)"
    out = []
    for L in tl.get("lines", []):
        words = " | ".join("%s %.2f" % (w["text"], w["s"]) for w in L.get("words", []))
        out.append(
            "line %d  %.2f-%.2f s  acc %.2f  %r\n  words: %s"
            % (L["i"], L["start"], L["end"], L.get("acc", 0), L["text"], words)
        )
    return "\n".join(out) or "(no lines)"


class Tools:
    def __init__(self, film, sched, emit, clock=None):
        self.film, self.sched, self.emit, self.clock = film, sched, emit, clock
        self.lock = asyncio.Lock()  # one step of this film at a time
        self.jobs = set()  # the steps running now (procs.Job), killed on cancel
        self.voice_runs, self.sheet_v = 0, 0
        self.priority = film.record().get("priority", 0)

    # ---------------------------------------------------------------- plumbing
    def _on_wait(self, pool, ahead):
        self.emit({"type": "wait", "pool": pool, "ahead": ahead, "text": waiting_text(pool, ahead)})

    def gate(self):
        """Pin what the studio decides, then refuse to run on files that are wrong."""
        pin_vo(self.film)
        pin_paint(self.film)
        bad = validate.gate(self.film)
        if bad:
            raise ToolError("Fix these first:\n- " + "\n- ".join(bad))

    async def _script(self, kind, script, args, pools=(), log=False, timeout=None):
        """One kitcut script on this film's manifest, once the pools let it. Returns the lines it
        printed last; raises ToolError when it fails."""
        f = self.film
        argv = [procs.python(), "-X", "utf8", os.path.join(SCRIPTS, script)]
        argv += ["--manifest", f.manifest] + list(args)
        env = procs.step_env(f, kind, locks=LOCKS, home=HOME)
        on_line = (lambda s: self.emit({"type": "log", "text": s})) if log else None
        async with contextlib.AsyncExitStack() as stack:
            for name, weight in pools:  # always browser before cpu (sched.py)
                await stack.enter_async_context(
                    self.sched[name].hold(weight, f.id, self._on_wait, self.clock, self.priority)
                )
            try:
                code, tail = await procs.run(
                    argv, f.dir, env, timeout or self.timeout(kind), on_line, self.jobs
                )
            except procs.StepTimeout as e:
                raise ToolError("%s %s" % (script, e)) from None
        if code != 0:
            raise ToolError("\n".join(tail[-25:]) or "%s failed (exit %d)" % (script, code))
        return tail

    def kill(self):
        for job in list(self.jobs):
            job.kill()

    def timeout(self, kind):
        return TIMEOUT.get(kind) or limits(self.film.length)[kind + "_s"]

    # ---------------------------------------------------------------- the tools
    async def check(self):
        node = shutil.which("node")
        if not node:
            raise ToolError("node is not installed on this machine; skip the syntax check")
        out = []
        async with self.lock:
            for rel in ("film.js", "engine/engine.js", "engine/props.js"):
                p = self.film.path(*rel.split("/"))
                if not os.path.exists(p):
                    if rel == "film.js":
                        raise ToolError("there is no film.js yet")
                    continue
                code, tail = await procs.run(
                    [node, "--check", p],
                    self.film.dir,
                    procs.step_env(self.film),
                    TIMEOUT["check"],
                    jobs=self.jobs,
                )
                if code != 0:
                    out.append("%s:\n%s" % (rel, "\n".join(tail[-12:])))
        if out:
            raise ToolError("\n\n".join(out))
        return "film.js and the engine parse."

    async def voice(self, retake_line=None):
        if self.voice_runs >= MAX_VOICE_RUNS:
            raise ToolError(
                "That is %d recordings, the limit for one film: keep the narration you have."
                % MAX_VOICE_RUNS
            )
        if _tts_spent(self.film) >= limits(self.film.length)["tts_usd"]:
            raise ToolError("The narration's budget is spent: keep the recording you have.")
        args = [] if retake_line is None else ["--only", str(int(retake_line)), "--retake"]
        async with self.lock:
            self.gate()
            await self._script("voice", "sketch-vo.py", args, pools=[("cpu", 1)])
            # only recordings that worked count: a TTS that gave no audio cost nothing (and the
            # narration's budget above caps what a film may spend on its voice either way)
            self.voice_runs += 1
        return (
            "Recorded. The timeline (also in audio/vo/timeline.json), times on the film clock:\n"
            + timeline_text(self.film)
        )

    async def paint(self, retake=None):
        if self.film.look != "painted":
            raise ToolError("This film is drawn, not painted: there is nothing to paint.")
        args = []
        if retake:
            names = [n for n in retake if isinstance(n, str)]
            args = ["--only", ",".join(names), "--retake"]
        async with self.lock:
            self.gate()
            tail = await self._script("paint", "sketch-paint.py", args)
        return "\n".join(tail[-8:]) + "\n\nRead images/sheet.jpg to look at the paintings."

    async def stills(self, times, sheet=True):
        try:
            ts = [round(float(t), 3) for t in times]
        except (TypeError, ValueError):
            raise ToolError("times is a list of seconds, e.g. [0, 1.5, 3, 4.9]") from None
        n = self.film.length
        if not ts or len(ts) > MAX_STILLS or any(t < 0 or t > n for t in ts):
            raise ToolError("give 1-%d times between 0 and %d seconds" % (MAX_STILLS, n))
        args = ["--stills", ",".join("%g" % t for t in ts)] + (["--sheet"] if sheet else [])
        async with self.lock:
            self.gate()
            await self._script("stills", "sketch-render.py", args, pools=[("browser", 1)])
        what = "outputs/review/<t>.png"
        if sheet and os.path.exists(self.film.path("outputs", "review", "sheet.png")):
            self.sheet_v += 1
            self.emit({"type": "image", "path": "review/sheet.png", "v": self.sheet_v})
            what = "outputs/review/sheet.png"
        return "Rendered %d stills. Read %s to look at them." % (len(ts), what)

    async def _automation_if_needed(self):
        """The air cues follow the picture's motion, traced by a render pass."""
        try:
            with open(self.film.path("sfx.json"), encoding="utf-8") as f:
                air = any(c.get("fx") == "air" for c in json.load(f))
        except (OSError, ValueError, AttributeError):
            air = False
        auto = self.film.path("temp", "automation.json")
        if air and not _newer(auto, self.film.path("film.js"), self.film.path("sfx.json")):
            await self._script(
                "automation", "sketch-render.py", ["--automation"], pools=[("browser", 1)]
            )

    async def sound(self, levels=False, log=False):
        async with self.lock:
            self.gate()
            await self._automation_if_needed()
            tail = await self._script(
                "sound",
                "sketch-audio.py",
                ["--levels"] if levels else [],
                pools=[("cpu", 1)],
                log=log,
            )
        return "\n".join(tail[-15:])

    async def render(self):
        """The final video (the studio's step, not Claude's): three browsers at once."""
        async with self.lock:
            self.gate()
            await self._script(
                "render", "sketch-render.py", ["--jobs", "3"], pools=[("browser", 3)], log=True
            )

    # ---------------------------------------------------------------- as Claude sees them
    def server(self):
        """An in-process MCP server with these tools, for this film only."""

        def wrap(fn):
            async def call(args):
                try:
                    text = await fn(args or {})
                except ToolError as e:
                    return {"content": [{"type": "text", "text": str(e)}], "is_error": True}
                return {"content": [{"type": "text", "text": text}]}

            return call

        opt_int = {"type": "integer", "description": "the line's index in vo.json lines"}
        tools = [
            tool(
                "check",
                "Syntax-check film.js (and engine/*.js) with node --check.",
                {"type": "object", "properties": {}},
            )(wrap(lambda a: self.check())),
            tool(
                "voice",
                "Record the narration in vo.json (Gemini TTS) and time every word; returns the "
                "timeline. retake_line: record just that line again.",
                {"type": "object", "properties": {"retake_line": opt_int}},
            )(wrap(lambda a: self.voice(a.get("retake_line")))),
            tool(
                "paint",
                "Paint every image in paint.json (unchanged ones come from cache) and tile them "
                "into images/sheet.jpg. retake: names of images to paint again.",
                {
                    "type": "object",
                    "properties": {"retake": {"type": "array", "items": {"type": "string"}}},
                },
            )(wrap(lambda a: self.paint(a.get("retake")))),
            tool(
                "stills",
                "Render review frames of the film at these times (seconds) into "
                "outputs/review/, tiled into outputs/review/sheet.png when sheet is true.",
                {
                    "type": "object",
                    "properties": {
                        "times": {"type": "array", "items": {"type": "number"}},
                        "sheet": {"type": "boolean"},
                    },
                    "required": ["times"],
                },
            )(wrap(lambda a: self.stills(a.get("times"), a.get("sheet", True)))),
            tool(
                "sound",
                "Render the soundtrack from score.json and sfx.json (and the narration) to prove "
                "they work; levels: also print the balance.",
                {"type": "object", "properties": {"levels": {"type": "boolean"}}},
            )(wrap(lambda a: self.sound(bool(a.get("levels"))))),
        ]
        if self.film.look != "painted":
            tools = [t for t in tools if t.name != "paint"]
        return create_sdk_mcp_server("studio", tools=tools)


def _newer(a, *bs):
    """Does file a exist and postdate every existing b?"""
    if not os.path.exists(a):
        return False
    t = os.path.getmtime(a)
    return all(not os.path.exists(b) or os.path.getmtime(b) <= t for b in bs)
