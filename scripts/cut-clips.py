#!/usr/bin/env python
"""Cut a list of episodes out of one long video into standalone clips.

Boundaries are given either as seconds or, better, as a phrase from the
transcript -- `start_text` / `end_text` / `end_before_text` are resolved against
`transcripts/<id>.words.json`, so a manifest keeps reading like the edit
decisions you actually made ("start where she says X") instead of magic numbers.

Cuts are frame-accurate: the source is re-encoded rather than stream-copied, so
a clip starts on the requested frame and not on the preceding keyframe. Pass
--copy for an instant, keyframe-snapped cut when that is good enough.

Each clip is skipped when its output already exists (--force reruns it), so
re-running after editing one entry only re-renders that entry.

Invoke as:  python scripts/cut-clips.py --manifest config/clips/<id>.json
"""
import sys, os, json, argparse, subprocess, shutil, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

_outline = import_module("transcript-outline")   # hyphen: not importable by name
_handle = import_module("handle-overlay")
_imgoverlay = import_module("image-overlay")
import _progress
import _project


ENV = _env.ENV

DEFAULT_RENDER = {
    "encoder": "h264_nvenc", "preset": "p5", "cq": 21,
    "maxrate": "16M", "bufsize": "32M", "audio_bitrate": "192k",
}


def run(cmd, **kw):
    return subprocess.run(cmd, env=ENV, **kw)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "json", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s\n%s" % (path, out.stderr.strip()))
    return float(json.loads(out.stdout)["format"]["duration"])


def probe_video(path):
    """(width, height, nb_frames) of the first video stream, (0, 0, 0) if none.

    Duration alone does not prove a render worked: a filter graph that ends up
    bounded by a one-frame image input produces a file whose AUDIO runs the full
    length while the video is a single frame or missing altogether, and every
    duration check still passes. Ask about the picture directly.
    """
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-count_packets", "-show_entries",
               "stream=width,height,nb_read_packets", "-of", "json", path],
              capture_output=True, text=True)
    if out.returncode:
        return 0, 0, 0
    streams = json.loads(out.stdout).get("streams") or []
    if not streams:
        return 0, 0, 0
    s = streams[0]
    return (int(s.get("width") or 0), int(s.get("height") or 0),
            int(s.get("nb_read_packets") or 0))


def probe_fps(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=r_frame_rate", "-of", "json", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed on %s" % path)
    num, _, den = json.loads(out.stdout)["streams"][0]["r_frame_rate"].partition("/")
    return float(num) / float(den or 1)


def hhmmss(t):
    if t >= 3600:
        return "%d:%02d:%05.2f" % (int(t) // 3600, (int(t) % 3600) // 60, t % 60)
    return "%02d:%05.2f" % (int(t) // 60, t % 60)


PY = _env.PY
ROOT = _env.ROOT


def even(n):
    """Crop and scale dimensions must be even for yuv420p chroma."""
    return int(n) // 2 * 2


def crop_box(clip, src_w, src_h, out_w, out_h):
    """The source rectangle to keep, as (w, h, x, y).

    Height is spent first -- going 16:9 -> 9:16 the full frame height already
    fits, so zoom stays at 1 unless asked for. `crop_x` moves the window because
    a fixed centre crop is a bet that the subject is centred, and over a whole
    video they are not.
    """
    zoom = float(clip.get("crop_zoom", 1.0))
    ch = even(min(src_h, src_h / zoom))
    cw = even(min(src_w, ch * out_w / float(out_h)))
    cx = float(clip.get("crop_x", src_w / 2.0)) - cw / 2.0
    cy = float(clip.get("crop_y", src_h / 2.0)) - ch / 2.0
    cx = even(min(max(cx, 0), src_w - cw))
    cy = even(min(max(cy, 0), src_h - ch))
    return cw, ch, cx, cy


def crop_x_expr(keys, x_lo, x_hi, cw):
    """Turn [[t, centre_x], ...] into a crop-x expression in t.

    Linear between keys so the window pans rather than jumping; a scene cut is
    expressed as two keys a few frames apart, which reads as a snap. Held flat
    before the first key and after the last.
    """
    pts = [(float(t), min(max(float(x), x_lo), x_hi) - cw / 2.0) for t, x in keys]
    pts.sort()
    e = "%g" % pts[-1][1]
    for i in range(len(pts) - 2, -1, -1):
        (t0, x0), (t1, x1) = pts[i], pts[i + 1]
        span = max(t1 - t0, 1e-3)
        seg = "(%g+(%g)*(t-%g))" % (x0, (x1 - x0) / span, t0)
        e = "if(lt(t,%g),%s,%s)" % (t1, seg, e)
    return "if(lt(t,%g),%g,%s)" % (pts[0][0], pts[0][1], e)


def vertical_chain(crop_filter, pads, out_w, out_h, blur_h=480):
    """Crop most of the time; letterbox the shots that have no subject.

    A wide burned-in graphic has no 9:16 window that contains it, so those shots
    are shown whole over a blurred fill instead of being sliced. Both treatments
    are composited onto the same blurred base and switched by `enable`, which
    keeps it to one pass -- the alternative, cutting each shot separately and
    concatenating, would re-encode every segment.

    The fill is blurred at 270x480 and then scaled up rather than blurred at
    full size: it is out of focus by definition, so nobody can tell, and it
    costs a fraction as much.
    """
    if not pads:
        return "[0:v]%s,scale=%d:%d:flags=lanczos,setsar=1[vcomp]" % (
            crop_filter, out_w, out_h), "vcomp"

    blur_w = int(round(blur_h * out_w / float(out_h)))
    hit = "+".join("between(t,%g,%g)" % (a, b) for a, b in pads)
    e = _handle.esc
    parts = [
        "[0:v]split=3[bgs][fgs][pds]",
        "[bgs]scale=-2:%d,crop=%d:%d,boxblur=10:2,scale=%d:%d,setsar=1[bgv]"
        % (blur_h, blur_w, blur_h, out_w, out_h),
        "[fgs]%s,scale=%d:%d:flags=lanczos,setsar=1[fgv]" % (crop_filter, out_w, out_h),
        "[pds]scale=%d:-2,setsar=1[pdv]" % out_w,
        "[bgv][fgv]overlay=0:0:enable=%s[vc1]" % e("not(%s)" % hit),
        "[vc1][pdv]overlay=0:(H-h)/2:enable=%s[vcomp]" % e(hit),
    ]
    return ";".join(parts), "vcomp"


def norm_colour(c):
    """`#13BA82` is what a brand file and a designer both write; ffmpeg wants
    `0x13BA82`. Names (`black`, `white`) and `0x` forms are passed through."""
    c = str(c).strip()
    return "0x" + c[1:] if c.startswith("#") else c


def ramp_expr(pts, lo, hi):
    """Piecewise-linear value in t from [[t, v], ...], held flat past both ends.

    The same shape as crop_x_expr, but it returns the value itself rather than a
    centre converted to an edge, and it is used for both axes -- a screen
    recording pans in y (a scroll) as often as in x.
    """
    pts = sorted((float(t), min(max(float(v), lo), hi)) for t, v in pts)
    e = "%g" % pts[-1][1]
    for i in range(len(pts) - 2, -1, -1):
        (t0, v0), (t1, v1) = pts[i], pts[i + 1]
        span = max(t1 - t0, 1e-3)
        e = "if(lt(t,%g),(%g+(%g)*(t-%g)),%s)" % (
            t1, v0, (v1 - v0) / span, t0, e)
    return "if(lt(t,%g),%g,%s)" % (pts[0][0], pts[0][1], e)


def mask_chain(masks, src_w, src_h, src_label="0:v"):
    """Blur or fill named source rectangles before anything else looks at them.

    A screen recording that is about to be re-voiced carries things that must
    not survive the edit: a webcam PiP whose lips will not match the new voice,
    a burned-in caption card whose words will contradict it. Cropping them out
    works only when they sit outside the region worth keeping, and a webcam in
    the bottom-left corner usually does not -- it shares a band with the buttons
    the demo is about. Masking first decouples the two decisions, so the rect
    can be chosen for readability alone.

    `delogo` is the default and, measured on real frames here, the only mode
    that actually disappears: it interpolates the rectangle from its own border
    pixels, so over a flat page background the patch is that background. A heavy
    blur of a dark webcam is a grey smudge, and copying a neighbouring strip
    duplicates whatever happens to be in it -- both were tried and both showed.
    Keep `blur` and `fill` for a region delogo cannot reach (one larger than a
    handful of pixels from a matching edge).
    """
    parts, label, n = [], src_label, 0
    for spec in masks:
        mx, my, mw, mh = (int(v) for v in spec["rect"])
        mx = even(min(max(mx, 0), max(src_w - 2, 0)))
        my = even(min(max(my, 0), max(src_h - 2, 0)))
        mw = even(min(mw, src_w - mx))
        mh = even(min(mh, src_h - my))
        if mw < 2 or mh < 2:
            continue
        out = "mk%d" % n
        mode = spec.get("mode", "delogo")
        if mode == "delogo":
            # delogo refuses a box touching the frame edge -- it has no border
            # to interpolate from there -- so hold it one pixel inside.
            dx, dy = max(mx, 1), max(my, 1)
            dw = min(mw, src_w - dx - 1)
            dh = min(mh, src_h - dy - 1)
            parts.append("[%s]delogo=x=%d:y=%d:w=%d:h=%d[%s]"
                         % (label, dx, dy, dw, dh, out))
        elif mode == "fill":
            parts.append("[%s]drawbox=%d:%d:%d:%d:color=%s:t=fill[%s]"
                         % (label, mx, my, mw, mh,
                            norm_colour(spec.get("color", "white")), out))
        else:
            parts.append("[%s]split=2[mb%d][mm%d]" % (label, n, n))
            parts.append("[mb%d]crop=%d:%d:%d:%d,boxblur=%d:3[mp%d]"
                         % (n, mw, mh, mx, my, int(spec.get("blur", 25)), n))
            parts.append("[mm%d][mp%d]overlay=%d:%d[%s]" % (n, n, mx, my, out))
        label, n = out, n + 1
    return parts, label, n


def rect_chain(rect, place, src_w, src_h, out_w, out_h, blur_h=480):
    """Fit a named source rectangle into the vertical frame, on a background.

    A screen recording has no 9:16 window worth cropping to. Its readable region
    is wider than it is tall, so `crop_box` -- which spends height first and
    keeps a 607px-wide slice of a browser -- produces something nobody can read.
    And what must LEAVE the frame is chosen by where it sits, not by where a
    subject is: a burned-in caption card that would contradict a new voice-over,
    a webcam PiP whose lips will not match it, a taskbar.

    So the manifest names the rectangle to keep. It is scaled to the canvas
    width and placed at `place.y`, over either a blurred blow-up of the frame or
    a flat colour. Returns the chain, its output label, and the geometry, so
    --list can price the framing without encoding anything.
    """
    rx, ry, rw, rh = (int(v) for v in rect)
    rx = min(max(rx, 0), max(src_w - 2, 0))
    ry = min(max(ry, 0), max(src_h - 2, 0))
    rw = even(min(rw, src_w - rx))
    rh = even(min(rh, src_h - ry))
    rx, ry = even(rx), even(ry)
    if rw < 2 or rh < 2:
        sys.exit("crop_rect %s has no area inside the %dx%d source"
                 % (rect, src_w, src_h))
    fit_h = even(rh * out_w / float(rw))
    if fit_h > out_h:
        sys.exit("crop_rect %s is %dx%d; scaled to %d wide it is %d tall, which "
                 "does not fit the %dx%d canvas -- widen the rect or lose height"
                 % (rect, rw, rh, out_w, fit_h, out_w, out_h))
    y = place.get("y")
    y = (out_h - fit_h) / 2.0 if y is None else float(y)
    y = even(min(max(y, 0), out_h - fit_h))
    bg = place.get("background", "blur")
    if bg == "blur":
        # out of focus by definition, so blur it small and scale it up
        blur_w = int(round(blur_h * out_w / float(out_h)))
        bgf = ("[bgs]scale=-2:%d,crop=%d:%d,boxblur=10:2,scale=%d:%d,setsar=1[bgv]"
               % (blur_h, blur_w, blur_h, out_w, out_h))
    else:
        # drawbox over a scaled copy of the frame, rather than a `color` source:
        # a lavfi source never ends, and the overlay would then need shortest=1
        # to stop the render running forever.
        bgf = ("[bgs]scale=%d:%d,drawbox=0:0:%d:%d:color=%s:t=fill,setsar=1[bgv]"
               % (out_w, out_h, out_w, out_h, norm_colour(bg)))
    # A pan keeps ONE window size and moves it. crop's w/h evaluate once and
    # only its x/y are per-frame, so a window that changes SIZE cannot be done
    # in this pass at all -- which is also why the rect is fixed and the
    # framing is chosen to hold across the whole clip.
    pan = place.get("pan")
    if pan:
        px = [(t, v[0]) for t, v in pan]
        py = [(t, v[1]) for t, v in pan]
        xf = _handle.esc(ramp_expr(px, 0, src_w - rw))
        yf = _handle.esc(ramp_expr(py, 0, src_h - rh))
        crop_f = "crop=%d:%d:x=%s:y=%s" % (rw, rh, xf, yf)
    else:
        crop_f = "crop=%d:%d:%d:%d" % (rw, rh, rx, ry)
    mparts, msrc, nmask = mask_chain(place.get("mask") or [], src_w, src_h)
    parts = mparts + [
        "[%s]split=2[bgs][fgs]" % msrc,
        bgf,
        "[fgs]%s,scale=%d:%d:flags=lanczos,setsar=1[fgv]"
        % (crop_f, out_w, fit_h),
        "[bgv][fgv]overlay=0:%d[vcomp]" % y,
    ]
    return ";".join(parts), "vcomp", (rw, rh, rx, ry, fit_h, y, bg,
                                      len(pan or []), nmask)


def clip_rect(clip, m):
    """The rect and placement for a clip: its own, else the manifest's default.

    One rect usually serves a whole batch -- the intruders sit in the same place
    in every shot of one recording -- so the manifest carries it and a clip only
    overrides when its framing genuinely differs.
    """
    rect = clip.get("crop_rect", m.get("crop_rect"))
    if not rect:
        return None, {}
    place = dict(m.get("place") or {})
    place.update(clip.get("place") or {})
    return rect, place


def build_captions(clip, words_path, style, start, end, w, h, fps, tmpdir,
                   verify=True, samples=24, overlays=None, fontsdir="fonts"):
    """Render an ASS for just this clip's span, rebased to t=0.

    --range/--time-offset already exist in the ASS builder, so a clip needs no
    sliced copy of the transcript: the full word list is the single source of
    truth and each clip is a view onto it.
    """
    # Forward slashes, always: a Windows backslash reaches libass through the
    # ass filter as an escape, so temp\05-x.ass silently becomes temp05-x.ass.
    ass = os.path.join(tmpdir, "%s.captions.ass" % clip["id"]).replace("\\", "/")
    dbg = os.path.join(tmpdir, "%s.captions.debug.json" % clip["id"]).replace("\\", "/")
    cmd = PY + ["scripts/build-captions-ass.py", "--words", words_path,
                "--style", style, "--out", ass, "--debug-out", dbg,
                "--scale-to", str(w), str(h),
                "--range", "%.3f" % start, "%.3f" % end,
                "--time-offset", "%.3f" % start]
    if overlays:
        cmd += ["--overlays", overlays]
    if subprocess.run(cmd, cwd=ROOT, env=ENV).returncode:
        sys.exit("%s: building captions failed" % clip["id"])
    if verify:
        # Same guarantee the captions pipeline gives: prove the highlight lands
        # on the right word BEFORE spending an encode on it.
        r = subprocess.run(PY + ["scripts/verify-captions.py", "--debug", dbg,
                                 "--style", style, "--ass", ass,
                                 "--fontsdir", fontsdir,
                                 "--tmp", os.path.join(
                                     tmpdir, "_probe_%s.png" % clip["id"]),
                                 "--fps", "%.6f" % fps, "--samples", str(samples)],
                           cwd=ROOT, env=ENV)
        if r.returncode:
            sys.exit("%s: caption sync verification failed" % clip["id"])
    return ass


def resolve(clip, words, pad_head, pad_tail):
    """Return (start, end) in seconds, padded but never into a neighbouring word.

    A pad is a guess about silence. When the transcript says a word is still
    being spoken inside the pad, meet it halfway instead -- that keeps the head
    of a clip from opening on the tail of the previous sentence.
    """
    def phrase(key):
        hit = _outline.find(words, clip[key])
        if hit is None:
            sys.exit("%s: phrase not found in transcript: %r" % (clip["id"], clip[key]))
        return hit

    anchor_a = anchor_b = None
    if "start" in clip:
        start = float(clip["start"])
    elif "start_text" in clip:
        anchor_a, _ = phrase("start_text")
        start = anchor_a
    else:
        sys.exit("%s: needs start or start_text" % clip["id"])

    if "end" in clip:
        end = float(clip["end"])
    elif "duration" in clip:
        end = start + float(clip["duration"])
    elif "end_text" in clip:
        _, anchor_b = phrase("end_text")
        end = anchor_b
    elif "end_before_text" in clip:
        # cut just before the next thought begins
        anchor_b, _ = phrase("end_before_text")
        end = anchor_b
    else:
        sys.exit("%s: needs end, duration, end_text or end_before_text" % clip["id"])

    if anchor_a is not None:
        prev_end = max([w["end"] for w in words if w["end"] <= anchor_a + 1e-6],
                       default=0.0)
        start = max(anchor_a - pad_head, min(anchor_a, (prev_end + anchor_a) / 2.0))
    if anchor_b is not None and "end_before_text" in clip:
        prev_end = max([w["end"] for w in words if w["end"] <= anchor_b + 1e-6],
                       default=anchor_b)
        end = min(anchor_b, max(prev_end, (prev_end + anchor_b) / 2.0) + pad_tail)
    elif anchor_b is not None:
        next_start = min([w["start"] for w in words if w["start"] >= anchor_b - 1e-6],
                         default=None)
        end = anchor_b + pad_tail
        if next_start is not None and next_start < end:
            end = (anchor_b + next_start) / 2.0

    if end <= start:
        sys.exit("%s: end (%.2f) is not after start (%.2f)" % (clip["id"], end, start))
    return max(0.0, start), end


def cut(src, dst, start, dur, render, copy, overlay=None, pre_chain=None,
        base="vbase", dub=None, img=None, fps=None):
    """overlay is (png_paths, filter_complex, out_label) from handle-overlay;
    pre_chain is a filter graph ending in [base] that runs before the badge;
    img is the same triple from image-overlay, composited after the badge;
    dub is a wav to use INSTEAD of the source audio."""
    extra = []
    if copy:
        if overlay or pre_chain or img:
            sys.exit("--copy cannot crop, caption or brand: stream copy does not filter")
        if dub:
            # -ss + -c copy snaps to the preceding keyframe, so the picture would
            # start somewhere the dub was never aligned to
            sys.exit("--copy cannot carry a dub: a keyframe-snapped cut desyncs it")
        args = ["-c", "copy"]
    else:
        chain = []
        if pre_chain:
            chain.append(pre_chain)
        n_in = 1
        if overlay:
            pngs, fc, label = overlay
            for p in pngs:
                extra += ["-i", p]
            n_in += len(pngs)
            chain.append(fc)
            # handle-overlay hardcodes [1:v]..[N:v]; this run's PNGs really do
            # sit at those indices only because nothing was inserted before
            # them. Keep that true, loudly.
            assert all(("[%d:v]" % (k + 1)) in fc for k in range(len(pngs))), \
                "badge filter no longer addresses inputs 1..N -- input order changed?"
        else:
            label = base
        # Image overlays go after the badge PNGs -- both in the input list, for
        # the reason below, and in the chain, so a card lands on top of the
        # badge. image-overlay addresses its inputs relative to first_input, so
        # unlike the badge it does not care where it ended up.
        if img:
            pngs, fc, label = img
            for p in pngs:
                # -loop 1 is NOT optional here, and its absence is silent. The
                # image-overlay chain ends in shortest=1 (it must -- see
                # image-overlay.py), and a plain image input is ONE frame long,
                # so the shortest stream would be that frame and the output
                # would carry a single video frame -- or none at all, while the
                # audio still runs the full length and every duration check
                # still passes. The badge gets away without it only because its
                # overlay has no shortest=1.
                extra += ["-loop", "1", "-framerate", "%g" % (fps or 30),
                          "-i", p]
            n_in += len(pngs)
            chain.append(fc)
        # The dub is appended AFTER the badge PNGs on purpose: handle-overlay
        # addresses those by absolute index ([1:v], [2:v], ...), so slipping an
        # input in ahead of them would quietly repoint the badge at the wav.
        amap = "0:a:0?"                  # '?': a silent source is not an error
        if dub:
            extra += ["-i", dub]
            amap = "%d:a:0" % n_in       # mandatory: a dub with no audio
                                         # stream must fail loudly
        if chain:
            # the badge animates on the OUTPUT clock, which -ss rebases to 0,
            # so every clip starts its cycle at the same place
            args = ["-filter_complex", ";".join(chain),
                    "-map", "[%s]" % label, "-map", amap]
        else:
            args = ["-map", "0:v:0", "-map", amap]
        args += ["-c:v", render["encoder"], "-preset", render["preset"],
                 "-rc", "vbr", "-cq", str(render["cq"]),
                 # NVENC ignores -cq unless the average bitrate target is unset
                 "-b:v", "0", "-maxrate", render["maxrate"], "-bufsize", render["bufsize"],
                 "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", render["audio_bitrate"], "-ac", "2"]
    tmp = dst + ".part.mp4"
    # -ss goes BEFORE -i so it seeks the input: ffmpeg decodes from the
    # preceding keyframe and discards what precedes it, landing the cut on the
    # requested frame. -t goes AFTER every input, because an option placed
    # before an -i attaches to THAT input -- with badge PNGs in the graph a -t
    # sitting next to the source would silently become the PNG's duration and
    # leave the clip running to the end of the source.
    # -progress publishes the encode's position for the status line; the clip's
    # own duration is the total, since -ss already rebased the output clock.
    job = os.path.splitext(os.path.basename(dst))[0]
    prog = _progress.begin(job, dur, os.path.relpath(dst, ROOT), kind="clip")
    cmd = (["ffmpeg", "-hide_banner", "-v", "error", "-nostdin",
            "-progress", prog, "-ss", "%.3f" % start, "-i", src]
           + extra + args + ["-t", "%.3f" % dur, "-movflags", "+faststart", "-y", tmp])
    try:
        rc = run(cmd).returncode
    finally:
        _progress.end(job)
    if rc:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit("ffmpeg failed for %s" % dst)
    # On Windows a media player holding the previous render open makes this
    # rename fail with EACCES, throwing away a finished encode over a file lock.
    # The lock clears as soon as the player lets go, so wait for it rather than
    # asking for the whole clip again -- and if it never clears, keep the batch
    # going and let the caller report this one at the end.
    for attempt in range(6):
        try:
            os.replace(tmp, dst)
            return True
        except PermissionError:
            if attempt == 5:
                print("  %s is still locked; the finished render is at %s"
                      % (dst, tmp), flush=True)
                return False
            wait = 5.0 * (attempt + 1)
            print("  %s is open in another program -- retry %d/5 in %.0fs"
                  % (os.path.basename(dst), attempt + 1, wait), flush=True)
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", help="comma-separated clip ids to build")
    ap.add_argument("--outdir", help="override the manifest outdir")
    ap.add_argument("--copy", action="store_true",
                    help="stream-copy instead of re-encoding (fast, keyframe-snapped)")
    ap.add_argument("--force", action="store_true", help="rebuild existing outputs")
    ap.add_argument("--list", action="store_true",
                    help="resolve boundaries and print the plan, cut nothing")
    ap.add_argument("--handle", help="burn in this social handle, e.g. @name "
                                     "(overrides the manifest)")
    ap.add_argument("--handle-preset", help="override the manifest handle preset")
    ap.add_argument("--no-handle", action="store_true", help="skip the handle badge")
    ap.add_argument("--vertical", action="store_true",
                    help="crop to 1080x1920 (overrides the manifest)")
    ap.add_argument("--no-vertical", action="store_true", help="keep the source framing")
    ap.add_argument("--caption-style", help="burn captions using this preset")
    ap.add_argument("--no-captions", action="store_true", help="skip burning captions")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the caption sync proof (not recommended)")
    ap.add_argument("--dub", metavar="DIR",
                    help="use the dubbed track and translated word timings from "
                         "this directory (see dub-clips.py) instead of the "
                         "source audio and transcript")
    ap.add_argument("--dub-tag",
                    help="language tag on the dub files and the output name "
                         "(default: the manifest's dub.tag, else en)")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit("%s not on PATH" % tool)

    m = json.load(open(args.manifest, encoding="utf-8"))
    src = m["source"]
    if not os.path.exists(src):
        sys.exit("source not found: %s" % src)
    outdir = args.outdir or m.get("outdir", "outputs/shorts")
    os.makedirs(outdir, exist_ok=True)
    prefix = m.get("prefix", "")
    pad = m.get("pad", {})
    pad_head, pad_tail = float(pad.get("head", 0.12)), float(pad.get("tail", 0.30))
    words = _outline.load_words(m["words"]) if m.get("words") else []
    src_dur = probe(src)
    dubdir = args.dub or (m.get("dub") or {}).get("dir")
    dub_tag = args.dub_tag or (m.get("dub") or {}).get("tag") or "en"

    # One badge render for the whole manifest: every clip shares the source's
    # dimensions, and the animation is driven by the output clock, so each clip
    # starts its cycle from the same place.
    hcfg = dict(m.get("handle") or {})
    if args.handle:
        hcfg["text"] = args.handle
    if args.handle_preset:
        hcfg["preset"] = args.handle_preset
    src_w, src_h = _handle.probe_dims(src)
    fps = probe_fps(src)
    tmpdir = m.get("tmp", "temp")

    vert = m.get("vertical") or None
    if args.vertical:
        vert = dict(vert or {}, width=1080, height=1920)
    if args.no_vertical:
        vert = None
    out_w, out_h = (int(vert["width"]), int(vert["height"])) if vert else (src_w, src_h)

    caps = m.get("captions") or None
    if args.caption_style:
        caps = dict(caps or {}, style=args.caption_style)
    if args.no_captions:
        caps = None
    if caps and not m.get("words") and not dubdir:
        sys.exit("captions need a words transcript in the manifest")

    if args.copy and (vert or caps or (hcfg.get("text") and not args.no_handle)):
        # refuse here, not deep inside cut(): by then a caption build and a
        # 24-frame sync verification have already been paid for
        sys.exit("--copy cannot crop, caption or brand: stream copy does not "
                 "filter. Pass --no-vertical --no-captions --no-handle, or "
                 "drop --copy.")
    if args.copy and dubdir:
        sys.exit("--copy cannot carry a dub: a keyframe-snapped cut desyncs it")

    # DEFAULT_RENDER <- caption preset render block <- manifest render block,
    # same precedence run-captions.py uses -- the presets carry an encoding
    # intent (p6/cq20) that used to be silently discarded here
    render = dict(DEFAULT_RENDER)
    if caps:
        try:
            with open(os.path.join(ROOT, caps["style"]), encoding="utf-8") as f:
                render.update(json.load(f).get("render") or {})
        except (OSError, ValueError):
            pass
    render.update(m.get("render", {}))

    # When anything precedes the badge, [0:v] is already consumed by that chain
    # and the badge has to composite onto its tail instead.
    base = "vbase" if (vert or caps) else "0:v"

    overlay = None
    if hcfg.get("text") and not args.no_handle:
        # size the badge to the OUTPUT frame, not the source: a vertical crop
        # changes both dimensions under it
        overlay = _handle.prepare(hcfg.get("preset", _handle.DEFAULT_PRESET),
                                  hcfg["text"], out_w, out_h, tmpdir, base=base)
        print("handle %s  (%s)" % (hcfg["text"],
                                   hcfg.get("preset", _handle.DEFAULT_PRESET)))
    # Face-tracked crop centres from auto-reframe.py, if that has been run.
    reframe = {}
    rpath = m.get("reframe") or (os.path.splitext(args.manifest)[0] + ".reframe.json")
    if vert and not m.get("crop_rect") and os.path.exists(rpath):
        reframe = json.load(open(rpath, encoding="utf-8"))
        print("reframe %s (%d clips)" % (rpath, len(reframe)))
    if vert:
        print("vertical %dx%d from %dx%d" % (out_w, out_h, src_w, src_h))
    if caps:
        print("captions %s" % caps["style"])

    if dubdir:
        print("dub %s (.%s)" % (dubdir, dub_tag))

    wanted = set(x.strip() for x in args.only.split(",")) if args.only else None
    plan, missing_dub = [], []
    # Image overlays: a manifest-level list applies to every clip, and a clip
    # may carry its own instead. Windows are in CLIP time -- -ss rebases the
    # output clock to zero -- so a negative `at` counts back from the clip's own
    # end, and one end card can ride every short in the batch.
    img_preset = m.get("overlay_preset", _imgoverlay.DEFAULT_PRESET)
    img_default = m.get("image_overlays") or []
    img_preset_doc = json.load(open(
        _imgoverlay._overlay.repo_path(img_preset), encoding="utf-8")) \
        if (img_default or any(c.get("image_overlays") for c in m["clips"])) \
        else {}

    for clip in m["clips"]:
        if wanted and clip["id"] not in wanted:
            continue
        start, end = resolve(clip, words, pad_head, pad_tail)
        if end > src_dur:
            sys.exit("%s: end %.2f is past the source (%.2f)" % (clip["id"], end, src_dur))
        name = "%s-%s" % (prefix, clip["id"]) if prefix else clip["id"]
        dub_wav = dub_words = None
        absent = []
        if dubdir:
            stem = os.path.join(dubdir, name)
            dub_wav = "%s.%s.wav" % (stem, dub_tag)
            dub_words = "%s.%s.words.json" % (stem, dub_tag)
            absent = [p for p in (dub_wav, dub_words) if not os.path.exists(p)]
            missing_dub += absent
            # a dubbed cut is a different deliverable, not a replacement
            name = "%s-%s" % (name, dub_tag)
        plan.append((clip, start, end, os.path.join(outdir, name + ".mp4"),
                     dub_wav, dub_words, not absent))

    if wanted:
        missing = wanted - set(c["id"] for c, *_ in plan)
        if missing:
            sys.exit("no such clip id: %s" % ", ".join(sorted(missing)))
    if not plan:
        sys.exit("nothing to do")

    for clip, start, end, dst, _dw, _dj, dub_ok in plan:
        print("%-20s %s -> %s  %5.1fs %s %s"
              % (clip["id"], hhmmss(start), hhmmss(end), end - start,
                 "" if not dubdir else ("dub:ok  " if dub_ok else "dub:MISSING"),
                 clip.get("title", "")))
        rect, place = clip_rect(clip, m) if vert else (None, {})
        if rect:
            _, _, geo = rect_chain(rect, place, src_w, src_h, out_w, out_h)
            print("  rect %dx%d+%d+%d -> %dx%d at y=%d on %s  (%.2fx)%s"
                  % (geo[0], geo[1], geo[2], geo[3], out_w, geo[4], geo[5],
                     geo[6], out_w / float(geo[0]),
                     ("  pan %d keys" % geo[7] if geo[7] else "")
                     + ("  %d mask(s)" % geo[8] if geo[8] else "")))
        for spec in (clip.get("image_overlays") or img_default):
            print("  %s" % _imgoverlay.describe(spec, img_preset_doc,
                                                end - start))
    if args.list:
        return                           # --list promises to cut nothing, so a
                                         # missing dub is information, not an error
    if missing_dub:
        sys.exit("missing dub artifacts:\n  %s\nrun dub-clips.py for those "
                 "clips first, or select the dubbed ones with --only"
                 % "\n  ".join(missing_dub))

    failed = []
    for clip, start, end, dst, dub_wav, dub_words, _ok in plan:
        if os.path.exists(dst) and not args.force:
            print("skip (exists) %s" % dst)
            continue
        print("cutting %s ..." % os.path.basename(dst), flush=True)
        parts, last = [], None
        rect, place = clip_rect(clip, m) if vert else (None, {})
        if rect:
            chain, last, geo = rect_chain(rect, place, src_w, src_h,
                                          out_w, out_h)
            parts.append(chain)
            print("  rect %dx%d+%d+%d -> %dx%d at y=%d on %s%s"
                  % (geo[0], geo[1], geo[2], geo[3], out_w, geo[4], geo[5],
                     geo[6], "  pan %d keys" % geo[7] if geo[7] else "")
                  + ("  %d mask(s)" % geo[8] if geo[8] else ""))
        elif vert:
            cw, ch, cx, cy = crop_box(clip, src_w, src_h, out_w, out_h)
            entry = clip.get("crop_keys") or reframe.get(clip["id"])
            # the sidecar is either a bare key list (pan/shot) or {keys, pad}
            if isinstance(entry, dict):
                keys, pads = entry.get("keys"), entry.get("pad") or []
            else:
                keys, pads = entry, clip.get("crop_pad") or []
            if keys:
                if not clip.get("crop_keys") and ("crop_x" in clip
                                                  or "crop_pad" in clip):
                    print("  note: the .reframe.json sidecar overrides this "
                          "clip's crop_x/crop_pad (only crop_keys wins over "
                          "the sidecar)")
                # No eval=frame here: crop has no such option (that is scale and
                # overlay). Its x/y are flagged runtime-tunable and already
                # re-evaluated every frame, which is what makes the pan work.
                crop_f = "crop=%d:%d:x=%s:y=%d" % (
                    cw, ch, _handle.esc(crop_x_expr(keys, cw / 2.0,
                                                    src_w - cw / 2.0, cw)), cy)
            else:
                crop_f = "crop=%d:%d:%d:%d" % (cw, ch, cx, cy)
            chain, last = vertical_chain(crop_f, pads, out_w, out_h)
            parts.append(chain)
            if pads:
                print("  letterboxing %d shot(s), %.0f%% of the clip"
                      % (len(pads), 100.0 * sum(b - a for a, b in pads) / (end - start)))
        if caps:
            # captions are drawn AFTER the crop, so they are sized for the frame
            # the viewer sees rather than cropped along with the source pixels
            ass = build_captions(clip, dub_words or m["words"],
                                 caps["style"], start, end,
                                 out_w, out_h, fps, tmpdir,
                                 verify=not args.no_verify,
                                 samples=int(caps.get("samples", 24)),
                                 overlays=caps.get("overlays"),
                                 fontsdir=caps.get("fontsdir", "fonts"))
            # captions go on top of the composite, so they are never letterboxed
            # along with the shot underneath them
            parts.append("[%s]ass=filename=%s:fontsdir=%s:shaping=simple[%s]"
                         % (last or "0:v", ass, caps.get("fontsdir", "fonts"), base))
        elif last:
            parts.append("[%s]null[%s]" % (last, base))
        pre_chain = ";".join(parts) if parts else None

        # The badge, if any, has already claimed inputs 1..N and the tail of the
        # chain; the card composites onto whatever that left.
        img = None
        img_specs = clip.get("image_overlays") or img_default
        if img_specs and not args.copy:
            img_base = overlay[2] if overlay else (base if parts else "0:v")
            pngs, ifc, iout = _imgoverlay.prepare(
                img_preset, img_specs, out_w, out_h, tmpdir,
                tag=clip["id"], base=img_base,
                first_input=1 + (len(overlay[0]) if overlay else 0),
                runtime=end - start)
            img = (pngs, ifc, iout)

        if not cut(src, dst, start, end - start, render, args.copy, overlay,
                   pre_chain, base, dub_wav, img, fps):
            failed.append(dst)
            continue
        got, want = probe(dst), end - start
        if args.copy:
            if abs(got - want) > 0.5:
                # -ss with -c copy snaps to the preceding keyframe; running a
                # GOP long is what stream copy costs, not a broken render
                print("  note: %.2fs vs %.2fs requested -- stream copy snaps "
                      "to keyframes" % (got, want))
        elif abs(got - want) > 0.5:
            sys.exit("%s: duration %.2fs, expected %.2fs" % (dst, got, want))

        # The picture, asked about directly. A graph bounded by a one-frame
        # input yields full-length audio over a single video frame (or none),
        # and the duration check above waves it straight through.
        vw, vh, frames = probe_video(dst)
        if not vw:
            sys.exit("%s: no video stream -- the filter graph produced audio "
                     "only" % dst)
        if not args.copy and (vw, vh) != (out_w, out_h):
            sys.exit("%s: %dx%d, expected %dx%d" % (dst, vw, vh, out_w, out_h))
        if frames < max(2, int(got * 0.5)):
            sys.exit("%s: %d video frames for %.2fs -- something bounded the "
                     "graph early (a non-looped image input under shortest=1 "
                     "does exactly this)" % (dst, frames, got))

        meta = dict(clip, source=src, start=round(start, 3), end=round(end, 3),
                    duration=round(got, 3), stream_copy=bool(args.copy),
                    dub=dub_wav, dub_words=dub_words,
                    render=None if args.copy else render)
        with open(os.path.splitext(dst)[0] + ".json", "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("  %s  %.2fs  %.1f MB" % (dst, got, os.path.getsize(dst) / 1e6))
        _project.record(
            _project.project_id(m, args.manifest), "render",
            out=dst, script=__file__, argv=sys.argv[1:],
            kind="short-dubbed" if dub_wav else "short",
            manifest=args.manifest,
            sidecars={"clip": os.path.splitext(dst)[0] + ".json",
                      "dub-audio": dub_wav, "dub-words": dub_words},
            burned=[b for b in (
                ("source rect %s fitted to %d wide on %s"
                 % (tuple(rect), out_w, place.get("background", "blur"))
                 if rect else "9:16 crop per reframe sidecar")
                if m.get("vertical") else None,
                "word-synced captions, style %s" % caps["style"] if caps else None,
                "handle badge %s" % (m.get("handle") or {}).get("text")
                if (m.get("handle") or {}).get("text") else None,
                "dubbed audio .%s" % dub_tag if dub_wav else None) if b]
            + [_imgoverlay.describe(s, img_preset_doc, end - start)
               for s in (clip.get("image_overlays") or img_default)])
    if failed:
        sys.exit("locked by another program, not replaced: %s\n(each finished "
                 "render is beside its target as .part.mp4)" % ", ".join(failed))


if __name__ == "__main__":
    main()
