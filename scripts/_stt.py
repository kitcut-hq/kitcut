"""Speech to text for short voice notes: one call, several engines, one answer shape.

A voice note is someone describing the film they want, in their own language, for up to three
minutes, recorded by a browser (WebM/Opus from Chrome, MP4/AAC from Safari). Every engine gets the
same thing: the note normalised by ffmpeg to 16 kHz mono FLAC (normalise()), because Gemini does
not list WebM and Whisper wants one rate anyway.

Engines, named "<kind>:<model>":
    openrouter:<model>   any OpenRouter chat model that takes audio (OPENROUTER_API_KEY), e.g.
                         openrouter:openai/gpt-audio-mini; the price comes back with the answer.
                         The account's allowed-providers setting decides which models answer
    gemini:<model>       the Gemini API directly (GEMINI_API_KEY), e.g. gemini:gemini-3.8-flash
    vertex:<model>       Gemini on Vertex AI (GOOGLE_SERVICE_ACCOUNT_KEY, as the painter uses it)
    openai:<model>       OpenAI's transcription endpoint (OPENAI_API_KEY), e.g.
                         openai:gpt-4o-mini-transcribe, openai:whisper-1
    whisper:<model>      faster-whisper on this machine, CPU int8 (the card belongs to the
                         renders), e.g. whisper:medium; no key, no cost, slower

transcribe() returns {"text", "lang", "seconds", "cost_usd", "engine"}; an engine that fails
raises SttError with the reason. A language model is told to write down only what was said, in
the language it was said in, and nothing when nothing was said (a Whisper-style hallucination on
silence is what that line is for); names the studio expects are passed as hints.

Not an entry script: imported by stt-compare.py (which measures the engines against each other)
and by the studio (studio/uploads.py).
"""

import os
import re
import json
import time
import base64
import subprocess

RATE = 16000
PROMPT = (
    "Transcribe this voice note word for word, in the language it is spoken in. Write only the "
    "words that were said: no introduction, no quotation marks, no timestamps, no speaker labels, "
    "no translation and no summary. Keep the speaker's own wording, and drop only filler sounds "
    "such as 'um' and 'uh'. If nothing is said, answer with nothing at all."
)
HINTS = ("KitCut", "Claude", "Opus")
# Gemini answers with tokens, not a price: USD per million input (audio) and output tokens, the
# list prices OpenRouter quotes for the same models (2026-09-26)
GEMINI_PRICE = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash": (3.0, 9.0),
    "gemini-3.5-flash-lite": (0.30, 2.5),
    "gemini-3.1-flash-lite": (0.50, 1.5),
}
# less speech than this and the note is treated as empty, without asking any engine: every
# language model tried wrote something for 8 s of silence (a French sentence, "He is making a lot
# of noise", the list of names it was given)
MIN_SPEECH_S = 0.4
_WHISPER = {}


class SttError(Exception):
    """An engine that could not transcribe, in words."""


def normalise(src, dst):
    """src (any audio ffmpeg reads) -> dst, 16 kHz mono FLAC. Returns its length in seconds."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(RATE), dst],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0 or not os.path.exists(dst):
        raise SttError("could not read the recording: %s" % (r.stderr.strip()[-200:] or "ffmpeg"))
    return duration(dst)


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError) as e:
        raise SttError("could not measure the recording") from e


def speech_seconds(path):
    """Seconds of speech in the note, by the Silero VAD faster-whisper ships (CPU, fast)."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(path, sampling_rate=RATE)
    spans = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300))
    return sum(s["end"] - s["start"] for s in spans) / RATE


def _key(env, name):
    """A setting from env (the studio hands its keys over this way: they are not in its
    environment) or else the environment."""
    return ((env or {}).get(name) or os.environ.get(name) or "").strip()


def _gemini_cost(model, tokens_in, tokens_out):
    p = GEMINI_PRICE.get(model)
    if not p or tokens_in is None:
        return None
    return round((tokens_in * p[0] + (tokens_out or 0) * p[1]) / 1e6, 6)


def _prompt(hints):
    names = [h for h in (*HINTS, *(hints or ())) if h]
    return PROMPT + (" Names that may come up: %s." % ", ".join(names) if names else "")


def _clean(text):
    """What a language model wraps a transcript in, removed: quotes, a 'Transcript:' label."""
    t = (text or "").strip()
    t = re.sub(r"^(transcript(ion)?|here is the transcript[^:]*)\s*:\s*", "", t, flags=re.I)
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    return t


def _post(url, headers, body, timeout):
    import httpx

    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise SttError("%s: %s" % (type(e).__name__, e)) from e
    try:
        j = r.json()
    except ValueError:
        j = {"error": r.text[:300]}
    return r.status_code, j


def _mp3(flac):
    """The note as MP3 beside it (OpenAI's audio models take wav or mp3, not flac)."""
    out = os.path.splitext(flac)[0] + ".mp3"
    if not os.path.exists(out):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", flac, "-b:a", "48k", out],
            check=True,
            capture_output=True,
        )
    return out


def _openrouter(flac, model, hints, env, timeout):
    key = _key(env, "OPENROUTER_API_KEY")
    if not key:
        raise SttError("OPENROUTER_API_KEY is not set")
    src, fmt = (_mp3(flac), "mp3") if model.startswith("openai/") else (flac, "flac")
    with open(src, "rb") as f:
        audio = base64.b64encode(f.read()).decode()
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt(hints)},
                    {"type": "input_audio", "input_audio": {"data": audio, "format": fmt}},
                ],
            }
        ],
        "reasoning": {"effort": "low", "exclude": True},
        "usage": {"include": True},
    }
    headers = {"Authorization": "Bearer " + key, "X-Title": "kitcut"}
    url = "https://openrouter.ai/api/v1/chat/completions"
    code, j = _post(url, headers, body, timeout)
    if code == 400 and "reason" in json.dumps(j).lower():  # a model that will not be told
        body.pop("reasoning")
        code, j = _post(url, headers, body, timeout)
    if code != 200 or not j.get("choices"):
        raise SttError("openrouter %s %s: %s" % (model, code, str(j.get("error", j))[:300]))
    text = j["choices"][0]["message"].get("content") or ""
    if isinstance(text, list):
        text = " ".join(p.get("text", "") for p in text if isinstance(p, dict))
    return _clean(text), (j.get("usage") or {}).get("cost")


def _gemini(flac, model, hints, env, timeout):
    key = _key(env, "GEMINI_API_KEY")
    if not key:
        raise SttError("GEMINI_API_KEY is not set")
    with open(flac, "rb") as f:
        audio = base64.b64encode(f.read()).decode()
    body = {
        "contents": [
            {
                "parts": [
                    {"text": _prompt(hints)},
                    {"inline_data": {"mime_type": "audio/flac", "data": audio}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    headers = {"x-goog-api-key": key}
    code, j = _post(url, headers, body, timeout)
    if code == 400 and "think" in json.dumps(j).lower():
        body["generationConfig"].pop("thinkingConfig")
        code, j = _post(url, headers, body, timeout)
    if code != 200:
        raise SttError("gemini %s %s: %s" % (model, code, str(j.get("error", j))[:300]))
    cands = j.get("candidates") or []
    if not cands:
        why = (j.get("promptFeedback") or {}).get("blockReason") or "no answer"
        raise SttError("gemini %s: %s" % (model, why))
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = " ".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = j.get("usageMetadata") or {}
    out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
    return _clean(text), _gemini_cost(model, u.get("promptTokenCount"), out)


def _vertex(flac, model, hints, env):
    from google import genai
    from google.genai import types
    from google.oauth2 import service_account

    raw = _key(env, "GOOGLE_SERVICE_ACCOUNT_KEY")
    if not raw:
        raise SttError("GOOGLE_SERVICE_ACCOUNT_KEY is not set")
    info = json.loads(base64.b64decode(raw) if not raw.startswith("{") else raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = genai.Client(
        vertexai=True,
        project=_key(env, "GOOGLE_CLOUD_PROJECT") or info["project_id"],
        location=_key(env, "GOOGLE_CLOUD_LOCATION") or "global",
        credentials=creds,
    )
    with open(flac, "rb") as f:
        audio = types.Part.from_bytes(data=f.read(), mime_type="audio/flac")
    try:
        r = client.models.generate_content(
            model=model,
            contents=[_prompt(hints), audio],
            config=types.GenerateContentConfig(temperature=0),
        )
    except Exception as e:  # noqa: BLE001 -- the library's errors, in words
        raise SttError("vertex %s: %s" % (model, str(e)[:300])) from e
    u = r.usage_metadata
    out = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0) if u else 0
    return _clean(r.text or ""), _gemini_cost(model, u.prompt_token_count if u else None, out)


def _openai(flac, model, hints, env, timeout):
    import httpx

    key = _key(env, "OPENAI_API_KEY")
    if not key:
        raise SttError("OPENAI_API_KEY is not set")
    src = _mp3(flac)
    data = {"model": model, "temperature": "0"}
    names = ", ".join((*HINTS, *(hints or ())))
    data["prompt"] = "A film brief. Names: %s." % names
    try:
        with open(src, "rb") as f:
            r = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": "Bearer " + key},
                data=data,
                files={"file": (os.path.basename(src), f, "audio/mpeg")},
                timeout=timeout,
            )
    except httpx.HTTPError as e:
        raise SttError("openai %s: %s" % (model, e)) from e
    if r.status_code != 200:
        raise SttError("openai %s %s: %s" % (model, r.status_code, r.text[:300]))
    return _clean(r.json().get("text", "")), None


def _whisper(flac, model, hints):
    from faster_whisper import WhisperModel

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    if model not in _WHISPER:
        try:
            _WHISPER[model] = WhisperModel(
                model, device="cpu", compute_type="int8", local_files_only=True
            )
        except Exception as e:  # noqa: BLE001 -- a model not downloaded, said plainly
            raise SttError("whisper %s: %s" % (model, str(e)[:200])) from e
    segs, info = _WHISPER[model].transcribe(
        flac,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        hotwords=" ".join((*HINTS, *(hints or ()))) or None,
    )
    return " ".join(s.text.strip() for s in segs).strip(), info.language


def transcribe(path, engine, hints=(), env=None, timeout=90, gate=True):
    """path: a note already normalised (normalise()). engine: "<kind>:<model>" (see above).
    env: keys and settings by name, looked up before the environment. gate: a note with no
    speech in it comes back empty without asking the engine."""
    kind, _, model = engine.partition(":")
    if not model:
        raise SttError("engine %r: say kind:model" % engine)
    t0 = time.time()
    if gate and speech_seconds(path) < MIN_SPEECH_S:
        return {
            "text": "",
            "lang": None,
            "seconds": round(time.time() - t0, 2),
            "cost_usd": 0.0,
            "engine": engine,
            "no_speech": True,
        }
    cost, lang = None, None
    if kind == "openrouter":
        text, cost = _openrouter(path, model, hints, env, timeout)
    elif kind == "gemini":
        text, cost = _gemini(path, model, hints, env, timeout)
    elif kind == "vertex":
        text, cost = _vertex(path, model, hints, env)
    elif kind == "openai":
        text, _ = _openai(path, model, hints, env, timeout)
    elif kind == "whisper":
        text, lang = _whisper(path, model, hints)
        cost = 0.0
    else:
        raise SttError("engine %r: kind is openrouter, gemini, vertex, openai or whisper" % engine)
    return {
        "text": text,
        "lang": lang,
        "seconds": round(time.time() - t0, 2),
        "cost_usd": cost,
        "engine": engine,
    }


def words(text):
    """The words of a transcript for scoring: lower case, punctuation and filler removed."""
    t = re.sub(r"[’`]", "'", (text or "").lower())
    t = re.sub(r"[^\w\s']", " ", t)
    return [w for w in t.split() if w not in ("um", "uh", "erm", "ah")]


def wer(ref, hyp):
    """Word error rate of hyp against ref (edits / words in ref)."""
    r, h = words(ref), words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(r)
