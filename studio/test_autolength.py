#!/usr/bin/env python
"""A film whose length Claude picks (kitcut.ai's "Let Claude choose the length"), without Claude:
python studio/test_autolength.py

Covers: the length read from a reply ("95", "1:35", "2 minutes", nonsense) on a 5 s step within
the longest; a film asked for with auto_length laid out at the longest, its record and its run's
record saying so; relength laying it out again (the manifest, the paintings' cap, scenes past
STUDIO_SCENES_OVER_S) and never past the longest; and pick_length end to end with the reply stubbed:
the length Claude said, the record and the run's record written for the site, and the fallback when
no answer comes. Every file is in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-autolength-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
from film import Film  # noqa: E402

SAVED = []  # what pick_length wrote to the run's record (kitcut.studio_runs)


async def fake_save(run_id, fields, final=False):
    SAVED.append((run_id, fields))


def manifest(f):
    with open(f.manifest, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    fails = []

    def check(ok, what):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    pf = agent.picked_from
    check(pf("95", 480) == 95, "a number of seconds")
    check(pf("95 seconds.", 480) == 95, "with words around it")
    check(pf("1:35", 480) == 95, "minutes and seconds")
    check(pf("2 minutes", 480) == 120, "minutes")
    check(pf("47", 480) == 45, "on a 5 s step")
    check(pf("600", 480) == 480, "never past the longest")
    check(pf("2", 480) == 5, "never under the shortest")
    check(pf("a while", 480) is None, "no length in it")

    os.environ.pop("STUDIO_SCENES_OVER_S", None)
    f = Film.create("How a zipper works", 480, "painted", client="u:alice", auto_length=True)
    r = f.record()
    check(r.get("auto_length") is True and r.get("length_max") == 480, "the record says so")
    check(r.get("length") == 480 and f.length == 480, "laid out at the longest until it is picked")
    check(f.mode == "single", "not in scenes before the length is picked")
    check(
        agent.first_record(f, "web", "u:alice").get("auto_length") is True, "the run's record too"
    )
    plain = Film.create("A film of a set length", 30, "drawn", client="u:alice")
    check("auto_length" not in plain.record(), "a film of a set length is not one")
    check(
        "Choose this film's length" in agent.pick_ask(f) and "to 480" in agent.pick_ask(f),
        "the pick reads the idea and the range",
    )

    with open(f.path("paint.json"), encoding="utf-8") as fh:
        before = json.load(fh)["max_images"]
    check(f.relength(95) == 95, "laid out again at the length picked")
    check(manifest(f)["duration"] == 95.0 and manifest(f)["poster_t"] == 94.6, "its manifest")
    with open(f.path("paint.json"), encoding="utf-8") as fh:
        after = json.load(fh)["max_images"]
    check(after < before, "its paintings' cap is the length's (%d, was %d)" % (after, before))
    r = f.record()
    check(r.get("length") == 95 and r.get("length_picked") is True, "its record")
    check(f.asked == 95, "what Claude is told it was asked for")
    check(f.relength(900) == 480, "never past the longest")

    os.environ["STUDIO_SCENES_OVER_S"] = "300"
    try:
        check(f.relength(400) == 400 and f.mode == "scenes", "made in scenes past the threshold")
        check(
            manifest(f).get("scenes") == "scenes" and os.path.isdir(f.path("scenes")),
            "with scenes/",
        )
        check(f.relength(60) == 60 and f.mode == "single", "and in one piece under it")
        check("scenes" not in manifest(f), "its manifest no longer names scenes")
    finally:
        os.environ.pop("STUDIO_SCENES_OVER_S", None)

    agent.save = fake_save
    agent.procs.SECRETS.setdefault("ANTHROPIC_API_KEY", "sk-test")  # never used: no real client
    said = []

    async def answer(prompt, opts):
        said.append(prompt)
        return "75", 0.002

    agent._pick_query = answer
    g = Film.create("A short ad for a bakery", 240, "drawn", client="u:bob", auto_length=True)
    events = []
    seconds, usd = asyncio.run(agent.pick_length(g, events.append))
    check(seconds == 75 and usd == 0.002, "the length Claude said, and what it cost")
    check(g.record().get("length") == 75 and g.length == 75, "the film is laid out at it")
    check(SAVED[-1] == (g.id, {"length": 75, "length_picked": True}), "the site is told the length")
    check(any(e["type"] == "say" and "1:15" in e["text"] for e in events), "the film's log says it")

    async def silent(prompt, opts):
        raise TimeoutError("no answer")

    agent._pick_query = silent
    h = Film.create("Another one", 40, "drawn", client="u:bob", auto_length=True)
    seconds, usd = asyncio.run(agent.pick_length(h, events.append))
    check(seconds == 40 and usd == 0.0, "no answer: a minute, or the longest when that is less")
    k = Film.create("And another", 300, "drawn", client="u:bob", auto_length=True)
    check(asyncio.run(agent.pick_length(k, events.append))[0] == agent.PICK_FALLBACK_S, "a minute")

    print("\n%s" % ("all passed" if not fails else "%d FAILED" % len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
