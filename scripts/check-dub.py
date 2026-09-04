#!/usr/bin/env python
"""Self-test the dub pipeline's internals, without spending a TTS call.

check-env.py proves the toolchain is installed; this proves the logic still
does what it claims. These paths are otherwise reachable only through a full
paid run, which is exactly why they grew bugs: two of the checks below -- a
model preamble that parses as a valid JSON list, and a word mark landing past
the end of the audio -- found real defects the day they were written.

Costs nothing and needs no key. Run it after touching any dub-*.py.

    python scripts/check-dub.py

Invoke as:  python scripts/check-dub.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

_tr = import_module("dub-translate")
_tts = import_module("dub-tts")
_clips = import_module("dub-clips")

fails = []


def check(name, got, want):
    if got == want:
        print("  OK   %s" % name)
    else:
        print("  FAIL %s\n       got  %r\n       want %r" % (name, got, want))
        fails.append(name)


def raises(name, fn, needle):
    try:
        fn()
    except BaseException as e:
        if needle.lower() in str(e).lower():
            print("  OK   %s -> %s" % (name, str(e)[:70]))
            return
        print("  FAIL %s: wrong error %r" % (name, str(e)[:90]))
        fails.append(name)
        return
    print("  FAIL %s: no error raised" % name)
    fails.append(name)


print("== _extract_json ==")
check("plain array", _tr._extract_json('[{"i":1}]'), [{"i": 1}])
check("fenced", _tr._extract_json('```json\n[{"i":2}]\n```'), [{"i": 2}])
check(
    "prose with a bracket first",
    _tr._extract_json('I kept slot [1] short. Here it is:\n[{"i":3}]'),
    [{"i": 3}],
)
check(
    "trailing prose with a bracket",
    _tr._extract_json('[{"i":4}]\nNote: slot [4] is tight.'),
    [{"i": 4}],
)
check(
    "array inside prose both sides",
    _tr._extract_json('Sure [see below]:\n[{"i":5,"text":"x"}]\nDone [ok].'),
    [{"i": 5, "text": "x"}],
)
raises("junk", lambda: _tr._extract_json("I could not do that."), "no JSON array")

print("== monotonic ==")
check(
    "overlaps nudged forward",
    _tts.monotonic([("a", 0.0, 0.5), ("b", 0.4, 0.9)]),
    [("a", 0.0, 0.5), ("b", 0.5, 0.9)],
)
check(
    "clamped to audio length",
    _tts.monotonic([("a", 0.0, 0.5), ("b", 0.6, 9.0)], max_t=1.0),
    [("a", 0.0, 0.5), ("b", 0.6, 1.0)],
)
raises(
    "degenerate all-zero", lambda: _tts.monotonic([("a", 0.0, 0.0), ("b", 0.0, 0.0)]), "degenerate"
)

print("== iso_lang ==")
for name, want in (
    ("English", "en"),
    ("Spanish", "es"),
    ("German", "de"),
    ("Portuguese", "pt"),
    ("Dutch", "nl"),
    ("Greek", "el"),
):
    check("iso %s" % name, _clips.iso_lang(name), want)

print("== retune scoping + tight preservation ==")
units = [
    {"i": 1, "dur": 2.0, "hard": 2.2, "text": "src one"},
    {"i": 2, "dur": 2.0, "hard": 2.2, "text": "src two"},
]
fits = [{"final": 5.0}, {"final": 2.0}]  # only slot 1 misfits
rows = [
    {"i": 1, "text": "long one", "tight": "KEEP-1"},
    {"i": 2, "text": "fine two", "tight": "KEEP-2"},
]

seen = {}


def _stub(prompt, engine, model=None):
    seen["prompt"] = prompt
    return [
        {"i": 1, "text": "shorter one"},  # no tight -> must keep KEEP-1
        {"i": 2, "text": "MEDDLED"},
    ]  # unrequested -> must be dropped


_tr._ask = _stub
out, n = _tr.retune(units, fits, rows, "ctx", verbose=False)
by = {r["i"]: r for r in out}
check("requested slot rewritten", by[1]["text"], "shorter one")
check("old tight kept when omitted", by[1]["tight"], "KEEP-1")
check("unrequested slot untouched", by[2]["text"], "fine two")
check("changed count", n, 1)
check("prompt shows current tight", "current tight: KEEP-1" in seen["prompt"], True)

print("== retune with --engine manual ==")
out2, n2 = _tr.retune(units, fits, rows, "ctx", engine="manual", verbose=True)
check("manual retune is a no-op", (out2 is rows, n2), (True, 0))

print("== translate refuses manual ==")
raises(
    "translate manual", lambda: _tr.translate([], "", engine="manual"), "hand-written translation"
)

print("== cross-slot word clamp (the logic dub-clips applies) ==")
words = [{"start": 0.0, "end": 1.0}, {"start": 0.8, "end": 1.5}, {"start": 1.4, "end": 1.4}]
clamped, prev = 0, 0.0
for w in words:
    a, b = w["start"], w["end"]
    if a < prev:
        a, clamped = prev, clamped + 1
    b = max(b, a + 0.01)
    w["start"], w["end"] = round(a, 3), round(b, 3)
    prev = b
check("two words nudged", clamped, 2)
check("strictly forward", all(words[i]["start"] >= words[i - 1]["end"] for i in (1, 2)), True)
check("no zero-length", all(w["end"] > w["start"] for w in words), True)

print("== fingerprint ==")


class A:
    max_dur, min_dur, engine, dst_lang = 4.0, 0.9, "claude", "English"


plan = {"units": [{"text": "one"}, {"text": "two"}]}
fp1 = _clips._fingerprint(plan, A)
A2 = type("A2", (A,), {"max_dur": 3.0})
check("stable", _clips._fingerprint(plan, A), fp1)
check("changes with max_dur", _clips._fingerprint(plan, A2) != fp1, True)
check(
    "changes with text",
    _clips._fingerprint({"units": [{"text": "one"}, {"text": "THREE"}]}, A) != fp1,
    True,
)

print("== retune revert: a rewrite that fits WORSE is thrown away ==")
# calls the real keep_better(), so this fails if that logic ever changes
units_by_i = {1: {"i": 1, "dur": 2.00}, 2: {"i": 2, "dur": 2.00}}
prev = {
    1: ("audioA", "marksA", {"final": 2.05}),  # off by .05
    2: ("audioB", "marksB", {"final": 2.40}),
}  # off by .40
fit_by_i = {
    1: {"final": 2.60},  # off by .60 -- worse
    2: {"final": 2.02},
}  # off by .02 -- better
audio_by_i = {1: "audioA2", 2: "audioB2"}
marks_by_i = {1: "marksA2", 2: "marksB2"}
before = {1: {"text": "old one"}, 2: {"text": "old two"}}
by_i = {1: {"text": "new one"}, 2: {"text": "new two"}}
back = _clips.keep_better([1, 2], units_by_i, prev, before, audio_by_i, marks_by_i, fit_by_i, by_i)
check("only the worse rewrite reverted", back, [1])
check("reverted slot kept its old audio", audio_by_i[1], "audioA")
check("reverted slot kept its old text", by_i[1]["text"], "old one")
check("better rewrite survived", (fit_by_i[2]["final"], audio_by_i[2]), (2.02, "audioB2"))

print("== cut(): a locked destination is reported, not fatal ==")
_cut = import_module("cut-clips")
_tmp = os.path.join(os.environ.get("TEMP", "."), "_lockprobe")
os.makedirs(_tmp, exist_ok=True)
_dst = os.path.join(_tmp, "out.mp4")
_part = _dst + ".part.mp4"
with open(_part, "w") as f:
    f.write("x")  # stand in for a finished encode
_replace, _sleep, _run = os.replace, _cut.time.sleep, _cut.run
slept = []
os.replace = lambda a, b: (_ for _ in ()).throw(PermissionError("locked"))
_cut.time.sleep = lambda s: slept.append(s)
_cut.run = lambda cmd, **kw: type("R", (), {"returncode": 0})()
try:
    got = _cut.cut("src.mp4", _dst, 0.0, 1.0, _cut.DEFAULT_RENDER, True)
finally:
    os.replace, _cut.time.sleep, _cut.run = _replace, _sleep, _run
check("returns False rather than exiting", got, False)
check("waited out the lock 5 times", len(slept), 5)
check("kept the finished encode", os.path.exists(_part), True)
os.remove(_part)

print()
if fails:
    print("FAILED %d: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("dub self-test OK")
