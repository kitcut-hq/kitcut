#!/usr/bin/env python
"""Four YouTube thumbnail options for a sketch film: posters composed from the film's own
pictures (its cut-outs, its photographs) when it has any, else stills of the film itself.

The same machinery kitcut.ai's "Publish to YouTube" runs (studio/thumbs.py), from the command
line: for trying concepts by hand, for the bake-off that set the thresholds in
config/thumbnails/thumbnails.json, and for looking at what a film would be offered.

  --film DIR        a finished film's folder (its sketch.json, film.js, voice timeline)
  --concepts FILE   four {"at", "words", "layout"} as JSON (a list, or {"thumbnails": [...]});
                    layout is one each of headline, card, panel, still; one word may be
                    *starred* for the film's accent colour. A film with pictures gets posters
                    whatever the layout: "hero" and "with" (a list of one) name the pictures a
                    poster is built on, else it takes the pieces of its moment's frame
  --auto            no concepts: the picture alone at 25/50/75% of the film -- about what
                    YouTube offers when it picks for itself (the baseline)
  --moments         only the labelled sheet of moments a writer chooses from
  --title TEXT      the video's title (words that repeat it are refused)
  --ocr             also read the words back with OCR at each feed width (slower)
  --list            print the moments, the settled frames, the layouts and every check;
                    writes stills and working files to the film's temp/ only
  (default)         also write thumb-N.jpg, sheet.jpg (the options side by side) and
                    feed.jpg (the options at YouTube's feed sizes, dark and light) to --out

Invoke as:  python scripts/thumb-options.py --film <film dir> --concepts c.json --title "..."
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _thumb  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--film", required=True, help="a finished film's folder")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--concepts", help="JSON: four {at, words, layout}")
    g.add_argument("--auto", action="store_true", help="the picture alone at 25/50/75%%")
    g.add_argument("--moments", action="store_true", help="only the sheet of moments")
    ap.add_argument("--title", default="", help="the video's title")
    ap.add_argument("--channel", default="Your channel", help="channel name on feed.jpg")
    ap.add_argument("--out", help="where the options go (default <film>/temp/thumbs/options)")
    ap.add_argument("--ocr", action="store_true", help="read the words back at feed widths")
    ap.add_argument(
        "--logo",
        choices=("config", "all", "none"),
        default="config",
        help="which options carry the film's logo (config: logo.options)",
    )
    ap.add_argument("--list", action="store_true", help="print everything; write no options")
    ap.add_argument(
        "--looks",
        nargs="?",
        const="all",
        help="the look round: every cover recipe (or the ones named, comma-separated) for each "
        "concept, on one sheet (looks.jpg) -- what a person picks from before any is offered",
    )
    a = ap.parse_args()

    film = os.path.abspath(a.film)
    if not os.path.exists(os.path.join(film, "sketch.json")):
        sys.exit("no sketch.json in %s" % film)
    length = _thumb.film_length(film)
    lines = _thumb.narration(film)
    moments = _thumb.moment_times(lines, length)
    print("  film %s: %.1f s, %d narration lines" % (os.path.basename(film), length, len(lines)))
    print("  moments: %s" % ", ".join("%.1f" % t for t in moments))
    out = a.out or os.path.join(film, "temp", "thumbs", "options")

    if a.moments:
        stills = _thumb.render_stills(film, moments)
        p = _thumb.moments_sheet(stills, os.path.join(out, "moments.jpg"))
        print("  %s" % p)
        return

    if a.auto:
        concepts = _thumb.auto_concepts(length)
    else:
        if not a.concepts:
            sys.exit("give --concepts, --auto or --moments")
        with open(a.concepts, encoding="utf-8") as f:
            raw = json.load(f)
        raw = raw.get("thumbnails") if isinstance(raw, dict) else raw
        concepts, notes, problems = _thumb.check_concepts(raw, length, a.title)
        for n in notes:
            print("  note: %s" % n)
        for p in problems:
            print("  PROBLEM: %s" % p["text"])
        concepts = _thumb.fill_concepts(concepts, moments, length)

    if a.looks:
        recipes = _thumb.COVERS if a.looks == "all" else tuple(a.looks.split(","))
        looks = _thumb.make_looks(
            film, concepts, out, recipes, logo="none" if a.logo == "none" else "all"
        )
        for x in looks:
            print(
                "  %-7s %d  caps %3d-%3d px  %s on %s (%.2fx)  %s%s"
                % (
                    x["recipe"],
                    x["n"],
                    x["cap"],
                    x["cap_max"],
                    x["subject"]["kind"],
                    x["subject"]["name"] or "the frame",
                    x["subject"]["zoom"],
                    json.dumps(x["checks"], ensure_ascii=False),
                    ("  FAILS: " + "; ".join(x["fails"])) if x["fails"] else "",
                )
            )
        print("  %s" % _thumb.looks_sheet(looks, os.path.join(out, "looks.jpg"), recipes=recipes))
        return

    opts = _thumb.make_options(film, concepts, out, logo=a.logo)
    for o in opts:
        ck = dict(o["checks"])
        ck.pop("ink_box", None)
        if a.ocr and o["words"]:
            ck["ocr"] = _thumb.ocr_recall(o["final"], o["words"])
        print(
            "  %d  %-8s at %6.2f -> %6.2f  %-24r %s"
            % (o["n"], o["layout"], o["at"], o["t"], o["words"], json.dumps(ck, ensure_ascii=False))
        )
        for n in o["notes"]:
            print("       %s" % n)
    if a.list:
        return
    labels = [
        "%d  %s  %.1f s  %s" % (o["n"], o["layout"], o["t"], _thumb.plain(o["words"])) for o in opts
    ]
    sheet = _thumb.contact_sheet([o["final"] for o in opts], labels, os.path.join(out, "sheet.jpg"))
    feed = _thumb.feed_sheet(
        [o["final"] for o in opts],
        a.title or "Your video's title",
        a.channel,
        os.path.join(out, "feed.jpg"),
        duration="%d:%02d" % divmod(round(length), 60),
    )
    for o in opts:
        print("  %s" % o["file"])
    print("  %s\n  %s" % (sheet, feed))


if __name__ == "__main__":
    main()
