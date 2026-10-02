#!/usr/bin/env python
"""A series' episode log (canon.py, library.canon_of/put_canon/canon_note), without Claude:
python studio/test_canon.py

Covers: an entry held to the log's shape and sizes, the log kept oldest first with a film
finished again replacing its own entry, the next episode's first message carrying every episode,
the oldest shrinking once the log is long, an up-to-date entry costing no call, and a film that
is not an episode (no project, an anonymous visitor's) getting no entry. Claude is a stub; every
file is in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-canon-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canon  # noqa: E402 -- imports _env first
import library  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

PROJECT = {"id": "p-abcdefghij", "name": "Duchess", "brief": "A deadpan cat."}
CALLS = []


async def fake_ask(text, sheet, auth, film, model, effort, system, session):
    CALLS.append(text)
    n = len(CALLS)
    return {
        "title": "Episode %d" % n,
        "story": "She resists the fridge, then does not. " * 20,  # far too long: cut
        "catchphrases": ["Just one lick.", "", "Lick forty."] + ["extra"] * 9,
        "twist": "The family gives her a saucer.",
        "fact": "",
        "new": ["the kitchen", "the fridge"],
        "callbacks": "not a list",
    }, 0.01


async def nothing(*a, **k):
    return None


def episode(prompt, created, client="u:alice", project=PROJECT):
    f = Film.create(prompt, 5, "drawn", client=client, project=project)
    f.update(state="done", created=created, claude_said="Made it.", title=prompt)
    with open(f.path("vo.json"), "w", encoding="utf-8") as fh:
        json.dump({"lines": [{"text": "This is Duchess."}, {"text": prompt}]}, fh)
    return f


def main():
    ytdraft.ask_json = fake_ask
    canon.agent.save = nothing
    fails = []

    def check(ok, what):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    e2 = episode("The Box", "2026-09-30T22:00:00")
    e1 = episode("The Dot", "2026-09-30T21:00:00")
    lib = canon.project_of(e1)[0]
    check(lib is not None and lib[1] == PROJECT["id"], "an episode has its project's library")

    a = asyncio.run(canon.write(e2))
    b = asyncio.run(canon.write(e1))
    check(len(CALLS) == 2, "one call per entry")
    check(len(a["story"]) <= canon.LIMITS["story"], "the story is cut to its size")
    check(a["catchphrases"][:2] == ["Just one lick.", "Lick forty."], "empty items dropped")
    check(len(a["catchphrases"]) == canon.LIMITS["catchphrases"], "lists cut to their length")
    check(a["callbacks"] == [], "a list that is not one is empty")
    log = library.canon_of(lib)
    check([e["film"] for e in log] == [e1.id, e2.id], "the log is oldest first, not by writing")
    check(b["made"].startswith("2026-09-30T21"), "an entry carries when its film was made")

    asyncio.run(canon.write(e1))
    check(len(CALLS) == 2, "an up-to-date entry costs no call")
    asyncio.run(canon.write(e1, force=True))
    check(len(CALLS) == 3 and len(library.canon_of(lib)) == 2, "a rewrite replaces its own entry")

    nxt = episode("The Sour Cream", "2026-10-01T20:00:00")
    nxt.update(state="queued", library={"cast": [], "films": []})
    note = library.note(nxt)
    check("The series so far" in note, "the next episode's note carries the log")
    check('1. "Episode' in note and '2. "Episode' in note, "every episode, numbered")
    check("twist: The family gives her a saucer." in note, "with its twist")

    entries = [dict(log[0], film="f%d" % i, title="Ep %d" % i) for i in range(400)]
    text = library.canon_note(entries)
    check(len(text) <= library.CANON_NOTE_MAX + 400, "a long log fits its budget")
    check("Ep 399" in text and "twist:" in text[-400:], "the newest stay whole")
    check("twist:" not in text.split("\n")[1] and "twist:" in text, "the oldest shrink first")

    lone = Film.create("a film of her own", 5, "drawn", client="u:alice")
    check(asyncio.run(canon.write(lone)) is None, "a film outside projects has no entry")
    anon = episode("an anonymous episode", "2026-10-01T00:00:00", client="203.0.113.9")
    check(asyncio.run(canon.write(anon)) is None, "nor does an anonymous visitor's")
    check(canon.premake(lone) is None, "premake does nothing for a film that is not an episode")

    print("\n%s" % ("all passed" if not fails else "%d FAILED" % len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
