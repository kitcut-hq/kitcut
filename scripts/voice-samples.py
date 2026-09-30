#!/usr/bin/env python
"""Record a short sample of each of KitCut's narrator voices, for the site's voice picker.

kitcut.ai lets a person pin one of the studio's Gemini voices as a project's narrator (the site's
voices/catalog.json, the studio's GEMINI_VOICES); the picker plays a sample of each so the choice
is made by ear. This records them with the studio's own path (sketch-vo.py gemini_take, with no
voice direction, the model the studio narrates with), levels every clip to the same loudness so
the voices compare fairly (sketch-vo.py level_to, the narration's own level), and encodes it small.

Writes, under projects/voice-samples/:
    outputs/<model>/<lang>/<Voice>.mp3   one clip a voice, 64 kbps mono
    outputs/<model>/<lang>/index.json    {voice, lang, text, seconds, model, cost_usd} each
    outputs/<model>/<lang>/index.html    every clip on one page, to listen through before shipping
The site takes the English clips as its voices/<Voice>.mp3 (a copy, committed there).

A clip already recorded for the same model, voice and text is kept, so a rerun pays only for what
changed (--retake records again). --plan prices the run and records nothing.

Invoke as:
    python scripts/voice-samples.py --plan
    python scripts/voice-samples.py [--lang en] [--model gemini-3.8-flash-tts] [--only Kore,Puck]
"""

import sys
import os
import json
import time
import hashlib
import argparse
import subprocess
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402

import numpy as np  # noqa: E402

vo = import_module("sketch-vo")

PROJECT = "voice-samples"
CONFIG = _env.resolve("config/sketch/voice-samples.json")
# what an 8 s clip costs, in tokens (measured on Gemini TTS: ~25 audio tokens a second, and the
# prompt is the sentence itself)
TOKENS_IN, TOKENS_OUT = 30, 200


def clip_key(model, voice, text):
    return hashlib.sha1(
        ("%s|%s|%s" % (model, voice, text)).encode(), usedforsecurity=False
    ).hexdigest()[:12]


def encode(samples, sr, out):
    """Float samples -> a 64 kbps mono MP3, through ffmpeg's stdin."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "s16le",
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-b:a",
            "64k",
            "-ac",
            "1",
            out,
        ],
        input=pcm,
        check=True,
    )


def page(rows, title):
    items = "\n".join(
        "<figure><figcaption><b>%s</b> &middot; %.1f s</figcaption>"
        '<audio controls preload="none" src="%s.mp3"></audio></figure>'
        % (r["voice"], r["seconds"], r["voice"])
        for r in rows
    )
    return (
        "<!doctype html><meta charset=utf-8><title>%s</title>"
        "<style>body{font:15px system-ui;max-width:760px;margin:32px auto;padding:0 16px}"
        "figure{margin:0 0 14px}figcaption{margin-bottom:4px}audio{width:100%%}</style>"
        "<h1>%s</h1>%s" % (title, title, items)
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--lang", default="en", help="the sample's language (a key of the config's text)"
    )
    ap.add_argument(
        "--model",
        default=None,
        help="Gemini TTS model (default: the studio's, STUDIO_TTS_MODEL or sketch-vo's)",
    )
    ap.add_argument("--only", default="", help="comma-separated voices (default: all 30)")
    ap.add_argument("--plan", action="store_true", help="price it; record nothing")
    ap.add_argument("--retake", action="store_true", help="record again even when a clip is there")
    a = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        text = json.load(f)["text"].get(a.lang)
    if not text:
        sys.exit("no sample text for %r in %s" % (a.lang, CONFIG))
    model = a.model or os.environ.get("STUDIO_TTS_MODEL") or "gemini-3.8-flash-tts"
    voices = [v for v in vo.GEMINI_VOICES if not a.only or v in a.only.split(",")]
    unknown = set(filter(None, a.only.split(","))) - set(vo.GEMINI_VOICES)
    if unknown:
        sys.exit("not KitCut voices: %s" % ", ".join(sorted(unknown)))
    out = os.path.join(_project.projects_dir(), PROJECT, "outputs", model, a.lang)
    idx_path = os.path.join(out, "index.json")
    try:
        with open(idx_path, encoding="utf-8") as f:
            index = {r["voice"]: r for r in json.load(f)}
    except (OSError, ValueError):
        index = {}
    todo = [
        v
        for v in voices
        if a.retake
        or index.get(v, {}).get("key") != clip_key(model, v, text)
        or not os.path.exists(os.path.join(out, v + ".mp3"))
    ]
    price_in, price_out = vo.GEMINI_PRICES.get(model, (1.0, 20.0))
    each = (TOKENS_IN * price_in + TOKENS_OUT * price_out) / 1e6
    print(
        "%d voice(s), %d to record with %s in %s: about $%.3f (%s)"
        % (len(voices), len(todo), model, a.lang, each * len(todo), text)
    )
    if a.plan:
        return

    os.makedirs(out, exist_ok=True)
    spent = 0.0
    for v in todo:
        t0 = time.time()
        samples, meta = vo.gemini_take(text, {"model": model, "voice": v, "style": ""})
        samples = vo.level_to(np.asarray(samples, dtype=np.float32), vo.BACKUP_LEVEL_DB)
        encode(samples, vo.SR, os.path.join(out, v + ".mp3"))
        spent += meta.get("cost_usd") or 0
        index[v] = {
            "voice": v,
            "lang": a.lang,
            "text": text,
            "model": model,
            "seconds": round(len(samples) / vo.SR, 2),
            "cost_usd": round(meta.get("cost_usd") or 0, 6),
            "key": clip_key(model, v, text),
        }
        print("  %-14s %.1f s  (%.1f s to record)" % (v, index[v]["seconds"], time.time() - t0))
    rows = [index[v] for v in vo.GEMINI_VOICES if v in index]
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(rows, "KitCut voices: %s, %s" % (model, a.lang)))
    print("recorded %d, $%.4f; listen: %s" % (len(todo), spent, os.path.join(out, "index.html")))
    _project.record(
        PROJECT,
        "voice samples recorded",
        out=os.path.join(out, "index.html"),
        script="voice-samples.py",
        argv=sys.argv[1:],
        kind="audio",
        note="%d clips, %s, %s; the site copies the English ones to voices/"
        % (len(rows), model, a.lang),
    )


if __name__ == "__main__":
    main()
