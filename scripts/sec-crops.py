#!/usr/bin/env python
"""Cut passages out of an SEC filing (an S-1, a 10-Q) as sharp pictures for a film.

A research film shows its evidence, and the strongest evidence is the filing's own page: the
income statement as printed, the paragraph that says "50.1% of the total voting power". Two things
stand in the way, and this script gets round both:

  * EDGAR refuses headless browsers ("Undeclared Automated Tool"), so the filing is downloaded
    with curl-style urllib and a declared user agent (`--ua "<org> research <contact>"`, which
    the SEC asks for) and rendered from the local file.
  * Workiva-built filings (most large S-1s) are laid out with absolute positioning: every printed
    page is one `<div ... height:792pt>` and every line is a `<div ... top:Xpt>`. Cropping by
    element returns slivers. So the page that holds the passage is cut out of the 14 MB file on
    its own, shot whole at 3x, and cropped by the `top:` of its first and last lines (and the
    `left:`/`width:` of their runs), which the HTML states exactly.

A crop is `name=start words|end words`: the first line containing the start words, through the
first line at or below it containing the end words. Words must sit on one printed line (a line
break in the filing breaks a match); tables work, because lines are matched in top-to-bottom
order, not in the order the HTML lists them.

    --list      the free mode: for each crop, the page it is on and the lines it would take,
                without rendering anything; --find "words" lists every page holding them

The pictures go to --out as <name>.png. They are evidence for a film, not a deliverable, so nothing
is recorded in a project file.

Invoke as:  python scripts/sec-crops.py --htm projects/<id>/research/s1.htm --list
                --crop "votes=Immediately prior to the completion|economic rights"
            python scripts/sec-crops.py --url <the filing's sec.gov .htm>
                --ua "Acme research ops@example.com" --save projects/<id>/research/s1.htm
                --out projects/<id>/logos/src/<n>
                --crop "income=Consolidated Statements of Operations Data|Net loss"
"""

import argparse
import html
import importlib
import os
import re
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image  # noqa: E402

_h2i = importlib.import_module("html-to-image")  # hyphen: not importable by name

PAGE_MARK = '<div style="--justify:justify;'  # how Workiva opens each printed page
PT = 4 / 3  # CSS px per pt
SCALE = 3  # device pixels per CSS px: small print stays sharp when a film zooms in
PAGE_PX = (816, 1056)  # a US Letter page, 612 x 792 pt


def plain(s):
    """Text of an HTML fragment, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def pages_of(raw):
    """Cut the filing into its printed pages (each one renders alone)."""
    parts = raw.split(PAGE_MARK)
    if len(parts) < 3:
        sys.exit(
            "no absolutely-positioned pages found: this filing is not Workiva-style, so crop it "
            "by element with a browser instead (the screenshots skill)"
        )
    pages = [PAGE_MARK + p for p in parts[1:]]
    pages[-1] = pages[-1].split("</body>")[0]
    return pages


class _Lines(HTMLParser):
    """Every positioned block's text at its position on the page.

    A table is a positioned block whose rows are positioned inside it, so a row's own `top:` is
    relative to the table: positions are summed down the open elements, never read alone.
    """

    VOID = {"br", "img", "hr", "meta", "link", "input", "col", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [(0.0, 0.0, None)]  # (top, left, line) of each open element
        self.lines = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        top, left, line = self.stack[-1]
        style = dict(attrs).get("style") or ""
        t = re.search(r"(?:^|;)\s*top:\s*([-\d.]+)pt", style)
        lf = re.search(r"(?:^|;)\s*left:\s*([-\d.]+)pt", style)
        w = re.search(r"(?:^|;)\s*width:\s*([\d.]+)pt", style)
        top += float(t.group(1)) if t else 0.0
        left += float(lf.group(1)) if lf else 0.0
        if tag == "div" and t:
            line = {"top": top, "text": [], "runs": []}
            self.lines.append(line)
        if tag == "font" and line is not None and lf and w:
            line["runs"].append((left, left + float(w.group(1))))
        self.stack.append((top, left, line))

    def handle_endtag(self, tag):
        if tag not in self.VOID and len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        line = self.stack[-1][2]
        if line is not None:
            line["text"].append(data)


def lines_of(page):
    """[(top_pt, text, [(left_pt, right_pt), ...])], top to bottom."""
    p = _Lines()
    p.feed(page)
    out = []
    for ln in p.lines:
        t = re.sub(r"\s+", " ", "".join(ln["text"])).strip()
        if t:
            out.append((ln["top"], t, ln["runs"]))
    return sorted(out, key=lambda x: x[0])


def locate(pages, start, end):
    """(page index, the lines from start through end) or None."""
    for pi, pg in enumerate(pages):
        if start[:30] not in plain(pg):
            continue
        ls = lines_of(pg)
        si = next((i for i, (_, t, _) in enumerate(ls) if start in t), None)
        if si is None:
            continue
        ei = next((i for i in range(si, len(ls)) if end in ls[i][1]), None)
        if ei is not None:
            below = ls[ei + 1][0] if ei + 1 < len(ls) else None
            return pi, ls[si : ei + 1], below
    return None


def box(lines, below=None):
    """Return the crop in device pixels: the lines' own extent, a little air round it.

    A line's `top:` is where its box starts and its glyphs hang about 9pt below that, so the
    bottom edge is 11pt under the last line -- unless the next line starts sooner, whose
    capitals would then show as a sliver along the edge.
    """
    top, bot = lines[0][0], lines[-1][0]
    bottom = bot + 11 if below is None else min(bot + 11, below + 1.5)
    runs = [r for _, _, rs in lines for r in rs]
    left = min((a for a, _ in runs), default=18.0)
    right = max((b for _, b in runs), default=594.0)
    k = PT * SCALE
    w, h = PAGE_PX[0] * SCALE, PAGE_PX[1] * SCALE
    return (
        max(0, int((left - 8) * k)),
        max(0, int((top - 2) * k)),
        min(w, int((right + 8) * k)),
        min(h, int(bottom * k)),
    )


def fetch(url, ua, save):
    """Download the filing as a declared tool, as the SEC asks."""
    if not ua or "@" not in ua:
        sys.exit('--ua must name who is asking, with a contact address: "<org> research <email>"')
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if save:
        os.makedirs(os.path.dirname(os.path.abspath(save)) or ".", exist_ok=True)
        with open(save, "wb") as f:
            f.write(data)
    return data.decode("utf-8", errors="ignore")


def main():
    """Parse, locate every crop, then render the pages that hold them."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--htm", help="the filing, downloaded already")
    src.add_argument("--url", help="the filing on sec.gov (needs --ua)")
    ap.add_argument("--ua", help='declared user agent for sec.gov: "<org> research <email>"')
    ap.add_argument("--save", help="with --url: keep the downloaded filing here")
    ap.add_argument(
        "--crop", action="append", default=[], help='"name=start words|end words"; repeatable'
    )
    ap.add_argument("--find", help="list the pages that hold these words, and stop")
    ap.add_argument("--out", help="folder for <name>.png")
    ap.add_argument("--list", action="store_true", help="say what each crop takes; render nothing")
    a = ap.parse_args()

    raw = (
        fetch(a.url, a.ua, a.save)
        if a.url
        else Path(_env.resolve(a.htm)).read_text(encoding="utf-8", errors="ignore")
    )
    pages = pages_of(raw)
    print("%d printed pages" % len(pages))

    if a.find:
        for pi, pg in enumerate(pages):
            for top, t, _ in lines_of(pg):
                if a.find in t:
                    print("  page %3d  top %6.1fpt  %s" % (pi + 1, top, t[:110]))
        return

    crops = []
    for spec in a.crop:
        name, _, rest = spec.partition("=")
        start, _, end = rest.partition("|")
        if not (name and start and end):
            sys.exit('a crop is "name=start words|end words": %r' % spec)
        hit = locate(pages, start, end)
        if not hit:
            sys.exit(
                "%s: no page has a line with %r followed by one with %r (words must sit on one "
                "printed line; try --find)" % (name, start, end)
            )
        pi, ls, below = hit
        crops.append((name, pi, ls, below))
        print(
            "%-12s page %3d, %d lines, top %.1f-%.1fpt"
            % (name, pi + 1, len(ls), ls[0][0], ls[-1][0])
        )
        if a.list:
            for top, t, _ in ls:
                print("    %6.1f  %s" % (top, t[:110]))
    if a.list or not crops:
        return
    if not a.out:
        sys.exit("--out is needed to render")

    out = _env.resolve(a.out, base=_env.workspace())
    os.makedirs(out, exist_ok=True)
    browser = (_h2i.find_browsers() or [None])[0]
    if not browser:
        sys.exit("no Edge or Chrome found (python scripts/html-to-image.py --check)")
    with tempfile.TemporaryDirectory(prefix="sec-crops-") as tmp:
        shots = {}
        for name, pi, ls, below in crops:
            if pi not in shots:
                page = os.path.join(tmp, "page-%d.html" % (pi + 1))
                with open(page, "w", encoding="utf-8") as f:
                    f.write(
                        '<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#fff}'
                        "body>div{margin:0!important;border:0!important}</style>" + pages[pi]
                    )
                png = page[:-5] + ".png"
                _h2i.shoot(page, png, browser, viewport=PAGE_PX, scale=SCALE)
                shots[pi] = Image.open(png).convert("RGB")
            dest = os.path.join(out, name + ".png")
            pic = shots[pi].crop(box(ls, below))
            pic.save(dest)
            print("  %s  %dx%d" % (dest, pic.width, pic.height))


if __name__ == "__main__":
    main()
