#!/usr/bin/env python
"""Sketch Studio: one line of text in, a short sketch film out, written by Claude.

    python studio/agent.py --smoke [--auth api]        one-turn check: key source, model, cost
    python studio/agent.py --check-login               the daily login check (kitcut.studio_hosts)
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
    --auth api     ANTHROPIC_API_KEY, a private config folder per film
    --auth login   this machine's Claude Code login (the default; the public site's films too,
                   unless STUDIO_SITE_AUTH=api -- server.site_auth)
A login film whose sign-in fails (SignInError) is made on the key instead, and its record says so;
one that runs into the plan's usage limit half-way (PlanLimit) carries on on the key, in the same
session, and only what it spends from there is billed.
"""

import sys
import os
import re
import json
import time
import shutil
import asyncio
import argparse
import contextlib
from collections import Counter
from datetime import datetime
from importlib import import_module

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

sys.path.insert(0, HERE)
import procs  # noqa: E402
import film as films  # noqa: E402
import library  # noqa: E402
import media  # noqa: E402
import peers  # noqa: E402

# the studio's keys, out of the environment before anything is started (procs.py)
procs.load_secrets(os.environ.get("STUDIO_ENV_FILE") or os.path.join(films.REPO, ".env"))

import store  # noqa: E402
import scenes  # noqa: E402
import templates  # noqa: E402
import validate  # noqa: E402
from film import (  # noqa: E402
    HOME,
    KIT,
    LENGTHS,
    LOOKS,
    MADE,
    RECIPES,
    RELEASE,
    Film,
    direction_fields,
    fills,
    limits,
    mark_note,
    paint_kinds,
    paint_words,
)
from guard import _path, guard, pin_after, pin_paint, pin_vo  # noqa: E402
from sched import Clock, Sched, waiting_text  # noqa: E402
import tools as tools_mod  # noqa: E402
from tools import ToolError, Tools  # noqa: E402

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CLINotFoundError,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
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
# how hard it thinks: adaptive thinking at this effort (the CLI's --effort). Pinned here, so a CLI
# update that moves the default cannot change the films unnoticed
EFFORT = "xhigh"
# how long Claude may work on a film, and what it may spend, grow with the film's length:
# film.limits() (20 min of working time for up to 15 s; waiting for the machine does not count)


class PlanLimit(RuntimeError):
    """The login works but its plan is spent for now: the reply is an AssistantMessage whose
    `error` is "rate_limit" or "billing_error" (Claude Code has already done its own retrying of
    a passing 429 by then). A film on the login then carries on on the key (make_film)."""

    def __init__(self, why):
        super().__init__("Claude's plan limit: %s" % why)
        self.why = why


class SignInError(RuntimeError):
    """Claude could not start on the credentials it was given -- for auth=login, this machine's
    Claude Code login is gone (logged out, the setup-token expired or was revoked, no CLI).

    The SDK does not raise on it. Measured with Claude Code 2.1.284 (SDK 0.2.x), 2026-09-28: a
    bogus CLAUDE_CODE_OAUTH_TOKEN and an empty config folder with no token both end the turn
    normally, with an AssistantMessage whose `error` is "authentication_failed" ("Failed to
    authenticate. API Error: 401 Invalid bearer token" / "Not logged in · Please run /login")
    and a ResultMessage with is_error (api_error_status 401 when a token was sent). A usage
    limit is "rate_limit" / "billing_error" and is not this: the login works, the plan is spent.
    """

    def __init__(self, why):
        super().__init__("Claude could not sign in: %s" % why)
        self.why = why


# ------------------------------------------------------------------ the environment Claude runs in
def tool_timeout_s(length):
    """How long Claude Code waits for one studio tool: 30 min for the machine to be free, plus
    the longest step Claude can call for a film of this length (film.limits())."""
    lim = limits(max(length, 5))
    return 30 * 60 + max(lim["voice_s"], lim["sound_s"])


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
        # a studio tool may wait for the machine, then run its step; the steps time out on their
        # own, and the voice and the mix grow with the film (an 8-minute one: about 43 min)
        "MCP_TOOL_TIMEOUT": str(tool_timeout_s(film.length if film else 0) * 1000),
        # one API request may run long: at effort xhigh, the reply that plans and writes an 8-minute
        # film's picture thought past Claude Code's own timeout, and was retried from scratch every
        # 5 minutes for an hour with nothing to show (llwtme, 2026-09-28, 205k tokens of context)
        "API_TIMEOUT_MS": str(30 * 60 * 1000),
        # the model's own cap on one reply (Opus 5.5: 128K tokens), not whatever lower default
        # this Claude Code version picks; a long film writes in parts anyway (LONG_FILM, STALLED)
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "128000",
    }
    if auth == "api":
        key = procs.secret("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY is not set (put it in the studio's .env)")
        cfg = film.claude_dir if film else os.path.join(HOME, "claude", "_smoke")
        os.makedirs(cfg, exist_ok=True)
        env.update(ANTHROPIC_API_KEY=key, CLAUDE_CONFIG_DIR=cfg)
    elif procs.secret("CLAUDE_CODE_OAUTH_TOKEN"):
        # a machine nobody logs into (the Azure VM) carries its login as a long-lived token
        # (`claude setup-token`), not as an interactive /login in its config folder -- so a film
        # needs no shared folder either: it gets its own, as on the key (no other film's history,
        # settings or memory), and a film that runs out of the plan resumes there on the key
        cfg = film.claude_dir if film else os.path.join(HOME, "claude", "_smoke")
        os.makedirs(cfg, exist_ok=True)
        env.update(
            CLAUDE_CODE_OAUTH_TOKEN=procs.secret("CLAUDE_CODE_OAUTH_TOKEN"), CLAUDE_CONFIG_DIR=cfg
        )
    return env


def _read(*parts):
    with open(os.path.join(KIT, *parts), encoding="utf-8") as f:
        return f.read()


# a part of a reference the studio's copy leaves out: from a line `// studio: cut` to a line
# `// studio: end cut` (the collage example's newspaper furniture, film.CAPS "fills")
CUT = re.compile(
    r"^[ \t]*// studio: cut\b.*?^[ \t]*// studio: end cut\b[^\n]*\n", re.MULTILINE | re.DOTALL
)


def _reference(*parts):
    """A file a capability puts in the system prompt, without the parts marked to leave out."""
    return CUT.sub("", _read(*parts))


# The kit in the system prompt: its header (sketch/kit.js above `// studio: cut`) and when to reach
# for it. The pieces are the ones 69 films of 2026-09-28..30 built by hand (studio/harvest.py);
# 47% of Claude's time went into writing a film's picture the first time
KIT_SECTION = """# Reference: the kit (`engine/kit.js`)

The pieces films keep needing, already drawn in this look and measured: text and labels, pills,
counters, checklists, callouts, charts, steppers and timelines, app windows, phones, chats,
cursors and buttons, icons, logos and end cards, page transitions, glows and particles, and a
table of every word cue at once (`SK.cues`). Use them for any of that, with the film's own
colours and type passed in, and spend your drawing on what is this film's alone: its people, its
places, its objects. The header below is the reference; the code is in `engine/kit.js` if you
need a detail.

```js
{KIT}
```

"""


CUE_RULE = """- Cue visuals to spoken words: `const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);`
  then `const tSoap = w(1, 'милом', 6.2);` -- the word as written in `vo.json` (any script works;
  punctuation and case are ignored), with a fallback time in seconds from the timeline."""
CUE_RULE_KIT = """- Cue visuals to spoken words, every cue at once at the top of film.js:
  `const T = SK.cues({soap: [1, 'милом'], again: [1, 'soap', 1], close: [4, null, 'e']});` then
  `T.soap` -- the word as written in `vo.json` (any script works; punctuation and case are
  ignored), the n-th match as a third element, a line's start (or with 'e' its end) for null. A
  word it cannot find is reported and takes its line's start: no fallback seconds to copy."""
KIT_STEP = """ Every piece the kit has comes from the kit (see "Reference: the kit"): text and labels,
   pills, counters, checklists, callouts, charts, screens, phones, chats, cursors and buttons,
   icons, logos and end cards, arrows and marks, glows and particles, page transitions -- with
   the film's own colours and type passed in. Draw by hand only what is this film's own: its
   people, its places, its objects."""


def system_prompt(look, caps=None):
    """prompt.md with the engine, the cast, the example and the sound notation filled in, read
    fresh so it always matches the code. It depends only on the look and what it is made of
    (caps: the film's, else the look's recipe) -- the film's own facts (its length, the
    prompt) come in the first message -- so films made close together share Claude's prompt
    cache."""
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
        "EXAMPLE_NIGHT": _read("studio", "examples", "night", "film.js"),
        "EXAMPLE_NIGHT_SCORE": _read("studio", "examples", "night", "score.json"),
        "EXAMPLE_NIGHT_SFX": _read("studio", "examples", "night", "sfx.json"),
        "EXAMPLE_BLUEPRINT": _read("studio", "examples", "blueprint", "film.js"),
        "EXAMPLE_BLUEPRINT_SCORE": _read("studio", "examples", "blueprint", "score.json"),
        "NOTATION": ref[a:b].strip() + "\n\n```\n" + notation + "\n```",
        "FX": fx,
        "INSTRUMENTS": ", ".join(inst) or "(none yet)",
    }
    # the people (film.CAPS "people"): only a film given people carries the section, so every
    # other film's prompt stays byte for byte what it was
    fill["PEOPLE"] = _read("studio", "people.md") if "people" in (caps or ()) else ""
    # a capability's own references, read only for the looks made of it (film.CAPS "fills")
    fill.update({k: _reference(*parts) for k, parts in fills(caps or RECIPES[look]).items()})
    # the kit's section, for the films made with it (a template's film made before it has none)
    fill["KIT_REFERENCE"] = KIT_SECTION.replace("{KIT}", fill["KIT"]) if "KIT" in fill else ""
    # where Claude acts: the cue rule and the step that writes film.js. In the kit's first bakeoff
    # (2026-10-01) the kit was only a section at the end, and four of six films still wrote their
    # own pills, phones, glows, arrows and confetti, and every one the old `w` cue wrapper
    kit = "KIT" in fill
    fill["CUE_RULE"] = CUE_RULE_KIT if kit else CUE_RULE
    fill["CUE_SHORT"] = (
        "`const T = SK.cues({...})` at the top" if kit else "`SK.w(line, 'word', fallbackSeconds)`"
    )
    fill["KIT_STEP"] = KIT_STEP if kit else ""
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


# a film longer than this is written in parts (LONG_FILM): its picture in one reply ran to 57k
# tokens and 7.7 minutes at 8 minutes of film (llwtme, 2026-09-28), and the per-reply cap is 128K
LONG_S = 90
LONG_FILM = (
    "\n\nThis is a long film, so work in parts: write film.js as the look, the helpers and the "
    "camera first, then add the scenes a few at a time (Edit), and check each batch -- never the "
    "whole picture in one reply. A reply that runs for many minutes is cut off and lost. Let the "
    "narration breathe too: a short pause (half a second to a second) between its sections."
)


def closing_s(n):
    """How long before the end the narration should stop: a beat for a short film, a few
    seconds for a long one (the 480 s film llwtme was told 479 s and used every one of them)."""
    return 1 if n <= 60 else min(4, round(1 + n / 120))


# Words per second of film the narration really takes, its lead, gaps and pauses included: 1.78
# (English), 1.80 (Ukrainian), 1.93 (Spanish) over the first full takes of 71 films, 2026-09-28..30
# (studio/harvest.py). The budget was 2.2: Claude wrote to it (words / budget 1.00 at the median),
# and 53 of the 71 first takes ran past the film's end, each a recording and a rewrite more. At 1.7
# about 57% fit as recorded, against 25%; a narration that ends a little early costs nothing.
WORDS_PER_S = 1.7


def narration_words(n):
    """The narration's word budget for an n-second film."""
    return max(4, round(WORDS_PER_S * (n - closing_s(n) - 0.5)))


def ask(film, recent=()):
    """The first message: the film's own facts, then the visitor's prompt, then what recent
    films chose -- here and not in the system prompt, which stays the same for every film of a
    look (and so stays cached). A remake of a template gets the template's own (templates.ask)."""
    if film.record().get("template"):
        return templates.ask(film) + mark_note(film)
    n = film.length
    text = (
        "Make the film.\n\nLength: %d seconds (fixed). Narration: about %d words, ending by "
        "about %d s. Your working time: about %d minutes (waiting for the machine is not "
        "counted); keep the last few for the music, the cues and the sound check.\n\nPrompt: %s"
        % (
            n,
            narration_words(n),
            n - closing_s(n),
            limits(n)["claude_s"] // 60,
            film.record().get("prompt", "").strip()
            or "(nothing typed: the idea is in what is attached)",
        )
    )
    if n > LONG_S and film.mode != "scenes":  # a scenes film is written in passes anyway
        text += LONG_FILM
    text += attached_note(film) + people_note(film) + mark_note(film) + voice_note(film)
    mine = library.note(film)  # the project, or the person's own cast and earlier films
    project = bool(film.record().get("project"))
    note = recent_note(film.look, recent, series=bool(mine), project=project)
    return text + "".join("\n\n" + x for x in (mine, note) if x)


def people_note(film):
    """The people the person added (film.CAPS "people"): who they are, the style they are being
    drawn in, and how to make them speak. They are drawn while Claude plans (draw_people)."""
    people = film.record().get("people") or []
    if not people:
        return ""
    lines = ["", "", 'People in this film (see "The people"), being drawn now:']
    for p in people:
        who = ' "%s"' % p["name"] if p.get("name") else ""
        lines.append(
            "- %s%s: a %s character from their photo (Read %s to see them). On screen: "
            'SK.head(\'%s\', x, y, h); their lines in vo.json: {"who": "%s", "text": ...} '
            "with a voice for them in cast."
            % (p["id"], who, p["style"], p["file"], p["id"], p["id"])
        )
    lines += [
        "",
        "They were added so they can be in the film and speak: give each of them lines of their "
        "own, in the words they would use, unless the prompt says otherwise. Use a name only "
        "where it was given or the prompt says it.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ a template's film


LEFTOVERS = (
    "The film still shows the template's own sample: %s. None of the sample's event, people, "
    "places or addresses may be in this film -- replace them with the person's content (or leave "
    "them out), in film.js and content.json -- and in vo.json, recording the changed lines again "
    "with the voice tool, when the film is narrated -- call check, and stop with one sentence. "
    "A word of these that is this film's own too -- an ordinary label any film of this kind says "
    '("Register", "Kitchen"), or a fact their event truly shares with the sample (the '
    "same city, the same hours) -- may stay: list it, exactly as written here, in content.json "
    'under "_own" (a list). Never list the event, people, places or addresses of the sample.'
)


async def no_leftovers(film, emit, meter, tools, auth):
    """A template's film must show nothing of the template's sample (templates.leftovers): one
    short turn to take out what is left, then it fails rather than show someone else's event."""
    left = await asyncio.to_thread(templates.leftovers, film)
    sid = film.record().get("claude_session")
    if left and sid:
        emit(
            {"type": "stage", "name": "claude", "text": "Claude is taking out the template's words"}
        )
        with contextlib.suppress(TimeoutError):
            await _within(
                run_claude(
                    film, emit, meter, tools, auth, prompt=LEFTOVERS % ", ".join(left), resume=sid
                ),
                Clock(),
                {"claude_s": WRAP_UP_S, "wall_s": WRAP_UP_S + 120},
            )
        left = await asyncio.to_thread(templates.leftovers, film)
    if left:
        raise RuntimeError("the film still shows the template's own words: %s" % ", ".join(left))


# ------------------------------------------------------------------ drawing the people
PEOPLE_S = 360  # how long drawing a film's people may take, the retry included
_PEOPLE = {}  # film id -> its drawing task (kept, so the task is not collected mid-way)


def draw_people_soon(film):
    """Start drawing the film's people in the background (Claude plans meanwhile)."""
    _PEOPLE[film.id] = asyncio.get_running_loop().create_task(draw_people(film))


async def draw_people(film):
    """Draw each person (scripts/head-rig.py: an image model redraws the photo in the film's
    style, with its mouth shapes and blink), then write rigs/ready.json: {id: {state, style,
    why}}. A person the model refuses is tried once more as a sticker, the style most photos
    pass in. The picture tools wait for ready.json (tools.Tools.people_ready)."""
    people = film.record().get("people") or []
    os.makedirs(film.path("rigs"), exist_ok=True)
    result, why = {}, {}
    try:
        for attempt in range(2):
            argv = [procs.python(), "-X", "utf8", os.path.join(KIT, "scripts", "head-rig.py")]
            argv += ["--manifest", film.manifest, "--jobs", str(films.MAX_PEOPLE)]
            try:
                _, tail = await procs.run(argv, film.dir, procs.step_env(film, "people"), PEOPLE_S)
            except procs.StepTimeout:
                tail = ["timed out"]
            for ln in tail:  # "  p2           felt: NOT BUILT -- the image model refused ..."
                m = re.match(r"\s*(p\d)\s+\S+: NOT BUILT -- (.*)", ln)
                if m:
                    why[m.group(1)] = m.group(2).strip()
            missing = [
                p for p in people if not os.path.exists(film.path("rigs", p["id"], "rig.json"))
            ]
            if not missing or attempt:
                break
            with open(film.manifest, encoding="utf-8") as f:  # once more, as stickers
                m_ = json.load(f)
            for p in missing:
                m_["heads"][p["id"]]["look"] = "sticker"
            with open(film.manifest, "w", encoding="utf-8") as f:
                json.dump(m_, f, indent=2)
    except Exception as e:  # noqa: BLE001 -- a film goes on without its people rather than fail
        print("film %s: people not drawn: %s" % (film.id, e), file=sys.stderr, flush=True)
    with open(film.manifest, encoding="utf-8") as f:
        heads = json.load(f).get("heads") or {}
    for p in people:
        ok = os.path.exists(film.path("rigs", p["id"], "rig.json"))
        result[p["id"]] = {
            "state": "ready" if ok else "failed",
            "style": (heads.get(p["id"]) or {}).get("look"),
            **({} if ok else {"why": why.get(p["id"]) or "not drawn"}),
        }
    with open(film.path("rigs", "ready.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    _PEOPLE.pop(film.id, None)
    return result


def voice_note(film):
    """The narrator the person picked for this film (the site's voice setting, studio.json
    "narrator"), in the first message: the voice is fixed, how it is read is still Claude's."""
    n = film.record().get("narrator") or {}
    if n.get("source") == "elevenlabs":
        return (
            "\n\nThe narrator is the person's own voice (their ElevenLabs account), set by the "
            "studio: leave `tts`, `voice` and `model` in vo.json as they are, and write only the "
            "`language` and the `lines` -- no `style`, no [tags]. Every recording is paid from "
            "their own characters: record once the words are final, and record again only a line "
            "that came out wrong. If the voice tool says the account cannot speak, stop."
            + (
                " The people in the film are seen, not heard: that voice is the person's own, and "
                "it is never put in someone else's mouth -- every line is the narrator's (no "
                "`who`, no `cast`)."
                if film.record().get("people")
                else ""
            )
        )
    if n.get("source") == "kitcut" and n.get("voice"):
        return (
            "\n\nThe narrator's voice is the person's choice: %s. Keep `voice` as it is in "
            "vo.json (the studio puts it back); choose the `style` -- how it is read -- and the "
            "`language` as you would." % n["voice"]
        )
    return ""


def waiting_words(info):
    """Why a film waits for its person's voice, in one sentence (the film page adds what to do)."""
    said = tools_mod.BLOCKED_WORDS.get(
        info.get("reason"), "the narrator's voice could not be recorded"
    )
    return said[:1].upper() + said[1:] + "."


def attached_note(film):
    """What the visitor attached (studio.json attachments, files in inputs/), and how to take it:
    a picture may be something to show, a reference, or the brief itself, and nobody says which,
    so Claude looks, decides, and says what it decided (the first thing the page shows). A short
    document is quoted here; a long one is named, for Claude to Read."""
    rec = film.record()
    items = rec.get("attachments") or []
    if not items:
        return ""
    lines = ["", "", "Attached by the person:"]
    notes = [a for a in items if a["kind"] == "audio"]
    pics = [a for a in items if a["kind"] == "image"]
    docs = [a for a in items if a["kind"] == "text"]
    for i, a in enumerate(notes, 1):
        lines.append(
            '- Voice note %d (%s, written out by speech recognition; a name may be misheard): "%s"'
            % (i, _mmss(a.get("secs") or 0), (a.get("transcript") or "").strip())
        )
    for i, a in enumerate(docs, 1):
        head = "- Document %d%s (%s words, %s)" % (
            i,
            ' "%s"' % a["name"] if a.get("name") else "",
            a.get("words"),
            a["file"],
        )
        text = _doc_text(film.path(*a["file"].split("/")))
        if (
            text is not None and "<gpx" in text[:600]
        ):  # a route: the route tool's, not words to read
            lines.append(
                head + ": a GPX track. The route tool reads it: route(gpx=%s); there is no need "
                "to Read it." % json.dumps(a.get("name") or "Document %d" % i)
            )
            continue
        if text is not None and len(text) <= DOC_INLINE:
            lines += [head + ":", "<<<", text.strip(), ">>>"]
        else:
            lines.append(head + ": Read %s." % a["file"])
    if docs:
        lines += [
            "",
            "The documents are the person's own brief, written or chosen for this film: a script, "
            "notes, facts about a product or a business, a list of scenes. Read every one before "
            "you plan and take what it says as part of the prompt; where the typed prompt and a "
            "document disagree, the typed prompt wins. A script's words may be the narration "
            "itself, but the film keeps its length: cut to what matters most rather than cram. "
            "Keep names, figures and quoted lines exactly as written.",
        ]
    for a in pics:
        lines.append(
            "- Picture %s (%sx%s): Read %s to see it. On screen: SK.image('%s', x, y, w)."
            % (a["name"], a.get("w"), a.get("h"), a["file"], a["name"])
        )
    if pics:
        lines += [
            "",
            "Read every picture before you plan. Each is one of three things: material to show "
            "(a logo, a product, a person, a place: put it on screen with SK.image), a reference "
            "to match (a look, a character, a layout: draw in its spirit, don't paste it), or the "
            "brief itself (a screenshot, a note, a sketch of the story: read it as the prompt). "
            "Where the person said how to use one, do that; otherwise decide. Before you write "
            "anything, say in one short sentence per picture what you took it to be. A photo in "
            "a drawn film sits best framed, as a pinned print or a card, so it belongs to the "
            "drawn world. A picture you don't draw never leaves the studio.",
        ]
    if not rec.get("prompt", "").strip():
        lines += [
            "",
            "Nothing was typed, so the film has no title yet: once you know what it is, call "
            "name_film with a short title (a few words, in the brief's language).",
        ]
    return "\n".join(lines)


def _mmss(s):
    return "%d:%02d" % (int(s) // 60, int(s) % 60)


DOC_INLINE = 6000  # a document up to this many characters is in the first message; longer, Read


def _doc_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# the visitor's pictures, their project's, and what Claude took from the web (web-grab.py)
PICTURE = r"upload\d+|pic_[a-z0-9_]+|web_[a-z0-9_]+"


def drop_unused_uploads(film):
    """The pictures (the person's, attached or their project's, and those Claude took from the
    web) that neither film.js nor the cast draws leave the manifest before the final render, so
    they are never bundled into the film's files. Returns the names dropped. A template's film
    names its pictures in its data (content.json), not its code: read too, or every photo it
    found left the film and its frames drew empty (an open house remake, 2026-10-04)."""
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    images = m.get("images") or {}
    code = [film.path("film.js")]
    code += [film.path(*str(rel).split("/")) for rel in (m.get("data") or {}).values()]
    if os.path.isdir(film.path("cast")):
        code += [film.path("cast", n) for n in os.listdir(film.path("cast")) if n.endswith(".js")]
    used = set()
    for p in code:
        try:
            with open(p, encoding="utf-8") as f:
                used |= set(re.findall(r"\b(?:%s)\b" % PICTURE, f.read()))
        except OSError:
            pass
    gone = [k for k in images if re.fullmatch(PICTURE, k) and k not in used]
    if gone:
        for k in gone:
            del images[k]
        films._write_json(film.manifest, m)
    return gone


def recent_films(film, n=8):
    """The directions of the last n finished films made here, other than this one, newest
    first: what they chose, never what they were asked."""
    out = []
    for f in Film.all():
        if len(out) >= n:
            break
        if f.id != film.id and f.state == "done":
            out.append(f.record().get("direction") or f.direction())
    return out


def recent_note(look, dirs, series=False, project=False):
    """What recent films chose, counted: 'grounds: paper x5, night'. Only the choices from the
    menus: never what a film was asked, nor its cast (a person's own). series: the person has
    films of their own (library.note), which a continuation keeps to; project: the film is an
    episode, and its project's brief and episodes come first."""
    if not dirs:
        return ""

    def tally(values, k=4):
        c = Counter(v for v in values if v)
        return ", ".join("%s x%d" % (v, m) if m > 1 else str(v) for v, m in c.most_common(k))

    def firsts(values, words, k=4):  # the opening words of each, without repeats
        seen = dict.fromkeys(" ".join(str(v).split()[:words]) for v in values if v)
        return "; ".join(list(seen)[:k])

    same = [d for d in dirs if d.get("look") == look]
    mine = direction_fields(RECIPES.get(look, ()))  # what films of this look record
    news = sum(1 for d in same if d.get("newsprint"))
    rows = [
        ("grounds", tally(d.get("ground") for d in same) if "ground" in mine else ""),
        (
            "painting styles",
            firsts((d.get("paint_style") for d in same), 6) if "paint_style" in mine else "",
        ),
        (
            "print faces",
            tally((f for d in same for f in d.get("faces") or []), 6) if "faces" in mine else "",
        ),
        (
            "a newspaper page under the film",
            "%d of the last %d" % (news, len(same)) if "newsprint" in mine and news else "",
        ),
        # a voice the person picked is theirs, not a choice for other films to weigh
        ("voices", tally(d.get("voice") for d in dirs if not d.get("voice_pinned"))),
        ("voice directions", firsts((d.get("voice_style") for d in dirs), 8)),
        ("instruments", tally((i for d in dirs for i in d.get("instruments") or []), 6)),
        ("tempos", tally(d.get("bpm") for d in dirs)),
    ]
    rows = ["- %s: %s" % (k, v) for k, v in rows if v]
    return (
        "Recent films made here, by everyone, chose (choose freshly for this prompt; repeat one "
        "only when it clearly calls for it%s):\n"
        % (
            ", or when the project's brief or its earlier episodes above do"
            if project
            else ", or when it continues one of this person's films above"
            if series
            else ""
        )
        + "\n".join(rows)
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
            return "looking at the %s" % paint_words(film.caps)[1]
        if p.endswith("motion.png"):
            return "looking at the cuts"
        return "looking at the review sheet" if p.endswith("sheet.png") else "read %s" % p
    if name == "WebSearch":
        return "searching the web: %s" % str(inp.get("query", ""))[:120]
    if name == "WebFetch":
        return "reading %s" % str(inp.get("url", ""))[:160]
    tool = name.removeprefix("mcp__studio__")
    if tool == "picture":
        return "saving a picture from %s" % str(inp.get("url", ""))[:160]
    if tool == "page":
        return "photographing the page %s" % str(inp.get("url", ""))[:160]
    if tool == "font":
        return "adding the font %s" % str(inp.get("family", ""))[:60]
    if tool == "check":
        return "checking film.js for syntax errors"
    if tool == "stills":
        return "rendering %d review stills" % len(inp.get("times") or [])
    if tool == "sound":
        return "rendering the soundtrack"
    if tool == "motion":
        return "checking the cuts and the motion"
    if tool == "route":
        return "drawing the route on a real map"
    if tool == "voice":
        if inp.get("retake_line") is not None:
            return "recording line %s again" % inp["retake_line"]
        return "recording the narration (Gemini TTS)"
    if tool == "paint":
        return (
            "repainting %s" % ", ".join(inp["retake"])
            if inp.get("retake")
            else paint_words(film.caps)[0]
        )
    return name


REFUSED = re.compile(
    r"HTTP (?:401|403|429|451)\b|\bForbidden\b|access denied|bot protection", re.IGNORECASE
)


def refused_note(response):
    """What to tell Claude after WebFetch was turned away by the site (not by the guard), or ""."""
    text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
    if not REFUSED.search(text or ""):
        return ""
    return (
        "That site turned WebFetch away. The studio's page tool opens it in a real browser, "
        "which most such sites let in; the page's words then land in web/<name>.txt to Read. "
        "A page you have not read is not a source."
    )


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


# a web search is billed per request, whatever the model: $10 per 1,000
WEB_SEARCH_USD = 0.01


def _price(model, t):
    p = PRICES.get(model, PRICES[MODEL])
    return (
        t["input"] * p["in"]
        + t["output"] * p["out"]
        + t["cache_read"] * p["read"]
        + t["cache_write_5m"] * p["w5m"]
        + t["cache_write_1h"] * p["w1h"]
    ) / 1e6 + t.get("web_search", 0) * WEB_SEARCH_USD


def _tokens(u):
    w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    return {
        "input": u.get("input_tokens") or 0,
        "output": u.get("output_tokens") or 0,
        "cache_read": u.get("cache_read_input_tokens") or 0,
        "cache_write_5m": (u.get("cache_creation_input_tokens") or 0) - w1h,
        "cache_write_1h": w1h,
        "web_search": (u.get("server_tool_use") or {}).get("web_search_requests") or 0,
    }


def _merge(a, b):
    """Two readings of one response's usage: every count at its highest. The assistant message
    Claude Code passes on carries the counts as the response began (a few output tokens); the
    stream's message_delta carries the final ones."""
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict):
            out[k] = _merge(out.get(k), v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = max(out.get(k) or 0, v)
        elif k not in out:
            out[k] = v
    return out


class Meter:
    """Token counts per API response, priced as they arrive, so a run cut short (a timeout,
    a crash, a stop) is still costed. The SDK reports its own total only at the very end."""

    def __init__(self, model=MODEL):
        self.model, self.msgs = model, {}

    def add(self, msg_id, usage, model=None, at=None):
        if msg_id and usage:
            # one response is read several times as it streams: keep the highest counts
            old = self.msgs.get(msg_id, {})
            self.msgs[msg_id] = {
                "usage": _merge(old.get("usage"), usage),
                "model": model or old.get("model") or self.model,
                "at": old.get("at") or at or store.now(),
            }

    def stream(self, ev, state):
        """A raw API stream event (the SDK's StreamEvent): message_start names the response and
        its opening counts, message_delta its final output. Returns True when the cost moved."""
        kind = ev.get("type")
        if kind == "message_start":
            m = ev.get("message") or {}
            state["id"] = m.get("id")
            self.add(state["id"], m.get("usage"), m.get("model"))
            return True
        if kind == "message_delta" and state.get("id") and ev.get("usage"):
            self.add(state["id"], ev["usage"])
            return True
        return False

    def tokens(self):
        t = dict.fromkeys(
            ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "web_search"), 0
        )
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
        # an error, not sys.exit: inside the server this runs in one film's task, and exiting
        # took the whole studio down with it (found on the Azure VM, which has no login)
        raise RuntimeError(
            "the Claude Code CLI is not installed (npm i -g @anthropic-ai/claude-code)"
        )
    return best[1]


def director_files(film):
    """What the director of a film made in scenes may write: the narration, the look, the plan,
    scene 1, the cast -- and paint.json when the film paints anything. It asked for the painted
    look by name, so a collage film's director could order no cut-outs, and i4d52n's twelve
    scenes drew their bikes in code (2026-09-29)."""
    allow = ["vo.json", "film.js", "scenes.json", "scenes/01-*.js", "cast/*.js", "engine/props.js"]
    return allow + (["paint.json"] if paint_kinds(film.caps) else [])


async def run_claude(
    film,
    emit,
    meter,
    tools,
    auth="api",
    prompt=None,
    resume=None,
    budget_usd=None,
    system=None,
    effort=None,
):
    """Claude's part: write, review and fix. Returns the SDK's ResultMessage (or None). With
    `resume` (a session id) and a `prompt`, one more turn of a session that was stopped;
    `budget_usd` then caps what that turn may add (the film's own cap less what it spent)."""
    pending, result, limited = {}, None, None

    async def pre_tool(inp, tool_use_id, ctx):
        ok, why = guard(inp["tool_name"], inp["tool_input"], film, getattr(tools, "allow", None))
        if not ok:
            emit({"type": "blocked", "text": why})
        out = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if ok else "deny"}
        if not ok:
            out["permissionDecisionReason"] = why
        return {"hookSpecificOutput": out}

    async def can_use(name, inp, ctx):  # backstop: the hook above decides first
        ok, why = guard(name, inp, film, getattr(tools, "allow", None))
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

    async def post_fetch(inp, tool_use_id, ctx):
        # a site that refuses WebFetch (openai.com answers 403) mostly lets a browser in: the
        # researched films gave up there and cited the page anyway
        note = refused_note(inp.get("tool_response"))
        if note:
            return {
                "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}
            }
        return {}

    # by file: with the engine and the cast inlined it is ~80 KB, more than twice the length
    # Windows allows a command line (the spawn then fails as "Claude Code not found")
    sp = film.path("temp", "system-prompt.md")
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(system or system_prompt(film.look, film.caps))
    cli = None
    if auth == "login":
        try:
            cli = claude_cli()
        except RuntimeError as e:  # no Claude Code on this machine: the login cannot be used
            raise SignInError(str(e)) from None
    opts = ClaudeAgentOptions(
        model=MODEL,
        effort=effort or EFFORT,  # a pass of a film made in scenes thinks less (scenes.EFFORT)
        cwd=film.dir,
        system_prompt={"type": "file", "path": sp},
        # the web: facts, and the real logos, pages and fonts of what a film is about (the
        # studio's picture, page and font tools); guard.py keeps WebFetch on the public internet
        tools=["Read", "Write", "Edit", "WebSearch", "WebFetch"],
        mcp_servers={"studio": tools.server()},
        strict_mcp_config=True,
        setting_sources=[],
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool])],
            "PostToolUse": [
                HookMatcher(matcher="Write|Edit", hooks=[post_tool]),
                HookMatcher(matcher="WebFetch", hooks=[post_fetch]),
            ],
        },
        can_use_tool=can_use,
        max_turns=limits(film.length)["turns"],
        max_budget_usd=budget_usd or limits(film.length)["budget_usd"],
        # a review sheet of painted frames is a PNG of several MB, and it comes back to the SDK
        # as one message (the default limit, 1 MB, failed a painted film)
        max_buffer_size=64 * 1024 * 1024,
        env=claude_env(film, auth),
        cli_path=cli,
        # the raw stream too: only its message_delta events carry a response's final token count
        include_partial_messages=True,
        resume=resume,
        # Claude Code's own log of the run (its requests, retries, timeouts), one file a run, beside
        # the transcript and outside the film, so Claude never reads it and it never ships. Without
        # it a stalled film showed only "Request timed out." (llwtme, 2026-09-28); claude_log.py
        # reads the two together
        extra_args={"debug-file": debug_log(film)},
    )
    streamed, signin = {}, None
    try:
        async with ClaudeSDKClient(options=opts) as client:
            await client.query(prompt or ask(film, recent_films(film)))
            pulse = getattr(tools, "pulse", None)
            async for msg in client.receive_response():
                if pulse is not None:
                    pulse.beat()
                if isinstance(msg, StreamEvent):
                    before = meter.usd()
                    if meter.stream(msg.event, streamed) and round(meter.usd(), 3) != round(
                        before, 3
                    ):
                        emit({"type": "cost", "usd": round(meter.usd(), 4)})
                elif isinstance(msg, SystemMessage) and msg.subtype == "init":
                    d = msg.data
                    if not resume and d.get("session_id"):  # to wrap up in, if time runs out
                        tools.session = d["session_id"]
                        # a pass of a film made in scenes keeps its own (scenes.py); a film's is
                        # the one conversation that makes it
                        if getattr(tools, "pass_name", None) is None:
                            film.update(claude_session=d["session_id"])
                    emit(
                        {
                            "type": "init",
                            "model": d.get("model"),
                            "key": d.get("apiKeySource") or auth,
                            "tools": [t for t in d.get("tools", []) if t.startswith("mcp__")],
                        }
                    )
                elif isinstance(msg, AssistantMessage):
                    if msg.error == "authentication_failed":  # see SignInError
                        said = [getattr(b, "text", "") for b in msg.content]
                        signin = " ".join(s for s in said if s).strip() or msg.error
                        continue
                    if auth == "login" and msg.error in ("rate_limit", "billing_error"):
                        said = [getattr(b, "text", "") for b in msg.content]
                        limited = " ".join(s for s in said if s).strip() or msg.error
                        continue
                    before = meter.usd()
                    meter.add(msg.message_id or msg.uuid, msg.usage, msg.model)
                    if meter.usd() != before:
                        emit({"type": "cost", "usd": round(meter.usd(), 4)})
                    for b in msg.content:
                        if isinstance(b, TextBlock) and b.text.strip():
                            emit({"type": "say", "text": b.text.strip()})
                        elif isinstance(b, ToolUseBlock):
                            pending[b.id] = (b.name, b.input)
                            if pulse is not None:
                                pulse.busy = len(pending)
                            emit({"type": "tool", "text": _describe(b.name, b.input, film)})
                elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                    for b in msg.content:
                        if not isinstance(b, ToolResultBlock):
                            continue
                        pending.pop(b.tool_use_id, None)
                        if pulse is not None:
                            pulse.busy = len(pending)
                        text = _result_text(b)
                        if b.is_error and "hook error" not in text:  # denials were reported
                            emit({"type": "fail", "text": text.strip()[-400:]})
                    if getattr(tools, "parked", None):  # the voice paused the film
                        raise Parked(tools.parked)
                elif isinstance(msg, ResultMessage):
                    result = msg
                    if msg.is_error and msg.api_error_status == 401:
                        signin = signin or msg.result or "401 from the API"
    except CLINotFoundError as e:  # the CLI the login needs is not there
        raise SignInError(str(e)) from None
    if signin:
        raise SignInError(signin)
    if limited:
        raise PlanLimit(limited)
    return result


def debug_log(film):
    """Where this run of Claude Code writes its debug log: STUDIO_HOME/claude/<film>/logs/."""
    d = os.path.join(film.claude_dir, "logs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "claude-%s.log" % datetime.now().strftime("%Y%m%d-%H%M%S"))


# How long Claude may go without a word -- no message from Claude Code, no event of the film's,
# and no tool of the studio's running -- before the studio calls it stalled and picks the session
# up again (make_film). Under Claude Code's own request timeout (API_TIMEOUT_MS), so the studio
# acts before Claude Code starts the same reply again from scratch: that is how film llwtme sat
# for an hour, twice, on 2026-09-28, with the CLI alive and the API answering other requests.
STALL_S = int(os.environ.get("STUDIO_STALL_S") or 20 * 60)
STALL_RETRIES = 2  # picked up at most this many times; then the film fails, and is refunded
STALLED = (
    "Your last reply never arrived: the studio waited %d minutes, got nothing back and cut it "
    "off. This is the same session, and everything before that reply is on disk as it was. Carry "
    "on from where you were, in shorter replies: write or change film.js a few scenes at a time, "
    "never the whole picture in one reply. You have about %d minutes left."
)


OVER_LIMIT = (
    "Your last reply was cut off by a usage limit on the studio's side, not by anything you did; "
    "that is lifted now. This is the same session, and everything before that reply is on disk as "
    "it was. Carry on from where you were. You have about %d minutes left."
)


class Stalled(Exception):
    pass


class Parked(Exception):  # noqa: N818 -- a pause, not an error
    """The film waits for its person: their own ElevenLabs account would not speak (tools.voice
    set tools.parked). Raised once Claude has the tool's answer, so its session ends whole and
    Continue picks it up there (server.continue_film)."""

    def __init__(self, info):
        super().__init__(info.get("reason"))
        self.info = info


class Pulse:
    """When Claude last showed a sign of life (run_claude beats on every message from Claude
    Code, make_film on every event of the film's), and how many of the studio's tools it is
    waiting on: a tool at work is not a stall, its step has a timeout of its own."""

    def __init__(self):
        self.at, self.busy = time.time(), 0

    def beat(self):
        self.at = time.time()

    def silent(self):
        return 0 if self.busy else time.time() - self.at

    def stalled(self):
        return self.silent() > STALL_S


async def _within(coro, clock, lim, pulse=None):
    """Run Claude's part, stopping it past its working time (the clock does not count waits for
    the machine) or its wall time (lim: film.limits), or once it has gone silent (Stalled)."""
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=2)
            if done:
                return task.result()
            if clock.active() > lim["claude_s"] or clock.wall() > lim["wall_s"]:
                raise TimeoutError()
            if pulse is not None and pulse.stalled():
                raise Stalled(pulse.silent())
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


async def make_film(
    film,
    emit=None,
    sched=None,
    auth="api",
    finish_only=False,
    control=None,
    resume=False,
    resume_minutes=None,
    resume_prompt=None,
):
    """The whole film, from its Claude slot to the video. Every step is reported through
    emit(dict); returns the final summary. Whatever happens, the run's cost goes to
    kitcut.studio_runs (STORE) and studio.json.

    finish_only: Claude's part is already done (a film a restart interrupted while mixing or
    rendering); only the soundtrack and the video are made. resume: Claude's part was stopped
    half-way (the studio restarted under it); one more turn of the film's own saved session
    picks it up (RESUME), then the film is finished as usual. Either way what the earlier attempt
    spent is carried into the record, not replaced. control: a dict the server may set
    {"requeue": True} in before it cancels a film still waiting for its slot -- the film then
    stays queued for the next server instead of being marked cancelled.

    The process making a film owns it (studio.json "server", peers.py) for as long as it lives,
    so the leading server never adopts a film someone is making -- a server's, or resume.py's
    picking one up by hand. A film left queued or finishing goes back to nobody, for the leader."""
    emit = emit or (lambda ev: None)
    sched = sched or Sched()
    control = control if control is not None else {}
    peers.hold_own()
    if film.record().get("server") != peers.SERVER_ID:
        film.update(server=peers.SERVER_ID)
    rec = film.record()
    prompt, length, look = rec.get("prompt", ""), film.length, film.look
    # an earlier attempt's Claude part, costed by the server that ran it: carried, not replaced
    carry = rec if (finish_only or resume) else {}
    prior_calls = None  # finish_only: the record's per-call detail is left as it is
    if resume:
        if not rec.get("claude_session"):
            raise RuntimeError("%s has no Claude session to pick up" % film.id)
        doc = await asyncio.to_thread(STORE.get, film.id)
        prior_calls = (doc.get("calls") or []) if doc else None
    fps = 60
    with contextlib.suppress(OSError, ValueError):
        with open(film.manifest, encoding="utf-8") as f:
            fps = json.load(f).get("fps", 60)
    t0, stages, meter, res = time.time(), {}, Meter(), None
    clock = Clock()
    tools = Tools(film, sched, emit, clock)
    tools.pulse = Pulse()  # the stall watchdog's (talk_to_claude)
    billed = auth == "api"  # on the login, Claude's tokens are covered by the plan
    summary = {
        "prompt": prompt,
        "model": MODEL,
        "effort": scenes.EFFORT if film.mode == "scenes" else EFFORT,
        "length": length,
        "look": look,
        "release": RELEASE,
        "auth": auth,
    }
    summary.update(
        {
            k: carry[k]
            for k in ("turns", "claude_said", "session", "overtime", "claude_login_usd")
            if k in carry
        }
    )
    emit({"type": "job", "id": film.id, "model": MODEL, "length": length, "look": look})

    def price():
        # the SDK's own figure when the run reached its end; the meter's when it did not. Not
        # for a resumed session: Claude Code may restore what the session spent before, and the
        # meter counts this attempt's responses only
        metered = round(meter.usd(), 4)
        sdk = res.total_cost_usd if res is not None and not resume else None
        claude = round(sdk, 4) if sdk is not None else metered
        tokens = meter.tokens()
        rows = _spend(film, "audio", "vo", "spend.jsonl")
        # a person's own ElevenLabs voice spends their characters, not KitCut's money: counted
        # apart (user_tts_chars), and never in cost_usd or the day's budget
        tts_rows = [r for r in rows if r.get("payer") != "user"]
        own_rows = [r for r in rows if r.get("payer") == "user"]
        if own_rows:
            summary["user_tts_chars"] = sum(r.get("chars") or 0 for r in own_rows)
            summary["user_tts_model"] = own_rows[-1].get("model")
        img_rows = _spend(film, "images", "spend.jsonl")
        tts = round(sum(r["cost_usd"] for r in tts_rows), 6)
        # the people's drawings (draw_people) are pictures too, kept apart so they never count
        # against the film's paintings
        img = round(
            sum(r.get("cost_usd") or 0 for r in img_rows + _spend(film, "rigs", "spend.jsonl")), 6
        )
        if film.mode == "scenes":  # every pass's own cost (scenes.py), and the one under way
            claude = metered = round(scenes.spent(film) + meter.usd() - pass_base[0], 4)
        elif carry:  # plus what Claude's earlier attempt spent
            claude = round(claude + (carry.get("claude_cost_usd") or 0), 4)
            metered = round(metered + (carry.get("cost_metered_usd") or 0), 4)
            for k, v in (carry.get("tokens") or {}).items():
                tokens[k] = tokens.get(k, 0) + v
        summary.update(
            # everything this film cost: Claude + the voice + the paintings
            # on the key after the plan ran out (to_key): only what it spent from there
            cost_usd=round(
                (claude - summary.get("claude_login_usd", 0) if billed else 0) + tts + img, 4
            ),
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
            tokens=tokens,
        )

    # how long the film took: a picked-up film's earlier attempt counts too (the site says it)
    before_s = (carry.get("seconds") or 0) if resume else 0

    def took():
        return round(before_s + time.time() - t0, 1)

    loop = asyncio.get_running_loop()
    saved_at = [time.time()]
    outer = emit

    def emit(ev):  # noqa: F811 -- the same emit, keeping the record's cost current as it grows
        outer(ev)
        tools.pulse.beat()  # anything the film reports is a sign of life
        if ev["type"] == "cost" and time.time() - saved_at[0] > 5:
            saved_at[0] = time.time()
            price()
            now = {
                "cost_usd": summary["cost_usd"],
                "tokens": summary["tokens"],
                "calls": (prior_calls or []) + meter.calls(),
            }
            loop.run_in_executor(None, STORE.save, film.id, now)

    tools.emit = emit

    def on_wait(pool, ahead):
        emit({"type": "wait", "pool": pool, "ahead": ahead, "text": waiting_text(pool, ahead)})

    lim, talk = limits(length), {}
    if film.mode == "scenes":  # every pass's allowance (scenes.film_claude_s), waits on top
        need = scenes.film_claude_s(film)
        if need > lim["claude_s"]:
            lim = lim | {"claude_s": need, "wall_s": lim["wall_s"] + need - lim["claude_s"]}
    if resume:  # what is left of the film's working time and budget, and the turn that picks it up
        used = (carry.get("stages") or {}).get("claude") or carry.get("seconds") or 0
        # what the film's own limit has left (a film stopped before its picture was written needs
        # most of it), or what the operator gives it (resume.py --minutes)
        work = resume_minutes * 60 if resume_minutes else max(RESUME_MIN_S, lim["claude_s"] - used)
        lim = lim | {"claude_s": work, "wall_s": work + 20 * 60}
        spent = carry.get("claude_cost_usd") or 0
        talk = {
            "prompt": (resume_prompt or (RESUME_UNVOICED if unvoiced(film) else RESUME))
            % round(work / 60),
            "resume": rec["claude_session"],
            "budget_usd": max(1.0, lim["budget_usd"] - spent),
        }
        summary["resumed"] = {
            "after": carry.get("error") or carry.get("state"),
            "earlier_s": carry.get("seconds"),
            "earlier_usd": spent,
        }

    async def talk_to_claude(say=None, within=None):
        """One conversation with Claude: the film's, or one pass of a film made in scenes (say:
        run_claude's opening -- prompt, resume, budget, system; within: its limits). A reply
        that never comes (Stalled) is cut off and the same session picked up again with STALLED,
        at most STALL_RETRIES times; its working time and budget go on counting from where they
        were. Past that the film fails -- and is refunded -- rather than sitting for hours in
        Claude Code's own retries. A conversation on the login that runs into the plan's limit
        (PlanLimit) is picked up the same way, on the key (to_key)."""
        nonlocal auth, billed
        say = dict(talk if say is None else say)
        within = lim if within is None else within
        m0 = meter.usd()
        budget0 = say.get("budget_usd") or max(
            1.0, limits(length)["budget_usd"] - (carry.get("claude_cost_usd") or 0)
        )
        attempt = 0  # stalls so far (a plan limit is picked up once, and does not count)
        while True:
            tools.pulse.beat()
            try:
                return await _within(
                    run_claude(film, emit, meter, tools, auth, **say), clock, within, tools.pulse
                )
            except PlanLimit as e:
                sid = tools.session or film.record().get("claude_session")
                if not sid or not procs.secret("CLAUDE_CODE_OAUTH_TOKEN"):
                    # the session is in this machine's own config folder (an interactive login),
                    # which the key cannot read: nothing to pick up
                    raise RuntimeError("Claude's plan ran out: %s" % e.why) from None
                auth, billed = await to_key(e.why)
                left = max(RESUME_MIN_S, within["claude_s"] - clock.active())
                say = {
                    "prompt": OVER_LIMIT % round(left / 60),
                    "resume": sid,
                    "budget_usd": max(1.0, budget0 - (meter.usd() - m0)),
                } | {k: say[k] for k in ("system", "effort") if say.get(k)}  # a scenes pass's
                continue
            except Stalled as e:
                silent = int(e.args[0]) if e.args else STALL_S
                summary["stalls"] = summary.get("stalls", 0) + 1
                # the conversation's own session: a pass's, or the film's
                sid = tools.session or film.record().get("claude_session")
                print(
                    "film %s: STALL, no reply from Claude for %d s (%d of %d)"
                    % (film.id, silent, attempt + 1, STALL_RETRIES + 1),
                    file=sys.stderr,
                    flush=True,
                )
                if attempt == STALL_RETRIES or not sid:
                    raise RuntimeError(
                        "Claude stopped answering (%d minutes without a reply, %d times)"
                        % (silent // 60, attempt + 1)
                    ) from None
                left = max(RESUME_MIN_S, within["claude_s"] - clock.active())
                emit(
                    {
                        "type": "fail",
                        "text": "Claude had not answered for %d minutes; the studio picked the "
                        "film up again where it was" % (silent // 60),
                    }
                )
                say = {
                    "prompt": STALLED % (silent // 60, round(left / 60)),
                    "resume": sid,
                    "budget_usd": max(1.0, budget0 - (meter.usd() - m0)),
                } | {k: say[k] for k in ("system", "effort") if say.get(k)}  # a scenes pass's
                attempt += 1

    async def to_key(why):
        """The plan is spent half-way through the film: from here it is made on the key -- the
        record says so and why, and only what Claude spends from now on is billed."""
        price()
        summary["claude_login_usd"] = summary["claude_cost_usd"]
        summary.update(auth="api", fallback={"from": "login", "why": why, "limit": True})
        film.update(
            auth="api", fallback=summary["fallback"], claude_login_usd=summary["claude_login_usd"]
        )
        await save(film.id, {"auth": "api", "fallback": summary["fallback"]})
        print("film %s: PLAN LIMIT, on the key from here: %s" % (film.id, why), file=sys.stderr)
        emit({"type": "fallback", "from": "login", "to": "api", "why": why})
        return "api", True

    pass_base = [meter.usd()]  # the meter where the last finished pass of a scenes film left it

    async def make_scenes():
        """A film made in scenes (scenes.py): the director unless its work is done, each scene not
        done, then the editor -- each a fresh conversation with its own opening, limits and the
        files it may write; each pass's state and cost go to studio.json as it ends, so a crash
        or a restart costs only the pass in progress."""
        system = system_prompt(film.look, film.caps) + scenes.system_section()
        passes = summary.setdefault("passes", [])

        async def one(kind, key, opening, allow, span=None, text=""):
            n = scenes.tries(film, key)
            if n >= scenes.TRIES:
                raise RuntimeError("the %s did not finish in %d tries" % (kind, scenes.TRIES))
            scenes.mark(film, key, state="todo", tries=n + 1)
            allowance = scenes.pass_limits(film, kind, span)
            within = lim | {
                "claude_s": min(lim["claude_s"], clock.active() + allowance["claude_s"]),
                "wall_s": min(lim["wall_s"], clock.wall() + allowance["claude_s"] + 30 * 60),
            }
            tools.pass_name, tools.allow, tools.span, tools.session = key, allow, span, None
            emit({"type": "stage", "name": "claude", "text": text})
            s0, res = time.time(), None
            try:
                res = await talk_to_claude(
                    {
                        "prompt": opening,
                        "system": system,
                        "budget_usd": allowance["budget_usd"],
                        "effort": scenes.EFFORT,
                    },
                    within,
                )
            except TimeoutError:
                pass  # past its time: judged by what it left, like any pass
            finally:
                tools.pass_name, tools.allow, tools.span = None, None, None
            cost = round(meter.usd() - pass_base[0], 4)
            pass_base[0] = meter.usd()
            prev = scenes.progress(film).get(key, {}).get("cost_usd") or 0
            scenes.mark(film, key, session=tools.session, cost_usd=round(prev + cost, 4))
            film.update(claude_cost_usd=scenes.spent(film))
            passes.append(
                {
                    "pass": key,
                    "session": tools.session,
                    "cost_usd": cost,
                    "seconds": round(time.time() - s0, 1),
                    "turns": res.num_turns if res is not None else None,
                }
            )
            return res

        async def parses():
            try:
                await tools.check()
                return True
            except ToolError:
                return False

        def said(res, n=1500):
            return ((res.result if res is not None else "") or "").strip()[:n]

        # the director: the narration, the look, the plan, and scene 1 as the pilot
        allow = director_files(film)
        while not scenes.done(film, scenes.DIRECTOR):
            res = await one(
                "director",
                scenes.DIRECTOR,
                scenes.director_message(film, ask(film, recent_films(film))),
                allow,
                text="Claude is planning the film",
            )
            rows = scenes.spans(film)
            if (
                rows
                and scenes.timed(film)
                and os.path.exists(film.path(*scenes.scene_file(rows[0][0]).split("/")))
                and await parses()
            ):
                scenes.mark(film, scenes.DIRECTOR, state="done", summary=said(res))
                scenes.mark(film, rows[0][0]["id"], state="done", summary=rows[0][0].get("shows"))
        # the scenes, one fresh conversation each
        rows = scenes.spans(film)
        for k, (sc, a, b) in enumerate(rows):
            if scenes.done(film, sc["id"]):
                continue
            sheet = await tools.sheet_of(
                [max(a - d, 0) for d in (1.2, 0.6, 0.1)], "before-" + sc["id"]
            )
            while not scenes.done(film, sc["id"]):
                res = await one(
                    "scene",
                    sc["id"],
                    scenes.scene_message(film, k, sheet),
                    [scenes.scene_file(sc)],
                    span=(a, b),
                    text="Claude is writing scene %d of %d" % (k + 1, len(rows)),
                )
                ok = os.path.exists(film.path(*scenes.scene_file(sc).split("/"))) and await parses()
                if ok:
                    try:  # its middle draws: a scene that throws is not done
                        await tools.sheet_of([(a + b) / 2], "check-" + sc["id"])
                    except ToolError:
                        ok = False
                if ok:
                    scenes.mark(film, sc["id"], state="done", summary=said(res, 600))
        # the editor: the whole film, the music and the cues
        while not scenes.done(film, scenes.EDITOR):
            sheets = []
            for i, ts in enumerate(scenes.contact_times(film)):
                sheets.append(await tools.sheet_of(ts, "contact-%d" % (i + 1)))
            res = await one(
                "editor",
                scenes.EDITOR,
                scenes.editor_message(film, sheets),
                ["scenes/*.js", "score.json", "sfx.json"],
                text="Claude is checking the whole film",
            )
            if (
                all(os.path.exists(film.path(f)) for f in ("score.json", "sfx.json"))
                and not validate.gate(film)
                and await parses()
            ):
                scenes.mark(film, scenes.EDITOR, state="done", summary=said(res))
                summary["claude_said"] = said(res, 4000)
        summary["turns"] = sum(p["turns"] or 0 for p in passes)

    state = "error"
    try:
        if not finish_only:
            async with sched["claude"].hold(1, film.id, on_wait, priority=rec.get("priority", 0)):
                clock.t0, clock.paused = time.time(), 0.0  # the queue was not Claude's time
                if resume:  # the stopped attempt's verdict goes; its start and its cost stay
                    film.update(state="claude", ok=None, error=None, finished=None)
                    await save(film.id, {"state": "running", "ok": None, "error": None})
                else:
                    film.update(
                        state="claude", started=datetime.now().isoformat(timespec="seconds")
                    )
                    await save(film.id, {"state": "running", "started_at": store.now()})
                emit(
                    {
                        "type": "stage",
                        "name": "claude",
                        "text": "Claude is picking the film up where it stopped"
                        if resume
                        else "Claude is writing and reviewing the film",
                    }
                )
                s = time.time()
                try:
                    try:
                        res = await (make_scenes() if film.mode == "scenes" else talk_to_claude())
                    except SignInError as e:
                        if auth != "login":
                            raise  # the key itself is refused: nothing to fall back to
                        # this machine's login is gone (a setup-token expired or was revoked, a
                        # logout, no CLI): the film is made on the key instead of being lost, and
                        # its record says so -- billed, and why
                        auth, billed = "api", True
                        summary.update(auth="api", fallback={"from": "login", "why": e.why})
                        film.update(auth="api", fallback=summary["fallback"])
                        await save(film.id, {"auth": "api", "fallback": summary["fallback"]})
                        emit({"type": "fallback", "from": "login", "to": "api", "why": e.why})
                        emit(
                            {
                                "type": "fail",
                                "text": "This machine's Claude login failed (%s); making the "
                                "film on the API key instead" % e.why,
                            }
                        )
                        res = await (make_scenes() if film.mode == "scenes" else talk_to_claude())
                except TimeoutError:
                    # past its time, Claude may only have been taking a last look at a film it
                    # had written: one that is whole and passes the checks is finished, not lost;
                    # one with its picture written gets one short last turn for what is missing
                    if film.mode == "scenes" or (
                        not await written(film, tools)
                        and not await wrap_up(film, emit, meter, tools, auth)
                    ):
                        raise
                    res = None
                    summary["overtime"] = True
                    emit(
                        {
                            "type": "stage",
                            "name": "claude",
                            "text": "Claude's time is up; finishing the film it wrote",
                        }
                    )
                stages["claude"] = time.time() - s
                stages["waited"] = clock.paused
            price()
            if res is not None:
                summary.update(
                    turns=res.num_turns + (summary.get("turns") or 0),
                    claude_said=res.result,
                    session=res.session_id,
                )
                if res.is_error:
                    raise RuntimeError("Claude stopped early: %s" % (res.result or res.subtype))
            await own_sound(film, tools)
            missing = [f for f in MADE if not os.path.exists(film.path(f))]
            if missing:
                raise RuntimeError("Claude finished without writing %s" % ", ".join(missing))
            if unvoiced(film):  # its lines are written but were never spoken: not a silent film
                raise RuntimeError("Claude finished without recording the narration")
            if film.record().get("template"):
                await no_leftovers(film, emit, meter, tools, auth)
            film.update(state="finishing", **summary)
            await save(film.id, {"state": "finishing"})
        pin_vo(film)  # whatever Claude left there, the backends and models stay the studio's
        pin_paint(film)
        library.drop_unused(film)  # the person's other characters stay out of this film's files
        drop_unused_uploads(film)  # then the pictures no code left in it draws
        if rec.get("branding"):
            missing = brand(film)
            if missing:
                print("film %s: no closing: %s" % (film.id, missing), file=sys.stderr, flush=True)
                summary["branding_error"] = missing
        else:
            debrand(film)

        s = time.time()
        emit({"type": "stage", "name": "sound", "text": "Mixing the soundtrack"})
        wav = film.path("audio", "final.wav")
        deps = [film.path("audio", "vo", "timeline.json"), film.manifest] + [
            film.path(f) for f in film.editable()
        ]
        if not _newer(wav, *deps):
            await tools.sound(log=True)
        stages["sound"] = time.time() - s

        s = time.time()
        emit(
            {"type": "stage", "name": "render", "text": "Rendering %d frames" % round(length * fps)}
        )
        await tools.render()
        stages["render"] = time.time() - s
        s = time.time()
        kept = await keep_cast(film, tools, emit)
        if kept is not None:
            summary["cast"] = kept
            stages["cast"] = time.time() - s
        changed = film.engine_diff()
        if media.enabled():  # online for good: plays when this machine is off (media.py)
            s = time.time()
            emit({"type": "stage", "name": "online", "text": "Making the web copy, then online"})
            summary["media"] = await media.publish(film) or None
            stages["online"] = time.time() - s
        summary.update(
            ok=True,
            video="film.mp4",
            poster="film_poster.png",
            engine_changed=changed,
            direction=film.direction(),
            seconds=took(),
            stages={k: round(v, 1) for k, v in stages.items()},
        )
        state = "done"
        emit({"type": "done", **summary})
    except asyncio.CancelledError:
        tools.kill()
        # a stopping server (server.shutdown) says so first: that is not its person pressing Stop
        stopping = control.get("shutdown")
        if (control.get("requeue") or stopping) and film.state == "queued":
            state = "queued"  # the next server makes it; nothing was spent
            film.update(server=None)  # nobody's: the leader gives it to whoever makes it next
            raise
        if stopping and film.state == "finishing":
            state = "finishing"  # Claude's part is whole: the next server mixes and renders it
            film.update(server=None)  # its steps are killed (above): the leader may take it now
            raise
        if stopping and film.mode == "scenes" and film.state == "claude":
            # its finished passes are kept (scenes.py): the next server carries it on from the
            # pass under way (server.adopt), so nothing is final here
            state = "claude"
            film.update(server=None)
            emit({"type": "fail", "text": "The studio is restarting; the film carries on after."})
            raise
        if stopping:
            state = "interrupted"
            summary.update(ok=False, error=INTERRUPTED, seconds=took())
            emit({"type": "error", "text": INTERRUPTED})
            raise
        state = "cancelled"
        summary.update(ok=False, error="cancelled", seconds=took())
        emit({"type": "error", "text": "The film was cancelled."})
        raise
    except Parked as p:
        # the person's own voice would not speak: the film waits for them, its credits held,
        # its slot free; Continue picks its session up where it stopped
        state = "waiting"
        tools.parked = None
        summary.update(waiting=p.info, seconds=took())
        emit({"type": "waiting", "reason": p.info.get("reason"), "text": waiting_words(p.info)})
    except Exception as e:  # noqa: BLE001 -- every failure goes to the page, not just the console
        text = str(e) or type(e).__name__
        if isinstance(e, TimeoutError):
            text = "Claude ran past the %d-minute limit" % (lim["claude_s"] // 60)
        summary.update(ok=False, error=text, seconds=took())
        emit({"type": "error", "text": text})
    finally:
        tools.kill()  # nothing of this film's keeps running
        if state == "waiting":  # nobody's until its person continues it (server.continue_film)
            price()
            keep = {
                k: summary[k]
                for k in (
                    "cost_usd",
                    "claude_cost_usd",
                    "tts_cost_usd",
                    "user_tts_chars",
                    "seconds",
                )
                if k in summary
            }
            film.update(state="waiting", waiting=summary["waiting"], server=None, **keep)
            # not final: kitcut.ai keeps the film's credits held while it waits (its lib/credits.js)
            await asyncio.shield(
                save(film.id, {"state": "waiting", "waiting": summary["waiting"], **keep})
            )
        elif state not in (
            "queued",
            "finishing",
            "claude",
        ):  # those two are the next server's to finish
            summary.setdefault("ok", False)
            if not summary["ok"]:
                summary.setdefault("error", "stopped before it finished")
                summary.setdefault("seconds", took())
            price()
            film.update(
                state=state, **summary, finished=datetime.now().isoformat(timespec="seconds")
            )
            final = {
                # kitcut.ai settles its credits on these names (sketch-studio lib/credits.js):
                # done is charged, the rest given back
                "state": {
                    "done": "done",
                    "cancelled": "cancelled",
                    "interrupted": "interrupted",
                }.get(state, "failed"),
                "ok": summary["ok"],
                "error": summary.get("error"),
                "calls": meter.calls(),
                "turns": summary.get("turns"),
                "seconds": summary.get("seconds"),
                "stages": {k: round(v, 1) for k, v in stages.items()} or None,
                "session_id": summary.get("session"),
                "engine_changed": summary.get("engine_changed"),
                "direction": summary.get("direction"),
                "cast": summary.get("cast"),  # what the person's library took in (library.py)
                # again here: the first record is not retried if the database was away
                "project_id": (film.record().get("project") or {}).get("id"),
                # again here, like project_id: a template's films are counted by it
                **(
                    {
                        "template": {
                            k: film.record()["template"].get(k) for k in ("id", "version", "title")
                        }
                    }
                    if film.record().get("template")
                    else {}
                ),
                "title": film.record().get("title"),  # name_film's, when nothing was typed
                "media": summary.get("media"),  # its lasting copy online (media.py)
                "overtime": summary.get("overtime", False),
                "stalls": summary.get("stalls", 0),  # replies that never came (talk_to_claude)
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
            if summary.get("fallback"):  # made on the key because the login failed
                final["fallback"] = summary["fallback"]
            if summary.get("resumed"):
                final["resumed"] = summary["resumed"]
            if prior_calls is not None:  # the stopped attempt's responses, then this one's
                final["calls"] = prior_calls + final["calls"]
            elif carry:  # the earlier detail could not be read: leave the record's as it is
                del final["calls"]
            # shielded: a cancelled film's record must still be written
            await asyncio.shield(save(film.id, final, final=True))
    return summary


def _newer(a, *bs):
    """Does file a exist and postdate every existing b?"""
    if not os.path.exists(a):
        return False
    t = os.path.getmtime(a)
    return all(not os.path.exists(b) or os.path.getmtime(b) <= t for b in bs)


def unvoiced(film):
    """Whether vo.json has lines that were never recorded (no audio/vo/timeline.json)."""
    if os.path.exists(film.path("audio", "vo", "timeline.json")):
        return False
    try:
        with open(film.path("vo.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("lines"))
    except (OSError, ValueError, AttributeError):
        return False


async def own_sound(film, tools):
    """A template's film writes its score and cues in its code, and the sound tool works them
    out. Claude can stop without calling it (a card whose picture it reviewed and never heard
    was refused for 'not writing score.json, sfx.json'): worked out here instead."""
    if not film.record().get("template") or not os.path.exists(film.path("film.js")):
        return
    with contextlib.suppress(ToolError):  # the check below names what is still missing
        async with tools.lock:
            await tools._sound_data_if_needed()


async def written(film, tools):
    """Whether the film Claude wrote is whole: every file it must make, a recorded narration,
    and files that pass the gate and the syntax check."""
    await own_sound(film, tools)
    if any(not os.path.exists(film.path(f)) for f in MADE):
        return False
    narrated = film.record().get("narration") is not False  # a template's film is music only
    if narrated and not os.path.exists(film.path("audio", "vo", "timeline.json")):
        return False
    try:
        tools.gate()
        await tools.check()
    except ToolError:
        return False
    return True


WRAP_UP_S = 240  # the last turn's working time
WRAP_UP = (
    "Time is up. Do not review or render stills again. Write whatever is still missing of "
    "film.js, score.json and sfx.json now -- keep them simple -- call check if you changed "
    "film.js, and stop with one sentence."
)


# the turn that picks up a film that waited for its person to fix their own voice
RESUME_VOICE = (
    "The person has put their ElevenLabs account right. This is the same session, and everything "
    "you made is on disk as it was: record the narration with the voice tool again (the lines "
    "already recorded are kept, and cost nothing), then carry on from where you were. You have "
    "about %d minutes left."
)


# what a film the studio stopped under it says (make_film on a shutdown; server.adopt after a crash)
INTERRUPTED = "The studio restarted before this film was finished."
# a film picked up after the studio stopped under it (make_film resume=True) gets what its own
# limit has left of Claude's working time, and at least this much. (It was capped at 20 minutes,
# right for a film missing only its music; an 8-minute film stopped before its picture was
# written -- llwtme, 2026-09-28 -- needs most of its limit.)
RESUME_MIN_S = 5 * 60
# the same, for a film stopped before its narration was recorded (2026-09-30, 52k5en: told "the
# narration is recorded", Claude did not record it and the film went out silent)
RESUME_UNVOICED = (
    "The studio stopped while you were making this film; this is the same session, picking up "
    "where it stopped. Everything you wrote is on disk as you left it, but the narration is NOT "
    "recorded yet: record it with the voice tool first, then look once at where the film stands "
    "(one set of review stills), hang the cues on the real word times, fix only what is clearly "
    "wrong, write whatever is still missing of film.js, score.json and sfx.json, call check, and "
    "stop with one sentence. You have about %d minutes."
)
RESUME = (
    "The studio restarted while you were making this film; this is the same session, picking up "
    "where it stopped. Everything you wrote is on disk as you left it and the narration is "
    "recorded -- do not record it again. Look once at where the film stands (one set of review "
    "stills), fix only what is clearly wrong, then write whatever is still missing of film.js, "
    "score.json and sfx.json, call check, and stop with one sentence. Write a long film.js in parts "
    "-- the first scenes with Write, the rest with Edit a few scenes at a time -- so that no single "
    "reply runs for many minutes. You have about %d minutes."
)


async def wrap_up(film, emit, meter, tools, auth):
    """One short last turn in the session that ran out of time, for a film whose picture is
    written: Claude writes what is missing (the music, the cues). Whether the film is whole."""
    sid = film.record().get("claude_session")
    if not sid or not os.path.exists(film.path("film.js")):
        return False
    emit({"type": "stage", "name": "claude", "text": "Claude's time is up; it is finishing up"})
    with contextlib.suppress(TimeoutError):
        await _within(
            run_claude(film, emit, meter, tools, auth, prompt=WRAP_UP, resume=sid),
            Clock(),
            {"claude_s": WRAP_UP_S, "wall_s": WRAP_UP_S + 120},
        )
    return await written(film, tools)


CLOSING_S = 3.0  # the Free plan's closing, after the film


def brand(film):
    """A Free-plan film's watermark and closing (studio/outro.js, studio/brand/), added to its
    manifest as a `tail` for the final sound and render only -- so Claude's review stills never
    show them. Copied into the film, which then renders the same way later. Idempotent.
    Returns why it could not (a file of the studio's missing), and then the film goes out
    without them rather than not at all."""
    d = film.path("temp", "brand")
    os.makedirs(d, exist_ok=True)
    try:
        for src in (
            os.path.join(HERE, "outro.js"),
            *(os.path.join(HERE, "brand", n) for n in ("kitcut.png", "closing.wav")),
        ):
            shutil.copyfile(src, os.path.join(d, os.path.basename(src)))
    except OSError as e:
        return str(e)
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m["tail"] = {
        "secs": CLOSING_S,
        "scripts": ["temp/brand/outro.js"],
        "images": {"kitcut": "temp/brand/kitcut.png"},
        "audio": "temp/brand/closing.wav",
    }
    films._write_json(film.manifest, m)
    return None


def debrand(film):
    """The other way: a film whose record says it carries no branding is finished without a
    `tail`, at its record's frame rate. One that lost its branding after it was made (unbrand.py
    swaps in a second render and leaves the manifest as it was, so what is keyed on the manifest
    stays valid) would otherwise get the closing back the next time it is finished by hand.
    Writes nothing when there is nothing to change."""
    try:
        with open(film.manifest, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return
    fps = film.record().get("fps")
    if "tail" not in m and (fps not in (30, 60) or m.get("fps", 60) == fps):
        return
    m.pop("tail", None)
    if fps in (30, 60):
        m["fps"] = fps
    films._write_json(film.manifest, m)


async def keep_cast(film, tools, emit):
    """After a finished film, the person's library takes in what it made (library.keep): its new
    and changed cast members, each drawn alone for a thumbnail. None when the film's client has
    no library. Never fails the film: what went wrong goes to stderr and the record."""
    if not library.lib_of(film.record()):
        return None
    try:
        items = library.changes(film)
        pictures = {}
        if items:
            names = [it["name"] for it in items]
            emit({"type": "stage", "name": "cast", "text": "Keeping the cast for the next films"})
            man, times = library.sheet(film, names)
            try:
                await tools.cast_sheet(man, times)
                pictures = await asyncio.to_thread(library.thumbs, film, names)
            except ToolError as e:  # kept all the same, without a picture
                print("film %s: no cast pictures: %s" % (film.id, e), file=sys.stderr, flush=True)
        kept = await asyncio.to_thread(library.keep, film, items, pictures)
        if kept and kept.get(
            "clashed"
        ):  # its copy stays in its own cast/; the library's newer one leads
            print(
                "film %s: cast not saved over a newer version: %s"
                % (film.id, ", ".join(kept["clashed"])),
                file=sys.stderr,
                flush=True,
            )
        return kept
    except Exception as e:  # noqa: BLE001 -- the film is made; its cast is a bonus
        print("film %s: cast not kept: %s" % (film.id, e), file=sys.stderr, flush=True)
        return {"error": (str(e) or type(e).__name__)[:200]}


def first_record(film, source, client):
    """The run's record as it is when the film is asked for (state queued), so it counts toward
    the day's limits from the first moment."""
    rec = film.record()
    return {
        "kind": "film",
        "source": source,
        "client": client,
        **({"member": rec["member"]} if rec.get("member") else {}),
        "host": store.HOST,
        "prompt": rec.get("prompt"),
        "model": MODEL,
        "effort": EFFORT,
        "job": film.id,
        "length": rec.get("length"),
        "look": rec.get("look"),
        "release": RELEASE,
        "priority": rec.get("priority", 0),
        "auth": rec.get("auth", "api"),
        "branding": bool(rec.get("branding")),
        "listed": rec.get("listed") is not False,  # false: link-only (no gallery, no sitemap)
        **({"app": rec["app"]} if rec.get("app") else {}),
        # people drawn as talking characters: how many and the style (never their photos)
        **(
            {"people": len(rec["people"]), "character_style": rec.get("character_style")}
            if rec.get("people")
            else {}
        ),
        # what came with the idea: kinds and sizes only (the words and pictures stay here)
        "attachments": [
            {k: a.get(k) for k in ("kind", "secs", "w", "h", "chars") if a.get(k) is not None}
            for a in rec.get("attachments") or []
        ],
        # what the film got from its library (library.seed): counts only
        "library": {k: len(v or []) for k, v in rec["library"].items()}
        if rec.get("library")
        else None,
        # the site's project it is an episode of: the id only (the name and brief are the site's)
        "project_id": (rec.get("project") or {}).get("id"),
        # the template it was remade from (templates.py): kitcut.ai counts a template's films by it
        **(
            {
                "template": {k: rec["template"].get(k) for k in ("id", "version", "title")},
                "frame": rec.get("frame"),
            }
            if rec.get("template")
            else {}
        ),
        "state": "queued",
        "cost_usd": 0.0,
    }


# ------------------------------------------------------------------ command line
async def smoke(auth="api"):
    """One turn, no tools: proves the key (or the login), the model and where the bill goes.
    Returns (ok, why): why is the failure in words, None when it worked. A failed sign-in does
    not raise (see SignInError): it is a reply marked is_error."""
    try:
        cli = claude_cli() if auth == "login" else None
    except RuntimeError as e:
        print("  FAILED:     %s" % e)
        return False, str(e)
    opts = ClaudeAgentOptions(
        model=MODEL,
        effort=EFFORT,
        cwd=HOME if os.path.isdir(HOME) else KIT,
        system_prompt="Reply with exactly: OK",
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=claude_env(None, auth),
        cli_path=cli,
        include_partial_messages=True,
    )
    t, meter, streamed = time.time(), Meter(), {}
    ok, why = False, "no reply from Claude"
    try:
        async for m in query(prompt="ping", options=opts):
            if isinstance(m, StreamEvent):
                meter.stream(m.event, streamed)
            elif isinstance(m, SystemMessage) and m.subtype == "init":
                print("  key source: %s" % m.data.get("apiKeySource"))
                print("  model:      %s" % m.data.get("model"))
                print("  mcp:        %s" % ([s.get("name") for s in m.data.get("mcp_servers", [])]))
            elif isinstance(m, AssistantMessage):
                meter.add(m.message_id or m.uuid, m.usage, m.model)
            elif isinstance(m, ResultMessage):
                ok, why = not m.is_error, (m.result or m.subtype) if m.is_error else None
                print("  reply:      %r%s" % (m.result, "  (ERROR)" if m.is_error else ""))
                print("  cost:       $%.4f in %.1fs" % (m.total_cost_usd or 0, time.time() - t))
                print("  metered:    $%.4f  %s" % (meter.usd(), meter.tokens()))
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
    except CLINotFoundError as e:
        ok, why = False, str(e)
    if not ok:
        print("  FAILED:     %s" % why)
    return ok, why


def check_login():
    """The daily check (studio/deploy/kitcut-login-check.timer): one turn on this machine's
    Claude login. Its result goes where the site and the owner can see it -- kitcut.studio_hosts
    ("login": ok, why, when) and the journal -- and a failure exits 1, so the unit shows failed.
    A film asked for in the meantime still gets made: it falls back to the key (make_film)."""
    ok, why = asyncio.run(smoke("login"))
    try:
        STORE.note_login(ok, why)
    except Exception as e:  # noqa: BLE001 -- the check's own result still stands
        print("  could not record the check in MongoDB: %s" % e)
    if not ok:
        print(
            "LOGIN CHECK FAILED on %s: %s -- films asked for on this machine fall back to the API "
            "key until it is renewed (`claude setup-token`; studio/deploy/README.md)"
            % (store.HOST, why)
        )
    return ok


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


PICTURE_EXT = ("png", "jpg", "jpeg", "webp", "gif")
DOC_EXT = ("md", "txt")


def local_attachment(path):
    """A file on this machine as an upload a film takes (uploads.take's meta, "src" its file): a
    picture or a short document."""
    if not os.path.isfile(path):
        sys.exit("no such file: %s" % path)
    ext = path.rsplit(".", 1)[-1].lower()
    meta = {"id": "up-local-" + os.path.basename(path), "src": path, "ext": ext}
    if ext in PICTURE_EXT:
        return meta | {"kind": "image"}
    if ext in DOC_EXT:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return meta | {
            "kind": "text",
            "name": os.path.basename(path),
            "chars": len(text),
            "words": len(text.split()),
        }
    sys.exit(
        "attach a picture (%s) or a document (%s)" % (", ".join(PICTURE_EXT), ", ".join(DOC_EXT))
    )


def template_film(
    template,
    prompt,
    attach=(),
    frame=None,
    listed=True,
    client="local",
    source="cli",
    auth="login",
):
    """A film remade from a template on this machine: template "t-<slug>[:version]" (a draft
    may be tried), what the person wants in their own words, and files that stand in for their
    uploads. Returns the film, seeded and ready for make_film."""
    tid, _, v = template.partition(":")
    t = templates.load(tid, int(v) if v else None, ("live", "draft"))
    if not t:
        sys.exit("no template %s" % template)
    film = Film.create(
        prompt or "",
        client=client,
        source=source,
        auth=auth,
        attachments=[local_attachment(p) for p in attach],
        template=t,
        frame=frame or t["frames"][0],
        listed=listed,
    )
    templates.seed(film, t)
    return film


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
        default="login",  # this machine's own runs; the public site's films are on the key
        choices=("api", "login"),
        help="api: ANTHROPIC_API_KEY (billed per token); login: this machine's Claude Code login",
    )
    ap.add_argument("--smoke", action="store_true", help="a one-turn check, no film")
    ap.add_argument("--template", help="remake this template (templates.py): t-<slug>[:version]")
    ap.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FILE",
        help="a picture or a short document the person attached (repeatable)",
    )
    ap.add_argument("--frame", help="with --template: one of its frames (16:9, 1:1...)")
    ap.add_argument(
        "--unlisted", action="store_true", help="keep the film out of every gallery (link-only)"
    )
    ap.add_argument(
        "--check-login",
        action="store_true",
        help="the daily check: a one-turn check on this machine's Claude login, recorded in "
        "kitcut.studio_hosts; exits 1 when it fails",
    )
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
        # only the production studio may say where the studio is: a dev server started with the
        # same scripts on another machine would otherwise point kitcut.ai at itself (or at nothing)
        if os.environ.get("STUDIO_ANNOUNCE") != "1":
            print("not announcing %s: STUDIO_ANNOUNCE=1 is set only on the production studio" % url)
            return
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
    if args.check_login:
        sys.exit(0 if check_login() else 1)
    if args.smoke:
        ok, _ = asyncio.run(smoke(args.auth))
        sys.exit(0 if ok else 1)
    if args.template:
        if not args.prompt and not args.attach:
            ap.error("say what you want made of the template, or attach something")
        film = template_film(
            args.template, args.prompt, args.attach, args.frame, not args.unlisted, auth=args.auth
        )
    else:
        if not args.prompt:
            ap.error("give a prompt, or --smoke")
        film = Film.create(
            args.prompt,
            args.seconds,
            args.look,
            client="local",
            source="cli",
            listed=not args.unlisted,
        )
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
