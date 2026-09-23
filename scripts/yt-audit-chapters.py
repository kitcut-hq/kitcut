#!/usr/bin/env python
"""Report which of a channel's videos actually show chapter markers.

The authority is the watch page, not a rule about description formatting. An
earlier version of this script inferred the verdict from the description alone
-- "first mark at 0:00, three or more, ten seconds apart" -- and was wrong on
11 of 46 videos, calling nine of them broken while every one rendered fine. So
this reads what YouTube really renders (yt-dlp's `chapters` field) and uses the
description only to say where those chapters came from.

Verdicts:

  NONE   no chapters on the watch page -- these are the ones to write
  AUTO   YouTube generated them itself; the description has no timestamps, so
         nobody chose these and an edit cannot steer them
  OK     rendering, and traceable to timestamps in the description
  SHORT  too brief to carry chapters at all

Reads only. The API side costs 1 unit per 50 videos; the yt-dlp side is one
page fetch per video, which is the slow part -- budget a couple of minutes for
a channel this size.

Go easy on the fetching. Auditing 46 videos a few times in quick succession is
enough to trip YouTube's "confirm you're not a bot" check, after which every
video comes back unreadable. That is reported as RETRY, never as "no chapters",
because the whole point of this script is that a failed read must not be
mistaken for an empty one. If you see RETRY, wait a few minutes and rerun with
--jobs 1, or supply cookies.

Invoke as:
  python scripts/yt-audit-chapters.py --channel @instafill_ai
  python scripts/yt-audit-chapters.py --channel @instafill_ai --none-only
  python scripts/yt-audit-chapters.py --channel @instafill_ai --json out.json
"""

import sys
import os
import re
import json
import argparse
import importlib.util
import subprocess
import ast
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _ytchapters as ch  # noqa: E402

# Shortest video that could hold MIN_CHAPTERS marks at MIN_GAP_S spacing.
SHORT_S = ch.MIN_GAP_S * (ch.MIN_CHAPTERS - 1)


def _setter():
    """yt-set-chapters.py, imported despite the hyphen, for its auth."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yt-set-chapters.py")
    spec = importlib.util.spec_from_file_location("yt_set_chapters", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def iso8601_seconds(dur):
    """PT6M34S -> 394. contentDetails.duration is always this shape."""
    m = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur)
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def uploads_playlist(yt, channel):
    if channel.startswith("@"):
        r = yt.channels().list(part="contentDetails", forHandle=channel).execute()
    elif channel.startswith("UC"):
        r = yt.channels().list(part="contentDetails", id=channel).execute()
    else:
        sys.exit(f"pass a @handle or a UC... channel id, not {channel!r}")
    if not r.get("items"):
        sys.exit(f"no channel matched {channel!r}")
    return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def all_video_ids(yt, playlist):
    ids, page = [], None
    while True:
        r = (
            yt.playlistItems()
            .list(part="contentDetails", playlistId=playlist, maxResults=50, pageToken=page)
            .execute()
        )
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        page = r.get("nextPageToken")
        if not page:
            return ids


def _reason(stderr):
    """Turn yt-dlp's stderr into the one line worth showing."""
    s = stderr or ""
    if "live event" in s or "premieres in" in s.lower():
        return "live", "scheduled live event; nothing published yet"
    if "not a bot" in s or "429" in s:
        return "throttled", (
            "YouTube is rate-limiting this machine; rerun with --jobs 1, or pass cookies"
        )
    for line in reversed(s.splitlines()):
        if line.startswith("ERROR:"):
            return "error", line[6:].strip()[:140]
    return "error", "no usable answer from yt-dlp"


def rendered_chapters(vid, attempts=2):
    """(chapters, reason) -- chapters is None when the page could not be read.

    Retried because a single fetch is not reliable: one video returned 0
    chapters on the first call and 10 on the next. A transient failure looks
    exactly like "no chapters", which would send someone off to write chapters
    a video already has -- so a zero has to survive twice before it is
    believed, and a persistent failure returns None rather than 0.
    """
    seen, last_err = [], ""
    for _ in range(attempts):
        p = subprocess.run(
            [_env.PY[0], "-m", "yt_dlp", "--skip-download", "--print", "%(chapters)s", "--", vid],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_env.ENV,
        )
        out = (p.stdout or "").strip()
        if p.returncode != 0:
            last_err = p.stderr  # network/extractor failure, not data
            continue
        # --print renders an absent field as the literal "NA". That is the
        # normal answer for a video with no chapters, NOT a parse failure --
        # mistaking it for one turned all 20 chapterless videos into errors.
        if out in ("NA", "None", ""):
            seen.append([])
            continue
        try:
            seen.append(ast.literal_eval(out) or [])
        except (ValueError, SyntaxError):
            continue
        if seen[-1]:
            return seen[-1], ""  # a non-empty answer is trustworthy
    if not seen:
        return None, _reason(last_err)  # never got a usable answer
    return max(seen, key=len), ""


def classify(chapters, description, duration_s, reason=("", "")):
    """(verdict, note) given what renders and what the description says."""
    block = ch.block_text(description)
    if chapters is None:
        kind, msg = reason if isinstance(reason, tuple) else ("error", reason)
        return {"live": "LIVE", "throttled": "RETRY"}.get(kind, "ERROR"), msg
    if not chapters:
        if duration_s < SHORT_S:
            return "SHORT", f"{ch.fmt_ts(duration_s)} long"
        return (
            "NONE",
            "no chapters in the description either"
            if not block
            else "description HAS timestamps but none render -- investigate",
        )
    if block is None:
        return "AUTO", "YouTube's own; no timestamps in the description"
    return "OK", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channel", required=True, help="@handle or UC... id")
    ap.add_argument("--none-only", action="store_true", help="list only videos with no chapters")
    ap.add_argument("--json", help="also write the full result here")
    ap.add_argument(
        "--jobs",
        type=int,
        default=3,
        help="parallel watch-page reads; raising this is the fastest way to get rate-limited",
    )
    args = ap.parse_args()

    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=_setter().credentials())

    ids = all_video_ids(yt, uploads_playlist(yt, args.channel))
    meta = {}
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,contentDetails", id=",".join(ids[i : i + 50])).execute()
        for it in r["items"]:
            meta[it["id"]] = (
                it["snippet"]["title"],
                it["snippet"]["description"],
                iso8601_seconds(it["contentDetails"]["duration"]),
            )

    print(f"{len(ids)} videos on {args.channel}; reading each watch page ...\n")
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        chapters = dict(zip(ids, ex.map(rendered_chapters, ids)))

    rows = []
    for vid in ids:
        title, desc, dur = meta[vid]
        got, reason = chapters[vid]
        verdict, note = classify(got, desc, dur, reason)
        rows.append(
            {
                "id": vid,
                "title": title,
                "duration_s": dur,
                "verdict": verdict,
                "note": note,
                "rendered": len(got or []),
                "from_description": ch.block_text(desc) is not None,
            }
        )

    order = {"RETRY": 0, "ERROR": 1, "NONE": 2, "AUTO": 3, "OK": 4, "SHORT": 5, "LIVE": 6}
    rows.sort(key=lambda r: (order[r["verdict"]], -r["duration_s"]))

    for r in rows:
        if args.none_only and r["verdict"] not in ("NONE", "ERROR", "RETRY"):
            continue
        title = r["title"] if len(r["title"]) <= 60 else r["title"][:57] + "..."
        n = f"  ({r['rendered']} marks)" if r["rendered"] else ""
        print(f"{r['verdict']:<6} {ch.fmt_ts(r['duration_s']):>6}  {r['id']:<12}  {title}{n}")
        if r["note"]:
            print(f"{'':>15}{r['note']}")

    print()
    for v in ("RETRY", "ERROR", "NONE", "AUTO", "OK", "SHORT", "LIVE"):
        c = sum(1 for r in rows if r["verdict"] == v)
        if c:
            print(f"{v:<6} {c}")

    worth = [r for r in rows if r["verdict"] == "NONE"]
    if worth:
        total = sum(r["duration_s"] for r in worth)
        print(f"\n{len(worth)} videos need chapters ({ch.fmt_ts(total)} of footage to outline).")

    if args.json:
        json.dump(rows, open(args.json, "w", encoding="utf-8"), indent=2)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
