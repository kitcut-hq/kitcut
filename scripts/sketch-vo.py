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

"tts": "gemini" is Google's Gemini text-to-speech. "model" (default gemini-3.8-flash-tts),
"voice" (a Gemini voice: Kore, Leda, Puck, Aoede, ...), and "style" (how to say it, e.g. "warm
and gentle, like a kind teacher talking to young children"). It needs no tail word and gives no
timings, so the word times come from Whisper's word timestamps on the take, matched back to the
script. Auth is the service account in GOOGLE_SERVICE_ACCOUNT_KEY (base64 JSON), or
GEMINI_API_KEY for the Gemini API. The 2.5 and 3.1 models go through Vertex AI (GOOGLE_CLOUD_LOCATION,
default global); the 3.8 models through the Gemini API (generativelanguage.googleapis.com), which
must be enabled in the service account's project. The timeline records each line's tokens and
what they cost.

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
import atexit
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _gpulock  # noqa: E402
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
        ]
        + ([vo.get("style")] if vo.get("style") else []),  # gemini's voice direction
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


# Gemini TTS: USD per 1M tokens (text in, audio out; 25 audio tokens a second), the Gemini API's
# list prices as published 2026-09 (ai.google.dev/gemini-api/docs/pricing); 3.8 is at its 2026
# introductory price, which doubles on 2027-01-01.
GEMINI_PRICES = {
    "gemini-3.8-flash-tts": (0.50, 9.00),
    "gemini-3.8-flash-lite-tts": (0.50, 6.00),
    "gemini-3.1-flash-tts-preview": (1.00, 20.00),
    "gemini-2.5-flash-tts": (0.50, 10.00),
    "gemini-2.5-flash-preview-tts": (0.50, 10.00),
    "gemini-2.5-pro-tts": (1.00, 20.00),
    "gemini-2.5-pro-preview-tts": (1.00, 20.00),
}
GEMINI_VERTEX = {  # what Vertex AI serves (measured 2026-09-25); anything else: the Gemini API
    "gemini-2.5-flash-tts",
    "gemini-2.5-pro-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-3.1-flash-tts-preview",
}
GEMINI_VOICES = (
    "Zephyr Puck Charon Kore Fenrir Leda Orus Aoede Callirrhoe Autonoe Enceladus Iapetus Umbriel "
    "Algieba Despina Erinome Algenib Rasalgethi Laomedeia Achernar Alnilam Schedar Gacrux "
    "Pulcherrima Achird Zubenelgenubi Vindemiatrix Sadachbia Sadaltager Sulafat"
).split()
GEMINI_SR = 24000


def _google_creds(scopes):
    from google.oauth2 import service_account

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip()
    if not raw:
        return None, None
    info = json.loads(base64.b64decode(raw) if not raw.startswith("{") else raw)
    return service_account.Credentials.from_service_account_info(info, scopes=scopes), info


def gemini_take(text, vo):
    """One line from Gemini TTS. Returns (samples float at SR, {model, voice, usage, cost_usd})."""
    from scipy.signal import resample_poly

    model = vo.get("model") or "gemini-3.8-flash-tts"
    voice = vo.get("voice") or "Kore"
    if voice not in GEMINI_VOICES:
        sys.exit("gemini voice %r is not one of: %s" % (voice, ", ".join(GEMINI_VOICES)))
    words = spoken(text)
    style = (vo.get("style") or "").strip()
    speech = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}
    if model in GEMINI_VERTEX:
        # the older models take direction in the prompt itself, and do not read it aloud
        from google import genai
        from google.genai import types

        creds, info = _google_creds(["https://www.googleapis.com/auth/cloud-platform"])
        if not creds:
            sys.exit("GOOGLE_SERVICE_ACCOUNT_KEY is not set (Vertex AI needs the service account)")
        client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT") or info["project_id"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
            credentials=creds,
        )
        r = client.models.generate_content(
            model=model,
            contents=("%s: %s" % (style, words)) if style else words,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )
        pcm = r.candidates[0].content.parts[0].inline_data.data
        u = r.usage_metadata
        usage = {"input": u.prompt_token_count or 0, "output": u.candidates_token_count or 0}
    else:
        # the Gemini API: 3.8 reads its input as a verbatim transcript, so the direction goes
        # in as a system instruction instead of being prefixed to the words
        import httpx

        body = {
            "contents": [{"parts": [{"text": words}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech},
        }
        if style:
            body["systemInstruction"] = {"parts": [{"text": "Voice direction: " + style}]}
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            headers = {"x-goog-api-key": key}
        else:
            from google.auth.transport.requests import Request

            creds, info = _google_creds(
                [
                    "https://www.googleapis.com/auth/generative-language",
                    "https://www.googleapis.com/auth/cloud-platform",
                ]
            )
            if not creds:
                sys.exit("set GEMINI_API_KEY or GOOGLE_SERVICE_ACCOUNT_KEY for Gemini TTS")
            creds.refresh(Request())
            headers = {
                "Authorization": "Bearer " + creds.token,
                "x-goog-user-project": os.environ.get("GOOGLE_CLOUD_PROJECT") or info["project_id"],
            }
        r = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
            headers=headers,
            json=body,
            timeout=180,
        )
        if r.status_code != 200:
            sys.exit("gemini %s %s: %s" % (model, r.status_code, r.text[:400]))
        j = r.json()
        pcm = base64.b64decode(j["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        u = j.get("usageMetadata") or {}
        usage = {
            "input": u.get("promptTokenCount") or 0,
            "output": u.get("candidatesTokenCount") or 0,
        }
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0
    y = resample_poly(x, SR // 1000, GEMINI_SR // 1000)  # 24 kHz -> the pipeline's 48 kHz
    pin, pout = GEMINI_PRICES.get(model, (0.0, 0.0))
    cost = (usage["input"] * pin + usage["output"] * pout) / 1e6
    return y, {"model": model, "voice": voice, "usage": usage, "cost_usd": round(cost, 6)}


def trim_silence(x, db=-50.0, pad=0.05):
    """The take without its leading and trailing silence (Gemini leaves some at both ends)."""
    loud = np.flatnonzero(np.abs(x) > 10 ** (db / 20))
    if not len(loud):
        return x, 0.0
    a, b = max(0, loud[0] - int(pad * SR)), min(len(x), loud[-1] + int(pad * SR))
    y = x[a:b].copy()
    f = min(len(y), int(0.02 * SR))
    y[-f:] *= np.linspace(1, 0, f)
    return y, a / SR


def align_words(script, heard):
    """Word times for the SCRIPT's words from Whisper's words on the take: matched in order,
    and the rare word Whisper spelled differently timed between its matched neighbours.
    heard: [(text, start, end)]. Returns [{text, s, e}] in the script's own spelling."""
    toks = [t for t in spoken(script).split() if any(c.isalnum() for c in t)]
    ref = ["".join(words_of(t)) for t in toks]
    hyp = ["".join(words_of(w)) for w, _, _ in heard]
    at = [None] * len(toks)
    for blk in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            _, s, e = heard[blk.b + k]
            at[blk.a + k] = (s, e)
    end = heard[-1][2] if heard else 0.0
    for i in range(len(toks)):  # fill the gaps between known neighbours
        if at[i] is None:
            j = next((k for k in range(i + 1, len(toks)) if at[k] is not None), None)
            lo = at[i - 1][1] if i and at[i - 1] else 0.0
            hi = at[j][0] if j is not None else end
            n = (j if j is not None else len(toks)) - i
            step = max(hi - lo, 0.0) / max(n, 1)
            at[i] = (lo, lo + step)
    return [
        {"text": t, "s": round(s, 3), "e": round(e, 3)} for t, (s, e) in zip(toks, at, strict=True)
    ]


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
_GPU = [None]  # the machine-wide GPU lock, held while large-v3 is loaded on the card


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
        # SKETCH_WHISPER_DEVICE=cpu keeps the card free (Sketch Studio: several films at once)
        if name.endswith(".en") or os.environ.get("SKETCH_WHISPER_DEVICE") == "cpu":
            _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
            return _WHISPER
        # the card is one 4 GB resource shared by every run on the machine (_gpulock.py): queue
        # for it a while, then score on the CPU rather than wait behind a long job
        _GPU[0] = _gpulock.hold("gpu", tool="sketch-vo", wait=90, required=False)
        _GPU[0].__enter__()
        if _GPU[0].token is None:
            print("  whisper %s on CPU (%s)" % (name, _gpulock.describe(_GPU[0].blocked)))
            _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
            return _WHISPER
        atexit.register(_GPU[0].__exit__, None, None, None)
        try:
            _WHISPER = WhisperModel(name, device="cuda", compute_type="int8_float16")
            _WHISPER.transcribe(np.zeros(SR // 10, dtype=np.float32), language=lang)
        except Exception as e:  # noqa: BLE001 -- no usable GPU: slower, same answer
            print("  whisper %s on CPU (%s)" % (name, str(e)[:80]))
            _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
    return _WHISPER


def whisper_score(path, text, hotwords, lang="en", model=None, words=False):
    """(accuracy against the script, what was heard) -- plus, with words=True, Whisper's word
    timestamps [(text, start, end)] for a backend that gives none (Gemini)."""
    segs, _ = _whisper(lang, model).transcribe(
        path,
        language=lang,
        initial_prompt=", ".join(hotwords) if hotwords else None,
        word_timestamps=words,
    )
    segs = list(segs)
    heard = " ".join(s.text for s in segs)
    ref, hyp = words_of(text), words_of(heard)
    acc = difflib.SequenceMatcher(None, ref, hyp).ratio()
    if not words:
        return acc, heard.strip()
    ws = [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]
    return acc, heard.strip(), ws


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--plan", action="store_true", help="price the run (characters, credits, layout) and stop"
    )
    ap.add_argument("--only", help="comma list of line numbers (0-based) to (re)process")
    ap.add_argument("--retake", action="store_true", help="discard cached takes for --only lines")
    ap.add_argument("--takes", type=int, help="override vo.takes")
    ap.add_argument(
        "--tts", choices=["elevenlabs", "edge", "gemini"], help="override vo.tts (edge is free)"
    )
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

    if tts == "gemini":
        dub, voice, voice_id = None, vo.get("voice") or "Kore", None
        if voice not in GEMINI_VOICES:  # before anything is spent
            sys.exit("gemini voice %r is not one of: %s" % (voice, ", ".join(GEMINI_VOICES)))
    else:
        dub = import_module("dub-tts")
        voice = vo.get("voice") or dub.default_voice(tts)
        # refuses unknown / unverified voices before any spend
        voice_id = dub.resolve_voice(voice, tts)

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
    except Exception:  # noqa: BLE001 -- the registry is optional for planning (and absent for gemini)
        pass
    model_name = {"elevenlabs": vo.get("model", "eleven_v3"), "gemini": vo.get("model")}.get(tts)
    t = vo.get("lead", 0.6)
    print(
        "%s  voice=%s (%s)  model=%s  takes=%d"
        % (
            m["_id"],
            voice,
            tts,
            (model_name or "gemini-3.8-flash-tts") if tts != "edge" else "edge",
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
        results, fresh = {}, set()  # fresh: takes rendered (and paid for) in this run
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
                    fresh.add(base)
                    if tts == "elevenlabs":
                        mp3, align = el_take(
                            ln["text"] + ("\n\n" + tail if tail else ""), voice_id, vo
                        )
                        with open(base + ".mp3", "wb") as f:
                            f.write(mp3)
                    elif tts == "gemini":
                        audio, meta = gemini_take(ln["text"], vo)
                        _sketch.write_wav(base + ".wav", audio)
                        align = {"gemini": meta}  # no timings: Whisper supplies the words
                        print(
                            "    %.1fs, %d+%d tokens, $%.5f"
                            % (
                                len(audio) / SR,
                                meta["usage"]["input"],
                                meta["usage"]["output"],
                                meta["cost_usd"],
                            )
                        )
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
                    elif "gemini" in align:  # a clean line; the words come from Whisper below
                        y, lead = trim_silence(x)
                        ok, words = True, None
                    else:
                        y, lead, ok = cut_at_tail(x, align, tail)
                        words = word_times(align, lead, tail)
                    out = base + "_line.wav"
                    _sketch.write_wav(out, y)
                    cand.setdefault(i, []).append(
                        {
                            "take": k,
                            "file": out,
                            "dur": len(y) / SR,
                            "clean": ok,
                            "words": words,
                            "tts": align.get("gemini") if base in fresh else None,
                        }
                    )
        with st("score"):
            for i, cs in cand.items():
                for c in cs:
                    got = whisper_score(
                        c["file"],
                        lines[i]["text"],
                        vo.get("hotwords", []),
                        _sketch.language(m),
                        vo.get("whisper"),
                        words=c["words"] is None,
                    )
                    c["acc"], c["heard"] = got[0], got[1]
                    if c["words"] is None:  # gemini: the script's words, timed by Whisper
                        c["words"] = align_words(lines[i]["text"], got[2])
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
                        # relative to the manifest: the film's folder can live anywhere
                        "file": os.path.relpath(b["file"], m["_dir"]).replace("\\", "/"),
                        "dur": round(b["dur"], 3),
                    }
                    spent = [c["tts"] for c in cand.get(i, []) if c.get("tts")]
                    if spent:
                        # what this line cost in this run: every take rendered, not only the pick
                        L["tts_cost_usd"] = round(sum(t["cost_usd"] for t in spent), 6)
                        L["tts_tokens"] = {
                            k: sum(t["usage"][k] for t in spent) for k in ("input", "output")
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
            if tts == "gemini":
                timeline["model"] = vo.get("model") or "gemini-3.8-flash-tts"
                # spent in THIS run: cached takes cost nothing again
                timeline["tts_cost_usd"] = round(sum(L.get("tts_cost_usd") or 0 for L in placed), 6)
                print("  gemini tts this run: $%.5f" % timeline["tts_cost_usd"])
                if timeline["tts_cost_usd"]:  # a film may run this more than once: keep them all
                    with open(os.path.join(vdir, "spend.jsonl"), "a", encoding="utf-8") as f:
                        tok = [L["tts_tokens"] for L in placed if L.get("tts_tokens")]
                        f.write(
                            json.dumps(
                                {
                                    "model": timeline["model"],
                                    "cost_usd": timeline["tts_cost_usd"],
                                    "input": sum(t["input"] for t in tok),
                                    "output": sum(t["output"] for t in tok),
                                }
                            )
                            + "\n"
                        )
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
