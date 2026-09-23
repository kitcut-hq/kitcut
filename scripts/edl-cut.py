#!/usr/bin/env python
"""Assemble a film from hand-chosen ranges of several silent recordings.

`screen-cut.py` decides what to keep from screen motion, which is right for an
hour of desktop capture nobody wants to watch twice. It is wrong for a handful
of takes that a person has already watched: there the decisions are editorial
("the second download is the better one", "keep two seconds of that hover,
not fifteen") and a motion metric cannot make them -- on bpo-realtor it
labelled the whole two-minute fill "still", because a progress bar moves below
any sensible threshold. So this script takes the decisions as data: an edit
decision list of (source, from, to, speed), in film order, with a `_why` on
every line.

THE ELAPSED COUNTER is the reason it exists. A sped-up wait needs a clock, and
a clock over sped-up footage lies unless it is driven by SOURCE time. Every
film frame is mapped back through the EDL to the source instant it shows, and
the card drawn on that frame reads (source instant - counter start). So the
digits race while the footage runs 10x, crawl at 1x, jump honestly across a
cut inside the counted span, and land on the true total the moment the
footage reaches the end event -- whatever speeds the EDL uses. The card is
drawn by Pillow, one PNG per distinct state, and piped into a short alpha
video that is overlaid in the film's one encode. Each digit sits in a fixed
cell, because Montserrat's figures are proportional and a clock whose digits
shuffle sideways every second reads as broken.

PAINT AND BLUR run in SOURCE time, before the speed change, so a window you
measured on a source frame stays true. `paint` fills a rect with a flat
colour (browser chrome: tab titles and a local file path, erased to the
chrome's own colour); `blur` defocuses one (an on-screen number that
contradicts the counter).

  --list      the EDL with film in/out, the runtime, the counter's film span
              and its final value; encodes nothing
  --frame T   the finished frame at film time T as a PNG, card included --
              the placement check that costs one frame, not one encode
  (none)      render

Invoke as:  python scripts/edl-cut.py --manifest projects/<id>/edit.json --list
"""
import sys
import os
import json
import math
import argparse
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import _encode  # noqa: E402 -- the one place encoder keys are chosen
import _overlay  # noqa: E402
import _progress  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV

DEFAULT_RENDER = {"speed": 5, "cq": 20, "maxrate": "12M", "bufsize": "24M"}
DEFAULT_STYLE = "config/overlays/elapsed-counter.json"


def parse_t(v):
    """Seconds, or 'M:SS.s' / 'H:MM:SS.s' as a human reads a timecode."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def fmt(t):
    t = max(0.0, t)
    return "%d:%04.1f" % (int(t // 60), t % 60)


def clock(t):
    t = int(math.floor(max(0.0, t) + 1e-6))
    return "%d:%02d" % (t // 60, t % 60)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- the plan

def load(mpath):
    m = json.load(open(mpath, encoding="utf-8"))
    cw, ch = m.get("canvas", [1920, 1080])
    fps = float(m.get("fps", 30))
    srcs = {}
    for key, s in (m.get("sources") or {}).items():
        path = _env.resolve(s["path"], base=_env.workspace())
        if not os.path.exists(path):
            sys.exit("source %s: %s does not exist" % (key, s["path"]))
        w, h, sfps, dur = _overlay.probe(path)
        srcs[key] = dict(s, key=key, abspath=path, w=w, h=h, fps=sfps, dur=dur)
    segs = []
    frame = 0
    for i, e in enumerate(m.get("edl") or []):
        if e["src"] not in srcs:
            sys.exit("edl[%d]: unknown source %r" % (i, e["src"]))
        s = srcs[e["src"]]
        a, b = parse_t(e["from"]), parse_t(e["to"])
        sp = float(e.get("speed", 1.0))
        if not (0 <= a < b <= s["dur"] + 1e-3) or sp <= 0:
            sys.exit("edl[%d] %s %s->%s x%s is outside the source (0-%s) or "
                     "has no speed" % (i, e["src"], fmt(a), fmt(b), sp, fmt(s["dur"])))
        # Frame-exact film length: every film offset below is a sum of these,
        # so the counter and the picture cannot drift apart across segments.
        n = int(math.floor((b - a) / sp * fps + 1e-6))
        if n < 1:
            sys.exit("edl[%d] is shorter than one frame at x%s" % (i, sp))
        segs.append({"i": i, "src": s, "from": a, "to": b, "speed": sp,
                     "f0": frame, "n": n, "why": e.get("_why", "")})
        frame += n
    if not segs:
        sys.exit("the manifest has no edl entries")
    return m, srcs, segs, (cw, ch), fps, frame


def seg_at(segs, g):
    for s in segs:
        if s["f0"] <= g < s["f0"] + s["n"]:
            return s
    return None


def src_time(seg, g, fps):
    """The source instant film frame g shows."""
    return seg["from"] + (g - seg["f0"]) / fps * seg["speed"]


# ---------------------------------------------------------------- counter

def counter_plan(spec, segs, fps, total):
    """Per-frame states for one counter: (g, value_s, done, speed) and the span.

    Refuses a counter whose start or end event is not in the film. A card that
    starts but never finishes would freeze mid-count, and one that never
    starts would be a silent no-op -- the same failure a name label past the
    end of a film has.
    """
    key = spec["src"]
    c0, c1 = parse_t(spec["start"]), parse_t(spec["end"])
    g0 = gend = None
    for g in range(total):
        s = seg_at(segs, g)
        if s["src"]["key"] != key:
            continue
        t = src_time(s, g, fps)
        if g0 is None and t >= c0:
            g0 = g
        if g0 is not None and t >= c1:
            gend = g
            break
    if g0 is None:
        sys.exit("counter start %s (%s) is not in the film" % (fmt(c0), key))
    if gend is None:
        sys.exit("counter end %s (%s) is not in the film -- the clock would "
                 "freeze mid-count" % (fmt(c1), key))
    hold = float(spec.get("hold_after", 3.0))
    fade = float(spec.get("fade", 0.3))
    g1 = min(total, gend + int(round((hold + fade) * fps)))
    frames = []
    for g in range(g0, g1):
        s = seg_at(segs, g)
        if g < gend:
            v = src_time(s, g, fps) - c0
            frames.append((g, max(0.0, v), False, s["speed"]))
        else:
            frames.append((g, c1 - c0, True, 1.0))
    # Source seconds of the counted span that the EDL does not show: the
    # clock jumps across them. Honest, but worth saying before an encode.
    shown = 0.0
    for s in segs:
        if s["src"]["key"] == key:
            shown += max(0.0, min(s["to"], c1) - max(s["from"], c0))
    return {"g0": g0, "gend": gend, "g1": g1, "frames": frames,
            "total_s": c1 - c0, "cut_s": max(0.0, (c1 - c0) - shown),
            "fade": fade}


class Card:
    """Draws the elapsed-time card. One instance per render; caches states."""

    def __init__(self, style, spec, canvas_h):
        self.st = style
        self.spec = spec
        k = canvas_h / 1080.0
        self.k = k
        c = style["card"]
        self.w, self.h = int(round(c["w"] * k)), int(round(c["h"] * k))
        f = lambda d: ImageFont.truetype(_overlay.repo_path(d["font"]),  # noqa: E731
                                         max(6, int(round(d["size"] * k))))
        self.f_label = f(style["label"])
        self.f_dig = f(style["digits"])
        self.f_chip = f(style["chip"])
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        # the widest figure sets every digit cell, so nothing moves sideways
        self.cell = max(probe.textlength(d, font=self.f_dig) for d in "0123456789")
        self.colon = probe.textlength(":", font=self.f_dig)
        self.cache = {}

    def draw(self, value, done, speed, alpha, pulse):
        key = (clock(value), done, round(speed, 2), round(alpha, 2), round(pulse, 1))
        if key in self.cache:
            return self.cache[key]
        st, k = self.st, self.k
        c = st["card"]
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, self.w - 1, self.h - 1], radius=int(c["radius"] * k),
                            fill=_overlay.hex_rgba(c["fill"], int(255 * c["alpha"])),
                            outline=_overlay.hex_rgba(c["border"]), width=max(1, int(k)))
        pad = st["pad"] * k
        # label row: a live dot while counting, a check once done
        ly = pad * 0.78
        lab_h = self.f_label.getbbox("H")[3]
        cy = ly + lab_h / 2.0 + 1
        r = 5.5 * k
        if done:
            col = _overlay.hex_rgba(st["done"])
            d.ellipse([pad, cy - r * 1.35, pad + r * 2.7, cy + r * 1.35], fill=col)
            x0, y0 = pad + r * 1.35, cy
            d.line([(x0 - r * 0.7, y0), (x0 - r * 0.15, y0 + r * 0.55),
                    (x0 + r * 0.75, y0 - r * 0.55)], fill=(255, 255, 255, 255),
                   width=max(2, int(2 * k)))
            text = self.spec.get("done_label", "DONE")
            tcol = _overlay.hex_rgba(st["done"])
        else:
            a = int(255 * (0.45 + 0.55 * pulse))
            d.ellipse([pad + r * 0.35, cy - r, pad + r * 2.35, cy + r],
                      fill=_overlay.hex_rgba(st["accent"], a))
            text = self.spec.get("label", "ELAPSED")
            tcol = _overlay.hex_rgba(st["label"]["color"])
        _overlay.draw_text_tracked(d, (pad + r * 2.7 + 9 * k, ly), text.upper(),
                                   self.f_label, tcol, st["label"]["tracking"] * k)
        # the clock, one fixed cell per figure
        txt = clock(value)
        dig_top = self.f_dig.getbbox("0")[1]
        dig_h = self.f_dig.getbbox("0")[3] - dig_top
        base_y = self.h - pad * 0.72 - dig_h - dig_top
        x = pad
        dcol = _overlay.hex_rgba(st["digits"]["color"])
        for chx in txt:
            if chx == ":":
                d.text((x, base_y - 3 * k), ":", font=self.f_dig, fill=dcol)
                x += self.colon + 2 * k
            else:
                wch = d.textlength(chx, font=self.f_dig)
                d.text((x + (self.cell - wch) / 2.0, base_y), chx,
                       font=self.f_dig, fill=dcol)
                x += self.cell
        # the speed chip: why the digits are racing
        if not done and speed > 1.01:
            label = "%g×" % round(speed, 1)
            tw = d.textlength(label, font=self.f_chip)
            th = self.f_chip.getbbox("0")[3] - self.f_chip.getbbox("0")[1]
            tri = th * 0.9
            cw_ = tri * 2 + 6 * k + tw + 22 * k
            chh = th + 16 * k
            cx1 = self.w - pad
            cx0 = cx1 - cw_
            cy1 = base_y + dig_top + dig_h
            cy0 = cy1 - chh
            d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(chh / 2),
                                fill=_overlay.hex_rgba(st["chip"]["fill"]))
            tx = cx0 + 11 * k
            my = (cy0 + cy1) / 2.0
            white = _overlay.hex_rgba(st["chip"]["color"])
            for j in range(2):
                ox = tx + j * tri * 0.85
                d.polygon([(ox, my - tri / 2), (ox + tri * 0.8, my), (ox, my + tri / 2)],
                          fill=white)
            d.text((tx + tri * 1.9 + 6 * k, my - th / 2 - self.f_chip.getbbox("0")[1]),
                   label, font=self.f_chip, fill=white)
        if alpha < 0.999:
            a = img.getchannel("A").point(lambda p: int(p * alpha))
            img.putalpha(a)
        self.cache[key] = img
        return img

    def xy(self, cw, ch):
        mx, my = [v * self.k for v in self.st.get("margin", [40, 20])]
        corner = self.st.get("corner", "bottom-right")
        x = cw - self.w - mx if "right" in corner else mx
        y = ch - self.h - my if "bottom" in corner else my
        return int(round(x)), int(round(y))


def card_frames(cp, card, fps):
    """(g, PIL image) for every film frame the card is on."""
    fade_n = max(1, int(round(cp["fade"] * fps)))
    hz = float(card.st.get("pulse_hz", 1.0))
    out = []
    for idx, (g, v, done, sp) in enumerate(cp["frames"]):
        a = min(1.0, (idx + 1) / fade_n, (len(cp["frames"]) - idx) / fade_n)
        pulse = 0.5 + 0.5 * math.cos(2 * math.pi * hz * (g / fps))
        out.append((g, card.draw(v, done, sp, a, round(pulse * 4) / 4)))
    return out


def write_card_video(frames, card, fps, path):
    """Pipe the card frames into a short PNG-in-MOV clip that keeps alpha."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (card.w, card.h),
           "-r", str(fps), "-i", "-", "-c:v", "png", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=ENV)
    for _, im in frames:
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait():
        sys.exit("could not write the counter clip %s" % path)


# ---------------------------------------------------------------- filters

def rect_px(r, w, h):
    x, y, rw, rh = r
    return (int(round(x * w)), int(round(y * h)),
            max(2, int(round(rw * w))), max(2, int(round(rh * h))))


def window(item, t0, length):
    """`enable` for a source-time window, in the chain's local time (0 = t0)."""
    w = item.get("when")
    if not w:
        return ""
    a, b = parse_t(w[0]) - t0, parse_t(w[1]) - t0
    if b <= 0 or a >= length:
        return None
    return ":enable='between(t\\,%.3f\\,%.3f)'" % (a, b)


def treat(src, t0, length, lab_in, tag):
    """Paint and blur for one source stretch starting at source time t0."""
    parts, cur = [], lab_in
    w, h = src["w"], src["h"]
    for j, p in enumerate(src.get("paint") or []):
        en = window(p, t0, length)
        if en is None:
            continue
        x, y, rw, rh = rect_px(p["rect"], w, h)
        nxt = "%sp%d" % (tag, j)
        parts.append("[%s]drawbox=x=%d:y=%d:w=%d:h=%d:color=0x%s:t=fill%s[%s]"
                     % (cur, x, y, rw, rh, p["color"].lstrip("#"), en, nxt))
        cur = nxt
    for j, b in enumerate(src.get("blur") or []):
        en = window(b, t0, length)
        if en is None:
            continue
        x, y, rw, rh = rect_px(b["rect"], w, h)
        sig = float(b.get("sigma", 6))
        nxt = "%sb%d" % (tag, j)
        parts.append("[%s]split[%sa][%sc]" % (cur, nxt, nxt))
        parts.append("[%sc]crop=%d:%d:%d:%d,gblur=sigma=%.1f[%sk]"
                     % (nxt, rw, rh, x, y, sig, nxt))
        parts.append("[%sa][%sk]overlay=%d:%d%s[%s]" % (nxt, nxt, x, y, en, nxt))
        cur = nxt
    return parts, cur


def fit(cw, ch, bg):
    return ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=0x%s,setsar=1"
            % (cw, ch, cw, ch, bg.lstrip("#")))


def build(segs, canvas, fps, card_clip=None, card_xy=None, card_g0=0):
    cw, ch = canvas
    inputs, parts = [], []
    for k, s in enumerate(segs):
        src = s["src"]
        length = s["to"] - s["from"]
        inputs += ["-ss", "%.3f" % s["from"], "-t", "%.3f" % length,
                   "-i", src["abspath"]]
        tp, cur = treat(src, s["from"], length, "%d:v" % k, "s%d" % k)
        parts += tp
        sp = s["speed"]
        pts = "PTS-STARTPTS" if sp == 1.0 else "(PTS-STARTPTS)/%g" % sp
        parts.append("[%s]setpts=%s,fps=%g,%s,trim=end_frame=%d,setpts=PTS-STARTPTS,"
                     "format=yuv420p[v%d]"
                     % (cur, pts, fps, fit(cw, ch, src.get("bg", "#000000")),
                        s["n"], k))
    parts.append("".join("[v%d]" % k for k in range(len(segs)))
                 + "concat=n=%d:v=1:a=0[film]" % len(segs))
    out = "film"
    if card_clip:
        ci = len(segs)
        inputs += ["-i", card_clip]
        parts.append("[%d:v]format=rgba,setpts=PTS-STARTPTS+%.6f/TB[card]"
                     % (ci, card_g0 / fps))
        parts.append("[film][card]overlay=%d:%d:eof_action=pass:format=auto,"
                     "format=yuv420p[vout]" % card_xy)
        out = "vout"
    return inputs, ";".join(parts), out


# ---------------------------------------------------------------- modes

def show_list(segs, fps, total, cps):
    print("\n  %-3s %-8s %-19s %6s  %-17s %s" % ("#", "source", "source in->out",
                                                "speed", "film in->out", "why"))
    for s in segs:
        a = s["f0"] / fps
        b = (s["f0"] + s["n"]) / fps
        print("  %-3d %-8s %8s->%-9s %5gx  %7s->%-8s %s"
              % (s["i"], s["src"]["key"], fmt(s["from"]), fmt(s["to"]), s["speed"],
                 fmt(a), fmt(b), s["why"][:70]))
    src_in = sum(s["to"] - s["from"] for s in segs)
    print("\n  runtime %s (%d frames at %g fps) from %s of source"
          % (fmt(total / fps), total, fps, fmt(src_in)))
    for spec, cp in cps:
        print("  counter '%s': film %s -> %s, stops at %s (true source interval "
              "%.2f s), holds to %s"
              % (spec.get("label"), fmt(cp["g0"] / fps), fmt(cp["gend"] / fps),
                 clock(cp["total_s"]), cp["total_s"], fmt(cp["g1"] / fps)))
        if cp["cut_s"] > 0.05:
            print("    note: %.1f s of the counted interval is cut; the clock "
                  "jumps across it" % cp["cut_s"])


def one_frame(segs, canvas, fps, t, cards, out_png):
    g = int(round(t * fps))
    s = seg_at(segs, g)
    if s is None:
        sys.exit("film time %s is past the end" % fmt(t))
    st = src_time(s, g, fps)
    tp, cur = treat(s["src"], st, 0.05, "0:v", "f")
    graph = ";".join(tp + ["[%s]%s[o]" % (cur, fit(canvas[0], canvas[1],
                                                   s["src"].get("bg", "#000000")))])
    tmp = out_png + ".base.png"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", "%.3f" % st, "-i", s["src"]["abspath"],
                        "-filter_complex", graph, "-map", "[o]", "-frames:v", "1", tmp],
                       env=ENV, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    im = Image.open(tmp).convert("RGBA")
    os.remove(tmp)
    for card, xy, frames in cards:
        for fg, cim in frames:
            if fg == g:
                im.alpha_composite(cim, xy)
    im.convert("RGB").save(out_png)
    print("  film %s = %s %s (x%g)  ->  %s"
          % (fmt(t), s["src"]["key"], fmt(st), s["speed"], rel(out_png)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the EDL, runtime and counter span; encode nothing")
    ap.add_argument("--frame", action="append", default=[], metavar="M:SS",
                    help="write the finished frame at this FILM time as a PNG; repeatable")
    ap.add_argument("--out", help="override the manifest's output path")
    args = ap.parse_args()

    m, srcs, segs, canvas, fps, total = load(args.manifest)
    mid = m.get("id") or os.path.basename(os.path.dirname(os.path.abspath(args.manifest)))
    style = json.load(open(_env.resolve(m.get("counter_style", DEFAULT_STYLE)),
                           encoding="utf-8"))
    specs = m.get("counters") or []
    if len(specs) > 1:
        sys.exit("one counter per film for now; the overlay chain takes one clip")
    cps = [(sp, counter_plan(sp, segs, fps, total)) for sp in specs]
    tmpdir = os.path.join(_project.projects_dir(), mid, "temp", "edl")
    os.makedirs(tmpdir, exist_ok=True)

    if args.list:
        show_list(segs, fps, total, cps)
        return

    cards = []
    for sp, cp in cps:
        st = dict(style, **{k: sp[k] for k in ("hold_after", "fade") if k in sp})
        card = Card(st, sp, canvas[1])
        cards.append((card, card.xy(*canvas), card_frames(cp, card, fps)))

    if args.frame:
        for t in args.frame:
            tt = parse_t(t)
            one_frame(segs, canvas, fps, tt, cards,
                      os.path.join(tmpdir, "frame-%s.png" % fmt(tt).replace(":", "m")))
        return

    dst = _env.resolve(args.out or m["output"], base=_env.workspace())
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    clip = xy = None
    g0 = 0
    if cards:
        card, xy, frames = cards[0]
        clip = os.path.join(tmpdir, "counter.mov")
        write_card_video(frames, card, fps, clip)
        g0 = cps[0][1]["g0"]
    inputs, graph, out = build(segs, canvas, fps, clip, xy, g0)
    render = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    runtime = total / fps
    tmp = dst + ".part.mp4"
    prog = _progress.begin(mid, runtime, rel(dst))
    cmd = (["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-progress", prog] + inputs
           + ["-filter_complex", graph, "-map", "[%s]" % out, "-an", "-r", "%g" % fps]
           + _encode.video_args(render)
           + ["-movflags", "+faststart", "-y", tmp])
    print("\n  rendering %s  (%s, %d segments, %s)"
          % (rel(dst), fmt(runtime), len(segs), _encode.describe(render)))
    try:
        p = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
    finally:
        _progress.end(mid)
    if p.returncode:
        sys.stderr.write((p.stderr or "")[-4000:])
        sys.exit("ffmpeg failed")
    got = _overlay.probe(tmp)[3]
    if abs(got - runtime) > 2.0 / fps + 0.05:
        sys.exit("output is %.3fs, the EDL predicted %.3fs; %s left in place"
                 % (got, runtime, tmp))
    shutil.move(tmp, dst)
    print("  %s  %s  %.1f MB" % (rel(dst), fmt(got), os.path.getsize(dst) / 1e6))

    burned = ["EDL cut: %d segments from %d sources, %s"
              % (len(segs), len({s["src"]["key"] for s in segs}), fmt(runtime))]
    for s in srcs.values():
        for p_ in s.get("paint") or []:
            burned.append("paint %s %s: %s" % (s["key"], p_["rect"], p_.get("_why", "")))
        for b in s.get("blur") or []:
            burned.append("blur %s %s %s: %s" % (s["key"], b["rect"], b.get("when"),
                                                 b.get("_why", "")))
    for sp, cp in cps:
        burned.append("elapsed counter '%s' film %s-%s, stops at %s (source %s->%s)"
                      % (sp.get("label"), fmt(cp["g0"] / fps), fmt(cp["g1"] / fps),
                         clock(cp["total_s"]), sp["start"], sp["end"]))
    _project.record(_project.project_id(m, args.manifest), "render",
                    out=dst, script=__file__, argv=sys.argv[1:], kind="edl",
                    manifest=args.manifest, burned=burned)


if __name__ == "__main__":
    main()
