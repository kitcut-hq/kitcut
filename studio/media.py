#!/usr/bin/env python
"""Finished films, online for good: film.mp4, its poster, its link-preview card and its subtitles
copied to Azure blob storage, so a film still plays when this laptop is off, and every page (and
the assistants' film player) names one media host instead of a tunnel whose name changes.

    python studio/media.py --film <id>      copy one film (again)
    python studio/media.py --backfill       every finished film that has no copy yet
    python studio/media.py --delete <id>    remove a film's copy
    python studio/media.py --web-backfill [--first <id>]   make and copy the web copy of every
                                            film online without one

Every film gets a web copy (make_web, WEB below): the master re-encoded at 5 Mbps, which is what
every page plays; the master stays for downloads and YouTube.

Where: STUDIO_MEDIA_BASE, the container's URL (https://kitcutst.blob.core.windows.net/films,
anonymous read of blobs), and STUDIO_MEDIA_SAS, a container SAS allowing create, write and delete
(a secret: the studio's .env). Without both nothing is copied, and films play from the tunnel as
before. Each file is one Put Blob call, <id>/<name>; the film's record keeps the URLs as "media".
The share page's two pictures (share.jpg, thumb.jpg: make_share, publish_share) go up the same
way when share.py has made them, as share-<v>.jpg and thumb-<v>.jpg (<v> a hash of their bytes,
so a remake gets a new URL); their URLs are kept in the record's "share".

Never the films' own container `media`: the catalog site's upload-media.py prunes that one of
everything that is not one of its own films.

A film never fails because of this: publish() answers {} when the copy did not work, and the
film is served from here as before.
"""

import os
import re
import sys
import asyncio
import argparse
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procs  # noqa: E402

VERSION = "2023-11-03"  # x-ms-version: single Put Blob up to 5000 MiB
# what is copied, as (key in the record, file in outputs/, type); the video must be there. "web"
# is the copy every page plays (make_web); "video" the master, for downloads (YouTube sends the
# master from this machine).
FILES = (
    ("web", "film_web.mp4", "video/mp4"),
    ("video", "film.mp4", "video/mp4"),
    ("poster", "film_poster.png", "image/png"),
    ("card", "card.jpg", "image/jpeg"),
    ("subtitles", "film.vtt", "text/vtt"),
)
CACHE = "public, max-age=31536000, immutable"  # a film's files never change under one id
CARD = (1200, 628)  # the 1.91:1 image X, Facebook and most link previews show

# The web copy: the master (sketch-render's cq 18, uncapped) is ~36 Mbps -- 2.2 GB for 8 minutes,
# too heavy to stream. Measured 2026-09-27 on the 8-minute Dell/HP film (60 s of the dark data
# hall, 60 s of paper) and a 10 s film, 1080p60 NVENC: every cq from 24 to 30 fills a 5 Mbps cap
# (~300 MB for 8 minutes, 7.7 MB for 13 s); uncapped cq 26 wants ~11 Mbps. SSIM reads only
# 0.93-0.95 at any of them, because the paper grain the engine animates is noise to SSIM; side by
# side at 1:1, the characters, lettering and racks at 5M are indistinguishable from the master,
# only the grain softens. 30 fps saves ~10 % and loses the smoothness, so 60 stays. A manifest's
# "web" block overrides this.
WEB = {"cq": 26, "preset": "p5", "maxrate": "5M", "bufsize": "10M", "audio_bitrate": "160k"}
WEB_MBPS = 5.5  # a master already this light is copied as it is


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


def blob_of(film, name):
    """Where a film's file goes online: <id>/<name>, or <id>/r<n>/<name> once the film has been
    rendered again after a hand patch (resume.py --patched sets media_rev). Its files are served
    as immutable for a year (CACHE), so a changed film must have new names, or everyone who
    watched it keeps the old one."""
    rev = film.record().get("media_rev")
    return "r%d/%s" % (rev, name) if rev else name


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
    from PIL import Image, ImageStat

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
    _save_jpeg(pillarbox(best), os.path.join(outputs, "card.jpg"))


def pillarbox(img):
    """A 16:9 picture as a 1200x628 link preview, nothing of it cut: scaled to the card's height
    and centred, the thin strips either side a blurred stretch of the same picture."""
    from PIL import Image, ImageFilter

    img = img.convert("RGB")
    card = img.resize(CARD, Image.LANCZOS).filter(ImageFilter.GaussianBlur(24))
    w = round(img.width * CARD[1] / img.height)
    card.paste(img.resize((w, CARD[1]), Image.LANCZOS), ((CARD[0] - w) // 2, 0))
    return card


def _save_jpeg(img, path):
    """JPEG q85, progressive, written whole (a reader never sees half a file)."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    img.save(tmp, "JPEG", quality=85, optimize=True, progressive=True)
    os.replace(tmp, path)


# ------------------------------------------------------------------ the share page's pictures
SHARE_FILES = (("image", "share.jpg"), ("thumb", "thumb.jpg"))  # (key in the share, file)
THUMB = (1280, 720)


def make_share(outputs, src_jpg):
    """The share page's pictures from one worded thumbnail (thumbs.py, 1920x1080): share.jpg, the
    link preview (1200x628, pillarboxed as the card is), and thumb.jpg (1280x720, the thumbnail
    scaled down). Returns their paths, {"image", "thumb"}."""
    from PIL import Image

    with Image.open(src_jpg) as im:
        src = im.convert("RGB")
    os.makedirs(outputs, exist_ok=True)
    out = {"image": os.path.join(outputs, "share.jpg"), "thumb": os.path.join(outputs, "thumb.jpg")}
    _save_jpeg(pillarbox(src), out["image"])
    _save_jpeg(src.resize(THUMB, Image.LANCZOS), out["thumb"])
    return out


def share_version(outputs):
    """The share pictures' version: the first 8 hex of a hash of their bytes. It is in their blob
    names (share-<v>.jpg, thumb-<v>.jpg), so a remade picture gets a new URL -- the files go up
    with the year-long immutable CACHE, and a browser or a link-preview cache would otherwise keep
    showing the old one."""
    import hashlib

    h = hashlib.sha256()
    for _, name in SHARE_FILES:
        p = os.path.join(outputs, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:8]


def share_blob(name, v):
    """share.jpg -> share-<v>.jpg"""
    stem, ext = os.path.splitext(name)
    return "%s-%s%s" % (stem, v, ext)


SHARE_BLOB = re.compile(r"^(share|thumb)(-[0-9a-f]{8})?\.jpg$")


async def publish_share(film, timeout=300):
    """Copy the share pictures online under versioned names (share_version): {"image": url,
    "thumb": url} (the ones there are), or {} when copying is off. Raises when a copy is
    refused. A remake's older copies are left where they are: a preview already posted may still
    point at them."""
    if not enabled():
        return {}
    import aiohttp

    v = share_version(film.path("outputs"))
    urls = {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        for key, name in SHARE_FILES:
            p = film.path("outputs", name)
            if os.path.isfile(p):
                blob = share_blob(name, v)
                await _put(s, "%s/%s" % (film.id, blob), p, "image/jpeg")
                urls[key] = url_of(film.id, blob)
    return urls


def share_blobs(fid):
    """The share pictures' blob names a film's record names (its "share" URLs), and the
    unversioned ones of before."""
    names = [n for _, n in SHARE_FILES]
    try:
        from film import Film

        f = Film.open(fid)
        sh = (f.record().get("share") or {}) if f is not None else {}
    except Exception:  # noqa: BLE001 -- no record: the fixed names only
        sh = {}
    for key, _ in SHARE_FILES:
        name = str(sh.get(key) or "").rsplit("/", 1)[-1]
        if SHARE_BLOB.match(name) and name not in names:
            names.append(name)
    return names


def ensure_card(outputs, length=None):
    """card.jpg, made now if it is not there yet (and the poster is)."""
    if not os.path.isfile(os.path.join(outputs, "card.jpg")) and os.path.isfile(
        os.path.join(outputs, "film_poster.png")
    ):
        make_card(outputs, length)


# ------------------------------------------------------------------ the web copy
def _duration(path):
    import subprocess

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def web_settings(film):
    """WEB, with the machine's STUDIO_WEB_PRESET and then the film's own manifest "web" block
    over it. A CPU-only machine encodes the web copy with libx264, where the speed tier is real
    time: on the Azure VM (8 vCPU) p2 (veryfast) took 16 s for 48 s of film against p5's 39 s,
    VMAF 99.99 both, under the same 5 Mbps cap (studio/deploy/README.md)."""
    import json

    try:
        with open(film.manifest, encoding="utf-8") as f:
            own = json.load(f).get("web") or {}
    except (OSError, ValueError):
        own = {}
    machine = (
        {"preset": os.environ["STUDIO_WEB_PRESET"]} if os.environ.get("STUDIO_WEB_PRESET") else {}
    )
    return WEB | machine | {k: v for k, v in own.items() if not k.startswith("_")}


def make_web(film):
    """outputs/film_web.mp4: the master re-encoded to stream (WEB), its soft subtitles kept; a
    master already light enough is copied as it is. Made once (a newer copy is kept). Returns
    its path, or None when there is no master. Raises on a failed encode."""
    import shutil
    import subprocess

    out = film.path("outputs")
    src, dst = os.path.join(out, "film.mp4"), os.path.join(out, "film_web.mp4")
    if not os.path.isfile(src):
        return None
    if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    secs = _duration(src)
    tmp = dst + ".%d.tmp.mp4" % os.getpid()
    if secs and os.path.getsize(src) * 8 / secs / 1e6 <= WEB_MBPS:
        shutil.copyfile(src, tmp)
    else:
        scripts = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
        )
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import _encode

        cfg = _encode.resolve(web_settings(film))
        cmd = (
            ["ffmpeg", "-y", "-v", "error"]
            + _encode.decode_args()
            + ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?"]
            + _encode.video_args(cfg)
            + _encode.audio_args(cfg)
            + ["-c:s", "copy", "-movflags", "+faststart", tmp]
        )
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode or not os.path.isfile(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            raise MediaError("web copy: %s" % (r.stderr.strip()[-300:] or "ffmpeg failed"))
    os.replace(tmp, dst)
    return dst


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


async def publish(film, timeout=3600):
    """Make the web copy, then copy the finished film's files; answers {"web", "video", "poster",
    "card", "subtitles"} (the ones there are), or {} when copying is off or the master could not
    be copied. A web copy that failed leaves the master to play."""
    if not enabled():
        return {}
    import aiohttp

    out = film.path("outputs")
    try:
        await asyncio.to_thread(ensure_card, out, film.record().get("length") or film.length)
    except Exception as e:  # noqa: BLE001 -- no card is no reason to keep the film offline
        print("film %s: no card: %s" % (film.id, e), file=sys.stderr, flush=True)
    try:
        await asyncio.to_thread(make_web, film)
    except Exception as e:  # noqa: BLE001 -- the master plays instead
        print("film %s: no web copy: %s" % (film.id, e), file=sys.stderr, flush=True)
    urls = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            for key, name, ctype in FILES:
                p = os.path.join(out, name)
                if os.path.isfile(p):
                    await _put(s, "%s/%s" % (film.id, blob_of(film, name)), p, ctype)
                    urls[key] = url_of(film.id, blob_of(film, name))
    except Exception as e:  # noqa: BLE001 -- the film is made; the copy is a bonus
        print("film %s: not copied online: %s" % (film.id, e), file=sys.stderr, flush=True)
        return urls if "video" in urls else {}
    return urls if "video" in urls else {}


async def publish_web(film, timeout=3600):
    """Make and copy only the web copy (a film already online): {"web": url}. Raises."""
    import aiohttp

    p = await asyncio.to_thread(make_web, film)
    if not p:
        raise MediaError("no film.mp4")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        await _put(s, "%s/%s" % (film.id, blob_of(film, "film_web.mp4")), p, "video/mp4")
    return {"web": url_of(film.id, blob_of(film, "film_web.mp4"))}


async def delete(fid, timeout=60):
    """Remove a film's copy. Returns how many files went."""
    if not enabled():
        return 0
    import aiohttp

    import film as films

    f = films.Film.open(fid)
    rev = (f.record().get("media_rev") or 0) if f else 0
    # every revision's copy too (blob_of): a patched film left its earlier files online
    names = [n for _, n, _ in FILES]
    names += ["r%d/%s" % (r, n) for r in range(1, rev + 1) for n in names]
    gone = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        for name in names + share_blobs(fid):
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
    if args.web_backfill:
        todo = [
            f
            for f in Film.all()
            if (f.record().get("media") or {}).get("video")
            and not (f.record().get("media") or {}).get("web")
        ]
        if args.first:
            todo.sort(key=lambda f: f.id != args.first)
        print("%d films online have no web copy" % len(todo), flush=True)
        for f in todo:
            try:
                urls = await publish_web(f)
            except Exception as e:  # noqa: BLE001 -- say which, and carry on
                print("  %s: NOT made: %s" % (f.id, e), flush=True)
                continue
            m = (f.record().get("media") or {}) | urls
            f.update(media=m)
            await agent.save(f.id, {"media": m})
            size = os.path.getsize(f.path("outputs", "film_web.mp4")) / 1e6
            print("  %s: ok, %.1f MB" % (f.id, size), flush=True)
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
    g.add_argument(
        "--web-backfill",
        action="store_true",
        help="make and copy the web copy of every film online without one",
    )
    ap.add_argument("--first", help="with --web-backfill: this film before the others")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
