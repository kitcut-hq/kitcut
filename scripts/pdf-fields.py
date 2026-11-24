#!/usr/bin/env python
"""A filled fillable PDF as a picture, every filled field tinted blue.

PDF viewers tint form fields blue, so a page whose fields are blue reads at a
glance as "a fillable form, and these are filled" -- with no label, arrow or
box. Amber highlight boxes drawn over the same page read as unclear decoration
(an owner's verdict on a Product Hunt gallery, 2026-11-24). The field rects
come from the PDF's own widgets, never from guessing at the picture.

The tint is multiplied under the page, so the values stay black on it.

  --list    every widget: rect (pt), type, filled or not, value; writes nothing
  (none)    write the PNG

The page is drawn from the PDF at `--width` px, or taken from `--page-png`
when a corrected render of the same page exists (the same frame: its width
sets the scale). `--all` tints the empty fields too (the viewer's look; the
"filled" story wants only the filled ones).

Invoke as:  python scripts/pdf-fields.py --pdf projects/<id>/assets/form.pdf
                --out projects/<id>/temp/form_blue.png [--page-png ...] [--list]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import pymupdf  # noqa: E402
from PIL import Image, ImageChops, ImageDraw  # noqa: E402
import _project  # noqa: E402


def filled(w):
    v = w.field_value
    if w.field_type_string == "CheckBox":
        return v not in (None, "", "Off", False)
    return v not in (None, "") and str(v).strip() != ""


def main():
    ap = argparse.ArgumentParser(description="Tint a PDF's filled form fields blue.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out")
    ap.add_argument("--page", type=int, default=0, help="page index (0-based)")
    ap.add_argument("--page-png", help="a render of the same page to tint instead")
    ap.add_argument("--width", type=int, default=3400, help="render width when no --page-png")
    ap.add_argument("--color", default="#B2C5FF", help="the field tint (Acrobat-like blue)")
    ap.add_argument("--all", action="store_true", help="tint empty fields too")
    ap.add_argument("--list", action="store_true", help="print the widgets; write nothing")
    a = ap.parse_args()
    ws = _env.workspace()
    pdf = _env.resolve(a.pdf, base=ws)
    p = pymupdf.open(pdf)[a.page]
    wid = list(p.widgets())
    if a.list or not a.out:
        for w in wid:
            r = w.rect
            print(
                "  %4.0f %4.0f %4.0f %4.0f  %-8s %s  %s"
                % (
                    r.x0,
                    r.y0,
                    r.x1,
                    r.y1,
                    w.field_type_string,
                    "F" if filled(w) else ".",
                    str(w.field_value)[:40],
                )
            )
        print("  %d widgets, %d filled" % (len(wid), sum(map(filled, wid))))
        return
    if a.page_png:
        page = Image.open(_env.resolve(a.page_png, base=ws)).convert("RGB")
    else:
        z = a.width / p.rect.width
        pm = p.get_pixmap(matrix=pymupdf.Matrix(z, z))
        page = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
    k = page.width / p.rect.width
    c = a.color.lstrip("#")
    blue = tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
    tint = Image.new("RGB", page.size, (255, 255, 255))
    d = ImageDraw.Draw(tint)
    n = 0
    for w in wid:
        if not (a.all or filled(w)):
            continue
        r = w.rect
        d.rectangle([r.x0 * k + 2, r.y0 * k + 2, r.x1 * k - 2, r.y1 * k - 2], fill=blue)
        n += 1
    out = _env.resolve(a.out, base=ws)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ImageChops.multiply(page, tint).save(out)
    print("  %d fields tinted -> %s" % (n, out))
    pd = _project.find_project_dir(out)
    if pd:
        _project.record(
            os.path.basename(pd),
            "pdf fields tinted (%d)" % n,
            out=out,
            script=__file__,
            kind="still",
        )


if __name__ == "__main__":
    main()
