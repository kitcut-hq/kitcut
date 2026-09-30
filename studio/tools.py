"""The studio's tools: what Claude calls instead of a shell.

Each one runs a kitcut script on the film's own manifest, and nothing else:

    check()                  node --check on film.js, the engine copy and the cast
    voice(retake_line?)      sketch-vo.py: records the narration and times every word
    paint(retake?)           sketch-paint.py (a film that paints): its pictures, tiled on a sheet
    stills(times, sheet?)    sketch-render.py --stills: review frames, tiled into a sheet
    sound(levels?)           sketch-audio.py (after --automation when a cue needs it)
    name_film(title)         the title, for a film whose visitor typed nothing (voice or pictures)

and the studio's own steps, render() and cast_sheet(), which Claude cannot call.

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
from datetime import datetime

from claude_agent_sdk import create_sdk_mcp_server, tool

import motion
import procs
import validate
from film import HOME, KIT, REPO, _write_json, limits, paint_kinds, paint_words
from guard import pin_paint, pin_vo
from sched import waiting_text

SCRIPTS = os.path.join(KIT, "scripts")
# the machine-wide GPU lock lives in the working tree, so a release's scripts queue behind the
# same card as a developer's (scripts/_gpulock.py)
LOCKS = os.path.join(REPO, "temp", "locks")
# seconds a step may run; the voice, the mix and the render get longer for a longer film
TIMEOUT = {"check": 30, "stills": 120, "paint": 300, "automation": 180}
MAX_STILLS = 12
PEOPLE_WAIT_S = 420  # the longest a picture tool waits for the people to be drawn (agent.py)
# narration takes recorded at once (sketch-vo.py --jobs): an 8-minute film's 70 Gemini lines took
# 341 s one at a time and 52 s eight at a time, same accuracy and cost (docs/studio-speed.md)
VOICE_JOBS = 8
# where the final render's frames are encoded (sketch-render.py --encode): in the page by its
# hardware H.264 encoder, 2-4x faster than sending raw pixels to ffmpeg, and the only path whose
# colour matches the drawing (BT.709, tagged); falls back to the pipe where the browser has none.
# Blind-tested on three films 2026-09-28 (docs/studio-speed.md). A machine with no GPU encoder
# sets STUDIO_RENDER_ENCODE from its own measurements (studio/deploy/README.md)
RENDER_ENCODE = os.environ.get("STUDIO_RENDER_ENCODE") or "browser"
# browsers one final render draws with (and takes from the browser pool): 3 on the laptop, where
# more did not help; a CPU-only machine draws in software and scales with cores
RENDER_JOBS = int(os.environ.get("STUDIO_RENDER_JOBS") or 3)


class ToolError(Exception):
    """A tool's failure, in words for Claude."""


def _tts_spent(film):
    p = film.path("audio", "vo", "spend.jsonl")
    if not os.path.exists(p):
        return 0.0
    with open(p, encoding="utf-8") as f:
        return sum(json.loads(x).get("cost_usd") or 0 for x in f if x.strip())


# Up to this many lines, every word's time comes back with each recording; past it only the line
# re-recorded brings its words. Every recording of film llwtme (67 lines) returned all of them,
# 24,000 characters a time, kept in Claude's context for the rest of the film -- 17% of it --
# while SK.w(line, word) finds a word's time by itself when the film plays.
WORDS_UP_TO = 24


def approved_line(film, i):
    """Whether line i of the film's last recording played an approved voice line."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            lines = json.load(f).get("lines", [])
        return any(L["i"] == int(i) and L.get("approved") for L in lines)
    except (OSError, ValueError, TypeError):
        return False


# Recordings past a film's limit, allowed only while its narration runs past the film's end. The
# mix cannot place a line that starts after the end, so such a film fails at its finish; with no
# recording left Claude could only watch it fail (ewwd6b, 2026-09-30: all 6 recordings spent, 4 on
# retakes of lines with long tails, and the narration still ended at 199.8 s of 180).
FIT_RUNS = 2


def narration_over(film):
    """The last recording's overrun, or None when it fits the film (or there is none yet):
    {"ends": where the narration ends, "length": the film's length, "late": the lines that start
    after the end, which the mix cannot place}."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            tl = json.load(f)
    except (OSError, ValueError):
        return None
    lines = tl.get("lines") or []
    length = tl.get("duration") or film.length
    ends = max((L.get("end", 0) for L in lines), default=0)
    if not length or ends <= length:
        return None
    return {"ends": ends, "length": length, "late": [L for L in lines if L["start"] >= length]}


def recording_refused(film, done):
    """Why the film may not record again after `done` recordings, or None: the film's limit, plus
    FIT_RUNS while the narration does not fit the film."""
    runs = limits(film.length)["voice_runs"]  # recordings per film, retakes included
    over = narration_over(film)
    if done < runs or (over and done < runs + FIT_RUNS):
        return None
    if over:
        return (
            "That is %d recordings, the limit for one film, and the narration still ends at"
            " %.2f s, after the film's %g s." % (done, over["ends"], over["length"])
        )
    return "That is %d recordings, the limit for one film: keep the narration you have." % done


def fit_advice(film, done):
    """How to make a narration that runs past the end fit, and how many recordings are left for
    it (the film's limit plus FIT_RUNS)."""
    left = max(0, limits(film.length)["voice_runs"] + FIT_RUNS - done)
    return (
        "Cut words or whole lines in vo.json and record the narration again (%d recording%s left,"
        " retakes included); retaking a line makes it shorter only when it has fewer words."
        % (left, "" if left == 1 else "s")
    )


# what a person's own voice blocked on means, for Claude and for the page (sketch-vo.py BLOCKED_BY)
BLOCKED_WORDS = {
    "el_key_invalid": "ElevenLabs no longer accepts the account's key",
    "el_key_permissions": "the account's key is missing a permission",
    "el_quota": "the ElevenLabs account is out of characters",
    "el_voice_missing": "the voice is no longer in the ElevenLabs account",
    "el_plan": "the ElevenLabs plan does not allow it",
    "el_account_blocked": "ElevenLabs has paused the account",
    "voice_disconnected": "the ElevenLabs account was disconnected",
    "voice_unreachable": "ElevenLabs is not answering",
}
PARKED = (
    "The narration cannot be recorded now: %s. That is the person's own ElevenLabs account, "
    "and only they can put it right. The studio pauses the film here, with everything you have "
    "made kept, and picks it up when they have: end your turn now, and write nothing else."
)


def voice_blocked(text):
    """The VOICE-BLOCKED line sketch-vo.py printed before it stopped, as {reason, status, detail,
    since}; None when the step failed for another reason."""
    for line in reversed(text.splitlines()):
        if line.startswith("VOICE-BLOCKED "):
            try:
                d = json.loads(line[len("VOICE-BLOCKED ") :])
            except ValueError:
                return None
            reason = str(d.get("reason") or "voice_unreachable")[:40]
            return {
                "reason": reason,
                "status": d.get("status"),
                "detail": str(d.get("detail") or "")[:60],
                "since": datetime.now().isoformat(timespec="seconds"),
            }
    return None


def timeline_text(film, retake=None):
    """The narration's timing as Claude needs it for cues: each line's span, and its words (all of
    them for a short narration; for a long one only the line just re-recorded)."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            tl = json.load(f)
    except (OSError, ValueError):
        return "(no timeline)"
    lines = tl.get("lines", [])
    every = len(lines) <= WORDS_UP_TO
    out = []
    # sketch-vo.py only prints this to its own log: a narration past the film's end loses its last
    # words (and before _sketch.captions was fixed, the whole film: u3edgl, 2026-09-29)
    end, over = tl.get("duration"), max((L["end"] for L in lines), default=0)
    if end and over > end:
        out.append(
            "NOTE: the narration ends at %.2f s, after the film's %g s: every word after %g s is"
            " cut and never heard. Shorten or drop lines, or close the gaps, and record again."
            % (over, end, end)
        )
    for L in lines:
        if every or L["i"] == retake:
            words = " | ".join("%s %.2f" % (w["text"], w["s"]) for w in L.get("words", []))
            out.append(
                "line %d  %.2f-%.2f s  acc %.2f  %r\n  words: %s"
                % (L["i"], L["start"], L["end"], L.get("acc", 0), L["text"], words)
            )
        else:
            out.append(
                "line %d  %.2f-%.2f s  acc %.2f  %r"
                % (L["i"], L["start"], L["end"], L.get("acc", 0), L["text"][:60])
            )
        if L.get("backup_voice"):
            out.append(
                "  (Gemini would not read this line; the backup voice %s read it, so it sounds a"
                " little different. Keep it, or reword it and record it again.)" % L["backup_voice"]
            )
        if L.get("approved"):
            out.append("  (the project's approved recording of these words: never recorded again)")
    return "\n".join(out) or "(no lines)"


class Tools:
    def __init__(self, film, sched, emit, clock=None):
        self.film, self.sched, self.emit, self.clock = film, sched, emit, clock
        self.lock = asyncio.Lock()  # one step of this film at a time
        self.jobs = set()  # the steps running now (procs.Job), killed on cancel
        self.voice_runs, self.sheet_v = 0, 0
        # a pass of a film made in scenes (scenes.py): its name, the stretch of the film it looks
        # at, the files it may write, and its Claude session
        self.pass_name, self.span, self.allow, self.session = None, None, None, None
        self.priority = film.record().get("priority", 0)
        self.people_told = False  # whether Claude has been told how the people were drawn

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

    async def _script(self, kind, script, args, pools=(), log=False, timeout=None, manifest=None):
        """One kitcut script on this film's manifest (or another inside the film's folder), once
        the pools let it. Returns the lines it printed last; raises ToolError when it fails."""
        f = self.film
        argv = [procs.python(), "-X", "utf8", os.path.join(SCRIPTS, script)]
        argv += ["--manifest", manifest or f.manifest] + list(args)
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

    async def people_ready(self):
        """Wait for the film's people to be drawn (agent.draw_people writes rigs/ready.json); the
        wait is the machine's, not Claude's. Returns, once, a note on anyone who could not be
        drawn or was drawn in another style."""
        people = self.film.record().get("people") or []
        ready = self.film.path("rigs", "ready.json")
        if not people:
            return ""
        if not os.path.exists(ready):
            self.emit({"type": "log", "text": "Drawing the people..."})
            t0 = asyncio.get_running_loop().time()
            while (
                not os.path.exists(ready) and asyncio.get_running_loop().time() - t0 < PEOPLE_WAIT_S
            ):
                await asyncio.sleep(1)
            if self.clock is not None:
                self.clock.paused += asyncio.get_running_loop().time() - t0
        if self.people_told or not os.path.exists(ready):
            return ""
        self.people_told = True
        with open(ready, encoding="utf-8") as f:
            got = json.load(f)
        notes = []
        for p in people:
            r = got.get(p["id"]) or {"state": "failed", "why": "not drawn"}
            if r["state"] != "ready":
                notes.append(
                    "%s could not be drawn (%s): show their photo instead with SK.image('%s', x, y, w)"
                    % (p["id"], r.get("why"), p["id"])
                )
            elif r.get("style") and r["style"] != p["style"]:
                notes.append(
                    "%s was drawn as a %s (the %s was refused)" % (p["id"], r["style"], p["style"])
                )
        return ("\n\nThe people: " + "; ".join(notes) + ".") if notes else ""

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
        d = self.film.path("cast")
        cast = (
            sorted("cast/" + n for n in os.listdir(d) if n.endswith(".js"))
            if os.path.isdir(d)
            else []
        )
        sd = self.film.path("scenes")
        scenes = (
            sorted("scenes/" + n for n in os.listdir(sd) if n.endswith(".js"))
            if os.path.isdir(sd)
            else []
        )
        async with self.lock:
            engine = ["engine/" + n for n in self.film.engine_files()]
            for rel in ["film.js"] + engine + cast + scenes:
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
        return (
            "film.js, the engine and the cast parse." if cast else "film.js and the engine parse."
        )

    async def voice(self, retake_line=None):
        refused = recording_refused(self.film, self.voice_runs)
        if refused:
            raise ToolError(refused)
        if _tts_spent(self.film) >= limits(self.film.length)["tts_usd"]:
            raise ToolError("The narration's budget is spent: keep the recording you have.")
        # a person's own ElevenLabs voice records as many lines at once as their plan allows
        narrator = self.film.record().get("narrator") or {}
        own = narrator.get("source") == "elevenlabs"
        args = ["--jobs", str(int(narrator.get("jobs") or 2) if own else VOICE_JOBS)]
        if retake_line is not None and approved_line(self.film, retake_line):
            raise ToolError(
                "Line %d plays the project's approved recording of those words, which its person"
                " chose by ear: it is not recorded again. To say something else there, change"
                " the line's words in vo.json and record." % int(retake_line)
            )
        if retake_line is not None:
            args += ["--only", str(int(retake_line)), "--retake"]
        async with self.lock:
            self.gate()
            try:
                await self._script("voice", "sketch-vo.py", args, pools=[("cpu", 1)])
            except ToolError as e:
                # the person's own account would not speak (sketch-vo.py blocked): the film
                # pauses for them (agent.Parked) instead of failing, its takes kept
                stop = voice_blocked(str(e)) if own else None
                if not stop:
                    raise
                self.parked = stop
                raise ToolError(
                    PARKED % BLOCKED_WORDS.get(stop["reason"], stop["reason"])
                ) from None
            # only recordings that worked count: a TTS that gave no audio cost nothing (and the
            # narration's budget above caps what a film may spend on its voice either way)
            self.voice_runs += 1
        text = timeline_text(self.film, retake_line)
        if text.count("  words: ") < text.count("\nline ") + 1:  # a long narration: words on demand
            text += (
                "\n\n(A line's words and their times are in audio/vo/timeline.json: Read it for "
                "the lines you place cues on -- SK.w(line, 'word') finds them by itself.)"
            )
        return (
            "Recorded. The timeline (also in audio/vo/timeline.json), times on the film clock:\n"
            + text
            + (
                "\n\nThe narration does not fit the film yet. "
                + fit_advice(self.film, self.voice_runs)
                if narration_over(self.film)
                else ""
            )
        )

    async def paint(self, retake=None):
        if not paint_kinds(self.film.caps):
            raise ToolError("This film is drawn, not painted: there is nothing to paint.")
        args = []
        if retake:
            names = [n for n in retake if isinstance(n, str)]
            args = ["--only", ",".join(names), "--retake"]
        async with self.lock:
            self.gate()
            tail = await self._script("paint", "sketch-paint.py", args)
        noun = paint_words(self.film.caps)[1]
        return "\n".join(tail[-8:]) + "\n\nRead images/sheet.jpg to look at the %s." % noun

    async def stills(self, times, sheet=True):
        try:
            ts = [round(float(t), 3) for t in times]
        except (TypeError, ValueError):
            raise ToolError("times is a list of seconds, e.g. [0, 1.5, 3, 4.9]") from None
        n = self.film.length
        lo, hi = self.span or (0, n)  # a scene's pass: its own stretch of the film (scenes.py)
        if not ts or len(ts) > MAX_STILLS or any(t < lo or t > hi for t in ts):
            raise ToolError("give 1-%d times between %g and %g seconds" % (MAX_STILLS, lo, hi))
        args = ["--stills", ",".join("%g" % t for t in ts)] + (["--sheet"] if sheet else [])
        told = await self.people_ready()
        async with self.lock:
            self.gate()
            await self._script("stills", "sketch-render.py", args, pools=[("browser", 1)])
        what = "outputs/review/<t>.png"
        if sheet and os.path.exists(self.film.path("outputs", "review", "sheet.png")):
            self.sheet_v += 1
            self.emit({"type": "image", "path": "review/sheet.png", "v": self.sheet_v})
            what = "outputs/review/sheet.png"
        return "Rendered %d stills. Read %s to look at them." % (len(ts), what) + told

    async def name_film(self, title):
        """The film's title, when the visitor typed nothing (voice notes or pictures only): the
        record's title (the page and the film's own page show it) and the manifest's."""
        title = " ".join(str(title or "").split())[:80]
        if len(title) < 2:
            raise ToolError("Give the film a short title, a few words.")
        self.film.update(title=title)
        with open(self.film.manifest, encoding="utf-8") as f:
            m = json.load(f)
        m["title"] = title
        _write_json(self.film.manifest, m)
        return "The film is called %r." % title

    async def motion(self):
        """The film a few times a second, for what a sheet of stills cannot show: its cuts, and
        any stretch where nothing moves (studio/motion.py)."""
        ts = motion.times(self.film.length)
        if self.span:  # a scene's pass: only its stretch
            ts = [t for t in ts if self.span[0] <= t <= self.span[1]]
        shutil.rmtree(self.film.path("temp", "motion"), ignore_errors=True)
        args = ["--stills", ",".join("%g" % t for t in ts), "--into", "temp/motion"]
        told = await self.people_ready()
        async with self.lock:
            self.gate()
            await self._script(
                "stills",
                "sketch-render.py",
                args,
                pools=[("browser", 1)],
                timeout=120 + 2 * len(ts),
            )
        text, sheet = await asyncio.to_thread(
            motion.analyse,
            self.film.path("temp", "motion"),
            self.film.path("outputs", "review", "motion.png"),
        )
        if sheet:
            self.sheet_v += 1
            self.emit({"type": "image", "path": "review/motion.png", "v": self.sheet_v})
        return text + told

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
        """The soundtrack, and what Claude needs to judge it without listening: whether the music
        stays under the narration, always, and with levels the balance per 2 s. Both come from
        audio/balance.json: only a script's last lines come back, and they were the stage timings,
        so a score whose strings played 28 dB too loud over the voice was reported as fine."""
        over = narration_over(self.film)
        if over and over["late"]:  # the mix cannot place them: say so, not a numpy traceback
            raise ToolError(
                "The narration ends at %.2f s, after the film's %g s, and the soundtrack cannot"
                " be mixed: %s after the end. %s"
                % (
                    over["ends"],
                    over["length"],
                    ", ".join(
                        "line %s starts %.2f s" % (L.get("i"), L["start"]) for L in over["late"]
                    ),
                    fit_advice(self.film, self.voice_runs),
                )
            )
        async with self.lock:
            self.gate()
            await self._automation_if_needed()
            tail = await self._script("sound", "sketch-audio.py", [], pools=[("cpu", 1)], log=log)
        return balance_text(self.film, levels) or "\n".join(tail[-15:])

    async def render(self):
        """The final video (the studio's step, not Claude's): RENDER_JOBS browsers at once."""
        await self.people_ready()
        async with self.lock:
            self.gate()
            await self._script(
                "render",
                "sketch-render.py",
                ["--jobs", str(RENDER_JOBS), "--encode", RENDER_ENCODE],
                pools=[("browser", RENDER_JOBS)],
                log=True,
            )

    async def sheet_of(self, times, name):
        """Stills the studio renders for Claude to look at (scenes.py: the scene before's last
        frames, the editor's contact sheets), tiled into outputs/review/<name>.png. Its path."""
        ts = [round(float(t), 3) for t in times][:MAX_STILLS]
        args = ["--stills", ",".join("%g" % t for t in ts), "--sheet"]
        async with self.lock:
            self.gate()
            await self._script("stills", "sketch-render.py", args, pools=[("browser", 1)])
        src, dst = (
            self.film.path("outputs", "review", "sheet.png"),
            self.film.path("outputs", "review", name + ".png"),
        )
        if os.path.exists(src):
            shutil.copyfile(src, dst)
        return "outputs/review/%s.png" % name

    async def cast_sheet(self, manifest, times):
        """Stills of library.sheet()'s small film (each new cast member drawn alone), for their
        thumbnails (the studio's step, after the film)."""
        args = ["--stills", ",".join("%g" % t for t in times), "--into", "stills"]
        async with self.lock:
            await self._script(
                "stills", "sketch-render.py", args, pools=[("browser", 1)], manifest=manifest
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
                "Syntax-check film.js (and engine/*.js and cast/*.js) with node --check.",
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
                "motion",
                "Render the film a few times a second and report its cuts and any stretch where "
                "nothing moves for 4 s or more, with a sheet of the frames around each "
                "(outputs/review/motion.png).",
                {"type": "object", "properties": {}},
            )(wrap(lambda a: self.motion())),
            tool(
                "name_film",
                "Name the film (only when the person typed nothing): a short title, a few words.",
                {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            )(wrap(lambda a: self.name_film(a.get("title")))),
            tool(
                "sound",
                "Render the soundtrack from score.json and sfx.json (and the narration) to prove "
                "they work, and say whether the music stays under the narration; levels: also "
                "print the music / sfx / voice balance per 2 s.",
                {"type": "object", "properties": {"levels": {"type": "boolean"}}},
            )(wrap(lambda a: self.sound(bool(a.get("levels"))))),
        ]
        if self.film.record().get("prompt", "").strip():  # a typed idea is the title already
            tools = [t for t in tools if t.name != "name_film"]
        if not paint_kinds(self.film.caps):
            tools = [t for t in tools if t.name != "paint"]
        return create_sdk_mcp_server("studio", tools=tools)


def balance_text(film, table=False):
    """What sketch-audio.py measured (audio/balance.json), in words for Claude: whether the voice
    gate had to pull the music down, and with table the balance per 2 s. None when there is none."""
    try:
        with open(film.path("audio", "balance.json"), encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        return None
    g = b.get("voice_gate")
    if not g:
        lines = ["No narration, so nothing to balance the music against."]
    elif g["max_cut_db"] > 1.0:
        where = ", ".join("%.1f-%.1f s" % tuple(s) for s in g["spans"][:6])
        lines = [
            "Too loud: the music came within %g dB of the narration, so the studio pulled it down "
            "by up to %.1f dB over %.1f s (%s). Lower the score there (vel, or a swell's gains) "
            "rather than leave it to the studio."
            % (g["margin_db"], g["max_cut_db"], g["seconds"], where)
        ]
    else:
        lines = ["Balance OK: the music stays %g dB or more under the narration." % g["margin_db"]]
    if table:
        i = {c: k for k, c in enumerate(b["columns"])}
        lines.append("  sec   music   sfx  voice   (dBFS per 2 s; music as heard, after ducking)")
        lines += [
            "%5.0f %7.1f %5.0f %6.1f" % (r[i["sec"]], r[i["heard"]], r[i["sfx"]], r[i["voice"]])
            for r in b["rows"]
        ]
    return "\n".join(lines)


def _newer(a, *bs):
    """Does file a exist and postdate every existing b?"""
    if not os.path.exists(a):
        return False
    t = os.path.getmtime(a)
    return all(not os.path.exists(b) or os.path.getmtime(b) <= t for b in bs)
