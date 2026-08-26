#!/usr/bin/env python
"""Prove the toolchain is healthy, and say precisely what is wrong when it is not.

Run this first whenever a script fails with an import or DLL error. It checks
the three things that have actually broken on this machine: a stray PYTHONPATH
pulling in another Python's compiled extensions, a venv that pip left
half-populated, and missing ffmpeg features (NVENC, rubberband).

    python scripts/check-env.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import


ROOT = _env.ROOT
FAIL = []
WARN = []


def ok(msg):
    print("  ✓ %s" % msg)


def bad(msg):
    FAIL.append(msg)
    print("  ✗ %s" % msg)


def warn(msg):
    WARN.append(msg)
    print("  ! %s" % msg)


print("== interpreter ==")
want = _env.venv_python()
if want is None:
    bad(".venv is missing -- run scripts/setup-python.ps1")
elif os.path.normcase(sys.prefix) == os.path.normcase(os.path.dirname(os.path.dirname(want))):
    ok("running in .venv (%s)" % sys.version.split()[0])
else:
    bad("not running in .venv: sys.prefix=%s" % sys.prefix)

print("== sys.path hygiene ==")
if os.environ.get("PYTHONPATH"):
    bad("PYTHONPATH is set (%s) -- it overrides the venv and breaks compiled "
        "extensions" % os.environ["PYTHONPATH"])
else:
    ok("PYTHONPATH is unset")
foreign = [p for p in sys.path
           if "site-packages" in p.lower()
           and os.path.normcase(ROOT) not in os.path.normcase(p)]
if foreign:
    bad("foreign site-packages on sys.path: %s" % "; ".join(foreign))
else:
    ok("no foreign site-packages on sys.path")

print("== python packages ==")
for mod, why in [
    ("numpy", "array maths"),
    ("cv2", "face detection for auto-reframe"),
    ("faster_whisper", "word-level transcription"),
    ("scenedetect", "shot boundaries"),
    ("PIL", "handle badge rendering"),
    ("fontTools", "badge cap-height metrics"),
    ("onnxruntime", "whisper VAD"),
    ("edge_tts", "dubbing text-to-speech"),
    ("httpx", "ElevenLabs TTS and the OpenAI translation engine"),
    ("yt_dlp", "fetching sources"),
    ("ctranslate2", "the inference engine under faster-whisper"),
    ("av", "audio decode for faster-whisper"),
]:
    try:
        m = __import__(mod)
        ok("%-15s %-9s (%s)" % (mod, getattr(m, "__version__", "") or "-", why))
    except Exception as e:
        bad("%-15s %s: %s -- %s" % (mod, type(e).__name__, str(e)[:60], why))

try:
    import cv2
    n = len([f for f in os.listdir(cv2.data.haarcascades) if f.endswith(".xml")])
    # OpenCV 5.0 ships none of these, which silently disables face tracking.
    (ok if n else bad)("%d Haar cascade XMLs bundled with OpenCV" % n)
except Exception:
    pass

# ctranslate2 needs cuBLAS at first encode, and if it cannot find it
# faster-whisper drops to CPU without an error -- a 40-minute source then takes
# most of an hour instead of a couple of minutes.
n_dll = 0
for _root in _env.site_roots():
    _nv = os.path.join(_root, "nvidia")
    if os.path.isdir(_nv):
        for _pkg in sorted(os.listdir(_nv)):
            _bin = os.path.join(_nv, _pkg, "bin")
            if os.path.isdir(_bin):
                n_dll += len([f for f in os.listdir(_bin) if f.lower().endswith(".dll")])
(ok if n_dll else warn)("%d CUDA DLLs on the package path (GPU transcription)" % n_dll)

# The two pins whose comments in requirements.txt say "load-bearing": drift
# here is exactly what pip check cannot see.
print("== pins ==")
try:
    import importlib.metadata as _md
    _pins = {}
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.split("#")[0].strip()
            if "==" in _line:
                _k, _, _v = _line.partition("==")
                _pins[_k.strip().lower()] = _v.strip()
    for _pkg in ("opencv-python", "nvidia-cublas-cu12"):
        _want = _pins.get(_pkg)
        if not _want:
            continue
        try:
            _have = _md.version(_pkg)
        except _md.PackageNotFoundError:
            bad("%s is not installed (requirements.txt pins %s)" % (_pkg, _want))
            continue
        if _have == _want:
            ok("%s %s matches its pin" % (_pkg, _have))
        else:
            warn("%s %s drifted from pin %s" % (_pkg, _have, _want))
except Exception as _e:
    warn("could not compare pins: %s" % _e)

print("== external tools ==")
import shutil as _sh  # noqa: E402
if _sh.which("claude"):
    ok("claude CLI on PATH (default translation engine for dubbing)")
else:
    warn("claude CLI not on PATH -- dub-clips.py's default --engine claude "
         "needs it; use --engine openai or manual otherwise")
for _k, _why in (("ELEVENLABS_API_KEY", "--tts elevenlabs"),
                 ("OPENAI_API_KEY", "--engine openai")):
    if os.environ.get(_k):
        ok("%s is set (%s)" % (_k, _why))
    else:
        warn("%s not set -- optional, only needed for %s" % (_k, _why))

print("== fonts ==")
_font = os.path.join(ROOT, "fonts", "Montserrat-Bold.ttf")
if os.path.exists(_font):
    ok("fonts/Montserrat-Bold.ttf present")
else:
    bad("fonts/Montserrat-Bold.ttf missing -- every caption preset points at "
        "it, and libass would silently substitute another face")

print("== ffmpeg ==")
for tool in ("ffmpeg", "ffprobe"):
    try:
        subprocess.run([tool, "-version"], capture_output=True, check=True)
        ok("%s on PATH" % tool)
    except Exception:
        bad("%s not on PATH" % tool)
try:
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    if "h264_nvenc" in enc:
        ok("h264_nvenc (GPU encoding)")
    else:
        # cut-clips.py and the caption presets default to h264_nvenc, so
        # "environment OK" with this warning still means zero renders succeed
        # until the encoder is changed -- say so, with the fix
        warn("h264_nvenc missing -- every render defaults to it; set "
             "render.encoder to libx264 in the manifest or preset to encode "
             "on CPU")
    flt = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                         capture_output=True, text=True).stdout
    # rubberband time-stretches without shifting pitch; atempo is the fallback
    # and sounds worse past about +/-15%.
    (ok if "rubberband" in flt else warn)("rubberband (pitch-preserving stretch)")
    import re as _re  # noqa: E402
    (ok if _re.search(r"^\s*\S+\s+ass\s", flt, _re.M) else bad)(
        "ass (subtitle burn-in)")
except Exception as e:
    bad("could not query ffmpeg: %s" % e)

print("== gpu ==")
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                          "--format=csv,noheader"],
                         capture_output=True, text=True, check=True).stdout.strip()
    ok(out)
except Exception:
    warn("no nvidia-smi; encoding and transcription fall back to CPU")

print()
if FAIL:
    print("FAILED (%d): fix these before running anything else" % len(FAIL))
    for f in FAIL:
        print("  - %s" % f)
    sys.exit(1)
print("environment OK%s" % (" (%d warning(s))" % len(WARN) if WARN else ""))
