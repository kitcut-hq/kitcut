"""The studio's tools: what Claude calls instead of a shell.

Each one runs a kitcut script on the film's own manifest, and nothing else:

    check()                  node --check on film.js, the engine copy and the cast
    voice(retake_line?)      sketch-vo.py: records the narration and times every word
    paint(retake?)           sketch-paint.py (a film that paints): its pictures, tiled on a sheet
    stills(times, sheet?)    sketch-render.py --stills: review frames, tiled into a sheet (and,
                             for a film that asks, the preview the site plays: PREVIEW)
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
import time
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
# route: tiles, OSM's answer (a busy Overpass is retried for minutes) and a ~30 MP map drawn on a
# core -- 90 s on the laptop with a warm cache
TIMEOUT = {"check": 30, "stills": 120, "paint": 300, "automation": 180, "web": 150, "route": 900}
MAX_STILLS = 12
PEOPLE_WAIT_S = 420  # the longest a picture tool waits for the people to be drawn (agent.py)
# what one film may bring in from the web (web-grab.py): pictures and page photographs together,
# and font families -- each is inlined into the film's page, which a phone downloads whole
MAX_WEB_PICTURES, MAX_WEB_FONTS = 12, 3
# portrait-cutout's time a photo, with room: 10.5 s on the laptop with every core, 54 s with two
# threads (the first template film: 7 photos took 6 minutes before Claude could start)
CUT_S_PER_PHOTO = 90
CUT_THREADS = max(2, (os.cpu_count() or 4) // 2)  # half the machine: other films' steps run too
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
# the preview (sketch-render.py --preview), for a film whose record asks for it (the site's
# X-Preview): outputs/review/preview.html, the film as it stands with its narration and the words
# under it, to watch while it is made. Written once the narration is recorded (over the bare
# ground: no picture is trusted before a sheet has drawn) and again with every review sheet, and
# announced as a "preview" event. It is something to watch, never part of the film: it fails
# quietly and costs Claude nothing it would see.
PREVIEW = "review/preview.html"


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
        self.voice_runs, self.sheet_v, self.preview_v = 0, 0, 0
        self._bg = None  # the narration's preview, being made beside Claude's turn
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

    def wants_preview(self):
        return bool(self.film.record().get("preview"))

    def _announce_preview(self, since, kind):
        """A "preview" event, when the stills (kind "film") or the narration ("narration") have
        just written one."""
        p = self.film.path("outputs", *PREVIEW.split("/"))
        if os.path.exists(p) and os.path.getmtime(p) >= since:
            self.preview_v += 1
            self.emit({"type": "preview", "path": PREVIEW, "v": self.preview_v, "kind": kind})

    async def _narration_preview(self):
        """The narration over the bare ground, before the picture has drawn: a background step, so
        Claude's turn goes on, and nothing it hears about."""
        try:
            async with self.lock:
                if self.sheet_v:  # a sheet has drawn: from now on the picture's previews stand
                    return
                since = time.time()
                await self._script(
                    "preview", "sketch-render.py", ["--preview", "narration"], timeout=90
                )
                self._announce_preview(since, "narration")
        except Exception as e:  # noqa: BLE001 -- something to watch, never the film's trouble
            self.emit({"type": "log", "text": "preview not made: %s" % str(e)[-200:]})

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
        if not self.sheet_v and self.wants_preview():
            self._bg = asyncio.ensure_future(self._narration_preview())
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
        preview = self.wants_preview()
        args += ["--preview"] if preview else []
        told = await self.people_ready()
        since = time.time()
        async with self.lock:
            self.gate()
            await self._script("stills", "sketch-render.py", args, pools=[("browser", 1)])
        what = "outputs/review/<t>.png"
        if sheet and os.path.exists(self.film.path("outputs", "review", "sheet.png")):
            self.sheet_v += 1
            self.emit({"type": "image", "path": "review/sheet.png", "v": self.sheet_v})
            what = "outputs/review/sheet.png"
        if preview:
            self._announce_preview(since, "film")
        return "Rendered %d stills. Read %s to look at them." % (len(ts), what) + told

    # ---------------------------------------------------------------- from the web
    def _manifest(self):
        with open(self.film.manifest, encoding="utf-8") as f:
            return json.load(f)

    def web_limit(self):
        """Pictures from the web one film may bring in: a template's own number (a conference's
        line-up of speakers), else MAX_WEB_PICTURES."""
        t = self.film.record().get("template")
        if not t:
            return MAX_WEB_PICTURES
        import templates  # noqa: PLC0415

        got = templates.load(t["id"], t["version"], ("live", "draft", "retired")) or {}
        return max(MAX_WEB_PICTURES, int((got.get("limits") or {}).get("images") or 0))

    async def picture(self, url, name, width=None):
        """A picture from the web (a logo, a product photo) into web/, as SK.image('web_<name>')."""
        have = [k for k in self._manifest().get("images") or {} if k.startswith("web_")]
        if len(have) >= self.web_limit() and "web_%s" % name not in have:
            raise ToolError(
                "That is %d pictures from the web, the limit for one film: reuse or replace one "
                "(the same name again replaces it)." % self.web_limit()
            )
        args = ["--picture", str(url or ""), "--name", str(name or "")]
        if width:
            args += ["--width", str(int(width))]
        async with self.lock:
            tail = await self._script("web", "web-grab.py", args, pools=[("browser", 1)])
        return tail[-1] if tail else "saved"

    async def page(self, url, name, width=None, height=None):
        """A photograph of a web page into web/, as SK.image('web_<name>')."""
        have = [k for k in self._manifest().get("images") or {} if k.startswith("web_")]
        if len(have) >= self.web_limit() and "web_%s" % name not in have:
            raise ToolError(
                "That is %d pictures from the web, the limit for one film: reuse or replace one "
                "(the same name again replaces it)." % self.web_limit()
            )
        args = ["--page", str(url or ""), "--name", str(name or "")]
        if width or height:
            args += ["--size", "%dx%d" % (int(width or 1920), int(height or 1080))]
        async with self.lock:
            tail = await self._script("web", "web-grab.py", args, pools=[("browser", 1)])
        # the photograph's line and what the page is made of, below it
        first = max((i for i, ln in enumerate(tail) if ln.startswith("web/")), default=0)
        return "\n".join(tail[first:]) or "saved"

    async def font(self, family, weights=None):
        """A Google Fonts family into web/fonts/ and the manifest's fonts."""
        mine = {f.get("family") for f in self._manifest().get("fonts") or [] if "web/" in f["file"]}
        if len(mine) >= MAX_WEB_FONTS and family not in mine:
            raise ToolError(
                "That is %d font families from the web, the limit for one film." % MAX_WEB_FONTS
            )
        args = ["--font", str(family or "")]
        if weights:
            try:
                args += ["--weights", ",".join(str(int(w)) for w in weights)]
            except (TypeError, ValueError):
                raise ToolError("weights is a list of numbers, e.g. [400, 700]") from None
        async with self.lock:
            tail = await self._script("web", "web-grab.py", args)
        return tail[-1] if tail else "saved"

    async def cut_people(self):
        """Cut every person of a template film still waiting out of their photo (templates.cut_list:
        the cache first), on half the machine's cores, then keep each in the cache."""
        import templates  # noqa: PLC0415

        f = self.film
        todo, spec = await asyncio.to_thread(templates.cut_list, f)
        if not todo:
            return 0
        self.emit(
            {"type": "stage", "name": "people", "text": "Cutting the people out of their photos"}
        )
        src, out = f.path("temp", "cut", "in"), f.path("temp", "cut", "out")
        shutil.rmtree(f.path("temp", "cut"), ignore_errors=True)
        os.makedirs(src)
        for key, photo, _, _ in todo:
            shutil.copyfile(photo, os.path.join(src, key + os.path.splitext(photo)[1]))
        argv = [procs.python(), "-X", "utf8", os.path.join(SCRIPTS, "portrait-cutout.py")]
        argv += ["--src", src, "--out", out, "--threads", str(CUT_THREADS)]
        argv += templates.cut_args(spec)
        async with self.sched["cpu"].hold(1, f.id, self._on_wait, self.clock, self.priority):
            code, tail = await procs.run(
                argv,
                f.dir,
                procs.step_env(f, "cutouts"),
                60 + CUT_S_PER_PHOTO * len(todo),
                jobs=self.jobs,
            )
        if code != 0:
            raise ToolError("the people could not be cut out: %s" % " ".join(tail[-3:]))
        cache = os.path.join(HOME, "cache", "cutouts")
        os.makedirs(cache, exist_ok=True)
        for key, _, dst, hit in todo:
            got = os.path.join(out, key + ".webp")
            if not os.path.exists(got):
                raise ToolError("no cut-out of %s: is there a face in its photo?" % key)
            shutil.copyfile(got, dst)
            shutil.copyfile(got, hit)
        return len(todo)

    async def template_pictures(self, logo=None, people=(), qr=None):
        """A template film's pictures -- the person's (upload1...) or ones Claude brought in with
        the picture tool (web_...) -- become the film's own: the logo on dark and light grounds
        (templates.logo_variants), each person cut out of their photo as sp-1, sp-2... in the
        order given, and a QR code of a link (templates.qr_picture). Answers with the keys for
        content.json."""
        import templates  # noqa: PLC0415

        f = self.film
        if not f.record().get("template"):
            raise ToolError("Only a film made from a template has template pictures.")
        m = self._manifest()
        images = m.setdefault("images", {})

        def web(name):  # a picture the person attached or Claude brought in, not the template's
            for key in (str(name), "web_%s" % name):
                rel = images.get(key)
                if (
                    rel
                    and not rel.startswith(("template/", "images/"))
                    and os.path.exists(f.path(*rel.split("/")))
                ):
                    return f.path(*rel.split("/"))
            raise ToolError(
                "No picture %r: name one the person attached (upload1...) or one brought in with "
                "the picture tool (web_...)." % name
            )

        said = []
        if qr:
            try:
                await asyncio.to_thread(templates.qr_picture, qr, f.path("images", "qr.png"))
            except templates.TemplateError as e:
                raise ToolError(str(e)) from None
            images["qr"] = "images/qr.png"
            said.append('the QR code of %s: "qr"' % qr)
        if logo:
            p1, p2 = await asyncio.to_thread(templates.logo_variants, web(logo), f.path("images"))
            images["logo"] = os.path.relpath(p1, f.dir).replace("\\", "/")
            images["logo-light"] = os.path.relpath(p2, f.dir).replace("\\", "/")
            said.append('the logo: {"image": "logo", "light": "logo-light"}')
        rows = list(f.record().get("people_cutouts") or [])
        start = len(rows)
        os.makedirs(f.path("inputs", "people"), exist_ok=True)
        for i, name in enumerate(people or (), start + 1):
            src = web(name)
            key = "sp-%d" % i
            rel = "inputs/people/%s%s" % (key, os.path.splitext(src)[1])
            shutil.copyfile(src, f.path(*rel.split("/")))
            images[key] = "images/people/%s.webp" % key
            rows.append({"key": key, "photo": rel})
        _write_json(f.manifest, m)
        f.update(people_cutouts=rows)
        if people:
            async with self.lock:
                await self.cut_people()
            said.append(
                "the people, in the order given: %s"
                % ", ".join("%s = %s" % (n, "sp-%d" % i) for i, n in enumerate(people, start + 1))
            )
        return "Ready. In content.json use " + "; ".join(said) + "."

    async def route(
        self,
        gpx=None,
        points=None,
        mode=None,
        start_at=None,
        finish_at=None,
        places=None,
        units=None,
    ):
        """A film's real route on its real map (scripts/route-map.py --film): the map picture as
        images/route_map.jpg (SK.image key route_map) and the route as route.json, SK.DATA.route
        -- rows of [u, v, elevation, distance, seconds], its marks, places and numbers. From a GPX
        the person attached (a document), or places routed along real roads and trails."""
        f = self.film
        spec = {"mode": mode or "bike", "image": "route_map"}
        if gpx:
            docs = [a for a in f.record().get("attachments") or [] if a.get("kind") == "text"]
            want = str(gpx).strip().lower()
            hit = next(
                (
                    a
                    for i, a in enumerate(docs, 1)
                    if want
                    in {
                        str(a.get("name") or "").lower(),
                        a["file"].lower(),
                        os.path.basename(a["file"]).lower(),
                        "document %d" % i,
                        "doc%d" % i,
                    }
                ),
                None,
            )
            if hit is None:
                raise ToolError(
                    "No document %r: name one the person attached (its name, or 'Document 1')."
                    % gpx
                )
            spec["gpx"] = f.path(*hit["file"].split("/"))
        elif points:
            spec["points"] = list(points)
        else:
            raise ToolError(
                "Give the route: gpx (an attached document) or points (two places at least)."
            )
        for k, v in (("start_at", start_at), ("finish_at", finish_at), ("units", units)):
            if v:
                spec[k] = v
        if places:
            spec["places"] = list(places)
        os.makedirs(f.path("temp"), exist_ok=True)
        _write_json(f.path("temp", "route-spec.json"), spec)
        args = ["--film", f.path("temp", "route-spec.json")]
        args += [
            "--out-image",
            f.path("images", "route_map.jpg"),
            "--out-data",
            f.path("route.json"),
        ]
        args += ["--cache", os.path.join(HOME, "cache")]
        async with self.lock:
            tail = await self._script("route", "route-map.py", args, pools=[("cpu", 1)])
        got = json.loads(tail[-1])
        m = self._manifest()
        m.setdefault("images", {})["route_map"] = "images/route_map.jpg"
        m.setdefault("data", {})["route"] = "route.json"
        _write_json(f.manifest, m)
        st, u = got["stats"], got["units"]
        placed = "; ".join(
            "%s at u %.4f v %.4f" % (p["name"], p["u"], p["v"]) for p in got["places"]
        )
        return (
            "The route is drawn: %s, %d rows in route.json (SK.DATA.route; its map is "
            "SK.image('route_map')). %s %s, climbs %s %s, highest %s %s; the main climb %s %s "
            "for %s %s; %s, %s clock. Marks (row numbers): %s. Placed: %s."
            % (
                got["map"],
                got["rows"],
                st["distance"],
                u["dist"],
                st["gain"],
                u["ele"],
                st["top"],
                u["ele"],
                st["climb_gain"],
                u["ele"],
                st["climb_distance"],
                u["dist"],
                "a loop" if got["loop"] else "point to point",
                "the ride's own" if got["timed"] else "an estimated",
                ", ".join("%s %d" % kv for kv in got["marks"].items()),
                placed or "nothing named",
            )
        )

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

    async def _sound_data_if_needed(self):
        """A template's film writes its own score and cues (SK.film({sound})): worked out again
        from its code and content whenever either changed since, before the mix hears them."""
        f = self.film
        if not f.record().get("template"):
            return
        if _newer(f.path("sfx.json"), f.path("film.js"), f.path("content.json")) and _newer(
            f.path("score.json"), f.path("film.js"), f.path("content.json")
        ):
            return
        await self._script("sound", "sketch-render.py", ["--sound-data"], pools=[("browser", 1)])

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
            await self._sound_data_if_needed()
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
                "picture",
                "Save a picture from the web (a logo, a product, a person, a place: its own URL, "
                "PNG/JPEG/WebP/GIF/ICO/SVG) into web/<name>.png|jpg, shown in film.js with "
                "SK.image('web_<name>', x, y, w). width: the px an SVG is drawn at (1600).",
                {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "name": {"type": "string", "description": "lowercase, e.g. logo"},
                        "width": {"type": "integer"},
                    },
                    "required": ["url", "name"],
                },
            )(wrap(lambda a: self.picture(a.get("url"), a.get("name"), a.get("width")))),
            tool(
                "page",
                "Open a web page in a real browser (it also reads pages WebFetch is refused) and "
                "photograph it (width x height px, 1920x1080 unless given; a taller one takes "
                "more of the page) into web/<name>.jpg, shown with SK.image('web_<name>', x, y, "
                "w). Reports what the page is made of, measured in it: the fonts that set its "
                "headings, text and buttons, the web fonts it loaded, its text and painted "
                "colours, its logo and icon files; a logo it draws inline is saved as "
                "web/<name>_logo1.png. Its words go to web/<name>.txt.",
                {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "name": {"type": "string", "description": "lowercase, e.g. site"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                    "required": ["url", "name"],
                },
            )(
                wrap(
                    lambda a: self.page(
                        a.get("url"), a.get("name"), a.get("width"), a.get("height")
                    )
                )
            ),
            tool(
                "font",
                "Add a Google Fonts family to the film (whole fonts, every script they cover), "
                "for SK.text(..., {font: '<family>', wt: <weight>}). weights: [400, 700] unless "
                "given.",
                {
                    "type": "object",
                    "properties": {
                        "family": {"type": "string", "description": "e.g. Inter"},
                        "weights": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["family"],
                },
            )(wrap(lambda a: self.font(a.get("family"), a.get("weights")))),
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
                "template_pictures",
                "A film made from a template: make a logo and people's photos the film's own -- the "
                "person's (upload1...) or ones brought in with the picture tool (web_...). logo: the "
                "logo picture's name; people: the photos' names, in the order the people should take "
                "(the first are the featured); qr: a link to make a QR code of (it is read back "
                "before it is kept). Cuts each person out of their photo and makes the logo "
                "readable on dark and light grounds; answers with the image keys for content.json.",
                {
                    "type": "object",
                    "properties": {
                        "logo": {"type": "string"},
                        "people": {"type": "array", "items": {"type": "string"}},
                        "qr": {"type": "string", "description": "a link, e.g. https://..."},
                    },
                },
            )(
                wrap(
                    lambda a: self.template_pictures(
                        a.get("logo"), a.get("people") or [], a.get("qr")
                    )
                )
            ),
            tool(
                "route",
                "Draw the film's real route on a real map (OpenStreetMap streets and trails over real "
                "terrain, made of paper sheets): images/route_map.jpg (SK.image key route_map) and "
                "route.json (SK.DATA.route: rows [u, v, elevation, distance, seconds] -- u, v "
                "fractions of the map -- marks start/climb/top/finish, places, stats). gpx: the name "
                "of a GPX document the person attached. Or points: the route's places in order, each "
                "a place name or [lat, lon], routed by mode along real roads and trails (a loop ends "
                "where it starts). start_at / finish_at: cut a recording to where the event starts "
                "and ends. places: names or [lat, lon] to locate for labels. units: imperial or "
                "metric. Takes one to three minutes.",
                {
                    "type": "object",
                    "properties": {
                        "gpx": {"type": "string"},
                        "points": {"type": "array", "items": {}},
                        "mode": {"type": "string", "enum": ["bike", "foot"]},
                        "start_at": {},
                        "finish_at": {},
                        "places": {"type": "array", "items": {}},
                        "units": {"type": "string", "enum": ["imperial", "metric"]},
                    },
                },
            )(
                wrap(
                    lambda a: self.route(
                        a.get("gpx"),
                        a.get("points"),
                        a.get("mode"),
                        a.get("start_at"),
                        a.get("finish_at"),
                        a.get("places"),
                        a.get("units"),
                    )
                )
            ),
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
        rec = self.film.record()
        if rec.get("prompt", "").strip():  # a typed idea is the title already
            tools = [t for t in tools if t.name != "name_film"]
        if rec.get("narration") is False:  # a template's film: the music carries it
            tools = [t for t in tools if t.name != "voice"]
        if not rec.get("template"):  # its pictures from the website: a template film's only
            tools = [t for t in tools if t.name != "template_pictures"]
        if not paint_kinds(self.film.caps):
            tools = [t for t in tools if t.name != "paint"]
        if "routes" not in self.film.caps:  # a film that replays a route on its map: a template's
            tools = [t for t in tools if t.name != "route"]
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
