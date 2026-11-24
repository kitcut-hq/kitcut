#!/usr/bin/env python
"""An edit of one scene or character (edits.py), with a stand-in for Claude:

    python studio/test_edits.py

Covers: what may be asked (the words, the marks, 1-4 variations, the model and effort, Fable at
medium only), the working copy (a copy of an episode, the library's cast over it, the marked
picture, Claude writing only its variations), a drawn edit end to end (the stand-in writes two
variations, `look` draws them for real, it names them), the edit's record and its document for
the site (done, how many delivered), choosing one (the member's next version, the episode after
it gets it; refused when the member moved, unless forced), an edit that names nothing
(unchanged), one that fails, one stopped, one at a time per workspace, a painted edit (the
stand-in leaves paintings), refining from a variation, and throwing an edit away. Everything in a
throwaway STUDIO_HOME; the drawings are real (a few seconds each).
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-edits-test-")
os.environ["STUDIO_HOME"] = HOME
os.environ["STUDIO_SHARE"] = "0"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import assets  # noqa: E402
import edits  # noqa: E402
import film as films  # noqa: E402
import library  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402
from guard import guard  # noqa: E402
from PIL import Image  # noqa: E402

CL, P1 = "u:edits", "p-editsabcde"
PROJECT = {"id": P1, "name": "Edits", "brief": ""}
FAILS = []
SEEN = []
PLAN = {"do": "two"}
USAGE = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 100000}


def check(ok, what, got=None):
    print("%s %s" % ("ok  " if ok else "FAIL", what) + ("" if ok else "\n     %r" % (got,)))
    if not ok:
        FAILS.append(what)


def room(colour, extra=""):
    return (
        "SK.cast.room = {\n  about: 'The room, %s walls',\n  kind: 'place',\n"
        "  camera: [960, 540, 1],\n  draw(x, y) {\n"
        "    SK.wash(SK.S.ellC(960, 540, 700, 400), '%s');\n"
        "    SK.ink(SK.S.ellC(960, 540, 700, 400), { w: 6 });%s\n  },\n};\n"
        % (colour, colour, extra)
    )


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
    r = tools.round
    SEEN.append(
        {
            "prompt": prompt or "",
            "effort": effort,
            "model": film.claude_model,
            "marks": os.path.isfile(film.path("variations", "marks.png")),
            "cast": sorted(os.listdir(film.path("cast")))
            if os.path.isdir(film.path("cast"))
            else [],
            "write_var": guard("Write", {"file_path": film.path("variations", "a.js")}, film)[0],
            "write_cast": guard("Write", {"file_path": film.path("cast", "room.js")}, film)[0],
            "write_film": guard("Write", {"file_path": film.path("film.js")}, film)[0],
            "write_paint": guard("Write", {"file_path": film.path("paint.json")}, film)[0],
            "tools": sorted(t for t in ("look", "variation", "summary") if hasattr(r, t)),
        }
    )
    meter.add("msg_edit_%d" % len(SEEN), USAGE)
    emit({"type": "cost", "usd": round(meter.usd(), 4)})
    do = PLAN["do"]
    if do == "fail":
        raise RuntimeError("a stub failure")
    if do == "slow":
        await asyncio.sleep(120)
        return
    if do == "nothing":
        await r.say_summary("The window belongs to the episode, not to the room.")
        return
    if film.edit_painted:
        os.makedirs(film.path("images"), exist_ok=True)
        for x, col in (("a", (200, 40, 40)), ("b", (40, 200, 40))):
            Image.new("RGB", (1920, 1080), col).save(film.path("images", "v_%s.jpg" % x), "JPEG")
        await r.variation("a", "The walls are red.")
        return
    with open(film.path("variations", "a.js"), "w", encoding="utf-8") as f:
        f.write(room("#c0392b"))
    with open(film.path("variations", "b.js"), "w", encoding="utf-8") as f:
        f.write(room("#2e86c1", "\n    SK.wash(SK.S.ellC(1100, 400, 120, 90), '#fff');"))
    with open(film.path("variations", "c.js"), "w", encoding="utf-8") as f:
        f.write("SK.cast.other = { about: 'x', draw() {} };\n")
    try:
        await r.variation("a", "too early")
        SEEN[-1]["early"] = "named unseen"
    except edits.toolbox.ToolError as e:
        SEEN[-1]["early"] = str(e)
    SEEN[-1]["look"] = await r.look()
    await r.variation("a", "The walls are red.")
    if "b" in r.letters():
        await r.variation("b", "The walls are blue, with a window.")
    try:
        await r.variation("c", "Another thing.")
    except edits.toolbox.ToolError as e:
        SEEN[-1]["wrong"] = str(e)
    await r.say_summary("Two rooms: one red, one blue with a window.")


async def done(job):
    try:
        await job["task"]
    except asyncio.CancelledError:
        pass


def episode(look="drawn"):
    f = films.Film.create("an episode", 5, look, client=CL, project=PROJECT)
    library.seed(f)
    ex = os.path.join(films.KIT, "config", "sketch", "example")
    for n in films.MADE:
        if not os.path.exists(f.path(n)):
            shutil.copy(os.path.join(ex, n), f.dir)
    f.update(state="done", ok=True)
    return f


async def main():
    agent.STORE = mem = store.MemoryStore()
    agent.run_claude = fake_claude
    lib = (library.clients.canon(CL), P1)

    # ---- what may be asked
    for args, words in (
        (("", [], 1, {}), "Say what"),
        (("x" * 1001, [], 1, {}), "At most 1000"),
        (("ok", [{"x": 2, "y": 0.5, "text": "a"}], 1, {}), "0 to 1"),
        (("ok", [{"x": 0.5, "y": 0.5, "text": "a"}] * 9, 1, {}), "At most 8 marks"),
        (("ok", [], 5, {}), "1 to 4"),
        (("ok", [], 1, {"model": "gpt"}), "model must be"),
        (("ok", [], 1, {"model": "claude-fable-5-2", "effort": "high"}), "With Fable"),
    ):
        try:
            edits.clean(*args)
            check(False, "refused: %s" % words)
        except edits.EditError as e:
            check(words in e.text, "refused: %s" % words, e.text)
    a = edits.clean(
        " bigger  window ",
        [{"x": 0.5, "y": 0.25, "w": 0.2, "h": 0.1, "text": " here "}],
        2,
        {"model": "claude-fable-5-2"},
    )
    check(
        a
        == (
            "bigger window",
            [{"x": 0.5, "y": 0.25, "w": 0.2, "h": 0.1, "text": "here"}],
            2,
            {"model": "claude-fable-5-2", "effort": "medium"},
        ),
        "an asking, cleaned; Fable is at medium effort",
        a,
    )
    check(
        edits.clean("", [{"x": 0.1, "y": 0.1, "text": "redder"}], 1, {})[0] == "",
        "a mark's note alone is an asking",
    )

    # ---- a project with a drawn place, and no episode yet
    first = episode()
    small, large = Image.new("RGB", (480, 270), (9, 9, 9)), Image.new("RGB", (1280, 720), (9, 9, 9))
    it = assets.member_of("room", room("#27ae60"))
    assets.put_drawn(lib, [it], {"room": None}, {"room": small}, {"room": large})
    idx = library.load(lib)
    idx["films"] = []
    library._save(lib, idx)
    try:
        edits.start(CL, P1, "room", server.SCHED, "red walls")
        check(False, "no episode yet: refused")
    except edits.EditError as e:
        check(
            e.status == 409 and e.reason == "episode", "no episode yet: refused, saying why", e.text
        )
    idx = library.load(lib)
    idx["films"] = [first.id]
    library._save(lib, idx)

    # ---- a drawn edit, end to end
    marks = [
        {"x": 0.5, "y": 0.3, "w": 0.3, "h": 0.2, "text": "a window here"},
        {"x": 0.1, "y": 0.9, "text": ""},
    ]
    job = edits.start(
        CL,
        P1,
        "room",
        server.SCHED,
        "Make the walls another colour.",
        marks,
        3,
        key="k1",
        claude={"model": "claude-fable-5-2"},
    )
    check(
        edits.start(CL, P1, "room", server.SCHED, "x", key="k1") is job,
        "the same key again: the same edit",
    )
    try:
        edits.start(CL, P1, "room", server.SCHED, "another")
        check(False, "one edit at a time for a workspace")
    except edits.EditError as e:
        check(e.status == 409 and e.reason == "edit", "one edit at a time for a workspace", e.text)
    check(edits.pending(lib, "room") == 1, "being made: one on the member's card")
    await done(job)
    s = SEEN[-1]
    e = edits.get(CL, P1, "room", 1)
    check(
        e["state"] == "done" and [v["letter"] for v in e["variations"]] == ["a", "b"],
        "done, with the two variations Claude named",
        (
            e["state"],
            e["error"],
            SEEN[-1:] and {k: v for k, v in SEEN[-1].items() if k != "prompt"},
        ),
    )
    if e["state"] != "done":
        sys.exit(1)
    check(
        e["summary"].startswith("Two rooms")
        and e["variations"][1]["what"].startswith("The walls are blue"),
        "what each changed, and the summary",
    )
    check(
        s["write_var"] and not s["write_cast"] and not s["write_film"] and not s["write_paint"],
        "Claude may write its variations and nothing else",
        s,
    )
    check(
        s["marks"]
        and "variations/marks.png" in s["prompt"]
        and "1. (top middle of the picture, a boxed area) a window here" in s["prompt"],
        "the marked picture and the marks, told",
        s["prompt"][-900:],
    )
    check(
        "Make 3 variations" in s["prompt"]
        and "variations/c.js" in s["prompt"]
        and "SK.cast.room" in s["prompt"],
        "the asking names the member and the files",
    )
    check(
        s["model"] == "claude-fable-5-2" and s["effort"] == "medium",
        "made with the model asked for, Fable at medium",
        (s["model"], s["effort"]),
    )
    check("room.js" in s["cast"], "the library's cast is in the working copy", s["cast"])
    check(
        "changed since you looked" in s.get("early", "") or "not written" in s.get("early", ""),
        "a variation is not named before it is looked at",
        s.get("early"),
    )
    check(
        "a: drawn" in s["look"]
        and "b: drawn" in s["look"]
        and "c: variations/c.js must register SK.cast.room" in s["look"],
        "look draws each, and says what is wrong with one",
        s["look"],
    )
    check(
        "c" not in [v["letter"] for v in e["variations"]] and "must register" in s.get("wrong", ""),
        "a file that is not the member is no variation",
    )
    d = edits._dir(lib, "room", 1)
    check(
        all(
            os.path.exists(os.path.join(d, n))
            for n in ("a.js", "a.png", "a.thumb.png", "b.js", "b.png", "marks.png")
        ),
        "the variations, their pictures and the marked picture are kept",
        os.listdir(d),
    )
    pa, pb = (
        Image.open(os.path.join(d, "a.png")).convert("RGB"),
        Image.open(os.path.join(d, "b.png")).convert("RGB"),
    )
    ca, cb = (
        pa.getpixel((pa.width // 4, pa.height // 2)),
        pb.getpixel((pb.width // 4, pb.height // 2)),
    )
    check(
        ca[0] > ca[2] and cb[2] > cb[0],
        "each picture is its own variation, drawn (red, blue)",
        (ca, cb),
    )
    check(
        edits.picture(CL, P1, "room", 1, "a")
        and edits.picture(CL, P1, "room", 1, "marks")
        and not edits.picture(CL, P1, "room", 1, "d"),
        "pictures are served by letter",
    )
    doc = mem.docs.get(job["id"]) or {}
    check(
        doc.get("kind") == "edit"
        and doc.get("state") == "done"
        and doc.get("delivered") == 2
        and doc.get("asked_for") == 3
        and doc.get("project_id") == P1,
        "the site's document: done, 2 of 3 delivered",
        {k: doc.get(k) for k in ("kind", "state", "delivered", "asked_for")},
    )
    check((doc.get("claude_cost_usd") or 0) > 0 and doc.get("finished_at"), "with what it cost")
    check(not os.path.exists(edits_work(job["id"])), "the working copy is gone")
    check(edits.pending(lib, "room") == 1, "variations to choose from: still one on the card")

    # ---- choosing
    got = edits.use(CL, P1, "room", 1, "b")
    m = library.load(lib)["cast"]["room"]
    md = os.path.join(library.dir_of(lib), "cast", "room")
    check(
        got["version"] == 2
        and "#2e86c1" in open(os.path.join(md, "v2.js"), encoding="utf-8").read()
        and m.get("edited") == job["id"]
        and m["kind"] == "place",
        "the chosen variation is the member's next version",
        m,
    )
    check(
        os.path.exists(os.path.join(md, "v2.png")) and edits.pending(lib, "room") == 0,
        "with its picture; nothing left to choose on the card",
    )
    nxt = films.Film.create("the next episode", 5, "drawn", client=CL, project=PROJECT)
    library.seed(nxt)
    check(
        "#2e86c1" in open(nxt.path("cast", "room.js"), encoding="utf-8").read(),
        "the next episode is seeded with it",
    )
    try:
        edits.use(CL, P1, "room", 1, "a")
        check(False, "the member moved since the edit: asked first")
    except edits.EditError as e:
        check(
            e.status == 409 and e.reason == "moved",
            "the member moved since the edit: asked first",
            e.text,
        )
    check(
        edits.use(CL, P1, "room", 1, "a", force=True)["version"] == 3,
        "and written when the person says so",
    )

    # ---- refining from a variation, nothing made, a failure, a stop
    job = edits.start(
        CL, P1, "room", server.SCHED, "Now a door too.", base={"edit": 1, "letter": "b"}
    )
    await done(job)
    e = edits.get(CL, P1, "room", 2)
    check(
        e["base"]["edit"] == 1 and e["base"]["letter"] == "b" and e["state"] == "done",
        "an edit may start from a variation",
        (e["base"], e["state"], e["error"]),
    )
    PLAN["do"] = "nothing"
    job = edits.start(CL, P1, "room", server.SCHED, "Move the window in episode 3.")
    await done(job)
    e, doc = edits.get(CL, P1, "room", 3), mem.docs.get(job["id"])
    check(
        e["state"] == "unchanged"
        and "belongs to the episode" in e["error"]
        and doc["state"] == "unchanged"
        and doc["delivered"] == 0,
        "nothing named: unchanged, with Claude's reason",
        e,
    )
    PLAN["do"] = "fail"
    job = edits.start(CL, P1, "room", server.SCHED, "x")
    await done(job)
    check(
        edits.get(CL, P1, "room", 4)["state"] == "failed"
        and mem.docs[job["id"]]["state"] == "failed",
        "a failure ends the edit as failed",
    )
    PLAN["do"] = "slow"
    job = edits.start(CL, P1, "room", server.SCHED, "x")
    await asyncio.sleep(1.5)
    check(edits.stop(CL, P1, "room", 5)["state"] == "cancelled", "Stop")
    await done(job)
    check(
        edits.get(CL, P1, "room", 5)["state"] == "cancelled"
        and mem.docs[job["id"]]["state"] == "cancelled"
        and not edits.in_flight(),
        "a stopped edit is cancelled, for the site too",
    )
    try:
        edits.dismiss(CL, P1, "room", 9)
        check(False, "no such edit")
    except edits.EditError as e:
        check(e.status == 404, "no such edit")
    check(
        edits.dismiss(CL, P1, "room", 4)
        and [x["k"] for x in edits.listing(CL, P1, "room")] == [5, 3, 2, 1],
        "an edit thrown away is gone from the list",
        [x["k"] for x in edits.listing(CL, P1, "room")],
    )

    # ---- a painted member
    PLAN["do"] = "two"
    pic = os.path.join(HOME, "kitchen.png")
    Image.new("RGB", (1280, 720), (240, 220, 90)).save(pic, "PNG")
    library.add_character(CL, P1, "kitchen", "The kitchen, yellow", pic, "place")
    pe = episode("painted")
    idx = library.load(lib)
    idx["films"] = [pe.id, first.id]
    library._save(lib, idx)
    job = edits.start(
        CL, P1, "kitchen", server.SCHED, "Red walls.", [{"x": 0.5, "y": 0.5, "text": "here"}], 2
    )
    await done(job)
    s, e = SEEN[-1], edits.get(CL, P1, "kitchen", 1)
    check(
        e["state"] == "done" and e["painted"] and [v["letter"] for v in e["variations"]] == ["a"],
        "a painted edit keeps the paintings Claude named",
        e,
    )
    check(
        s["write_paint"] and not s["write_var"] and not s["write_film"],
        "there Claude writes paint.json and nothing else",
        s,
    )
    check(
        '"ref": "cast_kitchen"' in s["prompt"]
        and "inputs/cast_kitchen.png" in s["prompt"]
        and s["marks"],
        "the asking names the picture and its ref",
        s["prompt"][:600],
    )
    got = edits.use(CL, P1, "kitchen", 1, "a")
    m = library.load(lib)["cast"]["kitchen"]
    check(
        got["version"] == 2
        and m["kind"] == "place"
        and m["painted"]
        and m.get("edited") == job["id"]
        and m["ext"] == "jpg",
        "choosing it makes the place's next version, still a place",
        m,
    )

    # ---- an episode brought up to the project's members ("Update episodes": rounds.py refresh)
    import rounds

    names, notes = rounds.refresh_notes(first, ["room", "kitchen", "room"])
    text = notes[0]["text"]
    check(
        names == ["room", "kitchen"]
        and notes[0]["kind"] == "film"
        and notes[0]["id"] == rounds.REFRESH_NOTE
        and "@room, @kitchen" in text
        and "SK.cast.<name>" in text
        and "`paint` with retake" in text
        and "change nothing else" in text,
        "a refresh round has one note of the studio's: use the new members, change nothing else",
        text,
    )
    one = rounds.refresh_notes(first, ["room"])[1][0]["text"]
    check("use it as it is now" in one and "retake" not in one, "worded for one drawn member", one)
    for bad, status in ((["nobody"], 404), ([], 400), ("room", 400)):
        try:
            rounds.refresh_notes(first, bad)
            check(False, "refresh refused: %r" % (bad,))
        except rounds.RoundError as e:
            check(e.status == status, "refresh refused: %r" % (bad,), e.text)
    loose = films.Film.create("not an episode", 5, "drawn", client=CL)
    try:
        rounds.refresh_notes(loose, ["room"])
        check(False, "a film outside projects has nothing to be brought up to")
    except rounds.RoundError as e:
        check(e.reason == "project", "a film outside projects has nothing to be brought up to")
    check(
        not os.path.exists(first.path("cast", "room.js")),
        "the episode was made before the room was",
    )
    work = rounds.copy_of(first, "t-refresh", notes)
    got = rounds.lay_over(work, names)
    man = json.load(open(work.manifest, encoding="utf-8"))
    check(
        got == {"drawn": ["room"], "painted": ["kitchen"]}
        and "#c0392b" in open(work.path("cast", "room.js"), encoding="utf-8").read()
        and os.path.exists(work.path("inputs", "cast_kitchen.jpg"))
        and man["images"].get("cast_kitchen") == "inputs/cast_kitchen.jpg",
        "the project's newest versions are laid over the round's copy; the film itself is untouched",
        (got, man.get("images")),
    )
    check(
        not os.path.exists(first.path("cast", "room.js")),
        "the episode keeps its own until the version is made",
    )
    shutil.rmtree(work.dir, ignore_errors=True)

    # ---- edits left in the making by a server that is gone
    e = edits._read(lib, "room", 5)
    e.update(state="running", server="gone-server")
    edits._write(lib, "room", e)
    swept = edits.sweep()
    check(
        [x[0] for x in swept] == [e["id"]]
        and edits.get(CL, P1, "room", 5)["state"] == "interrupted",
        "an edit a gone server left running is ended as interrupted",
        swept,
    )

    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


def edits_work(eid):
    import rounds

    return rounds.work_dir("edit-" + eid)


if __name__ == "__main__":
    asyncio.run(main())
