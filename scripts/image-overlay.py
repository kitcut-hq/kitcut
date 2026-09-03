#!/usr/bin/env python
"""Burn an image onto a video -- animated, transparent, optionally over a
treated copy of the film. The end-card grammar.

Modelled on the Invest Like the Best end card
(x.com/patrick_oshag/status/1985693514357756286 at 1:26:25), read frame by
frame: the footage keeps playing but desaturates, blurs and dims over about a
second and a half, while the show's logo reveals left to right behind a hard
edge and holds to the end. Two animations, one moment.

The image is either **found or written**. A user hands over a PNG with alpha;
or Claude writes an HTML page and `html-to-image.py` shoots it to a transparent
PNG. By the time it reaches this script the two are the same thing, which is
the point -- nothing below knows or cares which happened.

Where the motion comes from, since it is not obvious:

  * **fade** is a `fade` on the image's alpha -- the name label's idiom exactly.
  * **slide** is a clipped linear expression in `t` for the overlay's x or y.
  * **wipe** is a `geq` that multiplies the image's own alpha by a ramp across
    X (or Y), so the picture is revealed rather than faded. `geq` is a per-pixel
    interpreter and would be expensive left running, so it is gated with
    `enable=` to the wipe window itself -- a second or so, at logo size, not
    frame size. Outside that window the frames pass through untouched.

  * the **background treatment** is a `split`: one branch is left alone, the
    other is desaturated, blurred and dimmed, and then cross-faded over the
    first on its alpha. Fading a constant fully-treated layer over the sharp one
    looks the same as ramping the blur and costs no `sendcmd`. Those filters are
    `enable`-gated too, so a gaussian blur is not run over the whole film to be
    shown for eight seconds of it.

All of which keeps the contract `_overlay.py` describes: Pillow (or a browser)
draws once, ffmpeg animates with expressions in `t`, and `prepare()` hands back
a filter graph the caller splices onto its own chain -- so an end card on a film
is not a re-encode of the film.

Invoke as:  python scripts/image-overlay.py --video in.mp4 --image card.png --at -12
"""
import sys, os, json, argparse, subprocess, shutil, importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402 -- the one place encoder keys are chosen

from PIL import Image
import _overlay
from _overlay import esc, probe, anchor_xy

_html2img = importlib.import_module("html-to-image")   # hyphen: not importable
_makecard = importlib.import_module("make-card")

ENV = _env.ENV
ROOT = _overlay.ROOT

DEFAULT_PRESET = "config/overlays/end-card.json"


# ---------------------------------------------------------------- the image


def _merged(preset, spec, key):
    """A spec's block with the preset's block of the same name underneath."""
    out = {}
    for src, where in ((preset, "preset"), (spec, "overlay entry")):
        block = src.get(key)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise SystemExit("%s: %r should be a block of settings, got %r"
                             % (where, key, block))
        out.update(block)
    return out


SOURCES = ("image", "html", "card")


def source_png(spec, preset, tmpdir, tag, i):
    """The PNG for this overlay, whichever of the three ways it is described.

      image -- a file that already exists
      html  -- a page, shot by the browser
      card  -- a spec, designed into a page by make-card.py and then shot

    Anything generated is cached against the mtime of what it was generated
    FROM, so editing the source re-makes it while a re-render of the film does
    not pay for a browser launch it does not need.
    """
    given = [k for k in SOURCES if spec.get(k)]
    if len(given) != 1:
        raise SystemExit("image overlay %d: give exactly one of %s -- got %s"
                         % (i, "/".join(SOURCES), ", ".join(given) or "none"))

    if spec.get("image"):
        p = _overlay.repo_path(spec["image"])
        if not os.path.exists(p):
            raise SystemExit("no such overlay image: %s" % p)
        return p

    os.makedirs(tmpdir, exist_ok=True)
    # `html_render`, not `html`: on a spec `html` is the page's path, so a
    # preset block of the same name would be merged with a string and explode.
    cfg = _merged(preset, spec, "html_render")

    if spec.get("card"):
        card = _overlay.repo_path(spec["card"])
        if not os.path.exists(card):
            raise SystemExit("no such card spec: %s" % card)
        page = os.path.join(tmpdir, "imgoverlay%s-%d-card.html" % (tag, i))
        if not os.path.exists(page) or \
                os.path.getmtime(page) < os.path.getmtime(card):
            doc = json.load(open(card, encoding="utf-8"))
            with open(page, "w", encoding="utf-8") as f:
                f.write(_makecard.build_html(doc))
            cfg.setdefault("pad_px", int(doc.get("pad_px", 8)))
        src_mtime = os.path.getmtime(card)
    else:
        page = _overlay.repo_path(spec["html"])
        if not os.path.exists(page):
            raise SystemExit("no such overlay page: %s" % page)
        src_mtime = os.path.getmtime(page)

    out = os.path.join(tmpdir, "imgoverlay%s-%d-src.png" % (tag, i))
    if not os.path.exists(out) or os.path.getmtime(out) < src_mtime:
        vp = cfg.get("viewport", [1600, 1000])
        _html2img.render(page, out, viewport=(int(vp[0]), int(vp[1])),
                         scale=float(cfg.get("device_scale", 2)),
                         pad=int(cfg.get("pad_px", 0)))
    return out


def prepare_image(src, layout, vid_w, tmpdir, tag, i):
    """Load, crop to its own ink, and scale to the width the layout asks for."""
    img = Image.open(src).convert("RGBA")

    # Crop to the alpha bbox so corner anchoring and width_frac talk about the
    # artwork rather than about whatever empty margin the file happens to carry.
    box = img.split()[3].getbbox()
    if box and box != (0, 0, img.width, img.height):
        img = img.crop(box)

    want = layout.get("width_frac")
    if want:
        target = int(round(float(want) * vid_w))
        cap = layout.get("max_width_frac")
        if cap:
            target = min(target, int(round(float(cap) * vid_w)))
        if target > 0 and target != img.width:
            if target > img.width * 1.5:
                sys.stderr.write(
                    "  note: overlay %d scaled %.1fx above its native %dpx -- "
                    "it will soften; render the source larger\n"
                    % (i, target / float(img.width), img.width))
            h = max(1, int(round(img.height * target / float(img.width))))
            img = img.resize((target, h), Image.LANCZOS)

    p = os.path.join(tmpdir, "imgoverlay%s-%d.png" % (tag, i))
    img.save(p)
    return p, img.width, img.height


# ---------------------------------------------------------------- the motion


def _progress(at, dur, reverse=False):
    """0->1 across [at, at+dur] in ffmpeg expression form (1->0 if reversed).

    `T` -- the geq spelling of the timestamp -- not `t`; inside geq, `t` is not
    the one you want.
    """
    p = "clip((T-%.3f)/%.3f,0,1)" % (at, max(dur, 1e-3))
    return "(1-%s)" % p if reverse else p


def wipe_alpha(at, dur, direction, feather, out=False):
    """A geq that reveals (or hides) the image behind a moving edge.

    The image's OWN alpha is multiplied by the ramp, so a logo with transparent
    gaps stays transparent -- this reveals the picture, it does not paint a
    rectangle over it. `feather` is the width of the soft leading edge in
    pixels: 1 is the hard edge of the reference, 24 or so suits a photograph.
    """
    axis, span = ("X", "W") if direction in ("left", "right") else ("Y", "H")
    # The edge travels from the named side, so measure the pixel's distance
    # from that side and compare it with how far the edge has swept.
    pos = axis if direction in ("left", "up") else "(%s-1-%s)" % (span, axis)
    f = max(1.0, float(feather))
    swept = "(%s+%.1f)*%s" % (span, f, _progress(at, dur, reverse=out))
    ramp = "clip((%s-%s)/%.1f,0,1)" % (swept, pos, f)
    # r/g/b must be given: geq will not accept an alpha-only expression, and
    # copying them through is what leaves the picture itself untouched.
    return ("geq=a='alpha(X,Y)*%s':r='r(X,Y)':g='g(X,Y)':b='b(X,Y)'"
            ":enable='%s'" % (ramp, esc("between(t,%.3f,%.3f)" % (at, at + dur))))


def slide_xy(x, y, at, dur, direction, vid_w, vid_h, iw, ih, out=False):
    """x/y overlay expressions that travel the image in from one edge."""
    p = _progress(at, dur, reverse=out)
    if direction in ("left", "right"):
        off = -(iw + 20) if direction == "left" else (vid_w + 20)
        return ("%.0f+(%.0f-%.0f)*%s" % (off, x, off, p)), "%d" % y
    off = -(ih + 20) if direction == "up" else (vid_h + 20)
    return "%d" % x, ("%.0f+(%.0f-%.0f)*%s" % (off, y, off, p))


def treatment_chain(base, cfg, at, end, in_s, out_s, tag, i):
    """Desaturate / blur / dim the film under the overlay, ramped in and out.

    Returns (filter_parts, out_label). The treated branch is a real video
    stream, not a looped still, so it needs no `shortest=1`; and every filter in
    it is `enable`-gated to the window because a gaussian blur left running over
    a ten-minute film to be seen for eight seconds is most of the render.
    """
    win = esc("between(t,%.3f,%.3f)" % (max(0.0, at - in_s - 0.5), end + out_s + 0.5))
    keep, treat = "bgk%s%d" % (tag, i), "bgt%s%d" % (tag, i)
    nxt = "bgo%s%d" % (tag, i)

    steps = []
    if float(cfg.get("desaturate", 0)) > 0:
        steps.append("hue=s=%.3f:enable='%s'"
                     % (1.0 - float(cfg["desaturate"]), win))
    if float(cfg.get("blur_sigma", 0)) > 0:
        steps.append("gblur=sigma=%.2f:enable='%s'" % (float(cfg["blur_sigma"]), win))
    if float(cfg.get("dim", 0)) > 0:
        steps.append("eq=brightness=%.3f:enable='%s'" % (-float(cfg["dim"]), win))
    if cfg.get("vignette"):
        steps.append("vignette=enable='%s'" % win)
    if not steps:
        return [], base

    steps.append("format=rgba")
    steps.append("fade=t=in:st=%.3f:d=%.3f:alpha=1" % (at, max(in_s, 1e-3)))
    if out_s > 0:
        steps.append("fade=t=out:st=%.3f:d=%.3f:alpha=1"
                     % (max(at, end - out_s), out_s))

    return ([
        "[%s]split[%s][%s]" % (base, keep, treat),
        "[%s]%s[%s]" % (treat, ",".join(steps), treat + "f"),
        "[%s][%sf]overlay=format=auto:enable='%s'[%s]"
        % (keep, treat, esc("between(t,%.3f,%.3f)" % (at, end + out_s)), nxt),
    ], nxt)


# ---------------------------------------------------------------- prepare


def resolve_window(spec, preset, runtime):
    """(at, dur) in the caller's clock, with the conveniences resolved.

    A negative `at` counts back from the end, which is what an end card wants to
    say -- "twelve seconds before the finish", not a timecode that moves every
    time the cut changes. An omitted `dur` runs to the end for the same reason.
    """
    anim = preset.get("animation", {})
    at = float(spec["at"])
    if at < 0:
        if runtime is None:
            raise SystemExit(
                "image overlay: a negative `at` means 'seconds before the end', "
                "which needs the runtime -- give --dur/--at as absolute times, "
                "or run it from the pipeline where the runtime is known")
        at = max(0.0, runtime + at)
    if spec.get("dur") is not None:
        dur = float(spec["dur"])
    elif runtime is not None:
        dur = max(0.1, runtime - at)          # to the end
    else:
        dur = float(anim.get("hold_s", 8.0))
    return at, dur


def prepare(preset_path, specs, vid_w, vid_h, tmpdir, tag="", base="0:v",
            first_input=1, runtime=None):
    """Render each overlay's PNG and build the graph that animates them.

    Returns (png_paths, filter_complex, out_label). The caller adds each PNG as
    an ffmpeg input -- `-loop 1 -framerate <fps>`, in order, starting at input
    index `first_input` -- and splices the graph onto the tail of its own chain
    via `base`, so the whole film still costs one encode.

    vid_w/vid_h are the dimensions of the frame at THAT point in the chain (the
    output frame, after any crop), not of the source file.
    """
    preset = json.load(open(_overlay.repo_path(preset_path), encoding="utf-8"))
    canvas = preset.get("canvas", {"width": 1920, "height": 1080})
    scale = vid_w / float(canvas["width"])
    sy = vid_h / float(canvas.get("height", 1080))
    anim = preset.get("animation", {})

    os.makedirs(tmpdir, exist_ok=True)
    pngs, parts, cur = [], [], base

    for i, spec in enumerate(specs):
        src = source_png(spec, preset, tmpdir, tag, i)
        layout = _merged(preset, spec, "layout")
        png, iw, ih = prepare_image(src, layout, vid_w, tmpdir, tag, i)
        pngs.append(png)

        x, y = anchor_xy(layout, iw, ih, vid_w, vid_h, scale, sy)
        at, dur = resolve_window(spec, preset, runtime)
        end = at + dur

        a_in = _merged(anim, spec, "in") if isinstance(anim.get("in"), dict) \
            else dict(spec.get("in") or {})
        a_out = _merged(anim, spec, "out") if isinstance(anim.get("out"), dict) \
            else dict(spec.get("out") or {})
        in_t = (a_in.get("type") or "fade").lower()
        out_t = (a_out.get("type") or "fade").lower()
        in_d = float(a_in.get("dur", 0.6))
        out_d = float(a_out.get("dur", 0.6))

        # The film underneath, treated, before the image lands on top of it.
        if spec.get("background") is not None:
            bg = _merged(preset, spec, "background")
            bg_parts, cur = treatment_chain(
                cur, bg, at, end, float(bg.get("in_s", in_d)),
                float(bg.get("out_s", 0.0) if out_t != "none" else 0.0), tag, i)
            parts.extend(bg_parts)

        # The image stream. Its own pts start at zero and advance at the output
        # frame rate, so `st=`/`T` here are the caller's clock -- the same fact
        # the name label relies on.
        steps = ["format=rgba"]
        if in_t == "wipe":
            steps.append(wipe_alpha(at, in_d, a_in.get("direction", "left"),
                                    a_in.get("feather_px", 24)))
        elif in_t == "fade":
            steps.append("fade=t=in:st=%.3f:d=%.3f:alpha=1" % (at, in_d))
        if out_t == "wipe":
            steps.append(wipe_alpha(max(at, end - out_d), out_d,
                                    a_out.get("direction", "left"),
                                    a_out.get("feather_px", 24), out=True))
        elif out_t == "fade":
            steps.append("fade=t=out:st=%.3f:d=%.3f:alpha=1"
                         % (max(at, end - out_d), out_d))

        lbl = "io%s%d" % (tag, i)
        parts.append("[%d:v]%s[%s]" % (first_input + i, ",".join(steps), lbl))

        xe, ye = "%d" % x, "%d" % y
        if in_t == "slide":
            xe, ye = slide_xy(x, y, at, in_d, a_in.get("direction", "left"),
                              vid_w, vid_h, iw, ih)
        if out_t == "slide":
            xe, ye = slide_xy(x, y, max(at, end - out_d), out_d,
                              a_out.get("direction", "left"),
                              vid_w, vid_h, iw, ih, out=True)

        nxt = "iov%s%d" % (tag, i)
        # shortest=1 is not optional: a -loop 1 image input is INFINITE, and
        # without it the overlay waits forever for a second input that never
        # ends -- the render never finishes and the file has no moov atom.
        parts.append("[%s][%s]overlay=x=%s:y=%s:format=auto:shortest=1"
                     ":enable='%s'[%s]"
                     % (cur, lbl, esc(xe), esc(ye),
                        esc("between(t,%.3f,%.3f)" % (at, end)), nxt))
        cur = nxt

    return pngs, ";".join(parts), cur


def describe(spec, preset, runtime=None):
    """One human sentence for --list and for the project file's `burned` list."""
    at, dur = resolve_window(spec, preset, runtime)
    anim = preset.get("animation", {})
    a_in = _merged(anim, spec, "in") if isinstance(anim.get("in"), dict) \
        else dict(spec.get("in") or {})
    src = os.path.basename(spec.get("image") or spec.get("html")
                           or spec.get("card") or "?")
    ends = "to the end" if spec.get("dur") is None and runtime is not None \
        else "for %.1fs" % dur
    s = "image overlay '%s' %s in at %.1fs %s" % (
        src, (a_in.get("type") or "fade"), at, ends)
    if spec.get("background") is not None:
        bg = _merged(preset, spec, "background")
        bits = []
        if float(bg.get("desaturate", 0)) > 0:
            bits.append("B&W")
        if float(bg.get("blur_sigma", 0)) > 0:
            bits.append("blur")
        if float(bg.get("dim", 0)) > 0:
            bits.append("dim")
        s += ", over a %s treatment" % "/".join(bits or ["treated"])
    return s


# ---------------------------------------------------------------- cli


def load_specs(args):
    if args.overlays:
        specs = json.load(open(_overlay.repo_path(args.overlays), encoding="utf-8"))
        if isinstance(specs, dict):
            specs = specs.get("image_overlays") or specs.get("overlays") or []
        return specs
    if not (args.image or args.html or args.card):
        sys.exit("give --image, --html or --card (or --overlays <json>)")
    spec = {"at": args.at}
    for key, val in (("image", args.image), ("html", args.html),
                     ("card", args.card)):
        if val:
            spec[key] = val
    if args.dur is not None:
        spec["dur"] = args.dur
    if args.background:
        spec["background"] = {}
    if args.anim:
        spec["in"] = {"type": args.anim}
    return [spec]


def main():
    ap = argparse.ArgumentParser(
        description="Burn an animated, transparent image overlay into a video.")
    ap.add_argument("--video", help="input video (omit with --png-only)")
    ap.add_argument("--out", help="output video; default <input>-overlay.mp4")
    ap.add_argument("--image", help="a PNG (with alpha) or JPEG to overlay")
    ap.add_argument("--html", help="an HTML page to render and overlay")
    ap.add_argument("--card", help="a card spec to design, render and overlay "
                                   "(see make-card.py --list)")
    ap.add_argument("--at", type=float, default=-12.0,
                    help="when it appears (s); negative counts back from the end")
    ap.add_argument("--dur", type=float,
                    help="how long it stays; default to the end of the film")
    ap.add_argument("--anim", choices=("wipe", "fade", "slide", "none"),
                    help="entrance animation; default comes from the preset")
    ap.add_argument("--background", action="store_true",
                    help="treat the film under it (B&W, blur, dim)")
    ap.add_argument("--overlays", help="JSON list of overlay specs, for several")
    ap.add_argument("--preset", default=DEFAULT_PRESET)
    ap.add_argument("--tmp", default="temp")
    ap.add_argument("--png-only", action="store_true",
                    help="prepare the PNGs and stop, to eyeball the artwork")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="composite onto the frame at T and write a PNG -- "
                         "proves placement without spending an encode")
    ap.add_argument("--clip", action="store_true",
                    help="encode only the overlay windows, not the whole film")
    ap.add_argument("--width", type=int, default=1920, help="with --png-only")
    ap.add_argument("--height", type=int, default=1080, help="with --png-only")
    ap.add_argument("--cq", default="21")
    ap.add_argument("--encoder", default=None,
                    help="default: the best one this machine can run "
                         "(see _encode.py)")
    args = ap.parse_args()

    specs = load_specs(args)
    preset = json.load(open(_overlay.repo_path(args.preset), encoding="utf-8"))

    if args.png_only:
        pngs, _, _ = prepare(args.preset, specs, args.width, args.height,
                             args.tmp, runtime=0.0 if args.at >= 0 else 600.0)
        for p in pngs:
            print("%s  %dx%d" % (p, *Image.open(p).size))
        return

    if not args.video:
        sys.exit("--video is required")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    w, h, fps, dur = probe(args.video)
    for i, s in enumerate(specs):
        at, d = resolve_window(s, preset, dur)
        # An overlay past the end fails SILENTLY -- `enable` simply never turns
        # true and the render succeeds with nothing on it. Say so instead.
        if at >= dur:
            sys.exit("overlay %d starts at %.1fs but the film is %.1fs long"
                     % (i, at, dur))
        print("  %s" % describe(s, preset, dur))

    pngs, fc, out_label = prepare(args.preset, specs, w, h, args.tmp,
                                  runtime=dur)

    # --frame: one composited still, the cheapest proof that the card lands
    # where it should and stays legible over THIS footage.
    if args.frame is not None:
        png = os.path.join(args.tmp, os.path.basename(
            os.path.splitext(args.video)[0]) + "-overlay-%.0fs.png" % args.frame)
        os.makedirs(args.tmp, exist_ok=True)
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin",
               "-ss", "%.3f" % args.frame, "-i", args.video]
        for p in pngs:
            cmd += ["-i", p]
        # The still is grabbed at T, so the image inputs' clocks restart at zero
        # and every fade, wipe and enable would land somewhere else entirely.
        # Composite flat, with the treatment at full strength: this mode answers
        # WHERE and HOW IT READS, not when.
        canvas = preset.get("canvas", {"width": 1920, "height": 1080})
        sx = w / float(canvas["width"])
        sy = h / float(canvas.get("height", 1080))
        parts, cur = [], "0:v"
        for i, p in enumerate(pngs):
            spec = specs[i]
            if spec.get("background") is not None:
                bg = _merged(preset, spec, "background")
                steps = []
                if float(bg.get("desaturate", 0)) > 0:
                    steps.append("hue=s=%.3f" % (1.0 - float(bg["desaturate"])))
                if float(bg.get("blur_sigma", 0)) > 0:
                    steps.append("gblur=sigma=%.2f" % float(bg["blur_sigma"]))
                if float(bg.get("dim", 0)) > 0:
                    steps.append("eq=brightness=%.3f" % -float(bg["dim"]))
                if bg.get("vignette"):
                    steps.append("vignette")
                if steps:
                    parts.append("[%s]%s[bg%d]" % (cur, ",".join(steps), i))
                    cur = "bg%d" % i
            im = Image.open(p)
            layout = _merged(preset, spec, "layout")
            x, y = anchor_xy(layout, im.width, im.height, w, h, sx, sy)
            parts.append("[%d:v]format=rgba[q%d]" % (i + 1, i))
            parts.append("[%s][q%d]overlay=x=%d:y=%d[o%d]" % (cur, i, x, y, i))
            cur = "o%d" % i
        cmd += ["-filter_complex", ";".join(parts), "-map", "[%s]" % cur,
                "-frames:v", "1", "-y", png]
        if subprocess.run(cmd, env=ENV).returncode:
            sys.exit("ffmpeg failed building the preview frame")
        print(png)
        return

    out = args.out or os.path.splitext(args.video)[0] + "-overlay.mp4"
    trim = []
    if args.clip:
        wins = [resolve_window(s, preset, dur) for s in specs]
        a = max(0.0, min(x[0] for x in wins) - 1.5)
        b = min(dur, max(x[0] + x[1] for x in wins) + 1.5)
        # -ss AFTER -i so the input keeps its original timeline and every
        # expression still means what it says; seeking first would rebase t.
        trim = ["-ss", "%.3f" % a, "-to", "%.3f" % b]
        out = os.path.splitext(out)[0] + "-clip.mp4"

    # One place decides the encoder keys; these preview burns get the
    # same treatment as a pipeline render.
    rcfg = _encode.resolve({"encoder": args.encoder, "cq": args.cq,
                            "speed": 5, "maxrate": "16M",
                            "bufsize": "32M"})
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-i", args.video]
    for p in pngs:
        cmd += ["-loop", "1", "-framerate", "%g" % fps, "-i", p]
    cmd += ["-filter_complex", fc, "-map", "[%s]" % out_label, "-map", "0:a:0?"]
    cmd += trim
    cmd += (_encode.video_args(rcfg) + ["-r", "%g" % fps]
            + _encode.audio_args(rcfg)
            + ["-movflags", "+faststart", "-y", out])
    if subprocess.run(cmd, env=ENV).returncode:
        sys.exit("ffmpeg failed for %s" % out)

    got = probe(out)[3]
    want = (b - a) if args.clip else dur
    if abs(got - want) > 0.5:
        sys.exit("output is %.2fs, expected %.2fs -- %s left in place"
                 % (got, want, out))
    print("%s  %.1fs  %.1f MB" % (out, got, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
