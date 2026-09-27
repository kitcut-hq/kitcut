#!/usr/bin/env python
"""Finished films, online for good: film.mp4, its poster, its link-preview card and its subtitles
copied to Azure blob storage, so a film still plays when this laptop is off, and every page (and
the assistants' film player) names one media host instead of a tunnel whose name changes.

    python studio/media.py --film <id>      copy one film (again)
    python studio/media.py --backfill       every finished film that has no copy yet
    python studio/media.py --delete <id>    remove a film's copy

Where: STUDIO_MEDIA_BASE, the container's URL (https://kitcutst.blob.core.windows.net/films,
anonymous read of blobs), and STUDIO_MEDIA_SAS, a container SAS allowing create, write and delete
(a secret: the studio's .env). Without both nothing is copied, and films play from the tunnel as
before. Each file is one Put Blob call, <id>/<name>; the film's record keeps the URLs as "media".

Never the films' own container `media`: the catalog site's upload-media.py prunes that one of
everything that is not one of its own films.

A film never fails because of this: publish() answers {} when the copy did not work, and the
film is served from here as before.
"""

import os
import sys
import asyncio
import argparse
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procs  # noqa: E402

VERSION = "2023-11-03"  # x-ms-version: single Put Blob up to 5000 MiB
# what is copied, as (key in the record, file in outputs/, type); the video must be there
FILES = (
    ("video", "film.mp4", "video/mp4"),
    ("poster", "film_poster.png", "image/png"),
    ("card", "card.jpg", "image/jpeg"),
    ("subtitles", "film.vtt", "text/vtt"),
)
CACHE = "public, max-age=31536000, immutable"  # a film's files never change under one id
CARD = (1200, 628)  # the 1.91:1 image X, Facebook and most link previews show


class MediaError(Exception):
    pass


def base():
    return (os.environ.get("STUDIO_MEDIA_BASE") or "").strip().rstrip("/")


def sas():
    return procs.secret("STUDIO_MEDIA_SAS").lstrip("?")


def enabled():
    # plain http only to this machine (test_media.py's stand-in for Azure)
    return bool(base().startswith(("https://", "http://127.0.0.1:")) and sas())


def url_of(fid, name):
    return "%s/%s/%s" % (base(), fid, name)


# ------------------------------------------------------------------ the link-preview card
def _frame(mp4, t):
    """One frame of the film at t seconds, as a PIL image (None if ffmpeg cannot)."""
    import io
    import subprocess

    from PIL import Image

    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", mp4, "-frames:v", "1"]
        + ["-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True,
    )
    return (
        Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.returncode == 0 and r.stdout else None
    )


def make_card(outputs, length=None):
    """card.jpg: the film as a link preview, 1200x628 (1.91:1).

    The frame is the poster (the film's end, its payoff) unless that is mid fade-out -- films
    often end on paper -- when a clearly livelier frame from later in the film stands in (the
    most contrast among a few). The whole 16:9 frame is kept, so a title drawn at its top edge is
    not cut: scaled to the card's height, with the thin strips either side filled by a blurred
    stretch of the same frame (on paper it disappears; on a painting it reads as the picture
    going on)."""
    from PIL import Image, ImageFilter, ImageStat

    def contrast(im):
        return ImageStat.Stat(im.convert("L")).stddev[0]

    with Image.open(os.path.join(outputs, "film_poster.png")) as p:
        best = p.convert("RGB")
    mp4 = os.path.join(outputs, "film.mp4")
    if length and os.path.isfile(mp4):
        frames = [f for f in (_frame(mp4, length * k) for k in (0.5, 0.65, 0.8, 0.92)) if f]
        alt = max(frames, key=contrast, default=None)
        if alt is not None and contrast(alt) > 1.4 * contrast(best):
            best = alt
    card = best.resize(CARD, Image.LANCZOS).filter(ImageFilter.GaussianBlur(24))
    w = round(best.width * CARD[1] / best.height)
    card.paste(best.resize((w, CARD[1]), Image.LANCZOS), ((CARD[0] - w) // 2, 0))
    tmp = os.path.join(outputs, "card.%d.tmp" % os.getpid())
    card.save(tmp, "JPEG", quality=85, optimize=True, progressive=True)
    os.replace(tmp, os.path.join(outputs, "card.jpg"))


def ensure_card(outputs, length=None):
    """card.jpg, made now if it is not there yet (and the poster is)."""
    if not os.path.isfile(os.path.join(outputs, "card.jpg")) and os.path.isfile(
        os.path.join(outputs, "film_poster.png")
    ):
        make_card(outputs, length)


# ------------------------------------------------------------------ copying
async def _put(session, blob, path, ctype):
    url = "%s/%s?%s" % (base(), quote(blob), sas())
    headers = {
        "x-ms-blob-type": "BlockBlob",
        "x-ms-version": VERSION,
        "x-ms-blob-content-type": ctype,
        "x-ms-blob-cache-control": CACHE,
        "Content-Type": ctype,
        "Content-Length": str(os.path.getsize(path)),
    }
    with open(path, "rb") as f:
        async with session.put(url, data=f, headers=headers) as r:
            if r.status not in (200, 201):
                raise MediaError("%s: %d %s" % (blob, r.status, (await r.text())[:200]))


async def publish(film, timeout=900):
    """Copy the finished film's files; answers {"video", "poster", "card", "subtitles"} (the
    ones there are), or {} when copying is off or the video could not be copied."""
    if not enabled():
        return {}
    import aiohttp

    out = film.path("outputs")
    try:
        await asyncio.to_thread(ensure_card, out, film.record().get("length") or film.length)
    except Exception as e:  # noqa: BLE001 -- no card is no reason to keep the film offline
        print("film %s: no card: %s" % (film.id, e), file=sys.stderr, flush=True)
    urls = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            for key, name, ctype in FILES:
                p = os.path.join(out, name)
                if os.path.isfile(p):
                    await _put(s, "%s/%s" % (film.id, name), p, ctype)
                    urls[key] = url_of(film.id, name)
    except Exception as e:  # noqa: BLE001 -- the film is made; the copy is a bonus
        print("film %s: not copied online: %s" % (film.id, e), file=sys.stderr, flush=True)
        return urls if "video" in urls else {}
    return urls if "video" in urls else {}


async def delete(fid, timeout=60):
    """Remove a film's copy. Returns how many files went."""
    if not enabled():
        return 0
    import aiohttp

    gone = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        for _, name, _ in FILES:
            url = "%s/%s?%s" % (base(), quote("%s/%s" % (fid, name)), sas())
            async with s.delete(url, headers={"x-ms-version": VERSION}) as r:
                if r.status in (200, 202):
                    gone += 1
                elif r.status != 404:
                    raise MediaError("%s/%s: %d %s" % (fid, name, r.status, (await r.text())[:200]))
    return gone


# ------------------------------------------------------------------ the command line
async def _publish_and_record(f):
    import agent

    urls = await publish(f)
    if urls:
        f.update(media=urls)
        await agent.save(f.id, {"media": urls})
    return urls


async def _main(args):
    import agent  # noqa: F401 -- loads the studio's .env (the SAS) and the record store
    from film import Film

    if not enabled():
        sys.exit("STUDIO_MEDIA_BASE and STUDIO_MEDIA_SAS must both be set (the studio's .env)")
    if args.delete:
        n = await delete(args.delete)
        f = Film.open(args.delete)
        if f is not None:
            f.update(media=None)
            await agent.save(f.id, {"media": None})
        print("%s: %d files removed" % (args.delete, n))
        return
    if args.film:
        f = Film.open(args.film)
        if f is None or not f.record().get("ok"):
            sys.exit("%s: no such finished film" % args.film)
        print(args.film, await _publish_and_record(f) or "NOT copied")
        return
    todo = [f for f in Film.all() if f.record().get("ok") and not f.record().get("media")]
    print("%d finished films have no copy online" % len(todo))
    for f in reversed(todo):  # oldest first
        if not os.path.isfile(f.path("outputs", "film.mp4")):
            print("  %s: no film.mp4, skipped" % f.id)
            continue
        urls = await _publish_and_record(f)
        print("  %s: %s" % (f.id, "ok" if urls else "NOT copied"), flush=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--film", help="copy this film (again)")
    g.add_argument("--backfill", action="store_true", help="every finished film with no copy yet")
    g.add_argument("--delete", help="remove this film's copy")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
