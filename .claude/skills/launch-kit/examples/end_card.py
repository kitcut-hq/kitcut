# Reference copy from projects/instafill-ph-launch/ (2026-11-24), as it shipped.
# Paths are relative to that project folder; copy into projects/<id>/ and adapt.
"""End card in the Mister Blocks grammar (2026-11-24): no white panel. The
frame itself turns into Instafill's ink with a soft amber glow, the logo
with its wordmark in white, a two-line tagline whose accent phrase is amber
and underlined, and the address as a plain amber pill ("instafill.ai", no
https). Writes temp/caps6/end.png (9:16) and temp/caps6/end16.png (16:9).
Invoke: python projects/instafill-ph-launch/end_card.py"""

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(D, "../.."))
OUT = os.path.join(D, "temp/caps6")
os.makedirs(OUT, exist_ok=True)
INK, AMBER, WHITE = (26, 26, 26), (245, 166, 35), (255, 255, 255)
LOGO = os.path.join(R, "projects/agent-batch-filling/assets/instafill-logo-trim.png")


def font(path, size, var=None):
    f = ImageFont.truetype(os.path.join(R, path), size)
    if var:
        f.set_variation_by_name(var)
    return f


def light_logo(width):
    """The logo with its dark wordmark turned white; the square icon is kept."""
    lg = Image.open(LOGO).convert("RGBA")
    icon_w = lg.height + 10  # the icon is the square at the left
    px = lg.load()
    for y in range(lg.height):
        for x in range(icon_w, lg.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) < 140:
                px[x, y] = (255, 255, 255, a)
    return lg.resize((width, int(lg.height * width / lg.width)), Image.LANCZOS)


def card(W, H, logo_w, size, top):
    im = Image.new("RGBA", (W, H), INK + (255,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    rx, ry = W * 0.55, H * 0.32
    gd.ellipse([W / 2 - rx, H / 2 - ry, W / 2 + rx, H / 2 + ry], fill=AMBER + (34,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(W / 6)))
    d = ImageDraw.Draw(im)
    lg = light_logo(logo_w)
    im.alpha_composite(lg, ((W - lg.width) // 2, top))
    f = font("fonts/Inter-VF.ttf", size, "ExtraBold")
    y = top + lg.height + int(size * 1.3)
    l1, l2 = "An AI agent that", "fills your forms."
    d.text((W / 2, y), l1, font=f, fill=WHITE, anchor="mm")
    y += int(size * 1.22)
    d.text((W / 2, y), l2, font=f, fill=AMBER, anchor="mm")
    tw = d.textlength(l2[:-1], font=f)  # underline the words, not the full stop
    x0 = W / 2 - d.textlength(l2, font=f) / 2
    uy = y + size * 0.58
    d.rounded_rectangle([x0, uy, x0 + tw, uy + max(4, size // 11)], 3, fill=AMBER)
    fu = font("fonts/IBMPlexMono-Bold.ttf", int(size * 0.62))
    url = "instafill.ai"
    uw, uh = d.textlength(url, font=fu) + size * 0.9, size * 1.15
    py = uy + size * 1.0
    o = max(5, size // 9)
    d.rounded_rectangle([W / 2 - uw / 2 + o, py + o, W / 2 + uw / 2 + o, py + uh + o], 12, fill=(0, 0, 0))
    d.rounded_rectangle([W / 2 - uw / 2, py, W / 2 + uw / 2, py + uh], 12, fill=AMBER)
    d.text((W / 2, py + uh / 2), url, font=fu, fill=INK, anchor="mm")
    return im


card(1080, 1920, 760, 66, 700).save(os.path.join(OUT, "end.png"))
card(1920, 1080, 820, 64, 300).save(os.path.join(OUT, "end16.png"))
print("end cards ->", OUT)
