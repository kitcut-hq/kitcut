#!/usr/bin/env python
"""Many pictures for a film, packed into the few it may carry, with where each one is.

A kitcut.ai film takes six pictures. A research episode wants twenty: the source
pages, the posts people wrote, the logos. This packs them into sheets -- each
picture cropped (optionally) and scaled to a width, laid in shelves -- and says
where each one landed, so the film's code cuts it back out with one helper:

    SK.part(sheet, [x, y, w, h], cx, cy, width, o)   (written into sheets.md)

Outputs, in the spec's `out`:
    <sheet>.jpg / .png   each sheet: JPEG for screenshots (smaller), PNG when a
                         sheet needs transparency (logos)
    sheets.md            for the prompt: each sheet, each picture's key, its
                         rectangle [x, y, w, h] in the sheet's pixels, its aspect,
                         its caption -- and the helper's code, word for word
    sheets.json          the same, for scripts

A sheet is kept under 4 MB (the site's upload limit is 4.4 MB) by stepping the
JPEG quality down, and under `max_side` pixels on its longest side. Cells sit
`gap` pixels apart on a background that never reads as part of a picture.

`--list` prices it without writing anything: every sheet's size, its cells,
and each picture's scale (a picture shrunk below 0.6 of its own width says so,
since small type in a screenshot stops being readable).

Invoke as:  python scripts/picture-sheets.py --spec projects/<id>/<name>-sheets.json [--list]
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image  # noqa: E402

import _project  # noqa: E402

MAX_BYTES = 4 * 1024 * 1024

HELPER = """// A part of a picture sheet: rect [x, y, w, h] in the sheet's own pixels, drawn centred on cx, cy,
// `width` wide (height keeps the part's aspect). o.alpha fades it.
SK.part = function (name, rect, cx, cy, width, o = {}) {
  const im = SK.IMG[name]; if (!im) return;
  const [x, y, w, h] = rect, H = width * h / w, c = SK.ctx(), a = o.alpha ?? 1;
  if (a <= 0) return;
  const b = c.globalAlpha; c.globalAlpha = b * a;
  c.drawImage(im, x, y, w, h, cx - width / 2, cy - H / 2, width, H);
  c.globalAlpha = b;
};"""


def load_cell(cell, base):
    im = Image.open(_env.resolve(cell["src"], base))
    im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    if cell.get("crop"):
        im = im.crop(tuple(cell["crop"]))
    return im


def pack(sheet, base):
    """Shelf packing: cells left to right at their own width, a new shelf when the row is full."""
    W, gap = sheet.get("width", 2400), sheet.get("gap", 24)
    placed, x, y, shelf = [], gap, gap, 0
    for cell in sheet["cells"]:
        im = load_cell(cell, base)
        w = min(cell.get("w", im.width), W - 2 * gap)
        h = round(im.height * w / im.width)
        if x + w + gap > W and x > gap:
            x, y, shelf = gap, y + shelf + gap, 0
        placed.append((cell, im, [x, y, w, h], w / im.width))
        x += w + gap
        shelf = max(shelf, h)
    return placed, W, y + shelf + gap


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--spec",
        required=True,
        help="sheets: [{name, width, gap, png, cells: [{key, src, crop, w, caption}]}], out",
    )
    ap.add_argument("--list", action="store_true", help="price it: sizes and scales; write nothing")
    ap.add_argument("--workspace", metavar="DIR", help=argparse.SUPPRESS)
    a = ap.parse_args()

    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    base = os.path.dirname(os.path.abspath(a.spec))
    out = _env.resolve(spec.get("out", "sheets"), base)
    max_side = spec.get("max_side", 4096)
    doc, md = [], ["# Picture sheets", ""]
    for sheet in spec["sheets"]:
        placed, W, H = pack(sheet, base)
        name = sheet["name"]
        print("%s: %dx%d, %d pictures" % (name, W, H, len(placed)))
        if max(W, H) > max_side:
            sys.exit(
                "  %s is %dx%d, over max_side %d: fewer cells, or narrower ones"
                % (name, W, H, max_side)
            )
        for cell, _im, r, s in placed:
            warn = "  <- small: type may not read" if s < 0.6 else ""
            print("  %-22s %s scale %.2f%s" % (cell["key"], r, s, warn))
        if a.list:
            continue
        png = sheet.get("png", False)
        canvas = Image.new(
            "RGBA" if png else "RGB", (W, H), (0, 0, 0, 0) if png else sheet.get("bg", "#2a2a2a")
        )
        for cell, im, (x, y, w, h), _s in placed:
            im = im.resize((w, h), Image.LANCZOS)
            if im.mode == "RGBA" and not png:
                bg = Image.new("RGB", im.size, cell.get("bg", "#ffffff"))
                bg.paste(im, mask=im.split()[3])
                im = bg
            canvas.paste(im, (x, y), im if im.mode == "RGBA" else None)
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, name + (".png" if png else ".jpg"))
        if png:
            canvas.save(path, optimize=True)
        else:
            q = 92
            while True:
                canvas.save(path, "JPEG", quality=q, optimize=True)
                if os.path.getsize(path) <= MAX_BYTES or q <= 70:
                    break
                q -= 4
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            sys.exit(
                "  %s is %.1f MB, over the upload limit: smaller cells" % (path, size / 1048576)
            )
        print("  wrote %s (%.1f MB)" % (path, size / 1048576))
        cells = [
            {
                "key": c["key"],
                "rect": r,
                "aspect": round(r[2] / r[3], 3),
                "caption": c.get("caption", ""),
            }
            for c, _im, r, _s in placed
        ]
        doc.append({"sheet": name, "file": os.path.basename(path), "size": [W, H], "cells": cells})
        md += ["## %s (%s, %dx%d)" % (sheet.get("upload", name), os.path.basename(path), W, H), ""]
        md += ["| key | rect [x, y, w, h] | what it is |", "|---|---|---|"]
        md += [
            "| %s | [%d, %d, %d, %d] | %s |" % (c["key"], *c["rect"], c["caption"]) for c in cells
        ]
        md.append("")
    if a.list:
        return
    md += ["## The helper (paste into film.js as it is)", "", "```js", HELPER, "```", ""]
    with open(os.path.join(out, "sheets.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(os.path.join(out, "sheets.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s" % os.path.join(out, "sheets.md"))
    pid = _project.find_project_dir(a.spec)
    if pid:
        _project.record(
            os.path.basename(pid),
            "picture sheets",
            out=os.path.join(out, "sheets.md"),
            script=__file__,
            kind="data",
            manifest=a.spec,
        )


if __name__ == "__main__":
    main()
