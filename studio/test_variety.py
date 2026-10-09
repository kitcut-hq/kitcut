#!/usr/bin/env python
"""A series keeps its look and a collection's films differ, checked without Claude:
python studio/test_variety.py

    a series       a project that does not say what it keeps hears exactly what it heard
                   before, and so does one that names all four (film.PROJECT_KEEPS)
    a collection   a project that keeps less hears what its earlier films chose so as to differ
                   from them, is not told to keep the series, and gets no kept sounds
    in between     one that keeps its voice shares that and nothing else
    what is told   the colours a film set its ground to and how its narration opens are read
                   from its own files (Film.direction), for films made before they were too
    the tally      "what recent films chose" yields to a series' episodes, not a collection's
    measured       variety.py counts what a set of films chose (its frames need ffmpeg: not here)

A second or two.
"""

import os
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-variety-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import film as films  # noqa: E402
import library  # noqa: E402
from film import PROJECT_KEEPS as KEEP, Film  # noqa: E402

films.LEGACY = os.path.join(HOME, "legacy")  # only this test's films, not the working tree's

P = "p-cccccccccc"
BRIEF = "One piece of news per film. Facts from the sheet only."
RED = """// For: developers on a phone; dry
SK.setStyle('collage');
SK.setGround('paper', { paper: '#e8e4da', text: '#141312', accent: '#e2392b' });
SK.film({ duration: 5, draw(t) { SK.txt('A coffee machine', 0, 0, { face: 'Anton' }); } });
"""
GOLD = """// For: developers on a phone; a tribute
const INK = '#17140f', GOLD = '#d6a44c';
SK.setStyle('collage');
SK.setGround('night', { paper: '#191715', text: INK, accent: GOLD,
  tint: { mottle: '120,110,95' } });
SK.film({ duration: 5, draw(t) { SK.txt('1936', 0, 0, { face: 'Playfair Display' }); } });
"""
VO = {
    "voice": "Charon",
    "style": "Low, calm and quick",
    "lines": [{"text": "A coffee machine sent a terabyte. Why?"}, {"text": "Nobody looked."}],
}
SCORE = {"bpm": 104, "events": [{"type": "notes", "inst": "electric_piano_1"}, {"type": "drums"}]}


def write(film, name, data):
    with open(film.path(name), "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


def made(prompt, js, keep=None):
    """A finished film of the project, kept in its library the way the studio keeps one."""
    f = new(prompt, keep)
    write(f, "film.js", js)
    write(f, "vo.json", VO)
    write(f, "score.json", SCORE)
    f.update(state="done", direction=f.direction())
    library.keep(f, [], {})
    return f


def new(prompt, keep=None):
    project = {"id": P, "name": "AI news", "brief": BRIEF, "from_account_cast": False}
    if keep is not None:
        project["keep"] = keep
    return Film.create(prompt, 5, "collage", client="u:alice", project=project)


def main():
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "  -- %s" % detail if not ok else ""))
        if not ok:
            bad.append(what)

    try:
        # ---------------------------------------------------- what a project keeps
        check(library.keeps(None) == () and library.keeps({}) == (), "no project keeps nothing")
        check(library.keeps({"id": P}) == KEEP, "a project that does not say is a series")
        check(
            library.keeps({"keep": "voice"}) == KEEP and library.keeps({"keep": None}) == KEEP,
            "and so is one whose keep is not a list",
        )
        check(
            library.keeps({"keep": ["music", "nope", "voice"]}) == ("voice", "music"),
            "a collection keeps what it names, of the four, in their order",
        )
        check(
            not library.is_collection({"id": P})
            and not library.is_collection({"keep": list(KEEP)})
            and library.is_collection({"keep": []})
            and library.is_collection({"keep": ["cast", "look", "voice"]})
            and not library.is_collection(None),
            "a collection is a project that keeps less than all four",
        )

        # ---------------------------------------------------- what a film's files say it chose
        one = made("A coffee machine sent a terabyte", RED)
        d = one.direction()
        check(
            d.get("paper") == "#e8e4da" and d.get("accent") == "#e2392b",
            "the ground's colours are read from the film's code",
            d,
        )
        check(
            d.get("opening") == "A coffee machine sent a terabyte. Why?"
            and d.get("lines") == 2
            and d.get("words") == 9,
            "and how its narration opens, and how much of it there is",
            d,
        )
        two = made("Margaret Hamilton has died", GOLD)
        d2 = two.direction()
        check(
            d2.get("paper") == "#191715" and d2.get("accent") == "#d6a44c",
            "a colour given as a constant is looked up",
            d2,
        )
        check(
            films.ground_colours("SK.film({});") == {}
            and films.ground_colours("SK.setGround('night');") == {}
            and films.ground_colours("SK.setGround('paper', { newspaper: '#fff' });") == {},
            "a film that kept a ground's own colours records none",
        )

        # ---------------------------------------------------- a series hears what it always did
        ep = new("The third story")
        library.seed(ep)
        series = library.note(ep)
        check(
            'This film is an episode of the project "AI news".' in series
            and "Its earlier episodes, newest first (Read <folder>/about.json, film.js" in series
            and "An episode belongs with the others: keep what makes them one series (the cast, "
            "the look, the voice, the music), unless the prompt asks for something new."
            in series
            and "A series keeps its sounds as it keeps its cast" in series,
            "a project that does not say what it keeps is a series",
        )
        check(
            "paper #" not in series and "opens " not in series and "collection" not in series,
            "and hears nothing a collection hears",
        )
        ep.update(project=ep.record()["project"] | {"keep": list(KEEP)})
        check(library.note(ep) == series, "naming all four changes nothing: the same note")
        tally = [{"look": "collage", "voice": "Kore", "bpm": 90}]
        asked = agent.ask(ep, tally)
        check(
            "or when the project's brief or its earlier episodes above do" in asked,
            "and the tally of recent films yields to its episodes",
        )

        # ---------------------------------------------------- a collection is told to differ
        ep.update(project=ep.record()["project"] | {"keep": []})
        own = library.note(ep)
        check(
            'This film is one of the films of the project "AI news".' in own and BRIEF in own,
            "a collection's film hears its project and brief",
        )
        check(
            "they are here to be told apart from, not to be followed" in own
            and "paper #191715; accent #d6a44c" in own
            and "paper #e8e4da; accent #e2392b" in own
            and "type Anton" in own
            and "voice Charon" in own
            and "electric_piano_1, drums at 104 bpm" in own
            and 'opens "A coffee machine sent a terabyte. Why?"' in own
            and "2 narration lines, 9 words" in own,
            "and what each earlier film chose: colours, type, voice, music, how it opens",
            own,
        )
        check(
            "This project is a collection, not a series: its films share only what its brief "
            "asks for."
            in own
            and "should take this one for a different film" in own
            and "the narrator and how they speak" in own
            and "the instruments and the tempo, or no music at all" in own
            and "the pace, how it opens, the order it tells things in and how it ends" in own,
            "and that everything else is its own, to choose differently",
        )
        check(
            "belongs with the others" not in own
            and "keep what makes them one series" not in own
            and "A series keeps its sounds" not in own
            and "film.js, vo.json" not in own,
            "it is not told to keep the series, gets no kept sounds, is not sent to their code",
        )
        check(library.sounds_note(ep) == "", "nor does a film made in scenes hear of kept sounds")
        asked = agent.ask(ep, tally)
        check(
            "or when the project's brief does):" in asked
            and "earlier episodes above do" not in asked,
            "the tally of recent films yields to its brief only",
        )

        # ---------------------------------------------------- in between: it keeps its voice
        ep.update(project=ep.record()["project"] | {"keep": ["voice", "music"]})
        mid = library.note(ep)
        check(
            "its films share its voice and its music, and what its brief asks for." in mid
            and "the narrator and how they speak" not in mid
            and "or no music at all" not in mid
            and "the look of it" in mid
            and "A series keeps its sounds as it keeps its cast" in mid,
            "a project that keeps its voice and music shares those and nothing else",
            mid,
        )

        # ---------------------------------------------------- the first film of a collection
        other = "p-dddddddddd"
        first = Film.create(
            "The first",
            5,
            "collage",
            client="u:alice",
            project={"id": other, "name": "Promos", "brief": "", "keep": ["cast"]},
        )
        library.seed(first)
        alone = library.note(first)
        check(
            "its films share its cast, and what its brief asks for. Everything else is each "
            "film's own: choose it for this prompt alone."
            in alone
            and "first episode" not in alone,
            "a collection's first film is not told the next ones will have to keep its choices",
            alone,
        )

        # ---------------------------------------------------- films made before this was recorded
        rec = one.record()["direction"]
        one.update(
            direction={
                k: v
                for k, v in rec.items()
                if k not in ("paper", "accent", "opening", "lines", "words")
            }
        )
        old = new("After the old film", keep=[])
        got = library.seed(old)
        dirs = {m["title"]: m["direction"] for m in got["films"]}
        check(
            dirs["A coffee machine sent a terabyte"].get("opening")
            and dirs["A coffee machine sent a terabyte"].get("paper") == "#e8e4da",
            "a collection reads an older film's colours and opening from its files",
            dirs,
        )
        kept = new("A series after the old film")
        got = library.seed(kept)
        dirs = {m["title"]: m["direction"] for m in got["films"]}
        check(
            "opening" not in dirs["A coffee machine sent a terabyte"],
            "a series is given the film's record as it was",
        )

        # ---------------------------------------------------- measuring it (variety.py)
        import variety

        check(
            [variety.colour_name(c) for c in ("#e8e4da", "#191715", "#e2392b", "#888", "")]
            == ["light", "dark", "red", "grey", ""],
            "a colour is named roughly, so two near-white papers count as one",
        )
        rows = [variety.axes(x.direction(), 40) for x in (one, two, one)]
        t = variety.tally(rows)
        check(
            t["voice"]["distinct"] == 1
            and t["voice"]["share"] == 1
            and t["ground"]["values"] == {"light": 2, "dark": 1}
            and t["type"]["top"] == "Anton"
            and round(t["accent"]["share"], 2) == 0.67,
            "a set of films is counted choice by choice",
            t,
        )
        same = variety.sameness(variety.tally([rows[0], rows[0]]))
        check(same == 1 and variety.sameness(t) < 1, "and one number says how alike it is")
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("all passed" if not bad else "%d FAILED: %s" % (len(bad), "; ".join(bad))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
