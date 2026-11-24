#!/usr/bin/env python
"""A project's characters keep their voices (library CAST_VOICES, guard.pin_cast), without Claude:
python studio/test_castvoices.py

Covers: the first finished episode in which a character speaks records its voice (never a film's
people, a voice outside the studio's, or one already recorded); the person changing, restyling
and unlocking it (set_cast_voice) and what is refused; the next episode getting the voices
(seed), being told them (note), and its vo.json put back to them when Claude casts another or
makes a held character speak with no cast entry -- its style left to Claude; a film read in
ElevenLabs voices held to none. Everything in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-castvoices-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402,F401 -- imports _env first
import library  # noqa: E402
import validate  # noqa: E402
from film import Film  # noqa: E402
from guard import pin_vo  # noqa: E402

CLIENT = "u:castvoice"
PROJECT = {"id": "p-castvoic3s", "name": "Pip's Adventures", "brief": ""}
V1, V2, V3 = validate.VOICES[:3]
bad = []


def check(ok, what):
    print("%s  %s" % ("ok  " if ok else "FAIL", what))
    if not ok:
        bad.append(what)


def write_vo(film, vo):
    with open(film.path("vo.json"), "w", encoding="utf-8") as f:
        json.dump(vo, f)


def read_vo(film):
    with open(film.path("vo.json"), encoding="utf-8") as f:
        return json.load(f)


def episode():
    return Film.create("an episode", 15, "drawn", client=CLIENT, project=dict(PROJECT))


def main():
    lib = library.owner(CLIENT, PROJECT["id"])
    check(lib and lib[1] == PROJECT["id"], "the project has a library")

    # ------------------------------------------------ the first episode records the voices
    one = episode()
    write_vo(
        one,
        {
            "voice": V1,
            "cast": {
                "pip": {"voice": V2, "style": "small and bright"},
                "mo": {"voice": V3},
                "p1": {"voice": V3},
                "owl": {"voice": "NotAVoice"},
                "ghost": {"voice": V1},
            },
            "lines": [
                {"text": "Hello!", "who": "pip"},
                {"text": "Hi.", "who": "mo"},
                {"text": "Me too.", "who": "p1"},
                {"text": "Hoo.", "who": "owl"},
                {"text": "And so it began."},
            ],
        },
    )
    idx = library.load(lib)
    got = library._keep_voices(one, idx, "2026-11-20T10:00:00")
    library._save(lib, idx)
    have = library.cast_voices(lib)
    check(got == ["mo", "pip"], "the characters who spoke are recorded (%s)" % got)
    check(
        have["pip"]["voice"] == V2 and have["pip"]["style"] == "small and bright",
        "with the voice and style they were given",
    )
    check(
        have["pip"]["by"] == "film" and have["pip"]["film"] == one.id,
        "and the episode that gave it",
    )
    check("p1" not in have, "a film's people are its own, never the project's")
    check("owl" not in have, "a voice outside the studio's is not recorded")
    check("ghost" not in have, "a character cast but silent is not recorded")

    two = episode()
    write_vo(
        two, {"voice": V1, "cast": {"pip": {"voice": V3}}, "lines": [{"text": "x", "who": "pip"}]}
    )
    idx = library.load(lib)
    check(
        library._keep_voices(two, idx, "2026-11-20T11:00:00") == []
        and idx["voices"]["pip"]["voice"] == V2,
        "a voice already recorded is never replaced by a later episode",
    )

    # ------------------------------------------------ the person's choice
    e = library.set_cast_voice(CLIENT, PROJECT["id"], "mo", V1, "low and slow")
    check(
        e["voice"] == V1 and e["style"] == "low and slow" and e["by"] == "person",
        "the person sets mo's voice",
    )
    e = library.set_cast_voice(CLIENT, PROJECT["id"], "mo", V2)
    check(
        e["voice"] == V2 and e["style"] == "low and slow",
        "a new voice keeps the style when none is sent",
    )
    for args, what in (
        (("mo", "NotAVoice"), "a voice the studio does not have"),
        (("Mo!", V1), "a name that is not a character's"),
        (("p2", V1), "a film's person"),
        (("mo", V1, "x" * 301), "a style longer than a line"),
    ):
        try:
            library.set_cast_voice(CLIENT, PROJECT["id"], *args)
            check(False, "%s is refused" % what)
        except library.PictureError as err:
            check(err.status == 400, "%s is refused (%s)" % (what, err.text))
    try:
        library.set_cast_voice("anon:203.0.113.9", PROJECT["id"], "mo", V1)
        check(False, "a visitor who is not signed in is refused")
    except library.PictureError as err:
        check(err.status == 404, "a visitor who is not signed in has no project to set")
    library.set_cast_voice("u:someone-else", PROJECT["id"], "mo", V3)
    check(
        library.cast_voices(lib)["mo"]["voice"] == V2,
        "another person's choice is their own library's, never this one's",
    )
    library.set_cast_voice(CLIENT, PROJECT["id"], "zed", V3)
    check(
        library.set_cast_voice(CLIENT, PROJECT["id"], "zed", None) is None,
        "unlocking answers nothing",
    )
    check("zed" not in library.cast_voices(lib), "and the next episode chooses again")
    listed = library.listing(CLIENT, PROJECT["id"])["voices"]
    check(
        [v["name"] for v in listed] == ["mo", "pip"] and listed[0]["voice"] == V2,
        "the Cast tab gets every character's voice (%s)" % listed,
    )

    # ------------------------------------------------ the next episode is held to them
    three = episode()
    os.makedirs(three.path("cast"), exist_ok=True)
    library.seed(three)
    for n in ("pip", "mo", "rex"):  # the characters who may speak: its cast (validate._cast_of)
        with open(three.path("cast", n + ".js"), "w", encoding="utf-8") as f:
            f.write("SK.cast.%s = { about: '%s', draw() {} };\n" % (n, n))
    pins = three.cast_voice_pins()
    check(
        pins
        == {
            "pip": {"voice": V2, "style": "small and bright"},
            "mo": {"voice": V2, "style": "low and slow"},
        },
        "the next episode gets the voices (%s)" % pins,
    )
    told = library.note(three)
    check("pip: %s" % V2 in told and "mo: %s" % V2 in told, "and is told them")
    write_vo(
        three,
        {
            "voice": V1,
            "cast": {"pip": {"voice": V3, "style": "whispering"}, "rex": {"voice": V3}},
            "lines": [
                {"text": "Psst.", "who": "pip"},
                {"text": "Hm.", "who": "mo"},
                {"text": "Grr.", "who": "rex"},
            ],
        },
    )
    said = pin_vo(three)
    vo = read_vo(three)
    check(
        vo["cast"]["pip"] == {"voice": V2, "style": "whispering"},
        "a held voice is put back, the episode's style kept",
    )
    check(
        vo["cast"]["mo"] == {"voice": V2, "style": "low and slow"},
        "a held character who speaks with no cast entry is given it",
    )
    check(vo["cast"]["rex"] == {"voice": V3}, "a new character's voice is Claude's to choose")
    check(
        "pip=%s" % V2 in said and "mo=%s" % V2 in said,
        "Claude is told what was put back (%s)" % said,
    )
    check(pin_vo(three) == "" or "cast" not in pin_vo(three), "and nothing more once it holds them")
    wrong = [p for p in validate.problems(three, "vo.json") if "cast" in p]
    check(not wrong, "the pinned cast is valid (%s)" % wrong)

    # ------------------------------------------------ ElevenLabs voices are held to none
    four = episode()
    os.makedirs(four.path("cast"), exist_ok=True)
    library.seed(four)
    four.update(el_voices={"ids": ["S0ypc51SmsvcKXTWvjqJ"], "model": "eleven_v3"})
    write_vo(
        four,
        {
            "voice": "S0ypc51SmsvcKXTWvjqJ",
            "cast": {"pip": {"voice": "S0ypc51SmsvcKXTWvjqJ"}},
            "lines": [{"text": "x", "who": "pip"}],
        },
    )
    pin_vo(four)
    check(
        read_vo(four)["cast"]["pip"]["voice"] == "S0ypc51SmsvcKXTWvjqJ",
        "a film read in its prompt's ElevenLabs voices is not held to Gemini's",
    )
    idx = library.load(lib)
    check(library._keep_voices(four, idx, "2026-11-20T12:00:00") == [], "nor records any")

    # ------------------------------------------------ outside a project
    solo = Film.create("a film of its own", 15, "drawn", client=CLIENT)
    check(solo.cast_voice_pins() == {}, "a film outside a project is held to no voices")

    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
