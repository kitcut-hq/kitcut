#!/usr/bin/env python
"""A finished film's poster and link-preview card, remade from one of the film's first seconds.

Films made before 2026-10-19 have a poster from the film's end (and a card from late in it), so
whoever saw a preview -- the player before play, a shared link, the gallery -- was shown how the
film ends. This puts that right for a film already online, without drawing it again:

    python studio/firstframe.py --film <id> --dry-run      make both pictures in a folder, change nothing
    python studio/firstframe.py --film <id>                copy them online and point the record at them
    python studio/firstframe.py --film <id> --at 1.5       the poster from 1.5 s (default POSTER_AT)
    python studio/firstframe.py --dir <outputs> --at 1     only the pictures, from a folder holding
                                                           film.mp4 (a copy of the film will do)

The poster is the film's frame at --at; the card is the same frame, pillarboxed to 1200x628. Both go online beside the film's other files
under names of their own (<name>-<hash of the picture>.<ext>, in the film's revision folder): a
film's files are served as immutable for a year (media.CACHE), so a changed picture needs a new
address. The record's `media.poster` and `media.card` then point at them; nothing else moves
(the film, its web copy, its subtitles, the share page's own pictures). The record keeps
`first_frame = {at, at_utc}` so a film done once is skipped (--force to do it again).
"""

import os
import sys
import time
import asyncio
import hashlib
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import media  # noqa: E402

POSTER_AT = 1.5  # seconds: past a title still being written, well inside the first seconds


def make(outputs, at):
    """film_poster.png (the film's frame at `at`) and card.jpg in `outputs`, which holds film.mp4.
    Returns the two paths. Raises when the frame cannot be cut."""
    mp4 = os.path.join(outputs, "film.mp4")
    if not os.path.isfile(mp4):
        raise RuntimeError("no film.mp4 in %s" % outputs)
    dur = media._duration(mp4)
    if dur and at >= dur - 0.05:
        raise RuntimeError("the film is %.1f s long" % dur)
    frame = media._frame(mp4, at)
    if frame is None:
        raise RuntimeError("ffmpeg could not cut the frame at %s s" % at)
    poster = os.path.join(outputs, "film_poster.png")
    tmp = "%s.%d.tmp" % (poster, os.getpid())
    frame.save(tmp, "PNG")
    os.replace(tmp, poster)
    # the card is the same frame, pillarboxed (media.pillarbox): not media.make_card, which may pick
    # a later, livelier frame, and this script's whole point is that no later frame is shown
    card = os.path.join(outputs, "card.jpg")
    media._save_jpeg(media.pillarbox(frame), card)
    return poster, card


def _named(path):
    """<name>-<hash of the bytes>.<ext>: a changed picture gets a new address."""
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()[:8]
    stem, ext = os.path.splitext(os.path.basename(path))
    return "%s-%s%s" % (stem, h, ext)


async def put(film, outputs):
    """Copy the two pictures online beside the film's files: {"poster": url, "card": url}."""
    import aiohttp

    urls = {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as s:
        for key, name, ctype in (
            ("poster", "film_poster.png", "image/png"),
            ("card", "card.jpg", "image/jpeg"),
        ):
            path = os.path.join(outputs, name)
            blob = media.blob_of(film, _named(path))
            await media._put(s, "%s/%s" % (film.id, blob), path, ctype)
            urls[key] = media.url_of(film.id, blob)
    return urls


def finished(f):
    rec = f.record()
    return rec.get("state") == "done" and bool((rec.get("media") or {}).get("video"))


async def run(film, at, dry, force, log=print):
    import agent

    rec = film.record()
    if not finished(film):
        raise RuntimeError("not a finished film that is online")
    if rec.get("first_frame") and not force:
        log("FIRSTFRAME %s: done already (%s s); --force to redo" % (film.id, rec["first_frame"].get("at")))
        return None
    outputs = film.path("outputs")
    if dry:
        # leave the film's own folder alone: the pictures are made in a folder of their own
        import tempfile

        tmp = tempfile.mkdtemp(prefix="firstframe-")
        os.symlink(os.path.join(outputs, "film.mp4"), os.path.join(tmp, "film.mp4"))
        outputs = tmp
    poster, card = await asyncio.to_thread(make, outputs, at)
    if dry:
        log("FIRSTFRAME %s: dry run, nothing copied or changed\n  %s\n  %s" % (film.id, poster, card))
        return {"poster": poster, "card": card}
    if not media.enabled():
        raise RuntimeError("copying online is off")
    urls = await put(film, outputs)
    new = dict(rec.get("media") or {})
    new.update(urls)
    fields = {
        "media": new,
        "first_frame": {"at": at, "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }
    film.update(**fields)
    await agent.save(film.id, fields)
    log("FIRSTFRAME %s: the poster and the card from %s s\n  %s\n  %s" % (film.id, at, urls["poster"], urls["card"]))
    return urls


async def _main(a):
    if a.dir:
        poster, card = make(a.dir, a.at)
        print("%s\n%s" % (poster, card))
        return
    import film as films

    f = films.Film(a.film) if os.path.isdir(a.film) else films.Film.open(a.film)
    if f is None:
        sys.exit("%s: no such film" % a.film)
    await run(f, a.at, a.dry_run, a.force)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--film", help="a film id, or a film's folder")
    g.add_argument("--dir", help="an outputs folder holding film.mp4: make the pictures only")
    ap.add_argument("--at", type=float, default=POSTER_AT, help="seconds into the film")
    ap.add_argument("--dry-run", action="store_true", help="make the pictures; copy and change nothing")
    ap.add_argument("--force", action="store_true", help="do a film again that was done")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
