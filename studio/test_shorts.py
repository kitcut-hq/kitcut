#!/usr/bin/env python
"""A film from an idea in a frame of its own, with the narration's words in the picture: what a
YouTube Short needs (film.FRAMES, film.CAPS "captions", sketch/captions.js). No model, no
network, no browser; node runs the caption module against a stub when it is installed. Seconds.

    python studio/test_shorts.py

Covers: a film asked for in 9:16 with captions gets the frame in its manifest, the module in its
engine folder and both in its record; a film asked for as ever is byte for byte the film it was
(no frame, no module, no note, half a second before its first word); a Short speaks at once, keeps
its own opening as the video's first frame, and can be asked for with no music at all (the
manifest's audio.music, the record, the first message, and the pitched cues the mix leaves out);
the first message names the frame and the caption band; the band
film.py tells the writer about is the one captions.js draws in, for every frame; and the cards it
cuts a narration into never hold more words than the frame allows, never leave a last word alone,
and never overlap in time; and a film that is not 16:9 gets no share picture, since that is
composed for 16:9 (thumbs.wide) -- its YouTube options are punches at its own frame, drawn by a
browser, which studio/test_thumbs.py covers.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-shorts-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _sketchaudio as A  # noqa: E402
import agent  # noqa: E402
import film as films  # noqa: E402
import thumbs  # noqa: E402

FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


# what the bundler injects as SK.VO: two lines, word times a quarter of a second apart
LINES = [
    "This week, a model wrote seven hundred and twenty-two mathematics papers.",
    "Nobody asked it to. Mathematicians are still reading them, one by one, and arguing.",
]


def timeline():
    t, lines = 0.5, []
    for text in LINES:
        words = []
        for w in text.split():
            words.append({"text": w, "s": round(t, 3), "e": round(t + 0.2, 3)})
            t += 0.25
        lines.append({"start": words[0]["s"], "end": words[-1]["e"], "words": words})
        t += 0.8
    return {"lines": lines}


STUB = """
const SK = { W: %d, H: %d, clamp: (v) => Math.max(0, Math.min(1, v)), VO: %s, film() { SK._film = {}; },
  BRAND: %s };
globalThis.window = globalThis; globalThis.SK = SK;
require(%s); require(%s);
console.log(JSON.stringify({ box: SK.captionBox(), cards: SK.captionCards(), data: SK.captionData() }));
"""


def module(w, h, brand=None):
    """sketch/captions.js (and the layer it draws with) run by node against a stub of the
    engine: its band, its cards and its captions.json."""
    layer = os.path.join(_env.ROOT, "sketch", "captions-layer.js")
    src = os.path.join(_env.ROOT, "sketch", "captions.js")
    code = STUB % (w, h, json.dumps(timeline()), json.dumps(brand), json.dumps(layer), json.dumps(src))
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    _env.utf8_stdio()
    print("a film asked for as a Short")
    short = films.Film.create(
        "the week in AI", 30, "collage", client="t", frame="9:16", captions=True
    )
    with open(short.manifest, encoding="utf-8") as f:
        m = json.load(f)
    rec = short.record()
    expect("its manifest is 1080x1920", m.get("frame") == [1080, 1920], m.get("frame"))
    expect(
        "and loads the captions modules, the layer first",
        (m.get("modules") or [])[-2:] == ["captions-layer", "captions"],
        m.get("modules"),
    )
    expect(
        "which are in its engine folder",
        os.path.exists(short.path("engine", "captions.js"))
        and os.path.exists(short.path("engine", "captions-layer.js")),
    )
    expect(
        "with the face they are drawn in",
        any(
            f.get("family") == "Inter" and f.get("file") == films.CAPTIONS_FONT["file"]
            for f in m.get("fonts") or []
        ),
        m.get("fonts"),
    )
    expect(
        "its record says so",
        rec.get("frame") == "9:16" and "captions" in rec.get("caps"),
        (rec.get("frame"), rec.get("caps")),
    )
    first = agent.first_record(short, "web", "t")
    expect(
        "and so does the run the site reads",
        first.get("frame") == "9:16"
        and first.get("captions") == "live"
        and first.get("captions_on") is True,
        (first.get("frame"), first.get("captions"), first.get("captions_on")),
    )
    note = films.frame_note(short)
    x0, y0, x1, y1 = films.caption_band(1080, 1920)
    expect("the first message names the frame", "1080x1920" in note and "vertical" in note)
    expect(
        "and the band the captions take, in world units",
        "x %d to %d, y %d to %d" % (x0 - 540, x1 - 540, y0 - 960, y1 - 960) in note,
        note[-400:],
    )
    expect(
        "the band is clear of what a phone covers", y1 < 1920 * (1 - 0.2) and x1 < 1080, (y1, x1)
    )
    expect("and the whole of it is in the first message", note in agent.ask(short))
    with open(short.path("vo.json"), encoding="utf-8") as f:
        lead = json.load(f).get("lead")
    expect("it speaks at once", lead == films.TALL_LEAD, lead)
    expect("and its pins keep it so", short.vo_pins().get("lead") == films.TALL_LEAD)
    expect("its own opening is the video's first frame", m.get("cover") is False, m.get("cover"))
    expect(
        "the first message says both",
        "%g s in" % films.TALL_LEAD in note and "frame 0" in note,
        note[:900],
    )
    expect(
        "and it has music, nobody having said otherwise",
        "music" not in rec and "music" not in m["audio"] and "no music" not in note,
    )

    print("a Short with no music")
    quiet = films.Film.create(
        "the week in AI", 30, "collage", client="t", frame="9:16", captions=True, music=False
    )
    with open(quiet.manifest, encoding="utf-8") as f:
        qa = json.load(f)["audio"]
    expect(
        "its manifest says so, and keeps the rest of its sound",
        qa.get("music") is False and qa.get("score") == m["audio"].get("score"),
        qa,
    )
    expect(
        "so do its record and the run the site reads",
        quiet.record().get("music") == "none"
        and agent.first_record(quiet, "web", "t").get("music") == "none",
    )
    expect("and the first message", "This film has no music" in films.frame_note(quiet))
    expect(
        "the pitched cues it names are the ones the mix leaves out",
        films.TONAL_FX == A.TONAL_FX
        and all('"%s"' % n in films.frame_note(quiet) for n in A.TONAL_FX),
        (films.TONAL_FX, A.TONAL_FX),
    )

    print("a film asked for as ever")
    wide = films.Film.create("the week in AI", 30, "collage", client="t")
    with open(wide.manifest, encoding="utf-8") as f:
        m = json.load(f)
    expect("has no frame in its manifest", "frame" not in m, m.get("frame"))
    expect(
        "has captions too, live, starting off",
        "captions" in (m.get("modules") or [])
        and wide.record().get("captions") == "live"
        and wide.record().get("captions_on") is False,
        (m.get("modules"), wide.record().get("captions"), wide.record().get("captions_on")),
    )
    expect("no frame in its record", "frame" not in wide.record(), wide.record().get("frame"))
    wnote = films.frame_note(wide)
    x0, y0, x1, y1 = films.caption_band(1920, 1080)
    expect(
        "and its note is the captions' band alone",
        wnote.startswith("\n\nThe film has captions")
        and "x %d to %d, y %d to %d" % (x0 - 960, x1 - 960, y0 - 540, y1 - 540) in wnote
        and "1920" not in wnote,
        wnote[:300],
    )
    expect(
        "which says what may pass behind them, and what may not",
        all(w in wnote for w in ("people's legs and bodies", "never a head, a face or a neck"))
        and "check that no face is under a card" in wnote
        and "switch them on or off" in wnote,
        wnote,
    )
    with open(wide.path("vo.json"), encoding="utf-8") as f:
        lead = json.load(f).get("lead")
    expect(
        "it waits half a second before its first word, as ever",
        lead == films.VO_PINNED["lead"] == wide.vo_pins().get("lead"),
        lead,
    )
    expect("and its cover is the renderer's to choose", "cover" not in m, m.get("cover"))
    odd = films.Film.create("the week in AI", 30, "drawn", client="t", frame="4:3")
    expect("a frame the studio does not make is 16:9", "frame" not in odd.record())
    expect(
        "the look's prompt is the same with captions as without",
        agent.system_prompt("collage", short.caps) == agent.system_prompt("collage", wide.caps),
    )

    print("thumbnails")
    expect("a 16:9 film is one a thumbnail is composed for", thumbs.wide(wide))
    expect("a tall one is not", not thumbs.wide(short))
    rec = thumbs.make_now(short, "share", {"key": "k1", "thumbnails": [{"at": 1.0}]}, want=2)
    expect("so it gets no share picture (and no browser is started)", rec.get("options") == [], rec)
    expect(
        "which is told as a finished draft with none, at the film's own frame",
        thumbs.public(thumbs.saved(short, "share", "k1"))
        == {"state": "done", "v": "k1-%s" % rec["design"], "frame": [1080, 1920], "options": []},
        thumbs.public(thumbs.saved(short, "share", "k1")),
    )

    print("the caption module")
    if not shutil.which("node"):
        print("  skipped: node is not installed")
    for name, (w, h) in films.FRAMES.items() if shutil.which("node") else ():
        got = module(w, h)
        expect(
            "%s: the band film.py names is the one it draws in" % name,
            tuple(got["box"]) == films.caption_band(w, h),
            (got["box"], films.caption_band(w, h)),
        )
        cards = got["cards"]
        most = {"9:16": 4, "1:1": 5, "16:9": 8}[name]
        said = " ".join(c["text"] for c in cards)
        expect("%s: every word is on a card, in order" % name, said == " ".join(LINES), said)
        expect(
            "%s: no card holds more than %d words (one more to keep a last word company)"
            % (name, most),
            all(len(c["text"].split()) <= most + 1 for c in cards),
            [c["text"] for c in cards],
        )
        expect(
            "%s: no cards overlap" % name,
            all(a["e"] <= b["s"] + 1e-9 for a, b in zip(cards, cards[1:], strict=False)),
            [(c["s"], c["e"]) for c in cards],
        )
        expect(
            "%s: a sentence ends its card" % name,
            all(c["text"].endswith(".") for c in cards if "." in c["text"]),
            [c["text"] for c in cards],
        )
    if shutil.which("node"):
        print("the captions' data and their colours")
        got = module(1080, 1920)
        data = got["data"]
        expect(
            "captions.json holds the cards, with their words' times",
            [" ".join(w["text"] for w in c["words"]) for c in data["cards"]]
            == [c["text"] for c in got["cards"]]
            and all("s" in w and "e" in w for c in data["cards"] for w in c["words"]),
        )
        expect(
            "and the look and frame they are drawn in",
            data["frame"] == [1080, 1920]
            and all(k in data["style"] for k in ("card", "ink", "said", "font", "y", "size")),
            data.get("style"),
        )
        expect("a film with no brand wears the default", data["style"]["said"] == "#ffe14d")
        navy = {"colors": {"primary": "#192859", "accent": "#DAA33C", "background": "#FFFFFF"}}
        st = module(1080, 1920, navy)["data"]["style"]
        expect(
            "a brand's: its darkest colour for the card, white words, its accent said",
            (st["card"], st["ink"], st["said"]) == ("rgba(25,40,89,0.9)", "#ffffff", "#daa33c"),
            st,
        )
        dim = {"colors": {"primary": "#202020", "accent": "#333366", "text": "#3a3a3a"}}
        st = module(1080, 1920, dim)["data"]["style"]
        expect(
            "an accent that does not read on the card falls back to the yellow",
            st["said"] == "#ffe14d" and st["card"] == "rgba(32,32,32,0.9)",
            st,
        )
        pale = {"colors": {"primary": "#f4d35e", "accent": "#fefae0"}}
        st = module(1080, 1920, pale)["data"]["style"]
        expect(
            "a brand with no colour white reads on keeps the default card",
            st["card"] == "rgba(17,17,21,.86)",
            st,
        )
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
