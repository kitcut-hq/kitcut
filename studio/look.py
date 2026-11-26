"""Looking at and listening to a finished film without downloading it: kitcut.ai's get_film_frames
and get_film_audio, so an assistant can check what a round of changes made (or any version kept)
the way its owner would, by watching and listening, instead of fetching the MP4 and running ffmpeg
itself.

    sheet(film, version, times)   the film's frames at those moments, as one contact sheet, each
                                  stamped with its time (m:ss.s, as the notes page writes it)
    still(film, version, t)       one frame at its full size
    levels(film, version, a, b, window)
                                  the sound from a to b: mean and peak loudness (dBFS) a window,
                                  and the narration lines said in each

Every frame is sought, never the whole film decoded (rounds.make_strip does the same), and a video
that only lives online is read from its copy there (ffmpeg seeks it by ranges), so a version whose
files are no longer kept on this disk can still be looked at. The server's routes
(/api/films/{id}/frames and /audio) are the film's own client's only.
"""

import io
import os
import sys
import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rounds  # noqa: E402

MAX_FRAMES = 24  # on one sheet: past it the tiles get too small to see a glitch in
SHEET_W = 1568  # a sheet's width: what a model sees of a wider one anyway (review.SHEET_W)
MIN_EVERY = 0.1  # the closest two frames may be asked for: three at 30 fps
MAX_WINDOWS = 240  # windows of sound in one answer; a longer range gets wider windows
MIN_WINDOW, MAX_WINDOW = 0.5, 30.0
RATE = 16000  # what the sound is read at: enough for loudness, a fraction of the work
FLOOR_DB = -90.0  # digital silence is said as this, not as minus infinity
FFMPEG_S = 90  # one ffmpeg call's time: a frame read online can take a few seconds


class LookError(Exception):
    def __init__(self, status, text, reason=None):
        super().__init__(text)
        self.status, self.text, self.reason = status, text, reason


def clock(t):
    return "%d:%04.1f" % (t // 60, t % 60)


# ------------------------------------------------------------------ which files a version is
def _lines(raw):
    return [
        {
            "i": x.get("i", i),
            "text": str(x.get("text") or ""),
            "start": round(float(x.get("start") or 0), 2),
            "end": round(float(x.get("end") or 0), 2),
        }
        for i, x in enumerate(raw or [])
        if isinstance(x, dict)
    ]


def _timeline(d):
    try:
        with open(os.path.join(d, "audio", "vo", "timeline.json"), encoding="utf-8") as f:
            return _lines(json.load(f).get("lines"))
    except (OSError, ValueError, AttributeError):
        return None


def version(film, n=None):
    """Version n of the film (None: the one it shows) as {"n", "current", "src", "duration",
    "lines", "music", "versions"}: src is its video on this disk, or the URL of its copy online
    when it is only there. Raises LookError when there is no such version or no video of it."""
    rec = film.record()
    cur = rounds.version_of(rec)
    vs = [v for v in rec.get("versions") or [] if isinstance(v, dict) and v.get("n")]
    have = sorted({cur} | {int(v["n"]) for v in vs})
    n = cur if n is None else int(n)
    entry = next((v for v in vs if int(v["n"]) == n), None)
    if n != cur and entry is None:
        raise LookError(
            404,
            "This film has no version %d (it has %s)." % (n, ", ".join(map(str, have))),
            "version",
        )
    d = film.dir if n == cur else film.path(rounds.KEPT, "v%d" % n)
    src = next(
        (
            p
            for p in (os.path.join(d, "outputs", x) for x in ("film.mp4", "film_web.mp4"))
            if os.path.isfile(p)
        ),
        None,
    )
    if src is None:  # copied online, and not (or no longer) on this disk
        online = (entry or {}).get("media") or {}
        if n == cur:
            online = {**online, **(rec.get("media") or {})}
        src = next(
            (
                u
                for u in (online.get("web"), online.get("video"))
                if isinstance(u, str) and u.startswith(("https://", "http://127.0.0.1:"))
            ),
            None,
        )
    if src is None:
        raise LookError(404, "Version %d of this film has no video to look at." % n, "video")
    lines = _timeline(d)
    if lines is None:
        lines = _lines((entry or {}).get("lines"))
    secs = (entry or {}).get("video_s")
    if not secs:
        got = rounds._probe(src)
        secs = got[0] if got else float(film.length)
    return {
        "n": n,
        "current": n == cur,
        "src": src,
        "duration": round(float(secs), 2),
        "lines": lines,
        "music": rec.get("music") != "none",
        "versions": have,
    }


# ------------------------------------------------------------------ frames
def times(duration, a=None, b=None, count=None, every=None):
    """The moments a sheet shows: from a to b (the whole film when left out), `count` of them
    spread from end to end, or one `every` seconds from a. At most MAX_FRAMES: a step that would
    give more is widened. Returns (times, step)."""
    end = max(0.0, float(duration) - 0.05)  # the very last instant has no frame to seek to
    a = min(end, max(0.0, float(a or 0)))
    b = end if b is None else min(end, max(0.0, float(b)))
    if b < a:
        raise LookError(400, "`to` comes before `from`.", "range")
    span = b - a
    if every is not None:
        every = max(MIN_EVERY, float(every), span / (MAX_FRAMES - 1) if span else 0)
        k = int(span / every + 1e-6) + 1
        ts = [a + i * every for i in range(k)]
        step = every
    else:
        k = max(1, min(MAX_FRAMES, int(count or 12)))
        if k == 1 or span == 0:
            ts = [(a + b) / 2]
        else:
            ts = [a + span * i / (k - 1) for i in range(k)]
        step = span / (k - 1) if k > 1 else 0
    out = []
    for t in ts:
        t = round(t, 2)
        if not out or t - out[-1] >= 0.05:
            out.append(t)
    return out, round(step, 3)


def _grab(src, t, width=None):
    """One frame at t seconds as a PIL image (sought, not decoded up to), or None."""
    from PIL import Image

    vf = ["-vf", "scale=%d:-2" % width] if width else []
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", src, "-frames:v", "1"]
            + vf
            + ["-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True,
            timeout=FFMPEG_S,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    try:
        return Image.open(io.BytesIO(r.stdout)).convert("RGB")
    except Exception:  # noqa: BLE001 -- a frame that will not open is a missing frame
        return None


def _encode(im, fmt):
    b = io.BytesIO()
    if fmt == "png":
        im.save(b, "PNG", optimize=True)
    else:
        im.save(b, "JPEG", quality=85)
    return b.getvalue()


def sheet(v, ts, fmt="jpeg"):
    """The frames at ts as one sheet SHEET_W wide, a time on each; (bytes, [times got])."""
    from PIL import Image, ImageDraw

    import motion

    n = len(ts)
    cols = 1 if n == 1 else 2 if n <= 4 else 3 if n <= 9 else 4 if n <= 16 else 5
    gap = 6
    tw = (SHEET_W - gap * (cols - 1)) // cols
    with ThreadPoolExecutor(max_workers=6) as pool:
        frames = list(pool.map(lambda t: _grab(v["src"], t, tw), ts))
    first = next((f for f in frames if f is not None), None)
    if first is None:
        raise LookError(502, "No frame could be read from this version's video.", "video")
    th = first.height
    rows = math.ceil(n / cols)
    out = Image.new("RGB", (cols * tw + gap * (cols - 1), rows * th + gap * (rows - 1)), "white")
    draw = ImageDraw.Draw(out)
    font = motion._font(max(14, tw // 14))
    got = []
    for i, (t, im) in enumerate(zip(ts, frames)):
        x, y = (i % cols) * (tw + gap), (i // cols) * (th + gap)
        if im is None:
            draw.rectangle([x, y, x + tw - 1, y + th - 1], fill=(90, 90, 90))
            label = "%s  no frame" % clock(t)
        else:
            out.paste(im.resize((tw, th)) if im.size != (tw, th) else im, (x, y))
            label = clock(t)
            got.append(t)
        # the time on a dark box at the corner, readable on paper and on night skies alike
        l, tp, r, bt = draw.textbbox((0, 0), label, font=font)
        pad = max(3, (bt - tp) // 4)
        draw.rectangle([x, y, x + r - l + 2 * pad, y + bt - tp + 2 * pad], fill=(0, 0, 0))
        draw.text((x + pad - l, y + pad - tp), label, fill=(255, 255, 255), font=font)
    return _encode(out, fmt), got


def still(v, t, fmt="jpeg"):
    """One frame at t at its full size, with nothing drawn on it; bytes."""
    t = min(max(0.0, float(t)), max(0.0, v["duration"] - 0.05))
    im = _grab(v["src"], t)
    if im is None:
        raise LookError(502, "No frame could be read at %s." % clock(t), "video")
    return _encode(im, fmt), round(t, 2)


# ------------------------------------------------------------------ sound
def _db(x):
    return round(max(FLOOR_DB, 20 * math.log10(x)) if x > 0 else FLOOR_DB, 1)


def levels(v, a=None, b=None, window=None):
    """The sound from a to b in windows: {"from", "to", "window", "audio", "windows": [{"from",
    "to", "mean_db", "peak_db", "lines"}], "lines": [the narration lines said in the range]}.
    mean_db is the window's RMS loudness and peak_db its loudest sample, both in dBFS (0 is full
    scale; -90 is silence). Only the range is decoded."""
    import numpy as np

    dur = v["duration"]
    a = min(dur, max(0.0, float(a or 0)))
    b = dur if b is None else min(dur, max(0.0, float(b)))
    if b <= a:
        raise LookError(400, "`to` must come after `from`.", "range")
    span = b - a
    w = float(window or 2.0)
    w = max(MIN_WINDOW, min(MAX_WINDOW, w), span / MAX_WINDOWS)
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "%.3f" % a, "-t", "%.3f" % span, "-i", v["src"]]
            + ["-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
            capture_output=True,
            timeout=FFMPEG_S * 2,
        )
    except subprocess.TimeoutExpired:
        raise LookError(504, "The film's sound took too long to read.", "audio") from None
    x = np.frombuffer(r.stdout, dtype="<i2").astype(np.float64) / 32768.0 if r.stdout else None
    said = [ln for ln in v["lines"] if ln["end"] > a and ln["start"] < b]
    out = []
    k = math.ceil(span / w - 1e-9)
    for i in range(k):
        t0, t1 = a + i * w, min(b, a + (i + 1) * w)
        row = {"from": round(t0, 2), "to": round(t1, 2)}
        if x is not None:
            seg = x[int((t0 - a) * RATE) : int((t1 - a) * RATE)]
            if len(seg):
                row["mean_db"] = _db(float(np.sqrt(np.mean(seg * seg))))
                row["peak_db"] = _db(float(np.max(np.abs(seg))))
        row["lines"] = [ln["i"] for ln in said if ln["end"] > t0 and ln["start"] < t1]
        out.append(row)
    return {
        "from": round(a, 2),
        "to": round(b, 2),
        "window": round(w, 2),
        "audio": x is not None and len(x) > 0,
        "music": v["music"],
        "windows": out,
        "lines": said,
    }
