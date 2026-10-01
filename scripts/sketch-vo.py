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

Who scores: SKETCH_SCORER (the machine) or "whisper" (the film) -- a local faster-whisper model,
or "openrouter:<model>", a transcription service (the studio: openrouter:openai/whisper-large-v3,
OPENROUTER_API_KEY), several takes at once. Each take's score is remembered beside it
(<take>.score.json), so a re-recording scores only the takes that changed.

Why the tail word: eleven_v3 clips the last syllable of most takes (measured: 16 of 18 takes
ended above -30 dBFS). Rendering "line + tail" and cutting in the silence between them gives the
line a sentence-final ending and a clean decay. Only mp3_44100_128 is available below the
Creator tier (192k is a 403).

Voice names resolve through config/elevenlabs-voices.json (dub-tts.py's registry, which refuses
unverified ids before anything is spent). "tts": "edge" is the free draft backend.

Several people speaking (talking heads, sketch/heads.js): "cast" names each speaker's voice,
laid over the film's own ({"alex": {"voice": "Puck"}, "sam": {"voice": "Kore", "style": ...}}),
and a line says who speaks it ("who": "alex"). The timeline keeps each line's "who", which is
what sketch-render uses to move that speaker's mouth; a line without one is the narrator.

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
import time
import base64
import random
import secrets
import glob
import hashlib
import difflib
import atexit
import argparse
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
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


DIGIT = re.compile(r"\d")
# A Gemini take is broken when it runs past twice the time its words take at a slow narrator's
# pace (1.8 words a second of speech; the studio's voices measured 1.85-2.42) plus 1.5 s. In the
# kit bakeoff (2026-10-01) 6 of 12 first recordings came back with such a line -- a 16-word line
# drawled over 71 s, a 12-word nursery line sung as 46 words -- and each cost a full recording and
# a rewrite. A broken take is recorded again up to STRETCH_TRIES times and the shortest kept.
STRETCH_WPS, STRETCH_K, STRETCH_PAD, STRETCH_TRIES = 1.8, 2.0, 1.5, 2


# A line Gemini's prompt filter refuses ("PROHIBITED_CONTENT") is a false alarm often enough, and
# the voice direction is what trips it: in the Leo series (2026-10-01) "Like a team!", "I'm a big
# boy!" and "Brrrr!" were refused with the film's style and read every time without it, and 14
# lines across 6 episodes went to the backup voice -- another person's voice in the middle of the
# film. So a refused line is asked again in the same voice without the direction, twice, before
# the backup voice reads it.
PLAIN_TRIES = 2


def gemini_plain(text, vo):
    """gemini_take, and on a refusal the same voice again without the style (PLAIN_TRIES times)."""
    try:
        return gemini_take(text, vo)
    except Refused:
        if not (vo.get("style") or "").strip():
            raise
    for k in range(PLAIN_TRIES):
        try:
            audio, meta = gemini_take(text, {**vo, "style": ""})
            meta["plain"] = True  # read without the voice direction, after a refusal
            return audio, meta
        except Refused:
            if k == PLAIN_TRIES - 1:
                raise


def said(text, vo):
    """The line as the voice is given it: each word of vo.json's "say" map ({"Mikey": "My-key",
    "varenyky": "vah-REH-nih-kih"}) replaced, whole words only, any case. The script keeps its own
    spelling for the captions, the scoring and the word times (Gemini and the backup voice; edge
    and ElevenLabs time the words they were sent, so they are given the script as written)."""
    for word, as_said in (vo.get("say") or {}).items():
        text = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(word), as_said, text, flags=re.IGNORECASE)
    return text


def stretched(text, audio):
    """Is this take far longer than its words could take?"""
    n = len(words_of(text))
    return len(trim_silence(audio)[0]) / SR > STRETCH_K * n / STRETCH_WPS + STRETCH_PAD


def _same_word(a, b):
    """One word spelled two ways: harbour/harbor, Kit Cut/KitKut (>= .8 of their letters)."""
    return a == b or difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.8


def _credit(ref, hyp):
    """The script words a stretch of what was heard accounts for, where plain matching failed:
    a word spelled a little differently, one word heard as two or two as one, and a number the
    transcriber wrote in digits ("1986") for the words the script spells out ("nineteen eighty
    six") -- the studio's brief has every number written as words, and Whisper writes digits.
    Returns (matched script words, how many more words the heard side counts as)."""
    R, H = len(ref), len(hyp)
    best = [[None] * (H + 1) for _ in range(R + 1)]
    best[0][0] = (0, 0)

    def put(i, j, m, x):
        if i <= R and j <= H and (best[i][j] is None or (m, -x) > (best[i][j][0], -best[i][j][1])):
            best[i][j] = (m, x)

    for i in range(R + 1):
        for j in range(H + 1):
            if best[i][j] is None:
                continue
            m, x = best[i][j]
            put(i + 1, j, m, x)
            put(i, j + 1, m, x)
            if i < R and j < H and _same_word(ref[i], hyp[j]):
                put(i + 1, j + 1, m + 1, x)
            if i < R and j + 1 < H and _same_word(ref[i], hyp[j] + hyp[j + 1]):
                put(i + 1, j + 2, m + 1, x - 1)
            if i + 1 < R and j < H and _same_word(ref[i] + ref[i + 1], hyp[j]):
                put(i + 2, j + 1, m + 2, x + 1)
            if j < H and DIGIT.search(hyp[j]):  # digits heard for up to six spelled-out words
                for k in range(1, 7):
                    if i + k <= R and not any(DIGIT.search(w) for w in ref[i : i + k]):
                        put(i + k, j + 1, m + k, x + k - 1)
    return best[R][H]


def accuracy(text, heard):
    """How much of the script line the take says, 0..1: difflib's ratio over the two word lists,
    with the stretches it cannot match (a 'replace') given the credit _credit finds. Measured on
    the studio's 646 takes of 2026-09-28..30: of the 78 lines the plain ratio put under 0.9, 33
    were numbers in digits or names spelled another way (each one a retake for nothing); the 45
    left are the voice model adding or garbling words, or reading its direction aloud. No take
    scores lower than it did (studio/harvest.py, docs/studio-speed.md)."""
    ref, hyp = words_of(text), words_of(heard)
    matched, heard_n = 0, len(hyp)
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_opcodes():
        if op == "equal":
            matched += a1 - a0
        elif op == "replace" and a1 - a0 <= 12 and b1 - b0 <= 12:
            m, extra = _credit(ref[a0:a1], hyp[b0:b1])
            matched += m
            heard_n += extra
    return 2 * matched / max(1, len(ref) + heard_n)


def line_vo(vo, ln):
    """The voice settings one line is read with: the film's, with its speaker's laid over them.
    A film where several people speak (talking heads) names them in "cast", {who: {"voice",
    "style", "settings"}}, and each line says who speaks it ("who"); a line without "who" is
    the narrator, read with the film's own voice."""
    who = ln.get("who")
    if not who:
        return vo
    return {**vo, **(vo.get("cast") or {}).get(who, {})}


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
    """One take from ElevenLabs with its character timings: (mp3 bytes, alignment). A person's own
    voice (ELEVENLABS_RELAY set, studio/tools.py) goes through kitcut.ai's relay with the film's
    grant and never a key (the site's lib/connections/relay.js speaks with the workspace's key);
    the studio's own voice (the backup) goes straight to ElevenLabs with its key. A refusal that
    is the person's account raises VoiceBlocked, and ElevenLabs' answer is never echoed."""
    import httpx

    relay = os.environ.get("ELEVENLABS_RELAY", "").rstrip("/")
    if relay:
        url = relay + "/v1/text-to-speech/%s/with-timestamps" % voice_id
        headers = {
            "Authorization": "Bearer " + os.environ.get("ELEVENLABS_GRANT", ""),
            "X-Studio-Token": os.environ.get("KITCUT_SITE_TOKEN", ""),
            "X-Film": os.environ.get("ELEVENLABS_FILM", ""),
        }
    else:
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            sys.exit("ELEVENLABS_API_KEY is not set (put it in .env)")
        url, headers = EL_URL % voice_id, {"xi-api-key": key}
    body = {
        "text": text,
        "model_id": vo.get("model", "eleven_v3"),
        "voice_settings": vo.get("settings", {"stability": 0.5, "similarity_boost": 0.8}),
    }
    r = None
    for attempt in range(BUSY_TRIES):
        try:
            r = httpx.post(
                url,
                params={"output_format": vo.get("format", "mp3_44100_128")},
                headers=headers,
                json=body,
                timeout=300,
            )
        except httpx.TransportError:
            r = None  # no answer at all: like a busy one, worth asking again
        # 429 is also ElevenLabs' answer to more requests at once than the plan allows
        if r is not None and (r.status_code not in BUSY or attempt == BUSY_TRIES - 1):
            break
        if attempt < BUSY_TRIES - 1:
            time.sleep(busy_wait(attempt))
    if r is None or r.status_code in BUSY:
        code = r.status_code if r is not None else 0
        if relay:
            raise VoiceBlocked("voice_unreachable", code)
        sys.exit("elevenlabs did not answer (%s)" % (code or "no connection"))
    if r.status_code != 200:
        try:
            d = (r.json() or {}).get("detail") or {}
        except ValueError:
            d = {}
        said = str(d.get("status") or d.get("code") or "") if isinstance(d, dict) else ""
        if relay:
            reason = BLOCKED_BY.get(said) or {401: "el_key_invalid", 402: "el_quota"}.get(
                r.status_code
            )
            if reason:
                raise VoiceBlocked(reason, r.status_code, said)
            if said == "film_char_cap":
                sys.exit(
                    "this film's narration has used the characters it may spend in the person's "
                    "ElevenLabs account: record fewer lines again"
                )
        sys.exit(
            "elevenlabs refused the line (%s%s)" % (r.status_code, ", " + said if said else "")
        )
    j = r.json()
    return base64.b64decode(j["audio_base64"]), j.get("alignment") or {}


_SPENT = threading.Lock()


def user_spend(vdir, vo, chars):
    """A take recorded in the person's own ElevenLabs account: its characters, kept the moment
    it is made (audio/vo/spend.jsonl, payer "user"), so a film that stops half-way still says what
    it spent. It is the person's, not KitCut's: cost_usd 0 (studio/agent.py price)."""
    row = {
        "payer": "user",
        "provider": "elevenlabs",
        "model": vo.get("model", "eleven_v3"),
        "chars": chars,
        "cost_usd": 0,
        "input": 0,
        "output": 0,
    }
    with _SPENT, open(os.path.join(vdir, "spend.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def blocked(e):
    """The person's account will not speak: one line the studio reads (tools.voice), and the exit
    that tells it to pause the film until the person fixes it. Takes already made stay cached."""
    said = {"reason": e.reason, "status": e.status, "detail": e.detail}
    print("VOICE-BLOCKED " + json.dumps(said), flush=True)
    sys.exit(PARK_EXIT)


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
# the voices Google lists as female: how a backup voice is picked (vo["backup"]) only when
# nothing of the film has been recorded yet -- otherwise the film's own pitch decides
# (backup_kind), since a voice direction can move a voice a long way from its label
GEMINI_FEMALE = frozenset(
    "Zephyr Kore Leda Aoede Callirrhoe Autonoe Despina Erinome Laomedeia Achernar Gacrux "
    "Pulcherrima Vindemiatrix Sulafat".split()
)
LOW_VOICE_HZ = 165  # a narration pitched below this takes the backup's low voice
# what a refused line's backup is levelled to: the median speech level of a film's Gemini
# lines (40 lines, 2026-09-27: -18.4 dBFS; ElevenLabs v3 came out at -18.1, Turbo at -22.4)
BACKUP_LEVEL_DB = -18.4
# ElevenLabs API list prices, USD per character (elevenlabs.io/pricing/api, 2026-09)
EL_USD_PER_CHAR = {
    "eleven_v3": 0.10 / 1000,
    "eleven_multilingual_v2": 0.10 / 1000,
    "eleven_turbo_v2_5": 0.05 / 1000,
    "eleven_flash_v2_5": 0.05 / 1000,
}
# what Gemini says when it will not read a line: a content block, not a glitch -- asking
# again does not help, and rephrasing loses the words (a name, a wine)
BLOCKED = ("PROHIBITED", "SAFETY", "BLOCKLIST", "SPII", "BLOCKREASON", "BLOCK_REASON")
# a rate limit or a server hiccup: worth asking again after a pause, unlike a refusal. Lines
# recorded several at a time (--jobs) meet the rate limit that one at a time never did
BUSY = frozenset({429, 500, 502, 503, 504})
BUSY_TRIES = 7  # ~1.5 minutes of backing off before a busy service is an error


def busy_wait(attempt):
    """Seconds to wait before asking again: doubling, capped, jittered so parallel takes that
    were refused together do not all come back together."""
    return min(30.0, 2.0**attempt) + random.random()  # noqa: S311 -- jitter, not a secret


class Refused(Exception):
    """Gemini TTS will not read this line (its content filter), however often it is asked."""


class VoiceBlocked(Exception):
    """The person's own ElevenLabs account will not speak now -- its key, its characters, its
    permissions, the voice, or the connection itself -- however often it is asked. The studio
    pauses the film until the person fixes it (blocked(): exit PARK_EXIT)."""

    def __init__(self, reason, status=None, detail=None):
        super().__init__(reason)
        self.reason, self.status, self.detail = reason, status, detail


# what a refusal of the person's own account means for the film: the relay hands ElevenLabs'
# answer on as it came, and adds its own (kitcut.ai lib/connections/relay.js)
BLOCKED_BY = {
    "invalid_api_key": "el_key_invalid",
    "missing_permissions": "el_key_permissions",
    "quota_exceeded": "el_quota",
    "voice_not_found": "el_voice_missing",
    "detected_unusual_activity": "el_account_blocked",
    "paid_plan_required": "el_plan",
    "payment_required": "el_plan",
    "connection_removed": "voice_disconnected",
    "grant_expired": "voice_disconnected",
    "grant_mismatch": "voice_disconnected",
}
PARK_EXIT = 75  # EX_TEMPFAIL: the studio parks the film (studio/tools.py voice)
# the word said after every ElevenLabs line and cut off again (cut_at_tail): the line's own last
# word then ends as a word, not a trailing breath. In the film's language; English films keep
# the "Alright." their cached takes were recorded with
TAILS = {
    "en": "Alright.",
    "uk": "Добре.",
    "de": "Also.",
    "es": "Bueno.",
    "fr": "Voilà.",
    "it": "Allora.",
    "pl": "Dobrze.",
    "pt": "Pronto.",
}


def refused(why):
    return any(b in str(why).upper().replace(" ", "") for b in BLOCKED)


def _google_creds(scopes):
    from google.oauth2 import service_account

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip()
    if not raw:
        return None, None
    info = json.loads(base64.b64decode(raw) if not raw.startswith("{") else raw)
    return service_account.Credentials.from_service_account_info(info, scopes=scopes), info


def vertex_call(client, words, **kw):
    """client.models.generate_content, asked again while Vertex is busy (429/5xx)."""
    from google.genai import errors

    for attempt in range(BUSY_TRIES - 1):
        try:
            return client.models.generate_content(**kw)
        except errors.APIError as e:
            if e.code not in BUSY:
                raise
            wait = busy_wait(attempt)
            print("  gemini busy (%s) on %r; asking again in %.0fs" % (e.code, words[:40], wait))
            time.sleep(wait)
    return client.models.generate_content(**kw)  # the last try: busy now is an error


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
        # the preview models now and then answer with no audio at all (no candidate, or one with
        # no parts) for a line they read fine a moment later: ask again before giving up
        pcm, why = None, "no answer"
        for attempt in range(3):
            r = vertex_call(
                client,
                words,
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
            cand = (r.candidates or [None])[0]
            parts = (cand.content.parts if cand and cand.content else None) or []
            if parts and parts[0].inline_data and parts[0].inline_data.data:
                pcm = parts[0].inline_data.data
                break
            why = "finish reason %s" % (cand.finish_reason if cand else r.prompt_feedback)
            if refused(why):
                raise Refused(why)
            print("  gemini gave no audio for %r (%s); asking again" % (words[:40], why))
            time.sleep(2 * (attempt + 1))
        if pcm is None:
            sys.exit(
                "Gemini TTS gave no audio for the line %r three times (%s): rephrase it"
                % (words, why)
            )
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
        for attempt in range(BUSY_TRIES):
            r = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
                % model,
                headers=headers,
                json=body,
                timeout=180,
            )
            if r.status_code not in BUSY or attempt == BUSY_TRIES - 1:
                break
            wait = busy_wait(attempt)
            print(
                "  gemini busy (%s) on %r; asking again in %.0fs"
                % (r.status_code, words[:40], wait)
            )
            time.sleep(wait)
        if r.status_code != 200:
            sys.exit("gemini %s %s: %s" % (model, r.status_code, r.text[:400]))
        j = r.json()
        try:
            pcm = base64.b64decode(j["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except (KeyError, IndexError, TypeError):
            why = j.get("promptFeedback") or [
                c.get("finishReason") for c in j.get("candidates") or []
            ]
            if refused(why):
                raise Refused(str(why)[:300]) from None
            sys.exit(
                "Gemini TTS gave no audio for the line %r (%s): rephrase it" % (words, str(j)[:300])
            )
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


def pitch_hz(x, sr=SR):
    """Median pitch of the voiced 40 ms frames (autocorrelation, 70-400 Hz), or None."""
    from scipy.signal import resample_poly

    y, fs = resample_poly(x, 1, sr // 16000), 16000
    n, out = int(0.04 * fs), []
    for i in range(0, len(y) - n, n):
        f = y[i : i + n] - y[i : i + n].mean()
        if np.sqrt((f**2).mean()) < 0.02:
            continue
        ac = np.correlate(f, f, "full")[n - 1 :]
        lo, hi = fs // 400, fs // 70
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.4 * ac[0]:
            out.append(fs / k)
    return float(np.median(out)) if out else None


def backup_kind(vo, vdir):
    """ "low" or "high": the film's own Gemini takes, measured, else the voice's label. A film
    with a cast goes by the speaker's voice's label: its takes are several people's."""
    if vo.get("cast"):
        return "high" if vo.get("voice") in GEMINI_FEMALE else "low"
    got = []
    for js in sorted(glob.glob(os.path.join(vdir, "L*_T*_*.json")))[:8]:
        with open(js, encoding="utf-8") as f:
            meta = json.load(f).get("gemini")
        wav = js[:-5] + ".wav"
        if meta and not meta.get("backup") and os.path.exists(wav):
            hz = pitch_hz(_sketch.decode(wav))
            if hz:
                got.append(hz)
    if got:
        return "low" if float(np.median(got)) < LOW_VOICE_HZ else "high"
    return "high" if vo.get("voice") in GEMINI_FEMALE else "low"


def level_to(x, db):
    """The take with its speech (20 ms frames within 30 dB of the loudest) at db dBFS RMS, peaks
    kept under 0 dB."""
    f = x[: len(x) // 960 * 960].reshape(-1, 960)
    r = np.sqrt((f**2).mean(axis=1))
    loud = r[r > r.max() * 10 ** (-30 / 20)] if r.max() > 0 else r  # the voice, not its pauses
    if not len(loud) or not loud.any():
        return x
    y = x * 10 ** ((db - 20 * np.log10(np.sqrt((loud**2).mean()))) / 20)
    peak = np.abs(y).max()
    return y * (0.98 / peak) if peak > 0.98 else y


def backup_take(text, vo, vdir):
    """A line Gemini refused, read by the backup voice (vo["backup"]: ElevenLabs, a low and a
    high voice from config/elevenlabs-voices.json), levelled to Gemini's lines. Returns
    (samples at SR, meta) like gemini_take; the words are timed by Whisper as Gemini's are."""
    b = vo["backup"]
    name = b["voices"][backup_kind(vo, vdir)]
    vid = import_module("dub-tts").resolve_voice(name, "elevenlabs")
    model = b.get("model", "eleven_v3")
    words = spoken(text)
    mp3, _ = el_take(
        words,
        vid,
        {"model": model, "settings": b.get("settings")} if b.get("settings") else {"model": model},
    )
    tmp = os.path.join(vdir, "_backup_%s.mp3" % secrets.token_hex(4))
    with open(tmp, "wb") as f:
        f.write(mp3)
    y = level_to(_sketch.decode(tmp), BACKUP_LEVEL_DB)
    os.remove(tmp)
    cost = len(words) * EL_USD_PER_CHAR.get(model, 0.10 / 1000)
    meta = {
        "model": model,
        "voice": name,
        "backup": "elevenlabs",
        "usage": {"input": 0, "output": 0, "chars": len(words)},
        "cost_usd": round(cost, 6),
    }
    return y, meta


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


OPENROUTER_STT = "https://openrouter.ai/api/v1/audio/transcriptions"
FALLBACK = True  # a take the service fails is scored locally; a benchmark turns this off


def scorer(model=None):
    """Who listens to the takes: SKETCH_SCORER (the machine's choice, e.g. the studio VM's) wins
    over the film's "whisper"; "openrouter:<model>" is a transcription model OpenRouter serves
    (openrouter.ai/api/v1/models?output_modalities=transcription), anything else a local
    faster-whisper model name (None: small.en / large-v3 by language)."""
    return os.environ.get("SKETCH_SCORER", "").strip() or model


def remote(model):
    return bool(model) and model.startswith("openrouter:")


def openrouter_heard(path, lang, model, hotwords=()):
    """What an OpenRouter transcription model heard in the take: (text, [(word, start, end)]).
    The take goes up as 16 kHz mono WAV (a third of the 48 kHz bytes; speech needs no more).
    OpenRouter ignores a prompt; Azure's models (MAI-Transcribe) take the hotwords as a phrase
    list instead, the others go without."""
    import httpx

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("set OPENROUTER_API_KEY to score takes on %s" % model)
    wav = subprocess.run(  # 16-bit PCM: not every provider reads the float WAVs written here
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    body = {
        "model": model.split(":", 1)[1],
        "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"},
        "language": lang,
        "response_format": "verbose_json",
        "timestamp_granularities": ["word"],
        "temperature": 0,
    }
    if hotwords and model.startswith("openrouter:microsoft/"):
        body["provider"] = {"options": {"azure": {"phraseList": {"phrases": list(hotwords)}}}}
    for attempt in range(BUSY_TRIES):
        try:
            r = httpx.post(
                OPENROUTER_STT,
                headers={"Authorization": "Bearer " + key},
                json=body,
                timeout=120,
            )
        except httpx.TransportError as e:  # a dropped connection is busy too
            r = None
            why = type(e).__name__
        if r is not None and (r.status_code not in BUSY or attempt == BUSY_TRIES - 1):
            break
        wait = busy_wait(attempt)
        print(
            "  %s busy (%s); asking again in %.0fs"
            % (model, why if r is None else r.status_code, wait)
        )
        time.sleep(wait)
    if r is None or r.status_code != 200:
        raise RuntimeError("%s %s: %s" % (model, r and r.status_code, r and r.text[:300]))
    j = r.json()
    ws = [(w.get("word", ""), float(w["start"]), float(w["end"])) for w in j.get("words") or []]
    if not ws:  # a model that times segments only: its words, spread over each segment
        for seg in j.get("segments") or []:
            toks = seg.get("text", "").split()
            step = (seg["end"] - seg["start"]) / max(len(toks), 1)
            ws += [
                (t, seg["start"] + k * step, seg["start"] + (k + 1) * step)
                for k, t in enumerate(toks)
            ]
    return j.get("text", ""), ws


def whisper_score(path, text, hotwords, lang="en", model=None, words=False):
    """(accuracy against the script, what was heard) -- plus, with words=True, Whisper's word
    timestamps [(text, start, end)] for a backend that gives none (Gemini)."""
    model = scorer(model)
    if remote(model):
        try:
            heard, ws = openrouter_heard(path, lang, model, hotwords)
            acc = accuracy(text, heard)
            return (acc, heard.strip(), ws) if words else (acc, heard.strip())
        except (RuntimeError, ValueError, KeyError) as e:  # the service is down: slower, same job
            if not FALLBACK:
                raise
            print("  %s failed (%s); scoring this take here" % (model, str(e)[:120]))
            model = None
    segs, _ = _whisper(lang, model).transcribe(
        path,
        language=lang,
        initial_prompt=", ".join(hotwords) if hotwords else None,
        word_timestamps=words,
    )
    segs = list(segs)
    heard = " ".join(s.text for s in segs)
    acc = accuracy(text, heard)
    if not words:
        return acc, heard.strip()
    ws = [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]
    return acc, heard.strip(), ws


def use_approved(base, entry, key):
    """An approved voice line in as a line's only take: base.wav, then base.json {"approved":
    key, "sha"} (last, so the take is only ever cached whole). Copied again only when the
    approved recording changed (approved anew in the project). Returns True when it copied."""
    with open(entry["file"], "rb") as f:
        data = f.read()
    sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()[:16]
    try:
        with open(base + ".json", encoding="utf-8") as f:
            had = json.load(f)
    except (OSError, ValueError):
        had = {}
    if had.get("approved") == key and had.get("sha") == sha and os.path.exists(base + ".wav"):
        return False
    for ext in (".mp3", ".json", ".score.json"):
        if os.path.exists(base + ext):
            os.remove(base + ext)
    with open(base + ".wav", "wb") as f:
        f.write(data)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"approved": key, "sha": sha, "text": entry.get("text", "")}, f)
    return True


def cached_score(base, path, text, hotwords, lang="en", model=None, words=False):
    """whisper_score, remembered beside the take (base.score.json) under a key of everything the
    answer depends on: the audio's bytes, the script line, the hotwords, the language and the
    model. A re-recording re-scores only the takes that changed -- scoring every take again cost
    an 8-minute film 180-225 s per recording on the studio's 4-CPU VM, for lines whose audio was
    the same file as last time (studio-20260929-103129-i4d52n: 18 of its 23 narration minutes)."""
    with open(path, "rb") as f:
        audio = hashlib.sha1(f.read()).hexdigest()
    key = hashlib.sha1(
        json.dumps([audio, text, list(hotwords or []), lang, scorer(model), words]).encode("utf-8")
    ).hexdigest()
    memo = base + ".score.json"
    if os.path.exists(memo):
        try:
            with open(memo, encoding="utf-8") as f:
                got = json.load(f)
            if got.get("key") == key:
                got = list(got["got"])
                got[0] = accuracy(text, got[1])  # what was heard keeps; how it scores may change
                return tuple(got)
        except (OSError, ValueError, KeyError):
            pass  # a torn or older memo: score again
    got = whisper_score(path, text, hotwords, lang, model, words)
    with open(memo + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"key": key, "got": got}, f)
    os.replace(memo + ".tmp", memo)
    return got


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
        "--jobs",
        type=int,
        help="takes recorded at once (default vo.jobs, else 1): the TTS services answer one line "
        "in seconds, so an 85-line film spends minutes waiting one line at a time",
    )
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
    lang = str(vo.get("language") or "en")[:2]
    tail = vo.get("tail", TAILS.get(lang, "OK.")) if tts == "elevenlabs" else ""
    jobs = args.jobs or int(vo.get("jobs", 1))
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
    # several speakers: every line's "who" must be in the cast, and every cast voice must be a
    # voice this backend has -- all checked before anything is spent
    cast = vo.get("cast") or {}
    ids = {voice: voice_id}  # voice name -> the id the backend takes
    for i, ln in enumerate(lines):
        if ln.get("who") and ln["who"] not in cast:
            sys.exit(
                "line %d: who %r is not in vo.cast (%s)" % (i, ln["who"], ", ".join(cast) or "none")
            )
    for who, spec in cast.items():
        v = spec.get("voice") or voice
        if tts == "gemini" and v not in GEMINI_VOICES:
            sys.exit(
                "cast %r: gemini voice %r is not one of: %s" % (who, v, ", ".join(GEMINI_VOICES))
            )
        if tts != "gemini" and v not in ids:
            ids[v] = dub.resolve_voice(v, tts)

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
        "%s  voice=%s (%s)  model=%s  takes=%d  jobs=%d"
        % (
            m["_id"],
            voice,
            tts,
            (model_name or "gemini-3.8-flash-tts") if tts != "edge" else "edge",
            takes,
            jobs,
        )
    )
    for i, ln in enumerate(lines):
        est = len(words_of(ln["text"])) / WPS
        st = ln.get("start", t)
        who = (
            ("%s (%s): " % (ln["who"], line_vo(vo, ln).get("voice") or voice))
            if ln.get("who")
            else ""
        )
        print("  %2d  %5.2fs +%4.1fs  %s%s" % (i, st, est, who, spoken(ln["text"])[:90]))
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
            todo = []  # (line, take, base): the takes not in the cache
            # the project's approved voice lines (library.seed): a line with the same words, voice
            # and model plays the recording its person approved by ear, never a new one
            approved, given = _sketch.approved_lines(vdir), {}
            for i, ln in enumerate(lines):
                if i not in only:
                    continue
                lvo = line_vo(vo, ln)  # the speaker's voice, when the line names one
                # the words as said (the say map) are what is recorded: a new spelling records again
                fp = fingerprint({**ln, "text": said(ln["text"], vo)}, {**lvo, "tts": tts})
                key = _sketch.voice_line_key(ln["text"], lvo, tts)
                if key in approved:
                    given[i] = key
                    use_approved(os.path.join(vdir, "L%02d_T0_%s" % (i, fp)), approved[key], key)
                    print("  line %d: the approved recording %s" % (i, key), flush=True)
                    results[i] = fp
                    continue
                for k in range(takes):
                    base = os.path.join(vdir, "L%02d_T%d_%s" % (i, k, fp))
                    if args.retake and os.path.exists(base + ".json"):
                        for ext in (".mp3", ".wav", ".json", ".score.json"):
                            if os.path.exists(base + ext):
                                os.remove(base + ext)
                    if not os.path.exists(base + ".json"):
                        todo.append((i, k, base))
                results[i] = fp

            def synth(job):
                """One take, written to base.{mp3|wav,json}; returns what to print about it.
                The .json goes last, so a take is only ever cached whole."""
                i, k, base = job
                ln = lines[i]
                lvo = line_vo(vo, ln)  # the speaker's voice, when the line names one
                lvoice = lvo.get("voice") or voice
                note = "  line %d take %d" % (i, k)
                if tts == "elevenlabs":
                    sent = ln["text"] + ("\n\n" + tail if tail else "")
                    mp3, align = el_take(sent, ids[lvoice], lvo)
                    with open(base + ".mp3", "wb") as f:
                        f.write(mp3)
                    if os.environ.get("ELEVENLABS_RELAY"):  # the person's own characters
                        user_spend(vdir, lvo, len(sent))
                elif tts == "gemini":
                    say = said(ln["text"], vo)  # what the voice is given: the say map applied
                    try:
                        audio, meta = gemini_plain(say, lvo)
                        # a take far longer than its words is a broken one -- the voice drawled
                        # or said things the script does not: record it again before anyone
                        # pays a retake for it (stretched)
                        for k2 in range(STRETCH_TRIES):
                            if not stretched(ln["text"], audio):
                                break
                            note += "\n    %.1fs for %d words: broken, recorded again" % (
                                len(audio) / SR,
                                len(words_of(ln["text"])),
                            )
                            # the last try goes without the direction: a voice that reads its
                            # direction aloud does it again and again with it (Leo, episode 3)
                            last = k2 == STRETCH_TRIES - 1
                            again, meta2 = gemini_plain(say, {**lvo, "style": ""} if last else lvo)
                            meta2["cost_usd"] = meta2.get("cost_usd", 0) + meta.get("cost_usd", 0)
                            if len(trim_silence(again)[0]) < len(trim_silence(audio)[0]):
                                audio, meta = again, meta2
                            else:
                                meta["cost_usd"] = meta2["cost_usd"]
                    except Refused as e:
                        if not vo.get("backup"):
                            sys.exit(
                                "Gemini TTS refused the line %r (%s): rephrase it"
                                % (spoken(ln["text"]), e)
                            )
                        audio, meta = backup_take(say, lvo, vdir)
                        meta["refused"] = str(e)[:200]
                    _sketch.write_wav(base + ".wav", audio)
                    align = {"gemini": meta}  # no timings: Whisper supplies the words
                    if meta.get("backup"):
                        note += (
                            "\n    Gemini refused it: read by the backup voice (%s, %s), "
                            "%.1fs, $%.5f"
                        ) % (
                            meta["voice"],
                            meta["model"],
                            len(audio) / SR,
                            meta["cost_usd"],
                        )
                    else:
                        note += "\n    %.1fs, %d+%d tokens, $%.5f" % (
                            len(audio) / SR,
                            meta["usage"]["input"],
                            meta["usage"]["output"],
                            meta["cost_usd"],
                        )
                else:
                    audio, marks = edge_take(ln["text"], lvoice, dub)
                    _sketch.write_wav(base + ".wav", audio)
                    align = {"words": [{"text": w, "s": a, "e": b} for w, a, b in marks]}
                with open(base + ".json", "w", encoding="utf-8") as f:
                    json.dump(align, f)
                return note

            fresh.update(base for _, _, base in todo)
            n_jobs = max(1, min(jobs, len(todo) or 1))
            if todo:
                print("  %d takes to record, %d at a time" % (len(todo), n_jobs), flush=True)
            # a refused line with no backup, or a line that never comes back, exits: sys.exit in
            # a worker is re-raised here, the takes not started are dropped, and the takes
            # already written stay cached for the next run
            with ThreadPoolExecutor(max_workers=n_jobs) as pool:
                futs = [pool.submit(synth, job) for job in todo]
                try:
                    for f in as_completed(futs):
                        print(f.result(), flush=True)
                except BaseException as e:
                    for g in futs:
                        g.cancel()
                    if isinstance(e, VoiceBlocked):
                        blocked(e)
                    raise
        cand = {}
        with st("trim"):
            for i, fp in results.items():
                for k in range(1 if i in given else takes):
                    base = os.path.join(vdir, "L%02d_T%d_%s" % (i, k, fp))
                    with open(base + ".json", encoding="utf-8") as f:
                        align = json.load(f)
                    src = base + (".mp3" if os.path.exists(base + ".mp3") else ".wav")
                    x = _sketch.decode(src)
                    if "words" in align:  # edge: already a clean line, times in seconds
                        y, lead, ok, words = x, 0.0, True, align["words"]
                    elif "gemini" in align or "approved" in align:
                        # a clean line (an approved one was once a take like this); the words
                        # come from Whisper below
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
                            "base": base,
                            "file": out,
                            "dur": len(y) / SR,
                            "clean": ok,
                            "words": words,
                            "tts": align.get("gemini") if base in fresh else None,
                            "backup": (align.get("gemini") or {}).get("voice")
                            if (align.get("gemini") or {}).get("backup")
                            else None,
                            "approved": align.get("approved"),
                        }
                    )
        with st("score"):
            # a scoring service answers several takes at once (--jobs, as the voice does); the
            # local model has the CPU to itself, one take at a time
            flat = [(i, c) for i, cs in cand.items() for c in cs]

            def score(job):
                i, c = job
                return cached_score(
                    c["base"],
                    c["file"],
                    lines[i]["text"],
                    vo.get("hotwords", []),
                    _sketch.language(m),
                    vo.get("whisper"),
                    words=c["words"] is None,
                )

            n_jobs = jobs if remote(scorer(vo.get("whisper"))) else 1
            with ThreadPoolExecutor(max_workers=max(1, min(n_jobs, len(flat) or 1))) as pool:
                for (i, c), got in zip(flat, pool.map(score, flat)):
                    c["acc"], c["heard"] = got[0], got[1]
                    if c["words"] is None:  # gemini: the script's words, timed by Whisper
                        c["words"] = align_words(lines[i]["text"], got[2])
            for i, cs in cand.items():
                med = float(np.median([c["dur"] for c in cs]))
                for c in cs:
                    # accuracy first, then a clean cut, then the take nearest the median length
                    c["rank"] = (round(c["acc"], 2), c["clean"], -abs(c["dur"] - med))
                pick = lines[i].get("pick")
                # a pick that names no take (an approved line has only its one) is no pick
                best = next((c for c in cs if c["take"] == pick), None) or max(
                    cs, key=lambda c: c["rank"]
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
                    if b.get("approved"):  # the project's approved recording, as it was approved
                        L["approved"] = b["approved"]
                    if b.get("backup"):  # Gemini refused it: the backup voice read it
                        L["backup_voice"] = b["backup"]
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
                L.pop("who", None)  # the script decides who speaks, not an older timeline
                if ln.get("who"):
                    L["who"] = ln["who"]
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
            if cast:
                timeline["cast"] = {w: s.get("voice") or voice for w, s in cast.items()}
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
