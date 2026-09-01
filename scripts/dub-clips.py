#!/usr/bin/env python
"""Dub a clip into another language without losing its cadence.

The naive dub -- translate the clip, read the translation over the top -- drifts
within a few seconds and never recovers, because the English runs at a different
speed to the original. What the eye actually notices is not phoneme-level
mismatch but *cadence*: sound starting when the mouth opens, stopping when it
closes, and pausing where the speaker pauses.

So the clip is cut into speech units at the pauses the speaker actually took,
and each unit is dubbed into its own slot on the original timeline:

  1. segment   split at real pauses; recursively split anything still too long
               at its best internal gap. Punctuation is a hint, not the rule --
               this transcript stops punctuating entirely near the end, and a
               punctuation-driven split produced a 25-second "unit".
  2. translate ask for every slot at once, with the whole passage as context and
               a per-slot time budget, plus a shorter `tight` fallback.
  3. fit       render the slot, measure it, and re-render at a computed speaking
               rate so it lands in its slot. Prosodic re-timing beats stretching
               the waveform, so that is tried first and rubberband is the last
               resort.
  4. place     lay each unit at the exact time the original phrase began.

Speech therefore starts and stops with the mouth, and every pause the speaker
took is still a pause. `sync` in the report measures precisely that: the share
of the clip where dub and original agree about whether anyone is talking.

Invoke as:  python scripts/dub-clips.py --manifest projects/<id>/clips-vertical.json --only <clip-id>
"""
import sys, os, json, argparse, subprocess, math, hashlib
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

import numpy as np

_outline = import_module("transcript-outline")
_cut = import_module("cut-clips")          # boundary resolution, shared with the render
_tts = import_module("dub-tts")
_tr = import_module("dub-translate")

ENV = _env.ENV
SR = _tts.SR
MIN_GAP = 0.06        # never let one unit run into the next
SENT_END = (".", "!", "?", "…")
CLAUSE_END = (",", ";", ":", "—", "–")

# The words.json this script writes is byte-compatible with faster-whisper's,
# and that format carries a real ISO 639-1 code -- "Spanish"[:2] is not one.
ISO_639 = {"english": "en", "ukrainian": "uk", "russian": "ru", "spanish": "es",
           "german": "de", "french": "fr", "italian": "it", "portuguese": "pt",
           "polish": "pl", "dutch": "nl", "greek": "el", "czech": "cs",
           "turkish": "tr", "japanese": "ja", "chinese": "zh", "korean": "ko",
           "arabic": "ar", "hindi": "hi", "romanian": "ro", "hungarian": "hu"}


def iso_lang(name):
    code = ISO_639.get(name.strip().lower())
    if code:
        return code
    if len(name) == 2:
        return name.lower()
    guess = name[:2].lower()
    print("   WARNING: no ISO 639-1 code known for %r, writing %r" % (name, guess))
    return guess


def _fingerprint(plan, args):
    """Identity of the plan a translation belongs to.

    A cached translation is matched to plan slots purely by index, so a plan
    rebuilt with a different --max-dur silently maps every line onto the wrong
    stretch of audio. Index equality is not identity; this is.
    """
    key = "|".join(u["text"] for u in plan["units"])
    key += "|%s|%s|%s|%s" % (args.max_dur, args.min_dur, args.engine, args.dst_lang)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------- segmentation
def _span(u):
    return u[-1]["end"] - u[0]["start"]


def best_split(u, min_dur):
    """Index to cut a too-long unit at, or None if every cut leaves a sliver.

    Scored on the size of the pause, with a bonus for punctuation and a mild
    preference for the middle. Works on a transcript with no punctuation at all,
    which is what this one degrades into.
    """
    t0, t1 = u[0]["start"], u[-1]["end"]
    half = max((t1 - t0) / 2.0, 1e-6)
    mid = t0 + half
    best = bi = None
    for i in range(1, len(u)):
        if u[i - 1]["end"] - t0 < min_dur or t1 - u[i]["start"] < min_dur:
            continue
        s = u[i]["start"] - u[i - 1]["end"]
        tail = u[i - 1]["text"].rstrip()
        if tail.endswith(SENT_END):
            s += 0.30
        elif tail.endswith(CLAUSE_END):
            s += 0.15
        s += 0.10 * (1.0 - abs(u[i]["start"] - mid) / half)
        if best is None or s > best:
            best, bi = s, i
    return bi


def segment(words, max_dur=4.0, min_dur=0.9):
    units = [list(words)]
    changed = True
    while changed:
        changed, nxt = False, []
        for u in units:
            if _span(u) <= max_dur or len(u) < 4:
                nxt.append(u)
                continue
            i = best_split(u, min_dur)
            if i is None:
                nxt.append(u)
                continue
            nxt += [u[:i], u[i:]]
            changed = True
        units = nxt

    # a sliver on its own gets a whole slot and sounds clipped; fold it into the
    # preceding unit when it is closer to that than to what follows
    out = []
    for n, u in enumerate(units):
        if out and _span(u) < min_dur:
            gap_prev = u[0]["start"] - out[-1][-1]["end"]
            gap_next = (units[n + 1][0]["start"] - u[-1]["end"]
                        if n + 1 < len(units) else 1e9)
            if gap_prev <= gap_next and _span(out[-1]) + _span(u) < max_dur * 1.6:
                out[-1] = out[-1] + u
                continue
        out.append(u)
    return out


def plan_from_script(clip, path, start, end):
    """A plan whose slots come from a written narration, not from a transcript.

    `build_plan` segments what the original speaker said and lays the new lines
    on their pauses. That is right for a dub -- the mouth on screen is still
    moving -- and wrong for a voice-over that REPLACES the sound, because the
    old rhythm is usually the thing being fixed. Here the slots are declared
    against the picture instead:

        [ {"t": 0.4, "text": "...", "tight": "..."}, ... ]

    `t` is seconds from the start of the clip. A line runs until the next one
    begins (less a breath), or to the end of the clip if it is the last. `dur`
    may be given to end a line earlier than that.

    Units are marked `free`, which tells `fit_unit` not to draw a short line out
    to fill its slot: with no mouth on screen, a line that finishes early is a
    pause, not a hole.
    """
    with open(path, encoding="utf-8") as f:
        script = json.load(f)
    if isinstance(script, dict):
        script = script["lines"]
    if not script:
        sys.exit("%s: %s has no lines" % (clip["id"], path))
    dur = end - start
    rows = sorted(({"t": float(r["t"]), "text": r["text"].strip(),
                    "tight": (r.get("tight") or "").strip(),
                    "dur": r.get("dur")} for r in script),
                  key=lambda r: r["t"])
    if rows[0]["t"] < -1e-6:
        sys.exit("%s: first line starts at %.2fs, before the clip"
                 % (clip["id"], rows[0]["t"]))
    if rows[-1]["t"] >= dur:
        sys.exit("%s: a line starts at %.2fs but the clip is %.2fs long"
                 % (clip["id"], rows[-1]["t"], dur))
    units = []
    for n, r in enumerate(rows):
        nxt = rows[n + 1]["t"] if n + 1 < len(rows) else dur
        room = max(nxt - r["t"] - MIN_GAP, 0.35)
        slot = min(float(r["dur"]), room) if r["dur"] else room
        units.append({
            "i": n + 1,
            "t0": round(r["t"], 3),
            "t1": round(r["t"] + slot, 3),
            "dur": round(slot, 3),
            # nothing may run into the next line, so hard and dur are the same
            # here -- unlike a dub, there is no following silence to borrow
            "hard": round(slot, 3),
            "free": True,
            "text": r["text"],
        })
    return ({"clip": clip["id"], "start": round(start, 3), "end": round(end, 3),
             "duration": round(dur, 3), "units": units, "source": "script",
             "script": path,
             "context": " ".join(u["text"] for u in units)},
            [{"i": u["i"], "text": u["text"], "tight": r["tight"] or u["text"]}
             for u, r in zip(units, rows)])


def build_plan(clip, words, start, end, max_dur, min_dur):
    sel = [w for w in words if w["start"] >= start - 1e-6 and w["end"] <= end + 1e-6]
    if not sel:
        sys.exit("%s: no transcript words inside %.2f-%.2f" % (clip["id"], start, end))
    groups = segment(sel, max_dur, min_dur)
    dur = end - start
    units = []
    for n, g in enumerate(groups):
        t0 = g[0]["start"] - start
        t1 = g[-1]["end"] - start
        nxt = groups[n + 1][0]["start"] - start if n + 1 < len(groups) else dur
        units.append({
            "i": n + 1,
            "t0": round(t0, 3),
            "t1": round(t1, 3),
            "dur": round(t1 - t0, 3),
            # a unit may run on into the pause that follows it -- borrowing that
            # silence is free, and it saves speeding the voice up
            "hard": round(max(t1 - t0, nxt - t0 - MIN_GAP), 3),
            "text": " ".join(w["text"] for w in g).strip(),
        })
    return {"clip": clip["id"], "start": round(start, 3), "end": round(end, 3),
            "duration": round(dur, 3), "units": units,
            "context": " ".join(w["text"] for w in sel).strip()}


# -------------------------------------------------------------------- fitting
_RB = None


def _has_rubberband():
    global _RB
    if _RB is None:
        p = subprocess.run(["ffmpeg", "-v", "error", "-filters"],
                           capture_output=True, env=ENV)
        _RB = b" rubberband " in p.stdout
    return _RB


def _stretch(x, factor):
    """Time-scale audio by `factor` without moving pitch (rubberband).

    Returns (audio, ok). ok=False means the audio came back untouched -- the
    caller must not report a squeeze that never happened.
    """
    if abs(factor - 1.0) < 1e-3 or x.size == 0:
        return x, True
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
         "-i", "pipe:0", "-filter:a", "rubberband=tempo=%.6f" % (1.0 / factor),
         "-f", "f32le", "pipe:1"],
        input=x.astype(np.float32).tobytes(), capture_output=True, env=ENV)
    if p.returncode:
        return x, False
    return np.frombuffer(p.stdout, dtype=np.float32).copy(), True


def fit_unit(u, tr, voice, backend="edge"):
    """Render one slot so it lands inside it. Returns (audio, marks, fit)."""
    # How hard this voice can be pushed. ElevenLabs caps `speed` at 0.7-1.2, so
    # it has far less room to compress a long line than edge's rate does, and
    # falls back on the `tight` rewrite more often.
    lo, hi = _tts.rate_limits(backend)
    max_rate, slow_rate = min(25.0, hi), max(-18.0, lo)
    slot, hard = u["dur"], u["hard"]
    cache = {}                 # a TTS render costs money; never pay for the
                               # same (text, rate) twice within one slot

    def say(text, rate=0.0):
        k = (text, round(rate, 1))
        if k not in cache:
            cache[k] = _tts.speak(text, voice, rate, backend=backend)
        return cache[k]

    audio, marks = say(tr["text"])
    nat = audio.size / float(SR)
    nat_used = nat
    note, rate, text = "natural", 0.0, tr["text"]

    if nat > hard:
        # too long: ask the voice to speak faster before touching the waveform
        rate = min(max_rate, _tts.rate_for(nat, hard, backend=backend))
        audio, marks = say(text, rate)
        note = "rate%+.0f%%" % rate
        if audio.size / float(SR) > hard and tr.get("tight") and tr["tight"] != text:
            text = tr["tight"]
            audio, marks = say(text)
            nat_used = audio.size / float(SR)
            note, rate = "tight", 0.0
            if nat_used > hard:
                rate = _tts.rate_for(nat_used, hard, backend=backend)
                audio, marks = say(text, rate)
                note = "tight+rate%+.0f%%" % rate
    elif nat < slot * 0.80 and not u.get("free"):
        # too short: her mouth is still moving, so draw the delivery out rather
        # than leaving a hole of silence under a talking face
        rate = max(slow_rate, _tts.rate_for(nat, slot, backend=backend))
        audio, marks = say(text, rate)
        note = "rate%+.0f%%" % rate

    got = audio.size / float(SR)
    if got > hard:                       # last resort, kept small on purpose
        f = hard / got
        if f > 0.82:
            audio, ok = _stretch(audio, f)
            if ok:
                marks = [(w, a * f, b * f) for w, a, b in marks]
                note += "+squeeze%.0f%%" % ((1 - f) * 100)
            else:
                why = ("this ffmpeg has no rubberband filter"
                       if not _has_rubberband() else "rubberband failed")
                print("   WARNING: slot %d: %s -- audio left %.2fs over its slot"
                      % (u["i"], why, got - hard))
    final = audio.size / float(SR)
    if final > hard + 0.05:
        print("   WARNING: slot %d overruns its hard budget (%.2fs > %.2fs) -- "
              "it will overlap the next line" % (u["i"], final, hard))
    # `natural` is the unhurried duration of the text actually spoken -- when
    # the tight rewrite is used the full line's timing says nothing about it
    return audio, marks, {"note": note, "rate": round(rate, 1), "text": text,
                          "natural": round(nat_used, 3),
                          "natural_full": round(nat, 3),
                          "final": round(final, 3)}


# --------------------------------------------------------------------- mixing
def place(units, audios, total):
    """Lay each unit onto a silent bed at the time the original phrase began.

    The bed's length is the clip's length, exactly -- cut-clips.py asserts the
    rendered duration against the plan, so the wav must not run long. Anything
    a misfit unit pushes past the end is cut, but loudly.
    """
    n = int(math.ceil(total * SR))
    bed = np.zeros(n + SR, dtype=np.float32)     # slack absorbs an overrun
    fade = int(0.005 * SR)
    for u, a in zip(units, audios):
        if a.size == 0:
            continue
        i = int(round(u["t0"] * SR))
        if i >= bed.size:
            print("   WARNING: slot %d starts past the end of the clip -- skipped"
                  % u["i"])
            continue
        a = a.copy()
        if a.size > 2 * fade:            # no clicks at the splice points
            a[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            a[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        j = min(bed.size, i + a.size)
        bed[i:j] += a[:j - i]
    tail = bed[n:]
    if tail.size and float(np.abs(tail).max()) > 1e-4:
        over = float(np.flatnonzero(np.abs(tail) > 1e-4)[-1] + 1) / SR
        print("   WARNING: %.2fs of audio ran past the clip end and was cut"
              % over)
    return bed[:n]


def loudnorm(src, dst, lufs=-14.5):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af",
                        "loudnorm=I=%.1f:TP=-1.5:LRA=11" % lufs,
                        "-ar", str(SR), "-ac", "1", dst], env=ENV)
    if r.returncode:
        sys.exit("loudness normalisation failed for %s" % src)


def keep_better(changed, units_by_i, old, before,
                audio_by_i, marks_by_i, fit_by_i, by_i):
    """Undo any retune rewrite that measures worse than what it replaced.

    A rewrite is a guess corrected by measurement, and a correction can
    overshoot: asked for SHORTER, the model can come back far under, which is
    the dead-air-under-a-moving-mouth failure the retune exists to fix. Each
    re-rendered slot is compared against its previous take and reverted if it
    landed further from the slot length. Returns the slots put back.
    """
    reverted = []
    for i in changed:
        u = units_by_i[i]
        if (abs(fit_by_i[i]["final"] - u["dur"])
                > abs(old[i][2]["final"] - u["dur"]) + 1e-6):
            audio_by_i[i], marks_by_i[i], fit_by_i[i] = old[i]
            by_i[i].update(before[i])
            reverted.append(i)
    return reverted


def sync_score(units, fits, total, step=0.01):
    """Share of the clip where dub and original agree that someone is talking.

    This is the number the whole design is chasing: it drops when the dub talks
    over a pause, and when it falls silent under a moving mouth.
    """
    if total <= 0:
        return 0.0
    n = int(total / step)
    a = np.zeros(n, dtype=bool)
    b = np.zeros(n, dtype=bool)
    for u, f in zip(units, fits):
        a[int(u["t0"] / step):int(min(total, u["t1"]) / step)] = True
        b[int(u["t0"] / step):int(min(total, u["t0"] + f["final"]) / step)] = True
    return float((a == b).mean())


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids")
    ap.add_argument("--outdir", default="outputs/dub")
    ap.add_argument("--tts", default="edge", choices=["edge", "elevenlabs"],
                    help="which voice service to speak with")
    ap.add_argument("--voice", help="voice name or id; default depends on --tts")
    ap.add_argument("--el-model", help="ElevenLabs model id override (default "
                                       "comes from config/elevenlabs-voices.json)")
    ap.add_argument("--tag",
                    help="tag in the output filenames; defaults to en for edge "
                         "and en-el for elevenlabs, so the two backends never "
                         "overwrite each other's artifacts")
    ap.add_argument("--engine", default="claude",
                    choices=["claude", "openai", "manual"])
    ap.add_argument("--model", help="model override for the translation engine")
    ap.add_argument("--translation",
                    help="a hand-written translation json for ONE clip; "
                         "implies the retune round will not rewrite it")
    ap.add_argument("--script",
                    help="a written voice-over for ONE clip, timed against the "
                         "PICTURE: [{\"t\": 0.4, \"text\": \"...\"}, ...]. "
                         "Slots come from this instead of the speaker's pauses, "
                         "and nothing is translated")
    ap.add_argument("--src-lang", default="Ukrainian")
    ap.add_argument("--dst-lang", default="English")
    ap.add_argument("--max-dur", type=float, default=4.0,
                    help="longest speech unit before it is split again")
    ap.add_argument("--min-dur", type=float, default=0.9)
    ap.add_argument("--words-per-sec", type=float, default=3.2)
    ap.add_argument("--tune-rounds", type=int, default=1,
                    help="rounds of measure-then-rewrite for slots that do not fit")
    ap.add_argument("--plan-only", action="store_true",
                    help="write and print the segmentation, spend nothing")
    ap.add_argument("--retranslate", action="store_true",
                    help="drop the cached translation and ask the engine again "
                         "(--force alone re-renders audio but keeps the text)")
    ap.add_argument("--force", action="store_true",
                    help="re-render even if the wav exists; keeps the cached "
                         "translation (see --retranslate)")
    args = ap.parse_args()

    backend = args.tts
    if args.el_model:
        _tts.EL_MODEL = args.el_model
    # distinct default tags: with a shared one the second backend either
    # silently skips ("exists") or overwrites the first one's artifacts
    tag = args.tag or ("en" if backend == "edge" else "en-el")
    voice = args.voice or _tts.default_voice(backend)
    print("voice %s via %s, tag %s" % (_tts.resolve_voice(voice, backend),
                                       backend, tag))
    if args.translation and args.retranslate:
        sys.exit("--translation and --retranslate contradict each other: one "
                 "supplies the text, the other throws text away")
    if args.script:
        if args.translation:
            sys.exit("--script and --translation both supply the lines; pick one")
        # A written voice-over has nothing to translate, and the retune round
        # must not quietly rewrite words a human chose. `manual` makes retune
        # report which slots overran and change nothing -- which is the signal
        # to edit the script, not a failure.
        if args.engine != "manual":
            print("   --script implies --engine manual (nothing to translate)")
            args.engine = "manual"

    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)
    words = _outline.load_words(m["words"])
    pad = m.get("pad", {})
    pad_head, pad_tail = float(pad.get("head", 0.12)), float(pad.get("tail", 0.30))
    prefix = m.get("prefix", "")
    os.makedirs(args.outdir, exist_ok=True)
    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None
    selected = [c for c in m["clips"] if not wanted or c["id"] in wanted]
    if args.script and len(selected) != 1:
        # the lines are timed against ONE clip's picture; spreading them over a
        # second clip would speak them over footage they were not written for
        sys.exit("--script is written for one clip's timeline, but %d clips are "
                 "selected -- narrow it with --only" % len(selected))
    if args.translation and len(selected) > 1:
        sys.exit("--translation is one clip's script; select that clip with "
                 "--only (got %d clips)" % len(selected))

    for clip in selected:
        # the SAME resolver the video cut uses, so audio and picture agree to the
        # millisecond about where this clip starts
        start, end = _cut.resolve(clip, words, pad_head, pad_tail)
        stem = os.path.join(args.outdir,
                            ("%s-%s" % (prefix, clip["id"])) if prefix else clip["id"])
        if os.path.dirname(stem):        # a prefix may carry a subdirectory
            os.makedirs(os.path.dirname(stem), exist_ok=True)
        wav = "%s.%s.wav" % (stem, tag)
        wjson = "%s.%s.words.json" % (stem, tag)

        if args.plan_only:               # before the skip: re-planning an
            plan = (plan_from_script(clip, args.script, start, end)[0]
                    if args.script else
                    build_plan(clip, words, start, end,     # already-rendered
                               args.max_dur, args.min_dur))  # clip is the point
            with open("%s.%s.plan.json" % (stem, tag), "w",
                      encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            durs = sorted(u["dur"] for u in plan["units"])
            print("== %s  %.2f-%.2f (%.2fs)" % (clip["id"], start, end, end - start))
            print("   %d speech units, median %.2fs, longest %.2fs"
                  % (len(durs), durs[len(durs) // 2], durs[-1]))
            continue

        dpath = "%s.%s.dub.json" % (stem, tag)
        if os.path.exists(dpath):
            with open(dpath, encoding="utf-8") as f:
                prev = json.load(f)
            was = (prev.get("backend"), prev.get("voice"))
            now = (backend, _tts.resolve_voice(voice, backend))
            if was != (None, None) and was != now and not args.force:
                sys.exit("tag %r already holds a %s/%s dub; you asked for %s/%s."
                         "\nUse a distinct --tag to keep both, or --force to "
                         "overwrite." % ((tag,) + was + now))

        if os.path.exists(wav) and not args.force:
            print("skip (exists) %s" % wav)
            continue

        print("== %s  %.2f-%.2f (%.2fs)" % (clip["id"], start, end, end - start))
        script_rows = None
        if args.script:
            plan, script_rows = plan_from_script(clip, args.script, start, end)
        else:
            plan = build_plan(clip, words, start, end, args.max_dur, args.min_dur)
        with open("%s.%s.plan.json" % (stem, tag), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        durs = sorted(u["dur"] for u in plan["units"])
        print("   %d speech units, median %.2fs, longest %.2fs"
              % (len(durs), durs[len(durs) // 2], durs[-1]))

        # A cached translation is only valid for the plan and engine it was
        # made against -- slots are matched by bare index, so reusing across a
        # changed plan would speak the wrong line into the wrong hole.
        fp = _fingerprint(plan, args)
        tpath = "%s.%s.translation.json" % (stem, tag)

        def save_rows(rows):
            with open(tpath, "w", encoding="utf-8") as f:
                json.dump({"fingerprint": fp, "rows": rows}, f,
                          ensure_ascii=False, indent=2)

        if script_rows is not None:
            # the script IS the lines; there is nothing to translate and
            # nothing to cache, so the fingerprint dance is skipped entirely
            rows = script_rows
        elif args.translation:
            with open(args.translation, encoding="utf-8") as f:
                data = json.load(f)
            rows = data["rows"] if isinstance(data, dict) else data
        elif os.path.exists(tpath) and not args.retranslate:
            with open(tpath, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if data.get("fingerprint") not in (None, fp):
                    sys.exit("%s was translated for a different plan or engine "
                             "(fingerprint %s, this run needs %s).\nPass "
                             "--retranslate, or use a fresh --tag."
                             % (os.path.basename(tpath),
                                data.get("fingerprint"), fp))
                rows = data["rows"]
            else:
                rows = data              # pre-fingerprint file: trust it once
                print("   note: %s predates plan fingerprints -- assuming it "
                      "matches this plan" % os.path.basename(tpath))
            print("   reusing %s" % os.path.basename(tpath))
        else:
            rows = _tr.translate(plan["units"], plan["context"], args.engine,
                                 args.src_lang, args.dst_lang,
                                 args.words_per_sec, args.model)
            save_rows(rows)
        by_i = {int(r["i"]): r for r in rows}
        units_by_i = {u["i"]: u for u in plan["units"]}
        for u in plan["units"]:
            if u["i"] not in by_i:
                sys.exit("%s: no translation for slot %d" % (clip["id"], u["i"]))

        audio_by_i, marks_by_i, fit_by_i = {}, {}, {}

        def render(indices):
            for i in indices:
                (audio_by_i[i], marks_by_i[i],
                 fit_by_i[i]) = fit_unit(units_by_i[i], by_i[i], voice, backend)

        render([u["i"] for u in plan["units"]])

        # How long a sentence takes to say is a guess until you say it. Now that
        # every slot has been timed, hand the measurements back to the translator
        # and re-render only what it changed -- a line that came up short leaves
        # dead air under a moving mouth, which reads worse than a slightly long one.
        for rnd in range(args.tune_rounds):
            fits_now = [fit_by_i[u["i"]] for u in plan["units"]]
            before = {i: dict(by_i[i]) for i in by_i}
            old = {i: (audio_by_i[i], marks_by_i[i], fit_by_i[i]) for i in by_i}
            rows, n = _tr.retune(plan["units"], fits_now, rows, plan["context"],
                                 args.engine, args.src_lang, args.dst_lang,
                                 args.words_per_sec, args.model)
            if not n:
                break
            by_i = {int(r["i"]): r for r in rows}
            changed = [i for i in sorted(by_i)
                       if by_i[i]["text"] != before[i]["text"]]
            if not changed:
                break
            print("   round %d: re-rendering %d slot(s)" % (rnd + 1, len(changed)))
            render(changed)
            for i in keep_better(changed, units_by_i, old, before,
                                 audio_by_i, marks_by_i, fit_by_i, by_i):
                print("   slot %d: rewrite fit worse, kept the old line" % i)
            save_rows(rows)
            if args.translation:
                print("   (retuned rows went to %s; your --translation file "
                      "was left untouched)" % os.path.basename(tpath))

        audios, fits, en_words = [], [], []
        for u in plan["units"]:
            f = fit_by_i[u["i"]]
            audios.append(audio_by_i[u["i"]])
            fits.append(f)
            for w, t0, t1 in marks_by_i[u["i"]]:
                # SOURCE-timeline seconds, so the existing --range/--time-offset
                # path in cut-clips.py needs no special case for a dub
                en_words.append({"text": w,
                                 "start": round(start + u["t0"] + t0, 3),
                                 "end": round(start + u["t0"] + t1, 3),
                                 "probability": 1.0})
            print("   [%2d] slot %5.2fs -> %5.2fs  %-20s %s"
                  % (u["i"], u["dur"], f["final"], f["note"], f["text"][:58]))

        # per-slot marks are monotonic, but a slot that overran its budget can
        # push its last words past the next slot's first -- the same guarantee
        # has to be re-established across slots or the caption builder refuses
        clamped, prev_end = 0, 0.0
        for w in en_words:
            a, b = w["start"], w["end"]
            if a < prev_end:
                a, clamped = prev_end, clamped + 1
            b = max(b, a + 0.01)
            w["start"], w["end"] = round(a, 3), round(b, 3)
            prev_end = b
        if clamped:
            print("   WARNING: nudged %d word mark(s) forward to keep them "
                  "monotonic across slots" % clamped)

        bed = place(plan["units"], audios, plan["duration"])
        raw = "%s.%s.raw.wav" % (stem, tag)
        _tts.write_wav(raw, bed)
        try:
            loudnorm(raw, wav)
        finally:
            if os.path.exists(raw):      # never leave the raw wav for a media
                os.remove(raw)           # player to grab a lock on
        # Same envelope faster-whisper writes, so the caption builder cannot
        # tell a dub transcript from a real one and needs no special case.
        with open(wjson, "w", encoding="utf-8") as f:
            json.dump({"file": wav, "duration": plan["duration"],
                       "language": iso_lang(args.dst_lang),
                       "language_probability": 1.0,
                       "model": "%s/%s" % (backend,
                                           _tts.resolve_voice(voice, backend)),
                       "compute_type": "dub",
                       "text": " ".join(w["text"] for w in en_words),
                       "words": en_words}, f, ensure_ascii=False, indent=2)

        over = [f for f, u in zip(fits, plan["units"]) if f["final"] > u["hard"] + 0.05]
        err = [abs(f["final"] - u["dur"]) for f, u in zip(fits, plan["units"])]
        report = {
            "clip": clip["id"], "start": round(start, 3), "end": round(end, 3),
            "voice": _tts.resolve_voice(voice, backend), "backend": backend,
            "units": len(plan["units"]),
            "sync": round(sync_score(plan["units"], fits, plan["duration"]), 4),
            "slot_error_mean": round(float(np.mean(err)), 3),
            "slot_error_max": round(float(np.max(err)), 3),
            "overruns": len(over),
            "used_tight": sum(1 for f in fits if "tight" in f["note"]),
            "squeezed": sum(1 for f in fits if "squeeze" in f["note"]),
            "tight_missing": sum(1 for r in rows
                                 if not str(r.get("tight", "")).strip()
                                 or r["tight"].strip() == r["text"].strip()),
            "clamped_words": clamped,
            "fits": fits,
        }
        with open(dpath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("   sync %.1f%%  slot error mean %.2fs max %.2fs  tight %d  squeezed %d"
              % (report["sync"] * 100, report["slot_error_mean"],
                 report["slot_error_max"], report["used_tight"], report["squeezed"]))
        print("   %s" % wav)
        _project.record(
            _project.project_id(m, args.manifest), "dub",
            out=wav, script=__file__, argv=sys.argv[1:], kind="dub-audio",
            manifest=args.manifest,
            sidecars={"plan": "%s.%s.plan.json" % (stem, tag),
                      "translation": "%s.%s.translation.json" % (stem, tag),
                      "report": dpath, "words": wjson},
            note="sync %.1f%%, %s/%s" % (report["sync"] * 100, backend,
                                         report["voice"]))


if __name__ == "__main__":
    main()
