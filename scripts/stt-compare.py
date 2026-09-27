#!/usr/bin/env python
"""Measure speech-to-text engines against each other on the same voice notes, and weigh them.

The studio writes out every voice note a visitor records (_stt.py). Which engine does that is a
decision this script prices instead of guessing: every engine hears the same clips, and the
table scores what matters for a voice note --

    accuracy   word error rate against the script that was read          (absolute, 1 - WER)
    names      the names in each clip that came back spelt right         (absolute)
    speed      seconds to answer, per clip                               (relative to the fastest)
    cost       USD per minute of audio                                   (relative to the cheapest)
    robust     no invented words on a clip with no speech, no failures   (absolute)

-- each 0..1, then a weighted total (--weights). Everything lands in --out: results.json (every
answer, word for word) and table.txt.

--make-clips writes a test set to start from: short film briefs read by edge-tts voices in
English, Ukrainian and Spanish, with brand names, one over loud noise and one with no speech at
all, encoded the way browsers record (WebM/Opus like Chrome, MP4/AAC like Safari). A clip is any
audio file with a .txt beside it holding what was said (and an optional .names.txt, one name a
line); add real recordings to the folder the same way.

Invoke as:
    python scripts/stt-compare.py --make-clips temp/stt-compare/clips
    python scripts/stt-compare.py --clips temp/stt-compare/clips --plan
    python scripts/stt-compare.py --clips temp/stt-compare/clips \\
        --engines openrouter:google/gemini-3.8-flash gemini:gemini-3.8-flash whisper:medium
"""

import sys
import os
import json
import time
import asyncio
import argparse
import statistics
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _stt  # noqa: E402

AUDIO = (".webm", ".m4a", ".mp4", ".ogg", ".mp3", ".wav", ".flac")
WEIGHTS = {"accuracy": 40, "names": 15, "speed": 20, "cost": 10, "robust": 15}

# name, edge-tts voice, what is said, names to find, format, noise
CLIPS = [
    (
        "en-bakery",
        "en-US-AriaNeural",
        "Hi! So I want a short ad for my bakery. It's called Sunny Crumbs, we're on Maple "
        "Street. Make it warm and cosy, show fresh croissants coming out of the oven, and end on "
        "our logo. Oh, and please mention that we open at seven every morning.",
        ["Sunny Crumbs", "Maple Street", "croissants"],
        "webm",
        0,
    ),
    (
        "en-brands",
        "en-GB-RyanNeural",
        "Make an explainer about how Instafill fills in PDF forms with AI. Start with a messy "
        "stack of paper on a desk, then Claude Opus reads the form, and every field fills itself "
        "in. Finish with the KitCut logo and the words: paperwork, done.",
        ["Instafill", "PDF", "Claude Opus", "KitCut"],
        "m4a",
        0,
    ),
    (
        "en-long",
        "en-US-GuyNeural",
        "Okay, this one is for my daughter's birthday. She's turning six and she loves "
        "dinosaurs, especially the triceratops, and she has a stuffed one called Mister Pickles. "
        "So the story could be that Mister Pickles goes on an adventure through a jungle, meets a "
        "volcano that is actually friendly, and finds a giant cake at the end. Her name is Amelia, "
        "so maybe the cake says happy birthday Amelia. Keep it gentle, nothing scary, bright "
        "colours, and some happy music. If you can, add a little dance at the end where all the "
        "dinosaurs celebrate together.",
        ["Mister Pickles", "Amelia", "triceratops"],
        "webm",
        0,
    ),
    (
        "uk-story",
        "uk-UA-PolinaNeural",
        "Зроби короткий мультфільм про кота, який мріє навчитися літати. Він стрибає з даху "
        "на дах, а потім знаходить повітряну кульку і нарешті бачить Київ згори. Наприкінці "
        "він повертається додому до своєї господині Оксани.",
        ["Київ", "Оксани"],
        "m4a",
        0,
    ),
    (
        "uk-mixed",
        "uk-UA-OstapNeural",
        "Мені потрібне відео для мого магазину на Etsy. Я продаю керамічні чашки ручної "
        "роботи. Покажи, як чашку ліплять, розписують і випалюють у печі, а в кінці напиши "
        "назву магазину: Глиняна Хата.",
        ["Etsy", "Глиняна Хата"],
        "webm",
        0,
    ),
    (
        "es-travel",
        "es-ES-ElviraNeural",
        "Quiero un vídeo corto sobre un viaje en tren de Madrid a Sevilla. Empieza al amanecer "
        "en la estación de Atocha, pasa por campos de olivos y termina con la Giralda al "
        "atardecer.",
        ["Madrid", "Sevilla", "Atocha", "Giralda"],
        "m4a",
        0,
    ),
    (
        "en-noisy",
        "en-US-JennyNeural",
        "Can you make a film about a lighthouse keeper named Rosa who finds a message in a "
        "bottle? She follows the map to a tiny island where a lost puppy is waiting for her.",
        ["Rosa", "lighthouse", "puppy"],
        "webm",
        0.25,
    ),
    ("silence", None, "", [], "webm", 0.02),
]


def make_clips(out):
    import edge_tts

    os.makedirs(out, exist_ok=True)
    for name, voice, text, names, fmt, noise in CLIPS:
        raw = os.path.join(out, name + ".raw.mp3")
        dst = os.path.join(out, "%s.%s" % (name, fmt))
        if voice:
            asyncio.run(edge_tts.Communicate(text, voice).save(raw))
            src = ["-i", raw]
        else:
            src = ["-f", "lavfi", "-t", "8", "-i", "anullsrc=r=48000:cl=mono"]
        mix = []
        if noise:
            dur = _stt.duration(raw) if voice else 8
            mix = [
                "-f",
                "lavfi",
                "-t",
                "%.2f" % dur,
                "-i",
                "anoisesrc=color=pink:amplitude=%g:r=48000" % noise,
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=first:normalize=0",
            ]
        codec = (
            ["-c:a", "libopus", "-b:a", "32k"] if fmt == "webm" else ["-c:a", "aac", "-b:a", "64k"]
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *src, *mix, "-ac", "1", "-ar", "48000", *codec, dst],
            check=True,
        )
        if os.path.exists(raw):
            os.remove(raw)
        with open(os.path.join(out, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(out, name + ".names.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(names))
        print("  %-10s %5.1fs  %s" % (name, _stt.duration(dst), os.path.relpath(dst, _env.ROOT)))


def load_clips(d):
    clips = []
    for fn in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in AUDIO or not os.path.exists(os.path.join(d, stem + ".txt")):
            continue
        with open(os.path.join(d, stem + ".txt"), encoding="utf-8") as f:
            ref = f.read().strip()
        names = []
        np_ = os.path.join(d, stem + ".names.txt")
        if os.path.exists(np_):
            with open(np_, encoding="utf-8") as f:
                names = [x.strip() for x in f if x.strip()]
        clips.append({"name": stem, "path": os.path.join(d, fn), "ref": ref, "names": names})
    return clips


def found(name, hyp):
    """Is the name in the transcript, word for word (case and punctuation aside)?"""
    n, h = _stt.words(name), _stt.words(hyp)
    return any(h[i : i + len(n)] == n for i in range(len(h) - len(n) + 1)) if n else True


def score(rows, clips, weights):
    """Per engine: the five criteria (0..1) and the weighted total."""
    by = {}
    for r in rows:
        by.setdefault(r["engine"], []).append(r)
    mins = {c["name"]: c["secs"] for c in clips}
    stats = {}
    for eng, rs in by.items():
        ok = [r for r in rs if not r.get("error")]
        speech = [r for r in ok if r["ref"]]
        silent = [r for r in ok if not r["ref"]]
        wer = statistics.mean(r["wer"] for r in speech) if speech else 1.0
        names = [n for r in speech for n in r["names_found"]]
        costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
        audio_min = sum(mins[r["clip"]] for r in ok if r["cost_usd"] is not None) / 60
        invented = sum(len(_stt.words(r["text"])) > 2 for r in silent)
        stats[eng] = {
            "wer": round(wer, 4),
            "names_right": "%d/%d" % (sum(names), len(names)),
            "names": sum(names) / len(names) if names else 0.0,
            "median_s": round(statistics.median(r["seconds"] for r in ok), 2) if ok else None,
            "usd_per_min": round(sum(costs) / audio_min, 5) if costs and audio_min else None,
            "failures": len(rs) - len(ok),
            "invented_on_silence": invented,
            "robust": max(0.0, 1 - (len(rs) - len(ok)) / len(rs) - 0.5 * invented),
        }
    fastest = min((s["median_s"] for s in stats.values() if s["median_s"]), default=1)
    priced = [s["usd_per_min"] for s in stats.values() if s["usd_per_min"] is not None]
    cheapest = max(min(priced, default=0.001), 0.001)  # a free engine does not zero the rest
    total_w = sum(weights.values())
    for s in stats.values():
        crit = {
            "accuracy": max(0.0, 1 - s["wer"]),
            "names": s["names"],
            "speed": fastest / s["median_s"] if s["median_s"] else 0.0,
            "cost": min(1.0, cheapest / max(s["usd_per_min"], 0.001))
            if s["usd_per_min"] is not None
            else 0.5,
            "robust": s["robust"],
        }
        s["criteria"] = {k: round(v, 3) for k, v in crit.items()}
        s["total"] = round(sum(crit[k] * w for k, w in weights.items()) / total_w * 100, 1)
    return stats


def table(stats, weights):
    head = "%-40s %6s %6s %7s %9s %6s %5s %6s" % (
        "engine",
        "total",
        "WER",
        "names",
        "median s",
        "$/min",
        "fail",
        "silent",
    )
    lines = [
        "weights: " + ", ".join("%s %d%%" % (k, w) for k, w in weights.items()),
        "",
        head,
        "-" * len(head),
    ]
    for eng, s in sorted(stats.items(), key=lambda kv: -kv[1]["total"]):
        lines.append(
            "%-40s %6.1f %5.1f%% %7s %9s %6s %5d %6s"
            % (
                eng,
                s["total"],
                s["wer"] * 100,
                s["names_right"],
                s["median_s"],
                "-" if s["usd_per_min"] is None else "%.4f" % s["usd_per_min"],
                s["failures"],
                "ok" if not s["invented_on_silence"] else "INVENTS",
            )
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--make-clips", metavar="DIR", help="write the edge-tts test set here")
    ap.add_argument("--clips", metavar="DIR", help="audio files, each with a .txt of its words")
    ap.add_argument("--engines", nargs="+", default=[], help="kind:model, see _stt.py")
    ap.add_argument(
        "--weights",
        default=",".join("%s=%d" % kv for kv in WEIGHTS.items()),
        help="criterion=weight, comma-separated (default %(default)s)",
    )
    ap.add_argument("--out", default=os.path.join(_env.ROOT, "temp", "stt-compare"))
    ap.add_argument("--plan", action="store_true", help="list clips and engines; call nothing")
    ap.add_argument(
        "--no-gate",
        action="store_true",
        help="ask every engine even about a clip with no speech (measures what it invents)",
    )
    args = ap.parse_args()

    if args.make_clips:
        make_clips(_env.resolve(args.make_clips))
        if not args.clips:
            return
    if not args.clips:
        ap.error("--clips DIR (or --make-clips DIR first)")
    weights = {k: float(v) for k, v in (kv.split("=") for kv in args.weights.split(","))}
    if set(weights) - set(WEIGHTS):
        ap.error("weights are %s" % ", ".join(WEIGHTS))
    clips = load_clips(_env.resolve(args.clips))
    if not clips:
        sys.exit("no clips in %s (audio files with a .txt beside each)" % args.clips)
    os.makedirs(args.out, exist_ok=True)
    norm = os.path.join(args.out, "norm")
    os.makedirs(norm, exist_ok=True)
    for c in clips:
        c["flac"] = os.path.join(norm, c["name"] + ".flac")
        c["secs"] = _stt.normalise(c["path"], c["flac"])
    total = sum(c["secs"] for c in clips)
    print(
        "%d clips, %.0f s of audio; %d engines: %s"
        % (len(clips), total, len(args.engines), ", ".join(args.engines) or "none")
    )
    if args.plan or not args.engines:
        for c in clips:
            print("  %-12s %5.1fs  %s" % (c["name"], c["secs"], c["ref"][:70]))
        print("\n  --plan: nothing transcribed" if args.plan else "\n  name --engines to run")
        return

    rows = []
    for eng in args.engines:
        for c in clips:
            row = {"engine": eng, "clip": c["name"], "ref": c["ref"]}
            try:
                r = _stt.transcribe(c["flac"], eng, gate=not args.no_gate)
                row.update(r)
                row["wer"] = round(_stt.wer(c["ref"], r["text"]), 4) if c["ref"] else None
                row["names_found"] = [found(n, r["text"]) for n in c["names"]]
            except _stt.SttError as e:
                row.update(error=str(e), seconds=None, cost_usd=None, text="")
            rows.append(row)
            print(
                "  %-40s %-12s %s"
                % (
                    eng,
                    c["name"],
                    row.get("error")
                    or "%.1fs  WER %s  %s"
                    % (
                        row["seconds"],
                        "-" if row["wer"] is None else "%.0f%%" % (row["wer"] * 100),
                        (row["text"] or "(nothing)")[:60],
                    ),
                ),
                flush=True,
            )
    stats = score(rows, clips, weights)
    text = table(stats, weights)
    print("\n" + text)
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "when": time.strftime("%Y-%m-%d %H:%M"),
                "weights": weights,
                "stats": stats,
                "rows": rows,
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    with open(os.path.join(args.out, "table.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\n  %s" % os.path.join(args.out, "results.json"))


if __name__ == "__main__":
    main()
