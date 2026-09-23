#!/usr/bin/env python
"""Download audio and transcribe it, for a list of YouTube videos.

The front half of the chapter workflow: given video ids, leave a
`transcripts/<id>.words.json` for each one so chapters can be written from what
is actually said. Both steps skip work that already exists, so rerunning after
a failure costs nothing for the videos that succeeded.

Fetching is deliberately serial with a pause between videos. Hammering YouTube
in parallel trips its "confirm you're not a bot" check, after which every
request fails -- and the audit script that shares this machine then cannot read
anything either.

Invoke as:
  python scripts/yt-fetch-transcripts.py --ids abc123 def456
  python scripts/yt-fetch-transcripts.py --from-audit temp/chapters-audit.json
"""

import sys
import os
import json
import time
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ROOT = _env.ROOT
AUDIO = os.path.join(ROOT, "audio")
TRANSCRIPTS = os.path.join(ROOT, "transcripts")


def audio_path(vid):
    return os.path.join(AUDIO, f"{vid}.m4a")


def words_path(vid):
    return os.path.join(TRANSCRIPTS, f"{vid}.words.json")


def download(vid, pause):
    out = audio_path(vid)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print("  audio cached")
        return True
    r = subprocess.run(
        _env.PY
        + [
            "-m",
            "yt_dlp",
            "-f",
            "bestaudio[ext=m4a]/bestaudio",
            "-o",
            os.path.join(AUDIO, "%(id)s.%(ext)s"),
            "--",
            vid,
        ],
        env=_env.ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    time.sleep(pause)
    if r.returncode != 0 or not os.path.exists(out):
        tail = [l for l in (r.stderr or "").splitlines() if l.startswith("ERROR")]
        print(f"  DOWNLOAD FAILED: {tail[-1][:150] if tail else 'unknown'}")
        return False
    print(f"  audio {os.path.getsize(out) / 1e6:.1f} MB")
    return True


def transcribe(vid, language):
    out = words_path(vid)
    if os.path.exists(out):
        n = len(json.load(open(out, encoding="utf-8"))["words"])
        print(f"  transcript cached ({n} words)")
        return True
    cmd = _env.PY + [
        os.path.join(ROOT, "scripts", "transcribe-words.py"),
        audio_path(vid),
        "--out",
        out,
    ]
    if language:
        cmd += ["--language", language]
    r = subprocess.run(cmd, env=_env.ENV)
    if r.returncode != 0 or not os.path.exists(out):
        print("  TRANSCRIBE FAILED")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument(
        "--from-audit", help="JSON from yt-audit-chapters.py; takes every NONE/AUTO video"
    )
    ap.add_argument(
        "--min-duration", type=int, default=120, help="skip videos shorter than this many seconds"
    )
    ap.add_argument("--language", default="en", help="'' to autodetect")
    ap.add_argument(
        "--pause",
        type=float,
        default=3.0,
        help="seconds between downloads; lower trips the bot check",
    )
    args = ap.parse_args()

    ids = list(args.ids)
    if args.from_audit:
        rows = json.load(open(args.from_audit, encoding="utf-8"))
        ids += [
            r["id"]
            for r in rows
            if r["verdict"] in ("NONE", "AUTO") and r["duration_s"] >= args.min_duration
        ]
    if not ids:
        sys.exit("nothing to do: pass --ids or --from-audit")

    os.makedirs(AUDIO, exist_ok=True)
    os.makedirs(TRANSCRIPTS, exist_ok=True)

    ok, failed = [], []
    for i, vid in enumerate(dict.fromkeys(ids), 1):
        print(f"[{i}/{len(ids)}] {vid}")
        if download(vid, args.pause) and transcribe(vid, args.language):
            ok.append(vid)
        else:
            failed.append(vid)

    print(f"\n{len(ok)} transcribed, {len(failed)} failed")
    if failed:
        print("failed: " + " ".join(failed))
        print("rerun the same command; finished videos are skipped")
        sys.exit(1)


if __name__ == "__main__":
    main()
