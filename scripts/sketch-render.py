#!/usr/bin/env python
"""Render a sketch film: the self-contained HTML player, review stills, and the video.

A sketch film is JavaScript: sketch/engine.js + sketch/props.js + the project's film.js, where
every frame is a pure function of time. This script bundles those with the fonts and the
mastered soundtrack into one HTML file (plays anywhere, offline), and renders the video by
opening that page in headless Edge/Chrome (the browser html-to-image.py already finds -- no
Node, no Playwright). The page draws each frame and POSTs its PNG to a tiny local server here,
which pipes it straight into ffmpeg; `_encode` chooses the encoder.

Every stage is timed into the project's run log; `--timings` prints the latest time of every
stage of every sketch tool for the project -- the "how long does a film take" answer.

Outputs (projects/<id>/outputs/):
    <slug>.html                 the player (fonts, code, audio inlined)
    artifact/<slug>.html        the same, without html/head/body, for claude.ai Artifacts
    <slug>.mp4                  the film (audio + a soft English subtitle track when captions exist)
    <slug>_poster.png           the poster frame
    review/<t>.png, review/sheet.png    (--stills / --sheet)

Manifest keys: title, description, slug, duration, fps, film ("film.js"), fonts
([{"file", "family", "weight", "load"}]), images ({"logo": "assets/logo.png"} -> SK.IMG.logo),
player ({accent, paper, ink, hint, hint_font}), poster_t,
render ({cq, preset, audio_bitrate, encoder}).

Invoke as:
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --plan
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 1.5,9,23.8 --sheet
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --automation
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --bundle
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json            (full render)
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --draft    (30 fps, faster)
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --timings
"""

import sys
import os
import re
import json
import html
import time
import base64
import shutil
import argparse
import tempfile
import threading
import subprocess
from importlib import import_module
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _encode  # noqa: E402
import _project  # noqa: E402
import _sketch  # noqa: E402

SKETCH = os.path.join(_env.ROOT, "sketch")
FRAME_BYTES = 1920 * 1080 * 4  # the page exports raw RGBA frames


# ------------------------------------------------------------------ bundling
def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def vo_timeline(m):
    """sketch-vo's timeline, trimmed to what a film needs (line starts/ends and word times)."""
    p = _sketch.rel(m, m.get("audio", {}).get("vo_timeline", "audio/vo/timeline.json"))
    if not os.path.exists(p):
        return {"lines": []}
    with open(p, encoding="utf-8") as f:
        tl = json.load(f)
    return {
        "lines": [{"start": L["start"], "end": L["end"], "words": L["words"]} for L in tl["lines"]]
    }


def bundle(m, audio=True):
    """The player page with everything inlined. Returns the HTML text."""
    with open(os.path.join(SKETCH, "player.html"), encoding="utf-8") as f:
        page = f.read()
    faces, loads = [], []
    for fnt in m.get("fonts", []):
        p = _env.resolve(fnt["file"])
        fmt = "woff2" if p.endswith(".woff2") else "truetype"
        faces.append(
            "@font-face { font-family: '%s'; src: url(data:font/%s;base64,%s) format('%s'); "
            "font-weight: %s; font-display: block; }"
            % (fnt["family"], fmt, b64(p), fmt, fnt.get("weight", "400"))
        )
        for w in str(fnt.get("load", fnt.get("weight", "400"))).split():
            loads.append('%s 60px "%s"' % (w, fnt["family"]))
    pl = {
        "accent": "#d9733f",
        "paper": "#f7f2e7",
        "ink": "#2a2521",
        "hint": "play · sound on",
        "hint_font": "system-ui, sans-serif",
        **m.get("player", {}),
    }
    film = read_text(_sketch.rel(m, m.get("film", "film.js")))
    mp3 = os.path.join(m["_audio"], "final.mp3")
    src = "data:audio/mpeg;base64," + b64(mp3) if audio and os.path.exists(mp3) else ""
    rep = {
        "__TITLE__": html.escape(m.get("title", m["_id"])),
        "__DESCRIPTION__": html.escape(m.get("description", "")),
        "__FONTFACES__": "\n".join(faces),
        "__FONT_LOADS__": json.dumps(loads),
        "__ACCENT__": pl["accent"],
        "__PAPER__": pl["paper"],
        "__INK__": pl["ink"],
        "__HINT__": html.escape(pl["hint"]),
        "__HINT_FONT__": pl["hint_font"],
        "__POSTER_T__": str(m.get("poster_t", m["duration"] - 1)),
        "__ENGINE__": read_text(os.path.join(SKETCH, "engine.js")),
        "__PROPS__": read_text(os.path.join(SKETCH, "props.js")),
        "__FILM__": film,
        "__AUDIO__": src,
        "__VO__": json.dumps(vo_timeline(m)),
        "__IMAGES__": json.dumps(
            {
                k: "data:%s;base64,%s" % (mime(v), b64(_sketch.rel(m, v)))
                for k, v in m.get("images", {}).items()
            }
        ),
    }
    # one pass, so a placeholder-looking string inside the film code is never re-substituted
    return re.sub("|".join(re.escape(k) for k in rep), lambda mo: rep[mo.group(0)], page)


def artifact_flavour(page):
    """claude.ai Artifacts wrap the page in their own doctype/html/head/body and viewport meta."""
    return re.sub(
        r"<!doctype html>\s*|</?html[^>]*>\s*|</?head>\s*|</?body>\s*"
        r'|<meta charset[^>]*>\s*|<meta name="viewport"[^>]*>\s*',
        "",
        page,
        flags=re.IGNORECASE,
    )


# ------------------------------------------------------------------ the page drives, we listen
class Session:
    """Serve one page to headless Chromium and collect what it POSTs back."""

    def __init__(self, page, on_frame=None, on_still=None):
        self.page = page.encode("utf-8")
        self.on_frame, self.on_still = on_frame, on_still
        self.done = threading.Event()
        self.error, self.automation, self.frames, self.last = None, None, 0, time.time()
        sess = self

        class H(BaseHTTPRequestHandler):
            # keep-alive: an HTTP/1.0 server opens a new connection for every 8 MB frame, and a
            # render died on the one that got reset (~350 frames in, "Failed to fetch")
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Connection", "keep-alive")
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(sess.page)))
                self.end_headers()
                self.wfile.write(sess.page)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                path, _, q = self.path.partition("?")
                sess.last = time.time()
                try:
                    if path == "/frame" and sess.on_frame:
                        sess.on_frame(int(q.split("=")[1]), body)
                        sess.frames += 1
                    elif path == "/still" and sess.on_still:
                        sess.on_still(q.split("=")[1], body)
                    elif path == "/automation":
                        sess.automation = json.loads(body)
                    elif path == "/error":
                        sess.error = body.decode("utf-8", "replace")
                        sess.done.set()
                    elif path == "/done":
                        sess.done.set()
                except Exception as e:  # noqa: BLE001 -- a handler that dies silently leaves the page waiting forever
                    sess.error = "%s while handling %s: %s" % (type(e).__name__, self.path, e)
                    sess.done.set()
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

        class Server(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                # Chromium closing its keep-alive connection when the run ends is not an error
                if not isinstance(sys.exc_info()[1], (ConnectionError, OSError)):
                    super().handle_error(request, client_address)

        self.server = Server(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def run(self, query, stall=90):
        h2i = import_module("html-to-image")
        browsers = h2i.find_browsers()
        if not browsers:
            sys.exit("no Edge/Chrome found (set HTML2IMG_BROWSER to a Chromium executable)")
        prof = tempfile.mkdtemp(prefix="sketch-render-")
        url = "http://127.0.0.1:%d/film.html?%s" % (self.server.server_address[1], query)
        # the four --disable-* flags keep Chromium from throttling a page it thinks nobody sees:
        # a headless window on Windows counts as occluded, and a throttled page stalls a render
        cmd = [
            browsers[0],
            "--headless=new",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-features=CalculateNativeWinOcclusion",
            "--no-first-run",
            "--no-default-browser-check",
            "--mute-audio",
            "--hide-scrollbars",
            "--user-data-dir=" + prof,
            "--window-size=1920,1080",
            url,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            while not self.done.wait(1.0):
                if proc.poll() is not None:
                    self.error = self.error or "browser exited early (code %s)" % proc.returncode
                    break
                if time.time() - self.last > stall:
                    self.error = "no progress from the page for %ds" % stall
                    break
        finally:
            kill_tree(proc)
            self.server.shutdown()
            shutil.rmtree(prof, ignore_errors=True)
        if self.error:
            sys.exit("page error: %s" % self.error)


def kill_tree(proc):
    """Chromium is a process tree; on Windows killing the parent leaves the renderer and GPU
    children running (measured: a 1.3 GB renderer outlived its run). Take the whole tree."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.kill()
    proc.wait(timeout=10)


def contact_sheet(paths, out, cols=4):
    from PIL import Image, ImageDraw

    w, h = 1920 // cols, 1080 // cols
    rows = (len(paths) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * h), "white")
    d = ImageDraw.Draw(S)
    for i, p in enumerate(paths):
        x, y = (i % cols) * w, (i // cols) * h
        S.paste(Image.open(p).resize((w, h)), (x, y))
        d.rectangle([x, y, x + 64, y + 20], fill="black")
        d.text((x + 5, y + 4), os.path.splitext(os.path.basename(p))[0], fill="white")
    S.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--plan", action="store_true", help="check inputs and price the render; render nothing"
    )
    ap.add_argument("--bundle", action="store_true", help="only write the HTML player(s)")
    ap.add_argument("--stills", help="comma list of times -> outputs/review/<t>.png")
    ap.add_argument(
        "--sheet",
        action="store_true",
        help="with --stills: also tile them into outputs/review/sheet.png",
    )
    ap.add_argument(
        "--automation",
        action="store_true",
        help="write temp/automation.json for sketch-audio's 'air' cues",
    )
    ap.add_argument(
        "--draft", action="store_true", help="30 fps, lower quality: a fast preview render"
    )
    ap.add_argument("--fps", type=int)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument(
        "--timings",
        action="store_true",
        help="print the latest stage timings of every sketch tool for this project",
    )
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    slug = _sketch.slug(m)
    if args.timings:
        rep = _sketch.timing_report(m["_dir"])
        total = 0.0
        for tool in ("sketch-vo", "sketch-audio", "sketch-render"):
            for stage, secs in rep.get(tool, {}).items():
                print("  %-14s %-12s %8.1fs" % (tool, stage, secs))
                total += secs
        print("  %-27s %8.1fs" % ("machine time", total))
        return

    fps = args.fps or (30 if args.draft else int(m.get("fps", 60)))
    t1 = args.t1 if args.t1 is not None else float(m["duration"])
    cfg = _encode.resolve(
        {
            "cq": 16,
            "preset": "p6",
            "audio_bitrate": "320k",
            **m.get("render", {}),
            **({"cq": 24, "preset": "p3"} if args.draft else {}),
        }
    )
    film = _sketch.rel(m, m.get("film", "film.js"))
    final = os.path.join(m["_audio"], "final.wav")
    srt = os.path.join(m["_outputs"], slug + ".srt")
    n_frames = int(round((t1 - args.t0) * fps))
    print("%s  %.1fs  %d fps  %d frames" % (m["_id"], t1 - args.t0, fps, n_frames))
    print(
        "  film:    %s%s"
        % (os.path.relpath(film, _env.ROOT), "" if os.path.exists(film) else "  (MISSING)")
    )
    print(
        "  audio:   %s"
        % (
            "audio/final.wav"
            if os.path.exists(final)
            else "none yet -- run sketch-audio.py (the video will be silent)"
        )
    )
    print("  encoder: %s" % _encode.describe(cfg))
    for fnt in m.get("fonts", []):
        if not os.path.exists(_env.resolve(fnt["file"])):
            sys.exit("font missing: %s" % fnt["file"])
    if args.plan:
        print("\n  --plan: nothing rendered")
        return

    names = (
        ["bundle"]
        + (["stills"] if args.stills else [])
        + (["automation"] if args.automation else [])
    )
    full = not (args.bundle or args.stills or args.automation)
    if full:
        names += ["frames", "mux", "poster"]
    with _sketch.Stages(m, "sketch-render", names, argv=sys.argv[1:]) as st:
        with st("bundle"):
            page = bundle(m)
            out_html = os.path.join(m["_outputs"], slug + ".html")
            with open(out_html, "w", encoding="utf-8") as f:
                f.write(page)
            os.makedirs(os.path.join(m["_outputs"], "artifact"), exist_ok=True)
            with open(
                os.path.join(m["_outputs"], "artifact", slug + ".html"), "w", encoding="utf-8"
            ) as f:
                f.write(artifact_flavour(page))
            print("  %s (%.1f MB)" % (os.path.relpath(out_html, _env.ROOT), len(page) / 1e6))
        light = bundle(m, audio=False)  # the renderer needs no soundtrack inside the page

        if args.stills:
            with st("stills"):
                rdir = os.path.join(m["_outputs"], "review")
                os.makedirs(rdir, exist_ok=True)
                got = []

                def save(t, body):
                    p = os.path.join(rdir, "%06.2f.png" % float(t))
                    with open(p, "wb") as f:
                        f.write(body)
                    got.append(p)

                Session(light, on_still=save).run("stills=" + args.stills)
                if args.sheet:
                    contact_sheet(
                        got, os.path.join(rdir, "sheet.png"), cols=2 if len(got) <= 4 else 4
                    )
                print("  %d stills -> %s" % (len(got), os.path.relpath(rdir, _env.ROOT)))

        if args.automation:
            with st("automation"):
                s = Session(light)
                s.run("automation=1")
                p = os.path.join(m["_temp"], "automation.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(s.automation, f)
                print(
                    "  %s: %s"
                    % (os.path.relpath(p, _env.ROOT), ", ".join(s.automation or {}) or "no tracks")
                )

        if not full:
            return

        silent = os.path.join(m["_temp"], slug + "_silent.mp4")
        with st("frames"):
            ff = subprocess.Popen(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgba",
                    "-s",
                    "1920x1080",
                    "-framerate",
                    str(fps),
                    "-i",
                    "-",
                ]
                + _encode.video_args(cfg)
                + ["-movflags", "+faststart", silent],
                stdin=subprocess.PIPE,
            )
            t_start, expect = time.time(), [0]

            def frame(i, body):
                if i < expect[0]:
                    return  # a retried POST whose first attempt already landed
                if i != expect[0]:
                    raise RuntimeError("frame %d arrived, expected %d" % (i, expect[0]))
                if len(body) != FRAME_BYTES:
                    raise RuntimeError(
                        "frame %d is %d bytes, expected %d (1920x1080 RGBA)"
                        % (i, len(body), FRAME_BYTES)
                    )
                ff.stdin.write(body)
                expect[0] += 1
                if i % (fps * 5) == 0:
                    el = time.time() - t_start
                    print(
                        "  frame %d/%d  %.1f fps  eta %.0fs"
                        % (
                            i,
                            n_frames,
                            (i + 1) / max(el, 1e-3),
                            (n_frames - i - 1) / max((i + 1) / max(el, 1e-3), 1e-3),
                        ),
                        flush=True,
                    )

            Session(light, on_frame=frame).run("export=1&fps=%d&from=%s&to=%s" % (fps, args.t0, t1))
            ff.stdin.close()
            if ff.wait() != 0:
                sys.exit("ffmpeg failed encoding the frames")
            if expect[0] != n_frames:
                sys.exit("got %d frames, expected %d" % (expect[0], n_frames))

        out = os.path.join(m["_outputs"], slug + ("_draft" if args.draft else "") + ".mp4")
        with st("mux"):
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", silent]
            maps = ["-map", "0:v"]
            if os.path.exists(final):
                cmd += ["-ss", str(args.t0), "-i", final]
                maps += ["-map", "1:a"]
            if os.path.exists(srt) and args.t0 == 0:
                cmd += ["-i", srt]
                maps += [
                    "-map",
                    "%d:s" % (2 if os.path.exists(final) else 1),
                    "-c:s",
                    "mov_text",
                    "-metadata:s:s:0",
                    "language=eng",
                    "-disposition:s:0",
                    "0",
                ]
            # -t, never -shortest: the subtitle track ends early and -shortest cuts the film there
            cmd += (
                maps
                + ["-c:v", "copy"]
                + (_encode.audio_args(cfg) if os.path.exists(final) else [])
                + ["-t", "%.3f" % (t1 - args.t0), "-movflags", "+faststart", out]
            )
            subprocess.run(cmd, check=True)
            dur = float(
                subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "csv=p=0",
                        out,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
            if abs(dur - (t1 - args.t0)) > 0.1:
                sys.exit("rendered %.2fs, expected %.2fs" % (dur, t1 - args.t0))
            print(
                "  %s  %.2fs  %.1f MB"
                % (os.path.relpath(out, _env.ROOT), dur, os.path.getsize(out) / 1e6)
            )
        poster = os.path.join(m["_outputs"], slug + "_poster.png")
        with st("poster"):
            pt = min(float(m.get("poster_t", t1 - 1)) - args.t0, dur - 0.05)
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    str(max(0, pt)),
                    "-i",
                    out,
                    "-frames:v",
                    "1",
                    poster,
                ],
                check=True,
            )

    _project.record(
        m["_id"],
        "sketch film rendered (%d fps%s)" % (fps, ", draft" if args.draft else ""),
        out=out,
        script=__file__,
        argv=sys.argv[1:],
        kind="video",
        manifest=m["_path"],
        sidecars={"html": out_html, "poster": poster, "srt": srt if os.path.exists(srt) else None},
    )


if __name__ == "__main__":
    main()
