#!/usr/bin/env python
"""prune.py on films made of empty files in a home of its own: no browser, no network, seconds.

    python studio/test_prune.py

A finished film loses its working pictures and nothing else: the frames the review read, the
thumbnail stills, the silent render -- and keeps what it is made of, the Free plan's closing in
temp/brand, its record lock, the thumbnails' moments sheet and recorded look. A plan removes
nothing. A film being made, waiting for a voice, being changed or drawn again is left alone, and
so is a piece something wrote to lately. A folder a dead run left renamed goes. The review renders
its frames again once they are gone. And the paths and words this script shares with rounds.py and
unbrand.py without importing them are the same.
"""

import os
import sys
import json
import time
import shutil
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-prune-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402, F401 -- imports agent, which imports _env first
import film as films  # noqa: E402
import prune  # noqa: E402
import review  # noqa: E402
import rounds  # noqa: E402
import unbrand  # noqa: E402

bad = []
OLD = time.time() - 48 * 3600


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok   " if ok else "FAIL ", what, "" if ok else "  -- %r" % (got,)))
    if not ok:
        bad.append(what)


def touch(p, body="x", at=OLD):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    os.utime(p, (at, at))
    return p


def age(d, at=OLD):
    """Every folder under d as old as its files (making a file makes its folder new)."""
    for root, _, _ in os.walk(d):
        os.utime(root, (at, at))


GOES = (
    "temp/motion/000.50.png",
    "temp/motion/001.00.png",
    "temp/motion/report.json",
    "temp/motion-before/000.50.png",
    "temp/motion-before/report.json",
    "temp/motion-after/000.00.png",
    "temp/strip/012.40.png",
    "temp/thumbs/stills-0123456789abcdef/012.40.png",
    "temp/thumbs/stills-0123456789abcdef/4012.40.png",
    "temp/thumbs/probe/003.00.png",
    "temp/film_silent.mp4",
    "temp/film_silent_segments/0001.mp4",
    "temp/motion.pruned-4242/000.50.png",
)
STAYS = (
    "studio.json",
    "sketch.json",
    "film.js",
    "engine/engine.js",
    "cast/pip.js",
    "audio/vo/timeline.json",
    "outputs/film.mp4",
    "outputs/review/sheet-1.jpg",
    "outputs/youtube/UCx/thumb-1.jpg",
    "temp/brand/outro.js",
    "temp/brand/kitcut.png",
    "temp/brand/closing.wav",
    "temp/record.lock",
    "temp/lines/L01.mp3",
    "temp/system-prompt.md",
    "temp/castsheet/stills/000.75.png",
    "temp/thumbs/moments-0123456789abcdef.jpg",
    "temp/thumbs/stills-0123456789abcdef/style.json",
    "temp/thumbs/stills-0123456789abcdef/boxes.json",
    "temp/thumbs/stills-0123456789abcdef/manifest/sketch.json",
)
N = [0]


def film(state="done", **rec):
    N[0] += 1
    fid = "studio-20261001-0000%02d-%s" % (N[0], "abcdef"[N[0] % 6] * 6)
    d = os.path.join(HOME, "projects", fid)
    for rel in GOES + STAYS:
        touch(os.path.join(d, *rel.split("/")))
    touch(os.path.join(d, "studio.json"), json.dumps({"state": state, **rec}))
    # the film's code is older than the frames drawn from it, as on a film that is finished
    for name in ("sketch.json", "film.js"):
        touch(os.path.join(d, name), json.dumps({"duration": 2}), at=OLD - 3600)
    age(d)
    return films.Film(d)


def have(f, rels):
    return [r for r in rels if os.path.exists(f.path(*r.split("/")))]


def finished_film():
    f, other = film(), film()
    res = prune.sweep(plan=True)
    check(have(f, GOES) == list(GOES), "a plan removes nothing", have(f, GOES))
    kinds = set(res["kinds"])
    want = {"motion", "motion-before", "motion-after", "strip", "thumbs", "silent", "leftover"}
    check(kinds == want, "and names every kind it would", kinds)
    check(res["kinds"]["thumbs"]["files"] == 6, "the thumbnail stills of both films, counted", res)
    planned = res["bytes"]

    res = prune.sweep(only=f.id)
    check(not have(f, GOES), "a finished film's working pictures are gone", have(f, GOES))
    check(
        have(f, STAYS) == list(STAYS), "and nothing else of it is", set(STAYS) - set(have(f, STAYS))
    )
    check(have(other, GOES) == list(GOES), "the film beside it was not asked about, and is whole")
    check(res["left"] == 0 and res["bytes"] * 2 == planned, "what went is what the plan said", res)
    check(
        not [n for n in os.listdir(f.path("temp")) if ".pruned-" in n],
        "no renamed folder is left behind",
        os.listdir(f.path("temp")),
    )
    again = prune.sweep(only=f.id)
    check(again["bytes"] == 0 and again["films"] == 0, "a second run finds nothing to do", again)


def left_alone():
    making = film("claude")
    queued = film("queued")
    finishing = film("finishing")
    waiting = film("waiting")
    changing = film(round={"state": "running"})
    asked = film()
    touch(os.path.join(rounds.MARKS, asked.id + ".json"), "{}")
    redrawn = film()
    touch(os.path.join(unbrand.MARKS, redrawn.id + ".json"), "{}")
    res = prune.sweep()
    for f, what in (
        (making, "being written"),
        (queued, "queued"),
        (finishing, "being rendered"),
        (waiting, "waiting for its narrator's voice"),
        (changing, "in a round of changes"),
        (asked, "with a round asked for"),
        (redrawn, "being drawn again without its branding"),
    ):
        check(have(f, GOES) == list(GOES), "a film %s is left alone" % what, have(f, GOES))
    check(
        res["skipped"] == {"being made": 4, "being changed": 2, "being drawn again": 1},
        "and counted with its reason",
        res["skipped"],
    )
    for f in (making, queued, finishing, waiting, changing, asked, redrawn):
        shutil.rmtree(f.dir)
    os.remove(os.path.join(rounds.MARKS, asked.id + ".json"))
    os.remove(os.path.join(unbrand.MARKS, redrawn.id + ".json"))


def in_use():
    f = film()
    now = time.time()
    touch(f.path("temp", "motion", "002.00.png"), at=now)  # the review is rendering it
    touch(f.path("temp", "thumbs", "work", "page.html"), at=now)  # an option is being made
    prune.sweep(only=f.id)
    check(
        os.path.exists(f.path("temp", "motion", "000.50.png")),
        "frames something wrote to within the hours asked are kept",
    )
    check(
        os.path.exists(f.path("temp", "thumbs", "stills-0123456789abcdef", "012.40.png")),
        "thumbnail stills are kept while an option is being made beside them",
    )
    check(not os.path.exists(f.path("temp", "strip")), "the film's other pieces, untouched, go")
    prune.sweep(older_h=0, only=f.id)
    check(not os.path.exists(f.path("temp", "motion")), "--older-than 0 takes them however new")
    shutil.rmtree(f.dir)


def review_renders_again():
    f = film()
    made = []
    real = review.render_stills

    def fake(d, times, into, extra=()):
        made.append(into)
        touch(os.path.join(d, into, "report.json"), "{}", at=time.time())
        return ""

    review.render_stills = fake
    try:
        _, fresh = review.folder_frames(f.dir)
        check(not fresh and not made, "the review keeps frames newer than the film", made)
        prune.sweep(only=f.id)
        _, fresh = review.folder_frames(f.dir)
        check(fresh and len(made) == 1, "and renders them again once they are pruned", made)
    finally:
        review.render_stills = real
    shutil.rmtree(f.dir)


def same_as_the_studio():
    check(prune.ROUND_MARKS == rounds.MARKS, "a round's mark is where rounds.py puts it")
    check(prune.UNBRAND_MARKS == unbrand.MARKS, "an unbranding's mark is where unbrand.py puts it")
    check(prune.ROUND_ACTIVE == rounds.ACTIVE, "a round under way is what rounds.py calls one")
    check(
        "temp" in rounds.OWN,
        "a round never takes temp/ into a version (so pruning cannot break one)",
    )
    check(unbrand.WORK[0] == "temp" and unbrand.WORK[1] not in prune.WHOLE + prune.STILLS,
          "an unbranding's own folder in temp/ is not one this removes")  # fmt: skip


if __name__ == "__main__":
    try:
        finished_film()
        left_alone()
        in_use()
        review_renders_again()
        same_as_the_studio()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)
