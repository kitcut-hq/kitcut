# Reference copy from projects/instafill-ph-launch/ (2026-11-24), as it shipped.
# Paths are relative to that project folder; copy into projects/<id>/ and adapt.
"""Product Hunt gallery (2026-11-24: Mister Blocks copy, 2-6 words; white logo, no white chip; url instafill.ai in mono; also written at 1270x760) (texts follow the email's line, "an AI agent that fills your forms"; Eugene: no photo talk in them) for the Instafill launch: five 2540x1520 images (PH's
1270x760 at 2x, as Mister Blocks shipped) and a 240x240 thumbnail, in the
site's own type and colours (Inter, ink #1A1A1A, accent #F5A623), every
picture a real frame of the product or the filled form.

  1-hero    the promise + the phone with the filled form
  2-steps   four steps, Mister Blocks' 2x2 grammar
  3-before  the paper letter -> the filled ACORD 25
  4-detail  the coverage block close up, highlighted
  5-agent   the prompt with the attached phone photo

Invoke: python projects/instafill-ph-launch/ph_gallery.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
import _env  # noqa: E402,F401
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

D = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(D, "../.."))
T = os.path.join(D, "temp/ph")
OUT = os.path.join(D, "outputs/ph")
os.makedirs(OUT, exist_ok=True)
W, H = 2540, 1520
INK, ACC, WHITE = (26, 26, 26), (245, 166, 35), (255, 255, 255)


def font(size, var="ExtraBold"):
    f = ImageFont.truetype(os.path.join(R, "fonts/Inter-VF.ttf"), size)
    f.set_variation_by_name(var)
    return f


def backdrop():
    bg = Image.open(os.path.join(D, "temp/review/desk_bg.png")).convert("RGB")
    # cover, not fit: the 16:9 desk scaled to 2540 wide is only 1429 tall, and
    # the old crop to 1520 padded black bands top and bottom (Eugene)
    s = max(W / bg.width, H / bg.height)
    bw, bh = round(bg.width * s), round(bg.height * s)
    bg = bg.resize((bw // 4, bh // 4)).filter(ImageFilter.GaussianBlur(10)).resize((bw, bh))
    x, y = (bw - W) // 2, (bh - H) // 2
    bg = bg.crop((x, y, x + W, y + H))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (12, 12, 14)), 0.58)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-500, -400, W + 500, H + 400], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(260))
    return Image.composite(bg, Image.new("RGB", (W, H), (6, 6, 8)), vig).convert("RGBA")


def shadow(im, box, r, blur=40, alpha=0.6, dy=26):
    x0, y0, x1, y1 = box
    pad = blur * 3
    s = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle([pad, pad, pad + x1 - x0, pad + y1 - y0], r, fill=(0, 0, 0, int(255 * alpha)))
    im.alpha_composite(s.filter(ImageFilter.GaussianBlur(blur)), (x0 - pad, y0 - pad + dy))


def paste_round(im, pic, xy, r):
    m = Image.new("L", pic.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, pic.size[0] - 1, pic.size[1] - 1], r, fill=255)
    im.paste(pic, xy, m)


def phone(im, screen_png, x, y, h):
    scr = Image.open(os.path.join(T, screen_png)).convert("RGB")
    w = round(h * scr.width / scr.height)
    bez = round(h * 0.014)
    box = (x - bez, y - bez, x + w + bez, y + h + bez)
    shadow(im, box, round(h * 0.068), 46, 0.65)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, round(h * 0.068), fill=(14, 14, 16, 255))
    d.rounded_rectangle([box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3], round(h * 0.066), outline=(60, 60, 66, 255), width=3)
    paste_round(im, scr.resize((w, h), Image.LANCZOS), (x, y), round(h * 0.053))
    return w


def card(im, pic, box, r=40, border=None):
    x0, y0, x1, y1 = box
    shadow(im, box, r)
    p = pic.convert("RGB").resize((x1 - x0, y1 - y0), Image.LANCZOS)
    paste_round(im, p, (x0, y0), r)
    if border:
        ImageDraw.Draw(im).rounded_rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], r + 4, outline=border, width=8)


def words(d, xy, parts, f, anchor="la", line_gap=1.12, max_w=None):
    """parts: list of lines; each line a list of (text, colour)."""
    x, y = xy
    for line in parts:
        lw = sum(d.textlength(t, font=f) for t, _ in line)
        cx = x - lw / 2 if anchor == "ma" else x
        for t, c in line:
            d.text((cx, y), t, font=f, fill=c)
            cx += d.textlength(t, font=f)
        y += f.size * line_gap
    return y


def kicker(d, x, y, text, anchor="l"):
    f = font(34, "Bold")
    t = " ".join(text)
    tw = d.textlength(t, font=f)
    pw, ph = tw + 90, 62
    if anchor == "m":
        x -= pw / 2
    d.rounded_rectangle([x, y, x + pw, y + ph], 14, fill=INK + (255,))
    d.rectangle([x + 24, y + ph / 2 - 6, x + 54, y + ph / 2 + 6], fill=ACC)
    d.text((x + 70, y + ph / 2), t, font=f, fill=ACC, anchor="lm")


def url_pill(d, x, y):
    f = ImageFont.truetype(os.path.join(R, "fonts/IBMPlexMono-Bold.ttf"), 46)
    t = "instafill.ai"
    tw = d.textlength(t, font=f)
    d.rounded_rectangle([x + 8, y + 8, x + tw + 78, y + 86], 14, fill=(0, 0, 0, 255))
    d.rounded_rectangle([x, y, x + tw + 70, y + 78], 14, fill=ACC)
    d.text((x + 35, y + 39), t, font=f, fill=INK, anchor="lm")


def logo(im, x, y, w):
    lg = Image.open(os.path.join(R, "projects/agent-batch-filling/assets/instafill-logo-trim.png")).convert("RGBA")
    px = lg.load()  # the wordmark is dark ink: turn it white, keep the square icon
    for yy in range(lg.height):
        for xx in range(lg.height + 10, lg.width):
            r, g, b, a = px[xx, yy]
            if a and max(r, g, b) < 140:
                px[xx, yy] = (255, 255, 255, a)
    lg = lg.resize((w, round(lg.height * w / lg.width)), Image.LANCZOS)
    im.alpha_composite(lg, (x, y))


def save(im, name):
    p = os.path.join(OUT, name)
    im.convert("RGB").save(p, quality=95)
    os.makedirs(os.path.join(OUT, "1270x760"), exist_ok=True)
    im.convert("RGB").resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(OUT, "1270x760", name), quality=95)
    print(p)


# 1 hero ----------------------------------------------------------------------
im = backdrop()
d = ImageDraw.Draw(im)
logo(im, 170, 170, 520)
kicker(d, 170, 400, "INSTAFILL AGENT")
y = words(d, (170, 500), [[("An AI agent that", WHITE)], [("fills your ", WHITE), ("forms.", ACC)]], font(118))
words(d, (170, y + 30), [[("Snap a photo.", (225, 225, 228))],
                         [("Ask for the form.", (225, 225, 228))],
                         [("Get it filled.", (225, 225, 228))]], font(56, "Medium"), line_gap=1.3)
url_pill(d, 170, 1250)
# the real viewer frame (temp/c16a/phone.mp4 @ 28.2, 45% full page) with the
# blue-field page (blue_page.py) laid in the viewer's own page box (tour.json
# start: x 56, y 562+1, scale 0.285). Eugene: no orange boxes on the hero.
scr = Image.open(os.path.join(T, "ph_viewer.png")).convert("RGB")
bp = Image.open(os.path.join(T, "acord25_blue.png")).convert("RGB")
bp = bp.resize((round(bp.width * 0.285), round(bp.height * 0.285)), Image.LANCZOS)
scr.paste(bp, (56, 563))
scr.save(os.path.join(T, "ph_blue.png"))
phone(im, "ph_blue.png", 1660, 110, 1300)
save(im, "1-hero.png")

# 2 steps grid ------------------------------------------------------------------
im = backdrop()
d = ImageDraw.Draw(im)
words(d, (W / 2, 70), [[("Four steps. ", WHITE), ("One sentence.", ACC)]], font(92), anchor="ma")
tw, th = 1080, 560


def fit(pic, bg, top=40, side=60):
    """Whole UI block, uncropped, centred on the app's own background (Eugene:
    no prompt cut mid-word, no half message)."""
    s = min((tw - 2 * side) / pic.width, (th - top - 130) / pic.height)
    pic = pic.resize((round(pic.width * s), round(pic.height * s)), Image.LANCZOS)
    t = Image.new("RGB", (tw, th), bg)
    t.paste(pic, ((tw - pic.width) // 2, top))
    return t


# 1 the whole letter on the desk; 2 the full prompt, clean (screen_clean @ 58.5);
# 3 the agent's closing message + Open PDF / Download (screen_clean @ 115);
# 4 the coverage block with the filled fields in blue (blue_page.py)
snap = Image.open(os.path.join(T, "desk_letter.png")).convert("RGB").crop((0, 40, 1920, 1035))
typ = fit(Image.open(os.path.join(T, "ph_typ_full.png")).convert("RGB").crop((40, 432, 1040, 1038)), (247, 248, 251))
work = fit(Image.open(os.path.join(T, "ph_done.png")).convert("RGB").crop((40, 1054, 1040, 1764)), (247, 248, 251), top=24)
kb = 3400 / 612
tour = Image.open(os.path.join(T, "acord25_blue.png")).convert("RGB").crop(
    (round(206 * kb), round(291 * kb), round(596 * kb), round(493 * kb)))
tiles = [(snap, "1", "Snap the letter"), (typ, "2", "Ask for the form"),
         (work, "3", "It fills it"), (tour, "4", "Check every field")]
for i, (pic, n, cap) in enumerate(tiles):
    cx = 180 + (i % 2) * (tw + 100)
    cy = 250 + (i // 2) * (th + 100)
    pw = pic.width / pic.height
    crop = pic
    if abs(pw - tw / th) > 0.01:  # centre-crop to the tile
        if pw > tw / th:
            nw = round(pic.height * tw / th)
            crop = pic.crop(((pic.width - nw) // 2, 0, (pic.width + nw) // 2, pic.height))
        else:
            nh = round(pic.width * th / tw)
            crop = pic.crop((0, (pic.height - nh) // 2, pic.width, (pic.height + nh) // 2))
    card(im, crop, (cx, cy, cx + tw, cy + th), 36)
    f = font(46)
    lw = d.textlength(cap, font=f)
    d.rounded_rectangle([cx + 24, cy + th - 104, cx + 24 + 96 + lw + 40, cy + th - 24], 22, fill=INK + (240,))
    d.rounded_rectangle([cx + 40, cy + th - 92, cx + 96, cy + th - 36], 14, fill=ACC)
    d.text((cx + 68, cy + th - 64), n, font=font(40), fill=INK, anchor="mm")
    d.text((cx + 116, cy + th - 64), cap, font=f, fill=WHITE, anchor="lm")
save(im, "2-steps.png")

# 3 before -> after -------------------------------------------------------------
# Two whole pages, straight and the same size: the GC's letter (the very PDF
# that was printed and photographed) and the filled ACORD 25. Eugene: the
# tilted photo was cut off and soft.
im = backdrop()
d = ImageDraw.Draw(im)
words(d, (W / 2, 70), [[("From this letter ", WHITE), ("→ to this form.", ACC)]], font(92), anchor="ma")
ph_ = 1130
pw_ = round(ph_ * 8.5 / 11)
gap = 330
x_l = (W - 2 * pw_ - gap) // 2
x_r = x_l + pw_ + gap
y_p = 230
def letter_hi():
    """The letter drawn from its PDF at 3400 px wide (letter_page.png is 1700)."""
    import pymupdf
    p = pymupdf.open(os.path.join(D, "assets/docs/brandmoor_coi_request.pdf"))[0]
    pm = p.get_pixmap(matrix=pymupdf.Matrix(3400 / p.rect.width, 3400 / p.rect.width))
    out = os.path.join(T, "letter_page_hi.png")
    Image.frombytes("RGB", (pm.width, pm.height), pm.samples).save(out)
    return out


for x, src, label in ((x_l, letter_hi(), "The letter"),
                      (x_r, os.path.join(D, "assets/acord25_filled.png"), "The filled ACORD 25")):
    # Eugene: soft when zoomed. Downscale from 3400 px, then a light unsharp
    # mask so 8-pt type keeps an edge at 874 px wide
    pg = Image.open(src).convert("RGB").resize((pw_, ph_), Image.LANCZOS)
    pg = pg.filter(ImageFilter.UnsharpMask(radius=1.0, percent=90, threshold=2))
    card(im, pg, (x, y_p, x + pw_, y_p + ph_), 14)
    f = font(42, "Bold")
    tw = d.textlength(label, font=f)
    d.rounded_rectangle([x + pw_ / 2 - tw / 2 - 30, y_p + ph_ + 40, x + pw_ / 2 + tw / 2 + 30, y_p + ph_ + 112], 36, fill=INK + (255,))
    d.text((x + pw_ / 2, y_p + ph_ + 76), label, font=f, fill=ACC, anchor="mm")
ax0, ax1, ay = x_l + pw_ + 70, x_r - 70, y_p + ph_ // 2
d.line([(ax0, ay), (ax1 - 50, ay)], fill=ACC, width=24)
d.polygon([(ax1, ay), (ax1 - 80, ay - 56), (ax1 - 80, ay + 56)], fill=ACC)
save(im, "3-before-after.png")

# 4 sources -----------------------------------------------------------------------
# Eugene (2026-11-24, 4A): where every value came from. The three real inputs
# on the left, the filled ACORD 25 (fields in blue, blue_page.py) on the right;
# each input is joined to the band of the form it filled. Field rows are the
# PDF's own widget rects (pt): declarations -> producer, insured, insurer A and
# the CGL/auto/umbrella rows (120-480); workers' comp -> insurer B and the WC
# row (480-530; insurer B sits at 180, named in the text); the letter ->
# description of operations and certificate holder (570-745).
import pymupdf  # noqa: E402

im = backdrop()
d = ImageDraw.Draw(im)
kicker(d, 170, 110, "CHECK IT")
words(d, (170, 205), [[("Every field.", WHITE)], [("From your ", WHITE), ("files.", ACC)]], font(96))

PGH = 1240
ps = PGH / 792
PGW = round(612 * ps)
px0, py0 = W - 150 - PGW, (H - PGH) // 2
blue = Image.open(os.path.join(T, "acord25_blue.png")).convert("RGB").resize((PGW, PGH), Image.LANCZOS)
blue = blue.filter(ImageFilter.UnsharpMask(radius=1.0, percent=90, threshold=2))
card(im, blue, (px0, py0, px0 + PGW, py0 + PGH), 14)


def pdf_thumb(name, w, h):
    p = pymupdf.open(os.path.join(D, "assets/docs", name))[0]
    z = 2 * w / p.rect.width
    pm = p.get_pixmap(matrix=pymupdf.Matrix(z, z))
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples).resize((w, h), Image.LANCZOS)


TW, TH = 216, 280
photo = Image.open(os.path.join(T, "desk_letter.png")).convert("RGB").crop((585, 60, 1365, 1070)).resize((TW, TH), Image.LANCZOS)
rows = [  # top to bottom in the order of the form, so no line crosses another
    (pdf_thumb("kessler_lowe_declarations.pdf", TW, TH), "DECLARATIONS", "kessler_lowe_declarations.pdf",
     ["Producer, insured, insurer A,", "3 policies and their limits"], (120, 480)),
    (pdf_thumb("kessler_lowe_workers_comp.pdf", TW, TH), "WORKERS' COMP", "kessler_lowe_workers_comp.pdf",
     ["Insurer B, the WC policy", "and its limits"], (482, 530)),
    (photo, "THE LETTER, A PHONE PHOTO", "20261123_151140.jpg",
     ["Certificate holder and", "description of operations"], (572, 745)),
]
fm = ImageFont.truetype(os.path.join(R, "fonts/IBMPlexMono-Bold.ttf"), 34)
fk = font(28, "Bold")
fd = font(40, "Medium")
bx = px0 - 34  # the brackets, just left of the page
lx0 = 1220     # where the lines leave the text column
y = 520
for pic, kick, fname, desc, (a, b) in rows:
    card(im, pic, (170, y, 170 + TW, y + TH), 12)
    tx = 170 + TW + 44
    d = ImageDraw.Draw(im)
    d.text((tx, y + 18), " ".join(kick), font=fk, fill=ACC)
    d.text((tx, y + 66), fname, font=fm, fill=WHITE)
    for i, line in enumerate(desc):
        d.text((tx, y + 128 + i * 52), line, font=fd, fill=(205, 205, 210))
    # bracket over the band of the form this input filled
    ya, yb = py0 + a * ps, py0 + b * ps
    d.rounded_rectangle([bx - 4, ya, bx + 4, yb], 4, fill=ACC)
    d.line([(bx - 4, ya + 2), (bx + 16, ya + 2)], fill=ACC, width=6)
    d.line([(bx - 4, yb - 2), (bx + 16, yb - 2)], fill=ACC, width=6)
    # a soft S-curve from the text column to the bracket's middle
    y1, y2 = y + TH / 2, (ya + yb) / 2
    x1, x2 = lx0, bx - 14
    pts = []
    for k_ in range(41):
        u = k_ / 40
        e = u * u * (3 - 2 * u)
        pts.append((x1 + (x2 - x1) * u, y1 + (y2 - y1) * e))
    d.line(pts, fill=ACC, width=6, joint="curve")
    d.ellipse([x1 - 11, y1 - 11, x1 + 11, y1 + 11], fill=ACC)
    y += TH + 40
save(im, "4-sources.png")

# 5 call to action -------------------------------------------------------------
# Eugene (5A): the gallery ends the way the videos do: the promise, the address.
im = backdrop()
d = ImageDraw.Draw(im)
lg_w = 760
logo(im, (W - lg_w) // 2, 310, lg_w)
f = font(132)
y = 620
d.text((W / 2, y), "An AI agent that", font=f, fill=WHITE, anchor="mm")
y += 160
l2 = "fills your forms."
d.text((W / 2, y), l2, font=f, fill=ACC, anchor="mm")
x0 = W / 2 - d.textlength(l2, font=f) / 2
uy = y + 80
d.rounded_rectangle([x0, uy, x0 + d.textlength(l2[:-1], font=f), uy + 12], 5, fill=ACC)
d.text((W / 2, uy + 120), "ACORD 25  ·  W-9  ·  any PDF, fillable or flat", font=font(54, "Medium"),
       fill=(215, 215, 220), anchor="mm")
fu = ImageFont.truetype(os.path.join(R, "fonts/IBMPlexMono-Bold.ttf"), 62)
uw = d.textlength("instafill.ai", font=fu) + 100
py = uy + 240
d.rounded_rectangle([W / 2 - uw / 2 + 10, py + 10, W / 2 + uw / 2 + 10, py + 110], 16, fill=(0, 0, 0, 255))
d.rounded_rectangle([W / 2 - uw / 2, py, W / 2 + uw / 2, py + 100], 16, fill=ACC)
d.text((W / 2, py + 50), "instafill.ai", font=fu, fill=INK, anchor="mm")
save(im, "5-cta.png")

# thumbnail 240x240 ---------------------------------------------------------------
og = Image.open(os.path.join(D, "temp/site/og.png")).convert("RGB")
sq = og.crop((300, 0, 930, 630)).resize((240, 240), Image.LANCZOS)
sq.save(os.path.join(OUT, "thumbnail-240.png"))
print(os.path.join(OUT, "thumbnail-240.png"))
