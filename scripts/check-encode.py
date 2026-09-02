#!/usr/bin/env python
"""Encoder self-test: prove the keys _encode.py emits are keys that encoder takes.

The bug this exists to catch is cheap to write and expensive to find. Six
render scripts spelled `-preset p5 -rc vbr -cq N` next to a *configurable*
encoder, so setting `render.encoder` to anything but NVENC produced
`invalid preset 'p5'` -- and only after a manifest was loaded, a filtergraph
built and a real file opened. Nothing in the repo could ask "what would you
send this encoder" without starting a render.

So, in two halves and about ten seconds:

  table   the mapping, in memory: families, speed translation across
          vocabularies, and the keys that must NOT cross a family line
  live    every encoder this machine can actually run, handed the exact
          argument list a render would hand it, on two seconds of colour bars

The live half is the one that would have caught it. A table test agrees with
whatever the table says; ffmpeg does not.

Costs nothing: no GPU is required (an unavailable encoder is skipped and
said so), no project file is read, and the clips are lavfi colour bars
written to a scratch directory under %TEMP%.

Invoke as:  python scripts/check-encode.py
            python scripts/check-encode.py --table-only   (no ffmpeg at all)
"""
import os
import sys
import shutil
import tempfile
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen

ENV = _env.ENV

FAILED = []
PASSED = [0]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s%s" % (name, ("  -- " + detail) if detail else ""))


def keys(args):
    """Just the option names, so a test can ask what was sent without caring
    about the values."""
    return [a for a in args if a.startswith("-")]


# --------------------------------------------------------------------------
def test_families():
    print("== families ==")
    for enc, want in (("h264_nvenc", "nvenc"), ("hevc_nvenc", "nvenc"),
                      ("h264_amf", "amf"), ("hevc_amf", "amf"),
                      ("av1_amf", "amf"), ("h264_qsv", "qsv"),
                      ("h264_vaapi", "vaapi"), ("libx264", "software"),
                      ("libx265", "software")):
        check("%s -> %s" % (enc, want), _encode.family_of(enc) == want,
              "got %s" % _encode.family_of(enc))
    try:
        _encode.family_of("magicenc")
        check("an unknown encoder is refused", False,
              "family_of returned instead of raising -- a silent default here "
              "would emit NVENC keys to something that is not NVENC")
    except ValueError:
        check("an unknown encoder is refused", True)


def test_speed():
    print("== speed translation ==")
    # Every vocabulary this repo has committed, onto one scale. p5 is the one
    # that matters: it is written into projects/*/‌*.json today.
    for value, want in (("p5", 5), ("p6", 6), ("p1", 1), ("p7", 7),
                        (5, 5), ("medium", 5), ("slow", 6), ("veryfast", 2),
                        ("balanced", 5), ("quality", 6), ("high_quality", 7),
                        (None, _encode.DEFAULT_SPEED)):
        check("speed_tier(%r) == %d" % (value, want),
              _encode.speed_tier(value) == want,
              "got %d" % _encode.speed_tier(value))
    check("out-of-range p9 clamps rather than crashing",
          _encode.speed_tier("p9") == 7)
    check("an unknown name falls back to the default",
          _encode.speed_tier("turbo") == _encode.DEFAULT_SPEED)


def test_no_key_crosses_a_family():
    print("== keys stay inside their family ==")
    cfg = {"cq": 21, "preset": "p5", "maxrate": "16M", "bufsize": "32M",
           "tuning": True}

    nv = _encode.video_args(dict(cfg, encoder="h264_nvenc"))
    amf = _encode.video_args(dict(cfg, encoder="h264_amf"))
    x264 = _encode.video_args(dict(cfg, encoder="libx264"))

    # THE regression. A committed manifest says "p5"; AMF and x264 must never
    # see it, and must not silently lose the speed setting either.
    check("p5 does not reach AMF", "p5" not in amf)
    check("p5 does not reach libx264", "p5" not in x264)
    check("AMF still gets a speed", "-quality" in amf)
    check("libx264 still gets a speed", "-preset" in x264)
    check("p5 does reach NVENC", "p5" in nv)

    check("-rc vbr is NVENC-only",
          "-rc" in nv and nv[nv.index("-rc") + 1] == "vbr"
          and ("-rc" not in x264)
          and amf[amf.index("-rc") + 1] == "qvbr")
    check("-cq is NVENC-only", "-cq" in nv and "-cq" not in amf
          and "-cq" not in x264)
    check("-crf is software-only", "-crf" in x264 and "-crf" not in nv
          and "-crf" not in amf)
    check("-qvbr_quality_level is AMF-only", "-qvbr_quality_level" in amf
          and "-qvbr_quality_level" not in nv)
    # README ## Gotchas: without it NVENC ignores -cq entirely. It is also
    # meaningless to the other two, which already have a quality target.
    check("-b:v 0 is NVENC-only",
          nv[nv.index("-b:v") + 1] == "0" and "-b:v" not in amf
          and "-b:v" not in x264)
    check("the quality number survives into every family",
          "21" in nv and "21" in x264
          and str(_encode.amf_quality(21)) in amf)

    # The direction is the whole point, and it is what was broken. A smaller
    # number must mean a better picture on EVERY family, which on AMF means
    # the emitted quality level has to go UP as the asked-for number goes down.
    print("== better quality is always a smaller number ==")
    for enc in ("h264_nvenc", "h264_amf", "libx264"):
        hi = _encode.video_args({"encoder": enc, "cq": 16})   # want better
        lo = _encode.video_args({"encoder": enc, "cq": 30})   # want worse
        fam = _encode.family_of(enc)
        if fam == "amf":
            a = int(hi[hi.index("-qvbr_quality_level") + 1])
            b = int(lo[lo.index("-qvbr_quality_level") + 1])
            ok = a > b          # inverted scale: better quality is a HIGHER level
        else:
            key = "-cq" if fam == "nvenc" else "-crf"
            a = int(hi[hi.index(key) + 1])
            b = int(lo[lo.index(key) + 1])
            ok = a < b
        check("%s: cq 16 asks for better pictures than cq 30" % enc, ok,
              "cq16 emitted %d, cq30 emitted %d" % (a, b))
    check("AMF inverts rather than passing through",
          _encode.amf_quality(16) == 35 and _encode.amf_quality(21) == 30)
    check("AMF quality level stays inside 0..51",
          _encode.amf_quality(-5) <= 51 and _encode.amf_quality(99) >= 0)
    check("NVENC tuning is emitted", "-spatial-aq" in nv and "-tune" in nv)
    # Measured, not assumed: -vbaq/-preanalysis cost 26% and did nothing on
    # VCN 1.0, and this GPU has no H.264 B-frames at all.
    check("AMF tuning is deliberately empty",
          "-vbaq" not in amf and "-bf" not in amf)
    check("every family ends on a pixel format",
          nv[-2] == amf[-2] == x264[-2] == "-pix_fmt")

    bare = _encode.video_args({"encoder": "libx264", "cq": 21})
    check("an absent maxrate emits no -maxrate", "-maxrate" not in bare)
    check("tuning off emits no tuning keys", "-bf" not in bare)

    # profile/level are the CODEC's vocabulary, not the family's. The configs
    # here hold H.264 values, and hevc_amf rejected them outright.
    print("== profile and level follow the codec ==")
    pl = {"cq": 20, "profile": "high", "level": "4.2"}
    h264 = _encode.video_args(dict(pl, encoder="h264_amf"))
    hevc = _encode.video_args(dict(pl, encoder="hevc_amf"))
    x265 = _encode.video_args(dict(pl, encoder="libx265"))
    check("H.264 keeps profile high and level 4.2",
          "high" in h264 and "4.2" in h264)
    check("HEVC never sees the H.264 profile 'high'", "high" not in hevc)
    check("HEVC gets a profile it has", "main" in hevc)
    check("HEVC drops the level rather than guessing its units",
          "-level" not in hevc and "-level" not in x265)
    check("codec_of reads the encoder name",
          _encode.codec_of("h264_amf") == "h264"
          and _encode.codec_of("libx265") == "hevc"
          and _encode.codec_of("hevc_nvenc") == "hevc"
          and _encode.codec_of("av1_amf") == "av1")


def test_audio_and_describe():
    print("== audio and description ==")
    a = _encode.audio_args({"audio_bitrate": "256k"}, rate=48000)
    check("audio bitrate is carried", "256k" in a)
    check("a sample rate is emitted when asked", "-ar" in a and "48000" in a)
    check("no sample rate when not asked",
          "-ar" not in _encode.audio_args({}))
    d = _encode.describe({"encoder": "h264_amf", "cq": 18, "preset": "p5"})
    check("describe names the encoder and its family",
          "h264_amf" in d and "amf" in d and "p5" in d and "18" in d)


def test_live(tmp):
    """Hand each usable encoder the exact arguments a render would."""
    print("== live: the args a render would really send ==")
    good = _encode.available(_encode.CANDIDATES + ("hevc_amf", "hevc_nvenc"))
    if not good:
        check("at least one encoder runs here", False,
              "nothing can encode -- run scripts/check-env.py")
        return
    for enc in good:
        # The three shapes the repo actually renders: a clip, a conform, and
        # the caption pass with its tuning block.
        for label, cfg in (
                ("clip", {"cq": 21, "preset": "p5", "maxrate": "16M",
                          "bufsize": "32M"}),
                ("conform", {"cq": 16, "preset": "p5", "maxrate": "40M",
                             "bufsize": "80M"}),
                ("captions", {"cq": 20, "preset": "p6", "maxrate": "20M",
                              "bufsize": "40M", "tuning": True,
                              "aq_strength": 12, "gop": 120,
                              "profile": "high", "level": "4.2"})):
            cfg = dict(cfg, encoder=enc)
            out = os.path.join(tmp, "%s-%s.mp4" % (enc, label))
            cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
                   + _encode.video_args(cfg) + _encode.audio_args(cfg)
                   + ["-movflags", "+faststart", out])
            p = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
            wrote = os.path.exists(out) and os.path.getsize(out) > 1024
            check("%s / %s renders" % (enc, label),
                  p.returncode == 0 and wrote,
                  (p.stderr or "").strip().splitlines()[-1:] and
                  (p.stderr or "").strip().splitlines()[-1] or "no output file")
    for enc in _encode.CANDIDATES:
        if enc not in good:
            print("  skip %s -- not usable on this machine" % enc)


def test_resolve():
    print("== resolve ==")
    good = _encode.available()
    if not good:
        return
    # An encoder that cannot run is substituted, because the manifest naming it
    # was committed on somebody else's machine.
    got = _encode.resolve({"encoder": "definitely_not_an_encoder_nvenc"},
                          strict_encoder=False)
    check("an unusable encoder is substituted, not obeyed",
          got["encoder"] in good, "got %s" % got["encoder"])
    check("a usable encoder is left alone",
          _encode.resolve({"encoder": good[0]})["encoder"] == good[0])
    check("resolve keeps the rest of the config",
          _encode.resolve({"encoder": good[0], "cq": 17})["cq"] == 17)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--table-only", action="store_true",
                    help="skip the ffmpeg runs -- the mapping only")
    args = ap.parse_args()

    test_families()
    test_speed()
    test_no_key_crosses_a_family()
    test_audio_and_describe()
    if not args.table_only:
        test_resolve()
        tmp = tempfile.mkdtemp(prefix="videdit-encode-")
        try:
            test_live(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d checks passed, %d failed" % (PASSED[0], len(FAILED)))
    if FAILED:
        for f in FAILED:
            print("  - %s" % f)
        sys.exit(1)


if __name__ == "__main__":
    main()
