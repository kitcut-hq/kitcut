#!/usr/bin/env python
"""Measure a narration scorer against the one a film was made with: speed, accuracy, word times.

sketch-vo.py listens to every Gemini take twice over: how close it came to the script (a garbled
take scores low and gets re-recorded) and when each word was said (the film's cues hang off those
times). This re-scores a finished film's picked takes with each candidate scorer and compares it
with what the film's audio/vo/timeline.json already says.

Invoke as:

    python scripts/vo-scorer-bench.py --manifest projects/<id>/sketch.json --plan \\
        --scorer openrouter:openai/whisper-large-v3-turbo --scorer openrouter:deepgram/nova-3
    python scripts/vo-scorer-bench.py --manifest projects/<id>/sketch.json --jobs 8 \\
        --scorer openrouter:openai/whisper-large-v3-turbo --scorer small.en

A scorer is what sketch-vo.py's "whisper" / SKETCH_SCORER takes: "openrouter:<model>" (a
transcription model OpenRouter serves) or a local faster-whisper model name. Per scorer it prints
the wall time, what it cost, the lines whose accuracy moved by more than --flag (with both
hearings, so a misheard brand name reads differently from a garbled take), and how far its word
starts sit from the film's (median and 95th percentile). --plan prices it and spends nothing.
"""

import argparse
import difflib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _sketch  # noqa: E402

vo_mod = import_module("sketch-vo")


def onset(path, floor_db=-35.0):
    """Seconds to the take's first 10 ms frame within floor_db of its loudest: where the first
    word's sound begins, the one word time the audio itself can vouch for."""
    x = _sketch.decode(path)
    n = len(x) // 480
    rms = np.sqrt((x[: n * 480].reshape(n, 480) ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms / rms.max())
    hit = np.nonzero(db > floor_db)[0]
    return float(hit[0]) * 480 / _sketch.SR if len(hit) else 0.0


def price_per_second(model):
    """USD per audio second for an OpenRouter transcription model (its listed prompt price is
    per second of audio); None when it is priced per token or not found."""
    import httpx

    r = httpx.get(
        "https://openrouter.ai/api/v1/models", params={"output_modalities": "transcription"}
    )
    for m in r.json().get("data", []):
        if m["id"] == model:
            p = m.get("pricing", {})
            if p.get("completion") not in (None, "0"):
                return None
            pps = float(p.get("prompt", 0))
            # Microsoft's MAI models list a price per HOUR there ($0.10 = MAI-Transcribe 2's
            # published $0.10/hour); nothing real costs a cent per second
            return pps / 3600 if pps > 0.01 else pps
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--scorer", action="append", required=True, help="repeatable")
    ap.add_argument("--jobs", type=int, default=8, help="takes scored at once by a service")
    ap.add_argument("--lines", type=int, help="only the first N lines")
    ap.add_argument("--flag", type=float, default=0.1, help="accuracy change worth listing")
    ap.add_argument("--plan", action="store_true", help="price each scorer and stop")
    ap.add_argument("--out", help="write every hearing here as JSON")
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    with open(os.path.join(m["_dir"], "audio", "vo", "timeline.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"][: args.lines]
    lang = _sketch.language(m)
    hot = m["vo"].get("hotwords", [])
    secs = sum(L["dur"] for L in lines)
    print("%d lines, %.0f s of narration, language %s" % (len(lines), secs, lang))
    for s in args.scorer:
        if vo_mod.remote(s):
            pps = price_per_second(s.split(":", 1)[1])
            cost = "$%.4f" % (pps * secs) if pps is not None else "priced per token"
            print("  %-50s  %s" % (s, cost))
        else:
            print("  %-50s  free (this machine's CPU/GPU)" % s)
    if args.plan:
        print("\n  --plan: nothing scored")
        return

    report = {}
    for s in args.scorer:
        os.environ["SKETCH_SCORER"] = s

        def one(L):
            path = os.path.join(m["_dir"], L["file"])
            t0 = time.time()
            acc, heard, ws = vo_mod.whisper_score(path, L["text"], hot, lang, s, words=True)
            return acc, heard, ws, time.time() - t0

        t0 = time.time()
        n = args.jobs if vo_mod.remote(s) else 1
        with ThreadPoolExecutor(max_workers=n) as pool:
            got = list(pool.map(one, lines))
        wall = time.time() - t0
        moved, starts, rows, lead, lead_film = [], [], [], [], []
        for L, (acc, heard, ws, took) in zip(lines, got):
            words = vo_mod.align_words(L["text"], ws)
            ref = [w["s"] - L["start"] for w in L["words"]]
            mine = [w["s"] for w in words]
            if len(ref) == len(mine):
                starts += [b - a for a, b in zip(ref, mine)]
            # the ground truth both can be held to: where the take's sound actually begins
            on = onset(os.path.join(m["_dir"], L["file"]))
            if mine and ref:
                lead.append(mine[0] - on)
                lead_film.append(ref[0] - on)
            if abs(acc - L["acc"]) > args.flag:
                moved.append((L["i"], L["acc"], acc, heard))
            rows.append({"i": L["i"], "acc": acc, "was": L["acc"], "heard": heard, "s": took})
        report[s] = rows
        sd = np.array(starts) if starts else np.zeros(1)
        d = np.abs(sd)
        low_was = sum(1 for L in lines if L["acc"] < 0.9)
        low_now = sum(1 for r in rows if r["acc"] < 0.9)
        print("\n== %s" % s)
        print(
            "  wall %.1f s (%d at once), per take median %.2f s"
            % (wall, n, float(np.median([r["s"] for r in rows])))
        )
        print(
            "  accuracy: mean %.3f (film %.3f); under 0.9: %d lines (film %d)"
            % (
                np.mean([r["acc"] for r in rows]),
                np.mean([L["acc"] for L in lines]),
                low_now,
                low_was,
            )
        )
        print(
            "  word starts vs the film: median %.3f s, p95 %.3f s, max %.3f s (%d words)"
            % (np.median(d), np.percentile(d, 95), d.max(), len(starts))
        )
        print("  its words run %+.3f s from the film's (median, signed)" % np.median(sd))
        print(
            "  first word vs the sound's onset: this %+.3f s, the film's %+.3f s (median; "
            "|x| p90 %.3f vs %.3f)"
            % (
                np.median(lead),
                np.median(lead_film),
                np.percentile(np.abs(lead), 90),
                np.percentile(np.abs(lead_film), 90),
            )
        )
        for i, was, acc, heard in moved:
            ref = next(L for L in lines if L["i"] == i)
            print("  L%02d  %.2f -> %.2f  script: %s" % (i, was, acc, ref["text"][:90]))
            print("             heard: %s" % heard[:90])
            diff = [
                t
                for t in difflib.ndiff(vo_mod.words_of(ref["text"]), vo_mod.words_of(heard))
                if t[0] in "+-"
            ]
            print("             diff:  %s" % " ".join(diff)[:120])
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
