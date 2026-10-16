#!/usr/bin/env python
"""A project's style (stylekit.py), with Claude, the painters and Google Fonts stood in for:
python studio/test_stylekit.py

Covers: pictures sent in parts and converted (a transparent PNG onto white, an AVIF, a GIF's first
frame), a HEIC and a fourth picture refused with what to do, a font file read; the colours
measured; the card held to its shape (lettering boxes, faces offered, the first face of each role
picked, the route); a style line that names a thing found out; the lettering cut out and set in
each face; the proof painted two ways for a customer and three for the team, with prices only
for the team; Gemini refused to anyone else and moved off when anyone else edits; the assets (a
sent face only with the tick); an episode of the project getting the style (its picture, faces,
style.js before brand.js, its record's paint_route, paint.json pinned and held there by the
guard, a round keeping it) and its note; a film outside projects getting nothing; and the
painter sending the style picture first and the character second. Everything in a throwaway
STUDIO_HOME, no network.
"""

import io
import os
import sys
import json
import shutil
import asyncio
import importlib
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-style-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import brandkit  # noqa: E402
import guard  # noqa: E402
import library  # noqa: E402
import rounds  # noqa: E402
import stylekit  # noqa: E402
from film import KIT, Film  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SP = importlib.import_module("sketch-paint")
PROJECT = {"id": "p-stylestyle", "name": "Weddings", "brief": "Wedding stories for couples."}
FAILS = []
ANTON = os.path.join(KIT, "fonts", "Anton-Regular.ttf")


def check(ok, what, detail=""):
    print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)[:300]))
    if not ok:
        FAILS.append(what)


def enc(im, fmt, **kw):
    b = io.BytesIO()
    im.save(b, fmt, **kw)
    return b.getvalue()


def send(d, name, data, part=1000):
    """A file sent the way the page sends one: in parts, the second part sent twice."""
    m = stylekit.add_file(d, name, len(data))
    off = 0
    for k, i in enumerate(range(0, len(data), part)):
        chunk = data[i : i + part]
        stylekit.put_part(d, m["id"], off, chunk)
        if k == 1:
            stylekit.put_part(d, m["id"], off, chunk)  # a retry after a lost answer
        off += len(chunk)
    return stylekit.finish(d, m["id"])


def refused(fn, status):
    try:
        fn()
    except stylekit.StyleError as e:
        return e.status == status
    return False


CLAUDE = {
    "style": "soft watercolour on white paper, pastel blush and sage, a marble bust, no outlines",
    "objects": ["marble bust", "wedding cake", "rings"],
    "layout": "small objects scattered over a white page, words in the middle",
    "look": {"pick": "painted", "why": "washes of colour"},
    "mixed": None,
    "palette": [{"hex": "#FFFFFF", "role": "ground"}],
    "lettering": [
        {
            "picture": 1,
            "box": [0.1, 0.05, 0.9, 0.2],
            "text": "Samantha + Michael",
            "kind": "script",
            "case": "mixed",
            "spacing": 0,
            "weight": 400,
            "role": "title",
            "candidates": ["Allison", "Great Vibes", "not a family!"],
        },
        {"picture": 9, "box": [0, 0, 1, 1], "text": "no such picture", "candidates": ["Lato"]},
    ],
    "subject": "A couple walking across a bridge at sunset, a wide shot.",
}


def main():
    lib = ("u:alice", PROJECT["id"])
    d = stylekit.dir_of(lib)

    # ---- pictures in, converted
    see_through = Image.new("RGBA", (900, 600), (0, 0, 0, 0))
    ImageDraw.Draw(see_through).ellipse((100, 100, 500, 500), fill=(230, 160, 170, 255))
    a = send(d, "sign.png", enc(see_through, "PNG"))
    with Image.open(os.path.join(d, "pictures", a["id"] + ".jpg")) as im:
        corner = im.getpixel((5, 5))
    check(a["kind"] == "image" and corner[0] > 245, "a transparent PNG is a JPEG on white", corner)
    big = Image.new("RGB", (4000, 1000), (120, 160, 140))
    b = send(d, "wide.avif", enc(big, "AVIF"), part=4096)
    check(
        b["kind"] == "image" and (b["w"], b["h"]) == (2048, 512),
        "an AVIF is read and its long side held to 2048",
        (b.get("w"), b.get("h")),
    )
    frames = [Image.new("P", (200, 200), i) for i in (10, 200)]
    gif = io.BytesIO()
    frames[0].save(gif, "GIF", save_all=True, append_images=frames[1:])
    c = send(d, "moving.gif", gif.getvalue())
    check(c["kind"] == "image", "a GIF is its first frame")
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 40
    m = stylekit.add_file(d, "phone.heic", len(heic))
    stylekit.put_part(d, m["id"], 0, heic)
    check(refused(lambda: stylekit.finish(d, m["id"]), 415), "a HEIC is refused with what to do")
    check(
        refused(lambda: send(d, "fourth.png", enc(big, "PNG")), 409),
        "a fourth picture is refused",
    )
    with open(ANTON, "rb") as f:
        font = send(d, "Anton.ttf", f.read(), part=50_000)
    check(font["kind"] == "font" and font["family"] == "Anton", "a font file is read", font)
    check(refused(lambda: stylekit.put_part(d, a["id"], 0, b"x"), 409), "a finished file is shut")
    pics = stylekit.pictures(d)
    check([p["id"] for p in pics] == [a["id"], b["id"], c["id"]], "the pictures, in order")

    # ---- the colours, measured
    two = Image.new("RGB", (200, 100), "#E8A0AA")
    two.paste(Image.new("RGB", (100, 100), "#2E4A3F"), (100, 0))
    p2 = os.path.join(HOME, "two.png")
    two.save(p2)
    pal = stylekit.palette_of([p2])
    hexes = {c["hex"] for c in pal}
    check(
        len(pal) == 2 and {"#E8A0AA", "#2E4A3F"} == hexes,
        "the colours a picture is made of, measured",
        pal,
    )

    # ---- the card
    measured = stylekit.palette_of([os.path.join(d, "pictures", p["id"] + ".jpg") for p in pics])
    card = stylekit.clean_card(dict(CLAUDE, fonts=None), pics, measured, stylekit.font_files(d))
    ln = card["lettering"]
    check(
        len(ln) == 1
        and ln[0]["picture"] == a["id"]
        and ln[0]["candidates"] == ["Allison", "Great Vibes"],
        "lettering points at a picture, with faces that are families",
        ln,
    )
    check(
        card["fonts"] == {"title": {"family": "Allison", "weight": 400, "sent": False}},
        "each role's first face is picked",
        card["fonts"],
    )
    check(
        card["route"] == "words" and card["main"] == a["id"] and card["look"]["pick"] == "painted",
        "the route starts on Muse and the first picture is the main one",
        (card["route"], card["main"]),
    )
    check(
        [c["hex"] for c in card["palette"]] == [c["hex"] for c in measured],
        "the palette is the measured colours, with Claude's roles",
        card["palette"],
    )
    check(
        stylekit.leaks(card["style"], card["objects"]) == ["marble bust"],
        "a style line that names a thing in the pictures is found out",
        stylekit.leaks(card["style"], card["objects"]),
    )
    check(
        stylekit.leaks("glossy cut-out studio photography, plum and tangerine", card["objects"])
        == [],
        "one that names no thing passes",
    )

    # ---- a read as a job: Claude, Google Fonts and the painters stood in for
    asked = []

    async def fake_claude(content, system, auth="login", effort="medium", session="style"):
        text = content[-1]["text"]
        asked.append(text)
        if "Write it again" in text:
            return {"style": "soft watercolour on white paper, pastel blush and sage"}, 0.01
        return CLAUDE, 0.05

    def fake_standin(dd, family, weights, log=print):
        return [(ANTON, w) for w in weights]

    painted = []

    def fake_paint(
        prompt, model, ref=None, quality=None, aspect="16:9", transparent=False, style_ref=None
    ):
        painted.append({"model": model, "prompt": prompt, "style_ref": style_ref})
        cost = {"meta/muse-image": 0.01, "openai/gpt-image-2.5-flare": 0.016}.get(model, 0.07)
        return enc(Image.new("RGB", (64, 36), "#ddd"), "PNG"), {"cost_usd": cost}

    # the real step first: a process of its own, handed only the painter's key -- with none, each
    # painter says so in proof.json and nothing is spent
    os.makedirs(os.path.join(HOME, "nokey"), exist_ok=True)
    stylekit._write_json(os.path.join(HOME, "nokey", "card.json"), {"style": "x", "subject": "y"})  # noqa: SLF001
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    got = asyncio.run(
        stylekit.paint_proof_step(os.path.join(HOME, "nokey"), False, log=lambda s: None)
    )
    if saved:
        os.environ["OPENROUTER_API_KEY"] = saved
    check(
        sorted(got["routes"]) == ["gpt", "words"]
        and all("OPENROUTER_API_KEY" in g.get("error", "") for g in got["routes"].values()),
        "the proof is a step of its own, and says when it has no key",
        got,
    )

    async def fake_step(
        dd, team, log=print
    ):  # the step, in this process, with its painters stood in
        card_ = json.load(open(os.path.join(dd, "card.json"), encoding="utf-8"))
        return await asyncio.to_thread(stylekit.paint_proof, dd, card_, team, log)

    stylekit._claude = fake_claude  # noqa: SLF001
    stylekit.paint_proof_step = fake_step
    brandkit.standin = fake_standin
    SP.paint_openrouter = fake_paint

    async def run_read(team):
        stylekit.start(d, "api", "painted", PROJECT["brief"], team, log=lambda s: None)
        while stylekit.in_flight():
            await asyncio.sleep(0.05)

    asyncio.run(run_read(False))
    pub = stylekit.public(d, team=False)
    card = pub["card"]
    check(pub["state"] == "ready", "a read ends ready", pub.get("error"))
    check(
        "bust" not in card["style"]
        and card["leaks"] == []
        and any("Write it again" in t for t in asked),
        "a style line that named a thing was asked for again, without it",
        card["style"],
    )
    check(
        "Wedding stories for couples." in asked[0] and "NEVER name a thing" in asked[0],
        "Claude is shown the brief and told never to name a thing",
    )
    check(
        os.path.exists(os.path.join(d, "fonts", "l0.jpg"))
        and os.path.exists(os.path.join(d, "fonts", "l0-1.png")),
        "each line of lettering is cut out and set in each face",
    )
    routes = [r["id"] for r in pub["proof"]["routes"]]
    check(
        routes == ["gpt", "words"] and all(r["painted"] for r in pub["proof"]["routes"]),
        "a customer's proof is painted two ways",
        pub["proof"],
    )
    check(
        all("usd" not in r for r in pub["proof"]["routes"]) and pub["gemini_note"] is None,
        "and shows no prices",
    )
    gpt = next(p for p in painted if p["model"] == "openai/gpt-image-2.5-flare")
    words = next(p for p in painted if p["model"] == "meta/muse-image")
    check(
        gpt["style_ref"]
        and gpt["style_ref"].endswith(card["main"] + ".jpg")
        and "watercolour" not in gpt["prompt"]
        and "watercolour" in words["prompt"]
        and not words["style_ref"],
        "GPT Image gets the picture and only the subject; Muse gets the style line",
        (gpt["prompt"][:120], words["prompt"][:120]),
    )

    # ---- the team: Gemini painted, priced, picked; nobody else may
    painted.clear()
    asyncio.run(run_read(True))
    team = stylekit.public(d, team=True)
    check(
        [r["id"] for r in team["proof"]["routes"]] == ["gpt", "words", "gemini"],
        "the team's proof is painted three ways",
    )
    check(
        team["gemini_note"].startswith("Team only. Gemini costs about 7 times")
        and "$0.56" in team["gemini_note"],
        "the team is told what Gemini costs, from the proof's own prices",
        team["gemini_note"],
    )
    check(
        refused(lambda: stylekit.edit(d, {"route": "gemini"}, team=False), 403),
        "anyone else is refused Gemini",
    )
    picked = stylekit.edit(d, {"route": "gemini"}, team=True, log=lambda s: None)
    check(picked["route"] == "gemini" and picked["route_team"], "the team picks Gemini")
    moved = stylekit.edit(d, {"layout": "words in the middle"}, team=False, log=lambda s: None)
    check(
        moved["route"] == "gpt" and "team only" in (moved.get("route_note") or ""),
        "anyone else's edit moves a Gemini style to GPT Image, and says why",
        moved,
    )

    # ---- assets: a sent face only with the tick
    card = stylekit.edit(
        d,
        {"fonts": {"title": {"family": "Anton", "weight": 400}, "body": {"family": "Allison"}}},
        team=False,
        log=lambda s: None,
    )
    used = json.load(open(os.path.join(d, "assets", "used.json"), encoding="utf-8"))
    check(
        "title" not in used["families"] and used["families"]["body"]["family"] == "Allison",
        "a face the person sent is not used without their tick",
        used["families"],
    )
    stylekit.edit(d, {"fonts_consent": True}, team=False, log=lambda s: None)
    used = json.load(open(os.path.join(d, "assets", "used.json"), encoding="utf-8"))
    check(
        used["families"]["title"] == {"family": "Anton", "weight": 400, "sent": True}
        and os.path.exists(os.path.join(d, "assets", "style.jpg")),
        "with it, it is; the main picture is style.jpg",
        used["families"],
    )
    js = open(os.path.join(d, "assets", "style.js"), encoding="utf-8").read()
    check("SK.STYLE = " in js and '"title": "Anton"' in js, "style.js carries the style")

    # ---- an episode of the project
    stylekit.edit(d, {"route": "gpt"}, team=False, log=lambda s: None)
    ep = Film.create("The bridge", 10, "painted", client="u:alice", project=PROJECT)
    got = library.seed(ep)
    check(
        (got.get("style") or {}).get("route") == "gpt", "an episode is seeded with the style", got
    )
    man = json.load(open(ep.manifest, encoding="utf-8"))
    check(man["head"]["scripts"][0] == "style/style.js", "style.js runs before film.js")
    check(
        any(f["file"].startswith("style/fonts/") and f["family"] == "Anton" for f in man["fonts"]),
        "its faces are fonts",
    )
    rec = ep.record()
    check(
        rec.get("paint_route") == {"route": "gpt", "ref": "style/style.jpg", "line": card["style"]},
        "the record says how its pictures are painted",
        rec.get("paint_route"),
    )
    paint = json.load(open(ep.path("paint.json"), encoding="utf-8"))
    check(
        paint["model"] == "openai/gpt-image-2.5-flare"
        and paint["style_ref"] == "style/style.jpg"
        and paint["style"] == "",
        "paint.json is pinned to GPT Image and the style picture",
        paint,
    )
    paint |= {"model": "meta/muse-image", "style": "oil painting", "style_ref": "../x.jpg"}
    json.dump(paint, open(ep.path("paint.json"), "w", encoding="utf-8"))
    said = guard.pin_paint(ep)
    paint = json.load(open(ep.path("paint.json"), encoding="utf-8"))
    check(
        paint["model"] == "openai/gpt-image-2.5-flare"
        and paint["style_ref"] == "style/style.jpg"
        and paint["style"] == ""
        and said,
        "Claude cannot change the painter, the style or the picture",
        paint,
    )
    pins = rounds._pins(ep, rec)  # noqa: SLF001
    check(
        pins["paint"].get("style_ref") == "style/style.jpg"
        and pins["paint"]["model"] == "openai/gpt-image-2.5-flare",
        "a round keeps the episode's painter and picture",
        pins.get("paint"),
    )
    note = library.note(ep)
    check(
        "This project has a style" in note and "says ONLY what to draw" in note,
        "its note says to write only what to draw",
        note[-900:],
    )
    first = agent.first_record(ep, "web", "u:alice")
    check(first.get("paint_route") == "gpt", "the run's record names the route", first)
    drawn = Film.create("Drawn one", 10, "drawn", client="u:alice", project=PROJECT)
    library.seed(drawn)
    check(
        "paint_route" not in agent.first_record(drawn, "web", "u:alice"),
        "a drawn episode paints nothing, so its record names no route",
    )

    words_d = stylekit.dir_of(("u:alice", "p-stylewords"))
    shutil.copytree(d, words_d)
    stylekit.edit(words_d, {"route": "words"}, team=False, log=lambda s: None)
    ep2 = Film.create(
        "The cake", 10, "painted", client="u:alice", project=dict(PROJECT, id="p-stylewords")
    )
    library.seed(ep2)
    paint = json.load(open(ep2.path("paint.json"), encoding="utf-8"))
    check(
        paint["model"] == "meta/muse-image"
        and paint["style"] == card["style"]
        and "style_ref" not in paint,
        "on the words route Muse paints from the style line",
        paint,
    )
    lone = Film.create("No project", 10, "painted", client="u:alice")
    library.seed(lone)
    paint = json.load(open(lone.path("paint.json"), encoding="utf-8"))
    paint["style_ref"] = "x.jpg"
    json.dump(paint, open(lone.path("paint.json"), "w", encoding="utf-8"))
    guard.pin_paint(lone)
    paint = json.load(open(lone.path("paint.json"), encoding="utf-8"))
    check(
        not os.path.exists(lone.path("style")) and "style_ref" not in paint,
        "a film outside projects gets no style, and cannot name a style picture",
        paint,
    )

    # ---- a style is its project's alone: no other project, no film outside projects, no film
    # made before it, and nothing that reads across films sees any of it
    other = dict(PROJECT, id="p-styleother", name="Other")
    b_ep = Film.create("Other project", 10, "painted", client="u:alice", project=other)
    library.seed(b_ep)
    b_paint = json.load(open(b_ep.path("paint.json"), encoding="utf-8"))
    check(
        not os.path.exists(b_ep.path("style"))
        and "paint_route" not in b_ep.record()
        and b_paint.get("model") == "meta/muse-image"
        and b_paint.get("style") == ""
        and "style_ref" not in b_paint
        and stylekit.public(stylekit.dir_of(("u:alice", "p-styleother")))["state"] == "empty",
        "another project of the same account gets nothing of the style",
        b_paint,
    )
    check(
        "This project has a style" not in library.note(b_ep)
        and "style/style.js" not in json.dumps(json.load(open(b_ep.manifest, encoding="utf-8"))),
        "and is told nothing of it",
    )
    early = dict(PROJECT, id="p-styleearly", name="Early")
    e0 = Film.create("Made before the style", 10, "painted", client="u:alice", project=early)
    library.seed(e0)
    shutil.copytree(d, stylekit.dir_of(("u:alice", "p-styleearly")))  # its style arrives later
    guard.pin_paint(e0)
    e0_paint = json.load(open(e0.path("paint.json"), encoding="utf-8"))
    check(
        "paint_route" not in e0.record()
        and e0_paint["model"] == "meta/muse-image"
        and "style_ref" not in e0_paint
        and rounds._pins(e0, e0.record())["paint"]["model"] == "meta/muse-image",  # noqa: SLF001
        "an episode made before the style keeps its own painter, and so does its next version",
        e0_paint,
    )
    e1 = Film.create("Made after", 10, "painted", client="u:alice", project=early)
    library.seed(e1)
    check(e1.record().get("paint_route"), "while the project's next episode takes the style")
    for f_ in (ep, ep2, b_ep):
        f_.update(state="done")
    newcomer = Film.create("Someone else", 10, "painted", client="u:bob")
    recent = agent.recent_films(newcomer)
    told = agent.recent_note("painted", recent)
    seen = json.dumps(recent)
    check(
        card["style"][:40] not in seen
        and card["style"][:40] not in told
        and len(recent) == 1
        and recent[0].get("look") == "painted",
        "films made under a style never reach another film's note of recent choices",
        (len(recent), told[:300]),
    )
    looks_dir = os.path.join(KIT, "studio", "looks")
    check(
        all(
            "style_ref" not in open(os.path.join(looks_dir, n_), encoding="utf-8").read()
            for n_ in os.listdir(looks_dir)
        ),
        "the looks' own instructions are what every other film reads, unchanged",
    )

    import argparse  # noqa: PLC0415
    import template_from_film as tff  # noqa: PLC0415

    tff.PULLED = os.path.join(HOME, "pulled")
    fid = "studio-20261015-120000-styled"
    os.makedirs(os.path.join(tff.PULLED, fid))
    json.dump({"duration": 10}, open(os.path.join(tff.PULLED, fid, "sketch.json"), "w"))
    json.dump(
        {"state": "done", "paint_route": {"route": "gpt"}},
        open(os.path.join(tff.PULLED, fid, "studio.json"), "w"),
    )
    a_ = argparse.Namespace(film=fid, slug="styled-test", plan=False, force=True, with_style=False)
    try:
        tff.stage_pull(a_)
        refused_tpl = False
    except tff.Stop as e:
        refused_tpl = "project's style" in str(e)
    check(
        refused_tpl and not os.path.exists(tff.project("styled-test")),
        "a styled film is never made into a template by accident",
    )

    # ---- the painter: the style picture first, the character second
    pics_, lead = SP.ref_lead("char.jpg", "style.jpg")
    check(
        pics_ == ["style.jpg", "char.jpg"]
        and lead.startswith(SP.STYLE_REF)
        and SP.STYLE_AND_REF in lead,
        "the painter sends the style picture first and the character second",
    )
    check(SP.ref_lead("char.jpg") == (["char.jpg"], SP.KEEP_REF), "without a style, as before")
    im = {"name": "a", "prompt": "a bridge"}
    spec = {"backend": "openrouter", "model": "m", "style": ""}
    check(
        SP.fingerprint(spec, im) == SP.fingerprint(spec, im, None, None)
        and SP.fingerprint(spec, im, None, "abc") != SP.fingerprint(spec, im),
        "a style picture is in a painting's fingerprint, and nothing changes without one",
    )

    stylekit.remove(d)
    check(stylekit.public(d)["state"] == "empty", "a removed style is empty")
    print("\n%s" % ("all passed" if not FAILS else "%d FAILED" % len(FAILS)))
    shutil.rmtree(HOME, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
