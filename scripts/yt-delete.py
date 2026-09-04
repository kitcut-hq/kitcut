#!/usr/bin/env python
"""Delete videos from YouTube, and prove whose channel they came off.

Reuses the OAuth grant yt-set-chapters.py already established (.env refresh
token first, .yt-oauth/token.json second) -- same as yt-upload.py.

Refuses to do to a channel what yt-upload.py already refuses to do: delete
from one you did not name. --channel asserts the handle or title the token
actually points at before anything is removed. Without --yes it only lists
what it would delete -- deletion has no undo, so the default is dry-run.

Invoke as:
  python scripts/yt-delete.py <video-id-or-url> [<video-id-or-url> ...] --channel @handle
  python scripts/yt-delete.py <video-id-or-url> ... --channel @handle --yes
"""

import sys
import os
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

_yt = import_module("yt-set-chapters")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("videos", nargs="+", help="video id or any YouTube URL form")
    ap.add_argument("--channel", required=True, help="handle or title the token MUST point at")
    ap.add_argument("--yes", action="store_true", help="actually delete; without this, list only")
    args = ap.parse_args()

    ids = [_yt.video_id(v) for v in args.videos]

    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=_yt.credentials())

    r = yt.channels().list(part="snippet", mine=True).execute()
    items = r.get("items") or []
    if not items:
        sys.exit("this grant owns no channel")
    sn = items[0]["snippet"]
    title = sn.get("title", "")
    handle = (sn.get("customUrl") or "").lstrip("@").lower()
    want = args.channel.lstrip("@").lower()
    if want not in (handle, title.lower()):
        sys.exit(
            f"token is for '{title}' (@{handle or 'no handle'}), not '{args.channel}' -- refusing"
        )
    print(f"  channel: {title}  (@{handle or 'no handle'})")

    r = yt.videos().list(part="snippet,status", id=",".join(ids)).execute()
    found = {v["id"]: v for v in r.get("items", [])}
    for vid in ids:
        v = found.get(vid)
        if not v:
            print(f"  {vid}  NOT FOUND (already gone, or not owned by this channel)")
            continue
        print(f"  {vid}  {v['snippet']['title']}  ({v['status']['privacyStatus']})")

    if not args.yes:
        print("\n  --yes not given: nothing deleted (dry run)")
        return

    for vid in ids:
        if vid not in found:
            continue
        yt.videos().delete(id=vid).execute()
        print(f"  deleted {vid}")


if __name__ == "__main__":
    main()
