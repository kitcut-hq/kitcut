#!/usr/bin/env python
"""A finished film's share page (share.py), with Claude, the browser and Azure stood in for: no
model, no network, no cost, seconds.

    python studio/test_share.py

Covers: the ask (the film, the brief marked private, the page's limits); the words held to them --
a long title cut at a word with no full stop, a long description cut, a link dropped, the language
as a short code whatever the film says; the two pictures' rules (two of them, headline or card,
words short and not the title); the brief pasted back or the film called generated asked again,
twice given up; the draft kept and reused; what it cost on the record; the pictures cut to
1200x628 (the thumbnail whole in the middle, as card.jpg is) and 1280x720, copied online and
named in the share; the share written as a partial update that leaves the rest of the record
alone; no picture when it could not be made or copying is off; premake swallowing a failure
(even SystemExit) and never touching the film's state, and not running at all while Claude is a
stub; GET /api/films/{id} answering the share; the CLI's dry run pricing without calling; the
film's own frame as the thumbnail (thumb alone, no call, kept by a remake, refused past the end).
Everything happens in a throwaway STUDIO_HOME.
"""

import io
import os
import sys
import json
import shutil
import asyncio
import tempfile
import argparse
import contextlib

HOME = tempfile.mkdtemp(prefix="studio-share-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402
import media  # noqa: E402
import procs  # noqa: E402
import share  # noqa: E402
import thumbs  # noqa: E402
import ytdraft  # noqa: E402
from film import Film  # noqa: E402

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

os.environ.pop("STUDIO_MEDIA_BASE", None)
procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
procs.SECRETS.pop("STUDIO_R2_SECRET", None)
TOKEN = "test-token"
SAS = "sv=2023-11-03&sr=c&sp=cwd&sig=test"
BLOBS = {}
PROMPT = (
    "make a video telling my customers that we moved every account to the new faster engine "
    "and that it is the best one on the market"
)
LINES = [
    (0.5, 4.0, "Every account now runs on the new engine."),
    (4.4, 9.0, "Forms come back sooner, and the answers land in the right fields."),
    (9.4, 13.0, "Nothing to change. Just upload your next form."),
]
THUMBS = [
    {"at": 3.5, "layout": "headline", "words": "*Faster* forms", "place": "top"},
    {"at": 8.6, "layout": "card", "words": "Nothing to change", "place": "left"},
]


def fixture_film(language="en", length=15):
    f = Film.create(PROMPT, length, client="u:alice")
    os.makedirs(f.path("audio", "vo"), exist_ok=True)
    with open(f.path("vo.json"), "w", encoding="utf-8") as fh:
        json.dump({"language": language, "lines": [{"text": t} for _, _, t in LINES]}, fh)
    tl = [{"i": i, "start": s, "end": e, "text": t} for i, (s, e, t) in enumerate(LINES)]
    with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"duration": length, "lines": tl}, fh)
    with open(f.path("film.js"), "w", encoding="utf-8") as fh:
        fh.write("// For: Acme's customers, who fill forms at work.\n(function () {})();\n")
    f.update(ok=True, state="done", claude_said="I made a 15-second update.", cost_usd=1.0)
    return f


def good(**over):
    d = {
        "title": "Acme moves every account to its new engine",
        "description": "Every Acme account now runs on the new engine: forms come back sooner, "
        "with the answers in the right fields.",
        "language": "en",
        "thumbnails": THUMBS,
    }
    return d | over


TINT = [30]  # the first quadrant's green: changed to remake a different picture


def picture(path, size=(1920, 1080)):
    """A 16:9 test picture: four coloured quadrants, so a crop or a shift shows."""
    im = Image.new("RGB", size, (200, TINT[0], 30))
    w, h = size
    im.paste((30, 160, 40), (w // 2, 0, w, h // 2))
    im.paste((30, 40, 200), (0, h // 2, w // 2, h))
    im.paste((230, 220, 40), (w // 2, h // 2, w, h))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, "JPEG", quality=95)
    return im


async def put(req):
    if req.query_string != SAS:
        return web.Response(status=403)
    BLOBS[req.match_info["name"]] = (dict(req.headers), await req.read())
    return web.Response(status=201)


async def delete(req):
    if req.query_string != SAS:
        return web.Response(status=403)
    return web.Response(status=202 if BLOBS.pop(req.match_info["name"], None) else 404)


class Recording(store.MemoryStore):
    """The memory store, also keeping every save's fields as they were asked for."""

    def __init__(self):
        super().__init__()
        self.saves = []

    def save(self, run_id, fields, final=False):
        self.saves.append((run_id, dict(fields)))
        return super().save(run_id, fields, final)


async def main():
    agent.STORE = mem = Recording()
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % (detail,)))
        if not ok:
            bad.append(what)

    # ---------------------------------------------------------------- the ask
    f = fixture_film()
    mat = ytdraft.material(f)
    text = share.ask_text(mat)
    check(PROMPT not in text and "(private)" not in text, "the brief is never sent")
    check("4.4-  9.0 s  Forms come back sooner" in text, "the narration with its times")
    check("at most 70 characters" in text and "at most 155" in text, "the page's limits")
    check("# The channel" not in text, "no channel")
    check('"headline"' in text and '"card"' in text and "panel" not in text, "two layouts only")

    # ---------------------------------------------------------------- the language
    for said, want in [
        ("en", "en"),
        ("en-US", "en"),
        ("uk_UA", "uk"),
        ("Ukrainian", "uk"),
        ("UA", "uk"),
        ("es", "es"),
        ("pt-BR", "pt"),
        ("", "en"),
        ("??", "en"),
        (None, "en"),
    ]:
        check(
            share.language(said) == want, "language %r -> %s" % (said, want), share.language(said)
        )
    out, _ = share.check(good(language="de"), dict(mat, language="uk-UA"))
    check(out["language"] == "uk", "the film's own language over the writer's", out)

    # ---------------------------------------------------------------- the words held to the page
    long_title = (
        "An update for everyone who fills forms at work: every account moves to the new one."
    )
    out, notes = share.check(good(title=long_title), mat)
    check(
        len(out["title"]) <= 70
        and long_title.startswith(out["title"])
        and not out["title"].endswith((" ", ".", ":")),
        "a long title is cut at a word, no full stop",
        out["title"],
    )
    check(any("cut the title" in n for n in notes), "and it says so", notes)
    out, _ = share.check(good(title="Acme moves to the new engine."), mat)
    check(out["title"] == "Acme moves to the new engine", "no full stop at the end", out["title"])
    out, _ = share.check(good(title="What changed?"), mat)
    check(out["title"] == "What changed?", "a question keeps its mark", out["title"])
    long_desc = "Every account now runs on the new engine. " * 6
    out, _ = share.check(good(description=long_desc), mat)
    check(
        len(out["description"]) <= 155 and out["description"].endswith("."),
        "a long description is cut at a sentence",
        out["description"],
    )
    out, _ = share.check(good(description="word " * 60), mat)
    check(
        len(out["description"]) <= 155 and out["description"].endswith("…"),
        "or at a word, marked",
        out["description"],
    )
    out, _ = share.check(good(description="See it at https://acme.example/x now.\nTwo lines"), mat)
    check(
        "http" not in out["description"] and "\n" not in out["description"],
        "one line, no link",
        out["description"],
    )
    try:
        share.check(good(title=""), mat)
        check(False, "no title is refused")
    except ValueError:
        check(True, "no title is refused")

    # ---------------------------------------------------------------- the brief and the pictures
    check(share.problem(share.check(good(), mat)[0], mat) is None, "a share from the film passes")
    gen = {"title": "Acme's new engine", "description": "An AI-generated update for Acme."}
    check(share.problem(gen, mat), "calling the film generated fails")
    title = good()["title"]
    cs, _, probs = ytdraft.check_thumbs(good(), mat, title, share.CONCEPTS, share.LAYOUTS)
    check(len(cs) == 2 and not probs, "two good pictures pass", probs)
    cs, notes, _ = ytdraft.check_thumbs(
        good(thumbnails=[dict(THUMBS[0]), dict(THUMBS[1], layout="panel")]),
        mat,
        title,
        share.CONCEPTS,
        share.LAYOUTS,
    )
    check([c["layout"] for c in cs] == ["headline", "card"], "a panel becomes a card", cs)
    _, _, probs = ytdraft.check_thumbs(
        good(thumbnails=THUMBS + [dict(THUMBS[0], at=12.0)]), mat, title, 2, share.LAYOUTS
    )
    check(any("exactly two" in p["text"] for p in probs), "three are too many", probs)
    rep = [dict(THUMBS[0], words="Acme moves every account"), THUMBS[1]]
    _, _, probs = ytdraft.check_thumbs(good(thumbnails=rep), mat, title, 2, share.LAYOUTS)
    check(not probs, "the title's message on the picture is allowed", probs)
    fixed, _ = ytdraft.repair(cs[:1], [{"n": 1, "text": "x"}], mat, n=2)
    check(len(fixed) == 2, "repaired to two, not four", fixed)

    # ---------------------------------------------------------------- writing, kept, costed
    answers, calls = [], []

    async def fake_call(mat, auth, film, model, effort, note=None):
        calls.append((auth, note))
        a = answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a, 0.05

    async def fake_sheet(film):
        return b"moments-jpeg"

    made = []

    async def fake_make(film, channel, draft, want=4):
        made.append((film.id, channel, want))
        opts = []
        for i, t in enumerate(draft["thumbnails"][:want], 1):
            p = film.path("outputs", "youtube", channel, "thumb-%d.jpg" % i)
            picture(p)
            opts.append(
                {"n": i, "path": "youtube/%s/thumb-%d.jpg" % (channel, i), "layout": t["layout"],
                 "words": t["words"], "at": t["at"], "t": t["at"], "checks": {}}
            )  # fmt: skip
        return {"key": draft.get("key"), "channel": channel, "options": opts}

    real = share._call, thumbs.sheet, thumbs.make
    share._call, thumbs.sheet, thumbs.make = fake_call, fake_sheet, fake_make
    app = web.Application(client_max_size=16 * 2**20)
    app.add_routes([web.put("/films/{name:.+}", put), web.delete("/films/{name:.+}", delete)])
    blob = TestServer(app, host="127.0.0.1")
    await blob.start_server()
    try:
        answers[:] = [good()]
        d = await share.write(f, "api")
        check(d["title"] == good()["title"] and len(calls) == 1, "one call")
        rec = f.record()
        check(
            rec["share_drafts"] == 1
            and abs(rec["share_cost_usd"] - 0.05) < 1e-6
            and abs(rec["cost_usd"] - 1.05) < 1e-6,
            "the call paid for on the record",
            rec,
        )
        check(os.path.isfile(f.path("share", "draft.json")), "the draft is kept in share/")
        n = len(calls)
        again = await share.write(f, "api")
        check(len(calls) == n and again["key"] == d["key"], "asked again: the kept draft")
        g = fixture_film()
        answers[:] = [good(description="An AI-generated update."), good()]
        await share.write(g, "login")
        check("generated" in (calls[-1][1] or ""), "a film called generated is asked again")
        check(
            abs(g.record()["cost_usd"] - 1.0) < 1e-6 and g.record()["share_cost_usd"] == 0.1,
            "on the login: counted, not in cost_usd",
            g.record(),
        )
        h = fixture_film()
        answers[:] = [good(description="An AI-generated update.")] * 2
        try:
            await share.write(h, "api")
            check(False, "called generated twice is given up")
        except RuntimeError as e:
            check("kept going wrong" in str(e), "called generated twice is given up", e)

        # ------------------------------------------------------------ the pictures
        src = f.path("temp", "src.jpg")
        im = picture(src)
        got = media.make_share(f.path("outputs"), src)
        with Image.open(got["image"]) as a, Image.open(got["thumb"]) as b:
            check(a.size == (1200, 628) and a.format == "JPEG", "share.jpg is 1200x628", a.size)
            check(b.size == (1280, 720) and b.format == "JPEG", "thumb.jpg is 1280x720", b.size)
            w = round(1920 * 628 / 1080)  # 1116: the thumbnail whole, centred
            x0 = (1200 - w) // 2
            mid = a.convert("RGB").crop((x0 + 4, 4, x0 + w - 4, 624))
            ref = im.resize((w, 628)).crop((4, 4, w - 4, 624))
            diff = ImageStat.Stat(ImageChops.difference(mid, ref)).mean
            check(max(diff) < 6, "the middle is the whole thumbnail", diff)
            edge = ImageStat.Stat(a.convert("RGB").crop((0, 0, x0 - 2, 628))).mean
            check(max(edge) > 20, "the strips are the picture, blurred, not black", edge)
            small = ImageStat.Stat(ImageChops.difference(b.convert("RGB"), im.resize((1280, 720))))
            check(max(small.mean) < 6, "thumb.jpg is the thumbnail scaled down", small.mean)
            check(a.info.get("progressive") or a.info.get("progression"), "progressive JPEG")
        # make_card keeps its behaviour: the poster pillarboxed
        picture(f.path("outputs", "film_poster.png").replace(".png", ".jpg"))
        Image.open(f.path("outputs", "film_poster.jpg")).save(f.path("outputs", "film_poster.png"))
        media.make_card(f.path("outputs"))
        with Image.open(f.path("outputs", "card.jpg")) as c:
            check(c.size == (1200, 628), "card.jpg as before", c.size)

        # ------------------------------------------------------------ the whole run, recorded
        os.environ["STUDIO_MEDIA_BASE"] = "http://127.0.0.1:%d/films/" % blob.port
        procs.SECRETS["STUDIO_MEDIA_SAS"] = SAS
        mem.save(f.id, {"state": "done", "title": "Kept", "cost_usd": 1.1})
        mem.saves.clear()
        before = {k: v for k, v in f.record().items() if k != "share"}
        sh = await share.run(f, "api", log=lambda s: None)
        base = "http://127.0.0.1:%d/films/%s/" % (blob.port, f.id)
        v = media.share_version(f.path("outputs"))
        check(
            len(v) == 8
            and sh.get("image") == base + "share-%s.jpg" % v
            and sh.get("thumb") == base + "thumb-%s.jpg" % v,
            "the pictures' lasting URLs, versioned",
            sh,
        )
        h1, body = BLOBS.get("%s/share-%s.jpg" % (f.id, v), ({}, b""))
        with open(f.path("outputs", "share.jpg"), "rb") as fh:
            same = body == fh.read()
        check(
            same
            and h1.get("x-ms-blob-content-type") == "image/jpeg"
            and "%s/thumb-%s.jpg" % (f.id, v) in BLOBS
            and "%s/share.jpg" % f.id not in BLOBS,
            "both copied online, as JPEG",
            list(BLOBS),
        )
        check(made[-1] == (f.id, "share", 2), "two options made, not four", made)
        check(
            set(sh) == {"title", "description", "language", "image", "thumb", "at", "key"}
            and sh["at"].endswith("Z")
            and len(sh["title"]) <= 70
            and len(sh["description"]) <= 155,
            "the share has the contract's keys",
            sh,
        )
        print("      share = %s" % json.dumps(sh, ensure_ascii=False))
        check(f.record().get("share") == sh, "on studio.json")
        after = {k: v for k, v in f.record().items() if k != "share"}
        check(after == before, "the rest of studio.json untouched", (before, after))
        check(
            [s for s in mem.saves if s[0] == f.id] == [(f.id, {"share": sh})],
            "studio_runs: one partial update of share alone",
            mem.saves,
        )
        doc = mem.docs[f.id]
        check(
            doc["share"] == sh and doc["title"] == "Kept" and doc["state"] == "done",
            "and the run's other fields stay",
            doc,
        )

        # a remade picture gets a new URL; the same picture keeps its URL
        again = await share.run(f, "api", log=lambda s: None)
        check(again["image"] == sh["image"], "the same picture: the same URL", again)
        TINT[0] = 90
        new = await share.run(f, "api", log=lambda s: None)
        TINT[0] = 30
        v2 = media.share_version(f.path("outputs"))
        check(
            v2 != v
            and new["image"] == base + "share-%s.jpg" % v2
            and new["thumb"] == base + "thumb-%s.jpg" % v2,
            "a remade picture: a new URL",
            (sh["image"], new["image"]),
        )
        check(f.record()["share"]["image"] == new["image"], "the record names the new one")
        n = await media.delete(f.id)
        check(
            n == 2
            and "%s/share-%s.jpg" % (f.id, v2) not in BLOBS
            and "%s/thumb-%s.jpg" % (f.id, v2) not in BLOBS,
            "delete removes the pictures the record names",
            (n, sorted(BLOBS)),
        )
        check(
            "%s/share-%s.jpg" % (f.id, v) in BLOBS,
            "an earlier version is left for the previews already posted",
            sorted(BLOBS),
        )
        sh = new

        # ------------------------------------------------------------ a frame as the thumbnail
        import subprocess

        mp4 = f.path("outputs", "film.mp4")
        lav = ["-f", "lavfi", "-i", "color=c=red:s=640x360:d=2:r=10"]
        lav += ["-f", "lavfi", "-i", "color=c=blue:s=640x360:d=2:r=10"]
        cut = ["-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p"]
        subprocess.run(["ffmpeg", "-y", "-v", "error"] + lav + cut + [mp4], check=True)
        mem.saves.clear()
        n = len(calls)
        fr = await share.set_frame(f, 3, log=lambda s: None)
        with Image.open(f.path("outputs", "thumb.jpg")) as im:
            px, size = im.convert("RGB").getpixel((640, 360)), im.size
        check(size == (1280, 720) and px[2] > 180 and px[0] < 80, "thumb.jpg is the frame", px)
        v3 = media.share_version(f.path("outputs"))
        check(
            fr["thumb"] == base + "thumb-%s.jpg" % v3
            and "%s/thumb-%s.jpg" % (f.id, v3) in BLOBS
            and "%s/share-%s.jpg" % (f.id, v3) not in BLOBS,
            "copied online under a new name, the link preview not copied again",
            sorted(BLOBS),
        )
        check(
            fr["frame"] == 3
            and all(fr[k] == sh[k] for k in ("title", "description", "language", "image", "key")),
            "the share keeps its words and its link preview, and the frame's time",
            fr,
        )
        check(
            len(calls) == n and [s for s in mem.saves if s[0] == f.id] == [(f.id, {"share": fr})],
            "no call, one partial update",
            mem.saves,
        )
        kept = await share.run(f, "api", log=lambda s: None)
        check(
            kept.get("frame") == 3 and kept["thumb"].rsplit("/", 1)[1].startswith("thumb-"),
            "a remade share keeps the frame",
            kept,
        )
        with Image.open(f.path("outputs", "thumb.jpg")) as im:
            px = im.convert("RGB").getpixel((640, 360))
        check(px[2] > 180 and px[0] < 80, "and thumb.jpg is still the frame", px)
        try:
            await share.set_frame(f, 99, log=lambda s: None)
            past = None
        except RuntimeError as e:
            past = str(e)
        check(past and "long" in past, "a time past the film's end is refused", past)
        check(share.frame_arg("off") == "off" and share.frame_arg("2") == 2.0, "--frame's values")
        sh = kept

        # no picture: the words still go on the record
        async def no_make(film, channel, draft, want=4):
            raise RuntimeError("no browser")

        thumbs.make = no_make
        g2 = fixture_film()
        answers[:] = [good()]
        sh = await share.run(g2, "api", log=lambda s: None)
        check(
            sh["title"] and "image" not in sh and "thumb" not in sh,
            "no picture made: the share without image and thumb",
            sh,
        )
        thumbs.make = fake_make
        os.environ.pop("STUDIO_MEDIA_BASE", None)
        procs.SECRETS.pop("STUDIO_MEDIA_SAS", None)
        os.environ.pop("STUDIO_R2_ENDPOINT", None)  # nor to R2, whatever the .env says
        os.environ.pop("STUDIO_MEDIA_OLD_BASE", None)
        procs.SECRETS.pop("STUDIO_R2_KEY_ID", None)
        procs.SECRETS.pop("STUDIO_R2_SECRET", None)
        g3 = fixture_film()
        answers[:] = [good()]
        sh = await share.run(g3, "api", log=lambda s: None)
        check(
            "image" not in sh and os.path.isfile(g3.path("outputs", "share.jpg")),
            "copying off: the pictures kept here, no URLs",
            sh,
        )

        # ------------------------------------------------------------ premake
        p = fixture_film()
        answers[:] = [RuntimeError("no draft: the model was away")] * 2
        with contextlib.redirect_stdout(io.StringIO()) as out:
            t = share.premake(p)
            await t
        rec = p.record()
        check(
            rec["state"] == "done" and rec["ok"] is True and "share" not in rec,
            "a failure leaves the film as it was",
            rec,
        )
        check("away" in (rec.get("share_error") or ""), "and is noted", rec.get("share_error"))
        check("SHARE %s failed" % p.id in out.getvalue(), "and logged", out.getvalue())
        q = fixture_film()
        answers[:] = [SystemExit("ANTHROPIC_API_KEY is not set")]
        with contextlib.redirect_stdout(io.StringIO()):
            await share.premake(q)
        check(q.record()["state"] == "done" and q.record().get("share_error"), "even SystemExit")
        answers[:] = [good()]
        with contextlib.redirect_stdout(io.StringIO()):
            await share.premake(q)
        check(
            q.record().get("share") and q.record().get("share_error") is None,
            "a later success clears the error",
            q.record(),
        )
        real_rc = agent.run_claude

        async def stub_claude(*a, **k):
            raise AssertionError("no film is made here")

        agent.run_claude = stub_claude
        check(share.premake(fixture_film()) is None, "not while Claude is a stub (the tests)")
        agent.run_claude = real_rc
        os.environ["STUDIO_SHARE"] = "0"
        check(share.premake(fixture_film()) is None, "not when STUDIO_SHARE=0")
        os.environ.pop("STUDIO_SHARE")
        src_server = open(server.__file__, encoding="utf-8").read()
        check(
            "thumbs.premake(film)\n                share.premake(film)" in src_server,
            "server.py starts it beside the moments sheet, for a film that is done",
        )

        # ------------------------------------------------------------ the CLI's dry run
        n = len(calls)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ns = argparse.Namespace(
                film=None, missing=True, limit=2, dry_run=True, auth=None, model=share.MODEL
            )
            await share._main(ns)
        said = buf.getvalue()
        check(
            len(calls) == n and "2 films" in said and "~$" in said,
            "--missing --dry-run lists and prices, calls nothing",
            said,
        )
        check(f.id not in said, "a film with its share is not missing", said)

        # ------------------------------------------------------------ the API
        agent.run_claude = stub_claude  # a starting server adopts nothing here, but never for real
        async with TestClient(TestServer(server.make_app(TOKEN))) as c:
            r = await c.get("/api/films/%s" % f.id, headers={"Authorization": "Bearer " + TOKEN})
            j = await r.json()
            want = {k: v for k, v in f.record()["share"].items() if k not in ("at", "key", "frame")}
            check(r.status == 200 and j.get("share") == want, "GET /api/films/{id}: the share", j)
            r = await c.get("/api/films/%s" % h.id, headers={"Authorization": "Bearer " + TOKEN})
            j = await r.json()
            check("share" not in j, "a film without one: none", j.get("share"))
        agent.run_claude = real_rc
    finally:
        share._call, thumbs.sheet, thumbs.make = real
        await blob.close()

    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%d failed" % len(bad) if bad else "\nall passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
