"""A narrated film made of still pictures, one per line: the "entire history of X" format.

A manifest lists scenes; each scene is one narrated line and one picture (made elsewhere, e.g. in
Gemini on the web, and saved as images/<id>.png|jpg beside the manifest). The script voices every
line (Gemini TTS through sketch-vo.py's backend, or free edge-tts for a draft), lays the pictures
end to end so each one holds exactly as long as its line plus the gap after it, gives every still a
slow camera move so the picture never stands still (Shorts guidebook rule 33), puts a quiet music
bed under the voice if one is named, and renders it in one encode.

The format was measured off CEOzoned's "The ENTIRE History of Instagram" (projects/
anthropic-history-short/still-film.json, reference._measured): a new still every ~3.6 s, a calm
narrator at ~156 words a minute, 0.48 s pauses, no burned captions, words only inside the pictures.

Manifest keys: frame [w, h], fps, voice {tts: gemini|edge, voice, model, style, rate}, gap_s,
lead_s, tail_s, music {file | score, offset_s, db_under_voice}, motion {zoom, pan}, render {...}, scenes [{id, line,
image (the prompt), file (optional picture path), cut (true: kept, not played)}]. A scene with no picture yet renders as a card
with its line, so the timing can be watched before every picture exists.

Invoke as:
    python scripts/still-film.py --manifest projects/<id>/still-film.json --plan        (free)
    python scripts/still-film.py --manifest projects/<id>/still-film.json --prompts     (free)
    python scripts/still-film.py --manifest projects/<id>/still-film.json --voice
    python scripts/still-film.py --manifest projects/<id>/still-film.json --render
    python scripts/still-film.py --manifest projects/<id>/still-film.json --voice --tts edge
"""

import sys
import os
import json
import hashlib
import argparse
import asyncio
import subprocess
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import _encode  # noqa: E402 -- the one place encoder keys are chosen
import _project  # noqa: E402

DEFAULT_RENDER = {"speed": 5, "cq": 19, "maxrate": "14M", "bufsize": "28M"}
SR = 48000


def load(path):
    m = json.load(open(path, encoding="utf-8"))
    m["_dir"] = os.path.dirname(os.path.abspath(path))
    # a scene marked "cut" stays in the manifest (its take and picture are kept) but leaves the film
    m["scenes"] = [s for s in m["scenes"] if not s.get("cut")]
    return m


def pdir(m, *p):
    return os.path.join(m["_dir"], *p)


def picture(m, s):
    """The picture for a scene: its `file`, else images/<id>.(png|jpg|jpeg|webp)."""
    if s.get("file"):
        f = _env.resolve(s["file"], m["_dir"])
        return f if os.path.exists(f) else None
    for ext in ("png", "jpg", "jpeg", "webp"):
        f = pdir(m, "images", "%s.%s" % (s["id"], ext))
        if os.path.exists(f):
            return f
    return None


def vo_key(m, s, tts):
    v = {k: x for k, x in (m.get("voice") or {}).items() if k != "tempo"}
    v["tts"] = tts
    return hashlib.sha1(json.dumps([s["line"], v], sort_keys=True).encode()).hexdigest()[:12]


def vo_path(m, s, tts):
    return pdir(m, "audio", "vo", "%s.%s.%s.wav" % (s["id"], tts, vo_key(m, s, tts)))


def take(m, s, tts):
    """The take as the film plays it: voice.tempo (pitch kept, ffmpeg atempo) applied once, cached.

    Tempo is not part of the take's key, so changing it never re-records a line.
    """
    f = vo_path(m, s, tts)
    t = float((m.get("voice") or {}).get("tempo", 1.0))
    if abs(t - 1.0) < 1e-3 or not os.path.exists(f):
        return f
    out = f[:-4] + ".t%.3f.wav" % t
    if not os.path.exists(out):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", f, "-af", "atempo=%g" % t, out], check=True
        )
    return out


def wav_read(f):
    """A wav as mono float32 and its rate."""
    from scipy.io import wavfile

    sr, x = wavfile.read(f)
    if x.dtype.kind == "i":
        x = x.astype(np.float32) / np.iinfo(x.dtype).max
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x.astype(np.float32), sr


def wav_write(f, x, sr):
    from scipy.io import wavfile

    wavfile.write(f, sr, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def wav_dur(f):
    x, sr = wav_read(f)
    return len(x) / sr


def _sketchvo():
    spec = importlib.util.spec_from_file_location(
        "sketch_vo", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sketch-vo.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def trim_silence(x, sr, floor_db=-45.0, keep=0.04):
    """Cut leading and trailing silence a TTS take carries, keeping a breath of room."""
    if not len(x):
        return x
    a = np.abs(x)
    thr = 10 ** (floor_db / 20)
    idx = np.where(a > thr)[0]
    if not len(idx):
        return x
    k = int(keep * sr)
    return x[max(0, idx[0] - k) : min(len(x), idx[-1] + k)]


def voice(m, tts, only=None):
    v = m.get("voice") or {}
    os.makedirs(pdir(m, "audio", "vo"), exist_ok=True)
    cost = 0.0
    sv = None
    for s in m["scenes"]:
        if only and s["id"] not in only:
            continue
        out = vo_path(m, s, tts)
        if os.path.exists(out):
            continue
        if tts == "edge":
            import edge_tts

            tmp = out + ".mp3"
            rate = v.get("rate") or "+0%"
            asyncio.run(
                edge_tts.Communicate(
                    s["line"], v.get("edge_voice", "en-US-GuyNeural"), rate=rate
                ).save(tmp)
            )
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ac", "1", "-ar", str(SR), out],
                check=True,
            )
            os.remove(tmp)
            x, sr = wav_read(out)
        else:
            sv = sv or _sketchvo()
            try:
                x, info = sv.gemini_take(s["line"], v)
            except sv.Refused as e:
                # a content block, not a glitch: asking again does not help, rephrase the line
                print("  %s  REFUSED by Gemini TTS (%s): rephrase it" % (s["id"], str(e)[:80]))
                continue
            sr = sv.SR
            cost += float(info.get("cost_usd") or 0)
        x = trim_silence(np.asarray(x, dtype=np.float32), sr)
        wav_write(out, x, sr)
        print("  %s  %.2fs  %s" % (s["id"], len(x) / sr, s["line"][:60]))
    if cost:
        print("  voice cost: $%.4f" % cost)


def timeline(m, tts):
    """Each scene's start and hold: its line plus the gap after it (the lead before the first)."""
    gap = float(m.get("gap_s", 0.35))
    lead = float(m.get("lead_s", 0.25))
    tail = float(m.get("tail_s", 1.2))
    t, rows = 0.0, []
    for i, s in enumerate(m["scenes"]):
        f = take(m, s, tts)
        d = wav_dur(f) if os.path.exists(f) else len(s["line"].split()) / 2.6
        pre = lead if i == 0 else 0.0
        post = tail if i == len(m["scenes"]) - 1 else gap
        rows.append(
            {"id": s["id"], "start": t, "voice_at": t + pre, "voice": d, "hold": pre + d + post}
        )
        t += pre + d + post
    return rows, t


def placeholder(m, s, path):
    w, h = m.get("frame", [1080, 1920])
    im = Image.new("RGB", (w, h), (236, 224, 200))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("arial.ttf", 54)
    except OSError:
        f = ImageFont.load_default()
    words, lines, cur = s["line"].split(), [], ""
    for wd in words:
        if len(cur) + len(wd) > 26:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    y = h // 2 - len(lines) * 40
    d.text((60, 120), s["id"] + "  (no picture yet)", fill=(150, 90, 60), font=f)
    for ln in lines:
        d.text((60, y), ln, fill=(40, 30, 25), font=f)
        y += 80
    im.save(path)


def motion_filter(i, w, h, fps, hold, mo):
    """A slow push in, out or across a still, alternating per scene so cuts feel different.

    The still is scaled up 2x first so the per-frame crop moves in half pixels: an integer crop
    of a 1x picture steps visibly at these speeds.
    """
    zoom = float(mo.get("zoom", 0.08))
    pan = float(mo.get("pan", 0.04))
    n = max(1, int(round(hold * fps)))
    W, H = 2 * w, 2 * h
    kinds = mo.get("kinds") or ["in", "out"]
    kind = kinds[i % len(kinds)]
    p = "(n/%d)" % n
    ease = (
        "(%s)" % p
    )  # linear: an eased move stops dead at every cut, and a Short may not stand still
    if kind == "in":
        z = "(1+%g*%s)" % (zoom, ease)
        x, y = "(iw-ow)/2", "(ih-oh)/2"
    elif kind == "out":
        z = "(1+%g*(1-%s))" % (zoom, ease)
        x, y = "(iw-ow)/2", "(ih-oh)/2"
    else:
        z = "(1+%g)" % (zoom * 0.6)
        if kind == "left":
            x, y = "(iw-ow)*(0.5+%g*(0.5-%s))" % (pan * 10, ease), "(ih-oh)/2"
        elif kind == "right":
            x, y = "(iw-ow)*(0.5-%g*(0.5-%s))" % (pan * 10, ease), "(ih-oh)/2"
        else:
            x, y = "(iw-ow)/2", "(ih-oh)*(0.5+%g*(0.5-%s))" % (pan * 10, ease)
    # crop's w/h are fixed at init, so zoom is a per-frame scale; crop then follows x/y per frame
    return (
        "[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,"
        "loop=loop=-1:size=1,trim=end_frame=%d,setpts=N/%d/TB,"
        "scale=w='trunc(%d*%s/2)*2':h='trunc(%d*%s/2)*2':eval=frame,"
        "crop=%d:%d:'%s':'%s',scale=%d:%d,setsar=1,fps=%d[v%d]"
        % (i, W, H, W, H, n, fps, W, z, H, z, W, H, x, y, w, h, fps, i)
    )


def music_from_score(m, voice, sr, total, tmp):
    """Synthesize the music bed from a score (scripts/_sketchaudio.py) and level it under the voice.

    music.score is a score.json beside the manifest; music.db_under_voice is the bed's RMS against
    the voice's RMS while it speaks (measured off the reference: bed -25.9 dBFS, speech -17.1).
    """
    import _sketchaudio as SA

    mc = m["music"]
    score = json.load(open(_env.resolve(mc["score"], m["_dir"]), encoding="utf-8"))
    out = os.path.join(tmp, "music.wav")
    off = float(
        mc.get("offset_s", 0)
    )  # start the score this far in (keeps it on the story after a cut)
    dry, wet, _ = SA.render_score(score, off + total + 1.0)  # (2, n) each, at SA.SR
    x = (np.asarray(dry) + np.asarray(wet) * 0.6).mean(axis=0).astype(np.float32)
    x = x[int(off * SA.SR) :]
    if SA.SR != sr:
        from scipy.signal import resample_poly

        x = resample_poly(x, sr, SA.SR).astype(np.float32)
    talk = voice[np.abs(voice) > 0.01]
    v_db = 20 * np.log10(np.sqrt((talk**2).mean()) + 1e-9)
    m_db = 20 * np.log10(np.sqrt((x**2).mean()) + 1e-9)
    gain = 10 ** ((v_db + float(mc.get("db_under_voice", -9)) - m_db) / 20)
    wav_write(out, np.clip(x * gain, -1, 1), sr)
    print(
        "  music bed from %s: voice %.1f dB, bed %.1f dB"
        % (mc["score"], v_db, v_db + float(mc.get("db_under_voice", -9)))
    )
    return out


def render(m, tts, out, manifest_path):
    rows, total = timeline(m, tts)
    w, h = m.get("frame", [1080, 1920])
    fps = int(m.get("fps", 30))
    mo = m.get("motion") or {}
    tmp = pdir(m, "temp", "still-film")
    os.makedirs(tmp, exist_ok=True)
    missing = []
    inputs, chains = [], []
    for i, (s, r) in enumerate(zip(m["scenes"], rows)):
        f = picture(m, s)
        if not f:
            f = os.path.join(tmp, "card-%s.png" % s["id"])
            placeholder(m, s, f)
            missing.append(s["id"])
        inputs += ["-i", f]
        chains.append(motion_filter(i, w, h, fps, r["hold"], mo))
    n = len(rows)
    graph = ";".join(chains) + ";" + "".join("[v%d]" % i for i in range(n))
    graph += "concat=n=%d:v=1:a=0,format=yuv420p[vout]" % n

    # the narration: every take placed at its own start, so picture and voice cannot drift apart
    sr = SR
    bed = np.zeros(int((total + 0.5) * sr), dtype=np.float32)
    for s, r in zip(m["scenes"], rows):
        f = take(m, s, tts)
        if not os.path.exists(f):
            sys.exit("no voice for %s yet: run --voice first" % s["id"])
        x, xsr = wav_read(f)
        if xsr != sr:
            from scipy.signal import resample_poly

            x = resample_poly(x, sr, xsr).astype(np.float32)
        a = int(r["voice_at"] * sr)
        bed[a : a + len(x)] += x[: len(bed) - a]
    vo_wav = os.path.join(tmp, "narration.wav")
    wav_write(vo_wav, bed, sr)
    ai = len(rows)
    inputs += ["-i", vo_wav]
    mcfg = m.get("music") or {}
    mus = mcfg.get("file")
    if mcfg.get("score"):
        mus = music_from_score(m, bed, sr, total, tmp)
    if mus:
        mus = _env.resolve(mus, m["_dir"])
        inputs += ["-stream_loop", "-1", "-i", mus]
        # the bed's level was set against the voice in music_from_score (or is the file's own)
        graph += (
            ";[%d:a]volume=1.0[nv];[%d:a]atrim=0:%f,afade=t=in:d=1.5,afade=t=out:st=%f:d=2.5[mb];"
            "[nv][mb]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=7[aout]"
            % (ai, ai + 1, total, max(0, total - 2.5))
        )
    else:
        graph += ";[%d:a]loudnorm=I=-14:TP=-1.5:LRA=7[aout]" % ai
    rcfg = _encode.resolve(dict(DEFAULT_RENDER, **(m.get("render") or {})))
    script = os.path.join(tmp, "graph.txt")
    open(script, "w", encoding="utf-8").write(graph)
    part = out + ".part.mp4"
    cmd = (
        ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats"]
        + inputs
        + ["-filter_complex_script", script, "-map", "[vout]", "-map", "[aout]"]
        + ["-r", str(fps), "-t", "%.3f" % total]
        + _encode.video_args(rcfg)
        + _encode.audio_args(rcfg, rate=48000)
        + ["-movflags", "+faststart", "-y", part]
    )
    print(
        "  rendering %s  (%.1fs, %d stills, %d missing, %s)"
        % (out, total, n, len(missing), _encode.describe(rcfg))
    )
    subprocess.run(cmd, check=True)
    got = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", part],
            capture_output=True,
            text=True,
        ).stdout
    )
    if abs(got - total) > 0.25:
        sys.exit("rendered %.2fs, planned %.2fs: refusing to keep it" % (got, total))
    os.replace(part, out)
    json.dump(
        {"tts": tts, "total_s": total, "scenes": rows, "missing": missing},
        open(out + ".timeline.json", "w", encoding="utf-8"),
        indent=1,
    )
    if missing:
        print("  still to make: %s" % ", ".join(missing))
    _project.record(
        _project.project_id(m, manifest_path),
        "render",
        out=out,
        script=__file__,
        argv=sys.argv[1:],
        kind="still-film",
        manifest=manifest_path,
        burned={"pictures": "scenes[].file / images/<id>", "voice": "voice", "music": "music"},
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--plan", action="store_true", help="timings, words a minute, what is missing")
    ap.add_argument("--prompts", action="store_true", help="print each picture's full prompt")
    ap.add_argument("--voice", action="store_true", help="voice the lines that have no take yet")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--tts", choices=["gemini", "edge"], help="override voice.tts")
    ap.add_argument("--only", help="comma-separated scene ids")
    ap.add_argument("--out", help="output mp4 (default outputs/<project>.mp4)")
    a = ap.parse_args()
    m = load(a.manifest)
    tts = a.tts or (m.get("voice") or {}).get("tts", "gemini")
    only = set(a.only.split(",")) if a.only else None
    if a.prompts:
        cast = m.get("cast") or {}
        for s in m["scenes"]:
            who = [v for k, v in cast.items() if k in s["image"]]
            print(
                "=== %s\n%s\n%s%s\n"
                % (s["id"], m.get("style", ""), "\n".join(who) + "\n" if who else "", s["image"])
            )
    if a.voice:
        voice(m, tts, only)
    if a.plan or a.voice:
        rows, total = timeline(m, tts)
        words = sum(len(s["line"].split()) for s in m["scenes"])
        spoken = sum(r["voice"] for r in rows)
        holds = sorted(r["hold"] for r in rows)
        for s, r in zip(m["scenes"], rows):
            voiced = "v" if os.path.exists(vo_path(m, s, tts)) else "-"
            pic = "p" if picture(m, s) else "-"
            print(
                "  %s %s%s  %6.2f  hold %.2f  %s"
                % (s["id"], voiced, pic, r["start"], r["hold"], s["line"][:58])
            )
        print(
            "  total %.1fs  %d stills  hold median %.2fs (min %.2f, max %.2f)  %.0f wpm spoken"
            % (total, len(rows), holds[len(holds) // 2], holds[0], holds[-1], words / spoken * 60)
        )
    if a.render:
        pid = _project.project_id(m, a.manifest)
        out = a.out or pdir(m, "outputs", "%s.mp4" % pid)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        render(m, tts, out, a.manifest)


if __name__ == "__main__":
    main()
