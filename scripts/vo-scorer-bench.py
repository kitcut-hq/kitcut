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
vo_mod.FALLBACK = False  # a service that fails must not be scored as the local model in disguise


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
    ap.add_argument(
        "--reference", help="the referee every scorer is compared with (default: the film's)"
    )
    ap.add_argument("--bad", type=float, default=0.9, help="accuracy under which a take is bad")
    ap.add_argument("-v", "--verbose", action="store_true", help="list each disagreement")
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
    for s in [args.reference] + args.scorer if args.reference else args.scorer:
        if s in report:
            continue
        os.environ["SKETCH_SCORER"] = s

        def one(L, s=s):
            path = os.path.join(m["_dir"], L["file"])
            t0 = time.time()
            acc, heard, ws = vo_mod.whisper_score(path, L["text"], hot, lang, s, words=True)
            words = [w["s"] for w in vo_mod.align_words(L["text"], ws)]
            return {"i": L["i"], "acc": acc, "heard": heard, "starts": words, "s": time.time() - t0}

        t0 = time.time()
        n = args.jobs if vo_mod.remote(s) else 1
        try:
            with ThreadPoolExecutor(max_workers=n) as pool:
                rows = list(pool.map(one, lines))
        except RuntimeError as e:  # e.g. a model that gives no word times, or a refused provider
            print("  %s cannot be measured: %s" % (s, str(e)[:160]))
            continue
        report[s] = {"wall": time.time() - t0, "rows": rows, "n": n}
    # the film itself: what the scorer it was made with heard
    report["film"] = {
        "wall": None,
        "n": 1,
        "rows": [
            {
                "i": L["i"],
                "acc": L["acc"],
                "heard": "",
                "starts": [w["s"] - L["start"] for w in L["words"]],
                "s": 0,
            }
            for L in lines
        ],
    }
    ref_name = args.reference or "film"
    ref = {r["i"]: r for r in report[ref_name]["rows"]}
    bad_ref = {i for i, r in ref.items() if r["acc"] < args.bad}
    onsets = {L["i"]: onset(os.path.join(m["_dir"], L["file"])) for L in lines}
    print(
        "\nreferee: %s -- %d of %d takes under %.2f"
        % (ref_name, len(bad_ref), len(lines), args.bad)
    )
    print(
        "  %-46s %7s %6s %6s %6s %8s %8s %8s %7s"
        % ("scorer", "wall s", "acc", "missed", "extra", "|dt| med", "p95", ">0.2s", "onset")
    )
    for s, rep in report.items():
        rows = rep["rows"]
        d, lead = [], []
        for r in rows:
            a = ref[r["i"]]["starts"]
            if len(a) == len(r["starts"]):
                d += [abs(x - y) for x, y in zip(a, r["starts"])]
            if r["starts"]:
                lead.append(r["starts"][0] - onsets[r["i"]])
        d = np.array(d or [0.0])
        bad = {r["i"] for r in rows if r["acc"] < args.bad}
        print(
            "  %-46s %7s %6.3f %6d %6d %8.3f %8.3f %7.1f%% %+7.3f"
            % (
                s[:46],
                "%.1f" % rep["wall"] if rep["wall"] is not None else "--",
                np.mean([r["acc"] for r in rows]),
                len(bad_ref - bad),
                len(bad - bad_ref),
                np.median(d),
                np.percentile(d, 95),
                100 * (d > 0.2).mean(),
                np.median(lead),
            )
        )
        if args.verbose and s != ref_name:
            for r in rows:
                if (r["i"] in bad_ref) != (r["i"] in bad):
                    L = next(x for x in lines if x["i"] == r["i"])
                    print(
                        "      L%02d %s  %.2f (ref %.2f)  script: %s\n            heard: %s"
                        % (
                            r["i"],
                            "MISSED" if r["i"] in bad_ref else "extra ",
                            r["acc"],
                            ref[r["i"]]["acc"],
                            L["text"][:80],
                            r["heard"][:80],
                        )
                    )
    print(
        "\n  missed: takes the referee calls bad that this one passes (a bad line ships);"
        "\n  extra: takes it calls bad that the referee passes (a needless re-recording);"
        "\n  |dt|: word starts against the referee's; onset: first word minus where the sound"
        "\n  begins (median). film: what the film was made with (its timeline.json)."
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
