#!/usr/bin/env python
"""Set the "altered or synthetic content" disclosure on YouTube videos.

This is the Studio checkbox that shows up on the watch page as "How this was
made / Made with AI". The Data API exposes it as `status.containsSyntheticMedia`.
The API returns the flag only when it is "yes". "No" and never-set both read
back as `-` (measured: a video set to "no" through this script, read straight
after, carries no key at all), so a re-run of --set no re-spends its quota.

`videos.update` replaces the WHOLE status part. Every writable status field
(privacy, publishAt, license, embeddable, public stats, made-for-kids) is sent
back exactly as it was fetched, so the only thing that changes is the flag.

The label that YouTube applies ITSELF (from C2PA content credentials or its own
detection) is not this flag, and setting "no" does not clear it. Measured
2026-09-30: every upload on both channels already read "not yes", and
watMf06668M kept the label after an explicit "no". `--labels` reads each
public watch page to show which videos carry the label, whatever put it there.

Policy note: YouTube requires "yes" for realistic content that could mislead
viewers, such as a real person's cloned voice or a photo of a real person made
to speak. Animation and a generic narrator do not need it.

Invoke as:
  python scripts/yt-set-disclosure.py --channel @instafill_ai --list
  python scripts/yt-set-disclosure.py --channel @kitcut-hq --list --labels
  python scripts/yt-set-disclosure.py --channel @kitcut-hq --set no --dry-run
  python scripts/yt-set-disclosure.py --channel @kitcut-hq --set no
  python scripts/yt-set-disclosure.py --channel @kitcut-hq --set yes --video ktdGEptQ99Y
"""

import sys
import os
import argparse
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import

_yt = import_module("yt-set-chapters")
_audit = import_module("yt-audit-chapters")

# Status fields videos.update accepts. Anything omitted is reset to its
# default, so each one is copied back from the read.
WRITABLE = (
    "privacyStatus",
    "publishAt",
    "license",
    "embeddable",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)


def flag(v):
    return {True: "yes", False: "no"}.get(v.get("containsSyntheticMedia"), "-")


def shows_label(vid):
    """Whether the public watch page carries the "How this was made" label.

    The API cannot say (a label YouTube applied itself is not the flag), so
    this reads the page anonymously. A private video reads as False.
    """
    import time
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"https://www.youtube.com/watch?v={vid}",
        headers={"Accept-Language": "en-US", "User-Agent": "Mozilla/5.0"},
    )
    time.sleep(2)  # back to back, YouTube answers 429 after ~130 pages
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return "howThisWasMadeSectionViewModel" in r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code != 429:
            raise
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channel", required=True, help="@handle the token MUST point at")
    ap.add_argument(
        "--video", action="append", help="limit to this id (repeatable); default: every upload"
    )
    ap.add_argument("--set", choices=("yes", "no"), help="the value to write")
    ap.add_argument("--list", action="store_true", help="print the current flag and change nothing")
    ap.add_argument(
        "--labels", action="store_true", help="with --list: read each watch page for the label"
    )
    ap.add_argument("--dry-run", action="store_true", help="print what --set would change")
    args = ap.parse_args()
    if not args.list and not args.set:
        ap.error("pass --list, or --set yes|no")

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    yt = build("youtube", "v3", credentials=_yt.credentials(args.channel), cache_discovery=False)
    ids = args.video or _audit.all_video_ids(yt, _audit.uploads_playlist(yt, args.channel))

    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="status,snippet", id=",".join(ids[i : i + 50])).execute()
        videos += r["items"]

    want = {"yes": True, "no": False}.get(args.set)
    changed = kept = 0
    for v in videos:
        st, title = v["status"], v["snippet"]["title"][:60]
        before = flag(st)
        if args.list or st.get("containsSyntheticMedia") is want:
            label = ""
            if args.labels:
                seen = st["privacyStatus"] != "private" and shows_label(v["id"])
                label = {True: "LABEL ", None: "429?  "}.get(seen, "      ")
            print(f"  {v['id']}  {before:>3}  {st['privacyStatus']:<8}  {label}{title}")
            kept += not args.list
            continue
        body = {k: st[k] for k in WRITABLE if k in st}
        if "selfDeclaredMadeForKids" not in body and "madeForKids" in st:
            body["selfDeclaredMadeForKids"] = st["madeForKids"]
        body["containsSyntheticMedia"] = want
        print(f"  {v['id']}  {before:>3} -> {args.set:<3}  {st['privacyStatus']:<8}  {title}")
        if not args.dry_run:
            try:
                req = yt.videos().update(part="status", body={"id": v["id"], "status": body})
                got = req.execute()["status"]
            except HttpError as e:
                if "quotaExceeded" not in str(e):
                    raise
                # 50 units a video against a 10,000/day default: ~190 a day.
                # Re-running tomorrow skips what is already set.
                sys.exit(f"\nquota spent after {changed} changes; run again after midnight Pacific")
            if (
                got.get("containsSyntheticMedia") is not want
                or got["privacyStatus"] != st["privacyStatus"]
            ):
                sys.exit(f"{v['id']}: the update came back as {got}, not as asked")
        changed += 1

    if not args.list:
        verb = "would change" if args.dry_run else "changed"
        print(f"\n{args.channel}: {verb} {changed}, already {args.set} {kept}, of {len(videos)}")


if __name__ == "__main__":
    main()
