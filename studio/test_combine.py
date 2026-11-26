#!/usr/bin/env python
"""An episode that combines earlier ones (kitcut.ai's combine_films): python studio/test_combine.py

Covers: server.combine_of (only the client's own finished episodes of the same project, 2 to
COMBINE_MAX, each once), library.seed giving the new film every combined episode's files first
and in play order whatever MEMORY says (and the earlier episodes besides, up to MEMORY), the note
naming them as what the film is made from, and a film's narration lines saying who speaks.
Everything in a throwaway STUDIO_HOME; nothing is rendered.
"""

import os
import sys
import json
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-combine-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import library  # noqa: E402
from film import Film  # noqa: E402

P1, P2 = "p-aaaaaaaaaa", "p-bbbbbbbbbb"
PROJECT = {"id": P1, "name": "Clan Tales", "brief": "Cats of the forest."}


def write(film, rel, text):
    p = film.path(*rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def episode(prompt, project=P1, client="u:alice", done=True):
    f = Film.create(prompt, 5, "drawn", client=client, project=dict(PROJECT, id=project))
    write(f, "film.js", "// %s\n" % prompt)
    if done:
        f.update(state="done")
        library.keep(f, [], {})
    return f


def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    try:
        eps = [episode("scene %d" % i) for i in range(1, 10)]  # 9 finished episodes, newest last
        other = episode("elsewhere", project=P2)
        theirs = episode("bob's", client="u:bob")
        making = episode("not yet", done=False)
        pick = [eps[0].id, eps[2].id, eps[1].id]  # the three oldest, out of the order made

        # ------------------------------------------------ which films may be combined
        ok, err = server.combine_of(pick, "u:alice", PROJECT)
        check(ok == pick and err is None, "the client's own finished episodes, in the order asked")
        check(server.combine_of(None, "u:alice", PROJECT) == ([], None), "none asked: none")
        check(server.combine_of(pick, "u:alice", None)[1], "only for an episode of a project")
        check(
            server.combine_of([eps[0].id], "u:alice", PROJECT)[1], "one film is not a combination"
        )
        check(server.combine_of([eps[0].id] * 2, "u:alice", PROJECT)[1], "nor one film twice")
        check(
            server.combine_of(["x"] * (server.COMBINE_MAX + 1), "u:alice", PROJECT)[1],
            "at most COMBINE_MAX",
        )
        for odd, what in [(other, "another project's"), (theirs, "someone else's")]:
            check(
                "not an episode" in server.combine_of([eps[0].id, odd.id], "u:alice", PROJECT)[1],
                "%s film is refused" % what,
            )
        check(
            "not finished" in server.combine_of([eps[0].id, making.id], "u:alice", PROJECT)[1],
            "an unfinished one is refused",
        )
        check(
            "not a film id" in server.combine_of([eps[0].id, "../x"], "u:alice", PROJECT)[1],
            "a path is not a film id",
        )

        # ------------------------------------------------ the new film gets them first
        new = Film.create("all of it", 15, "drawn", client="u:alice", project=PROJECT)
        new.update(combine=pick)
        got = library.seed(new)
        joined = [m for m in got["films"] if m.get("combined")]
        check([m["combined"] for m in joined] == [1, 2, 3], "every combined episode, numbered")
        texts = [
            open(new.path(*m["dir"].split("/"), "film.js"), encoding="utf-8").read() for m in joined
        ]
        check(
            texts == ["// scene 1\n", "// scene 3\n", "// scene 2\n"],
            "with its own film.js, in play order (%s)" % texts,
        )
        rest = [m for m in got["films"] if not m.get("combined")]
        check(len(rest) == library.MEMORY, "and the earlier episodes besides, up to MEMORY")
        check(
            not {m["prompt"] for m in rest} & {"scene 1", "scene 2", "scene 3"},
            "never one of the combined ones twice",
        )
        about = json.load(
            open(new.path(*joined[1]["dir"].split("/"), "about.json"), encoding="utf-8")
        )
        check(about.get("combined") == 2, "about.json says its place")
        note = library.note(new)
        check("combines 3 of the project's finished episodes" in note, "the note says so")
        first = note.index("1. %s" % joined[0]["dir"])
        check(
            first < note.index("2. %s" % joined[1]["dir"]) < note.index("3. %s" % joined[2]["dir"]),
            "and names them in play order",
        )
        check(
            note.count(joined[0]["dir"]) == 1,
            "a combined episode is not listed again among the earlier ones",
        )
        plain = Film.create("one more", 5, "drawn", client="u:alice", project=PROJECT)
        library.seed(plain)
        check(
            "combines" not in library.note(plain),
            "a film that combines nothing hears nothing of it",
        )

        # ------------------------------------------------ who speaks a line
        f = eps[0]
        write(f, "vo.json", json.dumps({"voice": "Kore", "cast": {"rusty": {"voice": "Puck"}}}))
        write(
            f,
            "audio/vo/timeline.json",
            json.dumps(
                {
                    "lines": [
                        {"i": 0, "text": "Once.", "start": 0.5, "dur": 1, "file": "a.wav"},
                        {
                            "i": 1,
                            "text": "Hi!",
                            "start": 2,
                            "dur": 1,
                            "file": "b.wav",
                            "who": "rusty",
                        },
                    ]
                }
            ),
        )
        lines = library.film_lines(f)
        check(
            "who" not in lines[0] and lines[1]["who"] == "rusty",
            "a line says who speaks it; the narrator's does not",
        )
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("all passed" if not bad else "%d FAILED" % len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
