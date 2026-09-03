#!/usr/bin/env python
"""Turn one encoding *intent* into the ffmpeg keys the chosen encoder speaks.

Every render script here used to spell its own encoder line, and all of them
spelled the same NVENC one:

    -c:v h264_nvenc -preset p5 -rc vbr -cq 21 -b:v 0 -maxrate 16M ...

which is six copies of a decision that is not theirs to make. Changing
`render.encoder` to `libx264` on a machine with no NVIDIA card did not help,
because `-preset p5` and `-rc vbr` travelled with it -- x264 has no preset
called `p5` and AMF has no rate-control mode called `vbr`, so both die on
`invalid preset 'p5'`. The encoder was configurable; the keys around it were
not, which made the configuration a lie.

So: a manifest states quality, speed and bitrate ceilings, and this module
renders them into whichever family the encoder belongs to.

    nvenc     -preset p5   -rc vbr  -cq N -b:v 0
    amf       -quality quality      -rc qvbr -qvbr_quality_level N
    software  -preset medium        -crf N

`speed` is carried on NVENC's own p1..p7 scale, because every preset and
manifest already committed to this repo speaks it. A `preset` of `p5` written
before this module existed therefore still means what it meant -- it is
translated into the target family rather than ignored, and never passed
through to an encoder that would reject it.

Availability is probed by *encoding a frame*, not by reading `ffmpeg
-encoders`. On the machine this module was written for, `-encoders` lists
`h264_nvenc` quite happily and the encoder then fails with `Cannot load
nvcuda.dll`: the build has NVENC compiled in, the box has no NVIDIA driver.
A doctor that greps the encoder list reports that machine healthy and every
render on it fails.

Invoke as:  import _encode  (a library; scripts/check-encode.py is its test)
"""
import os
import sys
import json
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT
ENV = _env.ENV

# An explicit encoder -- a --encoder flag or this variable -- is honoured
# strictly: you named it, so a failure to run it is an error rather than a
# substitution. One written into a manifest or a caption preset is a portable
# default that may be substituted, because those files are committed and get
# read on machines their author never saw.
ENCODER_VAR = "VIDEDIT_ENCODER"
STRICT_VAR = "VIDEDIT_ENCODER_STRICT"

# Tried in order when nothing names an encoder. h264 before hevc because every
# consumer of these renders (YouTube, the comparators, the browsers) takes it,
# and hardware before software because a film is minutes either way on a GPU
# and the better part of an hour on a CPU.
CANDIDATES = ("h264_nvenc", "h264_amf", "h264_qsv", "libx264")

DEFAULT_SPEED = 5               # p5: what every render script defaulted to
DEFAULT_QUALITY = 21

# The frame usable() encodes to prove an encoder really runs. See its
# docstring: this is a measured floor, not a round number.
PROBE_SIZE = "320x240"


# --------------------------------------------------------------------------
# families
# --------------------------------------------------------------------------

def family_of(encoder):
    """Which key vocabulary this encoder speaks.

    Matched on the suffix rather than a fixed list, so `hevc_amf` and
    `av1_amf` are known without being enumerated -- the keys are a property of
    the vendor's wrapper, not of the codec.
    """
    e = (encoder or "").strip().lower()
    for suffix, fam in (("_nvenc", "nvenc"), ("_amf", "amf"),
                        ("_qsv", "qsv"), ("_vaapi", "vaapi")):
        if e.endswith(suffix):
            return fam
    if e.startswith("lib") or e in ("mpeg4", "h264", "hevc"):
        return "software"
    raise ValueError(
        "unknown encoder %r -- this module knows the *_nvenc, *_amf, *_qsv, "
        "*_vaapi and lib* families. Add it to family_of() and to SPEED/RATE "
        "below rather than spelling its keys at a call site." % encoder)


# A speed tier, 1 (fastest) to 7 (slowest/best), rendered into each family's
# own vocabulary.
#
# AMF is given by NAME and not by number on purpose: h264_amf's presets run
# 0..3 and hevc_amf's run 0..15, but both accept the same four names, so a
# number correct for one is a different setting on the other. Measured on
# ffmpeg 9.0.1 -- `ffmpeg -h encoder=hevc_amf` lists quality=0, balanced=5,
# speed=10, high_quality=15.
SPEED = {
    "nvenc":    lambda t: ["-preset", "p%d" % t],
    "amf":      lambda t: ["-quality", ("speed" if t <= 2 else
                                        "balanced" if t <= 5 else
                                        "quality" if t == 6 else
                                        "high_quality")],
    "qsv":      lambda t: ["-preset", ("veryfast" if t <= 2 else
                                       "faster" if t == 3 else
                                       "fast" if t == 4 else
                                       "medium" if t == 5 else
                                       "slow" if t == 6 else "veryslow")],
    "vaapi":    lambda t: [],           # VAAPI has no portable speed control
    "software": lambda t: ["-preset", {1: "ultrafast", 2: "veryfast",
                                       3: "faster", 4: "fast", 5: "medium",
                                       6: "slow", 7: "slower"}[t]],
}

# Quality-targeted rate control. The number a manifest writes is QP-shaped and
# runs 0..51: SMALLER MEANS BETTER, everywhere, because that is what -cq and
# -crf mean. Each family is then responsible for expressing that in its own
# terms -- and AMF's runs backwards, which is why amf_quality() exists rather
# than the number being handed straight over.
#
# `-b:v 0` is NVENC-only and load-bearing there: without it NVENC silently
# ignores -cq and encodes to its default average bitrate (README ## Gotchas).
# AMF's qvbr and x264's crf need no such thing, and handing `-b:v 0` to AMF
# asks for a zero-bitrate VBR target on an encoder that already has a quality
# target.
QP_MAX = 51


def amf_quality(q):
    """AMF's quality level from this repo's QP-shaped number, INVERTED.

    The one thing every other encoder here agrees on is that a smaller number
    means better pictures: NVENC's -cq, x264's -crf and a raw QP all run that
    way. AMF's `qvbr_quality_level` does NOT. Measured on this Vega 10, VMAF
    against a crf-12 reference over 20 s of 1080p30 of real footage:

        qvbr 10 -> VMAF 81.9 (505 KB)     qvbr 34 -> VMAF 92.9 (1875 KB)
        qvbr 21 -> VMAF 88.3 (1130 KB)    qvbr 40 -> VMAF 93.6 (2240 KB)
        qvbr 28 -> VMAF 91.7 (1527 KB)    qvbr 46 -> VMAF 94.6 (2781 KB)

    Monotonic across the whole range, and the opposite way round. Passing the
    number straight through -- which is what this module did first -- makes
    `cq: 16`, the setting a conform uses precisely because it wants the HIGHEST
    quality, ask AMF for nearly its lowest. Every AMF render came out quietly
    worse than its manifest asked for, and nothing said so: the file was
    smaller, which reads as efficiency rather than as loss.

    So invert. `51 - q` keeps the repo's meaning (smaller q, better picture)
    and lands the corpus's settings at VMAF 92-93, which is delivery quality.
    Note AMF still sits ~2 VMAF below x264 at the same nominal number on this
    hardware -- one linear map cannot make two encoders' scales identical, and
    the direction is the part that was actually broken.
    """
    return max(0, min(QP_MAX, QP_MAX - int(q)))


RATE = {
    "nvenc":    lambda q: ["-rc", "vbr", "-cq", str(q), "-b:v", "0"],
    "amf":      lambda q: ["-rc", "qvbr",
                           "-qvbr_quality_level", str(amf_quality(q))],
    "qsv":      lambda q: ["-global_quality", str(q), "-look_ahead", "1"],
    "vaapi":    lambda q: ["-rc_mode", "CQP", "-qp", str(q)],
    "software": lambda q: ["-crf", str(q)],
}

# The extra quality knobs, which exist only where they were measured to do
# something.
#
# NVENC's block is the one run-captions.py has always used. AMF's is EMPTY and
# that is a measurement, not an oversight: on the Vega 10 this was written
# against, `-vbaq 1 -preanalysis 1` cost 26% more wall clock (7.26 s against
# 5.76 s on 5 s of 1080p30) and moved the output by 8 bytes in 3.09 Mbps --
# VCN 1.0 ignores both. Re-measure on RDNA before adding them back.
#
# `-bf` is nvenc/software only for the same reason: this GPU answers `-bf 3`
# with "The current GPU in use does not support H.264 B-frame encoding",
# proceeds without them, and the flag buys nothing but a warning.
TUNING = {
    "nvenc":    lambda aq: ["-tune", "hq", "-rc-lookahead", "32",
                            "-spatial-aq", "1", "-aq-strength", str(aq),
                            "-temporal-aq", "1", "-bf", "3"],
    "amf":      lambda aq: [],
    "qsv":      lambda aq: [],
    "vaapi":    lambda aq: [],
    "software": lambda aq: ["-bf", "3"],
}


# --------------------------------------------------------------------------
# speed
# --------------------------------------------------------------------------

# Every spelling of a speed setting this repo has ever written down, on one
# scale. The point is that a committed `"preset": "p5"` keeps meaning p5 after
# the encoder changes under it, instead of reaching an encoder that rejects it.
_TIERS = {
    "ultrafast": 1, "superfast": 1, "fastest": 1,
    "veryfast": 2, "speed": 2, "faster": 3, "fast": 4,
    "medium": 5, "balanced": 5,
    "slow": 6, "quality": 6,
    "slower": 7, "veryslow": 7, "placebo": 7, "high_quality": 7, "best": 7,
}


def codec_of(encoder):
    """h264 / hevc / av1 / other, from the encoder name.

    A second axis, and not the same one as family_of(): `profile` and `level`
    belong to the CODEC, while `preset` and `-rc` belong to the vendor's
    wrapper. Conflating them is what made hevc_amf reject a caption render --
    `-profile:v high` is an H.264 profile and HEVC has never had one.
    """
    e = (encoder or "").strip().lower()
    if "264" in e:
        return "h264"
    if "265" in e or "hevc" in e:
        return "hevc"
    if "av1" in e:
        return "av1"
    return "other"


def profile_args(encoder, profile, level):
    """Profile and level, or nothing, depending on what the codec has.

    The values in this repo's configs are H.264 ones ("high", "4.2") because
    that is what every render here has always been. They are compatibility
    hints -- they exist so an old player accepts the file, not to change the
    picture -- so on a codec that has no such profile they are dropped rather
    than translated into a guess. Caught by scripts/check-encode.py, which
    rendered a caption pass through hevc_amf and got "Invalid argument".
    """
    codec = codec_of(encoder)
    out = []
    if codec == "h264":
        if profile:
            out += ["-profile:v", str(profile)]
        if level:
            out += ["-level", str(level)]
    elif codec == "hevc" and profile:
        # HEVC's own names. "high" is not one; main is the honest equivalent
        # of what an H.264 "high" was asking for here (8-bit 4:2:0). Level is
        # left off: libx265 wants "4.2" and hevc_amf wants an integer 126, and
        # a hint is not worth a units bug.
        out += ["-profile:v",
                "main10" if str(profile).lower() == "main10" else "main"]
    return out


def speed_tier(value, default=DEFAULT_SPEED):
    """A tier in 1..7 from a p-number, a family preset name, or a bare int.

    An unrecognised value falls back to the default with a note rather than
    dying: a preset naming a speed this module has not heard of is a cosmetic
    mistake, and refusing to render over it would be a bad trade.
    """
    if value is None:
        return default
    if isinstance(value, int):
        return max(1, min(7, value))
    v = str(value).strip().lower()
    if v.startswith("p") and v[1:].isdigit():
        return max(1, min(7, int(v[1:])))
    if v.isdigit():
        return max(1, min(7, int(v)))
    if v in _TIERS:
        return _TIERS[v]
    sys.stderr.write("note: unknown speed preset %r -- using p%d\n"
                     % (value, default))
    return default


# --------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------

_probe_cache = None


def _cache_path():
    return os.path.join(ROOT, "temp", "encoders.json")


def _ffmpeg_id():
    """Something that changes when the ffmpeg build does, so the cache expires."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], env=ENV,
                             capture_output=True, text=True).stdout
        return out.splitlines()[0].strip()
    except Exception:
        return "?"


def _load_cache():
    global _probe_cache
    if _probe_cache is not None:
        return _probe_cache
    _probe_cache = {"ffmpeg": _ffmpeg_id(), "encoders": {}}
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            got = json.load(f)
        if got.get("ffmpeg") == _probe_cache["ffmpeg"]:
            _probe_cache = got
    except (OSError, ValueError):
        pass
    return _probe_cache


def _save_cache():
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(_probe_cache, f, indent=2)
    except OSError:
        pass                        # a cache that will not persist is not fatal


def usable(encoder, recheck=False):
    """Can this encoder actually encode a frame on this machine?

    Not "is it in `ffmpeg -encoders`". That list reports what the BUILD
    supports, and a full Windows build supports NVENC whether or not an NVIDIA
    driver was ever installed -- so the string test passes on an AMD box and
    every render on it still dies with `Cannot load nvcuda.dll`. One frame
    settles it in about a fifth of a second, and the answer is cached against
    the ffmpeg version.

    PROBE_SIZE is not arbitrary and must not be shrunk to make the probe
    cheaper. A hardware encoder refuses a frame smaller than its alignment,
    and it refuses it with the same "could not open encoder" it gives a
    missing driver -- so too small a probe reports a working card as broken,
    which is the same lie as the encoder list, told the other way round.
    Measured on this Vega 10: 64x64 fails, 160x120 fails (120 is not a
    multiple of 16), 128x128 and 176x144 pass. 320x240 clears it with room.
    """
    cache = _load_cache()
    if not recheck and encoder in cache["encoders"]:
        return cache["encoders"][encoder]
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=%s:r=25:d=0.08" % PROBE_SIZE,
             "-c:v", encoder, "-frames:v", "1", "-f", "null", "-"],
            env=ENV, capture_output=True, text=True)
    except OSError:
        got = False                 # no ffmpeg at all: cannot encode, and
    else:                           # default_encoder() still needs a name
        got = p.returncode == 0 and "rror" not in (p.stderr or "")
    cache["encoders"][encoder] = got
    _save_cache()
    return got


def available(candidates=CANDIDATES, recheck=False):
    """The candidates that really run here, in preference order."""
    return [e for e in candidates if usable(e, recheck)]


def default_encoder():
    """The encoder to use when nothing names one, most explicit source winning:

        1. $VIDEDIT_ENCODER   a shell, a launcher or a host program
        2. the first of CANDIDATES that encodes a frame on this machine
        3. h264_nvenc         so a machine with no working ffmpeg at all still
                              has a name to put in an error message

    Deliberately the same shape as _env.workspace(): the assumption gets one
    home rather than being re-spelled per script.
    """
    named = os.environ.get(ENCODER_VAR)
    if named and named.strip():
        return named.strip()
    got = available()
    return got[0] if got else CANDIDATES[0]


def strict():
    return bool((os.environ.get(STRICT_VAR) or "").strip())


# --------------------------------------------------------------------------
# decoding, which is a different axis from encoding
# --------------------------------------------------------------------------
# `-hwaccel cuda` is NVDEC on the INPUT; the encoder keys above are NVENC on
# the output. Nothing translates between them, and a missing driver fails the
# *input*, which surfaces as a broken source file rather than a missing card
# -- eight call sites spelled it inline and four had no fallback at all, so
# scan-pii.py and film-redact.py could not read a frame on an AMD box while
# every render on that box was fine.
#
# It is probed the way an encoder is, and for the same reason: `ffmpeg
# -hwaccels` lists what the BUILD has, and a full Windows build lists cuda on
# a machine that has never seen an NVIDIA driver. NVENC's availability is not
# the test either -- the two capabilities ship on different silicon and a card
# can have one without the other -- so this decodes a real frame.


def nvdec_usable(recheck=False):
    """Can this machine actually DECODE through `-hwaccel cuda`?

    Answered by decoding one frame of a file this function encodes, because a
    lavfi source is generated rather than decoded and would let `-hwaccel`
    pass on a box with no driver at all. Cached against the ffmpeg version
    beside the encoder probes.
    """
    cache = _load_cache()
    probes = cache.setdefault("decoders", {})
    if not recheck and "cuda" in probes:
        return probes["cuda"]
    got = False
    enc = next((e for e in available()), None)
    if enc:
        tmp = os.path.join(tempfile.gettempdir(),
                           "_encode-nvdec-probe-%d.mp4" % os.getpid())
        try:                        # OSError: no ffmpeg -- no hwaccel either
            made = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi",
                 "-i", "color=c=black:s=%s:r=25:d=0.2" % PROBE_SIZE,
                 "-c:v", enc, "-frames:v", "5", tmp],
                env=ENV, capture_output=True, text=True)
            if made.returncode == 0 and os.path.exists(tmp):
                p = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error",
                     "-hwaccel", "cuda", "-i", tmp,
                     "-frames:v", "1", "-f", "null", "-"],
                    env=ENV, capture_output=True, text=True)
                got = p.returncode == 0 and "rror" not in (p.stderr or "")
        except OSError:
            got = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    probes["cuda"] = got
    _save_cache()
    return got


def decode_args(recheck=False):
    """The input-side hardware-decode flags for this machine, or none.

    Never spell `-hwaccel cuda` at a call site -- ask here, the same way a
    render asks video_args() rather than spelling `-preset`. A caller that
    keeps its own software retry loses nothing: this only ever removes an
    attempt that was going to fail.
    """
    return ["-hwaccel", "cuda"] if nvdec_usable(recheck) else []


# --------------------------------------------------------------------------
# the one place the keys are chosen
# --------------------------------------------------------------------------

def resolve(cfg, strict_encoder=None):
    """A render config whose `encoder` is one this machine can actually run.

    A manifest or caption preset is committed and gets read on machines its
    author never saw, so an encoder it names that cannot run here is
    substituted -- loudly, naming the key to edit for permanence. Twenty
    minutes into a filtergraph is the wrong moment to discover the box has no
    NVIDIA card.

    An encoder named explicitly (a --encoder flag, $VIDEDIT_ENCODER, or
    $VIDEDIT_ENCODER_STRICT set) is honoured strictly and fails instead: you
    asked for that one by name.
    """
    cfg = dict(cfg or {})
    want = cfg.get("encoder") or default_encoder()
    cfg["encoder"] = want
    if usable(want):
        return cfg
    if strict() if strict_encoder is None else strict_encoder:
        sys.exit("encoder %s cannot run on this machine -- it is in the "
                 "ffmpeg build but fails to open. Working encoders here: %s"
                 % (want, ", ".join(available()) or "none"))
    got = available()
    if not got:
        sys.exit("no usable video encoder: none of %s can encode a frame. "
                 "Run scripts/check-env.py." % ", ".join(CANDIDATES))
    sys.stderr.write(
        "note: encoder %s cannot run here -- using %s instead. Set "
        "render.encoder in the manifest or preset, or $%s, to make it "
        "permanent.\n" % (want, got[0], ENCODER_VAR))
    cfg["encoder"] = got[0]
    return cfg


def video_args(cfg):
    """The whole video side of an ffmpeg command, from -c:v to -pix_fmt.

    Six scripts spelled this by hand and all six spelled NVENC. Keys a family
    does not have are not emitted for it -- that is the entire point, and it
    is what makes `render.encoder` a setting rather than a suggestion.

    Recognised config keys, all optional:
        encoder     h264_nvenc | h264_amf | libx264 | ...
        cq          the quality target, 0-51 (alias: quality)
        preset      a speed, in any family's vocabulary (alias: speed)
        maxrate     bitrate ceiling, e.g. "16M"
        bufsize     rate-control buffer, e.g. "32M"
        tuning      True to add the family's extra quality knobs
        aq_strength NVENC's spatial-AQ strength, when tuning is on
        profile     e.g. "high"      level    e.g. "4.2"
        gop         keyframe interval in frames
        pix_fmt     defaults to yuv420p
    """
    enc = cfg.get("encoder") or default_encoder()
    fam = family_of(enc)
    q = int(cfg.get("cq", cfg.get("quality", DEFAULT_QUALITY)))
    tier = speed_tier(cfg.get("preset", cfg.get("speed")))

    out = ["-c:v", enc]
    out += SPEED[fam](tier)
    out += RATE[fam](q)
    if cfg.get("maxrate"):
        out += ["-maxrate", str(cfg["maxrate"])]
    if cfg.get("bufsize"):
        out += ["-bufsize", str(cfg["bufsize"])]
    if cfg.get("tuning"):
        out += TUNING[fam](cfg.get("aq_strength", 12))
    if cfg.get("gop"):
        out += ["-g", str(cfg["gop"])]
    out += profile_args(enc, cfg.get("profile"), cfg.get("level"))
    out += ["-pix_fmt", cfg.get("pix_fmt", "yuv420p")]
    return out


def audio_args(cfg, rate=None, channels=2):
    """The audio side, which no family has an opinion about -- here so a call
    site has one thing to call rather than two."""
    out = ["-c:a", "aac", "-b:a", str(cfg.get("audio_bitrate", "192k"))]
    if rate:
        out += ["-ar", str(rate)]
    return out + ["-ac", str(channels)]


def describe(cfg):
    """One line for a --list, so a render's cost is legible before it is paid."""
    enc = cfg.get("encoder") or default_encoder()
    tier = speed_tier(cfg.get("preset", cfg.get("speed")))
    return "%s (%s) speed p%d  q%s  ceiling %s/%s" % (
        enc, family_of(enc), tier,
        cfg.get("cq", cfg.get("quality", DEFAULT_QUALITY)),
        cfg.get("maxrate", "-"), cfg.get("bufsize", "-"))
