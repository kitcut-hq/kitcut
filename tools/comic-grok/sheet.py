#!/usr/bin/env python3
"""Build one contact sheet of a converted comic: a column per page, a thumbnail
per panel, in reading order. Lets you eyeball the whole book at a glance.

Invoke as:
    python -I tools/comic-grok/sheet.py <root_dir> <out.jpg>

<root_dir> holds page-NN/ folders with scene-NN.jpg panels (scene-NN_old.jpg
backups are ignored). Needs Pillow.
"""
import re
import sys
import pathlib

from PIL import Image, ImageDraw, ImageFont

SCENE_RE = re.compile(r"^scene-\d+\.jpg$")
THUMB_W, PAD, LABEL_H = 150, 10, 22
THUMB_H = int(THUMB_W * 16 / 9)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: sheet.py <root_dir> <out.jpg>", file=sys.stderr)
        return 2
    root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    cols = []
    for d in sorted(root.glob("page-*")):
        if not d.is_dir():
            continue
        scenes = sorted(p for p in d.glob("scene-*.jpg") if SCENE_RE.match(p.name))
        if scenes:
            cols.append((d.name, scenes))
    if not cols:
        print("no page-NN/ folders with panels under", root, file=sys.stderr)
        return 1
    maxrows = max(len(s) for _, s in cols)
    w = len(cols) * (THUMB_W + PAD) + PAD
    h = LABEL_H + maxrows * (THUMB_H + PAD) + PAD
    sheet = Image.new("RGB", (w, h), (28, 28, 32))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arialbd.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for ci, (name, scenes) in enumerate(cols):
        x = PAD + ci * (THUMB_W + PAD)
        dr.text((x, 3), name.replace("page-", "p"), fill=(235, 235, 235), font=font)
        for ri, sc in enumerate(scenes):
            y = LABEL_H + ri * (THUMB_H + PAD)
            try:
                sheet.paste(Image.open(sc).convert("RGB").resize((THUMB_W, THUMB_H)), (x, y))
            except OSError:
                dr.rectangle([x, y, x + THUMB_W, y + THUMB_H], outline=(200, 80, 80))
    sheet.save(out, quality=84)
    print("saved", out, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
