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
import motion  # noqa: E402

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
            "%s: it sets the bar, and asks who the film is for on film.js's first line" % look,
            "professionally made for that audience" in a
            and "`// For: <who it is for>; <its mood>`" in a
            and "`// For:` line" in a,  # the review checks the film against it
        )
        expect(
            "%s: it offers the ensembles" % look,
            "jazz cafe" in a and "night and mystery" in a,
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
    for look in films.LOOKS:
        p = agent.system_prompt(look)
        expect(
            "%s: the review calls motion" % look,
            "`motion`" in p and "One film, not a slideshow" in p,
        )
        expect(
            "%s: the review reads the whole film and looks inside the seconds" % look,
            "film-NN.jpg" in p and "`strip`" in p and "Two review rounds, and a third" in p,
        )
        # 2026-10-09, after Leo episode 11 came back from its owner: the faults it was sent back
        # for are named for every look, and the length is a target the narration may run past
        expect(
            "%s: what an owner sends a film back for is named" % look,
            all(
                x in p
                for x in (
                    "A body is one piece from every side",
                    "Everything stands on what holds it",
                    "Light shows what is there",
                    "A place has what belongs in it",
                    "The picture gets room",
                    "The last word is heard",
                    "thirtieth of its height",
                )
            ),
        )
        expect(
            "%s: the length is a target, and a line may ask for quiet before it" % look,
            "a target, not a wall" in p
            and '"pause": 1.5' in p
            and "lengthens the film and says so" in p
            and "is fixed, whatever" not in p,
        )
    expect(
        "drawn: what a viewer takes for a mistake is named",
        "Nothing breaks the picture" in drawn and "never by scaling through" in drawn,
    )

    # ---- the ensembles use only cached instruments
    sf = os.path.join(films.KIT, "models", "soundfonts", "FluidR3_GM")
    if os.path.isdir(sf):
        cached = set(os.listdir(sf))
        sound = drawn[drawn.index("- The ensemble is half") : drawn.index("- Sound effects:")]
        named = set(re.findall(r"`([a-z0-9_]+)`", sound))
        expect("every ensemble instrument is cached", named <= cached, sorted(named - cached))

    # ---- the Free plan's closing ships with the code (a release is committed files only)
    for name in (
        "outro.js",
        os.path.join("brand", "kitcut.png"),
        os.path.join("brand", "closing.wav"),
    ):
        expect("the closing's %s is in this code" % name, os.path.isfile(os.path.join(HERE, name)))

    # ---- motion: cuts and still stretches, from frames 0.25 s apart
    d = os.path.join(HOME, "motion")
    os.makedirs(d)
    from PIL import Image, ImageDraw

    for i in range(
        48
    ):  # 12 s: a square moving (0-5 s), then nothing moving (5-10 s), a cut at 10 s
        t = i / 4
        im = Image.new("RGB", (480, 270), "#f7f2e7" if t < 10 else "#1d2541")
        x = 40 + 30 * min(t, 5) if t < 10 else 40 + 30 * (t - 10)
        ImageDraw.Draw(im).rectangle((x, 100, x + 60, 160), fill="#c2592a")
        im.save(os.path.join(d, "%06.2f.png" % t))
    text, sheet = motion.analyse(d, os.path.join(HOME, "motion.png"))
    expect("motion: the still stretch is found", "Still for 4.8 s, from 5.0 to 9.8 s" in text, text)
    expect("motion: the cut is found", "Cuts or transitions at 9.9 s" in text, text)
    expect("motion: the moving part is not still", "from 0." not in text, text)
    expect(
        "motion: a sheet of the frames around them",
        sheet and os.path.exists(os.path.join(HOME, "motion.png")),
    )
    expect(
        "motion: the frames it looks at",
        motion.times(10)[:3] == [0, 0.25, 0.5] and len(motion.times(120)) == 240,
    )

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
            "audience": "",
        },
        d,
    )
    write(f, "film.js", "// For: investors and analysts; calm, serious\r\nSK.film({duration: 10});")
    expect(
        "direction: who it is for, from film.js's first line",
        f.direction()["audience"] == "investors and analysts; calm, serious",
        f.direction()["audience"],
    )
    write(f, "film.js", "SK.film({duration: 10, ground: (t) => t < 5 ? 'sky' : 'night'});")
    expect("direction: a ground that changes", f.direction()["ground"] == "changing")
    write(f, "film.js", "// for:   SECRET AUDIENCE; hushed  \nSK.film({duration: 10});")
    expect("direction: no ground named is the paper", f.direction()["ground"] == "paper")
    expect(
        "direction: the For line, any case", f.direction()["audience"] == "SECRET AUDIENCE; hushed"
    )
    p = films.Film.create("A dragon learns to cook", 10, "painted", client="t")
    write(p, "paint.json", {"style": "paper cut-out collage, bold primaries", "images": []})
    expect(
        "direction: a painted film's style",
        p.direction()["paint_style"].startswith("paper cut-out"),
    )

    c = films.Film.create("The history of ice cream", 10, "collage", client="t")
    write(c, "paint.json", {"style": "hand-tinted copperplate engraving", "images": []})
    write(
        c,
        "film.js",
        "SK.setStyle('collage');\nSK.newsprint({});\n"
        "SK.headline('A', 0, 0, { font: 'Playfair Display' });\n"
        "SK.tape('B', 0, 0, { font: 'Oswald' }); SK.tape('C', 0, 0, { font: \"Oswald\" });\n"
        "SK.film({duration: 10});",
    )
    d = c.direction()
    expect(
        "direction: a collage film's medium, faces and newspaper",
        (d["paint_style"], d["faces"], d["newsprint"], "ground" in d),
        ("hand-tinted copperplate engraving", ["Oswald", "Playfair Display"], True, False),
    )
    note = agent.recent_note("collage", [d, dict(d, faces=["Anton"], newsprint=False)])
    expect(
        "recent: a collage film's rows",
        "- painting styles: hand-tinted copperplate engraving" in note
        and "- print faces: Oswald, Playfair Display, Anton" in note
        and "- a newspaper page under the film: 1 of the last 2" in note,
        note,
    )
    expect(
        "recent: no collage rows for a drawn film",
        "print faces" not in agent.recent_note("drawn", [d]),
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
        msg.index("Prompt:") < msg.index("Recent films made here, by everyone, chose"),
    )
    expect(
        "the note counts choices",
        # the two films are made in the same second, so either may count as the newer
        ("- voices: Kore, Charon" in msg or "- voices: Charon, Kore" in msg)
        and "- grounds: paper" in msg
        and "- tempos: 76" in msg,
        msg,
    )
    expect("the note gives no other film's prompt", "lighthouse" not in msg and "dragon" not in msg)
    expect("the note gives no other film's audience", "SECRET AUDIENCE" not in msg, msg)
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
