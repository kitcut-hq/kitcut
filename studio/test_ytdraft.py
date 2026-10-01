#!/usr/bin/env python
"""A film's YouTube title and description (ytdraft.py), with Claude stood in for: no model, no
network, no cost, seconds.

    python studio/test_ytdraft.py

Covers: what the film is read from (the narration with its times, the maker's note, the pages
read and fetched, what Claude said) and that the brief goes in marked private; the draft held to
YouTube and to its inputs -- a link nobody gave removed, chapters past the end or not from 0:00
removed with their heading, good ones kept, the title cut at a word, the tags to 500; the brief
pasted back refused, once asked again, twice given up; a draft kept and reused until the film
changes; what it cost on the record; the four thumbnails with it -- held to the rules, asked once
more when they break them, then put right from the film, and made after the draft (the stills and
the browser are stood in for here: studio/test_thumbs.py runs them for real); and the API: the
owner only, a finished film only, 202 while writing, then the draft, then its thumbnails.
Everything happens in a throwaway STUDIO_HOME.
"""

import os
import sys
import json
import shutil
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-ytdraft-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402
import thumbs  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"
PROMPT = (
    "make a video telling my customers that we moved every account to the new faster engine "
    "and that it is the best one on the market"
)
LINES = [
    (0.5, 4.0, "Every account now runs on the new engine."),
    (4.4, 9.0, "Forms come back sooner, and the answers land in the right fields."),
    (9.4, 13.0, "Nothing to change. Just upload your next form."),
]
RECENT = [
    {
        "title": "How to fill out PDF forms in seconds with AI | Acme",
        "description": "Upload a form. Try Acme: https://acme.example/\nMore: https://acme.example/docs",
        "tags": ["acme", "pdf"],
    }
]
CHANNEL = {"id": "UCabcdefghijklmnopqrstuv", "title": "Acme", "handle": "@acme"}


def fixture_film(client="u:alice", length=15):
    f = Film.create(PROMPT, length, client=client)
    os.makedirs(f.path("audio", "vo"), exist_ok=True)
    os.makedirs(f.path("web"), exist_ok=True)
    with open(f.path("vo.json"), "w", encoding="utf-8") as fh:
        json.dump({"language": "en", "lines": [{"text": t} for _, _, t in LINES]}, fh)
    tl = [{"i": i, "start": s, "end": e, "text": t} for i, (s, e, t) in enumerate(LINES)]
    with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"duration": length, "lines": tl}, fh)
    with open(f.path("film.js"), "w", encoding="utf-8") as fh:
        fh.write(
            "// For: Acme's customers, who fill forms at work; a calm product update.\n"
            "/* Acme moves to the new engine. Clean line art in Acme's own blue.\n"
            "   Facts: the engine's maker says it is faster. */\n"
            "(function () {})();\n"
        )
    with open(f.path("web", "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "web_maker": {"url": "https://maker.example/engine", "kind": "page"},
                "web_logo": {"url": "https://acme.example/logo.png", "kind": "png"},
            },
            fh,
        )
    with open(f.path("web", "maker.json"), "w", encoding="utf-8") as fh:
        json.dump({"title": "The new engine | Maker"}, fh)
    with open(f.path("events.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "tool", "text": "reading https://acme.example/news"}) + "\n")
        fh.write(json.dumps({"type": "tool", "text": "searching the web: acme engine"}) + "\n")
    f.update(claude_said="I made a 15-second update. The speed claim is from your prompt.")
    return f


THUMBS = [
    {"at": 3.5, "layout": "headline", "words": "*Faster* forms", "place": "top"},
    {"at": 8.6, "layout": "card", "words": "Nothing to change", "place": "left"},
    {"at": 12.6, "layout": "panel", "words": "Right fields, first time", "place": "right"},
    {"at": 6.0, "layout": "headline", "words": "Forms come back *sooner*", "place": "left"},
]


def good(**over):
    d = {
        "title": "Acme now runs on the new engine | Acme",
        "description": "Every account now runs on the new engine.\n\nTry Acme: https://acme.example",
        "tags": ["acme", "new engine"],
        "thumbnails": THUMBS,
    }
    return d | over


async def main():
    agent.STORE = mem = store.MemoryStore()
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % (detail,)))
        if not ok:
            bad.append(what)

    # ---------------------------------------------------------------- what the film is
    f = fixture_film()
    mat = ytdraft.material(f)
    check([t for _, _, t in mat["narration"]] == [t for _, _, t in LINES], "the narration", mat)
    check(mat["narration"][1][0] == 4.4, "with its times")
    check(mat["audience"].startswith("Acme's customers"), "who it is for", mat["audience"])
    check("Clean line art" in mat["header"] and "(function" not in mat["header"], "the note")
    urls = {(s["url"], s["how"]) for s in mat["sources"]}
    check(
        urls
        == {("https://maker.example/engine", "read"), ("https://acme.example/news", "fetched")},
        "pages read and fetched, not pictures or searches",
        urls,
    )
    check(mat["sources"][0]["title"] == "The new engine | Maker", "a page read has its title")
    text = ytdraft.ask_text(mat, CHANNEL, ytdraft.sample(RECENT))
    check("brief it was made from (private)" in text and PROMPT in text, "the brief, private")
    check("4.4-  9.0 s  Forms come back sooner" in text, "the narration in the ask", text[:200])
    check("## How to fill out PDF forms" in text, "the channel's uploads in the ask")
    none = ytdraft.ask_text(mat, {"id": "x", "title": "New"}, [])
    check("No uploads to learn from" in none, "a channel with no uploads says so")
    check('"thumbnails"' not in text, "the words are asked for alone")
    picks = ytdraft.ask_text(mat, CHANNEL, ytdraft.sample(RECENT), "thumbs", "Acme | New engine")
    check('"thumbnails"' in picks and "main message" in picks, "the thumbnails are asked apart")
    check("## How to fill out PDF forms" not in picks, "without the channel's uploads")
    check('its title, "Acme | New engine"' in picks, "and with the title, once it is known")
    check(mat["sheet"] is None and mat["moments"], "no sheet made here, but the moments", mat)
    moments = ytdraft.ask_text(dict(mat, sheet=b"jpeg", moments_sheet=True), CHANNEL, [])
    check("the film's moments, in order" in moments, "the sheet is the film's moments")
    k1 = ytdraft.key_of(mat, CHANNEL, [], "m", "e")
    k2 = ytdraft.key_of(dict(mat, sheet=b"other", moments_sheet=True), CHANNEL, [], "m", "e")
    check(k1 == k2, "the key is the film's, not the sheet's bytes")

    # ---------------------------------------------------------------- the thumbnails' rules
    title = good()["title"]
    cs, _, probs = ytdraft.check_thumbs(good(), mat, title)
    check(len(cs) == 4 and not probs, "four good thumbnails pass", probs)
    check(
        cs[0]["place"] == "top" and [c["layout"] for c in cs][::3] == ["headline", "headline"],
        "with their places; the first and the fourth headlines",
        cs,
    )
    msg = [dict(THUMBS[0], words="Acme runs new engine"), *THUMBS[1:]]
    _, _, probs = ytdraft.check_thumbs(good(thumbnails=msg), mat, title)
    check(not probs, "the title's message on the picture is allowed", probs)
    bad_thumbs = [dict(THUMBS[0], words="one two three four five"), *THUMBS[1:]]
    cs, notes, probs = ytdraft.check_thumbs(good(thumbnails=bad_thumbs), mat, title)
    check(
        any("too long" in p["text"] and p["n"] == 1 for p in probs),
        "five words are too many",
        probs,
    )
    old = [*THUMBS[:3], dict(THUMBS[3], layout="still", words="")]
    cs, notes, probs = ytdraft.check_thumbs(good(thumbnails=old), mat, title)
    check(
        cs[3]["layout"] == "headline"
        and any(p["n"] == 4 and "needs words" in p["text"] for p in probs),
        "an old draft's still takes the free layout and is asked for words",
        (cs, probs),
    )
    twice = [dict(t, layout="card") for t in THUMBS]
    cs, notes, _ = ytdraft.check_thumbs(good(thumbnails=twice), mat, title)
    check(
        sorted(c["layout"] for c in cs) == sorted(["headline", "card", "panel", "headline"]),
        "the layouts as listed, the repeats given the missing ones",
        [c["layout"] for c in cs],
    )
    fixed, note = ytdraft.repair(cs[:1], [{"n": 1, "text": "x"}], mat)
    check(
        len(fixed) == 4 and fixed[0]["layout"] == "still" and "put right" in note,
        "repaired: the bad one the picture alone, the missing made up from the film",
        fixed,
    )

    # ---------------------------------------------------------------- held to its inputs
    recent = ytdraft.sample(RECENT)
    out, notes = ytdraft.check(
        good(
            description="Try: https://acme.example/\nSee https://invented.example/x now\n"
            "Buy: https://invented.example/buy"
        ),
        mat,
        recent,
    )
    check("invented.example" not in out["description"], "a link nobody gave is removed", out)
    check("https://acme.example/" in out["description"], "a link the channel gives is kept")
    check("Buy:" not in out["description"], "and a line left with only its label goes too", out)
    check(len(notes) == 2, "each removal is noted", notes)
    out, _ = ytdraft.check(good(description="Read https://maker.example/engine."), mat, recent)
    check("https://maker.example/engine" in out["description"], "a page it read may be linked")

    chapters = "Intro\n\nCHAPTERS\n0:00 Start\n0:05 Faster\n%s Nothing to change\n\nThanks"
    out, notes = ytdraft.check(good(description=chapters % "0:20"), mat, recent)
    check(
        "0:00" not in out["description"]
        and "CHAPTERS" not in out["description"]
        and "Thanks" in out["description"],
        "chapters past the end are removed, with their heading",
        out["description"],
    )
    check(any("past the film's end" in n for n in notes), "and it says why", notes)
    out, _ = ytdraft.check(good(description=chapters % "0:10"), mat, recent)
    check("0:10 Nothing to change" in out["description"], "chapters inside the film stay", out)
    out, notes = ytdraft.check(good(description="0:02 A\n0:05 B\n0:09 C"), mat, recent)
    check("0:02" not in out["description"], "chapters must start at 0:00", notes)

    long = "An update for everyone who fills forms at work: " + "every account moves " * 6
    out, _ = ytdraft.check(good(title=long), mat, recent)
    check(
        len(out["title"]) <= 100
        and out["title"].endswith("…")
        and not out["title"][:-1].endswith(" "),
        "a long title is cut at a word",
        out["title"],
    )
    out, _ = ytdraft.check(good(title="A <b>bold</b>\nmove"), mat, recent)
    check(out["title"] == "A bbold/b move", "one line, no angle brackets", out["title"])
    tags = ["#acme", "Acme", "pdf forms", *["tag number %d" % i for i in range(60)]]
    out, _ = ytdraft.check(good(tags=tags), mat, recent)
    cost = sum(len(t) + (2 if " " in t else 0) for t in out["tags"]) + len(out["tags"]) - 1
    check(
        out["tags"][:2] == ["acme", "pdf forms"] and cost <= 500,
        "tags: 500 and no repeats",
        (out["tags"][:3], cost),
    )

    # ---------------------------------------------------------------- the brief is private
    check(ytdraft.leak(good(), mat) is None, "a draft from the film is not a leak")
    check(ytdraft.leak(good(title=PROMPT), mat) is not None, "the prompt as the title is")
    pasted = good(
        description="We moved every account to the new faster engine and that it is "
        "the best one on the market."
    )
    check(ytdraft.leak(pasted, mat) is not None, "the prompt in the description is")
    said = good(description="Nothing to change. Just upload your next form.")
    mat2 = dict(mat, prompt="tell them: nothing to change, just upload your next form, easy")
    check(ytdraft.leak(said, mat2) is None, "words the narration says too are the film's own")
    # a heading over a sentence is two thoughts, not a paste, though the brief has the same pair
    # (ewwd6b: every draft refused for "making a film say the idea the")
    headed = good(
        description="Chapters\n0:55 Making a film\nSay the idea, the length and the look."
    )
    mat3 = dict(
        mat,
        prompt="3. Making a film. Say the idea, the length and the look, one beat each.",
        narration=[
            *mat["narration"],
            (55.0, 58.0, "To make a film, say the idea, the length and the look."),
        ],
    )
    check(ytdraft.leak(headed, mat3) is None, "a run across a sentence's end is not a paste")
    check(
        ytdraft.leak(
            good(description="Say the idea, the length and the look, one beat each."), mat3
        )
        is not None,
        "a run of the brief's inside one sentence still is",
    )

    # ---------------------------------------------------------------- writing, kept, costed
    answers, calls, picked, tcalls, order = [], [], [], [], []

    async def fake_call(
        mat, channel, recent, auth, film, model, effort, note=None, part="words", title=None
    ):
        if part == "thumbs":  # the picks: a moment slower than the words, as they are
            tcalls.append(note)
            await asyncio.sleep(0.05)
            order.append("picks")
            return (picked.pop(0) if picked else {"thumbnails": THUMBS}), 0.05
        calls.append(note)
        order.append("words")
        return answers.pop(0), 0.05

    sheets, made = [], []

    async def fake_sheet(film):
        sheets.append(film.id)
        return b"moments-jpeg"

    async def fake_make(film, channel, draft):
        made.append((film.id, channel))
        await asyncio.sleep(0.1)
        opts = [
            {
                "n": i,
                "path": "youtube/%s/thumb-%d.jpg" % (channel, i),
                "layout": t["layout"],
                "words": t["words"],
                "at": t["at"],
                "t": t["at"],
            }
            for i, t in enumerate(draft["thumbnails"], 1)
        ]
        return {"key": draft.get("key"), "channel": channel, "options": opts}

    real_call, ytdraft._call = ytdraft._call, fake_call
    real_sheet, real_make = thumbs.sheet, thumbs.make
    thumbs.sheet, thumbs.make = fake_sheet, fake_make
    try:
        answers[:] = [good(title=PROMPT), good()]
        before = f.record().get("cost_usd") or 0
        d = await ytdraft.write(f, CHANNEL, recent, "api", on_words=lambda w: order.append("shown"))
        check(d["title"] == good()["title"] and len(calls) == 2, "a pasted brief is asked again")
        check(calls[1] and "repeated the brief" in calls[1], "and told why", calls)
        check(len(tcalls) == 1, "the thumbnails asked once, at the same time", tcalls)
        check(
            order.index("shown") < order.index("picks"),
            "the words are out before the thumbnails are picked",
            order,
        )
        rec = f.record()
        check(
            rec["youtube_drafts"] == 1
            and abs(rec["youtube_draft_cost_usd"] - 0.15) < 1e-6
            and abs(rec["cost_usd"] - before - 0.15) < 1e-6,
            "all three calls are paid for on the record",
            rec,
        )
        check(
            mem.docs.get(f.id, {}).get("youtube_drafts") == 1,
            "and in the run log",
            mem.docs.get(f.id),
        )
        check(sheets == [f.id], "the moments sheet is made for the call", sheets)
        check(
            len(d["thumbnails"]) == 4 and d["thumbnails"][0]["words"] == "*Faster* forms",
            "the draft keeps its thumbnails",
            d["thumbnails"],
        )
        n = len(calls)
        again = await ytdraft.write(f, CHANNEL, recent, "api")
        check(len(calls) == n and again["key"] == d["key"], "asked again: the kept draft")
        with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as fh:
            json.dump({"lines": [{"i": 0, "start": 0.5, "end": 3, "text": "A new line."}]}, fh)
        answers[:] = [good(title="Rewritten")]
        d2 = await ytdraft.write(f, CHANNEL, recent, "api")
        check(d2["title"] == "Rewritten", "a changed film is written again")
        answers[:] = [good(title="Once more")]
        picked[:] = [{"thumbnails": bad_thumbs}, {"thumbnails": THUMBS}]
        n = len(tcalls)
        d3 = await ytdraft.write(f, dict(CHANNEL, id="UCthird"), recent, "api")
        check(
            len(tcalls) == n + 2 and "thumbnails broke the rules" in (tcalls[-1] or ""),
            "thumbnails that break the rules are asked again, and told why",
            tcalls[-1],
        )
        check(d3["thumbnails"][0]["words"] == "*Faster* forms", "and the second answer is kept")
        answers[:] = [good(title="Twice")]
        picked[:] = [{"thumbnails": bad_thumbs}] * 2
        d4 = await ytdraft.write(f, dict(CHANNEL, id="UCfourth"), recent, "api")
        check(
            d4["thumbnails"][0]["layout"] == "still" and any("put right" in x for x in d4["notes"]),
            "twice: put right from the film, the draft still written",
            d4["notes"],
        )
        answers[:] = [good(title=PROMPT), good(title=PROMPT)]
        try:
            await ytdraft.write(f, dict(CHANNEL, id="UCother"), recent, "login")
            check(False, "twice the brief is given up")
        except RuntimeError as e:
            check("repeating the brief" in str(e), "twice the brief is given up", e)
        rec = f.record()
        check(
            rec["youtube_drafts"] == 5 and abs(rec["cost_usd"] - before - 0.55) < 1e-6,
            "a draft on the login is counted, but not in cost_usd",
            rec,
        )

        # ------------------------------------------------------------ the API
        f.update(ok=True, state="done")  # a starting server resumes films left queued
        async with TestClient(TestServer(server.make_app(TOKEN))) as c:
            me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:alice", "Cf-Ray": "t"}
            other = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:bob", "Cf-Ray": "t"}
            g = fixture_film()
            ask = {"channel": CHANNEL, "recent": RECENT}
            r = await c.post("/api/films/%s/youtube/draft" % g.id, json=ask, headers=me)
            check(r.status == 409, "an unfinished film gets no draft", r.status)
            g.update(ok=True, state="done")
            r = await c.post("/api/films/%s/youtube/draft" % g.id, json=ask, headers=other)
            check(r.status == 403, "only its owner may ask", r.status)
            r = await c.post(
                "/api/films/%s/youtube/draft" % g.id,
                json={"channel": {"id": "../x"}, "recent": []},
                headers=me,
            )
            check(r.status == 400, "a channel id must be one", r.status)
            answers[:] = [good(title="From the API")]
            r = await c.post("/api/films/%s/youtube/draft" % g.id, json=ask, headers=me)
            j = await r.json()
            check(r.status == 202 and j["state"] == "writing", "202 while writing", (r.status, j))
            for _ in range(100):
                r = await c.get(
                    "/api/films/%s/youtube/draft/%s" % (g.id, CHANNEL["id"]), headers=me
                )
                j = await r.json()
                if j.get("state") != "writing":
                    break
                await asyncio.sleep(0.02)
            check(
                j.get("state") == "done"
                and j["title"] == "From the API"
                and j["tags"]
                and j["language"] == "en"
                and "key" not in j,
                "then the draft, and nothing of the studio's",
                j,
            )
            th = j.get("thumbs") or {}
            check(th.get("state") == "making", "then its thumbnails, being made", th)
            check(
                [g.id, CHANNEL["id"]] in ytdraft.in_flight(), "which the heartbeat counts as work"
            )
            for _ in range(100):
                r = await c.get(
                    "/api/films/%s/youtube/draft/%s" % (g.id, CHANNEL["id"]), headers=me
                )
                j = await r.json()
                if (j.get("thumbs") or {}).get("state") != "making":
                    break
                await asyncio.sleep(0.02)
            th = j.get("thumbs") or {}
            check(
                th.get("state") == "done"
                and [o["n"] for o in th.get("options", [])] == [1, 2, 3, 4]
                and th["options"][0]["path"] == "youtube/%s/thumb-1.jpg" % CHANNEL["id"],
                "then the four options, each with its picture's path",
                th,
            )
            check([g.id, CHANNEL["id"]] not in ytdraft.in_flight(), "and the work is over")
            r = await c.get("/api/films/%s/youtube/draft/%s" % (g.id, CHANNEL["id"]), headers=other)
            check(r.status == 404, "nobody else sees it", r.status)
            n = len(calls)
            r = await c.post("/api/films/%s/youtube/draft" % g.id, json=ask, headers=me)
            j = await r.json()
            check(r.status == 200 and len(calls) == n, "asked again: 200, no call", (r.status, j))
            ytdraft.JOBS.clear()  # a restarted server: the draft is on disk
            r = await c.get("/api/films/%s/youtube/draft/%s" % (g.id, CHANNEL["id"]), headers=me)
            j = await r.json()
            check(j.get("title") == "From the API", "and after a restart, from disk", j)
            check(j.get("thumbs") == {"state": "none"}, "no thumbnails on disk read none", j)
            n = len(made)
            r = await c.post("/api/films/%s/youtube/draft" % g.id, json=ask, headers=me)
            j = await r.json()
            check(
                r.status == 200 and j["thumbs"]["state"] == "making",
                "asked again, the kept draft has them made",
                j.get("thumbs"),
            )
            for _ in range(100):
                if not ytdraft.in_flight():
                    break
                await asyncio.sleep(0.02)
            check(len(made) == n + 1, "once", made)
            answers[:] = [RuntimeError]

            async def broken(*a, **k):
                raise RuntimeError("no draft: the model was away")

            ytdraft._call = broken
            h = fixture_film()
            h.update(ok=True, state="done")
            await c.post("/api/films/%s/youtube/draft" % h.id, json=ask, headers=me)
            for _ in range(100):
                r = await c.get(
                    "/api/films/%s/youtube/draft/%s" % (h.id, CHANNEL["id"]), headers=me
                )
                j = await r.json()
                if j.get("state") != "writing":
                    break
                await asyncio.sleep(0.02)
            check(j.get("state") == "failed" and j.get("error"), "a failure says so", j)
    finally:
        ytdraft._call = real_call
        thumbs.sheet, thumbs.make = real_sheet, real_make

    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
