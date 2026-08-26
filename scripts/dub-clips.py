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

    python scripts/dub-clips.py --manifest config/clips/<id>-vertical.json \
        --only 01-silver-button
"""
import sys, os, json, argparse, subprocess, math
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

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
def _stretch(x, factor):
    """Time-scale audio by `factor` without moving pitch (rubberband)."""
    if abs(factor - 1.0) < 1e-3 or x.size == 0:
        return x
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
         "-i", "pipe:0", "-filter:a", "rubberband=tempo=%.6f" % (1.0 / factor),
         "-f", "f32le", "pipe:1"],
        input=x.astype(np.float32).tobytes(), capture_output=True, env=ENV)
    if p.returncode:
        return x
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def fit_unit(u, tr, voice, max_rate=25.0, hard_rate=40.0, slow_rate=-18.0):
    """Render one slot so it lands inside it. Returns (audio, marks, fit)."""
    slot, hard = u["dur"], u["hard"]
    audio, marks = _tts.speak(tr["text"], voice)
    nat = audio.size / float(SR)
    note, rate, text = "natural", 0.0, tr["text"]

    if nat > hard:
        # too long: ask the voice to speak faster before touching the waveform
        rate = min(max_rate, _tts.rate_for(nat, hard))
        audio, marks = _tts.speak(text, voice, rate)
        note = "rate%+.0f%%" % rate
        if audio.size / float(SR) > hard and tr.get("tight") and tr["tight"] != text:
            text = tr["tight"]
            audio, marks = _tts.speak(text, voice)
            nat2 = audio.size / float(SR)
            note = "tight"
            if nat2 > hard:
                rate = min(hard_rate, _tts.rate_for(nat2, hard))
                audio, marks = _tts.speak(text, voice, rate)
                note = "tight+rate%+.0f%%" % rate
    elif nat < slot * 0.80:
        # too short: her mouth is still moving, so draw the delivery out rather
        # than leaving a hole of silence under a talking face
        rate = max(slow_rate, _tts.rate_for(nat, slot))
        audio, marks = _tts.speak(text, voice, rate)
        note = "rate%+.0f%%" % rate

    got = audio.size / float(SR)
    if got > hard:                       # last resort, kept small on purpose
        f = hard / got
        if f > 0.82:
            audio = _stretch(audio, f)
            marks = [(w, a * f, b * f) for w, a, b in marks]
            note += "+squeeze%.0f%%" % ((1 - f) * 100)
    return audio, marks, {"note": note, "rate": round(rate, 1), "text": text,
                          "natural": round(nat, 3),
                          "final": round(audio.size / float(SR), 3)}


# --------------------------------------------------------------------- mixing
def place(units, audios, total):
    """Lay each unit onto a silent bed at the time the original phrase began."""
    bed = np.zeros(int(math.ceil(total * SR)) + SR // 10, dtype=np.float32)
    fade = int(0.005 * SR)
    for u, a in zip(units, audios):
        if a.size == 0:
            continue
        a = a.copy()
        if a.size > 2 * fade:            # no clicks at the splice points
            a[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            a[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        i = int(round(u["t0"] * SR))
        j = min(bed.size, i + a.size)
        bed[i:j] += a[:j - i]
    return bed[:int(math.ceil(total * SR))]


def loudnorm(src, dst, lufs=-14.5):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af",
                        "loudnorm=I=%.1f:TP=-1.5:LRA=11" % lufs,
                        "-ar", str(SR), "-ac", "1", dst], env=ENV)
    if r.returncode:
        sys.exit("loudness normalisation failed for %s" % src)


def sync_score(units, fits, total, step=0.01):
    """Share of the clip where dub and original agree that someone is talking.

    This is the number the whole design is chasing: it drops when the dub talks
    over a pause, and when it falls silent under a moving mouth.
    """
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
    ap.add_argument("--voice", default=_tts.DEFAULT_VOICE)
    ap.add_argument("--engine", default="claude",
                    choices=["claude", "openai", "manual"])
    ap.add_argument("--translation", help="manual engine: a translation json to use")
    ap.add_argument("--src-lang", default="Ukrainian")
    ap.add_argument("--dst-lang", default="English")
    ap.add_argument("--max-dur", type=float, default=4.0,
                    help="longest speech unit before it is split again")
    ap.add_argument("--min-dur", type=float, default=0.9)
    ap.add_argument("--words-per-sec", type=float, default=3.2)
    ap.add_argument("--tune-rounds", type=int, default=1,
                    help="rounds of measure-then-rewrite for slots that do not fit")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--retranslate", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    m = json.load(open(args.manifest, encoding="utf-8"))
    words = _outline.load_words(m["words"])
    pad = m.get("pad", {})
    pad_head, pad_tail = float(pad.get("head", 0.12)), float(pad.get("tail", 0.30))
    prefix = m.get("prefix", "")
    os.makedirs(args.outdir, exist_ok=True)
    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None

    for clip in m["clips"]:
        if wanted and clip["id"] not in wanted:
            continue
        # the SAME resolver the video cut uses, so audio and picture agree to the
        # millisecond about where this clip starts
        start, end = _cut.resolve(clip, words, pad_head, pad_tail)
        stem = os.path.join(args.outdir,
                            ("%s-%s" % (prefix, clip["id"])) if prefix else clip["id"])
        wav, wjson = stem + ".en.wav", stem + ".en.words.json"
        if os.path.exists(wav) and not args.force:
            print("skip (exists) %s" % wav)
            continue

        print("== %s  %.2f-%.2f (%.2fs)" % (clip["id"], start, end, end - start))
        plan = build_plan(clip, words, start, end, args.max_dur, args.min_dur)
        json.dump(plan, open(stem + ".plan.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        durs = sorted(u["dur"] for u in plan["units"])
        print("   %d speech units, median %.2fs, longest %.2fs"
              % (len(durs), durs[len(durs) // 2], durs[-1]))
        if args.plan_only:
            continue

        tpath = stem + ".translation.json"
        if args.translation:
            rows = json.load(open(args.translation, encoding="utf-8"))
        elif os.path.exists(tpath) and not args.retranslate:
            rows = json.load(open(tpath, encoding="utf-8"))
            print("   reusing %s" % os.path.basename(tpath))
        else:
            rows = _tr.translate(plan["units"], plan["context"], args.engine,
                                 args.src_lang, args.dst_lang, args.words_per_sec)
            json.dump(rows, open(tpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        by_i = {int(r["i"]): r for r in rows}
        units_by_i = {u["i"]: u for u in plan["units"]}
        for u in plan["units"]:
            if u["i"] not in by_i:
                sys.exit("%s: no translation for slot %d" % (clip["id"], u["i"]))

        audio_by_i, marks_by_i, fit_by_i = {}, {}, {}

        def render(indices):
            for i in indices:
                (audio_by_i[i], marks_by_i[i],
                 fit_by_i[i]) = fit_unit(units_by_i[i], by_i[i], args.voice)

        render([u["i"] for u in plan["units"]])

        # How long a sentence takes to say is a guess until you say it. Now that
        # every slot has been timed, hand the measurements back to the translator
        # and re-render only what it changed -- a line that came up short leaves
        # dead air under a moving mouth, which reads worse than a slightly long one.
        for rnd in range(args.tune_rounds):
            fits_now = [fit_by_i[u["i"]] for u in plan["units"]]
            before = {i: by_i[i]["text"] for i in by_i}
            rows, n = _tr.retune(plan["units"], fits_now, rows, plan["context"],
                                 args.engine, args.src_lang, args.dst_lang,
                                 args.words_per_sec)
            if not n:
                break
            by_i = {int(r["i"]): r for r in rows}
            changed = [i for i in sorted(by_i) if by_i[i]["text"] != before.get(i)]
            if not changed:
                break
            print("   round %d: re-rendering %d slot(s)" % (rnd + 1, len(changed)))
            render(changed)
            json.dump(rows, open(tpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)

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

        bed = place(plan["units"], audios, plan["duration"])
        raw = stem + ".raw.wav"
        _tts.write_wav(raw, bed)
        loudnorm(raw, wav)
        os.remove(raw)
        # Same envelope faster-whisper writes, so the caption builder cannot
        # tell a dub transcript from a real one and needs no special case.
        json.dump({"file": wav, "duration": plan["duration"],
                   "language": args.dst_lang[:2].lower(),
                   "language_probability": 1.0,
                   "model": "edge-tts/%s" % _tts.resolve_voice(args.voice),
                   "compute_type": "dub",
                   "text": " ".join(w["text"] for w in en_words),
                   "words": en_words},
                  open(wjson, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

        over = [f for f, u in zip(fits, plan["units"]) if f["final"] > u["hard"] + 0.05]
        err = [abs(f["final"] - u["dur"]) for f, u in zip(fits, plan["units"])]
        report = {
            "clip": clip["id"], "start": round(start, 3), "end": round(end, 3),
            "voice": _tts.resolve_voice(args.voice), "units": len(plan["units"]),
            "sync": round(sync_score(plan["units"], fits, plan["duration"]), 4),
            "slot_error_mean": round(float(np.mean(err)), 3),
            "slot_error_max": round(float(np.max(err)), 3),
            "overruns": len(over),
            "used_tight": sum(1 for f in fits if "tight" in f["note"]),
            "squeezed": sum(1 for f in fits if "squeeze" in f["note"]),
            "fits": fits,
        }
        json.dump(report, open(stem + ".dub.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("   sync %.1f%%  slot error mean %.2fs max %.2fs  tight %d  squeezed %d"
              % (report["sync"] * 100, report["slot_error_mean"],
                 report["slot_error_max"], report["used_tight"], report["squeezed"]))
        print("   %s" % wav)


if __name__ == "__main__":
    main()
