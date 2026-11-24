#!/usr/bin/env python
"""Rounds of changes to a finished film (rounds.py), end to end with Claude stubbed out: no API
calls, no cost.

    python studio/test_rounds.py

A finished film is made through the real API (the stub writes the example film), then its
maker's notes are sent: the stand-in for Claude reads the notes and their frames, changes
film.js, and answers each note with the round's real tools. Everything else is real -- the copy
the round works on, the stills, the soundtrack, the render, the swap, the record, the limits.
What is checked: a version made and the one before kept; the film "done" and playable all the
way through; a round that fails, changes nothing or is stopped leaving the film byte for byte as
it was; going back to a version and forward again; a swap cut short undone; a round whose
server went away made again, once; the notes refused that cannot be a round; and that a round
is not one of the day's films but does take one of its person's places.
A few minutes, most of it rendering. Everything happens in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import stat
import time
import types
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-rounds-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import film as films  # noqa: E402
import rounds  # noqa: E402
import store  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

os.environ.pop("STUDIO_MEDIA_BASE", None)  # no copy online (test_media.py has its own stand-in)
# what follows a finished film in the background (its share words and pictures, its moments
# sheet) writes into the film's outputs for a while: not this test's, and it would make "the
# film is as it was" a race
os.environ["STUDIO_SHARE"] = "0"
server.thumbs.premake = lambda film: None
server.procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
server.procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
server.procs.SECRETS.pop("STUDIO_R2_SECRET", None)

TOKEN = "test-token"
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}
SEEN = []  # what each round's stand-in found: {"notes", "frames", "tools", "prompt"}
PLAN = {"do": "change"}  # what the next round's stand-in does: change | nothing | fail | slow


async def fake_claude(
    film,
    emit,
    meter,
    tools,
    auth="api",
    prompt=None,
    resume=None,
    budget_usd=None,
    system=None,
    effort=None,
):
    ex = os.path.join(films.KIT, "config", "sketch", "example")
    if not film.record().get("round_of"):  # the film itself: the example, no narration
        for f in films.MADE:
            shutil.copy(os.path.join(ex, f), film.dir)
            # as a film scaffolded from a release has them (a release's files are read-only, and
            # a copy keeps that): a round must change the film all the same
            os.chmod(film.path(f), stat.S_IREAD)
        with open(film.path("vo.json"), "w", encoding="utf-8") as f:
            json.dump({"voice": "Kore", "language": "en", "lines": []}, f)
        os.makedirs(film.path("audio", "vo"), exist_ok=True)
        meter.add("msg_" + film.id, USAGE)
        emit({"type": "cost", "usd": round(meter.usd(), 4)})
        await tools.check()
        return
    # a round: the copy of the film, the notes and their frames in notes/, the round's two tools
    tools.session = "fake-round-session"
    r = tools.round
    SEEN.append(
        {
            "dir": film.dir,
            "notes": os.path.isfile(film.path("notes", "notes.md")),
            "frames": sorted(n for n in os.listdir(film.path("notes")) if n.endswith(".png")),
            "prompt": prompt or "",
            "tail": "tail" in json.load(open(film.manifest, encoding="utf-8")),
            "pins": film.record().get("pins"),
            "resume": resume,
        }
    )
    meter.add("msg_round_%s_%d" % (film.id, len(SEEN)), USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    if resume:  # the short last turn for notes left unanswered: answer them
        for i in r.missing():
            await r.note(i, False, "I ran out of time before this one.")
        return
    do = PLAN["do"]
    if do == "fail":
        with open(film.path("film.js"), "a", encoding="utf-8") as f:
            f.write("\n// half a change\n")
        raise RuntimeError("Claude stopped early: a stub failure")
    if do == "slow":
        await asyncio.sleep(120)
        return
    if do == "nothing":
        await r.note(1, False, "I could not tell what to change.")
        await r.say_summary("Nothing was changed.")
        return
    with open(film.path("film.js"), "a", encoding="utf-8") as f:
        f.write("\n// changed in round %d\n" % len(SEEN))
    await tools.check()
    await tools.stills([1.0], False)
    emit({"type": "tool", "text": "changed film.js (stub)"})
    await r.note(1, True, "The label is bigger now.")
    if do != "forgets" and len(r.notes) > 1:
        await r.note(2, False, "The music is written to end with the film; a longer film has room.")
    await r.say_summary("The label is bigger. The music stays as it was.")


TOLD = {}  # run id -> the lines its document in the database said, in order (live.py)


def note_line(rid):
    d = agent.STORE.docs.get(rid) or {}
    said = TOLD.setdefault(rid, [])
    if d.get("now") and (not said or said[-1] != d["now"]):
        said.append(d["now"])
    return d


async def wait_film(c, auth, jid, limit=600):
    t0, st = time.time(), {}
    while time.time() - t0 < limit:
        note_line(jid)
        st = await (await c.get("/api/films/%s?since=0" % jid, headers=auth)).json()
        if st.get("status") in ("done", "error", "cancelled"):
            break
        await asyncio.sleep(1)
    return st


async def wait_round(
    f, states=("done", "failed", "cancelled", "interrupted", "unchanged"), limit=600
):
    """Until the film's round is in one of these states; also every state the FILM was in on the
    way (it must stay done)."""
    t0, seen = time.time(), set()
    while time.time() - t0 < limit:
        rec = f.record()
        seen.add(rec.get("state"))
        note_line((rec.get("round") or {}).get("id"))
        if (rec.get("round") or {}).get("state") in states:
            break
        await asyncio.sleep(0.3)
    await asyncio.sleep(0.3)  # the round's last record write
    return f.record(), seen


def differ(a, b):
    """What is not the same in two trees, for a failed check to say."""
    keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return (
        ", ".join(keys[:6]) + (" ... %d in all" % len(keys) if len(keys) > 6 else "") or "nothing"
    )


def tree(f):
    """Every file a version is made of, with its size and time: the film is 'as it was' when
    this is."""
    out = {}
    for root, dirs, names in os.walk(f.dir):
        rel = os.path.relpath(root, f.dir).replace("\\", "/")
        top = rel.split("/")[0]
        if top in rounds.OWN:
            dirs[:] = []
            continue
        for n in names:
            if (
                rel == "." and n in rounds.OWN
            ):  # the film's record and log: its own, not a version's
                continue
            p = os.path.join(root, n)
            out[(rel + "/" + n).lstrip("./")] = (os.path.getsize(p), round(os.path.getmtime(p), 2))
    return out


NOTES = [
    {"id": "a", "kind": "spot", "t": 1.0, "x": 0.25, "y": 0.5, "text": "Make this label bigger."},
    {"id": "b", "kind": "film", "text": "Slower, warmer music."},
]


async def main():
    bad = []

    def check(ok, what):
        print("%s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            bad.append(what)

    agent.STORE = mem = store.MemoryStore()
    agent.run_claude = fake_claude

    # ------------------------------------------------ the notes, read for Claude (no film needed)
    lines = [
        {
            "i": 0,
            "text": "A bee sips nectar.",
            "start": 0.5,
            "end": 2.5,
            "words": [{"text": "bee", "s": 0.7, "e": 1.0}],
        },
        {"i": 1, "text": "Seal it with wax.", "start": 3.0, "end": 4.5, "words": []},
    ]
    told = rounds.notes_text(
        [
            {"id": "1", "kind": "spot", "t": 0.8, "x": 0.21, "y": 0.56, "text": "Bigger."},
            {"id": "2", "kind": "stretch", "t": 2.0, "t2": 4.0, "text": "Too fast."},
            {
                "id": "3",
                "kind": "line",
                "t": 3.0,
                "t2": 4.5,
                "line": 1,
                "was": "Seal it with wax.",
                "words": "Capped with wax.",
                "text": "",
            },
            {"id": "4", "kind": "film", "text": "Warmer."},
            {
                "id": "5",
                "kind": "spot",
                "t": 0.8,
                "x": 0.5,
                "y": 0.2,
                "w": 0.3,
                "h": 0.12,
                "text": "This title.",
            },
        ],
        lines,
        {"1": "notes/1.png", "5": "notes/5.png"},
    )
    check(
        'at the word "bee"' in told
        and "the middle left of the picture (21% from the left, 56% from the top)" in told
        and "from 0:02.0 to 0:04.0" in told
        and 'line 0 ("A bee sips nectar."); line 1 ("Seal it with wax.")' in told
        and 'Say this instead: "Capped with wax."' in told
        and "[the whole film]" in told
        and "notes/1.png (the orange ring is the spot)" in told,
        "a note is told to Claude with its moment, its spot in words, and what is being said",
    )
    check(
        "an area: the box around the top centre of the picture (50% from the left, 20% from "
        "the top), 30% of the picture wide and 12% tall"
        in told
        and "notes/5.png (the orange box is the area)" in told,
        "a note on a boxed area is told with where the box is and how big",
    )
    f0 = types.SimpleNamespace(  # a film as clean_notes reads one: its length, no narration
        length=8, record=lambda: {}, path=lambda *a: os.path.join(HOME, "no-such-file")
    )
    boxed = rounds.clean_notes(
        f0,
        [
            {
                "id": "a",
                "kind": "spot",
                "t": 1,
                "x": 0.5,
                "y": 0.5,
                "w": 0.4,
                "h": 0.001,
                "text": "x",
            },
            {"id": "b", "kind": "spot", "t": 1, "x": 0.5, "y": 0.5, "w": 0.4, "text": "x"},
            {"id": "c", "kind": "spot", "t": 1, "x": 0.5, "y": 0.5, "w": 7, "h": 0.5, "text": "x"},
        ],
    )
    check(
        [(n.get("w"), n.get("h")) for n in boxed] == [(0.4, 0.02), (None, None), (1.0, 0.5)],
        "a box is kept with its size (never thinner than a sliver, never past the picture); "
        "half a size is a point",
    )
    check(
        [round(v) for v in rounds._box({"x": 0.1, "y": 0.5, "w": 0.4, "h": 0.2}, 1000, 500)]
        == [0, 200, 300, 300],
        "a box that runs past the picture's edge is drawn inside it",
    )
    lim = rounds.limits(30, 3)
    check(
        lim["claude_s"] == 14 * 60 and lim["budget_usd"] < films.limits(30)["budget_usd"],
        "a round's allowance: minutes by its notes, less than a film's budget",
    )
    fab = rounds.limits(30, 3, model="claude-fable-5-2")
    check(
        fab["budget_usd"] == 2 * lim["budget_usd"] and fab["claude_s"] == lim["claude_s"],
        "a Fable round may spend twice the dollars, in the same minutes",
    )
    check(
        rounds.claude_of({"round": {"claude": {"model": "claude-fable-5-2", "effort": "max"}}})
        == {"model": "claude-fable-5-2", "effort": "max"}
        and rounds.claude_of({"round": {"claude": {"model": "gpt-9", "effort": "huge"}}}) == {}
        and rounds.claude_of({"model": "claude-fable-5-2"}) == {},
        "a round's model and effort are its own: never the film's, never one the studio lacks",
    )
    whole = [{"kind": "film"}, {"kind": "line"}, {"kind": "line"}, {"kind": "moment"}]
    check(
        rounds.wide(whole) == 1
        and rounds.limits(210, 4, rounds.wide(whole))["claude_s"] == 26 * 60
        and rounds.limits(210, 4)["claude_s"] == 16 * 60
        and rounds.limits(210, 20, 2)["claude_s"] == 68 * 60
        and rounds.limits(210, 20, 2, reach=9999)["claude_s"] == 70 * 60,
        "a note on the whole film adds the time to look at every shot it changes (fhkoaw.r1)",
    )
    turn = {"id": "a", "kind": "stretch", "t": 216, "t2": 285, "text": "Turn their heads."}
    paw = {"id": "b", "kind": "stretch", "t": 21, "t2": 23, "text": "A cat's paw."}
    check(
        rounds.weight([turn]) == 69 * rounds.REACH_S
        and rounds.weight([paw]) == 2 * rounds.REACH_S
        and rounds.weight([{"kind": "stretch", "t": 0, "t2": 900}]) == rounds.REACH_MAX_S
        and rounds.weight([{"kind": "film"}, {"kind": "moment", "t": 3}]) == 0
        and rounds.limits(285, 2, reach=rounds.weight([turn, paw]))["claude_s"]
        == 8 * 60 + 2 * 120 + 71 * rounds.REACH_S,
        "a note's working time grows with the seconds of film it covers (ch7tno.r2)",
    )
    long_ts = rounds.frame_times(turn, 285)
    check(
        long_ts[0] == 250.5
        and min(long_ts) == 216
        and max(long_ts) == 285
        and len(long_ts) == rounds.FRAMES_MAX + 1
        and rounds.frame_times(paw, 285) == [22.0, 21.0, 23.0]
        and rounds.frame_times({"kind": "moment", "t": 0.2}, 5) == [0.2, 0.0, 0.7]
        and rounds.frame_times({"kind": "moment", "t": 5.0}, 5) == [5.0, 4.5]
        and rounds.frame_times({"kind": "film"}, 5) == []
        and sum(map(len, rounds._thin([[1, 2, 3, 4], [5], [6, 7, 8]], 5))) == 5
        and [x[0] for x in rounds._thin([[1, 2, 3, 4], [5], [6, 7, 8]], 5)] == [1, 5, 6],
        "a note comes with frames from its start to its end, its own moment first",
    )
    told = rounds.notes_text(
        [paw],
        [],
        {"b": [(22.0, "notes/1.png"), (23.0, "notes/1-023.00.png"), (21.0, "notes/1-021.00.png")]},
    )
    check(
        "The frame at 0:22.0: notes/1.png" in told
        and "Around it: notes/1-021.00.png at 0:21.0, notes/1-023.00.png at 0:23.0" in told,
        "the notes name every frame of a note, in the film's order",
    )
    import tempfile

    class Kept:  # a film, as far as the history goes
        def __init__(self):
            self.dir = tempfile.mkdtemp()

        def path(self, *parts):
            return os.path.join(self.dir, *parts)

    kept = Kept()
    check(rounds.earlier(kept) == "" and rounds.history(kept) == [], "no rounds: nothing told")
    rounds.keep_history(
        kept,
        "f.r1",
        2,
        "done",
        [paw, turn],
        [{"id": "b", "state": "done", "reply": "It is a real cat's paw now."}],
        "The paw.",
    )
    rounds.keep_history(kept, "f.r1", 2, "done", [paw], [], None)  # asked twice: kept once
    rounds._backfill(
        kept,
        {
            "round": {
                "id": "f.r2",
                "n": 3,
                "state": "unchanged",
                "notes": [turn],
                "answers": [{"id": "a", "state": "cannot", "reply": "No room."}],
            }
        },
    )
    rounds._backfill(kept, {"round": {"id": "f.r3", "state": "running", "notes": [turn]}})
    told = rounds.earlier(kept, kept)
    check(
        [x["rid"] for x in rounds.history(kept)] == ["f.r1", "f.r2"]
        and "made version 2" in told
        and "[from 0:21.0 to 0:23.0] A cat's paw." in told
        and "Answered: Done. It is a real cat's paw now." in told
        and "made no version" in told
        and "Answered: Not changed. No room." in told
        and "do it another way" in told
        and os.path.isfile(kept.path("notes", "earlier.md")),
        "a round is told the rounds before it: what was asked, and what was answered",
    )

    from PIL import Image

    class Stills:  # the film's tools, as far as the second look goes: frames drawn "now"
        calls = []

        async def stills(self, times, sheet=True):
            Stills.calls.append(list(times))
            os.makedirs(kept.path("outputs", "review"), exist_ok=True)
            for ts in times:
                Image.new("RGB", (320, 180), "green").save(
                    kept.path("outputs", "review", "%06.2f.png" % ts)
                )

    spot = {"id": "c", "kind": "spot", "t": 4.0, "x": 0.5, "y": 0.5, "text": "Bigger."}
    said = {"id": "d", "kind": "line", "t": 1, "t2": 2, "line": 0, "text": "Slower."}
    ns = [paw, turn, spot, said]
    frames = {
        "b": [(22.0, "notes/1.png"), (21.0, "notes/1-021.00.png"), (23.0, "notes/1-023.00.png")],
        "a": [(250.5, "notes/2.png")],
        "c": [(4.0, "notes/3.png")],
        "d": [(1.5, "notes/4.png")],
    }
    os.makedirs(kept.path("notes", "before"), exist_ok=True)
    for ts in (21.0, 22.0, 23.0, 250.5, 4.0, 1.5):
        Image.new("RGB", (320, 180), "red").save(kept.path("notes", "before", "%06.2f.png" % ts))
    asked = []

    async def eyes(text, images):
        asked.append((text, len(images)))
        return {
            "notes": [
                {"number": 1, "ok": False, "sure": True, "why": "A grey pole with a knob."},
                {"number": 3, "ok": False, "sure": False, "why": "Cannot tell."},
                {"number": 9, "ok": False},
            ]
        }, 0.01

    verdicts = {
        "b": {"state": "done", "reply": "A paw."},
        "a": {"state": "cannot", "reply": "No."},
        "c": {"state": "done", "reply": "Bigger."},
        "d": {"state": "done", "reply": "Slower."},
    }
    seen = await rounds.looked(kept, Stills(), ns, verdicts, frames, eyes)
    check(
        seen
        == {
            "b": {"ok": False, "sure": True, "why": "A grey pole with a knob."},
            "c": {"ok": True, "sure": False, "why": "Cannot tell."},
        }
        and asked[0][1] == 2
        and "Picture 1 -- note 1 [from 0:21.0 to 0:23.0]: A cat's paw." in asked[0][0]
        and "Picture 2 -- note 3 [at 0:04.0] (the orange mark is the place): Bigger." in asked[0][0]
        and sorted(Stills.calls[0]) == [4.0, 21.0, 22.0, 23.0]
        and os.path.isfile(kept.path("notes", "after", "1.jpg"))
        and os.path.isfile(kept.path("notes", "after", "3-now.png")),
        "the second look: every note answered done, its frames as they were beside now; not "
        "the notes left undone or on the words; a doubt it is not sure of does not send it back",
    )
    await rounds.looked(kept, Stills(), ns, verdicts, frames, eyes, rules=["Cats trot."])
    check(
        "plainly breaks one of them" in asked[-1][0]
        and "- Cats trot." in asked[-1][0]
        and "standing rules" not in asked[0][0]
        and films.clean_rules([" Cats  trot. ", "cats trot.", "", 5, "x" * 400])
        == ["Cats trot.", "5", "x" * 300]
        and films.rules_of({"project": {"rules": ["A."]}}) == ["A."]
        and films.rules_of({}) == [],
        "the second look is told the series' standing rules, as the studio keeps them",
    )
    import library

    check(
        "must not have to leave again" in library.RULES and "one at a time" in library.RULES,
        "a new episode is told to follow its project's standing rules, and to check each",
    )
    shown = await rounds.proofs(kept, Stills(), ns, frames)
    check(
        shown == {"b": "proof-1.jpg", "a": "proof-2.jpg", "c": "proof-3.jpg", "d": "proof-4.jpg"}
        and all(os.path.isfile(kept.path("notes", "after", v)) for v in shown.values()),
        "every timed note has its before and after as one picture, the ones not made too",
    )
    again = rounds.again_text(ns, [1], seen)
    only = await rounds.looked(kept, Stills(), ns, verdicts, frames, eyes, {"c"})
    check(
        "1. [from 0:21.0 to 0:23.0] A cat's paw." in again
        and "What they saw: A grey pole with a knob." in again
        and "notes/after/022.00.png" in again
        and list(only) == ["c"]
        and asked[-1][1] == 1,
        "what did not show goes back with what was seen, and is looked at again alone",
    )
    told = rounds.ASK % {
        "earlier": "",
        "project": "",
        "extra": "",
        "length": 210,
        "minutes": 18,
        "notes": "1. [the whole film]",
        "voice": rounds.VOICE % {"runs": rounds.limits(210, 4)["voice_runs"]},
    }
    check(
        "A note is done whole" in told
        and "never leave the narration naming something the picture no longer shows" in told
        and "`stills` of EVERY shot you changed" in told
        and "nobody blinks out and back" in told
        and "not a fence" in told
        and "Make each group as ONE change" in told
        and 'Never answer a note "not changed" because time is short' in told
        and "`stills` once more at every note's own moment" in told
        and "This round has 7 recordings" in told
        and "shortened BEFORE recording" in told,
        "a round is told: a note whole or not at all, every changed shot looked at, the "
        "recordings it has and what they are kept for",
    )

    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        auth = {"Authorization": "Bearer " + TOKEN}
        me = auth | {"X-Client-Ip": "u:maker", "Cf-Ray": "t", "X-Branding": "1", "X-Fps": "30"}
        other = auth | {"X-Client-Ip": "u:stranger", "Cf-Ray": "t"}
        lims = await (await c.get("/api/limits")).json()
        check(
            lims["rounds"]["per_film_per_day"] == rounds.PER_DAY
            and lims["rounds"]["notes"] == rounds.MAX_NOTES,
            "the limits say what a round's are",
        )

        # ------------------------------------------------ a finished film (Free plan: mark and closing)
        r = await c.post(
            "/api/films", json={"prompt": "a film to change", "seconds": 5}, headers=me
        )
        fid = (await r.json()).get("id")
        st = await wait_film(c, auth, fid)
        f = films.Film.open(fid)
        check(
            st.get("status") == "done",
            "a film is made (%s)" % (st.get("error") or st.get("status")),
        )
        url = "/api/films/%s/versions" % fid
        await asyncio.sleep(1.5)  # the line's last write
        d = mem.docs.get(fid) or {}
        told = TOLD.get(fid) or []
        check(
            any("Claude is writing" in x for x in told) and any("Rendering" in x for x in told),
            "while it was made, the film's document said what it was doing (%s)" % told,
        )
        check(
            d.get("now") is None
            and d.get("now_at") is None
            and d.get("stage") is None
            and d.get("state") == "done",
            "and says nothing once it is done (%r, %r)" % (d.get("now"), d.get("stage")),
        )

        # ------------------------------------------------ its versions, before any round
        r = await c.get(url, headers=other)
        check(r.status == 403, "a stranger is not told a film's versions")
        r = await c.get(url, headers=me)
        v = await r.json()
        one = (v.get("versions") or [{}])[0]
        check(
            r.status == 200
            and v["version"] == 1
            and len(v["versions"]) == 1
            and v["round"] is None,
            "its maker is: one version, no round",
        )
        # Sharper pictures were taken away (2026-11-17): a film's versions say nothing of its
        # pictures' quality, and a round asking for one is refused
        check("pictures" not in v, "the versions say nothing of picture quality")
        r = await c.post(url, json={"key": "s0", "from": 1, "sharpen": "high"}, headers=me)
        check(
            r.status == 400 and (await r.json()).get("reason") == "sharpen",
            "a sharper version is refused (%d)" % r.status,
        )
        check(
            one.get("strip") == {"count": 24, "w": 160, "h": 90}
            and os.path.getsize(f.path("outputs", "strip.jpg")) > 2000
            and one.get("duration") == 5.0
            and abs(one.get("video_s") - 8.0) < 0.2
            and one.get("fps") == 30,
            "version 1 has its filmstrip, the film's length and the video's (its closing included)",
        )
        check(
            v["words"] == {"can": False, "why": "no_voice"} or v["words"] == {"can": True},
            "and whether its words may change (%s)" % v["words"],
        )
        check(
            mem.docs[fid].get("version") == 1 and len(mem.docs[fid].get("versions") or []) == 1,
            "the film's document in the database carries its versions (the site reads them there)",
        )
        made = os.path.getmtime(f.path("outputs", "strip.jpg"))
        await c.get(url, headers=me)
        check(
            os.path.getmtime(f.path("outputs", "strip.jpg")) == made,
            "asked again, nothing is made again",
        )

        # ------------------------------------------------ notes that cannot be a round
        for body, status, why in (
            ({"notes": []}, 400, "no notes"),
            ({"notes": [{"id": "a", "kind": "wish", "text": "x"}]}, 400, "an unknown kind"),
            (
                {"notes": [{"id": "a", "kind": "spot", "t": 1, "text": "x"}]},
                400,
                "a spot with no place",
            ),
            (
                {"notes": [{"id": "a", "kind": "film", "text": " "}]},
                400,
                "a note that says nothing",
            ),
            (
                {"notes": [{"id": "a", "kind": "line", "line": 7, "text": "x"}]},
                409,
                "a line the film has not",
            ),
            ({"notes": NOTES, "from": 3}, 409, "notes written on another version"),
        ):
            r = await c.post(url, json=body, headers=me)
            check(r.status == status, "refused: %s (%d)" % (why, r.status))
        r = await c.post(url, json={"notes": NOTES}, headers=other)
        check(r.status == 403, "a stranger cannot change a film")
        check(
            not os.path.isdir(rounds.ROOT) or not rounds.in_flight(),
            "and none of that started a round",
        )

        # ------------------------------------------------ a round: version 2
        before, old_mp4 = tree(f), os.path.getsize(f.path("outputs", "film.mp4"))
        per_day, server.PER_CLIENT_DAILY = server.PER_CLIENT_DAILY, 0  # the day's films are used up
        try:
            r = await c.post(url, json={"key": "k1", "from": 1, "notes": NOTES}, headers=me)
        finally:
            server.PER_CLIENT_DAILY = per_day
        b = await r.json()
        rid = (b.get("round") or {}).get("id")
        check(
            r.status == 202 and rid == fid + ".r1" and b["round"]["n"] == 2,
            "a round is accepted, though its maker has had the day's films (%s %s)" % (r.status, b),
        )
        r2 = await c.post(url, json={"key": "k1", "from": 1, "notes": NOTES}, headers=me)
        check(
            r2.status == 202 and (await r2.json())["round"]["id"] == rid and len(rounds.JOBS) == 1,
            "asked again with the same key, it is the same round",
        )
        r3 = await c.post(url, json={"key": "k2", "from": 1, "notes": NOTES}, headers=me)
        check(
            r3.status == 409 and (await r3.json()).get("reason") == "round",
            "a second round must wait for the first",
        )
        r4 = await c.post("/api/films", json={"prompt": "another", "seconds": 5}, headers=me)
        check(
            r4.status == 429, "the round takes its maker's one film-at-once place (%d)" % r4.status
        )
        r5 = await c.post(
            "/api/films/%s/youtube" % fid, json={"key": "y1", "to": "https://x"}, headers=me
        )
        check(
            r5.status == 409 and (await r5.json()).get("reason") == "round",
            "and the film is not sent to YouTube meanwhile",
        )
        mid = await (await c.get("/api/films/%s?since=0" % fid, headers=auth)).json()
        check(
            mid.get("status") == "done" and mid.get("video_url"),
            "while it is made the film is done, and plays",
        )
        rec, states = await wait_round(f)
        rd = rec.get("round") or {}
        check(
            rd.get("state") == "done",
            "the round finishes (%s: %s)" % (rd.get("state"), rd.get("error")),
        )
        check(states == {"done"}, "the film's own state never left done (%s)" % states)
        seen = SEEN[-1] if SEEN else {}
        check(
            seen.get("notes")
            and seen.get("frames") == ["1-000.50.png", "1-001.50.png", "1.png"]
            and [x["rid"] for x in rounds.history(f)] == [rd.get("id")]
            and rounds.history(f)[0]["notes"][0].get("reply")
            and "Make this label bigger." in seen.get("prompt", "")
            and "the whole film" in seen.get("prompt", ""),
            "Claude was given the notes, and the frame of the one at a moment (%s)"
            % seen.get("frames"),
        )
        check(
            seen.get("tail") is False and os.path.dirname(seen.get("dir", "")) == rounds.ROOT,
            "it worked on a copy outside the film, with no closing on its frames",
        )
        check(
            (seen.get("pins") or {}).get("vo", {}).get("tts") == "gemini",
            "the copy's voice settings are pinned to the film's own",
        )
        vs = rec.get("versions") or []
        two = next((x for x in vs if x.get("n") == 2), {})
        check(
            rec.get("version") == 2
            and [x["n"] for x in vs] == [1, 2]
            and two.get("round") == rid
            and two.get("summary") == "The label is bigger. The music stays as it was."
            and two.get("strip"),
            "the film is version 2 now, with what Claude said changed and its own filmstrip",
        )
        js = open(f.path("film.js"), encoding="utf-8").read()
        kept = f.path("versions", "v1")
        check(
            "// changed in round" in js
            and "// changed in round"
            not in open(os.path.join(kept, "film.js"), encoding="utf-8").read()
            and os.path.getsize(os.path.join(kept, "outputs", "film.mp4")) == old_mp4
            and os.path.isfile(f.path("outputs", "film.mp4"))
            and os.path.getmtime(f.path("outputs", "film.mp4")) > before["outputs/film.mp4"][1],
            "the new film is in the film's place, and version 1's files are kept beside it",
        )
        got = rounds._probe(f.path("outputs", "film.mp4"))
        check(
            got and abs(got[0] - 8.0) < 0.2 and round(got[3]) == 30,
            "it is the film as its plan has it: the closing kept, 30 frames a second (%s)" % (got,),
        )
        doc = mem.docs.get(rid) or {}
        check(
            doc.get("kind") == "round"
            and doc.get("film") == fid
            and doc.get("state") == "done"
            and doc.get("n") == 2
            and rid in mem.finals
            and doc.get("notes")
            == [
                {"id": "a", "state": "done", "reply": "The label is bigger now."},
                {
                    "id": "b",
                    "state": "cannot",
                    "reply": "The music is written to end with the film; a longer film has room.",
                },
            ]
            and doc.get("summary"),
            "the round's own document says done, with Claude's answer to each note (%s)"
            % doc.get("state"),
        )
        check(
            mem.docs[fid].get("version") == 2
            and mem.docs[fid].get("state") == "done"
            and len(mem.docs[fid].get("versions")) == 2,
            "and the film's document has the version, its state still done",
        )
        told = TOLD.get(rid) or []
        check(
            "Reading your notes" in told
            and any(x.startswith("Drawing version 2") for x in told)
            and doc.get("now") is None,
            "the round's document said what it was doing as it went, and nothing once done (%s)"
            % told,
        )
        check(
            abs((doc.get("claude_cost_usd") or 0) - 0.064) < 0.001
            and mem.docs[fid].get("cost_usd") == mem.docs[fid].get("cost_usd"),
            "what the round cost is on the round, not added to the film ($%s)"
            % doc.get("claude_cost_usd"),
        )
        check(
            not os.path.isdir(rounds.work_dir(rid))
            and not [n for n in os.listdir(rounds.MARKS) if n.endswith(".json")]
            and not os.path.exists(f.path("versions", rounds.SWAP))
            and not rounds.in_flight(),
            "nothing of the round is left behind",
        )
        st = await (await c.get("/api/films/%s?since=0" % fid, headers=auth)).json()
        check(st.get("status") == "done" and st.get("video_url"), "the film's page plays on")

        # ------------------------------------------------ rounds that make no version leave the film as it was
        for do, want in (("fail", "failed"), ("nothing", "unchanged")):
            PLAN["do"] = do
            was, rec0 = tree(f), f.record()
            r = await c.post(
                url, json={"key": "k-" + do, "from": 2, "notes": NOTES[:1]}, headers=me
            )
            rid2 = ((await r.json()).get("round") or {}).get("id")
            rec, states = await wait_round(f)
            check(
                (rec.get("round") or {}).get("state") == want and states == {"done"},
                "a round that %s ends %s (%s)"
                % (
                    "fails" if do == "fail" else "changes nothing",
                    want,
                    (rec.get("round") or {}).get("state"),
                ),
            )
            check(
                tree(f) == was
                and rec.get("version") == 2
                and rec.get("media") == rec0.get("media")
                and len(rec.get("versions")) == 2,
                "and the film is byte for byte what it was (differs: %s; version %s)"
                % (differ(tree(f), was), rec.get("version")),
            )
            check(
                (mem.docs.get(rid2) or {}).get("state") == want
                and rid2 in mem.finals
                and not os.path.isdir(rounds.work_dir(rid2)),
                "its document says %s (the site gives the time back), its copy gone" % want,
            )
        PLAN["do"] = "slow"
        was = tree(f)
        r = await c.post(url, json={"key": "k-slow", "from": 2, "notes": NOTES[:1]}, headers=me)
        rid3 = (await r.json())["round"]["id"]
        await wait_round(f, states=("running",), limit=120)
        await asyncio.sleep(1)
        r = await c.post(url + "/stop", headers=me)
        check(
            r.status == 200 and (await r.json())["round"]["state"] == "cancelled",
            "a round is stopped by its maker",
        )
        rec, _ = await wait_round(f)
        check(
            (rec.get("round") or {}).get("state") == "cancelled"
            and tree(f) == was
            and (mem.docs.get(rid3) or {}).get("state") == "cancelled"
            and not rounds.in_flight(),
            "stopped: the film as it was, the round's document cancelled (differs: %s; %s, %s)"
            % (
                differ(tree(f), was),
                (rec.get("round") or {}).get("state"),
                (mem.docs.get(rid3) or {}).get("state"),
            ),
        )
        r = await c.post(url + "/stop", headers=me)
        check(r.status == 409, "there is nothing to stop twice")
        PLAN["do"] = "change"

        # ------------------------------------------------ a note Claude never answered
        PLAN["do"] = "forgets"
        r = await c.post(url, json={"key": "k-f", "from": 2, "notes": NOTES}, headers=me)
        rid4 = (await r.json())["round"]["id"]
        rec, _ = await wait_round(f)
        doc = mem.docs.get(rid4) or {}
        check(
            (rec.get("round") or {}).get("state") == "done"
            and rec.get("version") == 3
            and (doc.get("notes") or [{}, {}])[1].get("state") == "cannot"
            and SEEN[-1].get("resume") == "fake-round-session",
            "a note left unanswered gets one short turn, and a verdict either way (version 3)",
        )
        PLAN["do"] = "change"

        # ------------------------------------------------ going back, and forward
        three = open(f.path("film.js"), encoding="utf-8").read()
        r = await c.post(url + "/1/current", headers=other)
        check(r.status == 403, "a stranger cannot pick a film's version")
        r = await c.post(url + "/9/current", headers=me)
        check(r.status == 404, "there is no version 9")
        r = await c.post(url + "/1/current", headers=me)
        rec = f.record()
        check(
            r.status == 200
            and rec.get("version") == 1
            and "// changed in round" not in open(f.path("film.js"), encoding="utf-8").read()
            and os.path.getsize(f.path("outputs", "film.mp4")) == old_mp4
            and open(f.path("versions", "v3", "film.js"), encoding="utf-8").read() == three
            and not os.path.isdir(f.path("versions", "v1"))
            and mem.docs[fid].get("version") == 1,
            "version 1 is the film again: its files back, version 3's kept, nothing rendered",
        )
        r = await c.post(url + "/3/current", headers=me)
        check(
            r.status == 200
            and f.record().get("version") == 3
            and open(f.path("film.js"), encoding="utf-8").read() == three
            and os.path.isdir(f.path("versions", "v1")),
            "and version 3 again",
        )

        # ------------------------------------------------ a swap a restart cut short is undone
        was = tree(f)
        src = os.path.join(HOME, "half")
        os.makedirs(os.path.join(src, "outputs"))
        with open(os.path.join(src, "film.js"), "w", encoding="utf-8") as fh:
            fh.write("// a version that never was\n")
        rounds._swap(f, src, 3, 4)  # the files moved, the record never written
        check(
            "never was" in open(f.path("film.js"), encoding="utf-8").read(),
            "(a swap, cut before the record)",
        )
        check(
            rounds.heal(f)
            and tree(f) == was
            and f.record().get("version") == 3
            and not os.path.exists(f.path("versions", rounds.SWAP))
            and "never was" in open(os.path.join(src, "film.js"), encoding="utf-8").read(),
            "heal puts the film's own files back, and what had come in back where it came from",
        )
        check(not rounds.heal(f), "and has nothing to do twice")

        # ------------------------------------------------ a round whose server went away
        gone = {
            "id": fid + ".r9",
            "n": 4,
            "state": "running",
            "key": "k-gone",
            "client": "u:maker",
            "auth": "api",
            "asked": "2026-10-05T10:00:00",
            "server": "gone-server",
            "tries": 1,
            "notes": rounds.clean_notes(f, NOTES[:1]),
        }
        f.update(round=gone, rounds=9)
        rounds._set_mark(fid)
        os.makedirs(rounds.work_dir(fid + ".r9"))  # what its server left
        found = [x.id for x in rounds.orphans()]
        check(found == [fid], "a round whose server is gone is found (%s)" % found)
        rounds.resume(f, server.SCHED)
        rec, _ = await wait_round(f)
        check(
            (rec.get("round") or {}).get("state") == "done"
            and rec.get("version") == 4
            and (rec.get("round") or {}).get("tries") == 2
            and not rounds.orphans(),
            "and made again from its notes (version 4)",
        )
        f.update(round=gone | {"tries": rounds.TRIES, "n": 5, "id": fid + ".r10"}, rounds=10)
        rounds._set_mark(fid)
        was = tree(f)
        rounds.resume(f, server.SCHED)
        await asyncio.sleep(0.5)
        rec = f.record()
        check(
            rec["round"]["state"] == "interrupted"
            and tree(f) == was
            and rec.get("version") == 4
            and (mem.docs.get(fid + ".r10") or {}).get("state") == "interrupted"
            and not rounds.in_flight(),
            "one that lost its server %d times is given up on, the film untouched (differs: %s; %s, %s)"
            % (
                rounds.TRIES,
                differ(tree(f), was),
                rec["round"]["state"],
                (mem.docs.get(fid + ".r10") or {}).get("state"),
            ),
        )

        # ------------------------------------------------ the day's rounds, and the versions kept
        v = await (await c.get(url, headers=me)).json()
        left = v["limits"]["rounds_left"]
        check(
            left == rounds.PER_DAY - rounds.rounds_today(f.record()),
            "its maker is told the rounds left today (%s)" % left,
        )
        day, rounds.PER_DAY = rounds.PER_DAY, rounds.rounds_today(f.record())
        try:
            r = await c.post(url, json={"key": "k-cap", "from": 4, "notes": NOTES[:1]}, headers=me)
        finally:
            rounds.PER_DAY = day
        check(
            r.status == 429 and (await r.json()).get("reason") == "rounds",
            "past the day's rounds, the next waits for tomorrow",
        )
        kept = sorted(n for n in os.listdir(f.path("versions")) if n.startswith("v"))
        check(
            kept == ["v1", "v2", "v3"],
            "the versions that are not the film are kept beside it (%s)" % kept,
        )
        pruned = rounds.prune(f, [{"n": i, "kept": True} for i in range(1, 7)], 6)
        check(
            [x["n"] for x in pruned if x["kept"]] == [3, 4, 5, 6]
            and not os.path.isdir(f.path("versions", "v1")),
            "only the last %d: an older one's files go, and it says so" % rounds.KEEP,
        )

        # ------------------------------------------------ files changed by hand: a version too
        def by_hand(text, base, summary="The label is nudged, by hand.", name="film.js"):
            """The film's film.js with a line added, where ops.sh put leaves a hand's files."""
            d = os.path.join(rounds.HAND, fid)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
            with open(f.path("film.js"), encoding="utf-8") as fh:
                src = fh.read()
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(src + text)
            return {"base": base, "summary": summary}

        at = rounds.where(f)
        n0, asked, days = at["version"], len(SEEN), rounds.rounds_today(f.record())
        check(
            at["digest"] == rounds.digest(f)
            and at["round"] is None
            and n0 == f.record()["version"],
            "where a film stands: its version and what that is made of",
        )
        r = await c.post(
            url, json={"key": "h0", "hand": by_hand("\n// h\n", at["digest"])}, headers=me
        )
        check(r.status == 403, "the site cannot send files by hand (%d)" % r.status)
        for i, (more, why) in enumerate(
            (
                ({"summary": " "}, "nothing said of what changed"),
                ({"name": "studio.json"}, "the film's own record"),
            )
        ):  # each folder made as it is sent: the next one's replaces it
            body = by_hand("\n// h\n", at["digest"], **more)
            r = await c.post(url, json={"key": "h0-%d" % i, "hand": body}, headers=auth)
            check(r.status == 400, "refused by hand: %s (%d)" % (why, r.status))
        shutil.rmtree(os.path.join(rounds.HAND, fid))
        r = await c.post(
            url, json={"key": "h0-2", "hand": {"base": at["digest"], "summary": "x"}}, headers=auth
        )
        check(r.status == 400, "refused by hand: no files sent (%d)" % r.status)
        before = tree(f)
        r = await c.post(
            url, json={"key": "h1", "hand": by_hand("\n// by hand 1\n", at["digest"])}, headers=auth
        )
        b = await r.json()
        hid = (b.get("round") or {}).get("id")
        check(
            r.status == 202 and b["round"]["n"] == max(v["n"] for v in f.record()["versions"]) + 1,
            "files changed by hand are accepted as the next version (%s %s)" % (r.status, b),
        )
        rec, states = await wait_round(f)
        rd, new = rec.get("round") or {}, rec.get("version")
        with open(f.path("film.js"), encoding="utf-8") as fh:
            now_js = fh.read()
        with open(f.path("versions", "v%d" % n0, "film.js"), encoding="utf-8") as fh:
            old_js = fh.read()
        entry = next((v for v in rec.get("versions") or [] if v.get("n") == new), {})
        check(
            rd.get("state") == "done" and states == {"done"} and new == b["round"]["n"],
            "it is made, the film done all the while (%s: %s)" % (rd.get("state"), rd.get("error")),
        )
        check(
            "// by hand 1" in now_js and "// by hand 1" not in old_js,
            "the film is the hand's files, and the version before is kept as it was",
        )
        check(
            entry.get("summary") == "The label is nudged, by hand." and entry.get("round") == hid,
            "the version says what the hand changed (%s)" % entry.get("summary"),
        )
        doc = mem.docs.get(hid) or {}
        check(
            doc.get("by") == "hand"
            and doc.get("state") == "done"
            and doc.get("client") != "u:maker",
            "its record is the studio's own round, not its maker's (%s, %s)"
            % (doc.get("by"), doc.get("client")),
        )
        check(
            len(SEEN) == asked and rounds.rounds_today(f.record()) == days,
            "Claude was not asked, and it is not one of its maker's rounds of the day",
        )
        check(not os.path.isdir(os.path.join(rounds.HAND, fid)), "the files sent are cleared away")

        # ---- files taken before the film changed: refused, by what the film is made of
        before = tree(f)
        r = await c.post(
            url, json={"key": "h2", "hand": by_hand("\n// stale\n", at["digest"])}, headers=auth
        )
        check(
            r.status == 409 and (await r.json()).get("reason") == "stale" and tree(f) == before,
            "files taken from the version before are refused, the film as it was (%d)" % r.status,
        )
        with open(f.path("film.js"), "a", encoding="utf-8") as fh:  # written into in place
            fh.write("\n// in place\n")
        r = await c.post(
            url,
            json={
                "key": "h3",
                "hand": by_hand("\n// stale 2\n", rounds.where(f)["digest"])
                | {"base": rounds.digest(f) + "x"},
            },
            headers=auth,
        )
        at2 = rounds.where(f)
        check(
            r.status == 409 and at2["version"] == new and at2["digest"] != at["digest"],
            "and so are files taken before a change made in place, which no version number shows",
        )

        # ---- the same files: no version
        d = os.path.join(rounds.HAND, fid)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        shutil.copyfile(f.path("film.js"), os.path.join(d, "film.js"))
        r = await c.post(
            url,
            json={"key": "h4", "hand": {"base": at2["digest"], "summary": "Nothing."}},
            headers=auth,
        )
        rec, _ = await wait_round(f)
        check(
            r.status == 202
            and (rec.get("round") or {}).get("state") == "unchanged"
            and rec.get("version") == new,
            "files that are the film's own make no version (%s)"
            % (rec.get("round") or {}).get("state"),
        )

        # ---- the film written into while a version is made: that version is not swapped in
        lay = rounds.overlay

        def lay_and_meddle(work, d):
            lay(work, d)
            with open(f.path("film.js"), "a", encoding="utf-8") as fh:
                fh.write("\n// meanwhile\n")

        rounds.overlay = lay_and_meddle
        try:
            r = await c.post(
                url,
                json={"key": "h5", "hand": by_hand("\n// by hand 2\n", at2["digest"])},
                headers=auth,
            )
            rec, states = await wait_round(f)
        finally:
            rounds.overlay = lay
        rd = rec.get("round") or {}
        with open(f.path("film.js"), encoding="utf-8") as fh:
            now_js = fh.read()
        check(
            r.status == 202
            and rd.get("state") == "failed"
            and "changed while this version was being made" in (rd.get("error") or "")
            and rec.get("version") == new
            and states == {"done"},
            "a film written into while its next version is made keeps its place (%s: %s)"
            % (rd.get("state"), rd.get("error")),
        )
        check(
            "// meanwhile" in now_js and "// by hand 2" not in now_js,
            "what was written into it is still there, not swapped out unseen",
        )
        check(
            os.path.isdir(os.path.join(rounds.HAND, fid)),
            "and the hand's files are kept, to be put on top of the film as it is now",
        )

    rounds._ours(HOME)  # the films here carry read-only files, which Windows will not remove
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("ALL OK" if not bad else "%d FAILED:\n  - %s" % (len(bad), "\n  - ".join(bad))))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
