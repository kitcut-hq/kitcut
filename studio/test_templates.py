#!/usr/bin/env python
"""Templates (studio/templates.py): a finished film others remake with their own content, end to
end through the API with the film itself stubbed -- no Claude, no image model; one real render
(the health check), seconds.

    python studio/test_templates.py

Covers: what a version takes from a film (its code, its sample content, the engine, the sample's
pictures -- never anything else) and refuses (a film whose content is still in its code); what
anyone sees of one (an example of what to ask -- no form, no brief); drafts, live and retired
versions through the API; a film asked for from a template with a prompt and attachments (its
exact length, frame, capabilities, frozen engine, no narration, the sample as its starting point,
more pictures than a plain film may take); the first message; template_pictures (an attached or
web logo made readable on dark and light, the template's own pictures refused); the sample's own
words and pictures caught, the person's own words theirs, the sample's own event allowed when
asked for; and the health check drawing a live version again with this release's renderer.
"""

import os
import io
import sys
import json
import stat
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-templates-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import store  # noqa: E402
import templates  # noqa: E402
import uploads  # noqa: E402
import film as films  # noqa: E402
from film import Film  # noqa: E402
import tools  # noqa: E402
from tools import ToolError, Tools  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from PIL import Image  # noqa: E402

TOKEN = "test-token"

FILM_JS = """// For: a test
const D = SK.DATA.content;
SK.setStyle('clean', { grain: 0, vignette: 0 });
SK.film({
  duration: 5, camera: SK.camera([[0, [SK.W / 2, SK.H / 2, 1]]]), handheld: false, speedLines: false,
  fadeOut: 0,
  draw(t) {
    const c = SK.ctx(); c.fillStyle = D.palette.ground; c.fillRect(0, 0, SK.W, SK.H);
    c.fillStyle = '#ffffff'; c.font = '90px sans-serif'; c.fillText(D.event.name, 100 + t * 20, 300);
    const im = SK.IMG[D.speakers[0].image]; if (im) c.drawImage(im, 100, 420, 240, 240);
  },
  sound: { score: () => ({ bpm: 120, events: [] }), sfx: () => [{ t: 0.5, fx: 'pop', db: -20 }] },
});
"""
SAMPLE = {
    "_about": "a test template",
    "event": {
        "name": "SAMPLE FEST",
        "city": "SAMPLEVILLE",
        "url": "samplefest.example",
        "cta": "GET TICKETS",
    },
    "copy": {"speakers": "{city} SPEAKERS"},
    "palette": {"ground": "#102030"},
    "logo": {"image": "wordmark"},
    "speakers": [{"name": "ADA SAMPLEPERSON", "image": "sp-ada"}, {"image": "sp-bob"}],
}
SPEC = {
    "title": "Test promo",
    "frames": ["16:9", "1:1"],
    "caps": ["space", "portraits"],
    "moments": [1.0, 3.0],
    "limits": {"images": 9},
    "keep": ["_about", "copy"],
    "generic": ["GET TICKETS"],
    "identity": ["event.name"],
    "example": "A promo for Nordic Build 2027 in Helsinki: nordic.example",
    "brief": "Keep the title's slide.",
}


def png(w, h, col=(20, 30, 60, 255), bg=None):
    im = Image.new("RGBA" if bg is None else "RGB", (w, h), bg or (0, 0, 0, 0))
    for x in range(w // 4, 3 * w // 4):
        for y in range(h // 3, 2 * h // 3):
            im.putpixel((x, y), col if bg is None else col[:3])
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def jpg(w, h, col=(180, 140, 110)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), col).save(b, "JPEG")
    return b.getvalue()


def fixture():
    """A finished film's folder whose content is in "data": the sample event."""
    d = os.path.join(HOME, "src-film")
    os.makedirs(os.path.join(d, "images"))
    with open(os.path.join(d, "film.js"), "w", encoding="utf-8") as f:
        f.write(FILM_JS)
    with open(os.path.join(d, "content.json"), "w", encoding="utf-8") as f:
        json.dump(SAMPLE, f)
    for name, data in (
        ("wordmark", png(400, 120)),
        ("sp-ada", png(300, 300)),
        ("sp-bob", png(300, 300)),
    ):
        with open(os.path.join(d, "images", name + ".png"), "wb") as f:
            f.write(data)
    with open(os.path.join(d, "private-notes.txt"), "w", encoding="utf-8") as f:
        f.write("the author's own notes: never copied")
    m = {
        "title": "Sample Fest",
        "duration": 5.0,
        "fps": 30,
        "film": "film.js",
        "modules": ["space"],
        "data": {"content": "content.json"},
        "images": {k: "images/%s.png" % k for k in ("wordmark", "sp-ada", "sp-bob", "unused")},
        "audio": {"score": "score.json", "sfx": "sfx.json", "mix": {"music_db": 0}},
    }
    with open(os.path.join(d, "images", "unused.png"), "wb") as f:
        f.write(png(10, 10))
    with open(os.path.join(d, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)
    return d


async def main():
    agent.STORE = store.MemoryStore()
    server.start = lambda f, finish_only=False: None  # the film itself is test_server.py's job
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    # ---- a version: what it takes from a film, and what it will not
    src = fixture()
    got = [rel for _, rel in templates.plan(src, SPEC)]
    check(
        sorted(got)
        == sorted(
            [
                "film.js",
                "content.sample.json",
                "engine/engine.js",
                "engine/props.js",
                "engine/space.js",
                "sample/wordmark.png",
                "sample/sp-ada.png",
                "sample/sp-bob.png",
            ]
        ),
        "a version takes the code, the sample content, the engine and the sample's pictures only",
        got,
    )
    plain = os.path.join(HOME, "plain")
    os.makedirs(plain)
    with open(os.path.join(plain, "sketch.json"), "w", encoding="utf-8") as f:
        json.dump({"duration": 5}, f)
    try:
        templates.plan(plain, SPEC)
        refused = False
    except templates.TemplateError as e:
        refused = "not a template yet" in str(e)
    check(refused, "a film whose content is in its code is not a template yet")
    d = templates.make(src, "t-test-promo", SPEC)
    templates._readonly(d)
    names = {
        os.path.relpath(os.path.join(a, n), d).replace("\\", "/")
        for a, _, ns in os.walk(d)
        for n in ns
    }
    check(
        "private-notes.txt" not in " ".join(names) and not any("unused" in n for n in names),
        "nothing the sample does not name is copied",
        names,
    )
    ro = not (os.stat(os.path.join(d, "film.js")).st_mode & stat.S_IWUSR)
    check(ro, "a version is read-only once made")
    check(
        templates.load("t-test-promo") is None and templates.load("t-test-promo", 1, ("draft",)),
        "a new version is a draft, not live",
    )

    # ---- what anyone sees of it: an example to start from, never a form or the brief
    t = templates.load("t-test-promo", 1, ("draft",))
    pub = templates.public(t)
    check(
        pub.get("example") == SPEC["example"]
        and pub.get("limits") == {"images": 9}
        and "fields" not in pub
        and "brief" not in pub,
        "a template shows an example of what to ask and its picture cap -- no form, no brief",
        sorted(pub),
    )

    # ---- through the API
    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": "u:alice"}
        # from outside: the loopback is this machine, so the test says it came through the site
        out = {**me, "X-Forwarded-For": "203.0.113.9", "Cf-Connecting-Ip": "203.0.113.9"}
        server.from_this_machine = lambda req: req.headers.get("X-Test-Local") == "1"
        local = {**me, "X-Test-Local": "1"}

        async def up(data, ctype="image/png"):
            r = await c.post("/api/uploads", data=data, headers={**me, "Content-Type": ctype})
            return (await r.json())["id"]

        r = await c.get("/api/templates", headers=out)
        check((await r.json()).get("templates") == [], "a draft is not listed")
        r = await c.get("/api/templates/t-test-promo", headers=local)
        j = await r.json()
        check(
            r.status == 200 and "brief" not in j and j["preview"]["1:1"].endswith("/1x1/sheet.png"),
            "this machine sees a draft, never its brief",
            j,
        )
        logo = await up(png(600, 200, bg=(255, 255, 255, 255)))  # a dark logo on white, no alpha
        photos = [await up(jpg(500, 600, (40 + i, 90, 120)), "image/jpeg") for i in range(7)]
        body = {
            "template": {"id": "t-test-promo", "version": 1},
            "prompt": "A promo for Nordic Build 2027 in Helsinki, nordic.example",
            "attachments": [logo] + photos,
            "frame": "1:1",
            "seconds": 30,
        }
        r = await c.post("/api/films", json=body, headers=out)
        check(r.status == 404, "a draft cannot be made from the site", r.status)
        templates.set_status("t-test-promo", 1, "live")
        r = await c.get("/api/templates", headers=out)
        check(
            [x["id"] for x in (await r.json())["templates"]] == ["t-test-promo"],
            "a live one is listed",
        )
        r = await c.post("/api/films", json={**body, "prompt": "", "attachments": []}, headers=out)
        check(r.status == 400, "nothing asked and nothing attached is refused", r.status)
        r = await c.post(
            "/api/films", json={**body, "people": [{"upload": photos[0]}]}, headers=out
        )
        check(r.status == 400, "a template's film draws no talking people", r.status)
        r = await c.post("/api/films", json=body, headers=out)
        j = await r.json()
        check(
            r.status == 202 and j.get("template") == {"id": "t-test-promo", "version": 1},
            "a film from a template, from a prompt and 8 pictures (over a plain film's 6)",
            j,
        )
        f = Film.open(j.get("id"))
        rec = f.record()
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        first = agent.first_record(f, "web", "u:alice")
        check(
            first.get("template") == {"id": "t-test-promo", "version": 1, "title": "Test promo"},
            "the run's record names the template, for the site's count",
            first.get("template"),
        )
        r2 = await c.get("/api/films/%s" % f.id, headers=out)
        st = await r2.json()
        check(
            st.get("template", {}).get("id") == "t-test-promo" and st.get("frame") == "1:1",
            "the film's status says what it was made from",
            st.get("template"),
        )
        check(
            rec.get("length") == 5 and m["duration"] == 5.0,
            "its length is the template's",
            rec.get("length"),
        )
        check(
            m.get("frame") == [1080, 1080] and rec.get("frame") == "1:1",
            "the frame asked for",
            m.get("frame"),
        )
        check(
            rec.get("narration") is False
            and not os.path.exists(f.path("vo.json"))
            and "vo" not in m,
            "no narration: no vo.json",
            sorted(os.listdir(f.dir)),
        )
        check(
            {"template", "space", "portraits"} <= set(rec.get("caps") or [])
            and m.get("modules") == ["space"]
            and os.path.exists(f.path("engine", "space.js")),
            "its capabilities and their modules",
            (rec.get("caps"), m.get("modules")),
        )
        with (
            open(f.path("engine", "engine.js"), encoding="utf-8") as fh,
            open(os.path.join(d, "engine", "engine.js"), encoding="utf-8") as fh2,
        ):
            check(fh.read() == fh2.read(), "its engine is the version's, frozen")
        with open(f.path("content.json"), encoding="utf-8") as fh:
            cj = json.load(fh)
        check(
            cj == SAMPLE and m["data"] == {"content": "content.json"},
            "it starts from the template's own sample, for Claude to remake",
            cj.get("event"),
        )
        check(
            m["images"].get("upload8") == rec["attachments"][7]["file"]
            and m["images"].get("sp-ada") == "template/sample/sp-ada.png"
            and os.path.exists(f.path("template", "sample", "sp-ada.png")),
            "the person's pictures are attached as any film's; the sample's are there to draw",
            m["images"],
        )
        check(
            rec.get("prompt") == body["prompt"] and not rec.get("fields"),
            "the record keeps what they asked, in their words -- there is no form",
        )
        check(
            os.path.exists(f.path("template", "template.json"))
            and os.path.exists(f.path("template", "content.sample.json")),
            "the template sits beside the film to compare against",
        )
        check(
            f.writable(f.path("content.json"))
            and not f.writable(f.path("vo.json"))
            and not f.writable(f.path("template", "template.json")),
            "Claude may edit film.js and content.json, not the template's folder",
        )
        ask = agent.ask(f)
        check(
            body["prompt"] in ask
            and "an example, not a form" in ask
            and "Keep the title" in ask
            and "template_pictures" in ask
            and "WebSearch" in ask
            and "Narration: about" not in ask,
            "the first message: what they asked, the template as an example, the web theirs to use",
            ask[:300],
        )
        check(
            "upload1" in agent.attached_note(f),
            "and it names what they attached",
            agent.attached_note(f)[:200],
        )
        check(
            films.mark_box(f) == (820, 950, 1080, 1080),
            "the mark's corner in a square frame",
            films.mark_box(f),
        )

        # ---- the sample's own words and pictures are caught; the person's own are theirs
        left = templates.leftovers(f)
        check(
            "SAMPLE FEST" in left
            and "the picture sp-ada" in left
            and "GET TICKETS" not in left
            and "SAMPLE FEST" not in " ".join(x for x in left if x.startswith("the picture")),
            "a film still showing the sample is caught (its generic words are not)",
            left,
        )
        tl = Tools(f, server.SCHED, lambda ev: None)
        check(
            tl.web_limit() == max(tools.MAX_WEB_PICTURES, 9),
            "a template film may bring in its own number of pictures, never fewer than any film",
            tl.web_limit(),
        )
        said = await tl.template_pictures("upload1", [])
        with open(f.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        lg, ll = (
            Image.open(f.path("images", "logo.png")),
            Image.open(f.path("images", "logo-light.png")),
        )
        corner, mid = lg.getpixel((2, 2)), ll.getpixel((lg.width // 2, lg.height // 2))
        check(
            "logo-light" in said
            and m["images"].get("logo") == "images/logo.png"
            and corner[3] == 0
            and mid[3] > 200
            and sum(mid[:3]) > 600,
            "an attached logo on white: its background keyed out, a light copy for dark grounds",
            (said, corner, mid),
        )
        # a logo Claude brought in from the web is taken by its name too
        os.makedirs(f.path("web"), exist_ok=True)
        with open(f.path("web", "mark.png"), "wb") as fh:
            fh.write(png(500, 160, bg=(255, 255, 255, 255)))
        m["images"]["web_mark"] = "web/mark.png"
        with open(f.manifest, "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        said = await tl.template_pictures("mark", [])
        check("logo-light" in said, "a picture brought in from the web is taken by its name", said)
        for name in ("sp-ada", "nope"):
            try:
                await tl.template_pictures(name, [])
                refused = False
            except ToolError as e:
                refused = "attached" in str(e)
            check(refused, "the template's own picture or a missing one is refused: %s" % name)
        remade = dict(
            SAMPLE,
            event={
                "name": "NORDIC BUILD",
                "city": "HELSINKI",
                "url": "nordic.example",
                "cta": "GET TICKETS",
            },
            logo={"image": "logo"},
            speakers=[{"name": "AINO LEHTINEN", "image": "upload2"}],
        )
        with open(f.path("content.json"), "w", encoding="utf-8") as fh:
            json.dump(remade, fh)
        check(templates.leftovers(f) == [], "a film remade whole has nothing left over")
        with open(f.path("film.js"), "a", encoding="utf-8") as fh:
            fh.write("\n// SAMPLE FEST was here\n")
        left = templates.leftovers(f)
        check(left == ["SAMPLE FEST"], "the sample's words left in the code are caught", left)
        import validate  # noqa: PLC0415

        sc = {"bpm": 120, "events": [{"inst": "sub_bass", "notes": "0 F1 1 .5"}]}
        check(
            not [x for x in validate._score(sc, 5) if "instrument" in x],
            "a template's synthesised instrument (sub_bass) passes the score check",
            validate._score(sc, 5),
        )
        r = await c.post(
            "/api/films",
            json={
                "template": {"id": "t-test-promo"},
                "prompt": "Nordic Build 2027, also in Sampleville this year",
            },
            headers=local,
        )
        f2 = Film.open((await r.json()).get("id"))
        left = templates.leftovers(f2) if f2 else []
        check(
            "SAMPLEVILLE" not in left and "SAMPLE FEST" in left,
            "a word the person asked for is theirs, even when the sample has it",
            left,
        )
        r = await c.post(
            "/api/films",
            json={"template": {"id": "t-test-promo"}, "prompt": "Sample Fest again, in English"},
            headers=local,
        )
        f3 = Film.open((await r.json()).get("id"))
        check(
            f3 is not None and templates.leftovers(f3) == [],
            "asked for the sample's own event, nothing of it is a leftover",
        )
        # a new version retires the old one
        templates.make(src, "t-test-promo", SPEC)
        templates.set_status("t-test-promo", 2, "live")
        templates.set_status("t-test-promo", 1, "retired")
        r = await c.post("/api/films", json=body, headers=out)
        j = await r.json()
        check(
            r.status == 409 and j.get("version") == 2,
            "a retired version says which is current",
            j,
        )

        # ---- the pictures a plain film may take are still 6
        fresh = [await up(jpg(300, 300, (i, 50, 50)), "image/jpeg") for i in range(7)]
        try:
            await uploads.take("u:alice", fresh)
            why = ""
        except uploads.UploadError as e:
            why = str(e.body())
        check("Up to 6" in why, "a plain film still takes at most 6 pictures", why)
        try:
            await uploads.take("u:alice", fresh, 9)
            took = True
        except uploads.UploadError:
            took = False
        check(took, "a template's own cap lets it take more")

    # ---- the health check: a live version drawn again by this release
    t2 = templates.load("t-test-promo", 2)
    for fr in t2["frames"]:
        templates._render_stills(t2, fr, os.path.join(t2["_dir"], "preview", templates.fdir(fr)))
    worst = templates.check("t-test-promo")
    check(worst == [], "the health check draws a live version as it was", worst)
    sheet = os.path.join(t2["_dir"], "preview", "16x9", "sheet.png")
    check(os.path.exists(sheet), "a version has a preview sheet per frame")

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
