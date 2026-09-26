"""What Claude writes, checked before anything runs on it.

Claude's files feed the pipeline scripts, and some of what is in them becomes a file path (a
painting's name, an instrument), a download (an instrument's samples) or a loop count (a sound's
length). The scripts refuse unsafe names themselves (_sketch.safe_name, _sketchaudio.GM); this is
the friendlier, earlier check, and the caps on how much work one film may ask for:

    problems(film, "vo.json")   what is wrong with one file, as sentences Claude can act on
    gate(film)                  every file at once: the tools refuse to run while this is non-empty

It runs after every Write or Edit (Claude hears about it at once), before every studio tool, and
once more before the final render, since Claude can edit a file after its last tool call.
"""

import os
import re
import sys
import json
from importlib import import_module

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import _sketch  # noqa: E402
import _sketchaudio as A  # noqa: E402

from film import ENGINE, PAINT_PINNED, VO_PINNED, limits  # noqa: E402

VOICES = tuple(import_module("sketch-vo").GEMINI_VOICES)
MAX_JS = 256 * 1024  # film.js: the prompt asks for ~200 lines
MAX_ENGINE_JS = 400 * 1024  # engine.js + props.js are ~85 KB together
MAX_JSON = 64 * 1024
VO_KEYS = set(VO_PINNED) | {"model", "voice", "style", "language", "lines"}
VO_LINE_KEYS = {"text", "start"}
MAX_LINE_CHARS = 300  # and at most film.limits()["lines"] lines
PAINT_KEYS = set(PAINT_PINNED) | {"style", "images"}
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def _load(film, name):
    p = film.path(name)
    if not os.path.exists(p):
        return None, []
    if os.path.getsize(p) > MAX_JSON:
        return None, [
            "%s is %d KB; keep it under %d KB"
            % (name, os.path.getsize(p) // 1024, MAX_JSON // 1024)
        ]
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f), []
    except ValueError as e:
        return None, ["%s is not valid JSON (%s)" % (name, e)]


def _num(x, lo, hi):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and lo <= x <= hi


def _vo(d, max_lines):
    out = []
    if not isinstance(d, dict):
        return ["vo.json must be an object"]
    extra = sorted(set(d) - VO_KEYS)
    if extra:
        out.append("vo.json: %s not yours to set (the studio removes them)" % ", ".join(extra))
    if d.get("voice") not in VOICES:
        out.append("vo.json: voice must be one of %s" % ", ".join(VOICES))
    if not isinstance(d.get("language", "en"), str) or not LANG.match(d.get("language", "en")):
        out.append('vo.json: language is an ISO 639-1 code such as "en" or "uk"')
    if not isinstance(d.get("style", ""), str) or len(d.get("style", "")) > 300:
        out.append("vo.json: style is one line of text (at most 300 characters)")
    lines = d.get("lines", [])
    if not isinstance(lines, list) or len(lines) > max_lines:
        out.append("vo.json: lines is a list of at most %d" % max_lines)
        return out
    for i, ln in enumerate(lines):
        if (
            not isinstance(ln, dict)
            or not isinstance(ln.get("text"), str)
            or not ln["text"].strip()
        ):
            out.append('vo.json: line %d must be {"text": "..."}' % i)
            continue
        if len(ln["text"]) > MAX_LINE_CHARS:
            out.append("vo.json: line %d is over %d characters" % (i, MAX_LINE_CHARS))
        if set(ln) - VO_LINE_KEYS:
            out.append("vo.json: line %d may only have text (and start)" % i)
        if "start" in ln and not _num(ln["start"], 0, 60):
            out.append("vo.json: line %d start is seconds, 0-60" % i)
    return out


def _paint(d):
    out = []
    if not isinstance(d, dict):
        return ["paint.json must be an object"]
    extra = sorted(set(d) - PAINT_KEYS)
    if extra:
        out.append("paint.json: %s not yours to set" % ", ".join(extra))
    if not isinstance(d.get("style", ""), str) or len(d.get("style", "")) > 400:
        out.append("paint.json: style is one line of text (at most 400 characters)")
    ims = d.get("images", [])
    cap = PAINT_PINNED["max_images"]
    if not isinstance(ims, list) or len(ims) > cap:
        return out + ["paint.json: images is a list of at most %d" % cap]
    names = [im.get("name") for im in ims if isinstance(im, dict)]
    for i, im in enumerate(ims):
        if not isinstance(im, dict):
            out.append("paint.json: image %d must be an object" % i)
            continue
        try:
            _sketch.safe_name(im.get("name"), "paint.json: image %d name" % i)
        except ValueError as e:
            out.append(str(e))
        if not isinstance(im.get("prompt"), str) or not 0 < len(im["prompt"]) <= 2000:
            out.append("paint.json: image %d needs a prompt (at most 2000 characters)" % i)
        if "ref" in im and (im["ref"] not in names or im["ref"] == im.get("name")):
            out.append("paint.json: image %d ref must name another image" % i)
        if set(im) - {"name", "prompt", "ref"}:
            out.append("paint.json: image %d may only have name, prompt and ref" % i)
    if len(set(names)) != len(names):
        out.append("paint.json: image names must be unique")
    return out


def _inst(where, inst, out):
    if inst not in A.GM:
        out.append(
            "%s: instrument %r is not a General MIDI name (e.g. celesta, marimba, "
            "string_ensemble_1)" % (where, inst)
        )


def _score(d):
    out = []
    if not isinstance(d, dict) or not isinstance(d.get("events", []), list):
        return ['score.json must be {"bpm": ..., "events": [...]}']
    if "bpm" in d and not _num(d["bpm"], 40, 240):
        out.append("score.json: bpm must be 40-240")
    if len(d.get("events", [])) > 300:
        out.append("score.json: at most 300 events")
    for i, e in enumerate(d.get("events", [])):
        if not isinstance(e, dict):
            out.append("score.json: event %d must be an object" % i)
            continue
        if "inst" in e:
            _inst("score.json event %d" % i, e["inst"], out)
        if e.get("type") == "roll" and not _num(e.get("step", 0.125), 1 / 32, 4):
            out.append("score.json event %d: roll step must be 1/32-4 beats" % i)
        if e.get("type") == "drums" and not _num(e.get("bars", 1), 0, 64):
            out.append("score.json event %d: drums bars at most 64" % i)
    return out


def _sfx(d, length):
    out = []
    if not isinstance(d, list):
        return ["sfx.json must be a list of cues"]
    if len(d) > 200:
        out.append("sfx.json: at most 200 cues")
    for i, c in enumerate(d):
        if not isinstance(c, dict):
            out.append("sfx.json: cue %d must be an object" % i)
            continue
        if c.get("fx") not in A.FX and c.get("fx") not in ("sample", "air"):
            out.append("sfx.json cue %d: fx must be one of %s" % (i, ", ".join(sorted(A.FX))))
        times = c.get("times") or [c.get("t", 0)]
        if not isinstance(times, list) or len(times) > 64:
            out.append("sfx.json cue %d: times is a list of at most 64" % i)
        elif not all(_num(t, -1, length + 5) for t in times):
            out.append("sfx.json cue %d: times are seconds within the film" % i)
        args = c.get("args", {})
        if not isinstance(args, dict) or not _num(args.get("sec", 1), 0, 15):
            out.append("sfx.json cue %d: args.sec is at most 15 seconds" % i)
        if c.get("fx") == "sample":
            _inst("sfx.json cue %d" % i, c.get("inst"), out)
            if len(c.get("notes") or []) > 32 or not _num(c.get("sec", 1.5), 0, 15):
                out.append("sfx.json cue %d: at most 32 notes of at most 15 seconds" % i)
    return out


def problems(film, name):
    """What is wrong with one of Claude's files ([] when nothing, or when it is not there yet)."""
    if name in ENGINE or name.startswith("engine"):
        p = film.path("engine", os.path.basename(name))
        if os.path.exists(p) and os.path.getsize(p) > MAX_ENGINE_JS:
            return ["%s is over %d KB" % (name, MAX_ENGINE_JS // 1024)]
        return []
    if name == "film.js":
        p = film.path("film.js")
        if os.path.exists(p) and os.path.getsize(p) > MAX_JS:
            return ["film.js is over %d KB; keep it short" % (MAX_JS // 1024)]
        return []
    d, out = _load(film, name)
    if d is None:
        return out
    if name == "vo.json":
        return _vo(d, limits(film.length)["lines"])
    if name == "paint.json":
        return _paint(d)
    if name == "score.json":
        return _score(d)
    if name == "sfx.json":
        return _sfx(d, film.length)
    return []


def gate(film):
    """Everything wrong in all of Claude's files."""
    out = []
    for name in film.editable() + tuple("engine/" + n for n in ENGINE):
        out += problems(film, name)
    return out
