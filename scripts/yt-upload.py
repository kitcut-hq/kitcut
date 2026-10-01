#!/usr/bin/env python
"""Upload a rendered video to YouTube, and prove where it landed.

Reuses the OAuth grant yt-set-chapters.py already established (.env refresh
token first, .yt-oauth/token.json second). The youtube.force-ssl scope covers
videos.insert, so no second consent is needed.

Two things this refuses to do, both learned the hard way on this account:

  * Upload to a channel you did not name. A Google login can own several
    channels and the grant silently picks one; --channel asserts the handle or
    title of the channel the token actually points at before a byte is sent.
  * Report success without checking. After the insert it re-fetches the video
    and asserts the id, the title and the privacy status came back as asked --
    an upload that lands public when you asked for unlisted is not a small
    mistake, and the API will not tell you.

Defaults to unlisted: the safe end of the scale, and the one you can widen
later without having shown anything to anyone. --publish-at schedules it: the
video goes up private and YouTube makes it public at that time (the API takes
a schedule only on a private video).

Invoke as:
  python scripts/yt-upload.py <file> --title "..." --channel @handle --dry-run
  python scripts/yt-upload.py <file> --title "..." --channel @handle
  python scripts/yt-upload.py <file> --title "..." --channel @handle --publish-at 2026-10-02T15:45
"""

import sys
import os
import json
import time
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402
from importlib import import_module  # noqa: E402

_yt = import_module("yt-set-chapters")

PRIVACY = ("private", "unlisted", "public")
# 8 MiB chunks: big enough that a 250 MB file is not 200 round trips, small
# enough that a dropped connection does not cost the whole upload.
CHUNK = 8 * 1024 * 1024


def service(creds):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def which_channel(yt):
    r = yt.channels().list(part="snippet", mine=True).execute()
    items = r.get("items") or []
    if not items:
        sys.exit("this grant owns no channel")
    sn = items[0]["snippet"]
    return (items[0]["id"], sn.get("title", ""), (sn.get("customUrl") or "").lstrip("@").lower())


def check_channel(yt, want):
    cid, title, handle = which_channel(yt)
    print("  channel: %s  (@%s, %s)" % (title, handle or "no handle", cid))
    if want:
        w = want.lstrip("@").lower()
        if w not in (handle, title.lower()):
            sys.exit(
                "token points at '%s' (@%s), not %r -- refusing to upload.\n"
                "Re-grant just this channel: delete %s (if present), then rerun\n"
                "with --reauth --channel %s. At Google's chooser pick the BRAND\n"
                "account, not the personal one -- and note the chooser lists the\n"
                "BRAND ACCOUNT name, which a renamed channel no longer matches."
                % (title, handle, want, os.path.relpath(_yt.channel_token(want), _env.ROOT), want)
            )
    return cid


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--description-file")
    ap.add_argument("--tags", default="", help="comma separated")
    ap.add_argument("--privacy", default="unlisted", choices=PRIVACY)
    ap.add_argument("--category", default="28", help="28 = Science & Technology")
    ap.add_argument("--channel", help="handle or title the token MUST point at")
    ap.add_argument(
        "--reauth",
        action="store_true",
        help="force a new Google consent and file the grant under --channel; use when adding a channel this machine has never uploaded to",
    )
    ap.add_argument("--made-for-kids", action="store_true")
    ap.add_argument(
        "--publish-at",
        help="schedule it: an ISO time (2026-10-02T15:00:00Z) when YouTube makes it public; uploads as private until then",
    )
    ap.add_argument(
        "--thumbnail", help="a JPEG/PNG (1280x720, under 2 MB) set as the custom thumbnail"
    )
    ap.add_argument(
        "--publish-at",
        help="schedule: goes up private, public at this time (ISO; no offset = this machine's zone)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    publish_at = None
    if args.publish_at:
        when = datetime.datetime.fromisoformat(args.publish_at)
        if when.tzinfo is None:
            when = when.astimezone()
        when = when.astimezone(datetime.timezone.utc).replace(microsecond=0)
        if when <= datetime.datetime.now(datetime.timezone.utc):
            sys.exit("--publish-at %s is not in the future" % args.publish_at)
        if args.privacy != "private":
            print("  --publish-at: uploading private; YouTube publishes it at that time")
            args.privacy = "private"
        publish_at = when.strftime("%Y-%m-%dT%H:%M:%SZ")

    path = _env.resolve(args.file)
    if not os.path.exists(path):
        sys.exit("no such file: %s" % path)
    size = os.path.getsize(path)
    if size == 0:
        sys.exit("%s is empty" % path)

    desc = args.description
    if args.description_file:
        p = args.description_file
        p = _env.resolve(p)
        desc = open(p, encoding="utf-8").read()
    if len(desc) > 5000:
        sys.exit("description is %d chars; YouTube's limit is 5000" % len(desc))
    if len(args.title) > 100:
        sys.exit("title is %d chars; YouTube's limit is 100" % len(args.title))
    # YouTube rejects '<' and '>' anywhere in a title or description with a
    # bare "invalidDescription" -- and only once the upload is under way. An
    # arrow written "->" in acord-commercial's document map was enough.
    for field, text in (("title", args.title), ("description", desc)):
        bad = [i for i, ch in enumerate(text) if ch in "<>"]
        if bad:
            line = text.count("\n", 0, bad[0]) + 1
            sys.exit(
                "%s contains '<' or '>' (first on line %d) -- YouTube refuses both; "
                "use an arrow character or words" % (field, line)
            )

    publish_at = None
    if args.publish_at:
        from datetime import datetime, timezone

        try:
            when = datetime.fromisoformat(args.publish_at.replace("Z", "+00:00"))
        except ValueError:
            sys.exit("--publish-at: not an ISO time: %r" % args.publish_at)
        if when.tzinfo is None:
            sys.exit("--publish-at needs a time zone (Z or +hh:mm): %r" % args.publish_at)
        if when <= datetime.now(timezone.utc):
            sys.exit("--publish-at is in the past: %s" % args.publish_at)
        # YouTube schedules only private videos: one asked public would be refused
        args.privacy = "private"
        publish_at = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": args.title,
            "description": desc,
            "categoryId": args.category,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": bool(args.made_for_kids),
            **({"publishAt": publish_at} if publish_at else {}),
        },
    }

    print("%s  (%.1f MB)" % (os.path.relpath(path, _env.ROOT), size / 1e6))
    print("  title:   %s" % args.title)
    print("  privacy: %s" % args.privacy)
    if publish_at:
        print(
            "  publish: %s UTC (%s local)"
            % (publish_at, when.astimezone().strftime("%a %Y-%m-%d %H:%M"))
        )
    thumb = None
    if args.thumbnail:
        thumb = _env.resolve(args.thumbnail)
        if not os.path.exists(thumb):
            sys.exit("no such thumbnail: %s" % thumb)
        if os.path.getsize(thumb) > 2 * 1024 * 1024:
            sys.exit("thumbnail is over YouTube's 2 MB limit")
        print("  thumb:   %s" % os.path.relpath(thumb, _env.ROOT))

    # pass the channel so the grant filed under that handle is used --
    # one login can own several channels and each grant points at one.
    creds = _yt.credentials(args.channel, reauth=args.reauth)
    yt = service(creds)
    check_channel(yt, args.channel)

    if args.dry_run:
        print("\n  --dry-run: nothing uploaded")
        return

    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(path, chunksize=CHUNK, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    print("\n  uploading ...")
    t0, resp, tries = time.time(), None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
        except Exception as e:  # noqa: BLE001
            code = getattr(getattr(e, "resp", None), "status", None)
            if code is not None and 400 <= int(code) < 500:
                # A 4xx is YouTube refusing the request, not the network
                # dropping a chunk: the same bytes will be refused again, so
                # retrying only spends a minute before the same failure.
                sys.exit("YouTube refused the upload (%s): %s" % (code, e))
            tries += 1
            if tries > 5:
                raise
            wait = 2**tries
            print("    chunk failed (%s); retry %d in %ds" % (e, tries, wait))
            time.sleep(wait)
            continue
        tries = 0
        if status:
            done = status.progress()
            rate = done * size / max(1e-9, time.time() - t0) / 1e6
            print("    %5.1f%%  %.1f MB/s" % (done * 100, rate), flush=True)

    vid = resp["id"]
    url = "https://youtu.be/%s" % vid
    print("  uploaded in %.0fs -> %s" % (time.time() - t0, url))

    # Verify, do not assume. Processing is asynchronous but the snippet and
    # status are readable straight away.
    got = yt.videos().list(part="snippet,status", id=vid).execute()
    items = got.get("items") or []
    if not items:
        sys.exit("uploaded as %s but the video does not read back" % vid)
    sn, st = items[0]["snippet"], items[0]["status"]
    ok = True
    for label, want, have in (
        ("title", args.title, sn.get("title")),
        ("privacy", args.privacy, st.get("privacyStatus")),
    ) + (
        (("publish", publish_at, (st.get("publishAt") or "").replace(".000", "")),)
        if publish_at
        else ()
    ):
        mark = "ok" if want == have else "MISMATCH"
        if want != have:
            ok = False
        print("  %-8s %-8s asked %r, got %r" % (label, mark, want, have))
    if not ok:
        sys.exit("the video is up but not as asked -- fix it in Studio")

    if thumb:
        # A custom thumbnail is a separate call, and it can fail on its own --
        # an unverified channel is refused -- so the upload is not undone by it;
        # the failure is printed and the sidecar says the thumbnail is missing.
        from googleapiclient.http import MediaFileUpload as _M

        try:
            yt.thumbnails().set(
                videoId=vid,
                media_body=_M(
                    thumb, mimetype="image/png" if thumb.lower().endswith(".png") else "image/jpeg"
                ),
            ).execute()
            print("  thumbnail set")
        except Exception as e:  # noqa: BLE001
            print("  !! thumbnail NOT set (%s) -- upload it in Studio" % e)
            thumb = None

    side = os.path.splitext(path)[0] + ".youtube.json"
    with open(side, "w", encoding="utf-8") as f:
        json.dump(
            {
                "id": vid,
                "url": url,
                "title": args.title,
                "privacy": args.privacy,
                "publish_at": publish_at,
                "bytes": size,
                "thumbnail": thumb and _project.norm(thumb),
                "uploaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print("  %s" % os.path.relpath(side, _env.ROOT))

    pid, _doc = _project.find_by_output(path)
    if pid:
        _project.record(
            pid,
            "publish",
            out=path,
            script=__file__,
            argv=sys.argv[1:],
            published={
                "url": url,
                "privacy": args.privacy,
                "publish_at": publish_at,
                "sidecar": _project.norm(side),
            },
            note="uploaded %s" % args.title,
        )
    else:
        print(
            "  note: no project claims this render -- record the upload in "
            "its projects/<id>/project.json by hand"
        )
    print("\n%s" % url)


if __name__ == "__main__":
    main()
