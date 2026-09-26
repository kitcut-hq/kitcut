#!/usr/bin/env python
"""Score, sound design and mix for a sketch film -> a mastered soundtrack.

Reads `projects/<id>/sketch.json`: its `audio.score` (sampled-instrument score, see
_sketchaudio.py for the notation), `audio.sfx` (timed sound cues), the VO timeline written by
sketch-vo.py, and optional plane/object automation written by sketch-render.py --automation.
Renders music, SFX and voice, ducks the music under speech, mixes, and masters to EBU R128
(-14 LUFS, -1.5 dBTP by default) with a two-pass loudnorm.

Every stage is timed into the project's run log (run-log.py reads it), and the stage table is
printed at the end -- the answer to "how long does the audio for a film take".

Outputs, in projects/<id>/audio/:
    mix_pre.wav     the un-mastered mix          stem_music/sfx/vo.wav   (--stems)
    final.wav       mastered, 24-bit             final.mp3               for the HTML player

Manifest keys (audio block), all optional except score:
    score, sfx, automation ("temp/automation.json"), vo_timeline ("audio/vo/timeline.json")
    mix: {music_db: 6, sfx_db: 3, vo_db: -17, duck: .62, reverb_sec: 2.3, music_reverb: .9,
          sfx_reverb: .8, fade_out: .6}
    master: {lufs: -14, tp: -1.5}

Invoke as:
    python scripts/sketch-audio.py --manifest projects/<id>/sketch.json --plan
    python scripts/sketch-audio.py --manifest projects/<id>/sketch.json
    python scripts/sketch-audio.py --manifest projects/<id>/sketch.json --levels --stems
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _project  # noqa: E402
import _sketch  # noqa: E402
import _sketchaudio as A  # noqa: E402

SR = _sketch.SR


def load_json(m, key, default=None):
    p = m.get("audio", {}).get(key, default)
    if not p:
        return None, None
    path = _sketch.rel(m, p)
    if not os.path.exists(path):
        return None, path
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--plan",
        action="store_true",
        help="validate score/cues, list what would be fetched and rendered; render nothing",
    )
    ap.add_argument(
        "--levels",
        action="store_true",
        help="print the per-2s balance table of music / sfx / voice",
    )
    ap.add_argument(
        "--stems", action="store_true", help="also write the music, sfx and voice stems"
    )
    ap.add_argument("--no-vo", action="store_true", help="mix without the voice (music + sfx only)")
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    dur = float(m["duration"])
    au = m.get("audio", {})
    mix = {
        "music_db": 6.0,
        "sfx_db": 3.0,
        "vo_db": -17.0,
        "duck": 0.62,
        "reverb_sec": 2.3,
        "music_reverb": 0.9,
        "sfx_reverb": 0.8,
        "fade_out": 0.6,
        **au.get("mix", {}),
    }
    master = {"lufs": -14.0, "tp": -1.5, **au.get("master", {})}

    score, score_p = load_json(m, "score")
    if score is None:
        sys.exit("no score: set audio.score in %s (missing: %s)" % (m["_path"], score_p))
    cues, _ = load_json(m, "sfx")
    cues = cues or []
    autom, _ = load_json(m, "automation", "temp/automation.json")
    tl_path = _sketch.rel(m, au.get("vo_timeline", "audio/vo/timeline.json"))
    timeline = None
    if not args.no_vo and os.path.exists(tl_path):
        with open(tl_path, encoding="utf-8") as f:
            timeline = json.load(f)

    events = A.score_events(score)
    need = A.needed_samples(events)
    for c in cues:
        if c["fx"] == "sample":
            for nt in c.get("notes") or [c["note"]]:
                need.add((c["inst"], A.M(nt)))
        elif c["fx"] not in A.FX and c["fx"] not in ("air",):
            sys.exit(
                "sfx cue at %.2fs: unknown fx %r (have: %s)"
                % (c.get("t", -1), c["fx"], ", ".join(sorted(A.FX)))
            )
    missing = [p for p in need if not os.path.exists(A.sample_path(*p))]
    last = max((e[2] for e in events), default=0) * 60.0 / score.get("bpm", 120)

    print("%s  (%.1fs @ %s bpm)" % (m["_id"], dur, score.get("bpm", 120)))
    print(
        "  score:  %d note events, %d instruments, last note at %.1fs"
        % (len(events), len({e[0] for e in events}), last)
    )
    print(
        "  sfx:    %d cues (%s)" % (len(cues), ", ".join(sorted({c["fx"] for c in cues})) or "none")
    )
    print(
        "  voice:  %s"
        % (
            "%d lines from %s" % (len(timeline["lines"]), os.path.relpath(tl_path, _env.ROOT))
            if timeline
            else "none"
        )
    )
    print("  samples: %d needed, %d to fetch into %s" % (len(need), len(missing), A.SOUNDFONT))
    print("  master: %s LUFS, %s dBTP" % (master["lufs"], master["tp"]))
    if args.plan:
        print("\n  --plan: nothing rendered")
        return

    stages = ["samples", "music", "sfx", "voice", "mix", "master"]
    with _sketch.Stages(m, "sketch-audio", stages, argv=sys.argv[1:]) as st:
        with st("samples"):
            n_miss, got = A.fetch_samples(need)
            print("  fetched %d of %d missing notes" % (got, n_miss))
        with st("music"):
            dry, mwet, _ = A.render_score(score, dur)
            ir = A.make_ir(mix["reverb_sec"])
            music = A.hp(dry + A.reverb(mwet, ir) * mix["music_reverb"], 35)
        with st("sfx"):
            sfx, swet = A.render_sfx(cues, dur, autom)
            sfx = sfx + A.reverb(swet, ir) * mix["sfx_reverb"]
        with st("voice"):
            if timeline:
                vo = A.build_vo(timeline, dur, mix["vo_db"], base=m["_dir"])
                vo_st = np.stack([vo, vo]) * 0.98 + A.reverb(np.stack([vo, vo]) * 0.05, ir) * 0.6
                gain = A.duck_gain(vo, mix["duck"])
            else:
                vo_st, gain = np.zeros((2, int(dur * SR))), np.ones(int(dur * SR))
        with st("mix"):
            Mg, Sg = 10 ** (mix["music_db"] / 20), 10 ** (mix["sfx_db"] / 20)
            out = music * gain * Mg + sfx * Sg + vo_st
            k = int(mix["fade_out"] * SR)
            if k:
                out[:, -k:] *= np.linspace(1, 0, k) ** 1.5
            out = out / (np.abs(out).max() + 1e-9) * 0.89
            pre = os.path.join(m["_audio"], "mix_pre.wav")
            _sketch.write_wav(pre, out)
            if args.stems:
                for name, x in (("music", music * Mg), ("sfx", sfx * Sg), ("vo", vo_st)):
                    _sketch.write_wav(os.path.join(m["_audio"], "stem_%s.wav" % name), x * 0.5)
            if args.levels:
                names, rows = A.levels_table(
                    {
                        "music": music * Mg,
                        "ducked": music * gain * Mg,
                        "sfx": sfx * Sg,
                        "voice": vo_st,
                    }
                )
                print("\n  %5s " % "sec" + " ".join("%8s" % n for n in names))
                for r in rows:
                    print("  %5.0f " % r[0] + " ".join("%8.1f" % v for v in r[1:]))
        with st("master"):
            final = os.path.join(m["_audio"], "final.wav")
            A.loudnorm(pre, final, master["lufs"], master["tp"])
            mp3 = os.path.join(m["_audio"], "final.mp3")
            import subprocess

            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    final,
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    mp3,
                ],
                check=True,
            )
            lufs, peak = A.measure(final)
            print("  final: %s LUFS integrated, %s dBTP" % (lufs, peak))

    _project.record(
        m["_id"],
        "sketch soundtrack mastered (%s LUFS)" % lufs,
        out=final,
        script=__file__,
        argv=sys.argv[1:],
        kind="audio",
        manifest=m["_path"],
        sidecars={"mp3": mp3, "mix_pre": pre},
    )


if __name__ == "__main__":
    main()
