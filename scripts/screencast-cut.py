#!/usr/bin/env python
"""Cut a two-camera screencast down to what is worth watching, in one pass.

The material this is built for: a screen recording with NO audio, plus a phone
take that carries the narration and runs longer at both ends. sync-tracks.py has
already measured the offset; this decides what to keep and renders it.

The camera is the master clock, not the screen. It is the stream that has the
sound, and it is the one that covers the whole shoot -- the screen recorder was
started after the talking began and stopped before it ended. So the film is laid
out in camera time and falls into three acts:

  intro   camera rolling, no screen yet   -> camera fills the frame
  core    both rolling                    -> screen, with the camera as a square
  outro   camera still rolling, no screen -> camera fills the frame

Cutting rule: a pause is dropped only where the speaker is silent AND the screen
is not doing anything. Silence alone is the wrong test on a screencast, because
a long wait while output streams is the one silence the viewer needs. On this
shoot 89% of the screen is a frozen frame, so the freeze mask is what stops the
cut from being driven by the speaker's breathing alone.

  --plan   write config/screencast/<id>.cuts.json, a keep-list you can edit
  --list   print the timeline and the runtime, encode nothing
  (none)   render

Invoke as:  python scripts/screencast-cut.py --manifest config/screencast/<id>.json
"""
import sys, os, json, argparse, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_outline = import_module("transcript-outline")
_namelabel = import_module("name-label")   # hyphen: not importable by name
_imgoverlay = import_module("image-overlay")
import _progress  # noqa: E402
import _project  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_RENDER = {"encoder": "h264_nvenc", "preset": "p5", "cq": 21,
                  "maxrate": "16M", "bufsize": "32M", "audio_bitrate": "192k"}
DEFAULT_CUT = {"min_silence": 1.5, "air": 0.4, "silence_db": -34,
               "freeze_db": -60, "require_frozen": True, "min_drop": 0.5}
DEFAULT_PIP = {"corner": "bottom-left", "size_px": 360, "margin_px": 48,
               "crop_x": 0.5, "crop_y": 0.5, "border_px": 3,
               "border_colour": "#F2F2F2", "corner_radius_px": 0}
DEFAULT_CANVAS = {"width": 1920, "height": 1080, "fit": "pad",
                  "background": "#000000", "fps": 30}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path]).stdout
    return float(out.strip())


def detect_spans(cmd, start_key, dur_key):
    """Parse a detector filter's start/duration metadata into [(a, b), ...]."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    spans, cur = [], None
    for line in (p.stderr or "").splitlines():
        if start_key in line:
            try:
                cur = float(line.split(start_key)[1].split()[0])
            except (IndexError, ValueError):
                cur = None
        elif dur_key in line and cur is not None:
            try:
                spans.append((cur, cur + float(line.split(dur_key)[1].split()[0])))
            except (IndexError, ValueError):
                pass
            cur = None
    return spans


def silent_spans(audio, db, min_dur):
    """Where the speaker is not talking, in camera time."""
    return detect_spans(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", audio, "-vn",
         "-af", "silencedetect=noise=%ddB:d=%.3f" % (db, min_dur),
         "-f", "null", "-"],
        "silence_start:", "silence_duration:")


def frozen_spans(video, db, min_dur=0.5):
    """Where the screen is not moving, in screen time."""
    return detect_spans(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-an",
         "-vf", "freezedetect=n=%ddB:d=%.3f" % (db, min_dur),
         "-f", "null", "-"],
        "freeze_start:", "freeze_duration:")


def merge(spans, gap=0.0):
    out = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def intersect(spans, a, b):
    """The parts of `spans` inside [a, b]."""
    out = []
    for x, y in spans:
        lo, hi = max(x, a), min(y, b)
        if hi - lo > 1e-6:
            out.append((lo, hi))
    return out


def subtract(a, b, holes):
    """[a, b] minus every hole, as a list of surviving spans."""
    out, cur = [], a
    for x, y in merge(holes):
        if y <= cur or x >= b:
            continue
        x, y = max(x, cur), min(y, b)
        if x > cur + 1e-6:
            out.append((cur, x))
        cur = max(cur, y)
    if b > cur + 1e-6:
        out.append((cur, b))
    return out


def quantise(t, fps):
    return round(t * fps) / float(fps)


def plan_cuts(m, cut, film_a, film_b, screen_dur, offset, fps, verbose=True):
    """Decide what to keep, in camera time.

    Returns (keeps, drops). Each keep is (a, b, layout) with layout in
    {"full", "pip"} -- "pip" only where the screen actually covers it.
    """
    camera = rel(m["camera"])
    screen = rel(m["screen"])

    sil = silent_spans(camera, int(cut["silence_db"]), float(cut["min_silence"]))
    sil = intersect(sil, film_a, film_b)
    if verbose:
        print("  %d silences >= %.1fs at %ddB inside the film"
              % (len(sil), cut["min_silence"], cut["silence_db"]))

    # Screen coverage in camera time. Outside it there is no picture to disturb,
    # so those regions count as frozen -- otherwise no pause in the intro or
    # outro could ever be cut.
    cov_a, cov_b = offset, offset + screen_dur
    cutaway = float(cut.get("camera_when_frozen_over", 0.0))
    fz_cam = []
    if cut.get("require_frozen", True) or cutaway:
        fz = frozen_spans(screen, int(cut["freeze_db"]))
        fz_cam = merge([(a + offset, b + offset) for a, b in fz], gap=0.20)
        if verbose:
            tot = sum(b - a for a, b in intersect(fz_cam, cov_a, cov_b))
            print("  screen is frozen for %.1fs of its %.1fs (%.0f%%)"
                  % (tot, screen_dur, 100.0 * tot / screen_dur))
    if cut.get("require_frozen", True):
        still = merge(fz_cam + [(film_a - 1.0, cov_a), (cov_b, film_b + 1.0)],
                      gap=0.0)
    else:
        still = [(film_a - 1.0, film_b + 1.0)]

    air = float(cut["air"])
    min_drop = float(cut.get("min_drop", 0.5))
    # A silence this long goes whether or not the screen is moving. The freeze
    # mask exists to stop short breaths turning into jump cuts mid-animation;
    # it is not a reason to sit through five seconds of nobody saying anything
    # because output happened to be scrolling. 0 disables.
    force_over = float(cut.get("force_over", 0.0))
    drops = []
    for a, b in sil:
        # Leave air on both sides so the join does not clip the words around it.
        ca, cb = a + air, b - air
        if cb - ca < min_drop:
            continue
        if force_over and (b - a) >= force_over:
            drops.append((ca, cb))
            continue
        # Otherwise only the part that is ALSO a still screen may go.
        for x, y in intersect(still, ca, cb):
            if y - x >= min_drop:
                drops.append((x, y))
    drops = merge(drops)

    # Come back to the screen a beat BEFORE it starts moving again. Returning on
    # the exact frame it changes drops the viewer in with no context, and the
    # narration usually points at the screen ("below you can see...") a second
    # or two before the thing it points at happens.
    lead_out = float(cut.get("cutaway_lead_out", 2.0))
    long_still = ([(a, b - lead_out) for a, b in fz_cam
                   if b - lead_out - a >= cutaway] if cutaway else [])

    keeps = []
    for a, b in subtract(film_a, film_b, drops):
        # Split at the screen-coverage edges so every kept span has one layout.
        for x, y in _split_at(a, b, [cov_a, cov_b]):
            layout = "pip" if (x >= cov_a - 1e-6 and y <= cov_b + 1e-6) else "full"
            x, y = quantise(x, fps), quantise(y, fps)
            if y - x < 1.0 / fps:
                continue
            if layout == "pip" and long_still:
                keeps.extend(_cutaway(x, y, long_still, cutaway, fps))
            else:
                keeps.append((x, y, layout))
    if verbose and cutaway:
        cam = sum(b - a for a, b, l in keeps
                  if l == "full" and cov_a <= a and b <= cov_b)
        print("  %.1fs cuts away to camera (screen still for over %.0fs there)"
              % (cam, cutaway))
    return keeps, drops


def _cutaway(a, b, long_still, threshold, fps):
    """Show the camera instead of a screen that has stopped moving for good.

    Nobody watches a still picture for two minutes, and a picture-in-picture
    of a talking head does not rescue it -- the frame is still 95% dead. Where
    the screen has been frozen longer than the threshold, the camera takes the
    whole frame and the screen comes back when it has something to show.
    """
    # The test is on the frozen RUN, not on the overlap. Pause-cutting chops a
    # dead region into many short segments, and asking each one to overlap the
    # threshold on its own means the deadest stretch in the film qualifies for
    # nothing. MIN_CUTAWAY only keeps a sliver at a run's edge from becoming a
    # two-frame flash of camera.
    MIN_CUTAWAY = 3.0
    marks = []
    for fa, fb in long_still:
        lo, hi = max(fa, a), min(fb, b)
        if hi - lo >= MIN_CUTAWAY:
            marks.append((quantise(lo, fps), quantise(hi, fps)))
    if not marks:
        return [(a, b, "pip")]
    out, cur = [], a
    for lo, hi in sorted(marks):
        lo, hi = max(lo, cur), min(hi, b)
        if lo > cur + 1e-6:
            out.append((cur, lo, "pip"))
        if hi > lo + 1e-6:
            out.append((lo, hi, "full"))
            cur = hi
    if b > cur + 1e-6:
        out.append((cur, b, "pip"))
    return [(x, y, l) for x, y, l in out if y - x >= 1.0 / fps]


def _split_at(a, b, points):
    edges = [a] + sorted(p for p in points if a < p < b) + [b]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def resolve_bound(m, words, key, default):
    """A film boundary given as a phrase, a number, or left to the transcript.

    A phrase lands on the word's own edge, which cuts the film the instant the
    speaker stops -- audibly abrupt, and tighter than the transcript default,
    which gives itself 0.6s before the first word and 0.8s after the last.
    start_pad / end_pad buy that breath back. They default to 0, so a manifest
    that already resolves a bound by phrase keeps the timing it was cut with.
    """
    film = m.get("film") or {}
    spec = film.get(key)
    if spec is None:
        return default
    if isinstance(spec, (int, float)):
        return float(spec)
    hit = _outline.find(words, spec)
    if hit is None:
        sys.exit("film.%s phrase not found in transcript: %r" % (key, spec))
    if key == "start_text":
        return hit[0] - float(film.get("start_pad", 0.0))
    return hit[1] + float(film.get("end_pad", 0.0))


def pip_masks(pip, outdir):
    """Rounded-corner alpha mask and border ring, drawn once by Pillow.

    libass and ffmpeg have no rounded rectangle, and drawbox cannot round a
    corner, so the shape comes from Pillow the same way the handle badge does.
    Returns (mask_png, border_png) or (None, None) for a plain square.
    """
    radius = int(pip.get("corner_radius_px", 0))
    if radius <= 0:
        return None, None
    from PIL import Image, ImageDraw
    s = int(pip["size_px"])
    b = int(pip.get("border_px", 0))
    os.makedirs(outdir, exist_ok=True)

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([b, b, s - 1 - b, s - 1 - b],
                                           radius=max(1, radius - b), fill=255)
    mask_png = os.path.join(outdir, "pip-mask.png")
    mask.save(mask_png)

    border_png = None
    if b > 0:
        ring = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        col = pip.get("border_colour", "#FFFFFF")
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius,
                            outline=col, width=b)
        border_png = os.path.join(outdir, "pip-border.png")
        ring.save(border_png)
    return mask_png, border_png


def acts_from(keeps):
    """Group the keep-list into runs of one layout. Acts are sequential in the
    source timeline, which is what makes the whole film fit in one filtergraph:
    split feeds each act's select, and because act 2 discards everything before
    its first segment while act 1 is still playing, nothing queues up."""
    acts = []
    for a, b, layout in keeps:
        if acts and acts[-1]["layout"] == layout:
            acts[-1]["segs"].append((a, b))
        else:
            acts.append({"layout": layout, "segs": [(a, b)]})
    return acts


def labels(prefix, n):
    return "".join("[%s%d]" % (prefix, i) for i in range(n))


def cat(ch, parts, out, v, a):
    """concat the parts into `out`, or pass through when there is only one.

    Cutting is done with trim/atrim + concat rather than select/aselect. That
    is not a style preference: on this ffmpeg build (8.0.1) aselect silently
    passes EVERY audio frame -- measured, video cut to 4.00s while the audio
    stayed 518.36s -- so a select-based cut yields a file as long as the raw
    tape with the picture racing ahead of the sound. atrim is exact.
    """
    if len(parts) == 1:
        ch.append("%s%s[%s]" % (parts[0], "anull" if a else "null", out))
    else:
        ch.append("%sconcat=n=%d:v=%d:a=%d[%s]"
                  % ("".join(parts), len(parts), v, a, out))
    return "[%s]" % out


def fill(w, h):
    return ("scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop=%d:%d,setsar=1" % (w, h, w, h))


def fit(w, h, mode, bg):
    if mode == "crop":
        return fill(w, h)
    return ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:%s,setsar=1"
            % (w, h, w, h, bg))


def pip_xy(pip, w, h):
    s, mg = int(pip["size_px"]), int(pip["margin_px"])
    corner = pip.get("corner", "bottom-left")
    x = mg if "left" in corner else w - s - mg
    y = mg if "top" in corner else h - s - mg
    return x, y


def build_graph(acts, offset, canvas, pip, audio_cfg, mask_idx, border_idx,
                label_fc="", label_out=None):
    """One filtergraph for the whole film.

    Every act is rendered to the canvas independently and the finished acts are
    concatenated, so acts may differ in layout and even in source. Acts are
    sequential in each source's timeline, which is what keeps this cheap: a
    later act's trim discards frames while an earlier act is still playing, so
    nothing queues up behind the concat.
    """
    w, h, fps = canvas["width"], canvas["height"], canvas["fps"]
    bg = canvas.get("background", "black").replace("#", "0x")
    s = int(pip["size_px"])
    px, py = pip_xy(pip, w, h)
    cx, cy = float(pip.get("crop_x", 0.5)), float(pip.get("crop_y", 0.5))
    n = len(acts)
    ch = []

    # How many times each input is tapped. An input pad can only be consumed
    # once, so everything goes through a split sized up front.
    vt, at = {}, {}
    for act in acts:
        if act["layout"] == "clip":
            for src, _, _ in act["parts"]:
                vt[src] = vt.get(src, 0) + 1
            at[act["audio"][0]] = at.get(act["audio"][0], 0) + 1
        else:
            k = len(act["segs"])
            vt[1] = vt.get(1, 0) + k
            at[1] = at.get(1, 0) + k
            if act["layout"] == "pip":
                vt[0] = vt.get(0, 0) + k

    # Both sources go onto the output frame grid ONCE, before anything is
    # trimmed, so every trim lands on the same frame boundary and the video and
    # audio halves of a segment come out the same length.
    pool_v, pool_a = {}, {}
    for idx in sorted(vt):
        labs = ["xv%d_%d" % (idx, i) for i in range(vt[idx])]
        ch.append("[%d:v]fps=%d,split=%d%s"
                  % (idx, fps, len(labs), "".join("[%s]" % l for l in labs)))
        pool_v[idx] = labs
    for idx in sorted(at):
        labs = ["xa%d_%d" % (idx, i) for i in range(at[idx])]
        ch.append("[%d:a]asplit=%d%s"
                  % (idx, len(labs), "".join("[%s]" % l for l in labs)))
        pool_a[idx] = labs

    npip = sum(1 for a in acts if a["layout"] == "pip")
    if npip and mask_idx is not None:
        ch.append("[%d:v]format=gray,split=%d%s"
                  % (mask_idx, npip, labels("mk", npip)))
    if npip and border_idx is not None:
        ch.append("[%d:v]format=rgba,split=%d%s"
                  % (border_idx, npip, labels("bd", npip)))

    # Acts are concatenated, so every one must hand over the same pixel format,
    # sample rate and channel layout. The camera is mono 44.1k and a bookend
    # shot on another phone is stereo 48k; without this the concat refuses.
    vfmt = "format=yuv420p"
    afmt = ("aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000"
            ":channel_layouts=stereo")

    k = si = 0
    for i, act in enumerate(acts):
        if act["layout"] == "clip":
            src, a0, b0 = act["audio"]
            ch.append("[%s]atrim=start=%.4f:end=%.4f,asetpts=PTS-STARTPTS,%s[a%d]"
                      % (pool_a[src].pop(0), a0, b0, afmt, i))
            vp = []
            for j, (psrc, pa, pb) in enumerate(act["parts"]):
                lab = "cp%d_%d" % (i, j)
                ch.append("[%s]trim=start=%.4f:end=%.4f,setpts=PTS-STARTPTS,%s,%s[%s]"
                          % (pool_v[psrc].pop(0), pa, pb, fill(w, h), vfmt, lab))
                vp.append("[%s]" % lab)
            cat(ch, vp, "v%d" % i, 1, 0)
            continue

        vp, ap, sp = [], [], []
        for a, b in act["segs"]:
            ch.append("[%s]trim=start=%.4f:end=%.4f,setpts=PTS-STARTPTS[tv%d]"
                      % (pool_v[1].pop(0), a, b, k))
            ch.append("[%s]atrim=start=%.4f:end=%.4f,asetpts=PTS-STARTPTS[ta%d]"
                      % (pool_a[1].pop(0), a, b, k))
            vp.append("[tv%d]" % k)
            ap.append("[ta%d]" % k)
            if act["layout"] == "pip":
                ch.append("[%s]trim=start=%.4f:end=%.4f,"
                          "setpts=PTS-STARTPTS[ts%d]"
                          % (pool_v[0].pop(0), a - offset, b - offset, k))
                sp.append("[ts%d]" % k)
            k += 1

        cat(ch, ap, "araw%d" % i, 0, 1)
        ch.append("[araw%d]%s[a%d]" % (i, afmt, i))
        camv = cat(ch, vp, "camv%d" % i, 1, 0)

        if act["layout"] == "full":
            ch.append("%s%s,%s[v%d]" % (camv, fill(w, h), vfmt, i))
            continue

        # Screen behind, camera square in front.
        scr = cat(ch, sp, "scrv%d" % i, 1, 0)
        ch.append("%s%s[bg%d]"
                  % (scr, fit(w, h, canvas.get("fit", "pad"), bg), i))
        # min(iw,ih) rather than a probed number: the square stays square
        # whichever way round the source turns out to be.
        sq = ("crop=w='min(iw,ih)':h='min(iw,ih)'"
              ":x='(iw-min(iw,ih))*%.4f':y='(ih-min(iw,ih))*%.4f'" % (cx, cy))
        ch.append("%s%s,scale=%d:%d:flags=lanczos,setsar=1[sq%d]"
                  % (camv, sq, s, s, i))
        last = "sq%d" % i
        # shortest=1 everywhere the mask or border is involved. Those come from
        # -loop 1 image inputs, which are INFINITE: without it, alphamerge waits
        # forever for its second input to end and ffmpeg never finishes -- it
        # writes a growing file that has no moov atom and never will.
        if mask_idx is not None:
            ch.append("[%s]format=rgba[sqa%d]" % (last, i))
            ch.append("[sqa%d][mk%d]alphamerge=shortest=1[pip%d]" % (i, si, i))
            last = "pip%d" % i
        out = "vraw%d" % i
        ch.append("[bg%d][%s]overlay=%d:%d:shortest=1[%s]"
                  % (i, last, px, py, out))
        if border_idx is not None:
            ch.append("[%s][bd%d]overlay=%d:%d:shortest=1[vb%d]"
                      % (out, si, px, py, i))
            out = "vb%d" % i
        ch.append("[%s]%s[v%d]" % (out, vfmt, i))
        si += 1

    pairs = "".join("[v%d][a%d]" % (i, i) for i in range(n))
    # Name labels go on AFTER the concat, so their times are film time --
    # what the viewer sees on the scrubber -- rather than camera time, which
    # the cut has already stopped being a straight line through.
    ch.append("%sconcat=n=%d:v=1:a=1[%s][araw]"
              % (pairs, n, "vcat" if label_fc else "vout"))
    if label_fc:
        ch.append(label_fc)
        ch.append("[%s]null[vout]" % label_out)

    af = []
    if audio_cfg.get("highpass"):
        af.append("highpass=f=%d" % int(audio_cfg["highpass"]))
    if audio_cfg.get("denoise"):
        af.append("afftdn=nr=%d" % int(audio_cfg["denoise"]))
    if audio_cfg.get("loudnorm"):
        af.append("loudnorm=%s" % audio_cfg["loudnorm"])
    af.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")
    ch.append("[araw]%s[aout]" % ",".join(af))
    return ";".join(ch)



def act_dur(act):
    if act["layout"] == "clip":
        return act["audio"][2] - act["audio"][1]
    return sum(b - a for a, b in act["segs"])


def build_bookend(spec, extra):
    """A clip that tops or tails the film, from a source of its own.

    Its own audio runs the whole way; the picture may cut away to b-roll and
    back. That is the only way a silent clip earns a place -- it has nothing to
    say, so it plays under something that does.

    `extra` maps a path to its ffmpeg input index and is filled in as sources
    are met, so the caller can add them to the command line in the same order.
    """
    def idx(path):
        p = rel(path)
        if not os.path.exists(p):
            sys.exit("bookend source not found: %s" % p)
        if p not in extra:
            extra[p] = len(extra)
        return extra[p], p

    src, path = idx(spec["source"])
    words = _outline.load_words(rel(spec["words"])) if spec.get("words") else []
    a0 = spec.get("start")
    if a0 is None and spec.get("start_text"):
        hit = _outline.find(words, spec["start_text"])
        if hit is None:
            sys.exit("bookend %s: start_text not found" % spec.get("id"))
        a0 = max(0.0, hit[0] - float(spec.get("air", 0.4)))
    a0 = float(a0 if a0 is not None else 0.0)
    b0 = spec.get("end")
    if b0 is None and spec.get("end_text"):
        hit = _outline.find(words, spec["end_text"])
        if hit is None:
            sys.exit("bookend %s: end_text not found" % spec.get("id"))
        b0 = hit[1] + float(spec.get("air", 0.4))
    if b0 is None:
        b0 = probe_duration(path)
    b0 = float(b0)
    if b0 <= a0:
        sys.exit("bookend %s: end is not after start" % spec.get("id"))

    # Walk the clip start to end, handing each span either to the clip's own
    # picture or to a b-roll source. The parts must tile [a0, b0] exactly, or
    # the picture and the sound come out different lengths.
    parts, cur = [], a0
    for cut_in in sorted(spec.get("broll") or [], key=lambda c: c["at"]):
        at = a0 + float(cut_in["at"])
        dur = float(cut_in["dur"])
        if at < cur - 1e-6 or at + dur > b0 + 1e-6:
            sys.exit("bookend %s: b-roll at %.2f+%.2f does not fit inside the "
                     "clip or overlaps the one before it"
                     % (spec.get("id"), cut_in["at"], dur))
        if at > cur + 1e-6:
            parts.append((src, cur, at))
        bsrc, bpath = idx(cut_in["source"])
        bfrom = float(cut_in.get("from", 0.0))
        blen = probe_duration(bpath)
        if bfrom + dur > blen + 1e-6:
            sys.exit("bookend %s: b-roll wants %.2f..%.2f of a %.2fs source"
                     % (spec.get("id"), bfrom, bfrom + dur, blen))
        parts.append((bsrc, bfrom, bfrom + dur))
        cur = at + dur
    if b0 > cur + 1e-6:
        parts.append((src, cur, b0))

    tiled = sum(b - a for _, a, b in parts)
    if abs(tiled - (b0 - a0)) > 1e-3:
        sys.exit("bookend %s: picture is %.3fs against %.3fs of sound"
                 % (spec.get("id"), tiled, b0 - a0))

    return {"layout": "clip", "id": spec.get("id", "bookend"), "path": path,
            "audio": (src, a0, b0), "parts": parts}


def _truncate(acts, limit):
    """Keep only the first `limit` seconds of the film, for a quick look."""
    out, total = [], 0.0
    for act in acts:
        if total >= limit:
            break
        if act["layout"] == "clip":
            src, a0, b0 = act["audio"]
            take = min(b0 - a0, limit - total)
            parts, left = [], take
            for psrc, pa, pb in act["parts"]:
                if left <= 1e-6:
                    break
                d = min(pb - pa, left)
                parts.append((psrc, pa, pa + d))
                left -= d
            out.append(dict(act, audio=(src, a0, a0 + take), parts=parts))
            total += take
            continue
        segs = []
        for a, b in act["segs"]:
            if total >= limit:
                break
            take = min(b - a, limit - total)
            segs.append((a, a + take))
            total += take
        if segs:
            out.append({"layout": act["layout"], "segs": segs})
    return out, total


def _rotation(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream_side_data=rotation",
               "-of", "default=noprint_wrappers=1:nokey=1", path]).stdout
    for line in out.splitlines():
        if line.strip() and float(line.strip()) != 0.0:
            return line.strip()
    return None


def _dims(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height",
               "-of", "csv=p=0", path]).stdout.strip()
    w, _, h = out.partition(",")
    return int(w), int(h)


def _peak_db(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in (p.stderr or "").splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split("dB")[0])
            except (IndexError, ValueError):
                return None
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--plan", action="store_true",
                    help="write the keep-list sidecar and stop")
    ap.add_argument("--list", action="store_true",
                    help="print the timeline and runtime, encode nothing")
    ap.add_argument("--cuts", help="use this keep-list instead of planning one")
    ap.add_argument("--out", help="output path (default outdir/<id>.mp4)")
    ap.add_argument("--preview", type=float, default=0.0,
                    help="render only the first N seconds, for a look")
    ap.add_argument("--force", action="store_true", help="overwrite the output")
    args = ap.parse_args()

    m = json.load(open(args.manifest, encoding="utf-8"))
    mid = m.get("id") or os.path.splitext(os.path.basename(args.manifest))[0]
    screen, camera = rel(m["screen"]), rel(m["camera"])

    canvas = dict(DEFAULT_CANVAS, **(m.get("canvas") or {}))
    pip = dict(DEFAULT_PIP, **(m.get("pip") or {}))
    cut = dict(DEFAULT_CUT, **(m.get("cut") or {}))
    audio_cfg = m.get("audio") or {}
    render = dict(DEFAULT_RENDER, **(m.get("render") or {}))
    fps = int(canvas["fps"])
    name_specs = m.get("name_labels") or []
    for spec in name_specs:
        if "name" not in spec or "at" not in spec:
            sys.exit("every name_labels entry needs at least name and at")

    img_specs = m.get("image_overlays") or []
    img_preset = m.get("overlay_preset", _imgoverlay.DEFAULT_PRESET)
    for spec in img_specs:
        if "at" not in spec:
            sys.exit("every image_overlays entry needs at least at")
        given = [k for k in _imgoverlay.SOURCES if spec.get(k)]
        if len(given) != 1:
            sys.exit("every image_overlays entry needs exactly one of "
                     "%s -- got %s"
                     % ("/".join(_imgoverlay.SOURCES), ", ".join(given) or "none"))
        src = _imgoverlay._overlay.repo_path(spec[given[0]])
        if not os.path.exists(src):
            sys.exit("image overlay source does not exist: %s" % src)

    sync_path = os.path.join(os.path.dirname(args.manifest),
                             "%s.sync.json" % mid)
    if not os.path.exists(sync_path):
        sys.exit("no sync sidecar at %s -- run sync-tracks.py first" % sync_path)
    sync = json.load(open(sync_path, encoding="utf-8"))
    offset = float(sync["offset"])

    screen_dur = probe_duration(screen)
    camera_dur = probe_duration(camera)
    words = _outline.load_words(rel(m["words"])) if m.get("words") else []

    # The film runs from the first word to the last unless told otherwise. The
    # camera was rolling before and after both, and that dead air is not content.
    d0 = max(0.0, (words[0]["start"] - 0.6) if words else 0.0)
    d1 = min(camera_dur, (words[-1]["end"] + 0.8) if words else camera_dur)
    film_a = resolve_bound(m, words, "start_text", d0)
    film_b = resolve_bound(m, words, "end_text", d1)
    film_a = max(0.0, min(film_a, camera_dur))
    film_b = max(film_a + 1.0, min(film_b, camera_dur))

    print("%s  offset %+.3fs (%s)" % (mid, offset, sync.get("method")))
    print("  screen %.2fs, camera %.2fs" % (screen_dur, camera_dur))
    print("  film spans camera %.2f .. %.2f  (%.1fs of tape)"
          % (film_a, film_b, film_b - film_a))

    cuts_path = args.cuts or os.path.join(os.path.dirname(args.manifest),
                                          "%s.cuts.json" % mid)
    if args.cuts and os.path.exists(args.cuts):
        doc = json.load(open(args.cuts, encoding="utf-8"))
        keeps = [(float(a), float(b), l) for a, b, l in doc["keeps"]]
        drops = [(float(a), float(b)) for a, b in doc.get("drops", [])]
        print("  keep-list loaded from %s" % os.path.relpath(args.cuts, ROOT))
    else:
        keeps, drops = plan_cuts(m, cut, film_a, film_b, screen_dur,
                                 offset, fps)

    core = sum(b - a for a, b, _ in keeps)
    dropped = (film_b - film_a) - core
    print("")
    print("  %d segments, %d cuts" % (len(keeps), len(drops)))
    print("  core %s  (cut %.1fs of pauses, %.0f%% of the tape)"
          % (hhmmss(core), dropped,
             100.0 * dropped / max(1e-9, film_b - film_a)))

    extra = {}
    bk = m.get("bookends") or {}
    opens = [build_bookend(b, extra) for b in (bk.get("open") or [])]
    closes = [build_bookend(b, extra) for b in (bk.get("close") or [])]
    acts = opens + acts_from(keeps) + closes
    for a in opens + closes:
        print("  bookend %-10s %6.2fs from %s%s"
              % (a["id"], act_dur(a), os.path.basename(a["path"]),
                 "  (+%d b-roll)" % (len(a["parts"]) // 2)
                 if len(a["parts"]) > 1 else ""))

    runtime = sum(act_dur(a) for a in acts)
    print("  runtime %s" % hhmmss(runtime))
    print("  acts: %s" % ", ".join(
        "%s (%s)" % (a["layout"], hhmmss(act_dur(a))) for a in acts))

    if args.list:
        print("")
        print("  camera in       out      len   layout   what is said there")
        for a, b, layout in keeps:
            said = ""
            if words:
                ws = [w["text"] for w in words
                      if a <= w["start"] < min(b, a + 6)]
                said = " ".join(ws)[:56]
            print("  %8.2f %8.2f %6.2f   %-6s   %s"
                  % (a, b, b - a, layout, said))
        if drops:
            print("")
            print("  cut out:")
            for a, b in drops:
                print("  %8.2f %8.2f %6.2f   pause" % (a, b, b - a))

    # A label past the end of the cut film is not an error ffmpeg reports --
    # `enable` simply never turns true and the card silently never appears. The
    # runtime is only known here, after the cut, so this is where it is caught.
    for spec in name_specs:
        if float(spec["at"]) >= runtime:
            sys.exit("name label %r starts at %.1fs but the film runs %.1fs"
                     % (spec["name"], float(spec["at"]), runtime))
    if name_specs and args.list:
        print("")
        print("  name labels (film time):")
        for spec in name_specs:
            print("  %8.2f %8.2f   %s -- %s"
                  % (float(spec["at"]),
                     float(spec["at"]) + float(spec.get("dur", 5.5)),
                     spec["name"], spec.get("title", "")))

    # Same trap for image overlays, with one extra convenience to resolve: a
    # negative `at` means "this many seconds before the end", which only becomes
    # a number once the cut is planned. An end card is written that way on
    # purpose -- re-cutting the film moves it automatically.
    img_preset_doc = json.load(open(
        _imgoverlay._overlay.repo_path(img_preset), encoding="utf-8")) \
        if img_specs else {}
    for i, spec in enumerate(img_specs):
        at, dur = _imgoverlay.resolve_window(spec, img_preset_doc, runtime)
        if at >= runtime:
            sys.exit("image overlay %d starts at %.1fs but the film runs %.1fs"
                     % (i, at, runtime))
    if img_specs and args.list:
        print("")
        print("  image overlays (film time):")
        for spec in img_specs:
            at, dur = _imgoverlay.resolve_window(spec, img_preset_doc, runtime)
            print("  %8.2f %8.2f   %s"
                  % (at, at + dur,
                     _imgoverlay.describe(spec, img_preset_doc, runtime)))

    doc = {
        "_comment": "Keep-list for screencast-cut.py, in CAMERA time. Each keep "
                    "is [start, end, layout]; layout pip means the screen is up "
                    "with the camera as a square, full means camera only. Edit "
                    "this and re-run with --cuts to override the plan.",
        "id": mid, "offset": offset, "fps": fps,
        "film": [film_a, film_b],
        "rule": cut,
        "runtime": round(runtime, 3),
        "keeps": [[round(a, 4), round(b, 4), l] for a, b, l in keeps],
        "drops": [[round(a, 4), round(b, 4)] for a, b in drops],
    }
    if not args.cuts:
        with open(cuts_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print("")
        print("  keep-list -> %s" % os.path.relpath(cuts_path, ROOT))

    if args.plan or args.list:
        return

    outdir = rel(m.get("outdir", "outputs/screencast"))
    os.makedirs(outdir, exist_ok=True)
    dst = args.out or os.path.join(outdir, "%s.mp4" % mid)
    if os.path.exists(dst) and not args.force:
        sys.exit("%s exists; --force to replace it" % os.path.relpath(dst, ROOT))

    if args.preview > 0:
        acts, runtime = _truncate(acts, args.preview)
        print("  PREVIEW: first %.1fs only" % runtime)

    tmpdir = os.path.join(ROOT, "temp", "screencast-%s" % mid)
    mask_png, border_png = pip_masks(pip, tmpdir)

    # trim does not seek -- it decodes and discards -- so without an upper bound
    # ffmpeg reads both files to EOF however little of them the film uses. -to
    # is an INPUT option here, which caps the read without shifting timestamps
    # the way -ss would (and the trim times are absolute).
    cam_to = max([b for act in acts if act["layout"] != "clip"
                  for _, b in act["segs"]] or [1.0]) + 2.0
    scr_ends = [b - offset for act in acts if act["layout"] == "pip"
                for _, b in act["segs"]]
    inputs = []
    if scr_ends:
        inputs += ["-to", "%.3f" % (max(scr_ends) + 2.0)]
    inputs += ["-i", screen]
    # IMG_2695 carries rotation=-90 that is simply wrong. -display_rotation
    # rewrites the input's rotation rather than merely declining to apply it,
    # which -noautorotate does: with -noautorotate the frames come through
    # upright but the bogus matrix is COPIED ONTO THE OUTPUT, and every player
    # then turns the finished 1920x1080 film on its side. Measured, not guessed.
    rot = m.get("camera_rotate", "auto")
    if rot != "auto":
        inputs += ["-display_rotation:v:0", "0" if rot == "none" else str(rot)]
    inputs += ["-to", "%.3f" % cam_to, "-i", camera]
    mask_idx = border_idx = None
    nxt = 2
    # -loop/-framerate matter: a bare PNG is a ONE frame stream, and alphamerge
    # ends with the shorter of its inputs, so the square would keep its alpha
    # for a single frame and turn opaque for the rest of the film.
    for png, which in ((mask_png, "mask"), (border_png, "border")):
        if not png:
            continue
        inputs += ["-loop", "1", "-framerate", str(fps), "-i", png]
        if which == "mask":
            mask_idx = nxt
        else:
            border_idx = nxt
        nxt += 1

    # Bookend sources come last on the command line. build_bookend numbered them
    # from zero as it met them, which would collide with the screen and camera
    # pads, so rebase them onto their real input indices now that the mask and
    # border have claimed theirs.
    if extra:
        base = dict((ordinal, nxt + n)
                    for n, (_, ordinal) in enumerate(sorted(extra.items(),
                                                            key=lambda kv: kv[1])))
        for act in acts:
            if act["layout"] != "clip":
                continue
            s0, a0, b0 = act["audio"]
            act["audio"] = (base[s0], a0, b0)
            act["parts"] = [(base[s], a, b) for s, a, b in act["parts"]]
        for path, ordinal in sorted(extra.items(), key=lambda kv: kv[1]):
            inputs += ["-i", path]
            nxt += 1

    # Label PNGs claim the last input indices, after the bookends have been
    # rebased onto theirs -- allocating them earlier would shift every bookend.
    label_fc, label_out = "", None
    if name_specs:
        pngs, label_fc, label_out = _namelabel.prepare(
            m.get("label_preset", _namelabel.DEFAULT_PRESET), name_specs,
            canvas["width"], canvas["height"], tmpdir, tag=mid, base="vcat",
            first_input=nxt)
        for png in pngs:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", png]
            nxt += 1

    # Image overlays come after the labels, on both counts: later input indices,
    # and later in the chain, so an end card sits on top of a lower third rather
    # than under it. Both are spliced through build_graph's one seam.
    if img_specs:
        pngs, img_fc, img_out = _imgoverlay.prepare(
            img_preset, img_specs, canvas["width"], canvas["height"], tmpdir,
            tag=mid, base=(label_out or "vcat"), first_input=nxt,
            runtime=runtime)
        for png in pngs:
            inputs += ["-loop", "1", "-framerate", str(fps), "-i", png]
            nxt += 1
        label_fc = ";".join(x for x in (label_fc, img_fc) if x)
        label_out = img_out

    graph = build_graph(acts, offset, canvas, pip, audio_cfg,
                        mask_idx, border_idx, label_fc, label_out)

    tmp = dst + ".part.mp4"
    # -progress makes the encode legible from outside this process: ffmpeg
    # appends out_time and speed to that file twice a second, which is what the
    # status line reads. Without it a multi-minute NVENC pass is a silent wait.
    prog = _progress.begin(mid, runtime, os.path.relpath(dst, ROOT))
    cmd = (["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-progress", prog]
           + inputs
           + ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
              "-r", str(fps),
              "-c:v", render["encoder"], "-preset", render["preset"],
              "-rc", "vbr", "-cq", str(render["cq"]),
              # NVENC ignores -cq unless the average bitrate target is unset
              "-b:v", "0", "-maxrate", render["maxrate"],
              "-bufsize", render["bufsize"], "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", render["audio_bitrate"], "-ac", "2",
              "-movflags", "+faststart", "-y", tmp])

    print("")
    print("  rendering %s ..." % os.path.relpath(dst, ROOT))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        _progress.end(mid)
    if p.returncode != 0:
        sys.stderr.write((p.stderr or "")[-4000:])
        sys.exit("ffmpeg failed")

    got = probe_duration(tmp)
    if abs(got - runtime) > max(2.0 / fps, 0.5):
        sys.stderr.write("output is %.2fs, the keep-list predicted %.2fs\n"
                         % (got, runtime))
        sys.exit("duration assertion failed; %s left in place" % tmp)

    # The failure that started this job was a track nobody listened to.
    peak = _peak_db(tmp)
    if peak is None or peak < -60:
        sys.exit("rendered audio is silent (peak %s dB); refusing to ship it"
                 % peak)

    # A phone's display matrix can survive the filtergraph and land on the
    # output, which turns the whole film on its side in every player while
    # ffprobe still cheerfully reports 1920x1080.
    got_rot = _rotation(tmp)
    if got_rot:
        sys.exit("output carries rotation=%s, so players will turn it on its "
                 "side; %s left in place" % (got_rot, tmp))
    w, h = _dims(tmp)
    if (w, h) != (canvas["width"], canvas["height"]):
        sys.exit("output is %dx%d, expected %dx%d"
                 % (w, h, canvas["width"], canvas["height"]))

    shutil.move(tmp, dst)
    print("  %s  %s  %.1f MB  audio peak %.1f dB"
          % (os.path.relpath(dst, ROOT), hhmmss(got),
             os.path.getsize(dst) / 1e6, peak))

    _project.record(
        _project.project_id(m, args.manifest), "render",
        out=dst, script=__file__, argv=sys.argv[1:], kind="screencast",
        manifest=args.manifest,
        sidecars={"sync": sync_path, "cuts": cuts_path},
        burned=(["pause cut per cuts.json (min_silence %s)" % cut["min_silence"],
                 "camera PiP %s %spx" % (pip["corner"], pip["size_px"])]
                + ["opening bookend %s%s"
                   % (be.get("id", "clip"),
                      " + b-roll" if be.get("broll") else "")
                   for be in (m.get("bookends") or {}).get("open", [])]
                + ["name label '%s' at %ss film time for %ss"
                   % (s.get("name"), s.get("at"), s.get("dur"))
                   for s in name_specs]
                + [_imgoverlay.describe(s, img_preset_doc, runtime)
                   for s in img_specs]))


if __name__ == "__main__":
    main()
