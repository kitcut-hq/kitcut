#!/usr/bin/env python
"""Cut a film out of silent screen recordings: drop the dead air, speed the
waiting, blur what must not be published, in one NVENC pass per source.

`screencast-cut.py` cuts a screencast against a camera take that carries the
sound. This one has no sound at all -- a Windows window-capture with no
microphone writes a digitally silent AAC track (-91 dB), so every
silence-driven decision in that pipeline degenerates to "cut everything" or
"cut nothing". The picture is the only signal, and `screen-activity.py`
measures it.

THE THREE-WAY DECISION. A two-way keep/drop is wrong for a screencast of an
agent working, because two very different things both count as "moving": the
human driving a checkout, and an AI streaming text into a side panel. So each
sample is classified from the per-REGION activity tracks:

    main moving                 -> keep at 1x      the work
    only panel moving           -> speed up        the AI thinking out loud
    nothing moving              -> drop            dead air

`drop` and `speed` are separately thresholded and separately priced, and
--list sweeps them without encoding a frame. Guessing here is expensive: on
this film the difference between speeding the panel and keeping it was eleven
minutes of runtime.

BLUR IS APPLIED IN SOURCE TIME, BEFORE THE CUT. This is the same trap as the
name label's `at` being film time: once segments are dropped, a window
measured on the source no longer lands where it was measured. Rather than map
every window through the cut, the blur runs upstream of the trim, so a rect
you verified against a source timecode stays verified. --sheet proves each one
on a real frame before an encode is spent.

The scale to the output canvas also happens BEFORE the blur, so blur rectangles
are fractions of the source frame (what you can actually measure on a frame
grab) and the expensive filter runs at 1080p instead of 4K.

Invoke as:  python scripts/screen-cut.py --manifest projects/<id>/screen.json --list
"""
import sys
import os
import json
import argparse
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import _project  # noqa: E402
import _progress  # noqa: E402

ROOT = _env.ROOT

DEFAULTS = {
    "canvas": [1920, 1080],
    "fps": 30,
    "drop_still": 0.002,      # below this, a region counts as not moving
    "hold": 1.0,              # seconds a region stays "moving" after it moved
    "panel_hold": 2.0,        # the panel streams in packets; hold it longer
    "min_drop": 1.5,          # seconds; shorter dead runs are not worth cutting
    "min_speed": 3.0,         # seconds; shorter waits are not worth a speed ramp
    "min_keep": 1.2,          # seconds; shorter 1x islands stutter, so absorb
    "speed": 6.0,             # how fast to run the "AI is thinking" stretches
    "keep_speed": 1.0,        # how fast to run the working stretches
    "air": 0.30,              # seconds of stillness kept at each join, for breath
    "speed_badge": True,
    # A filled box, not a pixelate, and both halves of that are measured.
    # SPEED: 18 rects on one source cost 35 s per 10 s of video as pixelate
    # chains and 2 s as drawbox -- 17x, because each pixelate rect is its own
    # split / crop / scale-down / scale-up / overlay and the whole chain runs
    # per frame whether its `enable` window is open or not.
    # SAFETY: a box has nothing left to reconstruct. Pixelation of known-format
    # text is not a one-way function.
    "blur_mode": "box",
    "box_color": "0x15151C",
    "backdrop": "0x101014",
    # drawtext with no fontfile falls back to fontconfig, which on Windows
    # cannot load a default config and kills the render. Never leave it unset.
    "badge_font": "fonts/Montserrat-Bold.ttf",
}


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}"


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    return {"width": int(st.get("width") or 0), "height": int(st.get("height") or 0),
            "fps": float(num) / float(den) if float(den or 0) else 0.0,
            "duration": float((d.get("format") or {}).get("duration") or 0.0)}


def load_activity(track_path):
    with open(_env.resolve(track_path), encoding="utf-8") as f:
        return json.load(f)


def hold_on(flag, fps, seconds):
    """Dilate a boolean track forward and back by `seconds`.

    Screen activity is bursty in a way that means nothing: text streams in
    packets, a scroll is a flick and a wait, a cursor blinks. Thresholding the
    raw track produces hundreds of half-second runs and a film that strobes
    between 1x and 6x. "It moved within the last second, so it is still
    moving" is what a viewer perceives anyway, and it is the single change
    that took this cut from 1094 segments to something watchable.
    """
    k = int(round(seconds * fps))
    if k <= 0 or flag.size == 0:
        return flag
    out = flag.copy()
    for s in range(1, k + 1):
        out[s:] |= flag[:-s]
        out[:-s] |= flag[s:]
    return out


def classify(track, cfg):
    """Per-sample label: 2 = keep, 1 = speed, 0 = drop.

    A source with no named regions has nothing to tell "work" from "waiting",
    so it degrades honestly to keep/drop rather than inventing a speed class.
    """
    ra = track.get("region_activity") or {}
    n = len(track["activity"])
    thr = cfg["drop_still"]
    fps = track["sample_fps"]
    hold = cfg["hold"]
    if "main" in ra:
        main = hold_on(np.array(ra["main"][:n], float) >= thr, fps, hold)
        panel = hold_on(np.array(ra.get("panel", [0.0] * n)[:n], float) >= thr,
                        fps, cfg.get("panel_hold", hold))
        lab = np.zeros(n, np.int8)
        lab[panel] = 1
        lab[main] = 2
    else:
        act = hold_on(np.array(track["activity"], float) >= thr, fps, hold)
        lab = np.where(act, 2, 0).astype(np.int8)
    return lab


def _runs_of(lab):
    out = []
    i = 0
    n = lab.size
    while i < n:
        j = i
        while j < n and lab[j] == lab[i]:
            j += 1
        out.append([i, j, int(lab[i])])
        i = j
    return out


def smooth(lab, fps, cfg):
    """Turn a per-sample label track into segments a cut can use.

    Two passes, and both exist because the naive version produced a film that
    stutters:

      1. Any run shorter than its class minimum is absorbed into a NEIGHBOUR,
         repeatedly until nothing short is left. Absorbing into the longer
         neighbour rather than always promoting to "keep" matters: a
         half-second of panel flicker in the middle of a two-minute wait
         belongs to the wait, and promoting it to 1x put a visible hitch in
         the middle of every fast-forward.
      2. `air` seconds are handed back at each end of a dropped run AT 1x, so
         a cut lands on stillness and the film breathes. Handing it back as
         *sped* footage, which the first version did, is not breath -- it is a
         quarter-second lurch on either side of every join.
    """
    lab = lab.copy()
    mins = {0: cfg["min_drop"], 1: cfg["min_speed"], 2: cfg.get("min_keep", 1.0)}
    for _ in range(12):
        rs = _runs_of(lab)
        if len(rs) < 2:
            break
        short = [r for r in rs if (r[1] - r[0]) < mins[r[2]] * fps]
        if not short:
            break
        # shortest first, so a decision is never made against a run that is
        # about to disappear anyway
        r = min(short, key=lambda r: r[1] - r[0])
        k = rs.index(r)
        left = rs[k - 1] if k > 0 else None
        right = rs[k + 1] if k + 1 < len(rs) else None
        cands = [c for c in (left, right) if c is not None]
        take = max(cands, key=lambda c: c[1] - c[0])
        lab[r[0]:r[1]] = take[2]

    air = int(round(cfg["air"] * fps))
    if air:
        for a, b, c in _runs_of(lab):
            if c != 0 or (b - a) <= 2 * air + 1:
                continue
            lab[a:a + air] = 2
            lab[b - air:b] = 2
    return lab


def segments(lab, fps, dur):
    """Contiguous same-class runs as (start_s, end_s, class)."""
    out = []
    n = lab.size
    i = 0
    while i < n:
        j = i
        while j < n and lab[j] == lab[i]:
            j += 1
        out.append((i / fps, min(dur, j / fps), int(lab[i])))
        i = j
    return out


def plan_source(src, cfg):
    """Segments plus the arithmetic that prices them, for one source."""
    track = load_activity(src["activity"])
    fps = track["sample_fps"]
    dur = track["duration"]
    lab = smooth(classify(track, cfg), fps, cfg)
    segs = segments(lab, fps, dur)

    lo, hi = src.get("trim", [0.0, dur])
    hi = min(hi if hi else dur, dur)
    segs = [(max(a, lo), min(b, hi), c) for a, b, c in segs]
    segs = [(a, b, c) for a, b, c in segs if b - a > 1.0 / fps]

    # Windows the manifest insists on: forced to 1x whatever the picture is
    # doing, because "show each of the eight books" is a content requirement
    # and no motion metric knows which page matters.
    holds = [tuple(w) for w in (src.get("hold_1x") or [])]

    def overlaps_hold(a, b):
        return any(not (b <= w0 or a >= w1) for w0, w1 in holds)

    kept = []
    for a, b, c in segs:
        if c == 0 and not overlaps_hold(a, b):
            continue
        if overlaps_hold(a, b):
            speed = 1.0
        else:
            speed = cfg["speed"] if c == 1 else cfg["keep_speed"]
        kept.append({"start": round(a, 3), "end": round(b, 3), "speed": speed,
                     "out": round((b - a) / speed, 3)})
    # merge neighbours that survived at the same speed
    merged = []
    for s in kept:
        if merged and abs(merged[-1]["end"] - s["start"]) < 1e-6 and \
                merged[-1]["speed"] == s["speed"]:
            merged[-1]["end"] = s["end"]
            merged[-1]["out"] = round((merged[-1]["end"] - merged[-1]["start"])
                                      / merged[-1]["speed"], 3)
        else:
            merged.append(dict(s))
    return {
        "src": src, "duration": dur, "window": [lo, hi],
        "segments": merged,
        "in_s": sum(s["end"] - s["start"] for s in merged),
        "out_s": sum(s["out"] for s in merged),
        "keep_s": sum(s["end"] - s["start"] for s in merged
                      if s["speed"] <= cfg["keep_speed"]),
        "sped_in_s": sum(s["end"] - s["start"] for s in merged
                         if s["speed"] > cfg["keep_speed"]),
        "dropped_s": (hi - lo) - sum(s["end"] - s["start"] for s in merged),
        "sped": sum(1 for s in merged if s["speed"] != 1.0),
    }


def esc(p):
    """A path as an ffmpeg filter argument wants it."""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def blur_chain(blurs, cw, ch, label_in, label_out, cfg):
    """Rect blurs in SOURCE time, on the already-scaled frame.

    Each rect is its own crop/blur/overlay pair rather than one masked pass,
    because the rects have different lifetimes and overlay's `enable` is the
    only per-time gate that costs nothing outside its window.
    """
    parts = []
    cur = label_in
    for i, b in enumerate(blurs):
        x, y, w, h = b["rect"]
        px = max(2, int(round(x * cw)) // 2 * 2)
        py = max(2, int(round(y * ch)) // 2 * 2)
        pw = max(8, int(round(w * cw)) // 2 * 2)
        ph = max(8, int(round(h * ch)) // 2 * 2)
        strength = int(b.get("strength", 12))
        mode = b.get("mode") or cfg.get("blur_mode", "box")
        nxt = f"{label_out}{i}"
        if mode == "box":
            parts.append(f"[{cur}]drawbox=x={px}:y={py}:w={pw}:h={ph}:"
                         f"color={b.get('color', cfg.get('box_color', 'black'))}"
                         f":t=fill" + gate(b) + f"[{nxt}]")
        else:
            # pixelate reads as "deliberately hidden"; a soft blur can read as
            # a focus artefact and invites someone to try to sharpen it back.
            parts.append(f"[{cur}]split[{nxt}a][{nxt}b]")
            parts.append(f"[{nxt}b]crop={pw}:{ph}:{px}:{py},"
                         f"scale={max(2, pw // strength) // 2 * 2}:"
                         f"{max(2, ph // strength) // 2 * 2}:flags=area,"
                         f"scale={pw}:{ph}:flags=neighbor[{nxt}c]")
            parts.append(f"[{nxt}a][{nxt}c]overlay=x={px}:y={py}"
                         + gate(b) + f"[{nxt}]")
        cur = nxt
    return parts, cur


def gate(b):
    """`enable` for a blur that only applies over part of the source."""
    w = b.get("when")
    if not w:
        return ""
    return f":enable='between(t\\,{w[0]}\\,{w[1]})'"


def build_filter(plan, cfg, idx):
    """One source -> one filtergraph producing [vN] on the output canvas.

    Order matters and is not arbitrary: scale, then blur, then trim. Scaling
    first makes the blur run at 1080p rather than 4K; blurring before the trim
    keeps every blur window in SOURCE time, which is the only timebase a human
    can verify a rect against.
    """
    cw, ch = cfg["canvas"]
    info = plan["info"]
    # fit inside the canvas, preserving aspect; pad happens after the concat
    sw, sh = info["width"], info["height"]
    fit = min(cw / sw, ch / sh)
    vw = max(2, int(round(sw * fit)) // 2 * 2)
    vh = max(2, int(round(sh * fit)) // 2 * 2)

    if (sw, sh) == (vw, vh):
        # Already at the working size -- a proxy, or a source that happened to
        # match. Re-scaling identical dimensions is a resample for nothing.
        parts = [f"[{idx}:v]setsar=1[s{idx}]"]
    else:
        parts = [f"[{idx}:v]scale={vw}:{vh}:flags=lanczos,setsar=1[s{idx}]"]
    cur = f"s{idx}"
    blurs = plan["src"].get("blur") or []
    if blurs:
        bp, cur = blur_chain(blurs, vw, vh, cur, f"b{idx}_", cfg)
        parts += bp

    segs = plan["segments"]
    parts.append(f"[{cur}]split={len(segs)}" +
                 "".join(f"[t{idx}_{i}]" for i in range(len(segs))))
    outs = []
    for i, s in enumerate(segs):
        sp = s["speed"]
        pts = "PTS-STARTPTS" if sp == 1.0 else f"(PTS-STARTPTS)/{sp}"
        parts.append(f"[t{idx}_{i}]trim=start={s['start']}:end={s['end']},"
                     f"setpts={pts}[c{idx}_{i}]")
        outs.append(f"[c{idx}_{i}]")
    parts.append("".join(outs) + f"concat=n={len(segs)}:v=1:a=0[p{idx}]")
    # Fill the canvas HERE, per source, not once after the cross-source
    # concat: `concat` refuses inputs of differing size, and this film mixes a
    # 3840x2280 desktop capture (-> 1818x1080) with a 1008x2244 phone screen
    # recording (-> 484x1080). Padding late fails with "Input link parameters
    # do not match", which reads like a bug in the cut and is not.
    covers = (vw * vh) / float(cw * ch)
    if cfg.get("backdrop") == "blur" and covers < 0.9:
        # A portrait phone clip in a landscape film is two thirds black bar.
        # Filling them with a blurred, darkened copy of the same frame reads as
        # a deliberate treatment instead of a mistake. Only where it is worth
        # it: on a 1818x1080 desktop frame the bars are 51 px and a gblur pass
        # over the whole canvas would be spent on almost nothing.
        parts.append(f"[p{idx}]split[f{idx}][g{idx}]")
        parts.append(f"[g{idx}]scale={cw}:{ch}:force_original_aspect_ratio=increase,"
                     f"crop={cw}:{ch},gblur=sigma=32,eq=brightness=-0.18[gb{idx}]")
        parts.append(f"[gb{idx}][f{idx}]overlay=(W-w)/2:(H-h)/2,"
                     f"setsar=1[v{idx}]")
    else:
        color = cfg["backdrop"] if cfg.get("backdrop") != "blur" else "0x101014"
        parts.append(f"[p{idx}]pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:"
                     f"color={color},setsar=1[v{idx}]")
    return parts, vw, vh


def badge_filter(plans, cfg, label_in, label_out):
    """A '>> 6x' corner tag over every sped stretch, in OUTPUT time.

    Without it a speed ramp reads as a glitch. The windows are computed from
    the plan rather than declared, so they cannot drift out of step with the
    cut the way a hand-written timecode would.
    """
    # Only the WAITING class is badged, not "anything faster than 1x". Under
    # --target the working footage is sped up too (3.18x here), so a
    # speed != 1.0 test badges the entire film and tells the viewer nothing.
    base = cfg["keep_speed"]
    wins = []
    t = 0.0
    for p in plans:
        for s in p["segments"]:
            if s["speed"] > base * 1.5:
                wins.append((t, t + s["out"], s["speed"]))
            t += s["out"]
    if not wins:
        return [], label_in, 0.0
    # merge windows that touch, or the enable expression grows to hundreds of
    # terms and drawtext re-evaluates all of them on every frame
    wins.sort()
    merged = [list(wins[0])]
    for a, b, sp in wins[1:]:
        if a - merged[-1][1] < 0.05:
            merged[-1][1] = b
            merged[-1][2] = max(merged[-1][2], sp)
        else:
            merged.append([a, b, sp])
    wins = [tuple(w) for w in merged]
    cw, ch = cfg["canvas"]
    font = cfg.get("badge_font")
    size = max(18, int(ch * 0.030))
    pad = int(ch * 0.022)
    en = "+".join(f"between(t\\,{a:.3f}\\,{b:.3f})" for a, b, _ in wins)
    # Relative to the working footage, not absolute. Under --target the whole
    # film runs fast, so "19x" would be true of the encode and meaningless to
    # a viewer -- what they are seeing is this stretch running 6x the rest.
    rel = sorted({round(w[2] / base) for w in wins})
    text = f"{rel[0]}x faster" if len(rel) == 1 else "faster"
    d = (f"[{label_in}]drawtext=text='>> {text}':"
         f"x=w-tw-{pad}:y={pad}:fontsize={size}:fontcolor=white@0.92:"
         f"box=1:boxcolor=0x000000@0.55:boxborderw={size // 3}:"
         f"enable='{en}'")
    if font:
        d += f":fontfile='{esc(_env.resolve(font))}'"
    return [d + f"[{label_out}]"], label_out, sum(b - a for a, b, _ in wins)


def source_cmd(plan, cfg, out_path, prog=None):
    """One ffmpeg invocation for ONE source: cut, blur, pad, badge, encode.

    Deliberately not one giant graph across every source. ffmpeg demuxes all of
    a `concat` filter's file inputs CONCURRENTLY and buffers the ones it is not
    consuming yet, so a ten-input graph over 47 minutes of 1080p climbed past
    2.8 GB of RAM and stopped emitting frames entirely. Per source the memory
    is bounded, and the pieces are then joined by the concat DEMUXER with
    `-c copy`, which re-encodes nothing.

    The badge is drawn here rather than after the join, because that is what
    keeps the join a stream copy. badge_filter() is handed a single-plan list
    so its output timeline starts at zero -- this source's own local time,
    which is exactly what a per-source pass needs.
    """
    parts, _, _ = build_filter(plan, cfg, 0)
    last = "v0"
    if cfg.get("speed_badge"):
        bp, last, _ = badge_filter([plan], cfg, "v0", "badged")
        parts += bp
    parts.append(f"[{last}]fps={cfg['fps']},format=yuv420p[out]")

    # The graph goes in a FILE, not on the command line. Windows caps a command
    # line at 32767 characters and one source's graph is already past it (273
    # segments on the longest recording), so passing it inline dies with
    # "WinError 206: The filename or extension is too long", which names the
    # wrong thing entirely and sends you hunting for a long path.
    gpath = os.path.splitext(out_path)[0] + ".filtergraph.txt"
    os.makedirs(os.path.dirname(gpath), exist_ok=True)
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(";".join(parts))

    cmd = ["ffmpeg", "-v", "error", "-stats", "-nostdin", "-y"]
    if prog:
        cmd += ["-progress", prog]
    cmd += ["-i", plan["path"],
            "-filter_complex_script", gpath, "-map", "[out]", "-an",
            "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
            "-cq", str(cfg.get("cq", 21)), "-b:v", "0",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    return cmd, len(parts)


def run_ffmpeg(cmd, what):
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        tail = "\n".join((r.stderr or "").strip().splitlines()[-25:])
        raise SystemExit(f"ffmpeg failed on {what} ({r.returncode}):\n{tail}")


def render(plans, cfg, out_path, dry=False, prog=None):
    """Render each source, then join them without re-encoding."""
    piece_dir = os.path.join(os.path.dirname(out_path), "..", "temp", "cut")
    piece_dir = os.path.normpath(piece_dir)
    os.makedirs(piece_dir, exist_ok=True)
    total_out = sum(p["out_s"] for p in plans)
    pieces = []
    for i, p in enumerate(plans):
        base = os.path.splitext(os.path.basename(p["path"]))[0]
        dst = os.path.join(piece_dir, f"{i:02d}-{base}.mp4")
        cmd, nodes = source_cmd(p, cfg, dst, prog)
        pieces.append((p, dst, cmd, nodes))

    if dry:
        for p, dst, cmd, nodes in pieces:
            print(f"  {os.path.basename(p['path'])[:38]:<38} "
                  f"{len(p['segments']):>4} segs  {nodes:>4} filter nodes -> "
                  f"{os.path.basename(dst)}")
        print(f"\n  then concat demuxer, -c copy -> {os.path.basename(out_path)}")
        return None

    for i, (p, dst, cmd, nodes) in enumerate(pieces, 1):
        print(f"  [{i}/{len(pieces)}] {os.path.basename(p['path'])[:40]:<40} "
              f"{fmt(p['out_s']):>7}")
        run_ffmpeg(cmd, os.path.basename(p["path"]))

    listing = os.path.join(piece_dir, "concat.txt")
    with open(listing, "w", encoding="utf-8") as f:
        for _, dst, _, _ in pieces:
            f.write(f"file '{dst.replace(chr(92), '/')}'\n")
    print(f"  joining {len(pieces)} pieces (stream copy)")
    run_ffmpeg(["ffmpeg", "-v", "error", "-nostdin", "-y",
                "-f", "concat", "-safe", "0", "-i", listing,
                "-c", "copy", "-movflags", "+faststart", out_path], "concat")
    return total_out


def parse_hms(s):
    parts = [float(x) for x in str(s).split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def solve_target(man, cfg, target_s):
    """Scale both speeds until the film lands on `target_s`.

    A length is a decision, and this is the mode that prices it: the ratio
    between "work" and "waiting" is an editorial choice the manifest already
    made, so the solver moves both together rather than inventing a new one.
    Segments forced to 1x by `hold_1x` do not scale, which is the point of
    them -- the eight books stay watchable however short the film gets, and
    the solver reports the floor they impose.
    """
    lo, hi = 1.0, 24.0
    base_k, base_s = cfg["keep_speed"], cfg["speed"]
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        c = dict(cfg, keep_speed=base_k * mid, speed=base_s * mid)
        out = sum(plan_source(s, c)["out_s"] for s in man["sources"])
        best = (mid, out, c)
        if out > target_s:
            lo = mid
        else:
            hi = mid
        if abs(out - target_s) < 1.0:
            break
    mid, out, c = best
    print(f"  --target {fmt(target_s)}: x{mid:.2f} on both speeds -> "
          f"work {c['keep_speed']:.2f}x, waiting {c['speed']:.2f}x, "
          f"giving {fmt(out)}")
    if out > target_s + 5:
        print(f"  (floor: forced-1x `hold_1x` windows and the source count "
              f"keep it above {fmt(out)})")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="price the cut; measures and encodes nothing")
    ap.add_argument("--sweep", action="store_true",
                    help="price a grid of speed / drop settings")
    ap.add_argument("--sheet", metavar="DIR",
                    help="write a frame per blur rect and per kept segment "
                         "start, so both can be checked before an encode")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--speed", type=float)
    ap.add_argument("--keep-speed", type=float)
    ap.add_argument("--drop-still", type=float)
    ap.add_argument("--min-drop", type=float)
    ap.add_argument("--where", action="append", default=[], metavar="M:SS",
                    help="given a time in the FINISHED film, print which source "
                         "and which source timecode it came from, and the rect "
                         "transform between them; repeatable. This is how a "
                         "leak found by scanning the render gets traced back "
                         "to the manifest entry that should have covered it.")
    ap.add_argument("--no-proxy", action="store_true",
                    help="read the original sources even where a proxy exists")
    ap.add_argument("--target", metavar="M:SS",
                    help="solve for the speeds that land on this runtime, "
                         "keeping the panel:work ratio the manifest asks for")
    args = ap.parse_args()

    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cfg = dict(DEFAULTS)
    cfg.update(man.get("cut") or {})
    for k in ("speed", "keep_speed", "drop_still", "min_drop"):
        v = getattr(args, k, None)
        if v is not None:
            cfg[k] = v

    if args.target:
        cfg = solve_target(man, cfg, parse_hms(args.target))

    plans = []
    for s in man["sources"]:
        if s.get("skip"):
            # Left in the manifest, with its reason, rather than deleted: a
            # source dropped for a privacy reason must stay visible to the
            # next session, or someone re-adds it without knowing why it went.
            print(f"  skipping {os.path.basename(s['path'])}"
                  f"  -- {s.get('_skip_why', 'skip: true')}")
            continue
        p = plan_source(s, cfg)
        # Read the proxy when make-proxies.py has built one. It is the SAME
        # picture at the working size, and every rect in this pipeline is a
        # fraction of the frame rather than a pixel box, so nothing downstream
        # can tell which one it got. The 4K decode is the dominant cost of a
        # render and it does not need paying again on every iteration.
        chosen = _env.resolve(s["path"])
        proxy = s.get("proxy")
        if proxy and not args.no_proxy:
            pp = _env.resolve(proxy)
            if os.path.exists(pp):
                chosen = pp
            else:
                print(f"  proxy missing, reading the source: {proxy}")
        p["path"] = chosen
        p["source_path"] = _env.resolve(s["path"])
        p["is_proxy"] = chosen != p["source_path"]
        p["info"] = probe(p["path"])
        plans.append(p)

    tot_in = sum(p["window"][1] - p["window"][0] for p in plans)
    tot_out = sum(p["out_s"] for p in plans)
    nprox = sum(1 for p in plans if p["is_proxy"])
    print(f"{os.path.basename(mpath)}   {len(plans)} source(s)   "
          f"speed={cfg['speed']}x  drop_still={cfg['drop_still']}"
          f"   proxies={nprox}/{len(plans)}")
    hdr = (f"  {'source':<38} {'in':>7} {'drop':>7} {'1x':>7} "
           f"{'sped in':>7} {'out':>7} {'segs':>5}")
    print(hdr)
    for p in plans:
        print(f"  {os.path.basename(p['path'])[:38]:<38} "
              f"{fmt(p['window'][1] - p['window'][0]):>7} "
              f"{fmt(p['dropped_s']):>7} {fmt(p['keep_s']):>7} "
              f"{fmt(p['sped_in_s']):>7} {fmt(p['out_s']):>7} "
              f"{len(p['segments']):>5}")
    print(f"  {'TOTAL':<38} {fmt(tot_in):>7} "
          f"{fmt(sum(p['dropped_s'] for p in plans)):>7} "
          f"{fmt(sum(p['keep_s'] for p in plans)):>7} "
          f"{fmt(sum(p['sped_in_s'] for p in plans)):>7} "
          f"{fmt(tot_out):>7} {sum(len(p['segments']) for p in plans):>5}")

    if args.sweep:
        print(f"\n  {'speed':>6} {'drop':>7} {'min_drop':>9} {'out':>9} {'segs':>6}")
        for sp in (3.0, 4.0, 6.0, 8.0, 12.0):
            for ds in (0.001, 0.002, 0.004):
                c = dict(cfg, speed=sp, drop_still=ds)
                ps = [plan_source(s, c) for s in man["sources"]]
                print(f"  {sp:>6.0f} {ds:>7.3f} {c['min_drop']:>9.1f} "
                      f"{fmt(sum(x['out_s'] for x in ps)):>9} "
                      f"{sum(len(x['segments']) for x in ps):>6}")

    if args.where:
        where(plans, cfg, [parse_hms(w) for w in args.where])

    if args.sheet:
        sheet(plans, cfg, _env.resolve(args.sheet))

    if args.list or args.sweep or args.sheet or args.where:
        return

    out = _env.resolve(args.out or man["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if args.dry_run:
        render(plans, cfg, out, dry=True)
        return

    total_out = sum(p["out_s"] for p in plans)
    pid = os.path.basename(_project.find_project_dir(out) or "")
    job = pid or "screen-cut"
    # begin() RETURNS the path ffmpeg must write to; declaring the job without
    # wiring -progress leaves render-status.py reading an empty file, which it
    # correctly reports as "stalled" for the whole encode. Cleared in a finally,
    # so a crashed render does not freeze the status bar either.
    prog = _progress.begin(job, total_out, _project.norm(out), kind="screen-cut")
    try:
        print(f"\n  rendering {fmt(total_out)} -> {out}")
        render(plans, cfg, out, prog=prog)
    finally:
        _progress.end(job)

    got = probe(out)["duration"]
    if abs(got - total_out) > max(2.0, total_out * 0.02):
        raise SystemExit(f"FAIL: planned {fmt(total_out)} but rendered {fmt(got)}")
    print(f"  rendered {fmt(got)} (planned {fmt(total_out)})")

    if pid:
        blurs = sum(len(p["src"].get("blur") or []) for p in plans)
        _project.record(
            pid, "screen-cut", out=out, script=__file__, argv=sys.argv[1:],
            kind="film", manifest=mpath,
            burned={"cut": "activity-driven", "blur_rects": blurs,
                    "speed_badge": bool(cfg.get("speed_badge")),
                    "speed": cfg["speed"], "audio": "none (silent sources)"},
            note=f"{fmt(tot_in)} of sources -> {fmt(got)}")


def where(plans, cfg, times):
    """Film time -> source, source time, and the rect transform between them.

    Scanning the finished render is the check that catches what the source
    scans missed, but it reports a canvas-fraction rect at a film timecode and
    the manifest wants a SOURCE-fraction rect at a source timecode. Two
    transforms sit in between and both are easy to get wrong by hand: the cut
    (segments dropped, others run at 3x or 19x) and the pad (a 1818-wide frame
    centred in a 1920 canvas shifts x by 0.027 and scales it by 0.947).
    """
    cw, ch = cfg["canvas"]
    print("\n  film time -> source")
    for target in times:
        t = 0.0
        found = None
        for p in plans:
            for s in p["segments"]:
                if t <= target < t + s["out"]:
                    found = (p, s, target - t)
                    break
                t += s["out"]
            if found:
                break
        if not found:
            print(f"  {fmt(target):>8}  past the end of the film ({fmt(t)})")
            continue
        p, s, into = found
        src_t = s["start"] + into * s["speed"]
        info = p["info"]
        f = min(cw / info["width"], ch / info["height"])
        vw = max(2, int(round(info["width"] * f)) // 2 * 2)
        vh = max(2, int(round(info["height"] * f)) // 2 * 2)
        ox, oy = (cw - vw) / 2.0 / cw, (ch - vh) / 2.0 / ch
        sx, sy = vw / float(cw), vh / float(ch)
        print(f"  {fmt(target):>8}  {os.path.basename(p['source_path'])}"
              f"  @ {fmt(src_t)}   (segment {s['start']:.1f}-{s['end']:.1f} "
              f"at {s['speed']:.2f}x)")
        print(f"            canvas rect [X,Y] -> source rect "
              f"[(X-{ox:.4f})/{sx:.4f}, (Y-{oy:.4f})/{sy:.4f}]")


def sheet(plans, cfg, outdir):
    """Frame grabs that prove the two things a render cannot take back:
    every blur rect actually covers the thing it names, and every kept
    segment starts on something worth keeping."""
    os.makedirs(outdir, exist_ok=True)
    cw, ch = cfg["canvas"]
    n = 0
    for p in plans:
        base = os.path.splitext(os.path.basename(p["path"]))[0]
        info = p["info"]
        fit = min(cw / info["width"], ch / info["height"])
        vw = max(2, int(round(info["width"] * fit)) // 2 * 2)
        vh = max(2, int(round(info["height"] * fit)) // 2 * 2)
        blurs = p["src"].get("blur") or []
        for i, b in enumerate(blurs):
            w = b.get("when") or [p["window"][0], p["window"][1]]
            t = (w[0] + w[1]) / 2
            # Show the frame AS THE FILM WILL HAVE IT: every rect whose window
            # contains t, not just this one. A one-rect-at-a-time proof is
            # actively misleading -- it showed a card panel "covered" while an
            # IBAN two rects away sat in the clear, because the rect that was
            # supposed to catch it was drawn separately.
            #
            # The gates are then dropped ON PURPOSE. Seeking with -ss before -i
            # restarts timestamps at zero, so `between(t,18,46)` is false on a
            # frame grabbed from 32 s in and the preview comes back CLEAN --
            # which reads exactly like a rect that works. The render reads from
            # the start and keeps source time, so its gates are correct.
            active = [{k: v for k, v in o.items() if k != "when"}
                      for o in blurs
                      if not o.get("when")
                      or (o["when"][0] <= t <= o["when"][1])]
            parts, cur = blur_chain(active, vw, vh, "0:v", "bb_", cfg)
            fc = f"[0:v]scale={vw}:{vh}[s];" + \
                 ";".join(parts).replace("[0:v]", "[s]", 1)
            dst = os.path.join(outdir, f"{base}.blur{i}.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t),
                            "-i", p["path"], "-filter_complex", fc,
                            "-map", f"[{cur}]", "-frames:v", "1", dst],
                           check=True)
            n += 1
        for i, s in enumerate(p["segments"]):
            dst = os.path.join(outdir, f"{base}.seg{i:03d}."
                                       f"{'x%g' % s['speed']}.{s['start']:.1f}.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                            str(s["start"] + 0.2), "-i", p["path"],
                            "-vf", f"scale=640:-2", "-frames:v", "1", dst],
                           check=True)
            n += 1
    print(f"\n  wrote {n} frames -> {outdir}")


if __name__ == "__main__":
    main()
