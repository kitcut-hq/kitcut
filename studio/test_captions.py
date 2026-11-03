#!/usr/bin/env python
"""A film's captions as data: rendered clean, written beside the video, burned into a copy only
when one leaves KitCut (film.CAPS "captions", sketch/captions-layer.js, scripts/captions-burn.py,
studio/captions.py, youtube.py). No model, no network. With a browser, a small film is rendered
and burned for real (about a minute); without one those cases are skipped.

    python studio/test_captions.py

Covers: every film from an idea has the captions, live, whatever its frame, and a template's
film too when it has narration; a look picked on the film's page is checked before it reaches a
command line; a version with no captions.json has nothing to burn; a copy is asked for once and
answered the same afterwards, a new look is another copy, and an old one is pruned after its days;
a YouTube send asked for with captions sends the copy with them, and one asked without the film;
placing (scripts/_captionplace.py, on a made-up video): a scene whose picture sits low has its
cards at the top, one whose picture sits high keeps them at the foot, a card goes with the scene
it is most in, a film's own scene times split it where its picture does not change, words the
film drew under the foot send them up and a head under the top keeps them down; and, rendered
in three scenes: neither the video nor a still has a card in it, captions.json holds every word and
puts the low scene's cards at the top, and the burned copy draws each card where captions.json
says (the band's pixels far from a clean frame's there, and within a few levels of them in the
other band).
"""

import os
import sys
import json
import time
import asyncio
import shutil
import tempfile
import subprocess

HOME = tempfile.mkdtemp(prefix="studio-captions-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import captions  # noqa: E402
import film as films  # noqa: E402
import youtube  # noqa: E402

FAILED = []


def expect(what, ok, got=None):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else " -- got %r" % (got,)))
    if not ok:
        FAILED.append(what)


WORDS = "This is a test of live captions. They are drawn over the video, not in it."
# three scenes: the first busy in the lower part of the frame, the second in the upper, the third
# plain paper with a label drawn where the cards at the foot go
FILM_JS = """
const busy = (y0, y1) => { const c = SK.ctx(); c.fillStyle = '#16161a';
  for (let i = 0; i < 27; i++) for (let j = 0; (y0 + 40 * j) < y1; j++)
    if ((i + j) % 2 === 0) c.fillRect(-540 + 40 * i, y0 + 40 * j, 40, 40); };
SK.film({ duration: 5 });
SK.scene({ id: 'low', from: 0, draw() { busy(240, 960); } });
SK.scene({ id: 'high', from: 2.5, draw() { busy(-960, -240); } });
SK.scene({ id: 'label', from: 4.0, draw() { const c = SK.ctx(); c.fillStyle = '#16161a';
  c.font = 'bold 64px sans-serif'; c.textAlign = 'center'; c.fillText('A LABEL', 0, 450); } });
"""


def small_film(frame="9:16"):
    f = films.Film.create("a test", 5, "drawn", client="t", frame=frame, captions=True)
    with open(f.path("film.js"), "w", encoding="utf-8") as fh:
        fh.write(FILM_JS)
    os.makedirs(f.path("audio", "vo"), exist_ok=True)
    t, words = 0.3, []
    for w in WORDS.split():
        words.append({"text": w, "s": round(t, 2), "e": round(t + 0.22, 2)})
        t += 0.3
    line = {"start": words[0]["s"], "end": words[-1]["e"], "words": words}
    with open(f.path("audio", "vo", "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"lines": [line]}, fh)
    return f


def fake_version(f, cards=1):
    """outputs/ as a render leaves it, without a render: a video, a web copy, captions.json."""
    out = f.path("outputs")
    os.makedirs(out, exist_ok=True)
    for n in ("film.mp4", "film_web.mp4"):
        with open(os.path.join(out, n), "wb") as fh:
            fh.write(b"video")
    data = {"v": 1, "frame": [1080, 1920], "cards": [{"s": 0, "e": 1, "words": []}] * cards}
    with open(os.path.join(out, "captions.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return out


def cases_made():
    print("every film has them")
    for frame in ("16:9", "1:1", "9:16"):
        f = films.Film.create("an idea", 30, "drawn", client="t", frame=frame)
        rec = f.record()
        expect(
            "%s: live captions, starting hidden when nobody asked otherwise" % frame,
            rec.get("captions") == "live"
            and "captions" in rec["caps"]
            and rec.get("captions_on") is False,
            (rec.get("captions"), rec.get("captions_on")),
        )
    on = films.Film.create("an idea", 30, "drawn", client="t", captions=True).record()
    expect("asked for shown, it starts shown", on.get("captions_on") is True)


def cases_style():
    print("a look picked on the film's page")
    expect("none is the film's own", captions.clean_style(None) is None)
    got = captions.clean_style(
        {"preset": "plain", "card": "#192859", "said": "rgba(218,163,60,.9)", "font": "Outfit"}
    )
    expect(
        "a preset, colours and a face pass",
        got
        == {"preset": "plain", "card": "#192859", "said": "rgba(218,163,60,.9)", "font": "Outfit"},
        got,
    )
    bad = captions.clean_style(
        {"preset": "rm -rf", "ink": "red; x", "card": "url(x)", "font": 'a";b', "x": 1}
    )
    expect("anything else is dropped", bad is None, bad)


async def cases_copies():
    print("copies with captions")
    bare = films.Film.create("an idea", 30, "drawn", client="t")
    os.makedirs(bare.path("outputs"), exist_ok=True)
    expect(
        "a version with no captions.json has none",
        captions.want(bare, "download") == {"state": "none"},
    )
    f = films.Film.create("an idea", 30, "drawn", client="t")
    out = fake_version(f)
    made = []

    def burn(o, kind, style, path):
        made.append((kind, style))
        with open(path, "wb") as fh:
            fh.write(b"burned")

    real, captions.burn = captions.burn, burn
    try:
        first = captions.want(f, "download")
        expect("asked for, it is being made", first["state"] == "preparing", first)
        await asyncio.sleep(0.05)
        again = captions.want(f, "download")
        expect(
            "then it is there, under outputs/captioned/",
            again["state"] == "ready" and again["path"].startswith(os.path.join(out, "captioned")),
            again,
        )
        captions.want(f, "download")
        expect("and asked for again it is not made again", len(made) == 1, made)
        other = captions.want(f, "download", {"preset": "plain"})
        await asyncio.sleep(0.05)
        expect(
            "another look is another copy",
            other["name"] != first["name"] and made[-1] == ("download", {"preset": "plain"}),
            (other, made),
        )
        path = await captions.burned(f, "youtube")
        expect("a send waits for its copy", os.path.isfile(path))
        old = time.time() - (captions.CAPTIONED_DAYS + 1) * 86400
        os.utime(path, (old, old))
        captions.prune(f)
        expect("a copy not asked for in its days is deleted", not os.path.exists(path))
    finally:
        captions.burn = real

    print("YouTube")
    sent = []

    async def send(job, path, to):
        sent.append(path)
        return {"id": "v1"}

    async def burned(film, kind, style=None, version=None):
        return os.path.join(out, "captioned", "film-x.mp4")

    real_send, real_burned = youtube._send, youtube.captioned.burned
    youtube._send, youtube.captioned.burned = send, burned
    with open(os.path.join(out, "captioned", "film-x.mp4"), "wb") as fh:
        fh.write(b"burned!")
    try:
        to = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"
        await youtube.start(f, "t", to, "post-with-captions", captions={"on": True})["task"]
        await youtube.start(f, "t", to, "post-without-cc", captions={"on": False})["task"]
        expect(
            "with captions the copy goes up, without them the film",
            sent == [os.path.join(out, "captioned", "film-x.mp4"), f.path("outputs", "film.mp4")],
            sent,
        )
        expect(
            "and the send says which it was",
            youtube.public(youtube.get("post-with-captions")).get("captions") is True
            and "captions" not in youtube.public(youtube.get("post-without-cc")),
        )
    finally:
        youtube._send, youtube.captioned.burned = real_send, real_burned


def render(f, *args):
    cmd = _env.PY + [
        os.path.join(_env.ROOT, "scripts", "sketch-render.py"),
        "--manifest",
        f.manifest,
    ]
    r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=900, check=False)
    if r.returncode:
        print(r.stdout[-800:], r.stderr[-800:])
    return r.returncode == 0


def band_diff(a, b, box):
    from PIL import Image, ImageChops

    d = ImageChops.difference(
        Image.open(a).convert("RGB").crop(box), Image.open(b).convert("RGB").crop(box)
    )
    hist = d.convert("L").histogram()
    return sum(i * n for i, n in enumerate(hist)) / max(1, sum(hist))


def frame_at(video, t, png):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", png],
        check=True,
    )
    return png


def made_up_video(path, W, H, cut, fps=10, length=6.0):
    """A video busy in the lower third of the frame until `cut`, then in the upper third."""
    import numpy as np

    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray"]
    cmd += ["-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    yy, xx = np.mgrid[0:H, 0:W]
    board = np.where(((xx // 20 + yy // 20) % 2) == 0, 30, 235).astype(np.uint8)
    for i in range(int(length * fps)):
        img = np.full((H, W), 235, np.uint8)
        rows = slice(H * 2 // 3, H) if i / fps < cut else slice(0, H // 3)
        img[rows] = board[rows]
        p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()
    return path


def cases_place():
    print("where each scene's cards go")
    place = __import__("importlib").import_module("_captionplace")
    W, H = 540, 960
    style = {"y": H * 0.745, "top": H * 0.16, "size": W * 0.061, "w": W * 0.74}
    video = made_up_video(os.path.join(HOME, "made-up.mp4"), W, H, cut=3.0)
    card = lambda s, e: {"s": s, "e": e, "words": [{"text": "x", "s": s, "e": e}]}  # noqa: E731
    data = {
        "frame": [W, H],
        "duration": 6.0,
        "style": style,
        "cards": [card(0.5, 1.5), card(1.5, 2.4), card(2.4, 3.1), card(3.5, 5.5)],
    }
    place.place(video, data)
    at = [c.get("at", "bottom") for c in data["cards"]]
    expect(
        "the scene busy low has its cards at the top, the one busy high at the foot",
        at[:2] == ["top", "top"] and at[3] == "bottom",
        at,
    )
    expect("a card across the cut goes with the scene it is most in", at[2] == "top", at)
    sc = data["placed"]["scenes"]
    expect(
        "the video's cut splits it in two, and captions.json says what was measured",
        [r["at"] for r in sc] == ["top", "bottom"]
        and abs(sc[1]["s"] - 3.0) <= 1 / place.FPS
        and sc[0]["detail"][0] > sc[0]["detail"][1],
        sc,
    )
    data["scenes"] = [[0, 2.0], [2.0, 6.0]]
    place.place(video, data)
    got = [r["s"] for r in data["placed"]["scenes"]]
    expect(
        "a film's own scenes split it where the picture does not change",
        got[:2] == [0, 2.0] and len(got) == 3 and abs(got[2] - 3.0) <= 1 / place.FPS,
        got,
    )
    del data["scenes"]
    words = {
        "frames": [{"t": t / 2, "x": [[300, 760, 700, 790, 30, "a label"]]} for t in range(12)]
    }
    place.place(video, data, words)
    at = [c.get("at", "bottom") for c in data["cards"]]
    expect(
        "words the film drew under the foot's band send its cards up, though the top is busy",
        at[3] == "top" and data["placed"]["scenes"][1]["drawn"] == [1, 0],
        (at, data["placed"]["scenes"]),
    )
    head = {
        "frames": [
            {"t": t / 2, "s": [[0, 300, 100, 700, 900, 9, 1, 1, 0, 0, 1, 0, -1]]} for t in range(12)
        ]
    }
    place.place(video, data, head)
    at = [c.get("at", "bottom") for c in data["cards"]]
    expect(
        "a cast member's head under the top's band keeps them at the foot", at[0] == "bottom", at
    )
    expect(
        "with nothing to go on, a scene keeps them at the foot",
        place.choose(0.5, 0, 0, 0, 1) is None,
    )
    expect(
        "words, a head or a face under the foot send them up, unless the top hides one as often",
        place.choose(0, 0, 0.5, 0, 9) == "top" and place.choose(0, 0, 0.5, 0.5, 9) is None,
    )
    expect(
        "on detail alone, only clearly more at the foot and a top all but empty",
        place.choose(0.06, 0.02, 0, 0, 9) is None
        and place.choose(0.3, 0.02, 0, 0, 9) == "top"
        and place.choose(0.3, 0.05, 0, 0, 9) is None,
    )
    again = place.place(video, data)
    expect("placing again starts afresh", again["cards"][3].get("at") is None)


async def cases_rendered():
    print("rendered")
    sys.path.insert(0, os.path.join(_env.ROOT, "scripts"))
    h2i = __import__("importlib").import_module("html-to-image")
    place = __import__("importlib").import_module("_captionplace")
    if not h2i.find_browsers():
        print("  skipped: no browser")
        return
    f = small_film()
    expect("a small tall film in three scenes renders", render(f, "--jobs", "2"))
    out = f.path("outputs")
    p = os.path.join(out, "captions.json")
    expect("with captions.json beside its video", os.path.isfile(p))
    if not os.path.isfile(p):
        return
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    said = " ".join(w["text"] for c in data["cards"] for w in c["words"])
    expect("holding every word, in order", said == WORDS, said)
    expect(
        "and the face its card is set in, beside it",
        any(
            x["family"] == "Inter" and os.path.isfile(os.path.join(out, x["file"]))
            for x in data["fonts"]
        ),
        data.get("fonts"),
    )
    expect("and the film's scenes", [s for s, _ in data["scenes"]] == [0, 2.5, 4.0], data["scenes"])

    def where(a, b):
        return {c.get("at", "bottom") for c in data["cards"] if a <= (c["s"] + c["e"]) / 2 < b}

    expect(
        "the scene drawn low has its cards at the top, the one drawn high at the foot",
        where(0, 2.5) == {"top"} and where(2.5, 4.0) == {"bottom"},
        data["placed"],
    )
    expect(
        "and the one with a label where they would go, at the top",
        where(4.0, 9) == {"top"} and data["placed"]["scenes"][-1]["drawn"][0] == 1,
        data["placed"],
    )
    foot, top = place.band(data), place.band(data, "top")
    for t, up in ((1.0, top), (3.6, foot), (4.6, top)):
        name = "%06.2f" % t
        expect("a still at %g s renders" % t, render(f, "--stills", "%g" % t, "--into", "temp/st"))
        still = f.path("temp", "st", name + ".png")
        clean = frame_at(f.path("outputs", "film.mp4"), t, f.path("temp", "clean%s.png" % name))
        expect(
            "neither it nor the video has a card in it (%g s)" % t,
            band_diff(clean, still, up) < 8
            and band_diff(clean, still, foot if up == top else top) < 8,
            (band_diff(clean, still, up), band_diff(clean, still, top)),
        )
    got = captions.want(f, "download")
    path = await captions.burned(f, "download")
    expect(
        "a copy with captions is burned",
        got["state"] in ("preparing", "ready") and os.path.isfile(path),
    )
    for t, up, down in ((1.0, top, foot), (3.6, foot, top), (4.6, top, foot)):
        name = "%06.2f" % t
        clean = f.path("temp", "clean%s.png" % name)
        burned = frame_at(path, t, f.path("temp", "burned%s.png" % name))
        expect(
            "whose card at %g s is %s, where captions.json says"
            % (t, "at the top" if up == top else "at the foot"),
            band_diff(burned, clean, up) > 20 and band_diff(burned, clean, down) < 4,
            (band_diff(burned, clean, up), band_diff(burned, clean, down)),
        )


async def main():
    _env.utf8_stdio()
    cases_made()
    cases_style()
    await cases_copies()
    cases_place()
    await cases_rendered()
    shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % "; ".join(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    asyncio.run(main())
