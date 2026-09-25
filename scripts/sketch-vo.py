#!/usr/bin/env python
"""Voice-over for a sketch film: several takes per line, the best one picked, word-timed.

Reads the `vo` block of `projects/<id>/sketch.json`:

    "vo": {"tts": "elevenlabs", "voice": "sarah", "model": "eleven_v3", "takes": 3,
           "tail": "Alright.", "settings": {"stability": 0.5, "similarity_boost": 0.8},
           "hotwords": ["Acme", "BPO"], "lead": 0.6, "gap": 0.35,
           "language": "en", "whisper": "small.en",
           "lines": [{"text": "[warmly] Every BPO starts the same way.", "start": 0.6, "pick": 1}]}

Per line it: renders N takes (cached by text fingerprint, so an edit re-renders only that line),
cuts each take at the silence before a throwaway TAIL word, scores every take with Whisper
against the script, picks the best (or the manifest's "pick"), and places the line on the
film clock (its "start", else lead + gaps). It writes audio/vo/timeline.json (lines, files,
word times from the ElevenLabs character alignment) and the captions next to it.

A film in another language sets "language" (ISO 639-1, e.g. "uk") and a TAIL in that language
("Добре."): an English tail on a Ukrainian line switches the voice's accent for the last words.
Scoring then runs a multilingual Whisper ("whisper", default large-v3 on the GPU).

Why the tail word: eleven_v3 clips the last syllable of most takes (measured: 16 of 18 takes
ended above -30 dBFS). Rendering "line + tail" and cutting in the silence between them gives the
line a sentence-final ending and a clean decay. Only mp3_44100_128 is available below the
Creator tier (192k is a 403).

Voice names resolve through config/elevenlabs-voices.json (dub-tts.py's registry, which refuses
unverified ids before anything is spent). "tts": "edge" is the free draft backend.

Invoke as:
    python scripts/sketch-vo.py --manifest projects/<id>/sketch.json --plan
    python scripts/sketch-vo.py --manifest projects/<id>/sketch.json
    python scripts/sketch-vo.py --manifest projects/<id>/sketch.json --only 3 --retake
    python scripts/sketch-vo.py --manifest projects/<id>/sketch.json --tts edge     (free draft)
"""

import sys
import os
import re
import json
import base64
import hashlib
import difflib
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _project  # noqa: E402
import _sketch  # noqa: E402

SR = _sketch.SR
EL_URL = "https://api.elevenlabs.io/v1/text-to-speech/%s/with-timestamps"
WPS = 2.6  # planning estimate: words per second of unhurried narration


def spoken(text):
    """Script text minus [audio tags]."""
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", text)).strip()


def words_of(text):
    """Comparable words of any script (an a-z class leaves nothing of a Cyrillic line)."""
    t = spoken(text).lower().replace("-", " ").replace("’", "").replace("'", "")
    return re.sub(r"[^\w$ ]", " ", t).split()


def fingerprint(line, vo):
    key = json.dumps(
        [
            line["text"],
            vo.get("voice"),
            vo.get("model"),
            vo.get("tail"),
            vo.get("settings"),
            vo.get("tts"),
        ],
        sort_keys=True,
    )
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:10]


# ------------------------------------------------------------------ synthesis
def el_take(text, voice_id, vo):
    import httpx

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY is not set (put it in .env)")
    r = httpx.post(
        EL_URL % voice_id,
        params={"output_format": vo.get("format", "mp3_44100_128")},
        headers={"xi-api-key": key},
        json={
            "text": text,
            "model_id": vo.get("model", "eleven_v3"),
            "voice_settings": vo.get("settings", {"stability": 0.5, "similarity_boost": 0.8}),
        },
        timeout=300,
    )
    if r.status_code != 200:
        sys.exit("elevenlabs %s: %s" % (r.status_code, r.text[:300]))
    j = r.json()
    return base64.b64decode(j["audio_base64"]), j.get("alignment") or {}


def edge_take(text, voice, dub):
    audio, marks = dub.speak(spoken(text), voice, backend="edge")
    return audio, marks


# ------------------------------------------------------------------ cutting the tail off
def cut_at_tail(x, align, tail):
    """Samples of the line alone, cut in the silence before the tail word. Returns (y, lead, ok)."""
    chars = align.get("characters") or []
    starts = align.get("character_start_times_seconds") or []
    txt = "".join(chars)
    k = txt.rfind(tail.split()[0]) if tail else -1
    w = int(0.01 * SR)
    db = 20 * np.log10(
        np.sqrt(np.convolve(x**2, np.ones(w) / w, "same")[::w]) + 1e-9
    )  # 10 ms frames
    ok = True
    if k >= 0:
        ast = starts[k]
        lo, hi = max(0, int((ast - 1.5) * 100)), min(len(db), int((ast + 0.25) * 100))
        quiet = db[lo:hi] < -55
        runs, s0 = [], None
        for j, q in enumerate(quiet):
            if q and s0 is None:
                s0 = j
            if not q and s0 is not None:
                runs.append((s0, j))
                s0 = None
        if s0 is not None:
            runs.append((s0, len(quiet)))
        runs = [r for r in runs if r[1] - r[0] >= 8]
        if runs:
            cut = (lo + runs[-1][0]) / 100 + 0.08
        else:
            cut, ok = ast - 0.05, False
        y = x[: int(cut * SR)].copy()
    else:
        y, ok = x.copy(), False
    f = min(len(y), int(0.03 * SR))
    y[-f:] *= np.linspace(1, 0, f)
    nz = int(np.argmax(np.abs(y) > 10 ** (-50 / 20)))
    lead = max(0, nz - int(0.05 * SR))
    return y[lead:], lead / SR, ok


def word_times(align, lead, tail):
    """[{text, s, e}] from a character alignment, [tags] and the tail word dropped."""
    chars = align.get("characters") or []
    t0s = align.get("character_start_times_seconds") or []
    t1s = align.get("character_end_times_seconds") or []
    stop = "".join(chars).rfind(tail.split()[0]) if tail else len(chars)
    out, cur, cs, ce, tag = [], "", 0.0, 0.0, False
    for c, a, b in zip(chars[: stop if stop >= 0 else len(chars)], t0s, t1s, strict=False):
        if c == "[":
            tag = True
        if tag:
            tag = c != "]"
            continue
        if c.isspace():
            if cur.strip(" "):
                out.append({"text": cur, "s": round(cs - lead, 3), "e": round(ce - lead, 3)})
            cur = ""
            continue
        if not cur:
            cs = a
        cur += c
        ce = b
    if cur.strip():
        out.append({"text": cur, "s": round(cs - lead, 3), "e": round(ce - lead, 3)})
    return [w for w in out if any(ch.isalnum() for ch in w["text"])]


# ------------------------------------------------------------------ scoring
_WHISPER = None


def _whisper(lang, name):
    """English scores on small.en (CPU, measured fast enough); any other language needs a
    multilingual model -- large-v3 on the GPU by default, CPU if CUDA will not load."""
    global _WHISPER
    if _WHISPER is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        # ctranslate2 loads cuBLAS lazily through PATH (see transcribe-words.py)
        nv = [
            os.path.join(r, "nvidia", p, "bin")
            for r in _env.site_roots()
            if os.path.isdir(os.path.join(r, "nvidia"))
            for p in os.listdir(os.path.join(r, "nvidia"))
        ]
        os.environ["PATH"] = os.pathsep.join(nv + [os.environ.get("PATH", "")])
        from faster_whisper import WhisperModel

        name = name or ("small.en" if lang == "en" else "large-v3")
        if name.endswith(".en"):
            _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
        else:
            try:
                _WHISPER = WhisperModel(name, device="cuda", compute_type="int8_float16")
                _WHISPER.transcribe(np.zeros(SR // 10, dtype=np.float32), language=lang)
            except Exception as e:  # noqa: BLE001 -- no usable GPU: slower, same answer
                print("  whisper %s on CPU (%s)" % (name, str(e)[:80]))
                _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
    return _WHISPER


def whisper_score(path, text, hotwords, lang="en", model=None):
    segs, _ = _whisper(lang, model).transcribe(
        path, language=lang, initial_prompt=", ".join(hotwords) if hotwords else None
    )
    heard = " ".join(s.text for s in segs)
    ref, hyp = words_of(text), words_of(heard)
    return difflib.SequenceMatcher(None, ref, hyp).ratio(), heard.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--plan", action="store_true", help="price the run (characters, credits, layout) and stop"
    )
    ap.add_argument("--only", help="comma list of line numbers (0-based) to (re)process")
    ap.add_argument("--retake", action="store_true", help="discard cached takes for --only lines")
    ap.add_argument("--takes", type=int, help="override vo.takes")
    ap.add_argument("--tts", choices=["elevenlabs", "edge"], help="override vo.tts (edge is free)")
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    vo = dict(m.get("vo") or {})
    if not vo.get("lines"):
        sys.exit("no vo.lines in %s" % m["_path"])
    if args.tts:
        vo["tts"] = args.tts
    tts = vo.get("tts", "elevenlabs")
    takes = args.takes or vo.get("takes", 3 if tts == "elevenlabs" else 1)
    tail = vo.get("tail", "Alright.") if tts == "elevenlabs" else ""
    lines = vo["lines"]
    only = {int(x) for x in args.only.split(",")} if args.only else set(range(len(lines)))
    vdir = os.path.join(m["_audio"], "vo")
    os.makedirs(vdir, exist_ok=True)

    dub = import_module("dub-tts")
    voice = vo.get("voice") or dub.default_voice(tts)
    voice_id = dub.resolve_voice(voice, tts)  # refuses unknown / unverified voices before any spend

    # plan
    chars = sum(len(ln["text"]) + len(tail) + 2 for i, ln in enumerate(lines) if i in only)
    cost = 1.0
    try:
        cost = (
            dub._el_config()
            .get("models", {})
            .get(vo.get("model", "eleven_v3"), {})
            .get("cost_credits_per_character", 1.0)
        )
    except Exception:  # noqa: BLE001 -- the registry is optional for planning
        pass
    t = vo.get("lead", 0.6)
    print(
        "%s  voice=%s (%s)  model=%s  takes=%d"
        % (
            m["_id"],
            voice,
            tts,
            vo.get("model", "eleven_v3") if tts == "elevenlabs" else "edge",
            takes,
        )
    )
    for i, ln in enumerate(lines):
        est = len(words_of(ln["text"])) / WPS
        st = ln.get("start", t)
        print("  %2d  %5.2fs +%4.1fs  %s" % (i, st, est, spoken(ln["text"])[:90]))
        t = st + est + vo.get("gap", 0.35)
    print("  estimated end %.1fs of %.1fs" % (t - vo.get("gap", 0.35), m["duration"]))
    if tts == "elevenlabs":
        print("  %d characters x %d takes = ~%d credits" % (chars, takes, chars * takes * cost))
    if args.plan:
        print("\n  --plan: nothing rendered")
        return

    tl_path = os.path.join(vdir, "timeline.json")
    old = {}
    if os.path.exists(tl_path):
        with open(tl_path, encoding="utf-8") as f:
            old = {L["i"]: L for L in json.load(f).get("lines", [])}

    with _sketch.Stages(
        m, "sketch-vo", ["synth", "trim", "score", "place"], argv=sys.argv[1:]
    ) as st:
        results = {}
        with st("synth"):
            for i, ln in enumerate(lines):
                if i not in only:
                    continue
                fp = fingerprint(ln, {**vo, "tts": tts})
                for k in range(takes):
                    base = os.path.join(vdir, "L%02d_T%d_%s" % (i, k, fp))
                    if args.retake and os.path.exists(base + ".json"):
                        for ext in (".mp3", ".wav", ".json"):
                            if os.path.exists(base + ext):
                                os.remove(base + ext)
                    if os.path.exists(base + ".json"):
                        continue
                    print("  line %d take %d" % (i, k), flush=True)
                    if tts == "elevenlabs":
                        mp3, align = el_take(
                            ln["text"] + ("\n\n" + tail if tail else ""), voice_id, vo
                        )
                        with open(base + ".mp3", "wb") as f:
                            f.write(mp3)
                    else:
                        audio, marks = edge_take(ln["text"], voice, dub)
                        _sketch.write_wav(base + ".wav", audio)
                        align = {"words": [{"text": w, "s": a, "e": b} for w, a, b in marks]}
                    with open(base + ".json", "w", encoding="utf-8") as f:
                        json.dump(align, f)
                results[i] = fp
        cand = {}
        with st("trim"):
            for i, fp in results.items():
                for k in range(takes):
                    base = os.path.join(vdir, "L%02d_T%d_%s" % (i, k, fp))
                    with open(base + ".json", encoding="utf-8") as f:
                        align = json.load(f)
                    src = base + (".mp3" if os.path.exists(base + ".mp3") else ".wav")
                    x = _sketch.decode(src)
                    if "words" in align:  # edge: already a clean line, times in seconds
                        y, lead, ok, words = x, 0.0, True, align["words"]
                    else:
                        y, lead, ok = cut_at_tail(x, align, tail)
                        words = word_times(align, lead, tail)
                    out = base + "_line.wav"
                    _sketch.write_wav(out, y)
                    cand.setdefault(i, []).append(
                        {"take": k, "file": out, "dur": len(y) / SR, "clean": ok, "words": words}
                    )
        with st("score"):
            for i, cs in cand.items():
                for c in cs:
                    c["acc"], c["heard"] = whisper_score(
                        c["file"],
                        lines[i]["text"],
                        vo.get("hotwords", []),
                        _sketch.language(m),
                        vo.get("whisper"),
                    )
                med = float(np.median([c["dur"] for c in cs]))
                for c in cs:
                    # accuracy first, then a clean cut, then the take nearest the median length
                    c["rank"] = (round(c["acc"], 2), c["clean"], -abs(c["dur"] - med))
                pick = lines[i].get("pick")
                best = (
                    next((c for c in cs if c["take"] == pick), None)
                    if pick is not None
                    else max(cs, key=lambda c: c["rank"])
                )
                for c in cs:
                    print(
                        "  L%d T%d  acc %.2f  %5.2fs  %s%s  %s"
                        % (
                            i,
                            c["take"],
                            c["acc"],
                            c["dur"],
                            "clean" if c["clean"] else "HARD-CUT",
                            "  <- picked" if c is best else "",
                            c["heard"][:70],
                        )
                    )
                results[i] = best
        with st("place"):
            t = vo.get("lead", 0.6)
            placed = []
            for i, ln in enumerate(lines):
                if i in results:
                    b = results[i]
                    L = {
                        "i": i,
                        "text": spoken(ln["text"]),
                        "take": b["take"],
                        "acc": round(b["acc"], 3),
                        "file": os.path.relpath(b["file"], _env.ROOT).replace("\\", "/"),
                        "dur": round(b["dur"], 3),
                    }
                    words = b["words"]
                elif i in old:
                    L = {k: v for k, v in old[i].items() if k not in ("start", "end", "words")}
                    words = [
                        {
                            "text": w["text"],
                            "s": w["s"] - old[i]["start"],
                            "e": w["e"] - old[i]["start"],
                        }
                        for w in old[i]["words"]
                    ]
                else:
                    sys.exit("line %d has no take yet -- run without --only first" % i)
                start = float(ln.get("start", t))
                if i and start < t - vo.get("gap", 0.35) + 0.15:
                    print(
                        "  line %d: start %.2fs overlaps line %d; moved to %.2fs"
                        % (i, start, i - 1, t)
                    )
                    start = t
                L["start"], L["end"] = round(start, 3), round(start + L["dur"], 3)
                L["words"] = [
                    {
                        "text": w["text"],
                        "s": round(start + w["s"], 3),
                        "e": round(start + w["e"], 3),
                    }
                    for w in words
                ]
                placed.append(L)
                t = L["end"] + vo.get("gap", 0.35)
            if t - vo.get("gap", 0.35) > m["duration"]:
                print(
                    "  WARNING: voice ends at %.2fs, after the film's %.1fs"
                    % (t - vo.get("gap", 0.35), m["duration"])
                )
            timeline = {"duration": m["duration"], "voice": voice, "tts": tts, "lines": placed}
            with open(tl_path, "w", encoding="utf-8") as f:
                json.dump(timeline, f, indent=1)
            srt, vtt = _sketch.write_captions(
                timeline,
                os.path.join(m["_outputs"], _sketch.slug(m)),
                m.get("captions", {}).get("max_words", 9),
            )
            for L in placed:
                print(
                    "  %2d  %6.2f-%6.2f  %s"
                    % (
                        L["i"],
                        L["start"],
                        L["end"],
                        " ".join("%s@%.2f" % (w["text"], w["s"]) for w in L["words"][:6]) + " ...",
                    )
                )

    _project.record(
        m["_id"],
        "sketch voice-over timed",
        out=tl_path,
        script=__file__,
        argv=sys.argv[1:],
        kind="vo-timeline",
        manifest=m["_path"],
        sidecars={"srt": srt, "vtt": vtt},
    )


if __name__ == "__main__":
    main()
