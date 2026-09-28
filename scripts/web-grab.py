#!/usr/bin/env python
"""Bring the real thing from the web into a sketch film: a picture (a logo, a product photo), a
photograph of a web page, or a font from Google Fonts -- each saved beside the film's manifest
and registered in it, so film.js can show it.

A film about a real company, product or event is watched by people who know it, and an invented
logo in a comic font reads as a fake. This is what lets the studio use the real one.

    --picture URL --name logo   web/logo.png (or .jpg), manifest images.web_logo, so film.js draws
                                it with SK.image('web_logo', x, y, w). PNG, JPEG, WebP, GIF (first
                                frame), ICO (largest size) and SVG (drawn by the browser, at
                                --width px) all arrive as a PNG with their transparency, or a JPEG
                                for a large opaque photo
    --page URL --name site      the page as a browser at --size (default 1920x1080) sees it,
                                web/site.jpg, images.web_site. A taller --size (1440x4000) takes
                                more of the page, to scroll through
    --font "Inter" [--weights 400,700]
                                web/fonts/Inter-400.ttf ..., in the manifest's fonts, so film.js
                                writes with it: SK.text(..., {font: 'Inter', wt: 700})
    --check URL                 may this URL be fetched (public_url), and what it resolves to;
                                fetches nothing
    --dry-run                   says what the others would do; fetches nothing

Only the public internet is reached (_web.py): every connection, and every redirect, goes to an
address checked when it connects. Where each thing came from goes to web/sources.json.

Invoke as:  python scripts/web-grab.py --manifest <film>/sketch.json --picture <url> --name logo
            python scripts/web-grab.py --manifest <film>/sketch.json --font "Inter"
"""

import sys
import os
import io
import re
import json
import time
import base64
import shutil
import argparse
import tempfile
import importlib
import subprocess
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image  # noqa: E402

import _web  # noqa: E402

_html2img = importlib.import_module("html-to-image")  # hyphen: not importable

NAME = re.compile(r"[a-z][a-z0-9_]{0,30}")
FAMILY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ]{0,39}")
MAX_SIDE = 2560  # a picture's longest side, px: a 1080p film never shows more of one
PHOTO_SIDE = 1024  # an opaque picture larger than this is stored as a JPEG (the bundle inlines it)
MIN_SIDE = 16
FONTS_API = "https://fonts.googleapis.com/css2?family=%s"
FONT_HOST = "fonts.gstatic.com"


class GrabError(Exception):
    """Something Claude can act on: said in one line."""


# ------------------------------------------------------------------ the manifest
def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path, m):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def note_source(root, key, **fields):
    """web/sources.json: where each picture, page and font came from, and when."""
    p = os.path.join(root, "web", "sources.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d[key] = fields | {"fetched": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ pictures
def kind_of(data):
    """The picture's format from its first bytes (a server's Content-Type is often wrong)."""
    head = data[:512]
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"\x00\x00\x01\x00"):
        return "ico"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    text = data[:4096].decode("utf-8", "ignore").lower()
    if "<svg" in text:
        return "svg"
    if "<html" in text or "<!doctype html" in text:
        return "html"
    return None


def has_alpha(im):
    if im.mode in ("RGBA", "LA", "PA"):
        return im.getchannel("A").getextrema()[0] < 255
    return "transparency" in im.info


def store(im, out_base):
    """Save a PIL image as out_base.png (transparency, or small) or .jpg (a large opaque photo).
    Returns (path, w, h, alpha)."""
    im.load()
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    alpha = has_alpha(im)
    for ext in ("png", "jpg"):  # the same name again replaces the other format too
        if os.path.exists(out_base + "." + ext):
            os.remove(out_base + "." + ext)
    if alpha:
        path = out_base + ".png"
        im.convert("RGBA").save(path, optimize=True)
    elif max(im.size) > PHOTO_SIDE:
        path = out_base + ".jpg"
        im.convert("RGB").save(path, quality=90, optimize=True)
    else:
        path = out_base + ".png"
        im.convert("RGB").save(path, optimize=True)
    return path, im.size[0], im.size[1], alpha


def raster(data, kind):
    """A PIL image from raster bytes: the largest size of an icon, the first frame of a GIF."""
    im = Image.open(io.BytesIO(data))
    if kind == "ico":
        sizes = sorted(im.info.get("sizes") or [im.size], key=lambda s: s[0] * s[1])
        im.size = sizes[-1]
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im.load()
    return im


def browser():
    found = _html2img.find_browsers()
    if not found:
        raise GrabError("no Chromium browser on this machine (Edge or Chrome)")
    return found[0]


def _profile_dir():
    # Chromium's socket path must stay under 108 bytes: a film's TMPDIR is too deep (KI-030)
    return tempfile.mkdtemp(prefix="wg-", dir=None if os.name == "nt" else "/tmp")


def run_browser(url, out_png, size, transparent=False, settle_ms=6000, timeout=60):
    """Headless Chromium's screenshot of `url` at `size` (w, h) into out_png."""
    exe = browser()
    prof = _profile_dir()
    env = dict(_env.ENV)
    if os.name != "nt":
        env["TMPDIR"] = prof
    flags = [
        "--headless",
        "--screenshot=%s" % os.path.abspath(out_png),
        "--window-size=%d,%d" % size,
        "--force-device-scale-factor=1",
        "--hide-scrollbars",
        "--virtual-time-budget=%d" % settle_ms,
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--mute-audio",
        "--lang=en-US",
        "--user-agent=%s" % _web.UA,
        "--user-data-dir=%s" % prof,
    ]
    if transparent:
        flags.append("--default-background-color=00000000")
    try:
        if os.path.exists(out_png):
            os.remove(out_png)
        r = subprocess.run(
            [exe, *flags, url], env=env, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise GrabError("the browser took over %d s on %s" % (timeout, url)) from None
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    if not (os.path.exists(out_png) and os.path.getsize(out_png) > 0):
        raise GrabError(
            "the browser made no picture of %s: %s" % (url, (r.stderr or r.stdout).strip()[-300:])
        )


def svg_raster(data, width, work):
    """An SVG drawn by the browser at `width` px, cropped to its own ink. As an <img>, an SVG
    loads nothing from anywhere and runs no script."""
    uri = "data:image/svg+xml;base64," + base64.b64encode(data).decode()
    page = os.path.join(work, "svg.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
            "img{display:block;width:%dpx;height:auto}</style></head>"
            '<body><img src="%s"></body></html>' % (width, uri)
        )
    shot = os.path.join(work, "svg.png")
    run_browser(
        _html2img.file_url(page), shot, (width + 40, width * 2), transparent=True, settle_ms=500
    )
    im = Image.open(shot).convert("RGBA")
    box = im.getchannel("A").getbbox()
    if not box:
        raise GrabError("the SVG drew nothing (an empty or broken file)")
    return im.crop(box)


def picture(root, url, name, width=1600, dry=False):
    """Fetch a picture into web/<name>.png|jpg and the manifest's images as web_<name>."""
    ok, why = _web.public_url(url)
    if not ok:
        raise GrabError(why)
    if dry:
        return {"would": "fetch %s into web/%s.png|jpg as web_%s" % (url, name, name)}
    try:
        data, ctype, final = _web.fetch(url, accept="image/*,*/*;q=0.5")
    except _web.NotPublic as e:
        raise GrabError(str(e)) from None
    except (OSError, ValueError) as e:
        raise GrabError("could not fetch %s: %s" % (url, e)) from None
    kind = kind_of(data)
    if kind == "html":
        raise GrabError(
            "%s is a web page, not a picture: take the picture's own URL from the page "
            "(an <img> src, an og:image, an icon link), or photograph the page with page" % url
        )
    if kind in (None, "avif"):
        raise GrabError("%s is not a picture this studio reads (%s)" % (url, ctype or "unknown"))
    work = tempfile.mkdtemp(prefix="wg-")
    try:
        im = svg_raster(data, width, work) if kind == "svg" else raster(data, kind)
        if min(im.size) < MIN_SIDE:
            raise GrabError(
                "%s is only %dx%d px, too small to show" % (url, im.size[0], im.size[1])
            )
        d = os.path.join(root, "web")
        os.makedirs(d, exist_ok=True)
        path, w, h, alpha = store(im, os.path.join(d, name))
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise GrabError("%s could not be read as a picture: %s" % (url, e)) from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rel = "web/" + os.path.basename(path)
    note_source(root, "web_" + name, url=url, final=final, kind=kind, file=rel, w=w, h=h)
    return {"image": "web_" + name, "file": rel, "w": w, "h": h, "alpha": alpha, "kind": kind}


def page(root, url, name, size=(1920, 1080), dry=False):
    """The page as a browser sees it, into web/<name>.jpg and the manifest as web_<name>."""
    ok, why = _web.public_url(url)
    if not ok:
        raise GrabError(why)
    if dry:
        return {"would": "photograph %s at %dx%d into web/%s.jpg" % (url, size[0], size[1], name)}
    work = tempfile.mkdtemp(prefix="wg-")
    try:
        shot = os.path.join(work, "page.png")
        run_browser(url, shot, size, settle_ms=8000, timeout=90)
        im = Image.open(shot).convert("RGB")
        lo, hi = zip(*im.getextrema(), strict=True)
        if max(hi) - min(lo) < 8:
            raise GrabError(
                "the page came out blank (%s): it may need a login or refuse robots" % url
            )
        d = os.path.join(root, "web")
        os.makedirs(d, exist_ok=True)
        for ext in ("png", "jpg"):
            if os.path.exists(os.path.join(d, "%s.%s" % (name, ext))):
                os.remove(os.path.join(d, "%s.%s" % (name, ext)))
        path = os.path.join(d, name + ".jpg")
        im.save(path, quality=90, optimize=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rel = "web/" + name + ".jpg"
    note_source(root, "web_" + name, url=url, kind="page", file=rel, w=size[0], h=size[1])
    return {"image": "web_" + name, "file": rel, "w": size[0], "h": size[1], "kind": "page"}


# ------------------------------------------------------------------ fonts
def font_css(family, weights):
    """Google Fonts' CSS for the family at these weights: one full TTF per weight -- asked as a
    client that is not a browser, which gets whole fonts (a browser gets per-script WOFF2
    slices). {weight: url}, or {} when the family has none of them. A family Google does not
    have still answers 200, with a stand-in from /l/font; only its own files (/s/) count."""
    spec = urllib.parse.quote(family.replace(" ", "+"), safe="+")
    got = {}
    for w in weights:  # one at a time: one missing weight fails the whole request
        try:
            css, _, _ = _web.fetch(
                FONTS_API % ("%s:wght@%d" % (spec, w)), max_bytes=65536, ua="kitcut-web-grab"
            )
        except (OSError, ValueError, _web.NotPublic):
            continue
        for block in re.findall(r"@font-face\s*{([^}]*)}", css.decode("utf-8", "ignore")):
            fw = re.search(r"font-weight:\s*(\d+)", block)
            src = re.search(r"url\((https://[^)]+)\)", block)
            u = urllib.parse.urlsplit(src.group(1)) if src else None
            if fw and u and u.hostname == FONT_HOST and u.path.startswith("/s/"):
                got[int(fw.group(1))] = src.group(1)
    return got


def font(root, m, family, weights=(400, 700), dry=False):
    """A Google Fonts family into web/fonts/ and the manifest's fonts."""
    if not FAMILY.fullmatch(family or ""):
        raise GrabError("a font family is a Google Fonts name, like 'Inter' or 'Source Serif 4'")
    if dry:
        return {"would": "fetch %s %s from Google Fonts into web/fonts/" % (family, weights)}
    urls = font_css(family, weights)
    if not urls:
        raise GrabError(
            "%r is not on Google Fonts at weights %s (only Google Fonts can be fetched)"
            % (family, ", ".join(map(str, weights)))
        )
    d = os.path.join(root, "web", "fonts")
    os.makedirs(d, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "", family)
    fonts = [f for f in m.get("fonts", []) if f.get("family") != family]
    for w, url in sorted(urls.items()):
        data, _, _ = _web.fetch(url, max_bytes=8 * 1024 * 1024)
        rel = "web/fonts/%s-%d.ttf" % (stem, w)
        with open(os.path.join(root, *rel.split("/")), "wb") as f:
            f.write(data)
        fonts.append({"file": rel, "family": family, "weight": str(w)})
    m["fonts"] = fonts
    note_source(root, "font:" + family, url=FONTS_API % family, weights=sorted(urls))
    return {"font": family, "weights": sorted(urls), "missing": sorted(set(weights) - set(urls))}


# ------------------------------------------------------------------ main
def size_arg(s):
    m = re.fullmatch(r"(\d{3,4})x(\d{3,4})", s or "")
    if not m:
        raise argparse.ArgumentTypeError("a size is WxH, like 1920x1080")
    w, h = int(m.group(1)), int(m.group(2))
    if not (640 <= w <= 2560 and 480 <= h <= 6000):
        raise argparse.ArgumentTypeError("a page size is 640-2560 wide and 480-6000 tall")
    return w, h


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--manifest", help="the film's sketch.json (what is fetched goes beside it)")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--picture", metavar="URL", help="a picture's URL")
    what.add_argument("--page", metavar="URL", help="a web page to photograph")
    what.add_argument("--font", metavar="FAMILY", help="a Google Fonts family name")
    what.add_argument("--check", metavar="URL", help="may this URL be fetched; fetches nothing")
    ap.add_argument("--name", help="the picture's name (lowercase): SK.image('web_<name>')")
    ap.add_argument("--width", type=int, default=1600, help="an SVG's width in px (default 1600)")
    ap.add_argument("--size", type=size_arg, default=(1920, 1080), help="page: WxH (1920x1080)")
    ap.add_argument("--weights", default="400,700", help="font weights (default 400,700)")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen; fetch nothing")
    a = ap.parse_args()

    if a.check:
        ok, why = _web.public_url(a.check)
        host = urllib.parse.urlsplit(a.check).hostname
        addrs = ""
        if host:
            try:
                addrs = ", ".join(_web.addresses(host))
            except _web.NotPublic as e:
                addrs = str(e)
        print("%s  %s%s" % ("ok" if ok else "REFUSED", a.check, "" if ok else "  (%s)" % why))
        print("  resolves to: %s" % (addrs or "-"))
        return 0 if ok else 1

    if not a.manifest:
        ap.error("--manifest is required")
    mpath = _env.resolve(a.manifest)
    root = os.path.dirname(mpath)
    m = load_manifest(mpath)
    try:
        if a.font:
            try:
                weights = sorted({int(w) for w in a.weights.split(",") if w.strip()})
            except ValueError:
                raise GrabError("weights are numbers, like 400,700") from None
            if not weights or any(w not in range(100, 1000, 100) for w in weights):
                raise GrabError("font weights are 100..900 in hundreds")
            out = font(root, m, a.font.strip(), weights, a.dry_run)
        else:
            if not NAME.fullmatch(a.name or ""):
                raise GrabError("--name is lowercase letters, digits and _, starting with a letter")
            if a.picture:
                out = picture(
                    root, a.picture.strip(), a.name, max(64, min(a.width, 2560)), a.dry_run
                )
            else:
                out = page(root, a.page.strip(), a.name, a.size, a.dry_run)
            if "image" in out:
                m.setdefault("images", {})[out["image"]] = out["file"]
    except GrabError as e:
        print("web-grab: %s" % e, file=sys.stderr)
        return 2
    if a.dry_run:
        print("dry run: %s" % out["would"])
        return 0
    save_manifest(mpath, m)
    if "font" in out:
        miss = " (not on Google Fonts at %s)" % out["missing"] if out["missing"] else ""
        print(
            "font %r at weights %s%s: write with {font: %r, wt: %d}"
            % (out["font"], out["weights"], miss, out["font"], out["weights"][-1])
        )
    else:
        print(
            "%s %dx%d (%s%s): SK.image('%s', x, y, w). Read %s to see it."
            % (
                out["file"],
                out["w"],
                out["h"],
                out["kind"],
                ", transparent" if out.get("alpha") else "",
                out["image"],
                out["file"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
