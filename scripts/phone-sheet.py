#!/usr/bin/env python
"""A phone on the left of a 16:9 frame; the document flies out of its screen.

The 16:9 cut of a phone demo has an empty right half. A magnifier card there
(the phone's UI again, bigger, joined by a beam) read as two objects side by
side showing the same thing -- an owner turned it down. What earned the space:

  - while the work happens, the real screen recording in a phone body on the
    left, over the blurred desk, and the right half left to big step captions
    (edl-cut burns those in, step-captions.py draws them);
  - when the filled document opens, at `sheet_from` the page grows out of the
    phone's screen (from the screen's centre, ease-out cubic, `fly` seconds)
    into a large sheet on the right, which page-tour.py tours with its
    highlights. The phone stays, showing the same page in the real viewer.

No frames, beams or leader lines: a soft shadow is the only decoration.

Spec (example: config/launch-kit/phone-sheet.json; paths beside the spec):

    {"bg": "temp/desk_bg.png",            # a still of the desk, blurred here
     "phone": "temp/phone.mp4",           # the screen track, 1080x2400
     "phone_size": [1080, 2400],
     "sheet": "temp/sheet.mp4",           # page-tour.py output, card-sized
     "phone_box": [210, 66, 948],         # screen x, y, height on the canvas
     "card": [700, 40, 1160, 850],        # sheet x, y, w, h
     "sheet_from": 28.3, "fly": 0.7, "dur": 44.7, "out": "temp/middle.mp4"}

  --plan       the section's length and when the sheet flies; renders nothing
  --still T    one frame at section time T as a PNG beside the spec
  (none)       the section as MP4 (edl-cut takes it as a source)

Invoke as:  python scripts/phone-sheet.py --spec projects/<id>/phone-sheet.json [--plan | --still T]
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
import _encode  # noqa: E402
import _project  # noqa: E402

W, H, FPS = 1920, 1080, 30


def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def shadow(size, r, blur, alpha):
    pad = blur * 3
    s = Image.new("RGBA", (size[0] + 2 * pad, size[1] + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle(
        [pad, pad, pad + size[0], pad + size[1]], r, fill=(0, 0, 0, int(255 * alpha))
    )
    return s.filter(ImageFilter.GaussianBlur(blur)), pad


def ease(u):
    u = max(0.0, min(1.0, u))
    return 1 - (1 - u) ** 3  # ease-out cubic: leaves the phone fast, settles softly


class Section:
    def __init__(self, sp):
        self.sp = sp
        self.dir = os.path.dirname(sp)
        with open(sp, encoding="utf-8") as f:
            self.S = json.load(f)
        S = self.S
        self.ps = tuple(S.get("phone_size", [1080, 2400]))
        self.PH = S["phone_box"]
        self.PW = round(self.PH[2] * self.ps[0] / self.ps[1])
        self.CX, self.CY, self.CW, self.CH = S["card"]
        self.T0, self.FLY = S["sheet_from"], S["fly"]
        bg0 = Image.open(self.path(S["bg"])).convert("RGB")
        bgs = (
            bg0.resize((W // 4, H // 4))
            .filter(ImageFilter.GaussianBlur(9))
            .resize((W + 120, H + 68))
        )
        bgs = Image.blend(bgs, Image.new("RGB", bgs.size, (12, 12, 14)), 0.55)
        vig = Image.new("L", bgs.size, 0)
        ImageDraw.Draw(vig).ellipse([-300, -250, bgs.size[0] + 300, bgs.size[1] + 250], fill=255)
        vig = vig.filter(ImageFilter.GaussianBlur(160))
        self.bgs = Image.composite(bgs, Image.new("RGB", bgs.size, (6, 6, 8)), vig)
        self.bez = 13
        self.body = (self.PW + 2 * self.bez, self.PH[2] + 2 * self.bez)
        self.ph_shadow, self.ph_pad = shadow(self.body, 64, 26, 0.6)
        self.scr_mask = rounded_mask((self.PW, self.PH[2]), 50)

    def path(self, p):
        return _env.resolve(p, base=self.dir)

    def frame(self, t, phone, sheet):
        PH, PW, bez, body = self.PH, self.PW, self.bez, self.body
        dx = int(60 * t / self.S["dur"])  # the desk drifts: a still would read as a slide
        out = self.bgs.crop((dx, 34, dx + W, 34 + H)).convert("RGBA")
        x, y = PH[0] - bez, PH[1] - bez
        out.alpha_composite(self.ph_shadow, (x - self.ph_pad, y - self.ph_pad + 16))
        d = ImageDraw.Draw(out)
        d.rounded_rectangle([x, y, x + body[0], y + body[1]], 64, fill=(14, 14, 16, 255))
        d.rounded_rectangle(
            [x + 2, y + 2, x + body[0] - 2, y + body[1] - 2], 62, outline=(58, 58, 64, 255), width=2
        )
        out.paste(phone.resize((PW, PH[2]), Image.LANCZOS), (PH[0], PH[1]), self.scr_mask)
        if sheet is not None and t >= self.T0:
            u = ease((t - self.T0) / self.FLY)
            s0 = PH[2] * 0.62 / self.CH  # starts the size of the page on the phone
            sc = s0 + (1 - s0) * u
            w, h = max(2, round(self.CW * sc)), max(2, round(self.CH * sc))
            cx0, cy0 = PH[0] + PW / 2, PH[1] + PH[2] / 2
            cx1, cy1 = self.CX + self.CW / 2, self.CY + self.CH / 2
            mx, my = cx0 + (cx1 - cx0) * u, cy0 + (cy1 - cy0) * u
            x0, y0 = round(mx - w / 2), round(my - h / 2)
            r = max(6, round(22 * sc))
            sh, pad = shadow((w, h), r, max(8, round(34 * sc)), 0.55 * min(1.0, 0.3 + u))
            out.alpha_composite(sh, (x0 - pad, y0 - pad + round(20 * sc)))
            pic = sheet.resize((w, h), Image.LANCZOS) if (w, h) != sheet.size else sheet
            mask = rounded_mask((w, h), r)
            if u < 1:
                mask = mask.point(lambda v: int(v * min(1.0, 0.15 + 1.6 * u)))
            out.paste(pic, (x0, y0), mask)
        return out.convert("RGB")


def reader(path, size, frame=None):
    """Every frame as an RGB image; with `frame`, only that one (no broken pipe)."""
    sel = [] if frame is None else ["-vf", "select=eq(n\\,%d)" % frame, "-frames:v", "1"]
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", path, *sel, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
        env=_env.ENV,
    )
    n = size[0] * size[1] * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            return
        yield Image.frombytes("RGB", size, b)


def main():
    ap = argparse.ArgumentParser(description="Phone left, the page flies out into a sheet.")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--plan", action="store_true", help="print the timing; render nothing")
    ap.add_argument("--still", type=float, help="write the frame at section time T")
    a = ap.parse_args()
    sec = Section(_env.resolve(a.spec, base=_env.workspace()))
    S = sec.S
    if a.plan:
        print(
            "  section %.2fs; sheet flies %.2f-%.2fs into %s"
            % (S["dur"], sec.T0, sec.T0 + sec.FLY, S["card"])
        )
        return
    csize = (sec.CW, sec.CH)
    if a.still is not None:
        t = a.still
        ph = next(reader(sec.path(S["phone"]), sec.ps, round(t * FPS)))
        sh = None
        if t >= sec.T0:
            sh = next(reader(sec.path(S["sheet"]), csize, round((t - sec.T0) * FPS)))
        out = os.path.splitext(sec.sp)[0] + "-%05.2f.png" % t
        sec.frame(t, ph, sh).save(out)
        print(out)
        return
    out = sec.path(S["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = (
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24"]
        + ["-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-"]
        + _encode.video_args(_encode.resolve({"cq": 16}))
        + [out]
    )
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=_env.ENV)
    sheets = reader(sec.path(S["sheet"]), csize)
    last, i = None, 0
    for ph in reader(sec.path(S["phone"]), sec.ps):
        t = i / FPS
        if t >= sec.T0:
            last = next(sheets, last)
        enc.stdin.write(sec.frame(t, ph, last).tobytes())
        i += 1
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("ffmpeg failed")
    print("  %s  %d frames" % (out, i))
    pd = _project.find_project_dir(out)
    if pd:
        _project.record(
            os.path.basename(pd),
            "phone-sheet section (%d frames)" % i,
            out=out,
            script=__file__,
            kind="section",
        )


if __name__ == "__main__":
    main()
