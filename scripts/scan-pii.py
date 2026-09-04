#!/usr/bin/env python
"""Find the frames of a screen recording that must not be published as shot.

A screencast of somebody buying things is a screencast of somebody typing
their card number, and of other people's names, phones and delivery addresses
sitting on the page while it happens. Deciding what to blur by scrubbing the
timeline is how a phone number ends up on YouTube: the eye skips the one frame
between two identical-looking ones, and 4K screen text is unreadable at the
zoom level a human scrubs at.

So read the frames instead of watching them. Sample, OCR, and match against
patterns that describe the shape of the secret rather than its value -- a card
number is 13-19 digits in groups, a CVV is three digits next to the word, a
Ukrainian mobile is +380 and nine more, an IBAN is UA and 27. Each hit is
reported with the time it is on screen AND the box it occupies, in frame
fractions, which is exactly the shape `screen-cut.py` wants in a `blur` entry.
--emit writes those entries so the manifest is generated from measurement, not
typed from memory.

WHAT THIS IS AND IS NOT. It is a net that catches what a human scrub misses;
it is NOT a clearance. OCR misses rotated, low-contrast and partly-scrolled
text, and it cannot know that "Оксана Д." plus a Nova Poshta branch identifies
a real person. Treat a clean report as "nothing obvious left", never as "safe
to publish", and always look at the --sheet frames before an encode.

Rectangles are padded and merged deliberately generously: a blur that clips
the last digit of a card number has failed at the only job it had.

Invoke as:  python scripts/scan-pii.py --src projects/<id>/sources/<f>.mp4 --report
"""

import sys
import os
import re
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _encode  # noqa: E402
import numpy as np  # noqa: E402

ROOT = _env.ROOT

# Every hit this prints is page text, and this page text is Ukrainian. Windows
# hands a child process cp1252, which cannot encode Cyrillic at all, so the
# report dies on its first finding unless the streams are reconfigured here.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SAMPLE_FPS = 0.5  # a frame every 2s; screen text lives far longer than that
OCR_WIDTH = 1600  # OCR resolution; 4K is slower with no better recall here
PAD = 0.012  # fraction of frame added around every hit box


def _digits(s):
    return re.sub(r"\D", "", s)


def luhn(num):
    """Whether a digit string passes the card checksum.

    This is what keeps order numbers, phone numbers and IBAN fragments out of
    the card class -- '#1806413786' is ten digits in a row and is not a card.
    """
    d = [int(c) for c in num][::-1]
    tot = 0
    for i, v in enumerate(d):
        if i % 2:
            v *= 2
            if v > 9:
                v -= 9
        tot += v
    return tot % 10 == 0 and len(num) >= 13


# Each rule is (name, severity, test). `text` is the OCR line, lowercased for
# the keyword tests. Severity drives what --emit blurs by default.
def rules():
    # OCR does not preserve the mask glyph. Privat24 draws a bullet, this model
    # returns "----", another returns "****" or drops it entirely -- so match
    # the SHAPE (a run of any mask-ish character next to a digit group) rather
    # than the bullet the designer happened to choose.
    MASK = r"[*•·∙‧\.\-–—_=]{3,}"

    def card(t, low):
        # A URL is not a card. `threads.com/messages/t/2239405853520443/` has a
        # 16-digit thread id that PASSES Luhn -- one in ten random 16-digit
        # runs does -- and blurring the address bar for the whole DM section is
        # a worse outcome than missing nothing.
        if re.search(r"https?://|www\.|\.com/|\.ua/", low):
            return False
        for m in re.findall(r"(?:\d[ \-]?){13,19}", t):
            d = _digits(m)
            if 13 <= len(d) <= 19 and luhn(d):
                return True
        # a masked PAN is still worth hiding: it names the card
        return bool(re.search(MASK + r"\s*\d{3,}", t)) or bool(re.search(r"\d{3,}\s*" + MASK, t))

    def cvv(t, low):
        return bool(re.search(r"\b(cvv|cvc|cvv2|cvc2)\b", low)) and bool(re.search(r"\b\d{3}\b", t))

    def phone(t, low):
        # The +38 prefix is OPTIONAL, and leaving it mandatory is how a full
        # record reached a proof frame: a Claude panel summary read
        # "(Київ, відділення 57, 0XXXXXXXXX, <recipient> ...)" -- the
        # national 0XX form, with the name and the delivery branch beside it,
        # and the rule did not fire. A Ukrainian mobile is 0 plus nine digits
        # however it is punctuated.
        return bool(
            re.search(
                r"(?<!\d)(?:\+?\s*3\s*8[\s\-()]*)?"
                r"\(?0\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
                t,
            )
        )

    def iban(t, low):
        # A Ukrainian IBAN is UA + 2 check digits + 25 more, but it is almost
        # always drawn part-masked ("UA57 ---- 1111111"), so requiring the full
        # 27 finds nothing. The prefix plus any digits is the real signature.
        return bool(re.search(r"\bUA\s?\d{2}\b", t)) and bool(
            re.search(r"\d", t.split("UA", 1)[-1])
        )

    def email(t, low):
        # Bounded on every side, because OCR of mangled Cyrillic produces long
        # runs with an @ in them. Two real misfires from this footage:
        #   pMEAHyrOCbAo@gorokhovsky.FoTOBMionJaTMTW10AWTqyWxKHMKOK3caiT
        #   caiTy@ababahalamaha.Ane Tak Wo6 pi3HWM
        # both from the Threads post, which names two @handles. The second one
        # survives a length bound -- ".Ane" is a plausible-looking 3-letter TLD
        # -- so the TLD has to be an ALLOWLIST, not a shape.
        return bool(
            re.search(
                r"(?<![\w.\-])[\w.\-+]{1,32}@[\w\-]{2,30}"
                r"\.(?:com|ua|net|org|io|co|me|info|edu|gov|dev|app)"
                r"(?:\.[a-z]{2,4})?(?![\w\-])",
                t,
                re.IGNORECASE,
            )
        )

    def balance(t, low):
        # a five- or six-figure account balance next to a currency word
        return bool(re.search(r"\b\d{2,3}[  ]\d{3}[.,]\d{2}\b", t)) and bool(
            re.search(r"uah|грн", low)
        )

    def expiry(t, low):
        return bool(re.search(r"\b(мм|mm)\s*/\s*(рр|yy|гг)\b", low)) or bool(
            re.search(r"\b(0[1-9]|1[0-2])\s*/\s*\d{2}\b", t)
        )

    return [
        ("card", "high", card),
        ("cvv", "high", cvv),
        ("expiry", "high", expiry),
        ("iban", "high", iban),
        ("balance", "medium", balance),
        ("phone", "medium", phone),
        ("email", "medium", email),
    ]


def sample_times(path, fps):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dur = float(out)
    n = max(1, int(dur * fps))
    return dur, [i / fps for i in range(n)]


def frames_of(path, fps, width):
    """Yield (pts_time, BGR ndarray) sampled at `fps`, scaled to `width` wide.

    The time is the frame's REAL presentation time, read from `showinfo`, not
    the sample index divided by the rate. The difference is the single
    costliest bug of the first edit: ffmpeg's fps filter emits, for the slot
    labelled 16 s, whichever input frame falls inside that 4-second slot --
    and a template cut at exactly 16.0 landed on a Notepad window instead of
    the spreadsheet cell OCR had read at ~20 s. Blank crops, garbage
    templates, 46% recall, 183 leaks on the render. showinfo's pts_time is
    the frame that was actually read.
    """
    import cv2  # noqa: F401 -- keeps the import local like the callers
    import threading
    import queue

    info = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    st = json.loads(info)["streams"][0]
    h = max(2, int(round(width * st["height"] / st["width"])) // 2 * 2)
    # `select` every STEP-th frame, not `fps=`: the fps filter REWRITES
    # timestamps onto its output grid, so showinfo after it would report
    # k/fps again -- the very number that was wrong. select keeps the input
    # frame's own pts, and -fps_mode passthrough keeps the muxer from
    # duplicating frames to fill the gaps.
    rate = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    num, _, den = rate.partition("/")
    src_fps = float(num) / float(den) if den and float(den) else 30.0
    step = max(1, int(round(src_fps / fps)))
    p = subprocess.Popen(
        ["ffmpeg", "-v", "info", "-nostdin"]
        + _encode.decode_args()
        + [
            "-i",
            path,
            "-vf",
            rf"select=not(mod(n\,{step})),scale={width}:{h},showinfo",
            "-fps_mode",
            "passthrough",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    times = queue.Queue()

    def pump():
        for raw in p.stderr:
            ln = raw.decode("utf-8", "replace")
            m = re.search(r"showinfo.*n:\s*(\d+).*?pts_time:\s*([\d.]+)", ln)
            if m:
                times.put(float(m.group(2)))
        times.put(None)

    threading.Thread(target=pump, daemon=True).start()
    n = width * h * 3
    i = 0
    while True:
        # Read the FRAME first, then its time. Waiting on the time first
        # deadlocked: ffmpeg blocks writing the frame to a stdout nobody is
        # reading, while this side waits for a log line ffmpeg has not
        # reached. The showinfo line for a frame is emitted before the muxer
        # writes it, so once the bytes are here the time is too.
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        try:
            t = times.get(timeout=5.0)
        except queue.Empty:
            t = None
        if t is None:
            t = i / fps
        yield t, np.frombuffer(buf, np.uint8).reshape(h, width, 3)
        i += 1
    p.stdout.close()
    p.wait()


def ocr_pass(path, fps=SAMPLE_FPS, width=OCR_WIDTH, skip_static=0.004):
    """Read every sampled frame ONCE and keep everything the OCR said.

    OCR is the whole cost of this tool -- seconds per frame on CPU -- and the
    first session paid it THREE times over 47 minutes of footage because the
    rules changed after each scan and only the matching hits had been kept.
    So this pass persists the raw lines (box, text, confidence) per frame, and
    the rules become a second pass that costs seconds. A rule tweak is now a
    re-read of a JSON file, not a 30-minute re-OCR.

    A frame close enough to the last frame that was actually read is SKIPPED
    and the previous frame's lines are re-stamped at the current time --
    timing stays honest, and the OCR call count drops with the stillness of
    the recording rather than with its length.
    """
    from rapidocr_onnxruntime import RapidOCR
    import cv2

    ocr = RapidOCR()
    frames = []
    nread = 0
    last_gray = None
    last_lines = []
    for t, img in frames_of(path, fps, width):
        small = cv2.resize(
            img, (320, max(2, 320 * img.shape[0] // img.shape[1])), interpolation=cv2.INTER_AREA
        )
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.int16)
        if last_gray is not None and skip_static:
            if float((np.abs(gray - last_gray) > 10).mean()) < skip_static:
                frames.append({"t": round(t, 2), "carried": True, "lines": last_lines})
                continue
        last_gray = gray
        nread += 1
        res, _ = ocr(img)
        H, W = img.shape[:2]
        lines = []
        for box, text, conf in res or []:
            # RapidOCR hands the score back as a STRING; coerce, do not trust.
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = 0.0
            if conf < 0.4 or not text.strip():
                continue
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            lines.append(
                {
                    "box": [
                        min(xs) / W,
                        min(ys) / H,
                        (max(xs) - min(xs)) / W,
                        (max(ys) - min(ys)) / H,
                    ],
                    "text": text.strip()[:80],
                    "conf": round(conf, 3),
                }
            )
        last_lines = lines
        frames.append({"t": round(t, 2), "carried": False, "lines": lines})
        if len(frames) % 30 == 0:
            print(f"    ...{t:7.1f}s  {nread}/{len(frames)} frames read", file=sys.stderr)
    print(
        f"    OCR read {nread} of {len(frames)} sampled frames "
        f"({100 * (1 - nread / max(1, len(frames))):.0f}% skipped as unchanged)",
        file=sys.stderr,
    )
    return frames


def apply_rules(frames, only=None, extra=None):
    """The cheap half: every rule against every cached line. Seconds."""
    rs = [r for r in rules() if not only or r[0] in only]
    for name, pat in (extra or {}).items():
        rx = re.compile(pat, re.IGNORECASE)
        rs.append((name, "find", lambda t, low, rx=rx: bool(rx.search(t))))
    hits = []
    for fr in frames:
        for ln in fr["lines"]:
            text = ln["text"]
            low = text.lower()
            for name, sev, test in rs:
                try:
                    ok = test(text, low)
                except Exception:
                    ok = False
                if ok:
                    hits.append(
                        {
                            "t": fr["t"],
                            "kind": name,
                            "severity": sev,
                            "text": text[:60],
                            "conf": ln["conf"],
                            "rect": list(ln["box"]),
                        }
                    )
    return hits


def scan(
    path,
    fps=SAMPLE_FPS,
    width=OCR_WIDTH,
    only=None,
    extra=None,
    skip_static=0.004,
    cache=None,
    from_cache=False,
):
    """OCR once (or load the cache), then apply the rules."""
    if from_cache and cache and os.path.exists(cache):
        frames = json.load(open(cache, encoding="utf-8"))["frames"]
        print(f"    rules re-applied to cached OCR ({len(frames)} frames)", file=sys.stderr)
    else:
        frames = ocr_pass(path, fps, width, skip_static)
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "src": _env.resolve(path),
                        "sample_fps": fps,
                        "width": width,
                        "frames": frames,
                    },
                    f,
                    ensure_ascii=False,
                )
    return apply_rules(frames, only, extra), len(frames)


def merge(hits, gap=6.0, pad=PAD):
    """Group hits of the same kind that overlap in space into one blur entry.

    Grouped by kind and by rough position, then given one time window covering
    every appearance plus a margin, because a field that comes back after a
    scroll is the same secret and deserves one rectangle, not nine.
    """
    out = []
    for kind in sorted({h["kind"] for h in hits}):
        group = sorted((h for h in hits if h["kind"] == kind), key=lambda h: h["t"])
        clusters = []
        for h in group:
            x, y, w, hh = h["rect"]
            placed = False
            for c in clusters:
                cx, cy, cw, chh = c["rect"]
                if (
                    not (x > cx + cw or x + w < cx or y > cy + chh or y + hh < cy)
                    and h["t"] - c["last"] <= gap * 6
                ):
                    nx, ny = min(cx, x), min(cy, y)
                    c["rect"] = [nx, ny, max(cx + cw, x + w) - nx, max(cy + chh, y + hh) - ny]
                    c["last"] = h["t"]
                    c["when"][1] = h["t"]
                    c["n"] += 1
                    c["texts"].add(h["text"])
                    placed = True
                    break
            if not placed:
                clusters.append(
                    {
                        "rect": list(h["rect"]),
                        "last": h["t"],
                        "when": [h["t"], h["t"]],
                        "n": 1,
                        "kind": kind,
                        "severity": h["severity"],
                        "texts": {h["text"]},
                    }
                )
        for c in clusters:
            x, y, w, hh = c["rect"]
            c["rect"] = [
                round(max(0.0, x - pad), 4),
                round(max(0.0, y - pad), 4),
                round(min(1.0, w + 2 * pad), 4),
                round(min(1.0, hh + 2 * pad), 4),
            ]
            c["when"] = [round(max(0.0, c["when"][0] - gap), 2), round(c["when"][1] + gap, 2)]
            c["texts"] = sorted(c["texts"])[:3]
            c.pop("last")
            out.append(c)
    return sorted(out, key=lambda c: (c["severity"] != "high", c["when"][0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", help="write the raw hit list here (JSON)")
    ap.add_argument(
        "--report", action="store_true", help="print what was found; blurs nothing, encodes nothing"
    )
    ap.add_argument(
        "--emit", action="store_true", help="print merged `blur` entries ready for the manifest"
    )
    ap.add_argument("--kinds", help="comma-separated subset of the rules")
    ap.add_argument(
        "--match",
        action="append",
        default=[],
        metavar="NAME=REGEX",
        help="also report where this pattern is on screen; "
        "repeatable. Severity 'find', never blurred by --emit.",
    )
    ap.add_argument(
        "--min-severity",
        default="medium",
        choices=["high", "medium"],
        help="which hits --emit turns into blur rectangles",
    )
    ap.add_argument(
        "--emit-pad",
        default="0,0",
        metavar="W,H",
        help="extra fractions of the frame added around each "
        "emitted rect, on each side. A detected phone sits "
        "inside a RECORD -- the name above it and the "
        "delivery address below it are the same secret, and "
        "this OCR cannot read Cyrillic names at all, so the "
        "only way to cover them is to grow out from the one "
        "field it could read.",
    )
    ap.add_argument("--fps", type=float, default=SAMPLE_FPS)
    ap.add_argument("--width", type=int, default=OCR_WIDTH)
    ap.add_argument(
        "--gap", type=float, default=6.0, help="seconds of margin added around each hit window"
    )
    ap.add_argument(
        "--skip-static",
        type=float,
        default=0.004,
        help="skip OCR on a frame this close to the last one read; "
        "0 disables. This is what makes a 47-minute scan "
        "finish -- see ocr_pass().",
    )
    ap.add_argument(
        "--ocr-cache",
        metavar="PATH",
        help="where the raw OCR lines are kept (default: next to "
        "--out, under ../ocr/<base>.ocr.json). Written on "
        "every OCR run; read back by --from-cache",
    )
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="skip the OCR entirely and re-apply the rules to the "
        "cached lines -- seconds instead of half an hour",
    )
    args = ap.parse_args()

    src = _env.resolve(args.src)
    only = set(args.kinds.split(",")) if args.kinds else None
    extra = dict(m.split("=", 1) for m in args.match)
    print(f"scanning {os.path.basename(src)} at {args.fps} fps ...", file=sys.stderr)
    cache = args.ocr_cache
    if not cache and args.out:
        base = os.path.splitext(os.path.basename(src))[0]
        cache = os.path.join(
            os.path.dirname(_env.resolve(args.out)), "..", "ocr", base + ".ocr.json"
        )
        cache = os.path.normpath(cache)
    if args.from_cache and not (cache and os.path.exists(cache)):
        raise SystemExit(f"--from-cache: no cache at {cache}; run once without it")
    hits, n = scan(
        src,
        args.fps,
        args.width,
        only,
        extra,
        args.skip_static,
        cache=cache,
        from_cache=args.from_cache,
    )
    groups = merge(hits, args.gap)

    print(
        f"\n{os.path.basename(src)}: {len(hits)} hit(s) in {n} sampled "
        f"frames -> {len(groups)} region(s)"
    )
    if args.report or not (args.out or args.emit):
        print(f"  {'kind':<9}{'sev':<8}{'when':>16} {'n':>4}  rect  / sample text")
        for g in groups:
            print(
                f"  {g['kind']:<9}{g['severity']:<8}"
                f"{g['when'][0]:7.1f}-{g['when'][1]:<8.1f}{g['n']:>4}  "
                f"[{', '.join(f'{v:.3f}' for v in g['rect'])}]"
            )
            for t in g["texts"]:
                print(f"      {t}")

    if args.emit:
        want = ["high"] if args.min_severity == "high" else ["high", "medium"]
        pw, ph = [float(v) for v in args.emit_pad.split(",")]
        entries = []
        for g in groups:
            if g["severity"] not in want:
                continue
            x, y, w, h = g["rect"]
            entries.append(
                {
                    "_why": f"{g['kind']} ({g['n']} frames): {g['texts'][0][:44]}",
                    "rect": [
                        round(max(0.0, x - pw), 4),
                        round(max(0.0, y - ph), 4),
                        round(min(1.0 - max(0.0, x - pw), w + 2 * pw), 4),
                        round(min(1.0 - max(0.0, y - ph), h + 2 * ph), 4),
                    ],
                    "when": g["when"],
                }
            )
        print("\n" + json.dumps(entries, ensure_ascii=False, indent=2))

    if args.out:
        out = _env.resolve(args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "src": _env.resolve(src),
                    "sample_fps": args.fps,
                    "frames": n,
                    "hits": hits,
                    "groups": groups,
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"\n  wrote {args.out}")


if __name__ == "__main__":
    main()
