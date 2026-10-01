#!/usr/bin/env python
"""Change an already-uploaded YouTube video: its thumbnail, description,
title or privacy -- and prove each change came back as asked.

`yt-upload.py` sets all of these once, at upload. After that the only way to
change them was YouTube Studio, which leaves no record here and no check that
the right video on the right channel was touched. This is the same guard rail
as the upload: the token must point at `--channel` before anything is sent,
'<' and '>' are refused up front (YouTube rejects both in a title or
description, and says only "invalidDescription"), and every changed field is
read back afterwards.

A snippet update REPLACES the snippet, so the fields not being changed are
read from the live video first and sent back as they are -- a bare title +
description update would otherwise wipe the tags and the category.

Invoke as:
  python scripts/yt-update.py <id|url> --channel @handle --thumbnail t.png --dry-run
  python scripts/yt-update.py <id|url> --channel @handle --thumbnail t.png --description-file d.txt
  python scripts/yt-update.py <id|url> --channel @handle --privacy public --project <id>
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402
from importlib import import_module  # noqa: E402

_yt = import_module("yt-set-chapters")
_up = import_module("yt-upload")


def bad_chars(field, text):
    i = next((k for k, ch in enumerate(text) if ch in "<>"), None)
    if i is not None:
        sys.exit(
            "%s contains '<' or '>' (line %d) -- YouTube refuses both"
            % (field, text.count("\n", 0, i) + 1)
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", help="video id or URL")
    ap.add_argument("--channel", required=True, help="handle or title the token MUST point at")
    ap.add_argument("--title")
    ap.add_argument("--description-file")
    ap.add_argument("--privacy", choices=_up.PRIVACY)
    ap.add_argument("--thumbnail", help="a JPEG/PNG, 1280x720, under 2 MB")
    ap.add_argument("--project", help="project id, to record the change")
    ap.add_argument("--dry-run", action="store_true", help="show what would change; send nothing")
    a = ap.parse_args()

    vid = _yt.video_id(a.video)
    desc = None
    if a.description_file:
        desc = open(_env.resolve(a.description_file), encoding="utf-8").read()
        if len(desc) > 5000:
            sys.exit("description is %d chars; YouTube's limit is 5000" % len(desc))
        bad_chars("description", desc)
    if a.title:
        if len(a.title) > 100:
            sys.exit("title is %d chars; YouTube's limit is 100" % len(a.title))
        bad_chars("title", a.title)
    thumb = None
    if a.thumbnail:
        thumb = _env.resolve(a.thumbnail)
        if not os.path.exists(thumb):
            sys.exit("no such thumbnail: %s" % thumb)
        if os.path.getsize(thumb) > 2 * 1024 * 1024:
            sys.exit("thumbnail is over YouTube's 2 MB limit")
    if not (desc is not None or a.title or a.privacy or thumb):
        sys.exit("nothing to change: give --title, --description-file, --privacy or --thumbnail")

    yt = _up.service(_yt.credentials(a.channel))
    _up.check_channel(yt, a.channel)
    items = yt.videos().list(part="snippet,status", id=vid).execute().get("items") or []
    if not items:
        sys.exit("video %s is not visible to this channel's token" % vid)
    sn, st = items[0]["snippet"], items[0]["status"]
    print("  video:   %s  %r (%s)" % (vid, sn.get("title"), st.get("privacyStatus")))

    changes = []
    if a.title and a.title != sn.get("title"):
        changes.append(("title", sn.get("title"), a.title))
    if desc is not None and desc != sn.get("description", ""):
        changes.append(
            ("description", "%d chars" % len(sn.get("description", "")), "%d chars" % len(desc))
        )
    if a.privacy and a.privacy != st.get("privacyStatus"):
        changes.append(("privacy", st.get("privacyStatus"), a.privacy))
    if thumb:
        changes.append(("thumbnail", "(current)", os.path.relpath(thumb, _env.ROOT)))
    for f, old, new in changes:
        print("  %-11s %s  ->  %s" % (f, old, new))
    if not changes:
        print("  already as asked -- nothing to send")
        return
    if a.dry_run:
        print("\n  --dry-run: nothing sent")
        return

    if a.title or desc is not None:
        snippet = {
            "title": a.title or sn["title"],
            "description": desc if desc is not None else sn.get("description", ""),
            "categoryId": sn["categoryId"],
        }
        for keep in ("tags", "defaultLanguage", "defaultAudioLanguage"):
            if sn.get(keep):
                snippet[keep] = sn[keep]
        yt.videos().update(part="snippet", body={"id": vid, "snippet": snippet}).execute()
    if a.privacy:
        status = {"privacyStatus": a.privacy}
        if "selfDeclaredMadeForKids" in st:
            status["selfDeclaredMadeForKids"] = st["selfDeclaredMadeForKids"]
        yt.videos().update(part="status", body={"id": vid, "status": status}).execute()
    if thumb:
        from googleapiclient.http import MediaFileUpload

        mime = "image/png" if thumb.lower().endswith(".png") else "image/jpeg"
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb, mimetype=mime)).execute()
        print("  thumbnail set")

    back = yt.videos().list(part="snippet,status", id=vid).execute()["items"][0]
    ok = True
    for f, want, have in (
        ("title", a.title, back["snippet"].get("title")),
        ("description", desc, back["snippet"].get("description")),
        ("privacy", a.privacy, back["status"].get("privacyStatus")),
    ):
        if want is None:
            continue
        good = want == have
        ok = ok and good
        print("  %-11s %s" % (f, "ok" if good else "MISMATCH (asked %r, got %r)" % (want, have)))
    if a.project:
        _project.record(
            a.project,
            "youtube-update",
            script=__file__,
            argv=sys.argv[1:],
            note="https://youtu.be/%s: %s" % (vid, ", ".join(f for f, _, _ in changes)),
        )
    if not ok:
        sys.exit("the video did not come back as asked -- check it in Studio")


if __name__ == "__main__":
    main()
