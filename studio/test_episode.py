#!/usr/bin/env python
"""A series' next episode starting from its last one's code (episode.py), without Claude or a
render: python studio/test_episode.py

Covers: which episode it starts from (the one made last, not the one finished last), what it is
given and what not, the person's narrator still winning, every reason it starts empty instead, a
film carried only once, the engine (the same release, merged onto another, and one that does not
merge), cast members a round changed, a carry that fails half-way taking everything back, the
first message, the guards (a film.js left as it was, words of the last story), cues on words
their line does not say, and engine_diff measured against the engine a film started from.
Everything in a throwaway STUDIO_HOME; seconds.
"""

import os
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-episode-test-")
os.environ["STUDIO_HOME"] = HOME
os.environ["STUDIO_ENV_FILE"] = os.path.join(HOME, "no.env")  # the setting comes from below
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import episode  # noqa: E402
import library  # noqa: E402
import validate  # noqa: E402
from film import KIT, RELEASE, Film  # noqa: E402

bad = []
P = "p-aaaaaaaaaa"
OTHER = "p-bbbbbbbbbb"
ON = episode.SETTING


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def write(film, rel, text):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(film, rel):
    try:
        with open(film.path(*rel.split("/")), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def ep(prompt, project=P, created=None, keep=None, **kw):
    """An episode of the project, seeded from its library as the server does."""
    proj = {"id": project, "name": "Olga's Forest", "brief": "Bedtime stories."}
    if keep is not None:
        proj["keep"] = keep
    f = Film.create(
        prompt, kw.pop("seconds", 30), kw.pop("look", "drawn"), client="u:alice", project=proj, **kw
    )
    if created:
        f.update(created=created)
    library.seed(f)
    return f


def finish(f, film_js, vo_lines=("Olga wakes up.",), voice="Kore", cast=None, engine=None):
    """What a finished episode leaves: its code, its narration, its cast kept in the library."""
    write(f, "film.js", film_js)
    write(f, "score.json", json.dumps({"bpm": 84, "tracks": [{"inst": "piano", "notes": []}]}))
    write(f, "sfx.json", json.dumps({"cues": [{"t": 3.2, "sound": "bell"}]}))
    vo = json.loads(read(f, "vo.json") or "{}")
    vo.update(voice=voice, style="softly", lines=[{"text": t} for t in vo_lines])
    write(f, "vo.json", json.dumps(vo))
    for name, code in (cast or {}).items():
        write(f, "cast/%s.js" % name, code)
    for name, code in (engine or {}).items():
        write(f, "engine/" + name, code)
    f.update(state="done", title=f.record()["prompt"])
    library.keep(f, library.changes(f), {})
    return f


OWL = "SK.cast.owl = { about: 'Olga, a grey owl', draw(x, y) { SK.wash(SK.S.ellC(x, y, 40, 50), '#888'); } };\n"
OWL2 = OWL.replace("grey owl", "grey owl in a scarf")
FILM1 = (
    "// For: bedtime\nSK.film({ duration: 30, draw(t) {\n"
    "  SK.text('Olga\\'s Forest presents', 0, -300);\n"
    "  SK.text('Olga finds a golden acorn', 0, 0);\n"
    "  if (t > SK.w(0, 'wakes')) SK.cast.owl.draw(0, 200);\n} });\n"
)
FILM2 = FILM1.replace("a golden acorn", "a lost kite")


def kit(name):
    with open(os.path.join(KIT, "sketch", name), encoding="utf-8") as f:
        return f.read()


def main():
    # ------------------------------------------------ off: as before
    os.environ.pop(ON, None)
    e1 = finish(
        ep("Olga finds a golden acorn", created="2026-10-01T09:00:00"), FILM1, cast={"owl": OWL}
    )
    e2 = finish(ep("Olga and the lost kite", created="2026-10-02T09:00:00"), FILM2)
    off = ep("Olga and the snow")
    check(episode.carry(off) is None and "carried" not in off.record(), "off: nothing carried")
    check(not episode.wanted(off), "off: make_film does not even hop to a thread for it")
    check(not os.path.exists(off.path("film.js")), "and the episode starts empty")
    os.environ[ON] = OTHER
    check(episode.carry(off) is None, "on for another project only: nothing either")
    check(not episode.wanted(off), "and not asked for")

    # ------------------------------------------------ on: the last episode made
    os.environ[ON] = "%s, %s" % (OTHER, P)
    # finished again after the other: first in the library's index, yet not the one made last
    e1.update(state="done")
    library.keep(e1, [], {})
    check(
        library.load(("u:alice", P))["films"][0] == e1.id,
        "(the older episode is the index's first)",
    )
    check(
        episode.source(off).id == e2.id, "it starts from the episode made last, not finished last"
    )
    got = episode.carry(off)
    check(
        got and got["film"] == e2.id and not got.get("skipped"), "on for its project: carried", got
    )
    check(read(off, "film.js") == FILM2, "film.js is the last episode's")
    check(read(off, "score.json") == read(e2, "score.json"), "and so is score.json")
    check(
        not os.path.exists(off.path("sfx.json")),
        "sfx.json is not (its cues are seconds on the old narration)",
    )
    vo = json.loads(read(off, "vo.json"))
    check(
        vo["lines"] == [] and vo["voice"] == "Kore" and vo["style"] == "softly",
        "vo.json keeps the voice, no lines",
        vo,
    )
    start = off.path(*episode.START)
    check(
        sorted(os.listdir(start)) == ["about.json", "film.js", "score.json", "sfx.json", "vo.json"],
        "library/start/ holds the last episode as it was",
        sorted(os.listdir(start)),
    )
    check("Olga wakes up." in read(off, "library/start/vo.json"), "its narration among it, to read")
    check(
        off.record()["carried"]["hashes"]["film.js"] and episode.carried(off),
        "the record says what it started from",
    )
    check(
        episode.carry(off) is None and read(off, "film.js") == FILM2,
        "carried once: a second call changes nothing",
    )

    # ------------------------------------------------ the first message
    text = agent.ask(off, [])
    check(
        "starts from the last one's code" in text
        and "Olga and the lost kite" in text
        and "library/start/" in text,
        "the first message says where it starts and what to keep",
    )
    longer = ep("Olga's long night", seconds=120)
    episode.carry(longer)
    t2 = agent.ask(longer, [])
    check(
        episode.LONG in t2 and agent.LONG_FILM not in t2, "a long one is told to change it in parts"
    )

    # ------------------------------------------------ the guards
    check(episode.untouched(off), "a film.js left as it came is untouched")
    write(off, "film.js", FILM2.replace("a lost kite", "the first snow"))
    check(not episode.untouched(off), "and is not once it is changed")
    write(off, "film.js", FILM2)
    left = episode.leftovers(off)
    check(
        left == ["Olga finds a lost kite"],
        "words of the last story still on screen are found; the series' own title is not",
        left,
    )
    write(off, "film.js", FILM2.replace("Olga finds a lost kite", "Olga sees the first snow"))
    check(episode.leftovers(off) == [], "and none once replaced")

    # ------------------------------------------------ cues on words the narration does not say
    write(
        off,
        "vo.json",
        json.dumps(dict(vo, lines=[{"text": "Olga wakes up."}, {"text": "Snow falls."}])),
    )
    write(off, "film.js", "SK.w(0, 'wakes'); SK.w(1, 'kite'); SK.w(0, \"Olga\"); SK.w(4, 'x');\n")
    check(
        validate.cue_misses(off) == ["line 1: 'kite'", "line 4: 'x' (no such line)"],
        "a cue on a word its line does not say is named",
        validate.cue_misses(off),
    )

    # ------------------------------------------------ the person's narrator still wins
    picked = ep("Olga sings", narrator={"source": "kitcut", "voice": "Puck"})
    episode.carry(picked)
    check(
        json.loads(read(picked, "vo.json"))["voice"] == "Puck",
        "the narrator the person picked wins over the last's",
    )

    # ------------------------------------------------ when it starts empty instead
    for why, f in (
        ("a collection", ep("A promo", keep=["cast"])),
        ("another look", ep("Olga, painted", look="painted")),
        ("another frame", ep("Olga, a Short", frame="9:16")),
        ("captions in one", ep("Olga, captioned", captions=True)),
        ("no music in one", ep("Olga, quiet", music=False)),
        ("made in scenes", ep("Olga, in scenes", mode="scenes")),
    ):
        got = episode.carry(f)
        check(
            got and got.get("skipped") and not os.path.exists(f.path("film.js")),
            "%s: starts empty, and says why" % why,
            got,
        )
    first = ep("The first one", project="p-cccccccccc")
    os.environ[ON] = "all"
    check(
        episode.carry(first) == {"skipped": "no earlier episode"},
        "the series' first episode: nothing to start from",
    )

    # ------------------------------------------------ cast a round changed
    lib = ("u:alice", P)
    write(e2, "cast/owl.js", OWL2)  # a round's change: never in the library
    roundy = ep("Olga's scarf")
    got = episode.carry(roundy)
    check(
        got["cast"] == ["owl"] and read(roundy, "cast/owl.js") == OWL2,
        "a member the last episode changed after (a round) comes with it",
        got,
    )
    silver = OWL.replace("grey", "silver")
    moved = finish(
        ep("Olga's hat", created="2026-10-03T09:00:00"),
        FILM2.replace("kite", "hat"),
        cast={"owl": silver},
    )
    check(library.load(lib)["cast"]["owl"]["film"] == moved.id, "(the episode saved its own owl)")
    write(moved, "cast/owl.js", OWL2)  # and a round changed it after
    after = ep("Olga's boots")
    check(
        episode.carry(after)["cast"] == ["owl"] and read(after, "cast/owl.js") == OWL2,
        "one the last episode saved, then changed in a round, comes with the round's change",
    )
    gold = OWL.replace("grey", "gold")
    # another episode, made before it and finished since, changes the owl again
    finish(ep("Olga's gold", created="2026-10-02T12:00:00"), FILM2, cast={"owl": gold})
    newer = library.load(lib)["cast"]["owl"]["hash"]
    later = ep("Olga's coat")
    check(
        episode.carry(later)["cast"] == [],
        "one another episode changed since is left as the library has it",
    )
    check(library._hash(read(later, "cast/owl.js")) == newer, "(the library's, gold)")

    # ------------------------------------------------ the engine
    props = kit("props.js")
    mine = props + "\nSK.P.olga = function () { return 1; };\n"
    e3 = finish(ep("Olga's lamp", created="2026-10-04T09:00:00"), FILM2, engine={"props.js": mine})
    same = ep("Olga's lantern")
    got = episode.carry(same)
    check(
        got["engine"] == {"files": ["props.js"], "how": "copied"},
        "the same release: its engine changes come as they were",
        got["engine"],
    )
    check(read(same, "engine/props.js") == mine, "(its props.js)")
    check(same.engine_diff() == 0, "and engine_diff counts only what this film changes")
    check(
        read(same, "library/start/engine/props.js") == mine,
        "measured against the engine it started from",
    )

    rel = os.path.join(HOME, "releases", "aaaaaaaaaaaa", "sketch")
    os.makedirs(rel, exist_ok=True)
    for name in os.listdir(os.path.join(KIT, "sketch")):
        if name.endswith(".js"):
            shutil.copyfile(os.path.join(KIT, "sketch", name), os.path.join(rel, name))
    old = "// an older release's first line\n" + props.split("\n", 1)[1]
    with open(os.path.join(rel, "props.js"), "w", encoding="utf-8", newline="") as f:
        f.write(old)
    e3.update(release="aaaaaaaaaaaa")
    write(e3, "engine/props.js", old + "\nSK.P.olga = function () { return 1; };\n")
    merged = ep("Olga's candle")
    got = episode.carry(merged)
    check(
        got["engine"]["how"] == "merged",
        "another release: its changes merged onto today's engine",
        got["engine"],
    )
    check(
        read(merged, "engine/props.js") == mine, "(today's props.js, plus the series' own helper)"
    )

    with open(os.path.join(rel, "props.js"), "w", encoding="utf-8", newline="") as f:
        f.write(props + "// tail A\n")
    write(e3, "engine/props.js", props + "// tail B\n")
    clash = ep("Olga's torch")
    got = episode.carry(clash)
    check(
        got["engine"]["how"] == "conflict" and read(clash, "engine/props.js") == props,
        "changes that do not merge: today's engine",
        got["engine"],
    )
    check(
        "tail B" in (read(clash, "library/start/engine.diff") or ""),
        "and what they were, in library/start/engine.diff",
    )
    check("engine.diff" in agent.ask(clash, []), "which the first message names")
    check(
        "engine_from" not in clash.record() or not clash.record()["engine_from"],
        "measured against the release",
    )
    e3.update(release=RELEASE)
    write(e3, "engine/props.js", kit("props.js"))

    # ------------------------------------------------ a carry that fails half-way
    real = episode._engine

    def boom(*a):
        raise OSError("disk full")

    episode._engine = boom
    try:
        broke = ep("Olga's broken day")
        cast_before = sorted(os.listdir(broke.path("cast")))
        vo_before = read(broke, "vo.json")
        got = episode.carry(broke)
    finally:
        episode._engine = real
    check(got and got["skipped"].startswith("failed"), "a carry that fails says so", got)
    check(
        not os.path.exists(broke.path("film.js"))
        and not os.path.exists(broke.path("score.json"))
        and sorted(os.listdir(broke.path("cast"))) == cast_before
        and read(broke, "vo.json") == vo_before
        and not os.path.exists(broke.path(*episode.START)),
        "and takes back everything it copied: the episode starts empty",
    )
    check(
        agent.ask(broke, []).find("starts from the last one's code") < 0,
        "and its first message says nothing of it",
    )

    # ------------------------------------------------ engine_diff on a film made on another release
    other = Film.create("made on another release", 5, "drawn", client="u:alice")
    with open(os.path.join(rel, "props.js"), "w", encoding="utf-8", newline="") as f:
        f.write(old)
    other.update(release="aaaaaaaaaaaa")
    write(other, "engine/props.js", old)
    check(
        other.engine_diff() == 0, "a film finished on the next release is measured against its own"
    )
    write(other, "engine/props.js", old + "// mine\n")
    check(other.engine_diff() == 1, "and counts only its own change")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
