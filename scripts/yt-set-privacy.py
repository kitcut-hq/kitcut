#!/usr/bin/env python
"""Set a YouTube video's privacy: public, unlisted or private.

Uploads go up unlisted (yt-upload.py), the end you can widen later; this is the
widening, once the owner approves a video. `videos.update` replaces the WHOLE
status part, so every writable status field (the disclosure flag, license,
embeddable, public stats, made-for-kids) is sent back exactly as it was
fetched, and only the privacy changes. The update is read back and must say
what was asked. A scheduled `publishAt` is dropped when going public (YouTube
refuses one on a public video).

Invoke as:
  python scripts/yt-set-privacy.py --channel @kitcut-hq --video mP-0U6xBTs4 --privacy public --dry-run
  python scripts/yt-set-privacy.py --channel @kitcut-hq --video mP-0U6xBTs4 --privacy public
"""

import sys
import os
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import

_yt = import_module("yt-set-chapters")
_disclosure = import_module("yt-set-disclosure")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channel", required=True, help="@handle the token MUST point at")
    ap.add_argument("--video", required=True, action="append", help="a video id (repeatable)")
    ap.add_argument("--privacy", required=True, choices=("public", "unlisted", "private"))
    ap.add_argument("--dry-run", action="store_true", help="print what would change")
    args = ap.parse_args()

    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=_yt.credentials(args.channel), cache_discovery=False)
    items = yt.videos().list(part="status,snippet", id=",".join(args.video)).execute()["items"]
    missing = set(args.video) - {v["id"] for v in items}
    if missing:
        sys.exit("not on this channel's grant: %s" % ", ".join(sorted(missing)))
    for v in items:
        st, title = v["status"], v["snippet"]["title"][:60]
        if st["privacyStatus"] == args.privacy:
            print(f"  {v['id']}  already {args.privacy}  {title}")
            continue
        body = {k: st[k] for k in _disclosure.WRITABLE if k in st}
        if "selfDeclaredMadeForKids" not in body and "madeForKids" in st:
            body["selfDeclaredMadeForKids"] = st["madeForKids"]
        body["privacyStatus"] = args.privacy
        if args.privacy == "public":
            body.pop("publishAt", None)
        print(f"  {v['id']}  {st['privacyStatus']} -> {args.privacy}  {title}")
        if args.dry_run:
            continue
        got = yt.videos().update(part="status", body={"id": v["id"], "status": body}).execute()
        if got["status"]["privacyStatus"] != args.privacy:
            sys.exit(f"{v['id']}: came back {got['status']['privacyStatus']}, not {args.privacy}")
        print(f"    ok: https://youtu.be/{v['id']}")


if __name__ == "__main__":
    main()
