#!/usr/bin/env python
"""Self-test for the sketch-film scripts: no API, no browser, no encode, seconds.

Exercises the pieces a paid or slow run would otherwise be the first to reach: the score
notation and every event type, every SFX and drum generator, the speech ducker, the
tail-word cut that fixes eleven_v3's clipped endings, word timings with [audio tags],
caption chunking, the cut-outs a collage is built from (specks, trim, paper border, the key off
a white ground, and cache keys that stay put for scenes), and the page bundler against the
committed example film.

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


def heads():
    """Talking heads: the rig geometry (head-rig.py) on a face measured once from a
    public-domain photo, the mouth measured from a voice, who speaks which line, and the page a
    film with heads bundles. No MediaPipe, no browser."""
    rig = import_module("head-rig")
    hd = import_module("_heads")
    vo_mod = import_module("sketch-vo")
    ex = os.path.join(_env.ROOT, "config", "sketch", "heads-example")
    with open(os.path.join(ex, "wilbur.landmarks.json"), encoding="utf-8") as f:
        P = np.array(json.load(f)["p"], np.float64)
    fr = rig.frame(P)
    o, right, down, W, H = fr
    check(
        "heads: the face's axes are square and point to the chin",
        abs(np.dot(right, down)) < 1e-9 and np.dot(P[rig.CHIN] - o, down) > 0 and W > 0 and H > 0,
    )
    cuts = rig.cuts(P, fr)
    below = lambda poly: min((np.asarray(poly) - o) @ down) > -H * 0.03  # noqa: E731
    check(
        "heads: the jaw pieces lie under the mouth",
        below(cuts["chin"]["poly"]) and below(cuts["dummy"]["poly"]),
    )
    sl = cuts["dummy"]["slits"]
    check(
        "heads: the dummy's slits run down from the mouth corners",
        all(np.dot(s[1] - s[0], down) > H * 0.08 for s in sl),
    )
    # a photo of two founders: faces counted left to right, a small face behind them not counted
    boxes = [(600, 100, 200, 240, 0.9), (100, 120, 180, 220, 0.9), (400, 30, 40, 50, 0.8)]
    got = [b[0] for b in rig.main_faces(boxes)]
    check("heads: a group photo's people, left to right", got == [100, 600], str(got))
    m = rig.mesh(P, fr, 8.0)
    up_ring = set(rig.LIP_IU[1:-1]) | set(rig.LIP_OU[1:-1])
    lo_ring = set(rig.LIP_IL[1:-1]) | set(rig.LIP_OL[1:-1])
    u = (m["p"] - o) @ right / (W / 2)
    um = np.linalg.norm(P[291] - P[61]) / W
    bridges = [t for t in m["t"] if set(t) & up_ring and set(t) & lo_ring and abs(u[t].mean()) < um]
    # the lips once smeared across an open mouth: a triangle from the upper lip to the lower
    # lip's middle ring survived, stretched over the dark and hid the teeth
    check("heads: no triangle bridges the mouth", not bridges, "%d bridging" % len(bridges))
    check(
        "heads: the jaw carries the lower lip, not the eyes",
        min(m["wj"][i] for i in rig.LIP_IL[3:-3]) > 0.5
        and max(m["wj"][i] for i in rig.EYE_L_UP + rig.EYE_R_UP + rig.BROW_L) == 0,
    )
    lids = [m["b"][i] for i in rig.EYE_L_UP[2:-2] + rig.EYE_R_UP[2:-2]]
    check(
        "heads: a blink brings the upper lids down",
        all(np.dot(b, down) > 1.0 for b in lids),
        str(np.round(lids, 1).tolist()),
    )
    # the mouth, from a voice: silence shut, syllables open and shut, the mouth a hair early
    sr = hd.SR
    t = np.arange(int(2.0 * sr)) / sr
    buzz = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in (1, 2, 3, 4, 5, 6))
    syll = (np.sin(2 * np.pi * 4 * (t - 0.5)) > 0) & (t > 0.5) & (t < 1.5)  # 4 a second
    tr = hd.mouth_track(0.2 * buzz * syll, sr)
    o_ = np.array(tr["o"]) / 100
    fps = tr["fps"]
    check("heads: the track spans the line", len(o_) == int(np.ceil(len(t) / (sr // fps))))
    check(
        "heads: shut in the silence, wide on the syllables",
        o_[: int(0.4 * fps)].max() < 0.05 and o_[int(0.7 * fps) : int(1.3 * fps)].max() > 0.8,
        "%.2f / %.2f" % (o_[: int(0.4 * fps)].max(), o_[int(0.7 * fps) : int(1.3 * fps)].max()),
    )
    peaks = int(((o_[1:-1] > o_[:-2]) & (o_[1:-1] >= o_[2:]) & (o_[1:-1] > 0.5)).sum())
    check("heads: one opening a syllable", peaks == 4, "%d openings" % peaks)
    first = np.argmax(o_ > 0.3) / fps
    check("heads: the mouth leads its sound", 0.4 <= first <= 0.5, "%.2fs" % first)
    # who speaks: the timeline's word, else the script's, else the only head
    tl = {
        "lines": [
            {"i": 0, "start": 0, "end": 1, "words": [], "who": "a"},
            {"i": 1, "start": 1, "end": 2, "words": []},
        ]
    }
    mm = {"heads": {"a": "x.png", "b": "y.png"}, "vo": {"lines": [{}, {"who": "b"}]}, "_dir": ex}
    who = [L["who"] for L in hd.voice_lines(mm, tl)]
    one = hd.voice_lines({"heads": {"solo": "x.png"}, "vo": {"lines": [{}, {}]}, "_dir": ex}, tl)
    check(
        "heads: every line knows its speaker",
        who == ["a", "b"] and [L["who"] for L in one] == ["a", "solo"],
        str(who),
    )
    vo = {"voice": "Kore", "cast": {"a": {"voice": "Puck"}}}
    check(
        "heads: a speaker's voice is laid over the film's",
        vo_mod.line_vo(vo, {"who": "a"})["voice"] == "Puck"
        and vo_mod.line_vo(vo, {})["voice"] == "Kore",
    )
    ln = {"text": "Hello."}
    check(
        "heads: a line read in another voice is a new take, the narrator's cache stands",
        vo_mod.fingerprint(ln, vo_mod.line_vo(vo, {**ln, "who": "a"}))
        != vo_mod.fingerprint(ln, vo_mod.line_vo(vo, ln))
        and vo_mod.fingerprint(ln, vo_mod.line_vo(vo, ln)) == vo_mod.fingerprint(ln, vo),
    )
    # the page: the module, the rigs and their pictures, and the voice lines with mouths
    tmp = tempfile.mkdtemp(prefix="check-sketch-heads-")
    try:
        d = os.path.join(tmp, "heads")
        shutil.copytree(ex, d)
        from PIL import Image

        for name in ("wilbur", "orville"):
            rd = os.path.join(d, "rigs", name)
            os.makedirs(rd)
            Image.new("RGBA", (8, 8), (200, 180, 160, 255)).save(os.path.join(rd, "head.png"))
            Image.new("RGB", (8, 8), (90, 80, 70)).save(os.path.join(rd, "photo.jpg"))
            with open(os.path.join(rd, "rig.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "v": rig.RIG_VERSION,
                        "name": name,
                        "head": {"file": "head.png"},
                        "photo": {"file": "photo.jpg"},
                    },
                    f,
                )
        os.makedirs(os.path.join(d, "audio", "vo"))
        _sketch.write_wav(os.path.join(d, "audio", "vo", "l0.wav"), 0.2 * buzz * syll)
        with open(os.path.join(d, "audio", "vo", "timeline.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "lines": [
                        {
                            "i": 0,
                            "start": 0.6,
                            "end": 2.6,
                            "who": "wilbur",
                            "file": "audio/vo/l0.wav",
                            "words": [],
                        }
                    ]
                },
                f,
            )
        m = _sketch.load(os.path.join(d, "sketch.json"))
        render = import_module("sketch-render")
        page = render.bundle(m, audio=False)
        check(
            "heads: the page carries the module, the rigs and their pictures",
            "sourceURL=sketch/heads.js" in page
            and "SK.RIGS = {" in page
            and '"rig:orville:photo": "data:image/jpeg;base64,' in page,
        )
        vo_js = json.loads(page.split("<script>\nSK.VO = ")[1].split(";\n</script>")[0])
        L0 = vo_js["lines"][0]
        check(
            "heads: a voice line carries its speaker and its mouth",
            L0["who"] == "wilbur" and L0["mouth"]["fps"] == hd.FPS and max(L0["mouth"]["o"]) > 80,
        )
        plain = render.bundle(dict(m, heads={}), audio=False)
        check("heads: a film without heads carries none of it", "SK.RIGS" not in plain)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    heads()

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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
