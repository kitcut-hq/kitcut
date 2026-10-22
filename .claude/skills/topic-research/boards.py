"""Lay real screenshots out as a board for a film: crops on paper, a credit line under each.

A board is how a research film shows several sources at once without retyping any of them: the
studio pans and zooms across it one card at a time. Every card is a crop of a captured page; several
slices of one page are stacked with a visible gap, never blended. The captions are ours and name the
outlet and date.

Spec (JSON):
  {"out": "board.jpg", "size": [3840, 2160], "cols": 2,
   "cards": [{"src": "page.png", "crop": [x0, y0, x1, y1], "caption": "Outlet · Oct 21, 2026"},
             {"src": "page.png", "slices": [[0, 0, 2560, 124], [0, 840, 2560, 1470]],
              "caption": "..."},
             {"src": "page.png", "caption": "...", "cell": [x, y, w, h]}]}
  Paths are relative to the spec's folder. "cell" places a card by hand (in board pixels); without
  cells, cards fill a grid of "cols" columns. JPEG at quality 90 keeps a 3840x2160 board well under
  the studio's 4.4 MB a picture.

Invoke as: python -I boards.py <spec.json> [<spec.json> ...]
"""

# ruff: noqa: INP001, T201  (a helper beside a skill, not a package; printing is its output)

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
PAPER, EDGE, SHADOW, SUB = (241, 237, 229), (190, 185, 176), (205, 200, 190), (95, 92, 88)
FONTS = ["C:/Windows/Fonts/seguisb.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(px: int) -> ImageFont.ImageFont:
    """Return the first caption font this machine has."""
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, px)
    return ImageFont.load_default()


def card_image(base: Path, card: dict) -> Image.Image:
    """Return the card's picture: the page, a crop, or slices stacked with a visible gap."""
    page = Image.open(base / card["src"]).convert("RGB")
    if "slices" not in card:
        return page.crop(tuple(card["crop"])) if "crop" in card else page
    parts = [page.crop(tuple(s)) for s in card["slices"]]
    gap = 14
    out = Image.new(
        "RGB",
        (max(p.width for p in parts), sum(p.height for p in parts) + gap * (len(parts) - 1)),
        "white",
    )
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def grid_cells(n: int, cols: int, w: int, h: int, pad: int) -> list[tuple[int, int, int, int]]:
    """Return n cells in a grid of cols columns, with pad between and around them."""
    rows = (n + cols - 1) // cols
    cw, ch = (w - pad * (cols + 1)) // cols, (h - pad * (rows + 1)) // rows
    return [
        (pad + (i % cols) * (cw + pad), pad + (i // cols) * (ch + pad), cw, ch) for i in range(n)
    ]


def build(spec_path: Path) -> None:
    """Render one spec to its board."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base = spec_path.parent
    w, h = spec.get("size", [3840, 2160])
    k = w / 2400
    pad, cap_h = int(70 * k), int(70 * k)
    cards = spec["cards"]
    cells = grid_cells(len(cards), spec.get("cols", len(cards)), w, h, pad)
    board = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(board)
    f = font(int(34 * k))
    for card, auto in zip(cards, cells, strict=True):
        x, y, cw, ch = card.get("cell", auto)
        img = card_image(base, card)
        s = min(cw / img.width, (ch - cap_h) / img.height)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
        x0, y0 = int(x + (cw - img.width) / 2), int(y + (ch - cap_h - img.height) / 2)
        d.rectangle([x0 + 10, y0 + 12, x0 + img.width + 10, y0 + img.height + 12], fill=SHADOW)
        board.paste(img, (x0, y0))
        d.rectangle([x0, y0, x0 + img.width, y0 + img.height], outline=EDGE, width=2)
        d.text((x0, y0 + img.height + int(22 * k)), card.get("caption", ""), font=f, fill=SUB)
    out = base / spec["out"]
    board.save(out, quality=90)
    print(out, board.size, f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        build(Path(p))
