#!/usr/bin/env python
"""What keeps films from all looking alike, checked without Claude: python studio/test_direction.py

    the prompt     the system prompt is the same for every film of a look (so it stays cached),
                   fills every placeholder, and carries the grounds, voices and ensembles
    direction      a finished film's choices are read back from its own files
    the note       the first message tells a film what recent films chose -- counts only, never
                   another film's prompt
    the ensembles  every instrument the prompt offers is already cached (no download mid-film)

A second or two.
"""

import os
import re
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent  # noqa: E402
import film as films  # noqa: E402

films.LEGACY = os.path.join(HOME, "legacy")  # only this test's films, not the working tree's

bad = []


def expect(name, ok, detail=""):
    print(
        "%s  %s%s"
        % ("ok  " if ok else "FAIL", name, ("  -- " + str(detail)) if detail and not ok else "")
    )
    if not ok:
        bad.append(name)


def write(f, name, data):
    with open(f.path(name), "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data))


def main():
    # ---- the prompt
    for look in films.LOOKS:
        a, b = agent.system_prompt(look), agent.system_prompt(look)
        expect("%s: the system prompt is the same every time" % look, a == b)
        expect(
            "%s: every placeholder is filled" % look,
            not re.findall(r"\{[A-Z_]{3,}\}", a),
            re.findall(r"\{[A-Z_]{3,}\}", a),
        )
        expect(
            "%s: it asks for a direction first" % look,
            "# Direction" in a and "Do not assume the audience is children" in a,
        )
        expect(
            "%s: it offers the ensembles and the voice directions" % look,
            "jazz cafe" in a and "noir or mystery" in a,
        )
    drawn = agent.system_prompt("drawn")
    expect(
        "drawn: every ground is on the menu",
        all("`%s`" % g in drawn for g in ("paper", "night", "chalkboard", "blueprint", "kraft")),
    )
    expect(
        "drawn: the examples are the studio's two",
        "SK.setGround('night')" in drawn and "SK.setGround('blueprint')" in drawn,
    )
    expect("painted: the style menu", "paper cut-out collage" in agent.system_prompt("painted"))

    # ---- the ensembles use only cached instruments
    sf = os.path.join(films.KIT, "models", "soundfonts", "FluidR3_GM")
    if os.path.isdir(sf):
        cached = set(os.listdir(sf))
        sound = drawn[drawn.index("- The ensemble is half") : drawn.index("- Tempo from the mood")]
        named = set(re.findall(r"`([a-z0-9_]+)`", sound))
        expect("every ensemble instrument is cached", named <= cached, sorted(named - cached))

    # ---- direction, read back from a film's files
    f = films.Film.create("A lighthouse at night", 10, "drawn", client="t")
    write(f, "film.js", "SK.setStyle('clean');\nSK.setGround('night');\nSK.film({duration: 10});")
    write(f, "vo.json", {"voice": "Charon", "style": "low and wry", "lines": []})
    write(
        f,
        "score.json",
        {
            "bpm": 76,
            "events": [
                {"inst": "vibraphone", "notes": ""},
                {"inst": "acoustic_bass", "notes": ""},
                {"type": "drums", "kit": {}},
            ],
        },
    )
    d = f.direction()
    expect(
        "direction: ground, style, voice, music",
        d
        == {
            "look": "drawn",
            "ground": "night",
            "style": "clean",
            "voice": "Charon",
            "voice_style": "low and wry",
            "instruments": ["acoustic_bass", "vibraphone", "drums"],
            "bpm": 76,
        },
        d,
    )
    write(f, "film.js", "SK.film({duration: 10, ground: (t) => t < 5 ? 'sky' : 'night'});")
    expect("direction: a ground that changes", f.direction()["ground"] == "changing")
    write(f, "film.js", "SK.film({duration: 10});")
    expect("direction: no ground named is the paper", f.direction()["ground"] == "paper")
    p = films.Film.create("A dragon learns to cook", 10, "painted", client="t")
    write(p, "paint.json", {"style": "paper cut-out collage, bold primaries", "images": []})
    expect(
        "direction: a painted film's style",
        p.direction()["paint_style"].startswith("paper cut-out"),
    )

    # ---- the note in the first message
    f.update(state="done")
    p.update(state="done")
    n = films.Film.create("SECRET PROMPT of someone else", 10, "drawn", client="t")
    recent = agent.recent_films(n)
    expect("recent: the finished films, not this one", len(recent) == 2, recent)
    msg = agent.ask(n, recent)
    expect(
        "the note is after the prompt",
        msg.index("Prompt:") < msg.index("Recent films made here chose"),
    )
    expect(
        "the note counts choices",
        "- voices: Kore, Charon" in msg and "- grounds: paper" in msg and "- tempos: 76" in msg,
        msg,
    )
    expect("the note gives no other film's prompt", "lighthouse" not in msg and "dragon" not in msg)
    q = films.Film.create("Another", 10, "drawn", client="t")
    expect(
        "a film never sees its own prompt twice",
        agent.ask(q, agent.recent_films(q)).count("Another") == 1,
    )
    expect(
        "no note on a new studio",
        agent.recent_note("drawn", []) == "" and "Recent" not in agent.ask(f, []),
    )

    print("%d failed" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(code)
