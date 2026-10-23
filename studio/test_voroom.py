#!/usr/bin/env python
"""The narration's room: a film's voice takes a touch of the music's reverb, as it always has,
unless its vo.json asks for a dry voice ("dry": true -- a close, voice-message read, where the
2.3 s hall was heard as an echo on a stage). No model, no network. Seconds.

    python studio/test_voroom.py

Covers: a film that says nothing is mixed sample for sample as before (_sketchaudio.vo_stereo
against the old expression); a dry voice is the voice alone, with no tail after its last word;
vo.json takes "dry" as true or false and refuses anything else; the guard keeps it when it pins
vo.json; and the mixer reads it from the film's own vo.json, true only when it is true.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402

import _sketchaudio as A  # noqa: E402
import validate  # noqa: E402

FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


def main():
    sr = A.SR
    # half a second of a tone, then a second and a half of silence: where a room would ring on
    vo = np.zeros(2 * sr)
    vo[: sr // 2] = 0.3 * np.sin(2 * np.pi * 220 * np.arange(sr // 2) / sr)
    ir = A.make_ir(2.3)

    before = np.stack([vo, vo]) * 0.98 + A.reverb(np.stack([vo, vo]) * 0.05, ir) * 0.6
    got = A.vo_stereo(vo, ir)
    expect("a film that says nothing is mixed as before", np.array_equal(got, before))

    dry = A.vo_stereo(vo, ir, dry=True)
    expect("a dry voice is the voice alone", np.array_equal(dry, np.stack([vo, vo]) * 0.98))
    tail = np.abs(got[:, sr:]).max()
    expect("the room rings on after the last word", tail > 1e-4, tail)
    expect("a dry voice is silent after it", np.abs(dry[:, sr:]).max() == 0)

    ok = {"voice": validate.VOICES[0], "lines": [{"text": "Hi Parents."}]}
    expect("vo.json without dry passes", validate._vo(ok, 6, 10) == [], validate._vo(ok, 6, 10))
    for v in (True, False):
        said = validate._vo({**ok, "dry": v}, 6, 10)
        expect("vo.json takes dry: %s" % v, said == [], said)
    for v in ("yes", 1, None):
        said = validate._vo({**ok, "dry": v}, 6, 10)
        expect("vo.json refuses dry: %r" % (v,), any("dry" in s for s in said), said)
    expect("the guard keeps dry when it pins vo.json", "dry" in validate.VO_KEYS)

    # the mixer's reading of it (sketch-audio.py): the film's vo.json, as _sketch.load holds it
    def asks(m):
        return (m.get("vo") or {}).get("dry") is True

    src = open(os.path.join(os.path.dirname(HERE), "scripts", "sketch-audio.py"), encoding="utf-8")
    expect(
        "sketch-audio.py mixes the voice through vo_stereo with the film's own dry",
        'A.vo_stereo(vo, ir, dry=(m.get("vo") or {}).get("dry") is True)' in src.read(),
    )
    src.close()
    expect("a film with no vo.json is not dry", not asks({}))
    expect("dry: true is dry", asks({"vo": {"dry": True}}))
    expect('dry: "true" (a string) is not', not asks({"vo": {"dry": "true"}}))

    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
