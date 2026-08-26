#!/usr/bin/env python
"""Speak a line of text and report exactly where each word landed.

Edge's neural voices are used because they need no API key, no GPU and no model
download, and -- the part that matters here -- they emit WordBoundary events.
Those give the dub word-level timings for free, so the English captions can be
timed from the dub itself instead of being guessed at or re-transcribed.

Two things this module is careful about:

* `rate` is a prosodic control, not a resampler. Asking the voice to speak
  faster re-times the phonemes the way a person would; stretching the rendered
  audio afterwards smears the formants. Measured on this voice, duration tracks
  1/(1+rate) to within about half a percent, so `rate_for()` can aim straight at
  a target length and land within a few tens of milliseconds.
* The rendered clip carries leading and trailing silence (~0.36s of tail on a
  short line). Left in, every dubbed phrase would start late. It is trimmed, and
  the word marks are shifted by the same amount so they stay true.

Standalone:
    python scripts/dub-tts.py --say "hello there" --out temp/x.wav --rate 10
    python scripts/dub-tts.py --list-voices --filter en-US
"""
import sys, os, json, argparse, asyncio, subprocess, time, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np
import edge_tts

ENV = _env.ENV
SR = 48000

# Shortlist rather than the full 300+: these are the natural-sounding US voices.
# *Multilingual* variants keep their accent on foreign proper nouns, which
# matters when a dub is full of place names.
VOICES = {
    "ava":     "en-US-AvaMultilingualNeural",     # warm, young, conversational
    "emma":    "en-US-EmmaMultilingualNeural",
    "jenny":   "en-US-JennyNeural",
    "aria":    "en-US-AriaNeural",
    "andrew":  "en-US-AndrewMultilingualNeural",
    "brian":   "en-US-BrianMultilingualNeural",
}
DEFAULT_VOICE = "ava"


def resolve_voice(name, backend="edge"):
    if backend == "elevenlabs":
        return EL_VOICES.get(name, name)
    return VOICES.get(name, name)


def default_voice(backend="edge"):
    return EL_DEFAULT_VOICE if backend == "elevenlabs" else DEFAULT_VOICE


async def _stream(text, voice, rate_pct, pitch_hz):
    c = edge_tts.Communicate(text, voice,
                             rate="%+d%%" % int(round(rate_pct)),
                             pitch="%+dHz" % int(round(pitch_hz)),
                             # the default is SentenceBoundary, which for our
                             # purposes reports nothing useful
                             boundary="WordBoundary")
    audio, marks = bytearray(), []
    async for ch in c.stream():
        if ch["type"] == "audio":
            audio.extend(ch["data"])
        elif ch["type"] == "WordBoundary":
            marks.append(ch)
    return bytes(audio), marks


def _decode(mp3, sr=SR):
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "mp3", "-i", "pipe:0",
                        "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"],
                       input=mp3, capture_output=True, env=ENV)
    if p.returncode:
        raise RuntimeError("ffmpeg could not decode the TTS audio: %s"
                           % p.stderr.decode("utf-8", "replace")[:200])
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def _trim(x, sr=SR, floor_db=-45.0, margin=0.02):
    """Strip the silence the voice pads onto both ends. Returns (audio, lead_s)."""
    if x.size == 0:
        return x, 0.0
    amp = np.abs(x)
    peak = float(amp.max())
    if peak <= 0:
        return x, 0.0
    loud = np.nonzero(amp > peak * (10.0 ** (floor_db / 20.0)))[0]
    if loud.size == 0:
        return x, 0.0
    m = int(margin * sr)
    i0 = max(0, int(loud[0]) - m)
    i1 = min(x.size, int(loud[-1]) + m)
    return x[i0:i1], i0 / float(sr)


# --------------------------------------------------------------- ElevenLabs
# Better voices, and it can clone. The cost is headroom: `speed` is capped at
# 0.7-1.2, so a line can only be compressed to x0.83, where edge reaches x0.69.
# Lines that run long therefore fall back on the `tight` rewrite and rubberband
# more often. Both numbers were measured, not taken from the docs.
EL_URL = "https://api.elevenlabs.io/v1/text-to-speech/%s/with-timestamps"
EL_MODEL = "eleven_multilingual_v2"
EL_SPEED_LO, EL_SPEED_HI = 0.7, 1.2
EL_VOICES = {
    "sarah":   "EXAVITQu4vr4xnSDxMaL",
    "laura":   "FGY2WhTYpPnrIDTdsKH5",
    "alice":   "Xb7hH8MSUJpSbSDYk0k2",
    "matilda": "XrExE9yKIg1WjnnlVkGX",
    "jessica": "cgSgspJ2msm6clMCkdW9",
    "lily":    "pFZP5JQG7iQjIQuC4Bku",
    "brian":   "nPczCjzI2devNBz1zQrb",
}
EL_DEFAULT_VOICE = "jessica"


def _el_render(text, voice, rate_pct):
    """Returns (mp3 bytes, [(word, t0, t1)]) with times in seconds."""
    import base64
    import httpx

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set (put it in .env)")
    vid = EL_VOICES.get(voice, voice)
    speed = max(EL_SPEED_LO, min(EL_SPEED_HI, 1.0 + rate_pct / 100.0))
    r = httpx.post(EL_URL % vid, timeout=180,
                   headers={"xi-api-key": key, "Content-Type": "application/json"},
                   json={"text": text, "model_id": EL_MODEL,
                         "voice_settings": {"stability": 0.5,
                                            "similarity_boost": 0.75,
                                            "speed": round(speed, 3)}})
    if r.status_code != 200:
        raise RuntimeError("elevenlabs %s: %s" % (r.status_code, r.text[:200]))
    j = r.json()
    mp3 = base64.b64decode(j["audio_base64"])
    al = j.get("alignment") or {}
    # alignment is per CHARACTER; glue them back into words on whitespace
    marks, cur, t0, t1 = [], "", None, None
    for c, a, b in zip(al.get("characters") or [],
                       al.get("character_start_times_seconds") or [],
                       al.get("character_end_times_seconds") or []):
        if c.isspace():
            if cur:
                marks.append((cur, t0, t1))
            cur, t0 = "", None
            continue
        if not cur:
            t0 = a
        cur += c
        t1 = b
    if cur:
        marks.append((cur, t0, t1))
    return mp3, monotonic(marks)


def monotonic(marks, min_len=0.01):
    """Force word marks to run forward and never overlap.

    Character-level alignment hands back words that start a few milliseconds
    before the previous one finished -- 9 such pairs in a 228-word clip, where
    edge produced none. The caption builder refuses to write an ASS whose groups
    overlap (rightly: overlapping karaoke groups render as garbage), so a dub
    built on those timings fails at the self-check rather than at the eye.
    Nudging the start forward costs a few ms of highlight and fixes it.
    """
    out, prev_end = [], 0.0
    for w, a, b in marks:
        a = max(float(a), prev_end)
        b = max(float(b), a + min_len)
        out.append((w, a, b))
        prev_end = b
    return out


def speak(text, voice=DEFAULT_VOICE, rate_pct=0.0, pitch_hz=0.0, sr=SR, tries=4,
          backend="edge"):
    """Render one line. Returns (samples float32 mono, [(word, t0, t1), ...]).

    Word times are seconds from the first sample of the returned audio.

    Both services intermittently hand back nothing at all for a line they
    rendered happily a moment earlier. One dropped request would otherwise
    abandon a run of dozens of slots, so retry before giving up.
    """
    if not text or not text.strip():
        return np.zeros(0, dtype=np.float32), []
    last = None
    for attempt in range(tries):
        try:
            if backend == "elevenlabs":
                mp3, marks = _el_render(text, voice, rate_pct)
            else:
                mp3, raw = asyncio.run(
                    _stream(text, resolve_voice(voice), rate_pct, pitch_hz))
                # edge reports 100-nanosecond ticks; normalise to seconds so the
                # two backends hand back the same shape
                marks = [(m["text"], m["offset"] / 1e7,
                          (m["offset"] + m["duration"]) / 1e7) for m in raw]
            if mp3:
                break
            last = RuntimeError("empty audio")
        except Exception as e:                       # transient socket or service
            last = e
        time.sleep(0.6 * (attempt + 1))
    else:
        raise RuntimeError("text-to-speech failed after %d tries for %r: %s"
                           % (tries, text[:60], last))
    audio, lead = _trim(_decode(mp3, sr), sr)
    return audio, [(w, max(0.0, a - lead), max(0.0, b - lead)) for w, a, b in marks]


def rate_limits(backend="edge"):
    """How far each backend will let you push the speaking rate, in percent.

    edge takes a rate directly. ElevenLabs takes a `speed` multiplier capped at
    0.7-1.2, which is the same thing expressed as -30%..+20% -- noticeably less
    room to compress a line that has run long.
    """
    if backend == "elevenlabs":
        return (EL_SPEED_LO - 1.0) * 100.0, (EL_SPEED_HI - 1.0) * 100.0
    return -25.0, 45.0


def rate_for(natural_dur, target_dur, lo=None, hi=None, backend="edge"):
    """Speaking-rate percentage that turns natural_dur into target_dur.

    Duration goes as 1/(1+r), so r = natural/target - 1. Clamped, because past
    the limits the voice starts clipping its own consonants at one end and
    drawling at the other.
    """
    if target_dur <= 0 or natural_dur <= 0:
        return 0.0
    dlo, dhi = rate_limits(backend)
    lo = dlo if lo is None else lo
    hi = dhi if hi is None else hi
    return max(lo, min(hi, (natural_dur / target_dur - 1.0) * 100.0))


def write_wav(path, x, sr=SR):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--say")
    ap.add_argument("--out")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--rate", type=float, default=0.0, help="speaking rate %%")
    ap.add_argument("--pitch", type=float, default=0.0, help="semitone-ish Hz shift")
    ap.add_argument("--fit", type=float, help="re-render to hit this many seconds")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--filter", default="en-")
    args = ap.parse_args()

    if args.list_voices:
        vs = asyncio.run(edge_tts.list_voices())
        for v in sorted(vs, key=lambda v: v["ShortName"]):
            if args.filter.lower() in v["ShortName"].lower():
                print("%-38s %-8s %s" % (v["ShortName"], v["Gender"],
                                         v.get("FriendlyName", "")))
        print("\nshortcuts: %s" % ", ".join("%s=%s" % kv for kv in VOICES.items()))
        return
    if not args.say:
        sys.exit("nothing to say: pass --say TEXT or --list-voices")

    audio, words = speak(args.say, args.voice, args.rate, args.pitch)
    dur = audio.size / float(SR)
    if args.fit:
        r = rate_for(dur, args.fit)
        audio, words = speak(args.say, args.voice, r, args.pitch)
        print("fit: %.2fs -> rate %+.0f%% -> %.2fs (target %.2fs)"
              % (dur, r, audio.size / float(SR), args.fit))
        dur = audio.size / float(SR)
    print("%.3fs, %d words" % (dur, len(words)))
    for w, a, b in words:
        print("   %6.2f-%6.2f  %s" % (a, b, w))
    if args.out:
        write_wav(args.out, audio)
        print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
