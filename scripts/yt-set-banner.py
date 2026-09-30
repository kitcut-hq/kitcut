#!/usr/bin/env python
"""Set a YouTube channel's banner (the header image), and prove it changed.

Two Data API calls: `channelBanners.insert` uploads the image and hands back a
URL, then `channels.update(part=brandingSettings)` points
`brandingSettings.image.bannerExternalUrl` at it. The second call REPLACES the
whole brandingSettings part, so the channel's existing `brandingSettings.channel`
block -- title, description, keywords, country, language, trailer -- is read
first and sent back exactly as fetched; leaving it out wipes the description
and keywords. Afterwards the channel is re-read and the new URL, and the
unchanged channel block, are asserted.

What YouTube takes: JPEG or PNG, 16:9, at least 2048x1152 (2560x1440 is the
recommended size), under 6 MB. Only the middle 1235x338 is safe on every
device; the rest is cropped on phones and shown on TVs. The image is checked
before any consent is spent. This does not crop or scale -- make the image the
right shape first (a lanczos `scale=2560:1440` in ffmpeg for a 16:9 source).

Scope: `channels.update` needs `youtube` or `youtube.force-ssl` -- the grant
yt-set-chapters.py / yt-upload.py / yt-connect.py already share. kitcut.ai's
own grants are `youtube.upload` + `youtube.readonly` and cannot do this. A
channel this machine has no grant for needs `--reauth` once: Google's account
chooser opens (forced even for a signed-in browser), pick the BRAND account
that owns the channel. The grant is filed as .yt-oauth/token-<handle>.json and
refused -- and deleted -- if it came back for any other channel.

The profile picture (avatar) cannot be set through the API at all; that one is
uploaded by hand in Studio -> Customization -> Branding.

Invoke as:
  python scripts/yt-set-banner.py <image> --channel @handle --dry-run
  python scripts/yt-set-banner.py <image> --channel @handle
  python scripts/yt-set-banner.py <image> --channel @handle --reauth  # first time
  python scripts/yt-set-banner.py <image> --channel @handle --reauth --no-browser
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import _project  # noqa: E402
from importlib import import_module  # noqa: E402

_yt = import_module("yt-set-chapters")

MAX_BYTES = 6 * 1024 * 1024
MIN_W, MIN_H = 2048, 1152
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}
# what the channel block must still say after the write
KEPT = ("title", "description", "keywords", "country", "defaultLanguage", "unsubscribedTrailer")


def check_image(path):
    """(mimetype, w, h, bytes) for an image YouTube will take, or exit saying why."""
    from PIL import Image

    size = os.path.getsize(path)
    if size > MAX_BYTES:
        sys.exit("%s is %.1f MB; YouTube's banner limit is 6 MB" % (path, size / 1e6))
    with Image.open(path) as im:
        fmt, (w, h) = im.format, im.size
    if fmt not in FORMATS:
        sys.exit("%s is %s; a banner must be JPEG or PNG" % (path, fmt))
    if w < MIN_W or h < MIN_H:
        sys.exit("%s is %dx%d; YouTube needs at least %dx%d" % (path, w, h, MIN_W, MIN_H))
    if abs(w / h - 16 / 9) > 0.01:
        sys.exit("%s is %dx%d (%.3f:1), not 16:9 -- crop or pad it first" % (path, w, h, w / h))
    return FORMATS[fmt], w, h, size


def service(creds):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def assert_channel(yt, want):
    """The channel id the grant points at; exits (dropping a wrong grant) if it is not `want`."""
    items = yt.channels().list(part="snippet", mine=True).execute().get("items") or []
    if not items:
        sys.exit("this grant owns no channel -- rerun with --reauth and pick the brand account")
    cid, sn = items[0]["id"], items[0]["snippet"]
    title, handle = sn.get("title", ""), (sn.get("customUrl") or "").lstrip("@").lower()
    print("  channel: %s  (@%s, %s)" % (title, handle or "no handle", cid))
    w = want.lstrip("@").lower()
    if w not in (handle, title.lower(), cid.lower()):
        token = _yt.channel_token(want)
        if os.path.exists(token):
            os.remove(token)  # filed under the wrong handle, it would be confidently wrong forever
        sys.exit(
            "grant points at '%s' (@%s), not %s -- refusing to touch its banner.\n"
            "Rerun with --reauth; at Google's chooser pick the BRAND account that owns %s."
            % (title, handle, want, want)
        )
    return cid


def branding(yt, cid):
    items = yt.channels().list(part="brandingSettings", id=cid).execute().get("items") or []
    if not items:
        sys.exit("channel %s does not read back" % cid)
    return items[0].get("brandingSettings") or {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", help="JPEG/PNG, 16:9, >= 2048x1152, < 6 MB (2560x1440 ideal)")
    ap.add_argument(
        "--channel", required=True, help="handle, title or UC id the grant MUST point at"
    )
    ap.add_argument(
        "--reauth",
        action="store_true",
        help="force Google's consent (account chooser shown) and file the grant under --channel",
    )
    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="with --reauth: print the consent URL to paste into a private window",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="check the image, the grant and the channel; upload and change nothing",
    )
    _env.add_workspace_arg(ap)
    args = ap.parse_args()
    _env.set_workspace(args.workspace)

    path = _env.resolve(args.image)
    if not os.path.exists(path):
        sys.exit("no such file: %s" % path)
    mime, w, h, size = check_image(path)
    print("%s  %dx%d  %.2f MB  %s" % (path, w, h, size / 1e6, mime))

    creds = _yt.credentials(
        args.channel,
        reauth=args.reauth,
        open_browser=not args.no_browser,
        prompt="select_account consent",
    )
    yt = service(creds)
    cid = assert_channel(yt, args.channel)

    before = branding(yt, cid)
    chan = before.get("channel") or {}
    old_url = (before.get("image") or {}).get("bannerExternalUrl")
    print("  banner now: %s" % (old_url or "(none)"))
    print("  sent back unchanged: %s" % (", ".join(chan) or "(empty channel block)"))

    if args.dry_run:
        print("\n  --dry-run: nothing uploaded, nothing changed")
        return

    from googleapiclient.http import MediaFileUpload

    got = (
        yt.channelBanners()
        .insert(channelId=cid, media_body=MediaFileUpload(path, mimetype=mime))
        .execute()
    )
    url = got.get("url")
    if not url:
        sys.exit("channelBanners.insert returned no url: %r" % got)
    print("  uploaded -> %s" % url)

    body = {"id": cid, "brandingSettings": {"channel": chan, "image": {"bannerExternalUrl": url}}}
    yt.channels().update(part="brandingSettings", body=body).execute()

    # read-after-write is not immediately consistent on this API (see
    # yt-set-chapters.py), so a stale read gets a few tries before it counts
    for attempt in range(5):
        if attempt:
            time.sleep(3)
        after = branding(yt, cid)
        now = (after.get("image") or {}).get("bannerExternalUrl")
        if now == url:
            break
    else:
        sys.exit("update succeeded but the banner still reads %r -- inspect it in Studio" % now)
    lost = [k for k in KEPT if chan.get(k) != (after.get("channel") or {}).get(k)]
    if lost:
        sys.exit("banner set, but these channel fields changed: %s -- check Studio" % lost)
    print("  verified: bannerExternalUrl is the new image; channel fields unchanged")

    pid, _doc = _project.find_by_output(path)
    if pid:
        _project.record(
            pid,
            "publish",
            out=path,
            script=__file__,
            argv=sys.argv[1:],
            kind="channel-banner",
            published={"channel": cid, "banner_url": url, "replaced": old_url},
            note="set as the channel banner of %s" % args.channel,
        )
    else:
        print("  note: no project claims this image -- record the change by hand")
    print("\nhttps://www.youtube.com/channel/%s" % cid)


if __name__ == "__main__":
    main()
