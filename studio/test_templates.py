#!/usr/bin/env python
"""Templates (studio/templates.py): a finished film others remake with their own content, end to
end through the API with the film itself stubbed -- no Claude, no image model; one real render
(the health check), seconds.

    python studio/test_templates.py

Covers: what a version takes from a film (its code, its sample content, the engine, the sample's
pictures -- never anything else) and refuses (a film whose content is still in its code); the
form's rules (required, too long, colours, dates, people and the featured, unknown keys dropped);
the content built from a form (the kept labels, paths, defaults, derived fields, people as image
keys); drafts, live and retired versions through the API; a film asked for from a template (its
exact length, frame, capabilities, frozen engine, no narration, the content and pictures laid
in, a logo made readable on dark and light, the template's sheet beside it, more pictures than a
plain film may take); the first message; the sample's own words caught; and the health check
drawing a live version again with this release's renderer.
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
    "derive": {"event.code": {"from": "event.city", "first": 3, "upper": True}},
    "fields": [
        {
            "key": "name",
            "kind": "text",
            "label": "Event name",
            "path": "event.name",
            "required": True,
            "upper": True,
            "max": 20,
        },
        {
            "key": "city",
            "kind": "text",
            "label": "City",
            "path": "event.city",
            "required": True,
            "upper": True,
            "max": 10,
        },
        {
            "key": "dates",
            "kind": "daterange",
            "label": "Dates",
            "paths": {"short": "event.dates", "long": "event.dates_long", "year": "event.year"},
        },
        {
            "key": "cta",
            "kind": "text",
            "label": "Button",
            "path": "event.cta",
            "default": "GET TICKETS",
        },
        {"key": "url", "kind": "url", "label": "Website", "path": "event.url", "required": True},
        {"key": "logo", "kind": "logo", "label": "Logo", "path": "logo", "required": True},
        {
            "key": "ground",
            "kind": "colour",
            "label": "Background",
            "path": "palette.ground",
            "required": True,
        },
        {
            "key": "people",
            "kind": "people",
            "label": "Speakers",
            "path": "speakers",
            "required": True,
            "min": 2,
            "max": 8,
            "featured": {"min": 1, "max": 5},
            "item": [
                {"key": "name", "label": "Name", "max": 20, "upper": True},
                {"key": "role", "label": "Role", "max": 30},
            ],
        },
    ],
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

    # ---- the form
    t = templates.load("t-test-promo", 1, ("draft",))

    def refuses(values, word):
        try:
            templates.validate_fields(t, values)
            return False
        except templates.TemplateError as e:
            return word in str(e)

    ok_form = {
        "name": "Nordic Build",
        "city": "Helsinki",
        "dates": {"from": "2027-05-20", "to": "2027-05-21"},
        "url": "https://nordic.example/tickets",
        "logo": "up-aaaa",
        "ground": "#123524",
        "people": [
            {"photo": "up-p1", "name": "Aino Lehtinen", "role": "Founder"},
            {"photo": "up-p2"},
        ],
        "nonsense": "dropped",
    }
    clean = templates.validate_fields(t, ok_form)
    check(
        clean["name"] == "NORDIC BUILD"
        and "nonsense" not in clean
        and clean["ground"] == "#123524",
        "a form: upper-cased where the field says, unknown keys dropped",
        clean,
    )
    check(refuses({**ok_form, "name": ""}, "required"), "a required field left empty is refused")
    check(
        refuses({**ok_form, "city": "HELSINKI-VANTAA"}, "at most 10"),
        "too long is refused, not cut",
    )
    check(refuses({**ok_form, "ground": "green"}, "colour"), "a colour is #rrggbb")
    check(
        refuses({**ok_form, "dates": {"from": "2027-05-21", "to": "2027-05-20"}}, "before"),
        "an end before the start is refused",
    )
    check(
        refuses({**ok_form, "people": ok_form["people"][:1]}, "2 to 8"),
        "too few people are refused",
    )
    check(
        refuses({**ok_form, "people": [{"photo": "up-p1"}, {"photo": "up-p2"}]}, "featured"),
        "a line-up with no featured (named) speaker is refused",
    )
    check(
        refuses(
            {**ok_form, "people": [{"photo": "up-p1", "name": "A"}, {"photo": "up-p1"}]}, "twice"
        ),
        "the same photo twice is refused",
    )
    check(
        templates.dates_words("2026-11-09", "2026-11-12")
        == ("NOV 9–12", "NOVEMBER 9–12, 2026", "2026")
        and templates.dates_words("2026-10-30", "2026-11-02")[0] == "OCT30–NOV2",
        "dates: a range in one month, and across two",
    )
    content, pics = templates.build_content(t, clean)
    check(
        content.get("copy") == SAMPLE["copy"] and "SAMPLE FEST" not in json.dumps(content),
        "content keeps the labels and none of the sample's event",
        content,
    )
    check(
        content["event"]["cta"] == "GET TICKETS"
        and content["event"]["code"] == "HEL"
        and content["event"]["dates"] == "MAY 20–21"
        and content["event"]["year"] == "2027",
        "defaults, derived fields and dates fill in",
        content["event"],
    )
    check(
        pics == {"logo": "up-aaaa", "sp-1": "up-p1", "sp-2": "up-p2"}
        and content["speakers"][0] == {"name": "AINO LEHTINEN", "role": "Founder", "image": "sp-1"},
        "people become image keys the film draws",
        (pics, content["speakers"]),
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
            "this machine sees a draft's form, never its brief",
            j,
        )
        logo = await up(png(600, 200, bg=(255, 255, 255, 255)))  # a dark logo on white, no alpha
        photos = [await up(jpg(500, 600, (40 + i, 90, 120)), "image/jpeg") for i in range(7)]
        form = {
            **ok_form,
            "logo": logo,
            "people": [{"photo": photos[0], "name": "Aino Lehtinen", "role": "Founder"}]
            + [{"photo": p} for p in photos[1:]],
        }
        body = {
            "template": {"id": "t-test-promo", "version": 1},
            "fields": form,
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
        r = await c.post(
            "/api/films", json={**body, "fields": {**form, "city": "X" * 11}}, headers=out
        )
        j = await r.json()
        check(
            r.status == 400 and j.get("field") and "City" in j.get("error", ""),
            "a wrong field comes back named",
            j,
        )
        r = await c.post("/api/films", json=body, headers=out)
        j = await r.json()
        check(
            r.status == 202 and j.get("template") == {"id": "t-test-promo", "version": 1},
            "a film from a template (8 pictures: over a plain film's 6)",
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
            cj["event"]["name"] == "NORDIC BUILD"
            and len(cj["speakers"]) == 7
            and m["data"] == {"content": "content.json"},
            "the person's content is the film's",
            cj["event"],
        )
        check(
            m["images"].get("sp-3") == "images/people/sp-3.webp"
            and os.path.exists(f.path("inputs", "people", "sp-3.jpg")),
            "each photo waits to be cut out",
            m["images"].get("sp-3"),
        )
        lg, ll = (
            Image.open(f.path("images", "logo.png")),
            Image.open(f.path("images", "logo-light.png")),
        )
        corner, mid = lg.getpixel((2, 2)), ll.getpixel((lg.width // 2, lg.height // 2))
        check(
            corner[3] == 0 and mid[3] > 200 and sum(mid[:3]) > 600,
            "a logo on white: its background keyed out, a light copy for dark grounds",
            (corner, mid),
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
            "remake of the template" in ask
            and "Narration: about" not in ask
            and "Keep the title" in ask,
            "the first message is the template's",
            ask[:200],
        )
        check(
            films.mark_box(f) == (820, 950, 1080, 1080),
            "the mark's corner in a square frame",
            films.mark_box(f),
        )
        # the sample's own words are caught; the person's own are theirs
        with open(f.path("film.js"), "a", encoding="utf-8") as fh:
            fh.write("\n// SAMPLE FEST was here\n")
        left = templates.leftovers(f)
        check(
            left == ["SAMPLE FEST"],
            "the sample's words left in the code are caught (a default it shares is not)",
            left,
        )
        import validate  # noqa: PLC0415

        sc = {"bpm": 120, "events": [{"inst": "sub_bass", "notes": "0 F1 1 .5"}]}
        check(
            not [x for x in validate._score(sc, 5) if "instrument" in x],
            "a template's synthesised instrument (sub_bass) passes the score check",
            validate._score(sc, 5),
        )
        form2 = {
            **form,
            "name": "Sample Fest",
            "logo": await up(png(600, 200)),
            "people": [
                {"photo": await up(jpg(400, 400, (9, 9, 9)), "image/jpeg"), "name": "Aino"},
                {"photo": await up(jpg(400, 400, (19, 9, 9)), "image/jpeg")},
            ],
        }
        r = await c.post("/api/films", json={**body, "fields": form2}, headers=local)
        f2 = Film.open((await r.json()).get("id"))
        check(
            f2 is not None and "SAMPLE FEST" not in templates.leftovers(f2),
            "a word the person gave is theirs, even when the sample has it",
        )
        # a new version retires the old one's form
        templates.make(src, "t-test-promo", SPEC)
        templates.set_status("t-test-promo", 2, "live")
        templates.set_status("t-test-promo", 1, "retired")
        r = await c.post("/api/films", json=body, headers=out)
        j = await r.json()
        check(
            r.status == 409 and j.get("version") == 2,
            "a retired version asks for the form again",
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
