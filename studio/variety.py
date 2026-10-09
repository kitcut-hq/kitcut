#!/usr/bin/env python
"""How alike a set of films is: what they chose, counted, and how far apart their pictures are.

    python studio/variety.py <film folder> <film folder> ...      films pulled to this machine
    python studio/variety.py --project <p-id> [--last 10]         a project's films, where they live
    python studio/variety.py --films <film id> <film id> ...      by id, where they live
        [--sheet covers.jpg]   one frame of each, side by side at thumbnail size: the picture a
                               channel's list of videos shows, which is where sameness is seen
        [--json]               the numbers instead of the table

A project that is a collection (library.is_collection) asks its films to differ; this measures
whether they do, and it measures a series the same way (there, alike is the point). For every
choice a film records (Film.direction: voice, type, ground colours, instruments, tempo, how its
narration opens) it prints how many different values the set has and how much of the set the
commonest one takes. The pictures are compared directly: five frames of each film, shrunk to a
thumbnail, and the mean difference between every two films (0: the same frames, 1: black against
white). Calibrated on the ten AI news Shorts of 2026-10-08, made as a series: see studio/README.md.

Nothing is made and nothing is changed: it reads films and, with --sheet, writes one picture.
"""

import os
import sys
import json
import argparse
import colorsys
import tempfile
import subprocess
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

AT = (0.08, 0.28, 0.5, 0.72, 0.92)  # where in a film its five frames are taken
THUMB = (27, 48)  # a frame shrunk for comparing: what is left is layout and colour
COVER_AT = 1.0  # seconds: the frame a list of videos tends to show


def colour_name(hex_):
    """A ground or accent colour as a rough word, so two near-identical papers count as one:
    'dark', 'light', 'grey' or one of twelve hues."""
    h = (hex_ or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return ""
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if light < 0.2:
        return "dark"
    if light > 0.85:
        return "light"
    if sat < 0.18:
        return "light" if light > 0.75 else "grey"
    names = ("red", "orange", "yellow", "lime", "green", "teal", "cyan", "azure", "blue", "violet", "magenta", "rose")  # fmt: skip
    return names[round(hue * 12) % 12]


def axes(d, length):
    """One film's choices as the values this compares, from its direction and its length."""
    words = d.get("words") or 0
    return {
        "look": d.get("style") or d.get("look") or "",
        "ground": colour_name(d.get("paper")) or d.get("ground") or "",
        "accent": colour_name(d.get("accent")),
        "type": (d.get("faces") or [""])[0],
        "painted as": " ".join((d.get("paint_style") or "").split()[:5]),
        "voice": d.get("voice") or "",
        "instruments": ", ".join(d.get("instruments") or []),
        "tempo": str(round((d.get("bpm") or 0) / 10) * 10) if d.get("bpm") else "",
        "pace": "%.1f w/s" % (words / length) if words and length else "",
        "opens with": " ".join((d.get("opening") or "").split()[:2]).lower(),
    }


def tally(rows):
    """Per axis: {values, distinct, top, share} over the films that have a value for it."""
    out = {}
    for key in rows[0] if rows else ():
        got = [r[key] for r in rows if r[key]]
        if not got:
            continue
        c = Counter(got)
        top, n = c.most_common(1)[0]
        out[key] = {
            "values": dict(c.most_common()),
            "distinct": len(c),
            "top": top,
            "share": round(n / len(got), 2),
            "of": len(got),
        }
    return out


def sameness(t):
    """One number for the set: how much of it the commonest choice takes, averaged over the axes
    (1: every film chose the same everywhere)."""
    return round(sum(a["share"] for a in t.values()) / len(t), 2) if t else None


def frames(video, length):
    """A film's five frames as small pictures, and its cover; [] when it has no video."""
    from PIL import Image

    out, cover = [], None
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate([COVER_AT] + [a * length for a in AT]):
            p = os.path.join(tmp, "%d.png" % i)
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    "%.2f" % t,
                    "-i",
                    video,
                    "-frames:v",
                    "1",
                    p,
                ],
                capture_output=True,
                check=False,
            )
            if r.returncode or not os.path.exists(p):
                return [], None
            with Image.open(p) as im:
                im = im.convert("RGB")
                if i == 0:
                    cover = im.copy()
                else:
                    out.append(im.resize(THUMB, Image.BILINEAR))
    return out, cover


def apart(a, b):
    """How different two films' pictures are, 0..1: the mean difference of their five frames."""
    from PIL import ImageChops, ImageStat

    if not a or not b:
        return None
    d = [sum(ImageStat.Stat(ImageChops.difference(x, y)).mean) / 3 / 255 for x, y in zip(a, b)]
    return sum(d) / len(d)


def video_of(folder):
    for name in ("film_web.mp4", "film.mp4"):
        p = os.path.join(folder, "outputs", name)
        if os.path.exists(p):
            return p
    return None


def read(folder):
    """One film: its title, choices and frames."""
    from film import Film

    f = Film(os.path.abspath(folder))
    rec = f.record()
    d = f.direction() | (rec.get("direction") or {})  # the record wins; older records lack some
    length = rec.get("length") or f.length
    video = video_of(f.dir)
    small, cover = frames(video, length) if video else ([], None)
    title = " ".join((rec.get("title") or rec.get("prompt") or f.id).split())
    return {
        "id": f.id,
        "title": title[:60],
        "axes": axes(d, length),
        "frames": small,
        "cover": cover,
    }


def folders(args):
    if args.folders:
        return args.folders
    from film import Film

    if args.project:
        mine = [
            f
            for f in Film.all()
            if f.state == "done" and (f.record().get("project") or {}).get("id") == args.project
        ]
        return [f.dir for f in mine[: args.last]][::-1]  # Film.all is newest first
    out = []
    for fid in args.films or ():
        f = Film.open(fid)
        if f is None:
            sys.exit("no film %s here" % fid)
        out.append(f.dir)
    return out


def sheet(films, path):
    """Each film's cover in a row at thumbnail size, in the order given."""
    from PIL import Image

    covers = [f["cover"] for f in films if f["cover"]]
    if not covers:
        return None
    h = 320
    cells = [c.resize((round(c.width * h / c.height), h), Image.LANCZOS) for c in covers]
    gap = 8
    out = Image.new(
        "RGB", (sum(c.width for c in cells) + gap * (len(cells) + 1), h + 2 * gap), "#ffffff"
    )
    x = gap
    for c in cells:
        out.paste(c, (x, gap))
        x += c.width + gap
    out.save(path, quality=92)
    return path


def measure(films):
    t = tally([f["axes"] for f in films])
    pairs = []
    for i, a in enumerate(films):
        for b in films[i + 1 :]:
            d = apart(a["frames"], b["frames"])
            if d is not None:
                pairs.append((d, a["title"], b["title"]))
    pairs.sort()
    return {
        "films": len(films),
        "sameness": sameness(t),
        "axes": t,
        "pictures": {
            "mean": round(sum(p[0] for p in pairs) / len(pairs), 3),
            "closest": [round(pairs[0][0], 3), pairs[0][1], pairs[0][2]],
            "furthest": [round(pairs[-1][0], 3), pairs[-1][1], pairs[-1][2]],
        }
        if pairs
        else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folders", nargs="*", help="film folders on this machine")
    ap.add_argument("--project", help="a project's finished films, where they live")
    ap.add_argument("--films", nargs="+", help="film ids, where they live")
    ap.add_argument("--last", type=int, default=10, help="with --project: the newest N (10)")
    ap.add_argument("--sheet", help="write each film's cover side by side to this picture")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    dirs = folders(args)
    if len(dirs) < 2:
        sys.exit("two films or more: folders, --project <p-id> or --films <id> <id> ...")
    films = [read(d) for d in dirs]
    m = measure(films)
    if args.sheet:
        m["sheet"] = sheet(films, args.sheet)
    if args.json:
        print(json.dumps(m, indent=1))
        return
    print(
        "%d films; sameness %.2f (1.00: every film chose the same everywhere)\n"
        % (m["films"], m["sameness"])
    )
    print("%-12s %-9s %s" % ("", "different", "the commonest, and how much of the set it takes"))
    for key, a in m["axes"].items():
        print(
            "%-12s %2d of %-4d %s (%d%%)"
            % (key, a["distinct"], a["of"], a["top"][:44], round(a["share"] * 100))
        )
    p = m["pictures"]
    if p:
        print("\npictures, 0 the same to 1 opposite: mean %.3f between two films" % p["mean"])
        print('  closest  %.3f  "%s" and "%s"' % tuple(p["closest"]))
        print('  furthest %.3f  "%s" and "%s"' % tuple(p["furthest"]))
    if m.get("sheet"):
        print("\ncovers: %s" % m["sheet"])


if __name__ == "__main__":
    main()
