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
later without having shown anything to anyone.

Invoke as:
  python scripts/yt-upload.py <file> --title "..." --channel @handle --dry-run
  python scripts/yt-upload.py <file> --title "..." --channel @handle
"""
import sys, os, json, time, argparse

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
    return (items[0]["id"], sn.get("title", ""),
            (sn.get("customUrl") or "").lstrip("@").lower())


def check_channel(yt, want):
    cid, title, handle = which_channel(yt)
    print("  channel: %s  (@%s, %s)" % (title, handle or "no handle", cid))
    if want:
        w = want.lstrip("@").lower()
        if w not in (handle, title.lower()):
            sys.exit("token points at '%s' (@%s), not %r -- refusing to upload. "
                     "Delete .yt-oauth/ and the YOUTUBE_* lines in .env to "
                     "re-grant against the right channel."
                     % (title, handle, want))
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
    ap.add_argument("--made-for-kids", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = args.file if os.path.isabs(args.file) else os.path.join(_env.ROOT,
                                                                   args.file)
    if not os.path.exists(path):
        sys.exit("no such file: %s" % path)
    size = os.path.getsize(path)
    if size == 0:
        sys.exit("%s is empty" % path)

    desc = args.description
    if args.description_file:
        p = args.description_file
        p = p if os.path.isabs(p) else os.path.join(_env.ROOT, p)
        desc = open(p, encoding="utf-8").read()
    if len(desc) > 5000:
        sys.exit("description is %d chars; YouTube's limit is 5000" % len(desc))
    if len(args.title) > 100:
        sys.exit("title is %d chars; YouTube's limit is 100" % len(args.title))

    body = {
        "snippet": {"title": args.title, "description": desc,
                    "categoryId": args.category,
                    "tags": [t.strip() for t in args.tags.split(",") if t.strip()]},
        "status": {"privacyStatus": args.privacy,
                   "selfDeclaredMadeForKids": bool(args.made_for_kids)},
    }

    print("%s  (%.1f MB)" % (os.path.relpath(path, _env.ROOT), size / 1e6))
    print("  title:   %s" % args.title)
    print("  privacy: %s" % args.privacy)

    creds = _yt.credentials()
    yt = service(creds)
    check_channel(yt, args.channel)

    if args.dry_run:
        print("\n  --dry-run: nothing uploaded")
        return

    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(path, chunksize=CHUNK, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    print("\n  uploading ...")
    t0, resp, tries = time.time(), None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
        except Exception as e:                      # noqa: BLE001
            tries += 1
            if tries > 5:
                raise
            wait = 2 ** tries
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
    for label, want, have in (("title", args.title, sn.get("title")),
                              ("privacy", args.privacy,
                               st.get("privacyStatus"))):
        mark = "ok" if want == have else "MISMATCH"
        if want != have:
            ok = False
        print("  %-8s %-8s asked %r, got %r" % (label, mark, want, have))
    if not ok:
        sys.exit("the video is up but not as asked -- fix it in Studio")

    side = os.path.splitext(path)[0] + ".youtube.json"
    with open(side, "w", encoding="utf-8") as f:
        json.dump({"id": vid, "url": url, "title": args.title,
                   "privacy": args.privacy, "bytes": size,
                   "uploaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime())},
                  f, ensure_ascii=False, indent=1)
    print("  %s" % os.path.relpath(side, _env.ROOT))

    pid, _doc = _project.find_by_output(path)
    if pid:
        _project.record(pid, "publish", out=path, script=__file__,
                        argv=sys.argv[1:],
                        published={"url": url, "privacy": args.privacy,
                                   "sidecar": _project.norm(side)},
                        note="uploaded %s" % args.title)
    else:
        print("  note: no project claims this render -- record the upload in "
              "its projects/<id>/project.json by hand")
    print("\n%s" % url)


if __name__ == "__main__":
    main()
