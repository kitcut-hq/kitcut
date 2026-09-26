"""Sketch Studio's permission model: what Claude may do in its film's sandbox.

Claude has three built-in tools (Read, Write, Edit) and the studio's own (mcp__studio__*: check,
voice, paint, stills, sound), which run the pipeline for it. There is no shell. guard() is the
PreToolUse hook's answer for every call:

    Read          a file inside the film's folder (film.readable: never temp/, studio.json)
    Write, Edit   film.js, score.json, sfx.json, vo.json, paint.json (painted films) and the
                  film's engine copy, engine/engine.js and engine/props.js (film.writable)
    mcp__studio__ the studio's tools; they check their own arguments
    anything else refused, with a reason Claude can act on

Paths are resolved against the film's folder (Claude's working directory) and then to their real
path, so neither ../ nor a link reaches another film. After a write, pin_after() puts back what
the studio decides in vo.json and paint.json and says what else is wrong (validate.problems).
"""

import os
import re
import json

import validate
from film import PAINT_PINNED, VO_PINNED, tts_model

STUDIO_TOOLS = "mcp__studio__"


def _path(p, film):
    """A tool's path argument, absolute: relative to the film's folder, posix or git-bash
    (/c/...) spellings too."""
    p = str(p or "").strip().strip("\"'")
    m = re.match(r"^/([a-zA-Z])/(.*)$", p) if os.name == "nt" else None
    if m:
        p = m.group(1) + ":/" + m.group(2)
    return os.path.abspath(os.path.join(film.dir, p))


def guard(tool, inp, film):
    """(allowed, reason) for one tool call by Claude working on `film`."""
    if tool == "Read":
        if film.readable(_path(inp.get("file_path"), film)):
            return True, ""
        return False, "Read is limited to your film's folder (your working directory)."
    if tool in ("Write", "Edit"):
        if film.writable(_path(inp.get("file_path"), film)):
            return True, ""
        mine = ", ".join(film.editable() + ("engine/engine.js", "engine/props.js"))
        return False, "You can only write %s, in your working directory." % mine
    if tool.startswith(STUDIO_TOOLS):
        return True, ""
    return False, (
        "%s is not available here: use Read, Write, Edit and the studio tools "
        "(check, voice, paint, stills, sound)." % tool
    )


def _pin(film, name, want, keep=None):
    """Put back what Claude may not change in one of its files, and (keep) drop keys that are
    not Claude's to set. Returns what it had to restore, or "" -- the PostToolUse hook tells
    Claude so."""
    p = film.path(name)
    if not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        return "%s is not valid JSON (%s); fix it" % (name, e)
    if not isinstance(d, dict):
        return ""
    wrong = {k for k, v in want.items() if d.get(k) != v}
    extra = set(d) - set(keep) if keep else set()
    if not wrong and not extra:
        return ""
    d = {k: v for k, v in d.items() if k not in extra} | want
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    said = []
    if wrong:
        said.append(
            "the studio sets %s in %s; restored %s"
            % (
                ", ".join(sorted(want)),
                name,
                ", ".join("%s=%r" % (k, want[k]) for k in sorted(wrong)),
            )
        )
    if extra:
        said.append("removed %s from %s (not yours to set)" % (", ".join(sorted(extra)), name))
    return "; ".join(said)


def pin_vo(film):
    """vo.json: the voice backend, model and takes are the studio's, and so is everything that
    is not the narration (a Whisper model, hotwords...)."""
    return _pin(film, "vo.json", {**VO_PINNED, "model": tts_model()}, keep=validate.VO_KEYS)


def pin_paint(film):
    """paint.json: the painter, its model and the cap on paintings are the studio's."""
    return _pin(film, "paint.json", PAINT_PINNED, keep=validate.PAINT_KEYS)


def pin_after(file_path, film):
    """After a write: pin the file if the studio has a say in it, then check it. Returns a note
    for Claude, or ""."""
    name = os.path.relpath(_path(file_path, film), film.dir).replace("\\", "/")
    notes = []
    if name == "vo.json":
        notes.append(pin_vo(film))
    elif name == "paint.json":
        notes.append(pin_paint(film))
    notes += validate.problems(film, name)
    return "; ".join(n for n in notes if n)
