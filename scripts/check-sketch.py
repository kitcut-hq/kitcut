#!/usr/bin/env python
"""Self-test for the sketch-film scripts: no API, no browser, no encode, seconds.

Exercises the pieces a paid or slow run would otherwise be the first to reach: the score
notation and every event type, every SFX and drum generator, the speech ducker, the
tail-word cut that fixes eleven_v3's clipped endings, word timings with [audio tags],
caption chunking, the cut-outs a collage is built from (specks, trim, paper border, the key off
a white ground, and cache keys that stay put for scenes), the page bundler against the
committed example films, and -- under Node, skipped without it -- the jelly module's bake
(determinism, volume, inversion, the floor, settling, landing detection) and its live mode
(the per-draw step budget, the pointer hand), and the drink module's (the pour's volume, the
level, flotation, the glass wall, the straw's rest, the surface settling, the sound's events).

After touching _sketch.py, _sketchaudio.py, sketch-vo.py, sketch-audio.py, sketch-render.py or
anything under sketch/, run it.

Invoke as:  python scripts/check-sketch.py
"""

import sys
import os
import re
import json
import shutil
import argparse
import subprocess
import tempfile
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

import _sketch  # noqa: E402
import _sketchaudio as A  # noqa: E402

SR = _sketch.SR
FAILS = []


def check(name, ok, detail=""):
    print(
        "%s  %s%s"
        % ("ok  " if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else "")
    )
    if not ok:
        FAILS.append(name)


def cyrillic():
    """Cyrillic in collage films: every face collage.js stands in for (SK.NO_CYRILLIC) lacks the
    Ukrainian letters, and every stand-in has all of them (fonts/SOURCES.md)."""
    uk = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
    uk += uk.lower() + "\u2019"
    cover = {}  # family -> does every face of it draw every letter
    for n in os.listdir(os.path.join(_env.ROOT, "fonts")):
        if n.endswith(".ttf"):
            f = TTFont(os.path.join(_env.ROOT, "fonts", n), lazy=True)
            fam, cmap = f["name"].getDebugName(1), f.getBestCmap()
            cover[fam] = cover.get(fam, True) and all(ord(c) in cmap for c in uk)
    with open(os.path.join(_env.ROOT, "sketch", "collage.js"), encoding="utf-8") as f:
        src = f.read()
    table = re.findall(
        r"'([^']+)': \['([^']+)', \d+\]", src.split("SK.NO_CYRILLIC = {")[1].split("};")[0]
    )
    check("cyrillic: a stand-in for each Latin-only face", len(table) == 4, str(table))
    check(
        "cyrillic: the faces stood in for have no Cyrillic",
        all(cover.get(a) is False for a, _ in table),
        str({a: cover.get(a) for a, _ in table}),
    )
    check(
        "cyrillic: every stand-in has all of it",
        all(cover.get(b) is True for _, b in table),
        str({b: cover.get(b) for _, b in table}),
    )


def main():
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    # ---- notes and the score notation
    check("M() spellings", A.M("C4") == 60 and A.M("F#4") == A.M("Gb4") == 66 and A.M("Bb1") == 34)
    notes = A.parse_notes("1 E6 .5; 2 C4+E4+G4 1 .3")
    check(
        "parse_notes", notes == [(1.0, [88], 0.5, None), (2.0, [60, 64, 67], 1.0, 0.3)], str(notes)
    )
    score = {
        "bpm": 120,
        "events": [
            {"inst": "celesta", "vel": 0.4, "notes": "0 C5 1; 1 E5+G5 1", "transpose": 12},
            {"type": "strum", "at": 4, "chord": "C3+E3+G3", "vel": 0.5, "pattern": "half"},
            {
                "type": "gliss",
                "from": 8,
                "to": 9,
                "lo": "C4",
                "hi": "C5",
                "v0": 0.1,
                "v1": 0.4,
                "root": "C",
            },
            {
                "type": "roll",
                "inst": "timpani",
                "note": "C2",
                "from": 10,
                "to": 11,
                "step": 0.25,
                "v0": 0.1,
                "v1": 0.5,
            },
            {"type": "arp", "inst": "celesta", "at": 12, "notes": "C5 E5 G5", "step": 0.25},
            {
                "type": "drums",
                "from": 16,
                "bars": 2,
                "kit": {"kick": "x...x...x...x...", "hat": "o.o.o.o.o.o.o.o."},
            },
        ],
    }
    ev = A.score_events(score)
    kinds = {e[0] for e in ev}
    check("score: transpose", any(e[0] == "celesta" and e[1] == 84 for e in ev))
    check(
        "score: strum is 3 hits x 3 strings",
        sum(1 for e in ev if e[0] == "acoustic_guitar_nylon") == 9,
    )
    check("score: C major gliss has 8 notes", sum(1 for e in ev if e[0] == "orchestral_harp") == 8)
    check("score: roll steps", sum(1 for e in ev if e[0] == "timpani") == 5)
    check(
        "score: drums 2 bars",
        sum(1 for e in ev if e[0] == "drum") == 2 * (4 + 8),
        str(sum(1 for e in ev if e[0] == "drum")),
    )
    check(
        "score: drums need no samples",
        ("drum", "kick") not in A.needed_samples(ev) and "drum" in kinds,
    )
    try:
        A.score_events({"events": [{"type": "nope"}]})
        check("score: unknown type refused", False)
    except ValueError:
        check("score: unknown type refused", True)

    # ---- every generator makes finite, non-silent sound
    small = {"sec": 0.2}
    for name, f in sorted(A.FX.items()):
        args = dict(small) if "sec" in f.__code__.co_varnames else {}
        y = f(**args)
        check("fx %-12s" % name, y.size > 0 and np.isfinite(y).all() and np.abs(y).max() > 1e-4)
    for piece in A.DRUM_PAN:
        y = A.drum(piece)
        check("drum %-10s" % piece, y.size > 0 and np.isfinite(y).all() and np.abs(y).max() > 1e-4)
    check("drum seeds are stable", np.array_equal(A.drum("snare"), A.drum("snare")))

    # ---- ducking: full in the gaps, reduced under speech
    vo = np.zeros(SR * 3)
    vo[SR : 2 * SR] = np.sin(np.arange(SR) * 2 * np.pi * 200 / SR) * 0.3
    g = A.duck_gain(vo, amount=0.6)
    check("duck: 1.0 before speech", g[int(0.5 * SR)] > 0.98)
    check("duck: reduced under speech", g[int(1.6 * SR)] < 0.6, "%.2f" % g[int(1.6 * SR)])
    check("duck: recovers after", g[int(2.9 * SR)] > 0.8, "%.2f" % g[int(2.9 * SR)])

    # ---- the score's volumes: swell is a gain ramp, and [24, 30] (read as beats) was refused
    strings = {"inst": "string_ensemble_1", "vel": 0.17, "notes": "24 D4+F#4+B4 4"}
    bad = A.check_score({"events": [{**strings, "swell": [24, 30]}]})
    check("score volumes: swell [24, 30] refused", len(bad) == 1 and "swell" in bad[0], str(bad))
    check(
        "score volumes: swell [.3, 1] fine",
        not A.check_score({"events": [{**strings, "swell": [0.3, 1]}]}),
    )
    loud = {"drum_gain": 2, "events": [{"inst": "celesta", "vel": 3, "notes": "0 C5 1 1.8"}]}
    check(
        "score volumes: vel, note velocity, drum_gain",
        len(A.check_score(loud)) == 3,
        str(A.check_score(loud)),
    )

    # ---- the voice gate: music held under speech, left alone where it already is, free after
    t = np.arange(8 * SR) / SR
    vo = np.zeros_like(t)
    for a, b in ((1.0, 3.0), (3.3, 5.5)):  # two lines with a breath between
        k = (t >= a) & (t < b)
        vo[k] = (
            0.1 * np.sin(2 * np.pi * 180 * t[k]) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t[k]) ** 2)
        )
    voice = np.stack([vo, vo])
    tone = np.stack([np.sin(2 * np.pi * 330 * t)] * 2)

    def db(x, a, b):  # RMS in dBFS between a and b seconds
        return 20 * np.log10(np.sqrt(np.mean(x[:, int(a * SR) : int(b * SR)] ** 2)) + 1e-12)

    quiet = tone * 10 ** ((db(voice, 1, 5.5) - 16 - db(tone, 0, 8)) / 20)
    g, rep = A.voice_gate(quiet, voice, 8.0)
    check(
        "gate: music 16 dB under is left alone",
        rep["max_cut_db"] <= 1.0 and g.min() > 0.89,
        str(rep),
    )
    blare = tone * 10 ** ((db(voice, 1, 5.5) + 3 - db(tone, 0, 8)) / 20)
    g, rep = A.voice_gate(blare, voice, 8.0)
    heard = blare * g
    under = min(db(voice, a, a + 1) - db(heard, a, a + 1) for a in (1.0, 2.0, 3.5, 4.5))
    check("gate: music 3 dB over the voice held 8 dB under it", under >= 7.0, "%.1f dB" % under)
    check(
        "gate: untouched before the first word", g[int(0.3 * SR)] > 0.98, "%.2f" % g[int(0.3 * SR)]
    )
    check("gate: free again after the last word", g[int(7.5 * SR)] > 0.9, "%.2f" % g[int(7.5 * SR)])
    check("gate: says where", rep["spans"] and 0.5 <= rep["spans"][0][0] <= 1.5, str(rep["spans"]))

    # ---- the tail-word cut and word timing
    vo_mod = import_module("sketch-vo")
    tone = lambda s: np.sin(np.arange(int(s * SR)) * 2 * np.pi * 220 / SR) * 0.3  # noqa: E731
    x = np.concatenate([np.zeros(int(0.1 * SR)), tone(1.0), np.zeros(int(0.4 * SR)), tone(0.5)])
    text = "[soft] Hi there\n\nAlright."
    starts = []
    ends = []
    for i, _ch in enumerate(text):
        t0 = 0.1 + i * 0.08 if i < 15 else 1.5 + (i - 15) * 0.05
        starts.append(t0)
        ends.append(t0 + 0.07)
    align = {
        "characters": list(text),
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }
    y, lead, ok = vo_mod.cut_at_tail(x, align, "Alright.")
    check("tail: cut found a clean gap", ok)
    check("tail: tail removed, line kept", 0.95 < len(y) / SR < 1.3, "%.2fs" % (len(y) / SR))
    words = vo_mod.word_times(align, lead, "Alright.")
    check(
        "words: [tags] and tail dropped",
        [w["text"] for w in words] == ["Hi", "there"],
        str([w["text"] for w in words]),
    )

    # ---- the backup voice, for a line Gemini refuses (no API: what decides it)
    check(
        "backup: Gemini's content block is a refusal, a glitch is not",
        vo_mod.refused("finish reason block_reason=<BlockedReason.PROHIBITED_CONTENT: 2>")
        and vo_mod.refused({"blockReason": "SAFETY"})
        and not vo_mod.refused("finish reason STOP"),
    )

    def voiced(hz, s=1.5):  # a buzzy voice-like tone: a fundamental and a few harmonics
        t = np.arange(int(s * SR)) / SR
        return 0.2 * sum(np.sin(2 * np.pi * hz * k * t) / k for k in (1, 2, 3, 4))

    low, high = vo_mod.pitch_hz(voiced(115)), vo_mod.pitch_hz(voiced(230))
    check(
        "backup: pitch tells a low narrator from a high one",
        low and high and low < vo_mod.LOW_VOICE_HZ < high,
        "%s / %s Hz" % (low, high),
    )
    vdir = tempfile.mkdtemp(prefix="check-sketch-vo-")
    try:
        _sketch.write_wav(os.path.join(vdir, "L00_T0_x.wav"), voiced(230))
        with open(os.path.join(vdir, "L00_T0_x.json"), "w", encoding="utf-8") as f:
            json.dump({"gemini": {"model": "m", "voice": "Charon"}}, f)
        # Charon is labelled male, but this film's recordings are high: the measurement wins
        check(
            "backup: the film's own pitch picks the voice",
            vo_mod.backup_kind({"voice": "Charon"}, vdir) == "high",
        )
        empty = tempfile.mkdtemp(prefix="check-sketch-vo-")
        check(
            "backup: nothing recorded yet, the voice's label decides",
            vo_mod.backup_kind({"voice": "Kore"}, empty) == "high"
            and vo_mod.backup_kind({"voice": "Charon"}, empty) == "low",
        )
        shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(vdir, ignore_errors=True)
    # ---- a take's score is remembered: a re-recording re-scores only what changed
    vdir = tempfile.mkdtemp(prefix="check-sketch-vo-")
    real, calls = vo_mod.whisper_score, []
    try:
        vo_mod.whisper_score = lambda path, text, *a, **k: (
            calls.append(text) or (0.9, text, [(text, 0.0, 0.5)])
        )
        base, wav = os.path.join(vdir, "L00_T0_x"), os.path.join(vdir, "L00_T0_x_line.wav")
        _sketch.write_wav(wav, voiced(230, 0.5))
        first = vo_mod.cached_score(base, wav, "Hi there", ["Acme"], words=True)
        again = vo_mod.cached_score(base, wav, "Hi there", ["Acme"], words=True)
        check(
            "score memo: the same take is not scored twice, and reads back the same",
            len(calls) == 1 and list(again[:2]) == list(first[:2]) and again[2][0][0] == "Hi there",
            str(calls),
        )
        vo_mod.cached_score(base, wav, "Hi there", ["Acme", "Bpo"], words=True)
        _sketch.write_wav(wav, voiced(115, 0.5))
        vo_mod.cached_score(base, wav, "Hi there", ["Acme", "Bpo"], words=True)
        check("score memo: new hotwords or new audio score again", len(calls) == 3, str(calls))
    finally:
        vo_mod.whisper_score = real
        shutil.rmtree(vdir, ignore_errors=True)
    lv = vo_mod.level_to(voiced(115) * 0.01, vo_mod.BACKUP_LEVEL_DB)
    f = lv[: len(lv) // 960 * 960].reshape(-1, 960)
    got = 20 * np.log10(np.sqrt((np.sqrt((f**2).mean(axis=1)) ** 2).mean()))
    check(
        "backup: levelled to the Gemini lines",
        abs(got - vo_mod.BACKUP_LEVEL_DB) < 0.5,
        "%.1f dBFS" % got,
    )

    # ---- captions
    tl = {
        "duration": 10,
        "lines": [
            {
                "start": 0,
                "end": 4,
                "words": [
                    {"text": t, "s": i * 0.4, "e": i * 0.4 + 0.3}
                    for i, t in enumerate(
                        "One two three. Four five six seven eight nine ten eleven.".split()
                    )
                ],
            }
        ],
    }
    cues = _sketch.captions(tl, max_words=9)
    check(
        "captions: split at the sentence end",
        cues[0][2] == "One two three." and len(cues) == 2,
        str(cues),
    )
    # a narration that runs past the film (u3edgl: its last line began at 150.99 s of 150): no cue
    # from the end on, none running backwards, none outlasting the picture
    late = {
        "duration": 10,
        "lines": [
            {"start": 8.0, "end": 9.9, "words": [{"text": "Almost", "s": 8.0, "e": 9.9}]},
            {"start": 10.2, "end": 12, "words": [{"text": "gone.", "s": 10.2, "e": 12}]},
        ],
    }
    cues = _sketch.captions(late)
    check(
        "captions: nothing after the film's end, nothing backwards",
        [c[2] for c in cues] == ["Almost"] and all(s < e <= 10 for s, e, _ in cues),
        str(cues),
    )

    # ---- cut-outs (sketch-paint.py): a collage's pictures, made without a single paid call
    import io

    from PIL import Image

    paint = import_module("sketch-paint")
    a = np.zeros((400, 400, 4), np.uint8)
    yy, xx = np.mgrid[:400, :400]
    disc = (xx - 200) ** 2 + (yy - 200) ** 2 < 90**2
    a[disc] = (40, 60, 90, 255)
    a[10:14, 10:14] = (0, 0, 0, 255)  # a stray speck, the kind image models leave
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    cut = np.asarray(paint.cutout(buf.getvalue(), border=12, cut="scissor", long_side=400))
    h, w = cut.shape[:2]
    check("cutout: trimmed round the subject", abs(w - h) < 6 and 400 < w < 470, "%dx%d" % (w, h))
    check("cutout: the speck is gone, the corners clear", cut[0, 0, 3] == 0 and cut[4, 4, 3] == 0)
    rim = cut[h // 2, 6]  # just inside the left edge: the paper border, not the subject
    check("cutout: a white paper border round it", rim[3] > 200 and min(rim[:3]) > 230, str(rim))
    mid = cut[h // 2, w // 2]
    check(
        "cutout: the subject itself untouched",
        all(abs(int(v) - c) <= 2 for v, c in zip(mid[:3], (40, 60, 90), strict=True)),
        str(mid),
    )
    bare = np.asarray(paint.cutout(buf.getvalue(), border=0, long_side=400))
    edge = bare[bare.shape[0] // 2, 2]
    check(
        "cutout: border 0 leaves it bare",
        max(bare.shape[:2]) == 400 and bare[0, 0, 3] == 0 and max(edge[:3]) < 120,
        "%s %s" % (bare.shape, edge),
    )
    white = np.full((300, 300, 3), 255, np.uint8)
    white[100:200, 100:200] = (30, 30, 30)
    white[140:160, 140:160] = 255  # white inside the subject stays
    k = paint.matte_white(np.dstack([white, np.full((300, 300), 255, np.uint8)]))
    check(
        "matte: the white ground keyed off, the subject and its own white kept",
        k[5, 5, 3] == 0 and k[150, 110, 3] == 255 and k[150, 150, 3] == 255,
    )
    scene = {"name": "kitchen", "prompt": "a kitchen"}
    spec = {"backend": "muse", "model": "meta/muse-image", "style": "ink"}
    check(
        "cutouts: a scene keeps its cache key when the block gains cut-outs",
        paint.fingerprint(spec, scene)
        == paint.fingerprint({**spec, "cutouts": {"border": 9}}, scene),
    )
    cutim = {"name": "cone", "prompt": "a cone", "cutout": True}
    check(
        "cutouts: a cut-out is a .webp with its own model",
        paint.ext(spec, cutim) == ".webp"
        and paint.ext(spec, scene) == ".jpg"
        and paint.cut_spec(spec, cutim)["model"] == paint.CUTOUT_MODEL,
    )
    check(
        "cutouts: asked for alone, on white only when the model cannot do alpha",
        paint.CUTOUT_TEXT in paint.full_prompt(spec, cutim, transparent=True)
        and paint.CUTOUT_ON_WHITE not in paint.full_prompt(spec, cutim, transparent=True)
        and paint.CUTOUT_ON_WHITE in paint.full_prompt(spec, cutim)
        and paint.NO_TEXT in paint.full_prompt(spec, scene),
    )
    caps = {
        "supported_parameters": {
            "background": {"values": ["auto", "transparent"]},
            "aspect_ratio": {"values": ["1:1", "2:3", "3:2", "16:9"]},
        }
    }
    p = paint.pick_params(caps, aspect="2:3", transparent=True)
    check(
        "cutouts: alpha and shape sent where offered",
        p.get("background") == "transparent" and p.get("aspect_ratio") == "2:3",
        str(p),
    )

    cyrillic()

    # ---- the bundler, against the committed example
    ex = os.path.join(_env.ROOT, "config", "sketch", "example")
    tmp = tempfile.mkdtemp(prefix="check-sketch-")
    try:
        shutil.copytree(ex, os.path.join(tmp, "example"))
        m = _sketch.load(os.path.join(tmp, "example", "sketch.json"))
        render = import_module("sketch-render")
        page = render.bundle(m, audio=False)
        left = [
            k
            for k in (
                "__TITLE__",
                "__ENGINE__",
                "__PROPS__",
                "__MODULES__",
                "__FILM__",
                "__FONTFACES__",
                "__VO__",
                "__VARS__",
                "__IMAGES__",
            )
            if k in page
        ]
        check("bundle: every placeholder filled", not left, str(left))
        check("bundle: fonts inlined", "data:font/woff2;base64," in page)
        check("bundle: no module a film did not ask for", "SK.cutout = function" not in page)
        page3 = render.bundle(dict(m, modules=["collage"]), audio=False)
        check(
            "bundle: a module it asks for, named in an error",
            "SK.cutout = function" in page3 and "sourceURL=sketch/collage.js" in page3,
        )
        own = os.path.join(tmp, "engine")  # a film's own engine copy (Sketch Studio's)
        os.makedirs(own)
        for n in ("engine.js", "props.js", "collage.js"):
            shutil.copyfile(os.path.join(_env.ROOT, "sketch", n), os.path.join(own, n))
        with open(os.path.join(own, "collage.js"), "a", encoding="utf-8") as f:
            f.write("\n// the film's own collage.js\n")
        page4 = render.bundle(dict(m, modules=["collage"], _engine=own), audio=False)
        check(
            "bundle: the film's own copy of a module wins",
            "the film's own collage.js" in page4 and "sourceURL=engine/collage.js" in page4,
        )
        try:
            render.bundle(dict(m, modules=["nope"]), audio=False)
            unknown = False
        except SystemExit:
            unknown = True
        check("bundle: a module there is none of stops it", unknown)
        m["fonts"].append(
            {
                "file": "fonts/OldStandard-Italic.ttf",
                "family": "Old Standard TT",
                "weight": "400",
                "style": "italic",
            }
        )
        page2 = render.bundle(m, audio=False)
        check(
            "bundle: an italic face is declared and loaded as italic",
            "font-style: italic" in page2 and 'italic 400 60px \\"Old Standard TT\\"' in page2,
        )
        art = render.artifact_flavour(page)
        check(
            "artifact: no html/head/body wrapper",
            "<html" not in art and "<head>" not in art and "<body>" not in art and "<title>" in art,
        )
        with open(os.path.join(ex, "score.json"), encoding="utf-8") as f:
            ev = A.score_events(json.load(f))
        check("example score parses", len(ev) > 20, str(len(ev)))
        check("bundle: no module unless asked", "sourceURL=sketch/jelly.js" not in page)
        # a film that lists "modules" carries them; one that names a missing module is refused
        jx = os.path.join(_env.ROOT, "config", "sketch", "jelly")
        shutil.copytree(jx, os.path.join(tmp, "jelly"))
        mj = _sketch.load(os.path.join(tmp, "jelly", "sketch.json"))
        check("bundle: modules inlined", "sourceURL=sketch/jelly.js" in render.bundle(mj, False))
        # the drink: two modules in order, and the film's vars
        shutil.copytree(
            os.path.join(_env.ROOT, "config", "sketch", "mojito"), os.path.join(tmp, "mojito")
        )
        md = _sketch.load(os.path.join(tmp, "mojito", "sketch-clean.json"))
        pg = render.bundle(md, False)
        check(
            "bundle: gl3d before drink, vars inlined",
            0 < pg.find("sourceURL=sketch/gl3d.js") < pg.find("sourceURL=sketch/drink.js")
            and 'SK.VARS = {"text": false}' in pg,
        )
        mj["modules"] = ["nope"]
        try:
            render.bundle(mj, audio=False)
            check("bundle: unknown module refused", False)
        except SystemExit:
            check("bundle: unknown module refused", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    check_jelly()
    check_drink()

    print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


# The jelly's physics half has no DOM, so Node bakes a coarse specimen: a drop, a grab and a
# nudge. What is checked is what a render would otherwise be the first to show -- a bake that
# differs run to run (a still would not match its video), tets turned inside out, volume
# lost, the floor crossed, a wobble that never settles, a landing the sound never hears.
JELLY_HARNESS = r"""
globalThis.window = globalThis;
require(process.argv[2]);
const mk = () => SK.jelly.specimen({
  cell: 0.075, surfaceCell: 0.03, bubbles: { n: 2, seed: 3 },
  seeds: { rows: [0.5], spacing: 0.12, size: [0.06, 0.034, 0.017], depth: 0.045, both: false,
    seed: 7 },
  pose: { at: [0, 0.25, 0], yaw: 30 },
  actions: [
    { t: 0.6, grab: 'tip', path: [[0.35, [-0.2, 0.35, 0.1]]], twist: [[0.35, 15]] },
    { t: 1.6, nudge: 1 },
  ],
});
const a = mk(), b = mk();
a.bakeTo(3.2); b.bakeTo(3.2);
const pa = a.positions(2.5), pb = b.positions(2.5);
let same = true;
for (let i = 0; i < pa.length; i++) if (pa[i] !== pb[i]) { same = false; break; }
let minTet = Infinity, pen = 0, vmin = 9, vmax = 0, keNudge = 0, squashed = 0;
for (let f = 0; f <= 192; f++) {
  const s = a.stats(f / 60);
  minTet = Math.min(minTet, s.minTet); pen = Math.max(pen, s.pen);
  vmin = Math.min(vmin, s.volume); vmax = Math.max(vmax, s.volume); squashed += s.volume < 0.97;
  if (f / 60 > 1.6) keNudge = Math.max(keNudge, s.keSim);
}
const top = (t) => {
  const P = a.positions(t);
  let y = 0;
  for (let i = 0; i < a.n; i++) y = Math.max(y, P[i * 3 + 1]);
  return y;
};
const M = a._mesh, tets = [...M.surfE.tet, ...M.inclE.tet];
let wsum = 0;
for (let i = 0; i < M.surfE.w.length; i += 4) {
  const w = M.surfE.w;
  wsum = Math.max(wsum, Math.abs(w[i] + w[i + 1] + w[i + 2] + w[i + 3] - 1));
}
// live: the wall clock drives it -- one draw steps at most catchUp frames, the readouts a film
// draws beside it step nothing, the pointer takes hold only on the slice and drags it
const L = mk();
L.bakeTo(0.5); L.goLive();
let f0 = L.frameCount(); L.advance(5); const liveStep = L.frameCount() - f0;
f0 = L.frameCount(); L.stats(9); L.hand(9); L.follow(9); L.positions(9);
const readStep = L.frameCount() - f0;
const tip = L.pointNow('tip');
const grabMiss = L.grab([tip[0] + 3, 3, tip[2] + 3], [0, -1, 0]);
const grabHit = L.grab([tip[0], tip[1] + 3, tip[2]], [0, -1, 0]);
L.drag([tip[0] - 0.3, tip[1] + 3, tip[2]], [0, -1, 0]);
for (let k = 0; k < 40; k++) L.advance(6 + k);
const dragMoved = tip[0] - L.pointNow('tip')[0];
L.release(); L.reset();
console.log(JSON.stringify({
  liveStep, readStep, grabMiss, grabHit, dragMoved, resetT: L.simTime(),
  same, minTet, pen, vmin, vmax, squashed, vEnd: a.stats(3.2).volume,
  keNudge, keEnd: a.stats(3.2).keSim,
  lift: top(0.95) - top(0.55), embedded: tets.every((t) => t >= 0 && t < a.tets), wsum,
  events: a.events(3.2).map((e) => [e.kind, +e.t.toFixed(2)]),
}));
"""


def check_jelly():
    node = shutil.which("node")
    if not node:
        print("skip  jelly physics: node not found")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(JELLY_HARNESS)
    try:
        r = subprocess.run(
            [node, f.name, os.path.join(_env.ROOT, "sketch", "jelly.js")],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    finally:
        os.unlink(f.name)
    if r.returncode:
        check("jelly: bakes under node", False, r.stderr.strip()[-400:])
        return
    j = json.loads(r.stdout.strip().splitlines()[-1])
    ev = j["events"]
    check("jelly: two bakes are identical", j["same"])
    check("jelly: no tet inverts", j["minTet"] > 0.1, "min tet volume %.2f of rest" % j["minTet"])
    check("jelly: never below the floor", j["pen"] < 1e-9, "%.2g" % j["pen"])
    # a landing squashes it for a frame or two (measured: 94% for one frame, then 98%+) --
    # that is the impact, and is allowed; a slice that stays small is not
    check(
        "jelly: volume held (a landing may squash it briefly)",
        j["vmin"] > 0.9 and j["vmax"] < 1.05 and j["squashed"] <= 4 and abs(j["vEnd"] - 1) < 0.015,
        "%.3f .. %.3f, %d frames under 97%%, %.3f at rest"
        % (j["vmin"], j["vmax"], j["squashed"], j["vEnd"]),
    )
    check("jelly: the grab lifts the tip", j["lift"] > 0.2, "%.3f" % j["lift"])
    check(
        "jelly: a nudge settles",
        j["keEnd"] < 0.03 * j["keNudge"],
        "%.3g of %.3g" % (j["keEnd"], j["keNudge"]),
    )
    check("jelly: every surface point rides a tet", j["embedded"] and j["wsum"] < 1e-4)
    check("jelly live: a draw steps at most 2 frames", j["liveStep"] == 2, str(j["liveStep"]))
    check("jelly live: readouts step nothing", j["readStep"] == 0, str(j["readStep"]))
    check(
        "jelly live: a press takes hold on the slice, not the floor",
        j["grabHit"] and not j["grabMiss"],
    )
    check("jelly live: the drag moves the tip", j["dragMoved"] > 0.2, "%.3f" % j["dragMoved"])
    check("jelly live: reset starts the clock again", j["resetT"] == 0)
    lands = [t for k, t in ev if k == "land"]
    check("jelly: the drop is heard", any(0.05 < t < 0.4 for t in lands), str(ev))
    check(
        "jelly: the release lands",
        ["release", 0.95] in ev and any(0.95 < t < 1.6 for t in lands),
        str(ev),
    )


# The drink's physics half has no DOM either: a short pour, two cubes and a straw. What a render
# would be the first to show otherwise -- a still that does not match its video, poured volume
# lost or invented, ice that sinks, a straw through the glass, a surface that never settles.
DRINK_HARNESS = r"""
globalThis.window = globalThis;
require(process.argv[2]);
const drops = [
  { t: 1.2, kind: 'ice', at: [0.04, -0.02] }, { t: 1.45, kind: 'ice', at: [-0.1, 0.06] },
  { t: 1.7, kind: 'straw', at: [-0.06, -0.05], tilt: 10, yaw: 0.2, spin: 0.3, height: 0.12 },
];
const mk = () => SK.drink.glass({ drops, pour: { t0: 0.1, t1: 1.0, fill: 1.1 }, waves: { grid: 48 } });
const a = mk(), b = mk();
a.bakeTo(4.5); b.bakeTo(4.5);
const fa = a.frameAt(4.5), fb = b.frameAt(4.5);
const same = fa.level === fb.level && JSON.stringify(fa.bodies) === JSON.stringify(fb.bodies);
const GL = a.GL, rot = (q, v) => {
  const [x, y, z, w] = q, ix = w * v[0] + y * v[2] - z * v[1], iy = w * v[1] + z * v[0] - x * v[2];
  const iz = w * v[2] + x * v[1] - y * v[0], iw = -x * v[0] - y * v[1] - z * v[2];
  return [ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x];
};
let wall = 0;
for (let f = 60; f <= 270; f += 3) {
  const fr = a.frameAt(f / 60);
  a.bodies.forEach((bd, i) => {
    const B = fr.bodies[i];
    if (!B) return;
    for (const r0 of bd.spheres) {
      const o = rot(B.slice(3), r0), p = [B[0] + o[0], B[1] + o[1], B[2] + o[2]];
      if (p[1] > GL.yb && p[1] < GL.rim.y) wall = Math.max(wall, Math.hypot(p[0], p[2]) - GL.rIn(p[1]));
    }
  });
}
const ice = a.bodies.map((bd, i) => (bd.kind === 'ice' ? fa.bodies[i][1] : null)).filter((v) => v !== null);
const si = a.bodies.findIndex((bd) => bd.kind === 'straw'), S = fa.bodies[si];
const up = rot(S.slice(3), [0, 1, 0]);
let wave = 0;
for (const v of fa.H) wave = Math.max(wave, Math.abs(v));
const ev = a.events(4.5), pour = ev.find((e) => e.kind === 'pour');
console.log(JSON.stringify({
  same, poured: fa.vliq, want: a.pourVolume, level: fa.level, fill: GL.levelOf(a.pourVolume), ice,
  wall, strawTilt: Math.acos(Math.min(1, Math.abs(up[1]))) * 180 / Math.PI, strawInside: Math.hypot(S[0], S[2]) < GL.rim.r,
  wave, pour: pour ? [pour.f0, pour.f1] : null, enters: ev.filter((e) => e.kind === 'enter').length,
}));
"""


def check_drink():
    node = shutil.which("node")
    if not node:
        print("skip  drink physics: node not found")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(DRINK_HARNESS)
    try:
        r = subprocess.run(
            [node, f.name, os.path.join(_env.ROOT, "sketch", "drink.js")],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    finally:
        os.unlink(f.name)
    if r.returncode:
        check("drink: bakes under node", False, r.stderr.strip()[-400:])
        return
    j = json.loads(r.stdout.strip().splitlines()[-1])
    check("drink: two bakes are identical", j["same"])
    check(
        "drink: every drop poured lands in the glass",
        abs(j["poured"] - j["want"]) < 1e-9,
        "%.5f of %.5f" % (j["poured"], j["want"]),
    )
    check(
        "drink: the ice lifts the level above the pour's own",
        j["fill"] < j["level"] < j["fill"] + 0.1,
        "%.3f against %.3f" % (j["level"], j["fill"]),
    )
    check(
        "drink: ice floats just under the surface",
        all(j["level"] - 0.12 < y < j["level"] for y in j["ice"]),
        "centres %s, surface %.3f" % (j["ice"], j["level"]),
    )
    check("drink: nothing crosses the glass", j["wall"] < 0.01, "%.3f past the wall" % j["wall"])
    check(
        "drink: the straw leans on the rim, inside",
        j["strawInside"] and 10 < j["strawTilt"] < 45,
        "%.1f deg" % j["strawTilt"],
    )
    check("drink: the surface settles", j["wave"] < 0.03, "%.3f" % j["wave"])
    check(
        "drink: the pour's pitch rises as it fills",
        bool(j["pour"]) and j["pour"][1] > j["pour"][0] * 1.2,
        str(j["pour"]),
    )
    check("drink: each thing that goes in is heard", j["enters"] >= 3, str(j["enters"]))


if __name__ == "__main__":
    main()
