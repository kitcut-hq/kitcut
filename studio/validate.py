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

from film import PAINT_PINNED, VO_PINNED, limits, paint_kinds  # noqa: E402

VOICES = tuple(import_module("sketch-vo").GEMINI_VOICES)
MAX_JS = 256 * 1024  # film.js: the prompt asks for ~200 lines
MAX_CONTENT_JSON = 256 * 1024  # a template film's content.json
MAX_ENGINE_JS = 400 * 1024  # each engine file: engine.js + props.js are ~105 KB together
MAX_CAST_JS = 64 * 1024  # one cast member (library.MAX_BYTES)
MAX_JSON = 64 * 1024
MAX_SCENE_JS = 64 * 1024  # one scene of a film made in scenes: 12-75 s, not a whole film
# "jobs": pinned for a person's own ElevenLabs voice (film._own_pins); every key a pin set
# writes must be here, or the guard puts it back and this refuses it on every check
VO_KEYS = set(VO_PINNED) | {"model", "voice", "style", "language", "lines", "cast", "jobs"}
# "who": the person (film.CAPS "people") who speaks a line; "cast" gives each their voice
VO_LINE_KEYS = {"text", "start", "who"}
MAX_LINE_CHARS = 300  # and at most film.limits()["lines"] lines
PAINT_KEYS = set(PAINT_PINNED) | {"style", "images", "cutouts"}
# a cut-out (film.CAPS "cutouts") is painted on a canvas of its own shape
ASPECTS = ("1:1", "2:3", "3:2", "3:4", "4:3", "16:9", "9:16")
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


def _vo(d, max_lines, length=60, people=()):
    """people: the ids of the film's people (p1...), who may speak lines of their own."""
    out = []
    if not isinstance(d, dict):
        return ["vo.json must be an object"]
    extra = sorted(set(d) - VO_KEYS)
    if extra:
        out.append("vo.json: %s not yours to set (the studio removes them)" % ", ".join(extra))
    if d.get("tts") == "elevenlabs":
        pass  # the person's own voice, pinned by the studio (film.vo_pins): not Claude's
    elif d.get("voice") not in VOICES:
        out.append("vo.json: voice must be one of %s" % ", ".join(VOICES))
    if not isinstance(d.get("language", "en"), str) or not LANG.match(d.get("language", "en")):
        out.append('vo.json: language is an ISO 639-1 code such as "en" or "uk"')
    if not isinstance(d.get("style", ""), str) or len(d.get("style", "")) > 300:
        out.append("vo.json: style is one line of text (at most 300 characters)")
    cast = d.get("cast", {})
    if not isinstance(cast, dict):
        out.append('vo.json: cast is {"p1": {"voice": "..."}, ...}')
        cast = {}
    # a person's own ElevenLabs voice is theirs: never put in someone else's mouth, and its film's
    # grant speaks in that one voice -- so its people are seen, not heard
    own = d.get("tts") == "elevenlabs"
    if own and (cast or any(isinstance(ln, dict) and "who" in ln for ln in d.get("lines") or [])):
        out.append(
            "vo.json: this film is narrated in the person's own voice, which speaks for nobody "
            "else: remove cast and every line's who (the people are seen, not heard)"
        )
        cast = {}
    for who, spec in cast.items():
        if who not in people:
            out.append(
                "vo.json: cast %s is not one of this film's people (%s)"
                % (who, ", ".join(people) or "it has none")
            )
        elif (
            not isinstance(spec, dict)
            or spec.get("voice") not in VOICES
            or set(spec)
            - {
                "voice",
                "style",
            }
        ):
            out.append('vo.json: cast %s is {"voice": one of the voices, "style": "..."}' % who)
        elif not isinstance(spec.get("style", ""), str) or len(spec.get("style", "")) > 300:
            out.append("vo.json: cast %s style is one line of text" % who)
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
            out.append("vo.json: line %d may only have text (and start, who)" % i)
        if "who" in ln and not own and (ln["who"] not in people or ln["who"] not in cast):
            out.append(
                "vo.json: line %d who %r must be one of this film's people with a voice in cast"
                % (i, ln["who"])
            )
        if "start" in ln and not _num(ln["start"], 0, length):
            out.append("vo.json: line %d start is seconds, 0-%d" % (i, length))
    return out


def _paint(d, length, caps):
    out = []
    if not isinstance(d, dict):
        return ["paint.json must be an object"]
    extra = sorted(set(d) - PAINT_KEYS)
    if extra:
        out.append("paint.json: %s not yours to set" % ", ".join(extra))
    if not isinstance(d.get("style", ""), str) or len(d.get("style", "")) > 400:
        out.append("paint.json: style is one line of text (at most 400 characters)")
    ims = d.get("images", [])
    kinds = paint_kinds(caps)  # what this film's capabilities paint (film.CAPS)
    cap = sum(limits(length)[kind["cap"]] for kind in kinds)
    keys = {"name", "prompt", "ref"} | {k for kind in kinds for k in kind["keys"]}
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
        if set(im) - keys:
            out.append("paint.json: image %d may only have %s" % (i, ", ".join(sorted(keys))))
        c = im.get("cutout", False)
        if not (isinstance(c, bool) or (isinstance(c, dict) and _cut_ok(c))):
            out.append(
                'paint.json: image %d cutout is true, or {"border": 0-40, "cut": "scissor"|"round"}'
                % i
            )
        if "aspect" in im and im["aspect"] not in ASPECTS:
            out.append("paint.json: image %d aspect is one of %s" % (i, ", ".join(ASPECTS)))
    if len(set(names)) != len(names):
        out.append("paint.json: image names must be unique")
    return out


def _cut_ok(c):
    b = c.get("border", 12)
    return (
        not set(c) - {"border", "cut"}
        and isinstance(b, int)
        and 0 <= b <= 40
        and c.get("cut", "scissor") in ("scissor", "round")
    )


def _inst(where, inst, out):
    if inst not in A.GM:
        out.append(
            "%s: instrument %r is not a General MIDI name (e.g. celesta, marimba, "
            "string_ensemble_1)" % (where, inst)
        )


def _score(d, length=60):
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
        bars = limits(length)["drum_bars"]
        if e.get("type") == "drums" and not _num(e.get("bars", 1), 0, bars):
            out.append("score.json event %d: drums bars at most %d" % (i, bars))
        # a piece the kit has no sound for fails only when the soundtrack renders (a collage
        # film asked for a 'crash' on 2026-09-28): name it here, with the ones there are
        kit = e.get("kit") if e.get("type") == "drums" else None
        if isinstance(kit, dict) and set(kit) - set(A.DRUM_PAN):
            out.append(
                "score.json event %d: drums has no %s; the kit is %s"
                % (i, ", ".join(sorted(set(kit) - set(A.DRUM_PAN))), ", ".join(A.DRUM_PAN))
            )
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
    if name.startswith("engine"):
        p = film.path("engine", os.path.basename(name))
        if os.path.exists(p) and os.path.getsize(p) > MAX_ENGINE_JS:
            return ["%s is over %d KB" % (name, MAX_ENGINE_JS // 1024)]
        return []
    if name == "film.js":
        p = film.path("film.js")
        if os.path.exists(p) and os.path.getsize(p) > MAX_JS:
            return ["film.js is over %d KB; keep it short" % (MAX_JS // 1024)]
        return []
    if name.startswith("scenes/"):  # a scene of a film made in scenes (studio/scenes.py)
        p = film.path(*name.split("/"))
        if os.path.exists(p) and os.path.getsize(p) > MAX_SCENE_JS:
            return [
                "%s is over %d KB: a scene is 12-75 s, keep it lean" % (name, MAX_SCENE_JS // 1024)
            ]
        return []
    if name.startswith("cast/"):  # a cast member (library.py): kept only while it is small
        p = film.path(*name.split("/"))
        if os.path.exists(p) and os.path.getsize(p) > MAX_CAST_JS:
            return ["%s is over %d KB, too big to keep" % (name, MAX_CAST_JS // 1024)]
        return []
    if name == "content.json":  # a template film's words and people (templates.py)
        p = film.path("content.json")
        if os.path.exists(p) and os.path.getsize(p) > MAX_CONTENT_JSON:
            return ["content.json is over %d KB" % (MAX_CONTENT_JSON // 1024)]
    d, out = _load(film, name)
    if d is None:
        return out
    if name == "content.json":
        return [] if isinstance(d, dict) else ["content.json must be one JSON object"]
    if name == "vo.json":
        people = [p["id"] for p in film.record().get("people") or []]
        return _vo(d, limits(film.length)["lines"], film.length, people)
    if name == "paint.json":
        return _paint(d, film.length, film.caps)
    if name == "score.json":
        return _score(d, film.length)
    if name == "sfx.json":
        return _sfx(d, film.length)
    if name == "scenes.json":
        return _scenes(d, film)
    return []


# a film made in scenes (studio/scenes.py): its plan, scenes.json
SCENE_ID = re.compile(r"^[0-9]{2}-[a-z0-9-]{1,40}$")
SCENE_MIN_S, SCENE_MAX_S = 12, 75  # a scene's length once the narration is timed


def _timed(film):
    """The narration's timed lines (audio/vo/timeline.json), or [] before it is recorded."""
    try:
        with open(film.path("audio", "vo", "timeline.json"), encoding="utf-8") as f:
            return json.load(f).get("lines", [])
    except (OSError, ValueError, AttributeError):
        return []


def _scenes(d, film):
    """scenes.json: the scenes in order, each a stretch of narration lines [first, last] -- no
    gaps, no overlaps, every line covered -- and, once the narration is timed, 12-75 s long."""
    sc = d.get("scenes") if isinstance(d, dict) else None
    if not isinstance(sc, list) or not sc:
        return [
            'scenes.json needs "scenes": a list of {"id", "title", "lines": [first, last], "shows"}'
        ]
    try:
        with open(film.path("vo.json"), encoding="utf-8") as f:
            n = len(json.load(f).get("lines", []))
    except (OSError, ValueError, AttributeError):
        n = 0
    out, ids, want = [], set(), 0
    for i, s in enumerate(sc):
        where = "scene %d" % (i + 1)
        if not isinstance(s, dict):
            out.append(where + " is not an object")
            continue
        sid = s.get("id")
        if not isinstance(sid, str) or not SCENE_ID.match(sid):
            out.append('%s: id %r -- use "NN-slug" (01-orbit, 02-first-failure)' % (where, sid))
        elif sid in ids:
            out.append("%s: id %s is used twice" % (where, sid))
        elif not sid.startswith("%02d-" % (i + 1)):
            out.append(
                "%s: its id must start %02d- (the scenes are numbered in order)" % (where, i + 1)
            )
        ids.add(sid)
        ln = s.get("lines")
        if not (
            isinstance(ln, list)
            and len(ln) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in ln)
            and 0 <= ln[0] <= ln[1]
        ):
            out.append("%s: lines must be [first, last], line indexes in vo.json" % where)
        else:
            if ln[0] != want:
                out.append(
                    "%s starts at line %d, but the scene before it ended at line %d: start at %d "
                    "(no gaps, no overlaps)" % (where, ln[0], want - 1, want)
                )
            want = ln[1] + 1
        if not str(s.get("shows") or "").strip():
            out.append("%s: say what it shows (shows)" % where)
    if out:
        return out
    if n and want != n:
        return [
            "the scenes cover lines 0-%d, but the narration has %d lines (0-%d)"
            % (want - 1, n, n - 1)
        ]
    if len(sc) > max(1, film.length // SCENE_MIN_S):
        out.append(
            "%d scenes is too many for %d s: at most one per %d s"
            % (len(sc), film.length, SCENE_MIN_S)
        )
    tl = _timed(film)
    if len(tl) == n and n:
        starts = [0.0] + [max(0.0, tl[s["lines"][0]]["start"] - 0.3) for s in sc[1:]]
        for i, s in enumerate(sc):
            dur = (starts[i + 1] if i + 1 < len(sc) else film.length) - starts[i]
            if dur < SCENE_MIN_S and len(sc) > 1:
                out.append(
                    "%s runs %.1f s: at least %d s -- join it to a neighbour"
                    % (s["id"], dur, SCENE_MIN_S)
                )
            elif dur > SCENE_MAX_S:
                out.append("%s runs %.1f s: at most %d s -- split it" % (s["id"], dur, SCENE_MAX_S))
    return out


def gate(film):
    """Everything wrong in all of Claude's files."""
    out = []
    names = film.editable() + tuple("engine/" + n for n in film.engine_files())
    if os.path.isdir(film.path("scenes")):
        names += tuple("scenes/" + n for n in sorted(os.listdir(film.path("scenes"))))
    for name in names:
        out += problems(film, name)
    return out
