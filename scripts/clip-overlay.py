#!/usr/bin/env python
"""Lay real video clips into a rendered sketch film, where and when the film says.

A sketch film is drawn in a browser one frame at a time, so it cannot play a video file itself.
Benchmark films need to: the clips a video model made ARE the result. So the film leaves a window
for each clip and says, through SK.REPORT() (saved by any stills run as report.json), where every
clip goes: {"clips": [{"src", "x", "y", "w", "h", "t0", "t1", "from", "speed", "audio_db",
"fit"}]}, screen pixels and film seconds. This lays each clip into its window in one encode pass:
trimmed from `from`, sped by `speed`, scaled to cover the window (or `"fit": "contain"`), looped
when `"loop": true` or else its last frame held to t1, and its own sound mixed in at `audio_db` when given, or brought to `audio_lufs` (the clip's own
loudness measured over its window, so clips from different makers sound alike); the film's score
should make room there: the film knows where.

Nothing is drawn over a clip after this, so a film keeps its labels and stamps outside the
windows; what the film drew inside a window (a placeholder, a poster) is covered.

    --film      the rendered sketch film (outputs/<slug>.mp4)
    --report    the film's report.json (default <film dir>/review/report.json)
    --out       the finished film (default outputs/<slug>-clips.mp4)
    --plan      list the placements and the ffmpeg graph; encode nothing (the free mode)

Invoke as:
    python scripts/sketch-render.py --manifest projects/<id>/sketch.json --stills 0 --into projects/<id>/temp/report
    python scripts/clip-overlay.py --film projects/<id>/outputs/<slug>.mp4 --report projects/<id>/temp/report/report.json --plan
    python scripts/clip-overlay.py --film projects/<id>/outputs/<slug>.mp4 --report projects/<id>/temp/report/report.json
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _encode  # noqa: E402
import _project  # noqa: E402


def loudness(path, start=0.0, dur=None):
    """Integrated loudness (LUFS) of a clip's sound over [start, start + dur]."""
    cmd = ["ffmpeg", "-nostats", "-ss", "%.3f" % start] + (["-t", "%.3f" % dur] if dur else [])
    out = subprocess.run(
        cmd + ["-i", path, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    ).stderr
    vals = [
        ln.split("I:")[1].split("LUFS")[0] for ln in out.splitlines() if ln.strip().startswith("I:")
    ]
    try:
        return float(vals[-1])
    except (IndexError, ValueError):
        return None


def probe_audio(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(out.stdout.strip())


def graph(clips, base_has_audio, fps):
    """The filter graph: input 0 is the film, input i+1 is clips[i]."""
    v, a, last, mix = [], [], "[0:v]", []
    for i, c in enumerate(clips):
        k = i + 1
        w, h = int(round(c["w"])) // 2 * 2, int(round(c["h"])) // 2 * 2
        t0, t1 = float(c["t0"]), float(c["t1"])
        sp = float(c.get("speed", 1) or 1)
        fit = (
            "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black"
            % (w, h, w, h)
            if c.get("fit") == "contain"
            else "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (w, h, w, h)
        )
        span = max(0.05, t1 - t0)
        v.append(
            "[%d:v]trim=start=%.3f:duration=%.3f,setpts=(PTS-STARTPTS)/%.4f,fps=%s,%s,setsar=1,"
            "tpad=stop_mode=clone:stop_duration=%.3f,setpts=PTS+%.3f/TB[c%d]"
            % (k, float(c.get("from", 0)), span * sp + 0.2, sp, fps, fit, span + 1, t0, k)
        )
        v.append(
            "%s[c%d]overlay=x=%d:y=%d:enable='between(t,%.3f,%.3f)':eof_action=pass[o%d]"
            % (last, k, int(round(c["x"])), int(round(c["y"])), t0, t1, k)
        )
        last = "[o%d]" % k
        if c.get("audio_db") is not None and c.get("_has_audio"):
            d = int(t0 * 1000)
            a.append(
                "[%d:a]atrim=start=%.3f,asetpts=PTS-STARTPTS,atempo=%.4f,atrim=duration=%.3f,"
                "volume=%.1fdB,adelay=%d|%d[a%d]"
                % (
                    k,
                    float(c.get("from", 0)),
                    sp if 0.5 <= sp <= 2 else 1,
                    max(0.05, t1 - t0),
                    float(c["audio_db"]),
                    d,
                    d,
                    k,
                )
            )
            mix.append("[a%d]" % k)
    fc = ";".join(v) + (";" if v else "")
    if mix:
        fc += ";".join(a) + ";" + ("[0:a]" if base_has_audio else "") + "".join(mix)
        fc += (
            "amix=inputs=%d:normalize=0:duration=first,lowpass=f=15000,alimiter=limit=0.6:level=false[aout]"
            % (len(mix) + (1 if base_has_audio else 0))
        )
    return fc.rstrip(";"), last, bool(mix)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--film", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument(
        "--plan", action="store_true", help="print placements and graph; encode nothing"
    )
    ap.add_argument(
        "--fps", default=None, help="the film's frame rate (default: read from the film)"
    )
    a = ap.parse_args()

    film = _env.resolve(a.film)
    fdir = os.path.dirname(film)
    rep = _env.resolve(a.report) if a.report else os.path.join(fdir, "review", "report.json")
    with open(rep, encoding="utf-8") as f:
        report = json.load(f)
    clips = [dict(c) for c in report.get("clips", [])]
    proj = os.path.dirname(fdir)  # projects/<id>/outputs/<film> -> projects/<id>
    for c in clips:
        c["src"] = c["src"] if os.path.isabs(c["src"]) else os.path.join(proj, c["src"])
        if not os.path.exists(c["src"]):
            sys.exit("clip not found: %s" % c["src"])
        c["_has_audio"] = probe_audio(c["src"])
        if c.get("audio_lufs") is not None and c["_has_audio"]:
            # each clip brought to one loudness, so three voices from three models sound alike
            got = loudness(c["src"], float(c.get("from", 0)), float(c["t1"]) - float(c["t0"]))
            if got is not None and got > -70:
                c["audio_db"] = round(float(c["audio_lufs"]) - got, 1)
    fps = (
        a.fps
        or subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "csv=p=0",
                film,
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    base_audio = probe_audio(film)
    fc, vout, has_mix = graph(clips, base_audio, fps)
    out = _env.resolve(a.out) if a.out else os.path.splitext(film)[0] + "-clips.mp4"
    print("%d clips into %s (%s fps)" % (len(clips), os.path.relpath(film, _env.ROOT), fps))
    for c in clips:
        print(
            "  %6.2f-%6.2f  %4dx%-4d at %4d,%-4d  from %.2f x%s %s  %s"
            % (
                c["t0"],
                c["t1"],
                c["w"],
                c["h"],
                c["x"],
                c["y"],
                c.get("from", 0),
                c.get("speed", 1),
                "audio %sdB" % c["audio_db"] if c.get("audio_db") is not None else "",
                os.path.relpath(c["src"], _env.ROOT),
            )
        )
    if a.plan:
        print("\nfilter graph (%d characters):\n%s" % (len(fc), fc.replace(";", ";\n")))
        return 0
    cfg = _encode.resolve({"cq": 18, "preset": "p5", "audio_bitrate": "256k"})
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", film]
    for c in clips:  # a looping clip repeats until its window closes (the trim bounds it)
        cmd += (["-stream_loop", "-1"] if c.get("loop") else []) + ["-i", c["src"]]
    gpath = os.path.join(fdir, ".clip-overlay.graph")
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(fc)
    cmd += ["-filter_complex_script", gpath, "-map", vout]
    cmd += ["-map", "[aout]"] if has_mix else (["-map", "0:a"] if base_audio else [])
    cmd += _encode.video_args(cfg) + (_encode.audio_args(cfg) if (has_mix or base_audio) else [])
    cmd += ["-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    os.remove(gpath)
    print("wrote %s" % os.path.relpath(out, _env.ROOT))
    pid = os.path.basename(proj)
    _project.record(
        pid,
        "clips laid into the film",
        out=out,
        script=__file__,
        argv=sys.argv[1:],
        kind="film",
        note="%d clips from %s" % (len(clips), os.path.relpath(rep, proj)),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
