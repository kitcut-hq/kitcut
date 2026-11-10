#!/usr/bin/env python
"""A project's brand (brandkit.py), with Claude stood in for: python studio/test_brandkit.py

Covers: a file sent in parts (in order, a part sent again, one out of order refused, the size held
to), everything a brand folder can hold read from one zip -- a PDF drawn page by page, a PNG with
its transparency, a JPEG logo keyed off white with the white inside it kept, an SVG drawn by the
browser, a TrueType face and a woff2 one unpacked, a PowerPoint theme's colours and fonts, the
colour codes in a text file, an EPS refused with its reason, junk ignored, a zip in the zip --
then the card held to its shape (the brand's own pictures too: named once, each with what it is
for), the assets (sent fonts only with consent, a stand-in otherwise; a picture kept as it is), the
preview drawn by the film engine, a read as a job (the state it leaves), and an episode of the
project getting the brand (its manifest, brand.js, its note with each logo's and picture's
purpose; a brand picture the film never draws left out of it) while a film outside projects does
not. Everything in a throwaway STUDIO_HOME; the preview and the SVG take a browser (~20 s).
"""

import io
import os
import sys
import json
import shutil
import asyncio
import zipfile
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-brand-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import brandkit  # noqa: E402
import library  # noqa: E402
from film import KIT, Film  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

PROJECT = {"id": "p-abcdefghij", "name": "Course", "brief": "A course."}
FAILS = []


def check(ok, what, detail=""):
    print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)[:300]))
    if not ok:
        FAILS.append(what)


def png(im):
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def fixture():
    """A brand folder as somebody would zip it."""
    # a two-page PDF (Pillow writes one page per image)
    pages = [Image.new("RGB", (1240, 1754), c) for c in ("#ffffff", "#0056d2")]
    ImageDraw.Draw(pages[0]).rectangle((200, 200, 600, 400), fill="#0056d2")
    pdf = io.BytesIO()
    pages[0].save(pdf, "PDF", save_all=True, append_images=pages[1:])
    # a transparent PNG logo
    logo = Image.new("RGBA", (600, 240), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((20, 20, 220, 220), fill="#0056d2")
    # a JPEG logo on white: a blue badge with a white square inside it
    jpg = Image.new("RGB", (500, 300), "#ffffff")
    d = ImageDraw.Draw(jpg)
    d.rectangle((100, 50, 400, 250), fill="#0056d2")
    d.rectangle((200, 110, 300, 190), fill="#ffffff")
    jb = io.BytesIO()
    jpg.save(jb, "JPEG", quality=95)
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
        b'<rect x="10" y="10" width="180" height="80" rx="20" fill="#ff6600"/></svg>'
    )
    theme = (
        '<a:theme xmlns:a="x"><a:themeElements><a:clrScheme name="T">'
        '<a:dk1><a:srgbClr val="111111"/></a:dk1><a:accent1><a:srgbClr val="0056D2"/></a:accent1>'
        '</a:clrScheme><a:fontScheme name="F"><a:majorFont><a:latin typeface="Source Sans Pro"/>'
        "</a:majorFont></a:fontScheme></a:themeElements></a:theme>"
    )
    pptx = io.BytesIO()
    with zipfile.ZipFile(pptx, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("ppt/theme/theme1.xml", theme)
        z.writestr("ppt/slides/slide1.xml", "<p:sld><a:t>Learn anything, anywhere</a:t></p:sld>")
        z.writestr("ppt/media/image1.png", png(logo.rotate(90, expand=True)))
    # a mascot on a plain orange ground: a picture to show, whose ground is part of it
    mascot = Image.new("RGB", (400, 400), "#e8a33d")
    ImageDraw.Draw(mascot).ellipse((120, 80, 280, 320), fill="#222222")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("deep/mark.png", png(Image.new("RGBA", (120, 120), "#ff6600")))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Brand/Guidelines.pdf", pdf.getvalue())
        z.writestr("Brand/Logos/logo.png", png(logo))
        z.writestr("Brand/Logos/badge.jpg", jb.getvalue())
        z.writestr("Brand/Logos/logo.svg", svg)
        z.writestr("Brand/Logos/logo.eps", b"%!PS-Adobe-3.0 EPSF-3.0\n")
        z.writestr(
            "Brand/Fonts/Montserrat-Bold.ttf",
            open(os.path.join(KIT, "fonts", "Montserrat-Bold.ttf"), "rb").read(),
        )  # noqa: SIM115
        z.writestr(
            "Brand/Fonts/Inter.woff2", open(os.path.join(KIT, "fonts", "Inter.woff2"), "rb").read()
        )  # noqa: SIM115
        z.writestr("Brand/Deck.pptx", pptx.getvalue())
        z.writestr("Brand/colours.txt", "Primary blue #0056D2, orange #F60, RGB 17 17 17.")
        z.writestr("Brand/more.zip", inner.getvalue())
        z.writestr("Brand/Mascot/mascot.png", png(mascot))
        z.writestr("__MACOSX/Brand/._logo.png", b"junk")
        z.writestr("Brand/.DS_Store", b"junk")
    return out.getvalue()


CLAUDE = {
    "name": "Course Co",
    "summary": "A friendly learning brand.",
    "palette": [
        {"hex": "#0056d2", "name": "Blue", "role": "primary"},
        {"hex": "0056D2", "name": "dup", "role": "primary"},
        {"hex": "nope", "name": "bad"},
        {"hex": "#F60", "name": "Orange", "role": "primary"},
        {"hex": "#111111", "name": "Ink", "role": "text"},
    ],
    "type": {
        "headline": {
            "family": "Montserrat",
            "font": "f001",
            "weight": "700",
            "stand_in": "Montserrat",
        },
        "body": {
            "family": "Source Sans Pro",
            "font": "f999",
            "weight": "4OO",
            "stand_in": "Bad!Name",
        },
    },
    "logos": [
        {"image": "i002", "role": "other", "note": "the badge"},
        {"image": "i001", "role": "primary", "note": "the mark"},
        {"image": "i999", "role": "mark"},
        {"page": "p001", "box": [0.15, 0.1, 0.5, 0.25], "role": "on_dark"},
        {"page": "p001", "box": [0.5, 0.5, 0.5, 0.5], "role": "mark"},
    ],
    "tone": ["warm", "clear"],
    "voice": "Plain and encouraging.",
    "do": ["Lead with the learner"],
    "dont": ["Never stretch the logo"],
    "taglines": ["Learn anything, anywhere"],
    "pages": ["p002", "p404"],
}


def main():
    d = brandkit.dir_of(("u:alice", PROJECT["id"]))
    data = fixture()

    # ---- sending a file in parts
    m = brandkit.add_file(d, "C:\\Users\\x\\Brand kit.zip", len(data))
    check(m["name"] == "Brand kit.zip", "a file keeps its name, never a path", m["name"])
    half = len(data) // 2
    brandkit.put_part(d, m["id"], 0, data[:half])
    again = brandkit.put_part(d, m["id"], 0, data[:half])
    check(again["got"] == half, "a part sent again is taken as there")
    try:
        brandkit.put_part(d, m["id"], half + 10, data[half + 10 :])
        check(False, "a part out of order is refused")
    except brandkit.BrandError as e:
        check(e.status == 409, "a part out of order is refused")
    try:
        brandkit.finish(d, m["id"])
        check(False, "an unfinished file cannot be finished")
    except brandkit.BrandError:
        check(True, "an unfinished file cannot be finished")
    brandkit.put_part(d, m["id"], half, data[half:])
    check(brandkit.finish(d, m["id"])["done"], "the whole file finishes")
    check(brandkit.state_of(d)["state"] == "files", "the brand has files, not read")
    try:
        brandkit.add_file(d, "huge.pdf", brandkit.MAX_FILE + 1)
        check(False, "a file over the cap is refused")
    except brandkit.BrandError as e:
        check(e.status == 413, "a file over the cap is refused")

    # ---- reading
    inv = brandkit.ingest(os.path.join(d, "files"), os.path.join(d, "read"), log=lambda s: None)
    by = {f["path"].split("/")[-1]: f for f in inv["files"]}
    check(len(inv["pages"]) == 2, "the PDF's two pages are drawn", inv["pages"])
    check(
        by["Guidelines.pdf"]["used"] == "2 pages",
        "and the inventory says so",
        by.get("Guidelines.pdf"),
    )
    check("EPS" in (by["logo.eps"].get("skipped") or ""), "an EPS is refused with its reason")
    check(
        not any("__MACOSX" in f["path"] or ".DS_Store" in f["path"] for f in inv["files"]),
        "junk is ignored",
    )
    check(
        any(f["path"].endswith("more.zip/deep/mark.png") for f in inv["files"]),
        "a zip in the zip is opened",
    )
    check(
        by["logo.svg"]["used"].startswith("picture"),
        "an SVG is drawn by the browser",
        by["logo.svg"],
    )
    fams = sorted((f["family"], f["weight"]) for f in inv["fonts"])
    check(
        ("Montserrat", 700) in fams and any(f == "Inter" for f, _ in fams),
        "a ttf and a woff2 are read",
        fams,
    )
    check(all(f["file"].endswith((".ttf", ".otf")) for f in inv["fonts"]), "woff2 unpacked to sfnt")
    check(
        {"hex": "#0056D2", "slot": "accent1"} in inv["theme"]["colors"],
        "a PowerPoint theme's colours",
    )
    check(
        {"role": "majorFont", "family": "Source Sans Pro"} in inv["theme"]["fonts"], "and its fonts"
    )
    hexes = [c["hex"] for c in inv["colours"]]
    check(
        hexes[0] == "#0056D2" and "#FF6600" in hexes and "#111111" in hexes,
        "colour codes in the words",
        hexes,
    )
    with open(os.path.join(d, "read", "text.txt"), encoding="utf-8") as f:
        check("Learn anything" in f.read(), "a slide's words are read")
    png_logo = next(i for i in inv["images"] if i["from"].endswith("logo.png"))
    check(png_logo["alpha"], "a PNG keeps its transparency")

    # ---- the card
    for k, i in enumerate(
        inv["images"], 1
    ):  # the stand-in Claude names images by the fixture's order
        i["fixture"] = k
    card = brandkit.clean_card(CLAUDE, inv)
    check(
        [c["hex"] for c in card["palette"]] == ["#0056D2", "#FF6600", "#111111"],
        "colours: real, once",
        card["palette"],
    )
    check([c["role"] for c in card["palette"]].count("primary") == 1, "exactly one primary colour")
    check(
        card["type"]["body"]["font"] is None and card["type"]["body"]["weight"] == "400",
        "a face that is not there is not used",
    )
    check(card["type"]["body"]["stand_in"] == "Inter", "a stand-in that is not a family falls back")
    roles = [g["role"] for g in card["logos"]]
    check(
        len(card["logos"]) == 3 and roles.count("primary") == 1,
        "logos that exist, one primary",
        card["logos"],
    )
    check(card["pages"] == ["p002"], "pages that exist")

    # ---- key-out: the white inside the badge survives
    badge = next(i for i in inv["images"] if i["from"].endswith("badge.jpg"))
    with Image.open(os.path.join(d, "read", "images", badge["id"] + ".png")) as im:
        k = brandkit.key_out(im)
    check(k.getpixel((5, 5))[3] == 0, "a logo's white surround goes transparent")
    check(k.getpixel((250, 150))[3] == 255, "the white inside the logo stays")

    # ---- the brand's own pictures: each named once, with what it is for
    mascot = next(i for i in inv["images"] if i["from"].endswith("mascot.png"))
    said = "The brand's one character. Show her on the end card"
    pics = brandkit.clean_card(
        {
            **CLAUDE,
            "pictures": [
                {"image": mascot["id"], "name": "The Mascot!", "note": said},
                {"image": mascot["id"], "name": "twice"},
                {"image": "i999", "name": "nowhere"},
                {"image": badge["id"], "name": "pic_the_mascot"},
                "junk",
            ],
        },
        inv,
    )["pictures"]
    check(
        [g["name"] for g in pics] == ["the_mascot", "the_mascot_2"] and pics[0]["note"] == said,
        "pictures that exist, once, each under a name of its own",
        pics,
    )
    check(
        len(
            brandkit.clean_card(
                {"pictures": [{"image": i["id"]} for i in inv["images"]] * 3}, inv
            )["pictures"]
        )
        == min(brandkit.MAX_PICTURES, len(inv["images"])),
        "at most MAX_PICTURES of them",
    )
    card["pictures"] = pics

    # ---- assets: sent fonts only with consent
    brandkit.standin = lambda d, family, weights, log=print: []  # no network here
    card["type"]["headline"]["font"] = next(
        f["id"] for f in inv["fonts"] if f["family"] == "Montserrat"
    )
    used = brandkit.build_assets(d, card, log=lambda s: None)
    check(
        used["families"]["headline"] == {"family": "Inter", "sent": False, "missing": "Montserrat"},
        "no consent: the sent face is not used",
        used["families"],
    )
    card["fonts_consent"] = True
    used = brandkit.build_assets(d, card, log=lambda s: None)
    check(
        used["families"]["headline"]["sent"]
        and used["families"]["headline"]["family"] == "Montserrat",
        "with consent it is",
        used["families"],
    )
    check(
        os.path.exists(os.path.join(d, "assets", "brand_logo.png")),
        "the primary logo is brand_logo",
    )
    check(
        any(n.startswith("brand_logo_on_dark") for n in os.listdir(os.path.join(d, "assets"))),
        "a logo cut from a page",
    )
    with Image.open(os.path.join(d, "assets", "brand_pic_the_mascot.png")) as im:
        check(
            im.size == (400, 400) and im.convert("RGBA").getpixel((5, 5))[3] == 255,
            "a brand picture is kept as it is, its ground too",
            im.size,
        )
    check(
        used["picture_files"] == ["brand_pic_the_mascot", "brand_pic_the_mascot_2"],
        "the pictures an episode gets, in the card's order",
        used["picture_files"],
    )
    with open(os.path.join(d, "assets", "brand.js"), encoding="utf-8") as f:
        js = f.read()
    check(
        "SK.BRAND = " in js and "logoFor" in js and '"primary": "#0056D2"' in js,
        "brand.js carries the brand",
    )
    brandkit._write_json(os.path.join(d, "card.json"), card)  # noqa: SLF001

    # ---- the preview, drawn by the film engine
    os.makedirs(os.path.join(d, "preview"), exist_ok=True)
    p = brandkit.render_preview(d, "drawn", used, card, log=lambda s: None)
    with Image.open(p) as im:
        check(im.width > 1900 and im.height == 360, "the preview is three frames", im.size)
    check(os.path.exists(os.path.join(d, "preview", "drawn-3.jpg")), "and each frame on its own")

    # ---- an episode of the project gets it; a film outside projects does not
    ep = Film.create("Lesson one", 5, "drawn", client="u:alice", project=PROJECT)
    got = library.seed(ep)
    check(
        (got.get("brand") or {}).get("name") == "Course Co",
        "an episode is seeded with the brand",
        got.get("brand"),
    )
    with open(ep.manifest, encoding="utf-8") as f:
        man = json.load(f)
    check(man["head"]["scripts"][0] == "brand/brand.js", "brand.js runs before film.js")
    check(man["images"].get("brand_logo") == "brand/brand_logo.png", "its logos are images")
    check(
        any(
            f["file"].startswith("brand/fonts/") and f["family"] == "Montserrat"
            for f in man["fonts"]
        ),
        "its faces are fonts",
    )
    note = library.note(ep)
    check(
        "This project has a brand: Course Co" in note and "SK.BRAND.logoFor" in note,
        "its note says how to use it",
        note[-800:],
    )
    check("Never: Never stretch the logo" in note, "with the brand's rules")
    check(
        man["images"].get("brand_pic_the_mascot") == "brand/brand_pic_the_mascot.png"
        and got["brand"]["pictures"] == ["brand_pic_the_mascot", "brand_pic_the_mascot_2"],
        "its pictures are images",
        got["brand"],
    )
    check(
        "'brand_pic_the_mascot' (400x400): %s." % said in note and "never redrawn" in note,
        "its note says what each picture is and how to use it",
        note[-1200:],
    )
    check(
        "'brand_logo': the mark." in note and "'brand_logo_2': the badge." in note,
        "and what each logo is for, by the name a film draws it with",
        note[-1200:],
    )
    with open(ep.path("film.js"), "w", encoding="utf-8") as f:
        f.write("SK.image('brand_pic_the_mascot', 0, 0, 400);\n")
    gone = agent.drop_unused_uploads(ep)
    with open(ep.manifest, encoding="utf-8") as f:
        man = json.load(f)
    check(
        gone == ["brand_pic_the_mascot_2"] and "brand_logo" in man["images"],
        "a brand picture the film never draws leaves it; its logos stay",
        gone,
    )
    lone = Film.create("Not a lesson", 5, "drawn", client="u:alice")
    library.seed(lone)
    check(not os.path.exists(lone.path("brand")), "a film outside projects gets no brand")

    # ---- a read as a job: Claude stood in for
    async def fake_ask(inv, read_dir, auth="login", **k):
        return dict(CLAUDE, logos=[{"image": inv["images"][0]["id"], "role": "primary"}]), 0.12

    brandkit.ask = fake_ask
    brandkit._set_state(d, state="files", step=None)  # noqa: SLF001
    asyncio.run(brandkit.read(d, "api", "drawn", log=lambda s: None))
    pub = brandkit.public(d)
    check(pub["state"] == "ready", "a read ends ready", pub.get("error"))
    check(
        pub["card"]["name"] == "Course Co" and pub["card"]["fonts_consent"],
        "the card keeps the person's consent across a read",
    )
    check(pub["previews"].get("drawn"), "with its preview")
    check(
        len(pub["files"]) == 1 and pub["found_files"], "the page sees the files and what was found"
    )
    check(
        brandkit.asset(d, "logo", "brand_logo") and not brandkit.asset(d, "logo", "../card"),
        "assets by name only",
    )
    edited = brandkit.edit(
        d,
        {
            "name": "Course Company",
            "palette": [{"hex": "#123456", "role": "primary"}],
            "state": "x",
        },
    )
    check(
        edited["name"] == "Course Company" and edited["palette"][0]["hex"] == "#123456",
        "an edit is held to the card's shape",
    )
    hero = pub["images"][0]
    edited = brandkit.edit(
        d, {"pictures": [{"image": hero["id"], "name": "Hero shot", "note": "The product."}]}
    )
    pub = brandkit.public(d)
    check(
        edited["pictures"] == [{"image": hero["id"], "name": "hero_shot", "note": "The product."}]
        and pub["in_use"]["picture_files"] == ["brand_pic_hero_shot"]
        and brandkit.asset(d, "logo", "brand_pic_hero_shot")
        and hero.get("from")
        and pub["limits"]["pictures"] == brandkit.MAX_PICTURES,
        "a picture the person adds on the card is one every episode gets",
        (edited.get("pictures"), pub["in_use"]),
    )
    brandkit.remove(d)
    check(brandkit.public(d)["state"] == "empty", "a removed brand is empty")

    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    agent  # noqa: B018 -- imported for _env
    main()
