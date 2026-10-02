#!/usr/bin/env python
"""A series' kept sounds (library.py: sounds_of, _seed_sounds, _keep_sounds, sounds_note; and
validate.py's sounds.json), without Claude and without rendering: python studio/test_sounds.py

Covers: only an episode may write sounds.json; a bad sounds.json and a cue or theme played by a
name it lacks are named by the validator; a finished episode's sounds go into its project's
library; the next episode starts with them in its sounds.json and hears of them in its note; a
sound the library changed meanwhile is not overwritten by an older episode finished again; a
film outside projects keeps nothing. Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-sounds-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import library  # noqa: E402
import validate  # noqa: E402
from film import Film  # noqa: E402

PROJECT = {"id": "p-abcdefghij", "name": "Duchess", "brief": "A deadpan cat."}
KIT = {
    "sounds": {
        "bell": {"about": "her collar bell", "cue": {"fx": "chime", "db": -24}},
        "sad": {
            "about": "the sad trombone when her dignity is gone",
            "cue": {"fx": "sample", "inst": "bassoon", "notes": ["F2", "E2", "Eb2"], "every": 0.4},
        },
    },
    "themes": {
        "main": {"about": "her stately theme", "events": [{"inst": "clarinet", "notes": "0 C5 1"}]}
    },
}


def put(film, name, d):
    with open(film.path(name), "w", encoding="utf-8") as f:
        json.dump(d, f)


def main():
    fails = []

    def check(ok, what, detail=""):
        print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)))
        if not ok:
            fails.append(what)

    lone = Film.create("a film of her own", 5, "drawn", client="u:alice")
    e1 = Film.create("The Box", 5, "drawn", client="u:alice", project=PROJECT)
    check("sounds.json" in e1.editable(), "an episode may write sounds.json")
    check("sounds.json" not in lone.editable(), "a film outside projects may not")

    put(e1, "sounds.json", {"sounds": {"Bell!": {"cue": {"fx": "nope"}}}, "extra": 1})
    bad = validate.problems(e1, "sounds.json")
    check(bad and "must be" in bad[0], "a sounds.json of the wrong shape is named", bad)
    put(e1, "sounds.json", {"sounds": {"Bell": {"about": "x", "cue": {"fx": "nope"}}}})
    bad = validate.problems(e1, "sounds.json")
    check(any("lowercase" in b for b in bad), "a bad name is named", bad)
    check(any("fx must be" in b for b in bad), "a bad cue in a sound is named", bad)
    put(e1, "sounds.json", {"themes": {"main": {"events": [{"type": "roll", "inst": "timpani"}]}}})
    bad = validate.problems(e1, "sounds.json")
    check(any('"notes" events' in b for b in bad), "a theme of other events is refused", bad)

    put(e1, "sounds.json", KIT)
    check(validate.problems(e1, "sounds.json") == [], "a good sounds.json passes")
    put(e1, "sfx.json", [{"t": 1, "sound": "bell"}, {"t": 2, "sound": "gong"}])
    bad = validate.problems(e1, "sfx.json")
    check(
        len(bad) == 1 and "gong" in bad[0] and "have:" in bad[0], "an unknown sound is named", bad
    )
    put(e1, "sfx.json", [{"t": 1, "sound": "bell"}, {"t": 2, "sound": "sad", "db": -20}])
    check(validate.problems(e1, "sfx.json") == [], "sounds played by name pass")
    put(
        e1, "score.json", {"bpm": 100, "events": [{"type": "theme", "theme": "main", "at": [0, 8]}]}
    )
    check(validate.problems(e1, "score.json") == [], "a theme played by name passes")
    put(e1, "score.json", {"bpm": 100, "events": [{"type": "theme", "theme": "waltz"}]})
    check(validate.problems(e1, "score.json"), "an unknown theme is named")

    e1.update(state="done", library={"cast": [], "films": [], "sounds": {}})
    got = library.keep(e1, [])
    check(
        sorted(got.get("sounds") or []) == ["bell", "main", "sad"], "the episode's sounds kept", got
    )
    lib = library.lib_of(e1.record())
    kept = library.sounds_of(lib)
    check(kept["sounds"]["bell"]["films"] == [e1.id], "a kept sound knows its film")

    e2 = Film.create("The Sour Cream", 5, "drawn", client="u:alice", project=PROJECT)
    seeded = library.seed(e2)
    with open(e2.path("sounds.json"), encoding="utf-8") as f:
        mine = json.load(f)
    check(mine == KIT, "the next episode starts with the series' sounds", mine)
    check(set(seeded["sounds"]["sounds"]) == {"bell", "sad"}, "its record has what it got")
    note = library.note(e2)
    check('sound "bell": her collar bell' in note, "its note names them", note[-600:])
    check('theme "main"' in note and '"type": "theme"' in note, "and says how to play them")

    # the second episode changes the bell; then the first is finished again with its old bell
    mine["sounds"]["bell"]["cue"]["db"] = -20
    mine["sounds"]["fridge"] = {"about": "the fridge's choir", "cue": {"fx": "shimmer"}}
    put(e2, "sounds.json", mine)
    e2.update(state="done")
    got = library.keep(e2, [])
    check(sorted(got.get("sounds") or []) == ["bell", "fridge"], "changed and new sounds kept", got)
    library.keep(e1, [])
    kept = library.sounds_of(lib)
    check(kept["sounds"]["bell"]["cue"]["db"] == -20, "an older episode does not undo a newer one")
    check(kept["sounds"]["bell"]["films"][:1] == [e2.id], "the newer film is its maker")

    put(lone, "sounds.json", KIT)
    lone.update(state="done")
    out = library.keep(lone, []) or {}
    check(not out.get("sounds"), "a film outside projects keeps no sounds", out)

    print("\n%s" % ("all passed" if not fails else "%d FAILED" % len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    agent  # noqa: B018 -- imported for _env
    main()
