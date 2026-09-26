"""Audio for sketch films: a sampled-instrument score player, a synthesised SFX kit, drums, a
convolution reverb, speech ducking and an EBU R128 master.

Everything is data-driven: the score is `score.json`, the sound cues `sfx.json`, the mix a block
in `sketch.json`. Nothing here knows a particular film.

Instruments are FluidR3 GM (MIT) notes rendered by gleitz/midi-js-soundfonts, fetched on demand
into `models/soundfonts/FluidR3_GM/<instrument>/<note>.mp3` (gitignored, shared by every project).

Score notation -- an event list, each one of:
  {"inst": "celesta", "vel": .4, "notes": "1 E6 .5; 1.5 F6 .5; 2 C4+E4+G4 1 .3"}
      beat, note(s) joined by '+', duration in beats, optional per-note velocity
      optional: "transpose": 12, "swell": [from, to], "humanize": false
  {"type": "strum", "at": 22, "chord": "F3+A3+C4+F4+A4", "vel": .55,
   "pattern": "bar"|"half"|"once"|"up", "inst": "acoustic_guitar_nylon"}
  {"type": "gliss", "from": 23.45, "to": 24.2, "lo": "C4", "hi": "C7", "v0": .18, "v1": .42,
   "root": "F", "scale": "major"}
  {"type": "roll", "inst": "timpani", "note": "C2", "from": 44, "to": 47.4, "step": .125,
   "v0": .12, "v1": .67}
  {"type": "drums", "from": 0, "bars": 8, "beats_per_bar": 4, "steps": 16, "vel": .8,
   "kit": {"kick": "x...x...x...x...", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."}}
      step chars: x = hit, X = accent, o = soft, . = rest

Not an entry script: imported by sketch-audio.py and check-sketch.py.
"""

import functools
import json
import math
import os
import re
import subprocess
import urllib.request

import numpy as np
from scipy import signal

import _env
from _sketch import SR, decode

SOUNDFONT = "models/soundfonts/FluidR3_GM"
SOUNDFONT_URL = (
    "https://cdn.jsdelivr.net/gh/gleitz/midi-js-soundfonts@gh-pages/FluidR3_GM/%s-mp3/%s.mp3"
)
# The 128 General MIDI instruments as the soundfont names them: the only names a score may use,
# since each becomes a folder in the shared cache and part of a download URL
GM = (
    "acoustic_grand_piano bright_acoustic_piano electric_grand_piano honkytonk_piano "
    "electric_piano_1 electric_piano_2 harpsichord clavinet celesta glockenspiel music_box "
    "vibraphone marimba xylophone tubular_bells dulcimer drawbar_organ percussive_organ "
    "rock_organ church_organ reed_organ accordion harmonica tango_accordion "
    "acoustic_guitar_nylon acoustic_guitar_steel electric_guitar_jazz electric_guitar_clean "
    "electric_guitar_muted overdriven_guitar distortion_guitar guitar_harmonics acoustic_bass "
    "electric_bass_finger electric_bass_pick fretless_bass slap_bass_1 slap_bass_2 synth_bass_1 "
    "synth_bass_2 violin viola cello contrabass tremolo_strings pizzicato_strings "
    "orchestral_harp timpani string_ensemble_1 string_ensemble_2 synth_strings_1 "
    "synth_strings_2 choir_aahs voice_oohs synth_choir orchestra_hit trumpet trombone tuba "
    "muted_trumpet french_horn brass_section synth_brass_1 synth_brass_2 soprano_sax alto_sax "
    "tenor_sax baritone_sax oboe english_horn bassoon clarinet piccolo flute recorder pan_flute "
    "blown_bottle shakuhachi whistle ocarina lead_1_square lead_2_sawtooth lead_3_calliope "
    "lead_4_chiff lead_5_charang lead_6_voice lead_7_fifths lead_8_bass__lead pad_1_new_age "
    "pad_2_warm pad_3_polysynth pad_4_choir pad_5_bowed pad_6_metallic pad_7_halo pad_8_sweep "
    "fx_1_rain fx_2_soundtrack fx_3_crystal fx_4_atmosphere fx_5_brightness fx_6_goblins "
    "fx_7_echoes fx_8_scifi sitar banjo shamisen koto kalimba bagpipe fiddle shanai tinkle_bell "
    "agogo steel_drums woodblock taiko_drum melodic_tom synth_drum reverse_cymbal "
    "guitar_fret_noise breath_noise seashore bird_tweet telephone_ring helicopter applause gunshot"
).split()
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "penta": (0, 2, 4, 7, 9),
}

# gain, pan, reverb send, release (s). Anything not listed gets DEFAULT_INS.
DEFAULT_INS = dict(g=0.25, pan=0.0, send=0.3, rel=0.5)
INSTRUMENTS = {
    "music_box": dict(g=0.26, pan=-0.25, send=0.35, rel=1.2),
    "celesta": dict(g=0.30, pan=0.28, send=0.40, rel=1.0),
    "glockenspiel": dict(g=0.22, pan=0.32, send=0.35, rel=1.2),
    "vibraphone": dict(g=0.26, pan=0.3, send=0.4, rel=1.2),
    "string_ensemble_1": dict(g=0.20, pan=0.0, send=0.50, rel=0.7),
    "pizzicato_strings": dict(g=0.42, pan=-0.12, send=0.25, rel=0.25),
    "acoustic_guitar_nylon": dict(g=0.24, pan=-0.38, send=0.22, rel=0.3),
    "acoustic_guitar_steel": dict(g=0.22, pan=-0.35, send=0.22, rel=0.35),
    "acoustic_grand_piano": dict(g=0.30, pan=0.1, send=0.35, rel=0.9),
    "electric_piano_1": dict(g=0.26, pan=-0.15, send=0.3, rel=0.7),
    "electric_bass_finger": dict(g=0.40, pan=0.0, send=0.05, rel=0.25),
    "acoustic_bass": dict(g=0.38, pan=0.0, send=0.15, rel=0.4),
    "pad_2_warm": dict(g=0.16, pan=0.0, send=0.55, rel=1.0),
    "clarinet": dict(g=0.26, pan=0.18, send=0.30, rel=0.25),
    "bassoon": dict(g=0.34, pan=-0.18, send=0.25, rel=0.25),
    "flute": dict(g=0.24, pan=0.22, send=0.38, rel=0.3),
    "marimba": dict(g=0.24, pan=0.38, send=0.22, rel=0.5),
    "timpani": dict(g=0.50, pan=0.0, send=0.40, rel=1.2),
    "french_horn": dict(g=0.24, pan=-0.25, send=0.45, rel=0.5),
    "orchestral_harp": dict(g=0.28, pan=-0.32, send=0.45, rel=1.4),
    "xylophone": dict(g=0.22, pan=0.20, send=0.20, rel=0.4),
    "woodblock": dict(g=0.30, pan=0.10, send=0.15, rel=0.2),
    "tinkle_bell": dict(g=0.18, pan=0.30, send=0.40, rel=1.0),
}


# ------------------------------------------------------------------ notes
def M(s):
    """'F#4' / 'Bb3' / 60 -> midi number."""
    if isinstance(s, (int, np.integer)):
        return int(s)
    n, o = s[:-1], int(s[-1])
    n = SHARP.get(n, n)
    return NAMES.index(n) + (o + 1) * 12


def mname(m):
    return NAMES[m % 12] + str(m // 12 - 1)


def parse_notes(spec):
    """'1 E6 .5; 2 C4+E4 1 .3' -> [(beat, [midi...], dur, vel|None)]"""
    out = []
    for part in re.split(r"[;|]", spec):
        f = part.split()
        if not f:
            continue
        if len(f) < 3:
            raise ValueError("bad note %r: need 'beat note dur [vel]'" % part.strip())
        vel = float(f[3]) if len(f) > 3 else None
        out.append((float(f[0]), [M(x) for x in f[1].split("+")], float(f[2]), vel))
    return out


# ------------------------------------------------------------------ samples
def sample_path(inst, m):
    if inst not in GM:
        raise ValueError("unknown instrument %r: use a General MIDI name such as celesta" % inst)
    return _env.resolve(os.path.join(SOUNDFONT, inst, mname(m) + ".mp3"))


def needed_samples(events):
    """{(inst, midi)} the score will play (drums are synthesised and need none)."""
    return {(e[0], e[1]) for e in events if e[0] != "drum"}


def fetch_samples(pairs, log=print):
    """Download missing notes; a note the soundfont lacks is later re-pitched from a neighbour."""
    missing = [(i, m) for i, m in sorted(pairs) if not os.path.exists(sample_path(i, m))]
    got = 0
    for inst, m in missing:
        p = sample_path(inst, m)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(SOUNDFONT_URL % (inst, mname(m)), timeout=30) as r:
                    data = r.read()
                # the cache is shared by every run on the machine: a file of our own, then a
                # rename, so a run reading at the same moment never sees half a note
                os.makedirs(os.path.dirname(p), exist_ok=True)
                tmp = "%s.%d.tmp" % (p, os.getpid())
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, p)
                got += 1
                break
            except Exception as e:  # noqa: BLE001 -- the CDN 404s the odd note; neighbours cover it
                if "404" in str(e) or attempt == 2:
                    log("  no sample %s %s (%s) -- will re-pitch a neighbour" % (inst, mname(m), e))
                    break
    return len(missing), got


@functools.lru_cache(None)
def sample(inst, m):
    p, shift = sample_path(inst, m), 0
    if not os.path.exists(p):
        for d in (1, -1, 2, -2, 3, -3):
            if os.path.exists(sample_path(inst, m + d)):
                p, shift = sample_path(inst, m + d), d
                break
        else:
            raise FileNotFoundError(
                "no %s sample within 3 semitones of %s -- run sketch-audio.py first"
                % (inst, mname(m))
            )
    x = decode(p)
    if shift:
        x = signal.resample(x, int(len(x) * 2 ** (shift / 12)))
    a = np.abs(x)
    i0 = int(np.argmax(a > a.max() * 10 ** (-45 / 20)))
    x = x[max(0, i0 - 24) :]
    return x / (np.sqrt(np.mean(x[: int(0.3 * SR)] ** 2)) + 1e-9) * 0.1


# ------------------------------------------------------------------ score -> events
def score_events(score):
    """Flatten score.json into (inst, midi, beat, dur_beats, vel, extra) tuples.

    Kit hits come back as ("drum", piece, ...) -- synthesised, no sample needed.
    """
    ev = []
    for e in score["events"]:
        typ = e.get("type", "notes")
        if typ == "notes":
            tr = e.get("transpose", 0)
            for b, ms, d, v in parse_notes(e["notes"]):
                for m in ms:
                    ev.append(
                        (
                            e["inst"],
                            m + tr,
                            b,
                            d,
                            v if v is not None else e.get("vel", 0.5),
                            {k: e[k] for k in ("swell", "humanize") if k in e},
                        )
                    )
        elif typ == "strum":
            inst, chord, vel = (
                e.get("inst", "acoustic_guitar_nylon"),
                [M(x) for x in e["chord"].split("+")],
                e.get("vel", 0.5),
            )
            pat = {
                "bar": [
                    (0, 1, 0),
                    (1, 0.75, 0),
                    (1.5, 0.6, 1),
                    (2.5, 0.65, 1),
                    (3, 0.8, 0),
                    (3.5, 0.6, 1),
                ],
                "half": [(0, 1, 0), (1, 0.75, 0), (1.5, 0.6, 1)],
                "once": [(0, 1, 0)],
                "up": [(0, 1, 1)],
            }[e.get("pattern", "bar")]
            spread = e.get("spread", 0.012) / (60.0 / score.get("bpm", 120))
            for off, vv, up in pat:
                ns = list(reversed(chord)) if up else chord
                for i, m in enumerate(ns):
                    ev.append(
                        (
                            inst,
                            m,
                            e["at"] + off + i * spread,
                            e.get("dur", 0.9),
                            vel * vv * (0.85 if up else 1) * (1 - i * 0.04),
                            {},
                        )
                    )
        elif typ == "gliss":
            root = NAMES.index(SHARP.get(e.get("root", "C"), e.get("root", "C")))
            sc = SCALES[e.get("scale", "major")]
            notes = [m for m in range(M(e["lo"]), M(e["hi"]) + 1) if (m - root) % 12 in sc]
            for i, m in enumerate(notes):
                u = i / max(1, len(notes) - 1)
                ev.append(
                    (
                        e.get("inst", "orchestral_harp"),
                        m,
                        e["from"] + (e["to"] - e["from"]) * u,
                        e.get("dur", 1.5),
                        e["v0"] + (e["v1"] - e["v0"]) * u,
                        {},
                    )
                )
        elif typ == "roll":
            n = int(round((e["to"] - e["from"]) / e.get("step", 0.125)))
            for i in range(n + 1):
                u = i / max(1, n)
                ev.append(
                    (
                        e["inst"],
                        M(e["note"]),
                        e["from"] + i * e.get("step", 0.125),
                        e.get("dur", 0.2),
                        e["v0"] + (e["v1"] - e["v0"]) * u**1.6,
                        {},
                    )
                )
        elif typ == "arp":
            for i, nt in enumerate(e["notes"].split()):
                ev.append(
                    (
                        e["inst"],
                        M(nt),
                        e["at"] + i * e.get("step", 0.25),
                        e.get("dur", 1.0),
                        e.get("vel", 0.4),
                        {},
                    )
                )
        elif typ == "drums":
            bpb, steps = e.get("beats_per_bar", 4), e.get("steps", 16)
            for bar in range(e.get("bars", 1)):
                for piece, pat in e["kit"].items():
                    for i, ch in enumerate(pat.replace(" ", "")):
                        if ch in "xXo":
                            v = (
                                {"x": 0.8, "X": 1.0, "o": 0.45}[ch]
                                * e.get("vel", 0.8)
                                * e.get("gains", {}).get(piece, 1.0)
                            )
                            ev.append(
                                (
                                    "drum",
                                    piece,
                                    e["from"] + bar * bpb + i * bpb / steps,
                                    0.25,
                                    v,
                                    {},
                                )
                            )
        else:
            raise ValueError("unknown score event type %r" % typ)
    return ev


# ------------------------------------------------------------------ mixing primitives
def pan_gains(p):
    a = (max(-1.0, min(1.0, p)) + 1) * math.pi / 4
    return math.cos(a), math.sin(a)


def add(buf, x, t, pan=0.0, gain=1.0):
    i0 = int(round(t * SR))
    if i0 >= buf.shape[1] or i0 + len(x) <= 0:
        return
    if i0 < 0:
        x, i0 = x[-i0:], 0
    n = min(len(x), buf.shape[1] - i0)
    lg, rg = pan_gains(pan)
    buf[0, i0 : i0 + n] += x[:n] * lg * gain
    buf[1, i0 : i0 + n] += x[:n] * rg * gain


def make_ir(sec=2.3, seed=3, damp=5500):
    n = int(sec * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    ir = np.stack([rng.standard_normal(n) * np.exp(-t * (6.9 / sec)) for _ in range(2)])
    ir = signal.sosfilt(signal.butter(2, damp, "low", fs=SR, output="sos"), ir, axis=1)
    ir = signal.sosfilt(signal.butter(1, 180, "high", fs=SR, output="sos"), ir, axis=1)
    ir[:, : int(0.018 * SR)] = 0
    return ir / np.sqrt((ir**2).sum(axis=1, keepdims=True))


def reverb(x, ir):
    return np.stack([signal.fftconvolve(x[c], ir[c])[: x.shape[1]] for c in range(2)])


# ------------------------------------------------------------------ synth building blocks
RNG = np.random.default_rng(7)


def env_exp(n, tau):
    return np.exp(-np.arange(n) / SR / tau)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(
        signal.butter(order, [lo, min(hi, SR / 2 - 100)], "band", fs=SR, output="sos"), x
    )


def lp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f, "high", fs=SR, output="sos"), x)


def noise(sec, rng=None):
    return (rng or RNG).standard_normal(int(sec * SR))


def sweep_sine(f0, f1, sec, curve=1.0):
    n = int(sec * SR)
    u = np.linspace(0, 1, n) ** curve
    return np.sin(2 * np.pi * np.cumsum(f0 * (f1 / f0) ** u) / SR)


def svf_sweep(x, f0, f1, q=1.5, curve=1.0):
    """Time-varying band-pass (Chamberlin state-variable filter) -- the whoosh engine."""
    n = len(x)
    fc = f0 * (f1 / f0) ** (np.linspace(0, 1, n) ** curve)
    F = 2 * np.sin(np.pi * np.minimum(fc, SR / 6) / SR)
    qq = 1 / q
    low = band = 0.0
    out = np.empty(n)
    for i in range(n):
        high = x[i] - low - qq * band
        band += F[i] * high
        low += F[i] * band
        out[i] = band
    return out


# ------------------------------------------------------------------ SFX kit (mono samples each)
def fx_whoosh(sec=0.6, f0=300, f1=2600, peak=0.55, curve=1.0, q=1.2):
    x = svf_sweep(noise(sec), f0, f1, q=q, curve=curve)
    u = np.linspace(0, 1, len(x))
    return x * np.where(u < peak, (u / peak) ** 2, ((1 - u) / (1 - peak)) ** 1.6)


def fx_pop(f0=900, f1=260, sec=0.07):
    y = sweep_sine(f0, f1, sec, 0.5) * env_exp(int(sec * SR), sec / 3.5)
    c = hp(noise(0.004), 2000) * 0.3
    y[: len(c)] += c
    return y


def fx_boing(f0=240, f1=520, sec=0.38):
    n = int(sec * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / sec) * (1 + 0.06 * np.sin(2 * np.pi * 18 * t))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * np.minimum(1, t * 200)


def fx_thunk(sec=0.45):
    y = sweep_sine(120, 45, sec, 0.4) * env_exp(int(sec * SR), 0.09)
    y = y + lp(noise(sec), 900) * env_exp(int(sec * SR), 0.025) * 0.8
    slap = bp(noise(0.05), 1500, 6000) * env_exp(int(0.05 * SR), 0.008) * 0.6
    y[: len(slap)] += slap
    return y


def fx_clink(freqs=(2640, 3960, 5280, 7390), sec=0.8, tau=0.18):
    t = np.arange(int(sec * SR)) / SR
    y = sum(
        np.sin(2 * np.pi * f * t + i) * np.exp(-t / (tau * (1 - i * 0.15))) / (1 + i * 0.6)
        for i, f in enumerate(freqs)
    )
    return y + hp(noise(sec), 4000) * np.exp(-t * 90) * 0.4


def fx_crash(sec=2.2):
    t = np.arange(int(sec * SR)) / SR
    return (
        hp(noise(sec), 4500) * (np.exp(-t * 2.2) * 0.9 + np.exp(-t * 18) * 0.6)
        + bp(noise(sec), 300, 1200) * np.exp(-t * 12) * 0.5
    )


def fx_rumble(sec=0.6):
    t = np.arange(int(sec * SR)) / SR
    return (
        lp(noise(sec), 160, 4) * (t / sec) ** 1.5 * 3
        + bp(noise(sec), 200, 900) * (t / sec) ** 2 * 0.3
    )


def fx_boom(sec=1.0):
    t = np.arange(int(sec * SR)) / SR
    return (
        sweep_sine(110, 32, sec, 0.3) * np.exp(-t * 4) + lp(noise(sec), 300) * np.exp(-t * 9) * 0.8
    )


def fx_zip(sec=0.22, f0=300, f1=2200):
    w = np.hanning(int(sec * SR))
    return sweep_sine(f0, f1, sec, 1.4) * w * 0.6 + svf_sweep(noise(sec), 800, 6000, 2) * w * 0.5


def fx_blip(f=1320, sec=0.09):
    t = np.arange(int(sec * SR)) / SR
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 40)


def fx_click(sec=0.006, lo=1800, hi=6000):
    return bp(noise(sec), lo, hi) * np.hanning(int(sec * SR))


def fx_scribble(sec=1.0, seed=0, dens=1.0):
    """Pencil / pen on paper: band-passed grain modulated into irregular strokes."""
    rng = np.random.default_rng(seed)
    n = int(sec * SR)
    x = bp(rng.standard_normal(n), 1400, 7000) + bp(rng.standard_normal(n), 300, 1200) * 0.25
    env = np.zeros(n)
    pos = 0
    while pos < n:
        L = int(rng.uniform(0.06, 0.22) * SR)
        g = int(rng.uniform(0.01, 0.06) * SR / dens)
        seg = np.sin(np.linspace(0, np.pi, min(L, n - pos))) ** 0.7 * rng.uniform(0.5, 1)
        env[pos : pos + len(seg)] = seg
        pos += L + g
    am = 1 + 0.5 * np.sin(2 * np.pi * rng.uniform(18, 30) * np.arange(n) / SR + rng.uniform(0, 6))
    return x * env * am * (1 + 0.6 * np.abs(lp(rng.standard_normal(n), 60)))


def fx_crinkle(sec=0.25, dens=260, seed=1):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(sec * SR))
    for _ in range(int(sec * dens)):
        i = rng.integers(0, max(1, len(y) - 400))
        L = int(rng.integers(60, 400))
        y[i : i + L] += (
            bp(rng.standard_normal(L), 1200, 9000)
            * np.hanning(L)[: len(y[i : i + L])]
            * rng.uniform(0.2, 1)
        )
    return y * np.hanning(len(y)) ** 0.3


def fx_keys(sec=2.0, rate=11, seed=5):
    """Keyboard typing: clicks with a soft thump, at a jittered rate per second."""
    rng = np.random.default_rng(seed)
    y = np.zeros(int(sec * SR))
    t = 0.0
    while t < sec - 0.03:
        c = fx_click(0.008, 1500, 5500) * rng.uniform(0.4, 1)
        th = lp(rng.standard_normal(int(0.015 * SR)), 500) * np.hanning(int(0.015 * SR)) * 0.6
        i = int(t * SR)
        y[i : i + len(c)] += c
        y[i : i + len(th)] += th
        t += rng.exponential(1 / rate) + 0.025
    return y


def fx_shimmer(sec=1.0, f0=400, f1=4000):
    return svf_sweep(noise(sec), f0, f1, 3) * np.hanning(int(sec * SR))


def fx_swoosh_soft(sec=0.5):
    """A gentle UI swipe (for clean-style cards sliding in)."""
    return fx_whoosh(sec, 900, 3200, 0.4, 1.0, 0.9) * 0.8


def fx_tick(sec=0.03):
    """A precise UI tick (a field landing, a checkbox)."""
    t = np.arange(int(sec * SR)) / SR
    return over(np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 260), fx_click(0.004, 3000, 9000), 0.4)


def fx_chime(freqs=(1568, 2349, 3136), sec=1.4, tau=0.45):
    """A clean success chime (three soft partials)."""
    t = np.arange(int(sec * SR)) / SR
    return sum(
        np.sin(2 * np.pi * f * t) * np.exp(-t / tau) * np.minimum(1, t * 400) / (1 + i)
        for i, f in enumerate(freqs)
    )


def fx_siren(sec=3.0, lo=420, hi=760, period=1.5, vib=5.5):
    """A civil-defence siren, softened for a film: a sine wail rising and falling between LO
    and HI every PERIOD seconds, a little vibrato, two soft upper partials, fade in and out.
    Recognisable without the full-scale horn's harshness -- for children, keep it quiet."""
    t = np.arange(int(sec * SR)) / SR
    u = 0.5 - 0.5 * np.cos(2 * np.pi * t / period)  # 0 -> 1 -> 0 each period
    f = lo + (hi - lo) * u**0.8 + 6 * np.sin(2 * np.pi * vib * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.28 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
    env = np.minimum(1, t / 0.35) * np.minimum(1, (sec - t) / 0.6)
    return lp(x * env, 3500) * 0.6


FX = {n[3:]: f for n, f in globals().items() if n.startswith("fx_")}


# ------------------------------------------------------------ drums (synthesised; a light bed)
def over(a, b, g=1.0):
    """A with b added from its first sample (b may be shorter)."""
    a = a.copy()
    a[: len(b)] += b[: len(a)] * g
    return a


def drum(piece):
    rng = np.random.default_rng(sum(map(ord, piece)))  # stable across runs (str hash is salted)
    if piece == "kick":
        sec = 0.35
        t = np.arange(int(sec * SR)) / SR
        return over(
            sweep_sine(150, 45, sec, 0.35) * np.exp(-t * 11), fx_click(0.004, 1000, 4000), 0.3
        )
    if piece == "snare":
        sec = 0.25
        t = np.arange(int(sec * SR)) / SR
        return (
            bp(noise(sec, rng), 1200, 8000) * np.exp(-t * 22) * 0.8
            + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.6
        )
    if piece == "clap":
        sec = 0.3
        t = np.arange(int(sec * SR)) / SR
        env = (
            sum(np.exp(-np.maximum(0, t - d) * 90) * (t >= d) for d in (0, 0.011, 0.023))
            + np.exp(-t * 14) * 0.5
        )
        return bp(noise(sec, rng), 900, 5000) * env * 0.7
    if piece in ("hat", "openhat"):
        sec = 0.05 if piece == "hat" else 0.35
        t = np.arange(int(sec * SR)) / SR
        return hp(noise(sec, rng), 7000) * np.exp(-t * (90 if piece == "hat" else 9)) * 0.7
    if piece == "shaker":
        sec = 0.09
        return hp(noise(sec, rng), 5000) * np.hanning(int(sec * SR)) * 0.5
    if piece == "rim":
        sec = 0.06
        t = np.arange(int(sec * SR)) / SR
        return over(
            np.sin(2 * np.pi * 1700 * t) * np.exp(-t * 120), fx_click(0.003, 2000, 7000), 0.5
        )
    raise ValueError("unknown drum %r" % piece)


DRUM_PAN = {
    "kick": 0,
    "snare": 0.05,
    "clap": -0.05,
    "hat": 0.3,
    "openhat": 0.3,
    "shaker": -0.35,
    "rim": 0.2,
}


# ------------------------------------------------------------------ render the score
def render_score(score, duration):
    ev = score_events(score)
    bpm = score.get("bpm", 120)
    beat = 60.0 / bpm
    ins = {**INSTRUMENTS, **score.get("instruments", {})}
    n = int(duration * SR)
    dry, wet = np.zeros((2, n)), np.zeros((2, n))
    drums = {}
    for inst, m, b, d, v, kw in ev:
        human = kw.get("humanize", True)
        t = b * beat + (RNG.normal(0, 0.006) if human else 0)
        v = v * (1 + (RNG.normal(0, 0.05) if human else 0))
        if inst == "drum":
            x = drums.setdefault(m, drum(m))
            add(dry, x, t, DRUM_PAN.get(m, 0), score.get("drum_gain", 0.5) * v)
            add(wet, x, t, DRUM_PAN.get(m, 0), score.get("drum_gain", 0.5) * v * 0.08)
            continue
        cfg = {**DEFAULT_INS, **ins.get(inst, {})}
        x = sample(inst, m)
        dur, rel = d * beat, cfg["rel"]
        L = min(len(x), int((dur + rel) * SR))
        y = x[:L].copy()
        r0 = int(dur * SR)
        if r0 < L:
            y[r0:] *= np.linspace(1, 0, L - r0) ** 2
        if "swell" in kw:
            y *= np.linspace(kw["swell"][0], kw["swell"][1], len(y))
        if cfg.get("soft_attack", inst in ("string_ensemble_1", "pad_2_warm")):
            k = min(len(y), int(0.08 * SR))
            y[:k] *= np.linspace(0, 1, k)
        pan = cfg["pan"] + (RNG.normal(0, 0.05) if human else 0)
        add(dry, y, t + (0.012 if inst == "string_ensemble_1" else 0), pan, cfg["g"] * v)
        add(wet, y, t, pan, cfg["g"] * v * cfg["send"])
    return dry, wet, ev


# ------------------------------------------------------------------ SFX cues
def norm(x, db):
    return x / (np.abs(x).max() + 1e-12) * 10 ** (db / 20)


def render_sfx(cues, duration, automation=None):
    """cues: [{"t", "fx", "db", "pan", "send", "args"}]; fx may also be
    "sample" (inst + note or notes/every) or "air" (a track from the film's automation).
    """
    n = int(duration * SR)
    out, wet = np.zeros((2, n)), np.zeros((2, n))

    def put(x, t, db, pan=0.0, send=0.15):
        y = norm(x, db)
        add(out, y, t, pan)
        add(wet, y, t, pan, send)

    for c in cues:
        db, pan, send, a = (
            c.get("db", -24),
            c.get("pan", 0.0),
            c.get("send", 0.15),
            c.get("args", {}),
        )
        times = c.get("times") or [c["t"]]
        for k, t in enumerate(times):
            if c["fx"] == "sample":
                notes = c.get("notes") or [c["note"]]
                for i, nt in enumerate(notes):
                    x = sample(c["inst"], M(nt))[: int(c.get("sec", 1.5) * SR)].copy()
                    x[-int(0.2 * SR) :] *= np.linspace(1, 0, min(len(x), int(0.2 * SR)))
                    put(x, t + i * c.get("every", 0.05), db, pan, send)
            elif c["fx"] == "air":
                tr = (automation or {}).get(c["track"])
                if not tr:
                    raise ValueError(
                        "sfx 'air' needs automation track %r -- run sketch-render.py --automation"
                        % c["track"]
                    )
                ts, sp, pn = np.array(tr["t"]), np.array(tr["speed"]), np.array(tr["pan"])
                L = int((ts[-1] - ts[0] + 0.3) * SR)
                air = svf_sweep(noise(L / SR), a.get("f0", 700), a.get("f1", 1400), a.get("q", 1.0))
                tt = ts[0] + np.arange(L) / SR
                amp = np.interp(tt, ts, sp / sp.max()) ** 1.3 * np.minimum(
                    1, (ts[-1] + 0.3 - tt) / 0.3
                )
                p = np.clip(np.interp(tt, ts, pn), -0.8, 0.8)
                y = norm(air * amp, db)
                i0 = int(ts[0] * SR)
                m = min(L, n - i0)
                out[0, i0 : i0 + m] += (y * np.cos((p + 1) * np.pi / 4))[:m]
                out[1, i0 : i0 + m] += (y * np.sin((p + 1) * np.pi / 4))[:m]
            else:
                f = FX.get(c["fx"])
                if not f:
                    raise ValueError("unknown fx %r (have: %s)" % (c["fx"], ", ".join(sorted(FX))))
                args = dict(a)
                if "seed" in f.__code__.co_varnames and "seed" not in args:
                    args["seed"] = int(t * 1000) + k
                put(f(**args), t, db, pan, send)
    return out, wet


# ------------------------------------------------------------------ voice + ducking
def build_vo(timeline, duration, target_db=-17.0, base=None):
    """base: the manifest's folder, which the line files are relative to (older timelines were
    written relative to the repo root, and still resolve there)."""
    vo = np.zeros(int(duration * SR))
    for L in timeline["lines"]:
        p = L["file"]
        if base and not os.path.isabs(p) and os.path.exists(os.path.join(base, p)):
            p = os.path.join(base, p)
        x = hp(decode(_env.resolve(p)), 70)
        a = np.abs(x)
        act = x[a > a.max() * 0.05]
        x = x / (np.sqrt(np.mean(act**2)) + 1e-9) * 10 ** (target_db / 20)
        i0 = int(L["start"] * SR)
        vo[i0 : i0 + len(x)] += x[: len(vo) - i0]
    return vo


def duck_gain(vo, amount=0.62, attack=0.03, release=0.35, decimate=48):
    """Music gain under the voice: 1 in the gaps, 1-amount under speech; attack/release smoothed.
    Computed at SR/decimate and interpolated back, because the smoother is a Python loop.
    """
    env = np.sqrt(np.maximum(lp(vo**2, 12), 0))
    env = env / (env.max() + 1e-9)
    g = (1 - amount * np.clip(env * 3.2, 0, 1))[::decimate]
    gs = np.empty_like(g)
    cur = 1.0
    sr = SR / decimate
    a, r = 1 - math.exp(-1 / (attack * sr)), 1 - math.exp(-1 / (release * sr))
    for i, tgt in enumerate(g):
        cur += (tgt - cur) * (a if tgt < cur else r)
        gs[i] = cur
    return np.interp(np.arange(len(vo)), np.arange(len(gs)) * decimate, gs)


# ------------------------------------------------------------------ master
def loudnorm(src, dst, lufs=-14.0, tp=-1.5, lra=11):
    """Two-pass EBU R128 to `dst` (24-bit WAV). Returns the measured input stats."""
    r = subprocess.run(  # noqa: PLW1510 -- loudnorm's analysis pass reports on stderr; exit code is not the signal
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            src,
            "-af",
            "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (lufs, tp, lra),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    j = json.loads(r.stderr[r.stderr.rindex("{") : r.stderr.rindex("}") + 1])
    af = (
        "loudnorm=I=%s:TP=%s:LRA=%s:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true,aresample=%d"
        % (
            lufs,
            tp,
            lra,
            j["input_i"],
            j["input_tp"],
            j["input_lra"],
            j["input_thresh"],
            j["target_offset"],
            SR,
        )
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-c:a", "pcm_s24le", dst], check=True
    )
    return j


def measure(path):
    """(integrated LUFS, true peak dBTP) of a file."""
    r = subprocess.run(  # noqa: PLW1510 -- the summary is on stderr; a failure shows as (None, None)
        ["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    s = r.stderr[r.stderr.rfind("Summary:") :]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", s)
    p = re.search(r"Peak:\s+(-?[\d.]+) dBFS", s)
    return (float(i.group(1)) if i else None, float(p.group(1)) if p else None)


def levels_table(stems, step=2.0):
    """Per-window RMS (dBFS) for each named stem -- the balance, readable without listening."""
    names = list(stems)
    n = min(x.shape[-1] for x in stems.values())
    rows = []
    for k in range(int(n / SR / step)):
        a, b = int(k * step * SR), int((k + 1) * step * SR)
        rows.append(
            [k * step]
            + [
                20 * np.log10(np.sqrt(np.mean(np.asarray(stems[s])[..., a:b] ** 2)) + 1e-12)
                for s in names
            ]
        )
    return names, rows
