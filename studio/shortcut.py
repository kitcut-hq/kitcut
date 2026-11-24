#!/usr/bin/env python
"""A finished 16:9 film cut into a vertical YouTube Short: kitcut.ai's film_to_short.

    python studio/shortcut.py --plan <film id> [--segments 0-22,140-159]
                                            what the Short would be, or why it would be refused;
                                            writes nothing

The site asks POST /api/films {"short": {"from", "version", "segments"?, "headline"?, "key"},
"listed"?} as the original's own client. The studio makes it as a FILM OF ITS OWN (a new id, page
and record) from the original's finished master, and nothing is drawn, painted or said again: no
Claude, no voice, no picture model.

The picture is 1080x1920: the whole 16:9 frame, uncropped, centred over a blurred, darkened copy of
itself, the headline above it and the film's own subtitles, large, below it. The sound is the
film's. segments keep only those seconds of the original, in order; without them the whole film is
kept. A Short is at most MAX_S seconds, YouTube's limit.

A Short has to behave like any other finished film, and the studio's thumbnails, share page and
YouTube drafts all draw a film from its code (scripts/_thumb.py). So its folder holds a small
film.js that shows the Short's own frames (images/f00.jpg...), its manifest, and its words as a
narration (vo.json, audio/vo/timeline.json) with the Short's own times. The video itself is never
drawn from that code.

Refused, before anything is made (409 {reason}): a film that is not finished (state), one whose next
version is being made (round), one that is not 16:9 (frame), and a result over MAX_S (long). 400
{reason: segments} for segments that cannot be cut, 404 for a film that is not the asker's. Asking
twice with one key is one film.
"""

import os
import re
import sys
import json
import math
import time
import shutil
import asyncio
import argparse
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clients  # noqa: E402
import localize  # noqa: E402
import media  # noqa: E402
import procs  # noqa: E402
import store  # noqa: E402
from film import Film, _write_json  # noqa: E402

MAX_S = 180  # the longest YouTube takes as a Short
MIN_PART_S = 0.5  # a shorter cut is a flash, not a part of the film
MAX_PARTS = 12
SLACK_S = 0.25  # an end this far past the film is the film's end
HEADLINE_MAX = 90
W, H = 1080, 1920
FPS = 30
STILLS = 16  # the Short's frames its thumbnails are made from
CUT_S = 1800  # the longest one cut may take
THREADS = "4"  # a cut runs beside films being rendered: it never takes the whole machine
KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
LONG = (
    "The Short would be %d seconds long, and a YouTube Short can be at most %d. "
    "Pass segments: the parts of the film to keep."
)


class Refused(Exception):
    def __init__(self, status, reason, error):
        super().__init__(error)
        self.status, self.reason, self.error = status, reason, error

    def body(self):
        return {"reason": self.reason, "error": self.error}


# ------------------------------------------------------------------ what is kept
def _second(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Refused(400, "segments", "a segment's start and end are seconds of the film")
    return round(float(v), 3)


def parts_of(raw, duration):
    """The seconds kept, [(start, end)], from the segments asked for (none: the whole film).
    Raises Refused for parts that cannot be cut, or a result over MAX_S."""
    if not raw:
        parts = [(0.0, round(float(duration), 3))]
    else:
        if not isinstance(raw, list) or len(raw) > MAX_PARTS:
            raise Refused(400, "segments", "segments is a list of up to %d parts" % MAX_PARTS)
        parts, last = [], 0.0
        for s in raw:
            if not isinstance(s, dict):
                raise Refused(400, "segments", "each segment is {start, end}, in seconds")
            a, b = _second(s.get("start")), _second(s.get("end"))
            if a < last:
                raise Refused(400, "segments", "segments go in order and do not overlap")
            if b > duration + SLACK_S:
                raise Refused(
                    400,
                    "segments",
                    "A segment ends at %g s, and the film is %.1f s long." % (b, duration),
                )
            b = min(b, round(float(duration), 3))
            if b - a < MIN_PART_S:
                raise Refused(400, "segments", "each segment is at least %g s long" % MIN_PART_S)
            parts.append((a, b))
            last = b
    total = sum(b - a for a, b in parts)
    if total > MAX_S:
        raise Refused(409, "long", LONG % (math.ceil(total), MAX_S))
    return parts


def headline_of(raw):
    """The headline as it is drawn: one line of plain words, | where a line breaks."""
    return " ".join(str(raw or "").split())[:HEADLINE_MAX].strip()


def probe(path):
    """{w, h, duration, audio} of a video, a file or an address."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height"]
        + ["-show_entries", "format=duration", "-of", "json", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode:
        raise RuntimeError("ffprobe: %s" % r.stderr.strip()[-200:])
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams") or [] if s.get("codec_type") == "video"), {})
    return {
        "w": int(v.get("width") or 0),
        "h": int(v.get("height") or 0),
        "duration": float((d.get("format") or {}).get("duration") or 0),
        "audio": any(s.get("codec_type") == "audio" for s in d.get("streams") or []),
    }


def master_of(src):
    """Where the original's master can be read now: on this disk, else its copy online."""
    p = src.path("outputs", "film.mp4")
    return p if os.path.isfile(p) else media.stored(src, "film.mp4")


def check(spec, client):
    """The original and what is kept of it, checked: (source Film, parts, headline, key, version).
    Raises Refused. Reads the master's own length: a record's `length` is what was asked for, and
    a film can run a little past it."""
    if not isinstance(spec, dict):
        raise Refused(400, "short", 'short must be {"from", "version", "segments", "key"}')
    src_id, key = str(spec.get("from") or ""), str(spec.get("key") or "")
    if not localize.FILM_ID.match(src_id):
        raise Refused(400, "short", "short.from is not a film id")
    if not KEY.match(key):
        raise Refused(400, "short", "short.key must be the site's hold id")
    src = Film.open(src_id)
    if src is None or not clients.same(src.record().get("client"), client):
        raise Refused(404, "short", "no such film")
    rec = src.record()
    if rec.get("state") != "done":
        raise Refused(409, "state", "the film is not finished")
    if rec.get("frame") not in (None, "16:9"):
        raise Refused(409, "frame", "only a wide (16:9) film can be cut into a Short")
    if localize._round_making(src):  # noqa: SLF001
        raise Refused(409, "round", "a new version of the film is being made")
    where = master_of(src)
    if not where:
        raise Refused(409, "state", "the film's video is not here any more")
    p = probe(where)
    if p["w"] * 9 != p["h"] * 16:
        raise Refused(409, "frame", "only a wide (16:9) film can be cut into a Short")
    parts = parts_of(spec.get("segments"), p["duration"])
    try:
        version = int(spec.get("version") or rec.get("version") or 1)
    except (TypeError, ValueError):
        version = int(rec.get("version") or 1)
    return src, parts, headline_of(spec.get("headline")), key, version


def by_key(key, films=None):
    """The Short already made for this key (asked twice: one film), or None."""
    for f in films if films is not None else localize.recent():
        if (f.record().get("short_of") or {}).get("key") == key:
            return f
    return None


# ------------------------------------------------------------------ the words
def _clock(s):
    p = s.strip().replace(",", ".").split(":")
    p = ["0"] * (3 - len(p)) + p
    return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])


def read_vtt(text):
    """[(start, end, words)] of a subtitle file. A number standing alone on a caption's own line is
    the caption's: only the lines after a cue's times are its words."""
    cues, cur = [], None
    for line in text.replace("\r", "").split("\n"):
        if "-->" in line:
            a, b = line.split("-->")[:2]
            cur = [_clock(a), _clock(b.split()[0]), []]
            cues.append(cur)
        elif not line.strip():
            cur = None
        elif cur is not None:
            cur[2].append(re.sub(r"<[^>]+>", "", line.strip()))
    return [(a, b, " ".join(w).strip()) for a, b, w in cues if " ".join(w).strip()]


def retime(cues, parts):
    """The cues on the Short's clock: each cut to the parts kept, a cue across a join in both."""
    out, at = [], 0.0
    for a, b in parts:
        for s, e, words in cues:
            s2, e2 = max(s, a), min(e, b)
            if e2 - s2 > 0.05:
                out.append((round(at + s2 - a, 3), round(at + e2 - a, 3), words))
        at += b - a
    return out


def _ass_time(t):
    cs = round(t * 100)
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs % 360000 // 6000, cs % 6000 // 100, cs % 100)


def _ass_words(s):
    """Words as libass reads them: a brace or a backslash would be an instruction."""
    return " ".join(str(s).replace("\\", "/").replace("{", "(").replace("}", ")").split())


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Head,DejaVu Sans,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,5,2,2,70,70,0,1
Style: Cap,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,0,0,3,14,0,8,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass(headline, cues, length):
    """The Short's words: the headline standing on the film's top edge, each caption under the
    film's bottom edge (the film is 608 px tall, centred: 656 to 1264)."""
    rows = []
    if headline:
        lines = [_ass_words(x) for x in headline.split("|") if x.strip()]
        rows.append(
            "Dialogue: 0,%s,%s,Head,,0,0,0,,{\\an2\\pos(540,620)}%s"
            % (_ass_time(0), _ass_time(length + 1), "\\N".join(lines))
        )
    for a, b, words in cues:
        rows.append(
            "Dialogue: 0,%s,%s,Cap,,0,0,0,,{\\an8\\pos(540,1320)}%s"
            % (_ass_time(a), _ass_time(b), _ass_words(words))
        )
    size = 74 if len(headline) <= 60 else 60
    return ASS_HEAD % size + "\n".join(rows) + "\n"


# ------------------------------------------------------------------ the cut
def command(master, parts, out, audio, subs="short.ass"):
    """The ffmpeg command for the Short. Each part is read from its own seek, so a long film is
    decoded only where it is kept; the words are burned in after the join, on the Short's clock."""
    argv = ["nice", "-n", "10"] if shutil.which("nice") else []
    argv += ["ffmpeg", "-v", "error", "-y"]
    chain, join = [], ""
    for i, (a, b) in enumerate(parts):
        d = b - a
        argv += ["-ss", "%.3f" % a, "-t", "%.3f" % d, "-i", master]
        chain.append("[%d:v]fps=%d,trim=duration=%.3f,setpts=PTS-STARTPTS[v%d]" % (i, FPS, d, i))
        join += "[v%d]" % i
        if audio:
            chain.append(
                "[%d:a]aresample=48000,asetpts=PTS-STARTPTS,afade=t=in:d=0.04,"
                "afade=t=out:st=%.3f:d=0.05,apad=whole_dur=%.3f,atrim=0:%.3f[a%d]"
                % (i, max(0, d - 0.05), d, d, i)
            )
            join += "[a%d]" % i
    chain.append("%sconcat=n=%d:v=1:a=%d[vc]%s" % (join, len(parts), audio, "[a]" if audio else ""))
    chain.append(
        "[vc]split=2[bg][fg];"
        "[bg]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
        "boxblur=30:2,eq=brightness=-0.28[b];"
        "[fg]scale=%d:-2[f];"
        "[b][f]overlay=0:(H-h)/2,ass=%s,setsar=1,format=yuv420p[v]" % (W, H, W, H, W, subs)
    )
    argv += ["-filter_complex", ";".join(chain), "-map", "[v]"]
    argv += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if audio else []
    argv += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-threads", THREADS]
    return [*argv, "-movflags", "+faststart", out]


def film_js(title, frames):
    """The Short's frames as a film: what the thumbnails and the share picture are drawn from."""
    return """// %s
// A Short cut from a finished film: the video is the film's own, and this only shows its frames
// to the studio's thumbnails and share picture.
const FRAMES = %s;
SK.film({
  camera: SK.camera([[0, [0, 0, 1]]]),
  fadeIn: 0,
  fadeOut: 0,
  handheld: false,
  speedLines: false,
  draw() {},
  overlay(t) {
    let at = FRAMES[0];
    for (const f of FRAMES) if (f[0] <= t) at = f;
    SK.image(at[1], SK.W / 2, SK.H / 2, SK.W, SK.H);
  },
});
""" % (" ".join(title.split())[:120], json.dumps(frames))


def seed(film, src, parts, headline, key, version):
    """Lay the Short's record and manifest into the new film's folder (Film.create made it)."""
    length = round(sum(b - a for a, b in parts), 3)
    rec = src.record()
    title = headline.replace("|", " ").strip() or rec.get("title") or ""
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m.update(duration=length, poster_t=round(min(1.0, length / 2), 2), fps=FPS)
    if title:
        m["title"] = title[:60]
    _write_json(film.manifest, m)
    film.update(
        short_of={
            "from": src.id,
            "version": version,
            "key": key,
            "segments": [{"start": a, "end": b} for a, b in parts],
            "headline": headline,
        },
        length=max(1, round(length)),
        look=rec.get("look") or "drawn",
        mode="single",
        **({"title": title} if title else {}),
    )


def _lay_words(film, src, cues):
    """The Short's words as a narration, for what reads one: its YouTube draft and thumbnails."""
    lines = [{"text": w} for _, _, w in cues]
    _write_json(film.path("vo.json"), {"language": localize.language_of(src), "lines": lines})
    os.makedirs(film.path("audio", "vo"), exist_ok=True)
    timeline = {
        "lines": [
            {"i": i, "start": a, "end": b, "text": w, "words": []}
            for i, (a, b, w) in enumerate(cues)
        ]
    }
    _write_json(film.path("audio", "vo", "timeline.json"), timeline)


def _lay_frames(film, out, length, title):
    """Its frames, its film.js and its poster, from the Short itself."""
    os.makedirs(film.path("images"), exist_ok=True)
    n = max(1, min(STILLS, int(length // 3) + 1))
    frames, images = [], {}
    for i in range(n):
        t = round(length * (i + 0.5) / n, 2)
        name = "f%02d" % i
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % t, "-i", out, "-frames:v", "1"]
            + ["-q:v", "3", film.path("images", name + ".jpg")],
            check=True,
            timeout=120,
        )
        frames.append([round(length * i / n, 2), name])
        images[name] = "images/%s.jpg" % name
    with open(film.path("film.js"), "w", encoding="utf-8") as f:
        f.write(film_js(title, frames))
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    m["images"] = images
    _write_json(film.manifest, m)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % min(1.0, length / 2), "-i", out]
        + ["-frames:v", "1", film.path("outputs", "film_poster.png")],
        check=True,
        timeout=120,
    )


async def cut(film, src, jobs=None):
    """The Short's video and everything a finished film has beside it. Raises when it is wrong."""
    spec = film.record()["short_of"]
    parts = [(float(s["start"]), float(s["end"])) for s in spec["segments"]]
    length = sum(b - a for a, b in parts)
    master = await asyncio.to_thread(media.bring_back, src, "film.mp4")
    if not master:
        raise RuntimeError("the film's video could not be read")
    vtt = await asyncio.to_thread(media.bring_back, src, "film.vtt")
    cues = []
    if vtt:
        with open(vtt, encoding="utf-8") as f:
            cues = retime(read_vtt(f.read()), parts)
    os.makedirs(film.path("outputs"), exist_ok=True)
    os.makedirs(film.path("temp"), exist_ok=True)
    with open(film.path("temp", "short.ass"), "w", encoding="utf-8") as f:
        f.write(ass(spec.get("headline") or "", cues, length))
    was = await asyncio.to_thread(probe, master)
    out = film.path("outputs", "film.mp4")
    part = film.path("temp", "short.mp4")
    code, tail = await procs.run(
        command(master, parts, part, int(was["audio"])),
        film.path("temp"),
        procs.step_env(film),
        CUT_S,
        jobs=jobs,
    )
    if code:
        raise RuntimeError("the cut failed: %s" % " | ".join(tail[-3:])[:300])
    got = await asyncio.to_thread(probe, part)
    if (got["w"], got["h"]) != (W, H) or abs(got["duration"] - length) > 0.5:
        raise RuntimeError("the cut came out %(w)dx%(h)d, %(duration).1f s" % got)
    if was["audio"] and not got["audio"]:
        raise RuntimeError("the cut came out without its sound")
    os.replace(part, out)
    await asyncio.to_thread(_lay_words, film, src, cues)
    title = film.record().get("title") or ""
    await asyncio.to_thread(_lay_frames, film, out, length, title)


async def make(film, emit, sched, control):
    """The whole Short, in the place of agent.make_film's Claude and render: the same events, the
    same final record. A server that stops half-way leaves it queued, for the leader to cut it."""
    import agent  # noqa: PLC0415 -- it imports this module

    t0, stages, jobs = time.time(), {}, set()
    spec = film.record()["short_of"]
    state, summary = "error", {"ok": False, "length": film.record().get("length")}
    film.update(state="finishing")
    await agent.save(film.id, {"state": "finishing"})

    def on_wait(pool, ahead):
        emit(
            {
                "type": "wait",
                "pool": pool,
                "ahead": ahead,
                "text": agent.waiting_text(pool, ahead),
            }
        )

    try:
        src = Film.open(spec["from"])
        if src is None:
            raise RuntimeError("the film it is cut from is not here any more")
        async with sched["cpu"].hold(1, film.id, on_wait):
            s = time.time()
            emit({"type": "stage", "name": "cut", "text": "Cutting the Short"})
            await cut(film, src, jobs)
            stages["cut"] = round(time.time() - s, 1)
        if media.enabled():
            s = time.time()
            emit({"type": "stage", "name": "online", "text": "Making the web copy, then online"})
            summary["media"] = await media.publish(film) or None
            stages["online"] = round(time.time() - s, 1)
        summary.update(ok=True, video="film.mp4", poster="film_poster.png")
        state = "done"
        emit({"type": "done", **summary})
    except asyncio.CancelledError:
        for j in list(jobs):
            j.kill()
        if control.get("requeue") or control.get("shutdown"):
            film.update(state="queued", server=None)  # nothing is lost: the leader cuts it again
            await asyncio.shield(agent.save(film.id, {"state": "queued"}))
            raise
        state = "cancelled"
        summary.update(error="cancelled")
        emit({"type": "error", "text": "The film was cancelled."})
        await asyncio.shield(_final(film, state, summary, stages, t0))
        raise
    except Exception as e:  # noqa: BLE001 -- every failure goes to the page, and its credits back
        summary.update(error=str(e) or type(e).__name__)
        emit({"type": "error", "text": summary["error"]})
    await _final(film, state, summary, stages, t0)
    return summary


async def _final(film, state, summary, stages, t0):
    """The film's last word, in both records: the site settles its credits on `state`."""
    import agent  # noqa: PLC0415 -- it imports this module

    summary.update(seconds=round(time.time() - t0, 1), stages=stages, cost_usd=0.0)
    film.update(state=state, **summary, finished=datetime.now().isoformat(timespec="seconds"))
    rec = film.record()
    final = {
        "state": {"done": "done", "cancelled": "cancelled"}.get(state, "failed"),
        "ok": summary["ok"],
        "error": summary.get("error"),
        "seconds": summary["seconds"],
        "stages": stages or None,
        "title": rec.get("title"),
        "length": rec.get("length"),
        "frame": "9:16",
        "short_of": rec.get("short_of"),
        "media": summary.get("media"),
        "cost_usd": 0.0,
        "claude_cost_usd": 0.0,
        "tts_cost_usd": 0.0,
        "image_cost_usd": 0.0,
        "release": rec.get("release"),
        "auth": rec.get("auth"),
        "finished_at": store.now(),
    }
    await asyncio.shield(agent.save(film.id, final, final=True))


def _segments_arg(s):
    return [
        {"start": float(a), "end": float(b)}
        for a, b in (x.split("-") for x in s.split(",") if x.strip())
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", metavar="FILM", required=True)
    ap.add_argument("--segments", type=_segments_arg, default=None, help="0-22,140-159")
    a = ap.parse_args()
    src = Film.open(a.plan)
    if src is None:
        sys.exit("no film %s" % a.plan)
    spec = {"from": src.id, "key": "plan", "segments": a.segments}
    try:
        _, parts, _, _, v = check(spec, src.record().get("client"))
    except Refused as e:
        print("refused (%d %s): %s" % (e.status, e.reason, e.error))
        return
    total = sum(b - a for a, b in parts)
    print("%s v%d -> a Short of %.1f s from %d part(s): %s" % (src.id, v, total, len(parts), parts))


if __name__ == "__main__":
    main()
