#!/usr/bin/env python
"""A project's brief casts the episode's voices (film.Film.create, prompt_voices), without Claude or
any voice: python studio/test_brief_voices.py

A series names each character's ElevenLabs voice once, in its brief; every episode must then be read
in those voices. Until 2026-11-20 only the episode's own idea and attached documents were read, so a
Warrior Cats episode whose brief named the cats' ElevenLabs voices came out in Gemini voices and the
cats sounded alike. Covers: an episode of a project whose brief names ElevenLabs voices gets an
ElevenLabs vo.json in them; an episode of a project whose brief names none, and a film outside any
project, stay on the studio's own voices; the episode's idea still wins when it names its own.
Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-brief-voices-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import film as films  # noqa: E402 -- imports _env first
from film import Film  # noqa: E402

R, S, P = "S0ypc51SmsvcKXTWvjqJ", "mrQhZWGbb2k9qWJb5qeA", "acCWxmzPBgXdHwA63uzP"
CATS = {
    "id": "p-aaaaaaaaaa",
    "name": "Warrior Cats",
    "brief": "Cats who talk. VOICES: each in its own ElevenLabs voice (model eleven_v4): "
    "Rusty %s, Smudge %s, Princess %s." % (R, S, P),
}
PLAIN = {
    "id": "p-bbbbbbbbbb",
    "name": "Duchess",
    "brief": "A very dignified cat, told by a narrator.",
}


def vo_of(f):
    with open(f.path("vo.json"), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    try:
        ep = Film.create(
            "Scene 1: the fence. @rusty and @smudge talk.",
            5,
            "drawn",
            client="u:a",
            project=dict(CATS),
        )
        v = vo_of(ep)
        check(
            v.get("tts") == "elevenlabs",
            "an episode of a project whose brief names ElevenLabs voices is read in ElevenLabs: %r"
            % v.get("tts"),
        )
        check(v.get("voice") == R, "its first voice is the brief's first: %r" % v.get("voice"))
        model_ok = v.get("model") in films.EL_MODELS
        check(model_ok, "in a model ElevenLabs has: %r" % v.get("model"))

        own = Film.create(
            "Scene 2. Voices on ElevenLabs: the narrator %s." % S,
            5,
            "drawn",
            client="u:a",
            project=dict(CATS),
        )
        check(
            vo_of(own).get("voice") == S, "an episode naming its own ElevenLabs voice leads with it"
        )

        plain = Film.create(
            "Episode 9: the cushion.", 5, "drawn", client="u:a", project=dict(PLAIN)
        )
        check(
            vo_of(plain).get("tts") != "elevenlabs",
            "a project whose brief names no voice keeps the studio's voices",
        )

        alone = Film.create("A cat on a fence.", 5, "drawn", client="u:a")
        check(
            vo_of(alone).get("tts") != "elevenlabs",
            "a film outside any project keeps the studio's voices",
        )
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
