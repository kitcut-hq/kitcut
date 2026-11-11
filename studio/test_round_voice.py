#!/usr/bin/env python
"""A round on a film told in its person's own ElevenLabs voice (rounds.words, keep_pass,
copy_of, ask): with a fresh pass the round may record -- a line's words changed, or the same
words taken again -- and without one it says so and the site knows to send one. No API calls.

    python studio/test_round_voice.py
"""

import os
import sys
import json
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-round-voice-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import film as films  # noqa: E402
import rounds  # noqa: E402

FAILS = []
VOICE = "AbCdEfGhIjKlMnOpQrSt"
GRANT = "g" * 40


def expect(what, ok):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def film_with(narrator):
    d = tempfile.mkdtemp(prefix="film-", dir=HOME)
    rec = {"state": "done", "ok": True, "length": 30}
    if narrator:
        rec["narrator"] = narrator
    with open(os.path.join(d, "studio.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f)
    return films.Film(d)


own = {"source": "elevenlabs", "voice": VOICE, "model": "eleven_v3", "jobs": 2, "chars": 0}

# ---- words: what a round may do with the narration
w = rounds.words({"narrator": own})
expect(
    "own voice, no pass: not now, but with a pass",
    w == {"can": False, "why": "own_voice", "with_pass": True},
)
expect(
    "own voice, a fresh pass: the round may record",
    rounds.words({"narrator": own}, fresh=True) == {"can": True},
)
expect("KitCut's voice: always", rounds.words({"narrator": {"source": "kitcut"}}) == {"can": True})
expect(
    "no narration: never, pass or not",
    rounds.words({"narration": False}, fresh=True)["can"] is False,
)

# ---- keep_pass: the pass is kept beside the film, never in its record
f = film_with(own)
rounds.keep_pass(f, {**own, "grant": GRANT})
with open(f.path("temp", rounds.VOICE_PASS), encoding="utf-8") as fh:
    expect("the pass is kept in the film's temp/", json.load(fh) == {"grant": GRANT})
expect("the record never holds the grant", GRANT not in json.dumps(f.record()))
try:
    rounds.keep_pass(f, {**own, "voice": "ZzZzZzZzZzZzZzZzZzZz", "grant": GRANT})
    expect("another voice's pass is refused", False)
except rounds.RoundError as e:
    expect("another voice's pass is refused", e.reason == "own_voice")
try:
    rounds.keep_pass(film_with({"source": "kitcut"}), {**own, "grant": GRANT})
    expect("a pass for a film in KitCut's voice is refused", False)
except rounds.RoundError as e:
    expect("a pass for a film in KitCut's voice is refused", e.reason == "own_voice")

# ---- can_voice: a round's copy records only with the pass it was given
work = film_with(own)
expect("a copy with no pass may not record", rounds.can_voice(work) is False)
os.makedirs(work.path("temp"), exist_ok=True)
with open(work.path("temp", "voice.json"), "w", encoding="utf-8") as fh:
    json.dump({"grant": GRANT}, fh)
expect("a copy given the pass may record", rounds.can_voice(work) is True)
expect("the voice step gets that pass", work.own_voice() == {"grant": GRANT})

# ---- what Claude is told
expect(
    "the prompt says how to take the same words again",
    "a new take of the same words" in rounds.VOICE,
)
expect("without a voice, a retake is answered not done", "recorded again" in rounds.NO_VOICE)

if FAILS:
    sys.exit("%d failed" % len(FAILS))
print("all passed")
