#!/usr/bin/env python
"""A vertical YouTube Short cut from a finished 16:9 sketch-film episode.

A series episode (Duchess, Leo) is a two-to-five-minute crayon film. Its best moment, 40 to 60
seconds of it, makes a Short: the episode cropped to a 4:5 window that follows the action, set
full width in a 1080x1920 frame over a blurred copy of itself, a headline on a card in the top
band in the film's own paper, ink and accent, and the narration captioned word by word from the
film's own word timings (audio/vo/timeline.json) -- no transcription, so the captions are exact.

Cuts are named by QUOTING the narration (`from_text` / `to_text`), so they land in the gap
between two words; a numeric `from` / `to` is taken as is. Several segments join with a short
audio fade, so a Short may open on the series' own first line and jump to the payoff.

The output folder is a sketch-film folder that `studio/import_film.py` takes as it is
(sketch.json with a 9:16 frame at 30 fps, outputs/film.mp4, outputs/film_poster.png), so the
Short becomes a film of the series' project on kitcut.ai and is published to YouTube through the
site's queue like any episode.

The manifest (one per Short):

    { "src": "<the episode's folder: outputs/film.mp4 or outputs/r*/film.mp4, audio/vo/timeline.json>",
      "film": "studio-...",                       (the episode's id, for the record)
      "title": "Nobody trained for TWO dots",     (the headline, eight words or fewer)
      "segments": [ {"from_text": "This is Duchess.", "to_text": "dignified."},
                    {"from_text": "Victory.", "to_text": "come from."} ],
      "camera": {"x": 0.5, "keys": [[0, 0.5], [31.0, 0.62]]},   (the crop window's centre, as a
                                       fraction of the episode's width, over the SHORT's seconds)
      "picture": {"aspect": [1, 1], "y": 400},    (optional: a wider window than the style's 4:5)
      "out": "<folder to write>" }

`style` (default config/shorts/episode-short.json) holds every number of the look.

Invoke as:
    python scripts/episode-short.py --manifest m.json --list          (segments, cut gaps, length)
    python scripts/episode-short.py --manifest m.json --stills 0,12,30 (frames of the Short, no encode)
    python scripts/episode-short.py --manifest m.json                  (render)
"""

import os
import re
import sys
import glob
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402
import _project  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = _env.ROOT
STYLE = os.path.join("config", "shorts", "episode-short.json")


def fold(s):
    return re.sub(r"[^a-z0-9']+", " ", s.lower().replace("’", "'")).split()


def source_files(src):
    """The episode's master and its timeline: the newest version's render when it has versions."""
    vids = sorted(glob.glob(os.path.join(src, "outputs", "r*", "film.mp4")), key=os.path.getmtime)
    mp4 = vids[-1] if vids else os.path.join(src, "outputs", "film.mp4")
    tl = os.path.join(src, "audio", "vo", "timeline.json")
    for p in (mp4, tl):
        if not os.path.exists(p):
            sys.exit("missing %s" % p)
    return mp4, tl


def all_words(tl):
    out = []
    for ln in json.load(open(tl, encoding="utf-8"))["lines"]:
        for w in ln.get("words") or []:
            out.append(
                {"text": w["text"], "start": float(w["s"]), "end": float(w["e"]), "line": ln["i"]}
            )
    return out


def find(words, text, after=0.0, last=False):
    """Index of the first (or, with last, the final) word of `text` in the narration at or after
    `after` seconds. A quote that matches nothing, or more than once, is an error: a cut that
    quietly lands somewhere else is worse than none."""
    q = fold(text)
    # one token per folded piece, so "ninety-nine" matches "ninety-nine" and "ninety nine"
    toks = [(t, i) for i, w in enumerate(words) for t in fold(w["text"])]
    flat = [t for t, _ in toks]
    hits = []
    for k in range(len(flat) - len(q) + 1):
        if flat[k : k + len(q)] == q and words[toks[k][1]]["start"] >= after - 0.01:
            if k and toks[k - 1][1] == toks[k][1]:
                continue  # starts inside a word
            hits.append((toks[k][1], toks[k + len(q) - 1][1]))
    if not hits:
        sys.exit("quote not found in the narration (after %.2fs): %r" % (after, text))
    if len(hits) > 1:
        sys.exit(
            "quote %r is said %d times after %.2fs (at %s): quote more words"
            % (text, len(hits), after, ", ".join("%.1f" % words[a]["start"] for a, _ in hits))
        )
    return hits[0][1] if last else hits[0][0]


def resolve(man, words, pad, length):
    """[(t0, t1)] in the episode's seconds, never past its end (`length`): a cut padded past the
    last frame silently makes the Short shorter than its segments say."""
    segs, after = [], 0.0
    for s in man["segments"]:
        if "from_text" in s:
            i = find(words, s["from_text"], after)
            prev_end = words[i - 1]["end"] if i else 0.0
            t0 = max(prev_end + 0.02, words[i]["start"] - s.get("pad_in", pad[0]))
        else:
            t0 = float(s["from"])
        if "to_text" in s:
            j = find(words, s["to_text"], t0, last=True)
            nxt = words[j + 1]["start"] if j + 1 < len(words) else 1e9
            t1 = min(nxt - 0.02, words[j]["end"] + s.get("pad_out", pad[1]))
        else:
            t1 = float(s["to"])
        t1 = min(t1, length - 0.02)
        if t1 <= t0:
            sys.exit("segment runs backwards: %.2f -> %.2f" % (t0, t1))
        segs.append((round(t0, 3), round(t1, 3)))
        after = t1
    return segs


def remap(words, segs):
    """The words said inside the segments, on the Short's own clock."""
    out, base = [], 0.0
    for t0, t1 in segs:
        for w in words:
            if w["start"] >= t0 - 0.01 and w["end"] <= t1 + 0.05:
                out.append(
                    {
                        "text": w["text"],
                        "start": round(base + w["start"] - t0, 3),
                        "end": round(base + min(w["end"], t1) - t0, 3),
                    }
                )
        base += t1 - t0
    return out


def film_look(src, style):
    """The film's own paper, ink and accent (its sketch.json player block), else the style's."""
    t = dict(style["title"])
    try:
        p = json.load(open(os.path.join(src, "sketch.json"), encoding="utf-8")).get("player") or {}
        for k in ("paper", "ink", "accent"):
            if p.get(k):
                t[k] = p[k]
    except (OSError, ValueError):
        pass
    return t


def title_png(text, t, W, path):
    """The headline on a rounded card in the film's paper, a border in its accent, a slight tilt."""
    font_path = _env.resolve(t["font"])
    lines, size = [text], t["max_size"]
    while size >= t["min_size"]:
        font = ImageFont.truetype(font_path, size)
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if font.getlength(trial) <= t["max_width"] - 2 * t["pad"][0] or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= t["max_lines"] and all(
            font.getlength(x) <= t["max_width"] - 2 * t["pad"][0] for x in lines
        ):
            break
        size -= 4
    else:
        sys.exit("headline does not fit in %d lines: %r" % (t["max_lines"], text))
    lh = int(size * t["line_gap"])
    tw = max(font.getlength(x) for x in lines)
    cw, ch = int(tw + 2 * t["pad"][0]), int(lh * len(lines) + 2 * t["pad"][1])
    card = Image.new("RGBA", (cw + 40, ch + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((26, 28, cw + 26, ch + 28), t["radius"], fill=(0, 0, 0, 90))  # soft drop
    d.rounded_rectangle(
        (18, 18, cw + 18, ch + 18),
        t["radius"],
        fill=t["paper"],
        outline=t["accent"],
        width=t["border_px"],
    )
    y = 18 + t["pad"][1] - int(size * 0.06)
    for x in lines:
        d.text((18 + (cw - font.getlength(x)) / 2, y), x, font=font, fill=t["ink"])
        y += lh
    card = card.rotate(t["tilt_deg"], resample=Image.BICUBIC, expand=True)
    band0, band1 = t["band"]
    if card.height > band1 - band0 + 40:
        sys.exit("headline card is %d px tall, the band %d" % (card.height, band1 - band0))
    out = Image.new("RGBA", (W, band1 + 40), (0, 0, 0, 0))
    out.alpha_composite(card, ((W - card.width) // 2, band0 + (band1 - band0 - card.height) // 2))
    out.save(path)
    return size, len(lines)


def camera_expr(cam, cw, sw, total):
    """The crop's x as an ffmpeg expression of t (the Short's seconds): linear between keys,
    eased (smoothstep) so a pan starts and stops gently, clamped inside the frame."""
    keys = sorted(cam.get("keys") or [[0, cam.get("x", 0.5)]])
    keys = [(float(a), float(b)) for a, b in keys]

    def px(f):
        return max(0, min(sw - cw, f * sw - cw / 2))

    if len(keys) == 1:
        return "%d" % round(px(keys[0][1]))
    expr = "%.1f" % px(keys[-1][1])
    for (ta, xa), (tb, xb) in reversed(list(zip(keys, keys[1:], strict=False))):
        a, b = px(xa), px(xb)
        u = "clip((t-%.3f)/%.3f,0,1)" % (ta, max(0.001, tb - ta))
        seg = "(%.1f+(%.1f)*(%s*%s*(3-2*%s)))" % (a, b - a, u, u, u)
        expr = "if(lt(t,%.3f),%s,%s)" % (tb, seg, expr)
    return "if(lt(t,%.3f),%.1f,%s)" % (keys[0][0], px(keys[0][1]), expr)


def probe(mp4):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            mp4,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def graph(segs, style, cam, sw, sh, ass, title_png_path, fade):
    W, H = style["canvas"]
    aw, ah = style["picture"]["aspect"]
    cw = int(round(sh * aw / ah / 2) * 2)
    pw, ph = W, int(round(W * ah / aw / 2) * 2)
    py = style["picture"]["y"]
    bd = style["backdrop"]
    total = sum(b - a for a, b in segs)
    n = len(segs)
    # an input pad feeds one filter: split it once per segment
    parts = [
        "[0:v]split=%d%s" % (n, "".join("[sv%d]" % k for k in range(n))),
        "[0:a]asplit=%d%s" % (n, "".join("[sa%d]" % k for k in range(n))),
    ]
    labels = []
    for k, (a, b) in enumerate(segs):
        parts.append("[sv%d]trim=%.3f:%.3f,setpts=PTS-STARTPTS[v%d]" % (k, a, b, k))
        f = fade / 1000.0
        parts.append(
            "[sa%d]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS,afade=t=in:d=%.3f,afade=t=out:st=%.3f:d=%.3f[a%d]"
            % (k, a, b, f, max(0, b - a - f), f, k)
        )
        labels.append("[v%d][a%d]" % (k, k))
    parts.append("%sconcat=n=%d:v=1:a=1[vc][ac]" % ("".join(labels), len(segs)))
    parts.append("[vc]fps=%d,split[bgs][fgs]" % style["fps"])
    # the backdrop: the same picture, filled to the canvas at a quarter size, blurred, darkened
    q = 4
    parts.append(
        "[bgs]scale=-2:%d,crop=%d:%d,boxblur=%d:2,scale=%d:%d,eq=brightness=%.2f:saturation=%.2f[bg]"
        % (
            H // q,
            W // q,
            H // q,
            max(1, bd["blur_px"] // 2),
            W,
            H,
            bd["brightness"],
            bd["saturation"],
        )
    )
    parts.append(
        "[fgs]crop=%d:%d:'%s':0,scale=%d:%d:flags=lanczos[fg]"
        % (cw, sh, camera_expr(cam, cw, sw, total), pw, ph)
    )
    parts.append("[bg][fg]overlay=0:%d[pic]" % py)
    parts.append("[pic][1:v]overlay=0:0:shortest=1[tt]")
    fonts = _env.resolve("fonts").replace("\\", "/").replace(":", "\\:")
    a = ass.replace("\\", "/").replace(":", "\\:")
    parts.append("[tt]subtitles=filename='%s':fontsdir='%s',format=yuv420p[vout]" % (a, fonts))
    return ";".join(parts), total


def build_captions(words, out_dir, style):
    wj = os.path.join(out_dir, "words.json")
    json.dump({"words": words}, open(wj, "w", encoding="utf-8"), indent=1)
    ass = os.path.join(out_dir, "captions.ass")
    subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "scripts", "build-captions-ass.py"),
            "--words",
            wj,
            "--style",
            _env.resolve(style["captions"]),
            "--out",
            ass,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        cwd=ROOT,  # the preset names its font relative to the repo
    )
    return ass


def write_vtt(words, path):
    """A plain caption file for the film page: one cue a sentence."""

    def ts(t):
        return "%02d:%02d:%06.3f" % (t // 3600, t % 3600 // 60, t % 60)

    cues, cur = [], []
    for w in words:
        cur.append(w)
        if w["text"].rstrip()[-1:] in ".!?" or len(cur) >= 10:
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for c in cues:
            f.write(
                "%s --> %s\n%s\n\n"
                % (ts(c[0]["start"]), ts(c[-1]["end"]), " ".join(w["text"] for w in c))
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--list", action="store_true", help="the segments, the gaps each cut lands in, the length"
    )
    ap.add_argument(
        "--stills",
        help="comma-separated seconds of the Short: PNGs of the finished frame, no encode",
    )
    ap.add_argument("--out", help="override the manifest's out folder")
    ap.add_argument("--src", help="override the manifest's episode folder (another machine's copy)")
    args = ap.parse_args()

    man = json.load(open(args.manifest, encoding="utf-8"))
    style = json.load(open(_env.resolve(man.get("style", STYLE)), encoding="utf-8"))
    # a two-hander whose cast stand far apart wants a wider window: the manifest may override the
    # picture's shape ({"aspect": [1, 1], "y": 400}) for its own Short
    style["picture"].update(man.get("picture") or {})
    src = _env.resolve(args.src or man["src"], os.path.dirname(os.path.abspath(args.manifest)))
    out_dir = _env.resolve(args.out or man["out"], os.path.dirname(os.path.abspath(args.manifest)))
    mp4, tl = source_files(src)
    words = all_words(tl)
    length = float(json.load(open(tl, encoding="utf-8"))["duration"])
    segs = resolve(man, words, man.get("pad", style["pad"]), length)
    sw_words = remap(words, segs)
    total = sum(b - a for a, b in segs)

    if args.list:
        print("source  %s" % mp4)
        base = 0.0
        for a, b in segs:
            inside = [w for w in words if w["start"] >= a - 0.01 and w["end"] <= b + 0.05]
            before = [w for w in words if w["end"] <= a]
            after = [w for w in words if w["start"] >= b]
            gin = a - before[-1]["end"] if before else a
            gout = after[0]["start"] - b if after else 0
            print(
                "  %6.2f-%6.2f  (%5.2fs, short %5.2f-%5.2f)  %d words  room before %.2fs, after %.2fs"
                % (a, b, b - a, base, base + b - a, len(inside), gin, gout)
            )
            print("      first: %s" % " ".join(w["text"] for w in inside[:8]))
            print("      last:  %s" % " ".join(w["text"] for w in inside[-8:]))
            base += b - a
        print(
            "length %.2fs, %d words, %.0f words a minute"
            % (total, len(sw_words), 60 * len(sw_words) / total)
        )
        if sw_words:
            print("first word at %.2fs" % sw_words[0]["start"])
        return

    os.makedirs(os.path.join(out_dir, "outputs"), exist_ok=True)
    sw, sh = probe(mp4)
    look = film_look(src, style)
    tpng = os.path.join(out_dir, "title.png")
    size, nl = title_png(man["title"], look, style["canvas"][0], tpng)
    ass = build_captions(sw_words, out_dir, style)
    fg, total = graph(
        segs, style, man.get("camera") or {}, sw, sh, ass, tpng, style["join_fade_ms"]
    )

    if args.stills:
        for s in [float(x) for x in args.stills.split(",")]:
            png = os.path.join(out_dir, "still-%06.2f.png" % s)
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", mp4, "-loop", "1", "-i", tpng]
                + ["-filter_complex", fg + ";[ac]anullsink"]
                + ["-map", "[vout]", "-ss", "%.3f" % s, "-frames:v", "1", png],
                check=True,
            )
            print(png)
        return

    cfg = _encode.resolve(style["render"])
    final = os.path.join(out_dir, "outputs", "film.mp4")
    cmd = (
        ["ffmpeg", "-v", "error", "-y"]
        + _encode.decode_args()
        + [
            "-i",
            mp4,
            "-loop",
            "1",
            "-i",
            tpng,
            "-filter_complex",
            fg,
            "-map",
            "[vout]",
            "-map",
            "[ac]",
        ]
        + _encode.video_args(cfg)
        + _encode.audio_args(cfg, rate=48000)
        + ["-t", "%.3f" % total, "-movflags", "+faststart", final]
    )
    subprocess.run(cmd, check=True)
    got = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    if abs(got - total) > 0.25:
        sys.exit("the Short runs %.2fs, the segments add up to %.2fs" % (got, total))
    poster = os.path.join(out_dir, "outputs", "film_poster.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", final, "-frames:v", "1", poster], check=True
    )
    write_vtt(sw_words, os.path.join(out_dir, "outputs", "film.vtt"))
    sk = {
        "title": man["title"],
        "slug": "film",
        "duration": round(total, 3),
        "fps": style["fps"],
        "frame": list(style["canvas"]),
        "cover": False,
        "from_film": man.get("film"),
        "segments": segs,
    }
    json.dump(sk, open(os.path.join(out_dir, "sketch.json"), "w", encoding="utf-8"), indent=2)
    if man.get("project"):
        _project.record(
            man["project"],
            "episode short",
            out=final,
            script="scripts/episode-short.py",
            argv=sys.argv,
            kind="short",
            manifest=args.manifest,
            burned=["captions", "headline"],
        )
    print("%s  %.2fs  headline %d px in %d line(s)" % (final, total, size, nl))


if __name__ == "__main__":
    main()
