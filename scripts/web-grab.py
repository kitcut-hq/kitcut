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
import asyncio
import argparse
import tempfile
import contextlib
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


# what the page is made of, measured in the page itself: the fonts its text is set in, the colours
# of its text and of what it paints, its logo files, its words. Runs as one expression.
BRAND_JS = r"""
(() => {
  const hex = c => {
    const m = /rgba?\(([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:[,/ ]+([\d.]+))?/.exec(c || '');
    if (!m || (m[4] !== undefined && +m[4] < 0.5)) return null;
    return '#' + [m[1], m[2], m[3]].map(v => (+v | 0).toString(16).padStart(2, '0')).join('');
  };
  const seen = el => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && +cs.opacity > 0.05;
  };
  const isButton = e => e.tagName === 'BUTTON' || e.getAttribute('role') === 'button' ||
    /btn|button|cta/i.test(typeof e.className === 'string' ? e.className : '');
  const role = el => {
    const e = el.closest('h1,h2,h3,button,[role=button],a,nav,header,footer');
    if (!e) return 'text';
    const t = e.tagName.toLowerCase();
    if (/^h[1-3]$/.test(t)) return 'headings';
    if (isButton(e)) return 'buttons';
    if (t === 'nav' || t === 'header') return 'navigation';
    return t === 'a' ? 'links' : 'text';
  };
  const tally = (m, k, n, r) => {
    if (!k) return;
    const e = m[k] || (m[k] = {n: 0, roles: {}});
    e.n += n;
    e.roles[r] = (e.roles[r] || 0) + n;
  };
  const fonts = {}, ink = {}, fills = {};
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node, k = 0;
  while ((node = walk.nextNode()) && k < 6000) {
    const txt = node.textContent.trim(), el = node.parentElement;
    if (!txt || !el || !seen(el)) continue;
    k++;
    const cs = getComputedStyle(el), r = role(el), n = txt.length * parseFloat(cs.fontSize);
    tally(fonts, cs.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, ''), n, r);
    tally(ink, hex(cs.color), n, r);
  }
  const vw = innerWidth, vh = innerHeight;
  for (const el of document.querySelectorAll('body, body *')) {
    const c = hex(getComputedStyle(el).backgroundColor);
    if (!c) continue;
    const r = el.getBoundingClientRect();
    const area = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) *
      Math.max(0, Math.min(r.bottom, vh * 3) - Math.max(r.top, 0));
    if (area < 400) continue;
    const t = el.tagName.toLowerCase();
    const what = isButton(el) ? 'buttons' : t === 'body' ? 'page'
      : el.closest('header,nav') ? 'navigation' : 'panels';
    tally(fills, c, what === 'buttons' ? area * 20 : area, what);
  }
  const abs = u => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
  const logos = [];
  const add = (url, how, w, h, alt) => {
    url = abs(url);
    if (url && /^https?:/.test(url) && !logos.some(l => l.url === url))
      logos.push({url, how, w, h, alt: (alt || '').slice(0, 80)});
  };
  const sel = 'header img, nav img, a[href="/"] img, img[src*=logo i], img[alt*=logo i], ' +
    'img[class*=logo i], img[id*=logo i]';
  for (const img of document.querySelectorAll(sel))
    add(img.currentSrc || img.src, 'img', img.naturalWidth, img.naturalHeight, img.alt);
  // a logo drawn inline has no file: its markup, with the page's computed fills baked in (the
  // page's CSS does not travel with it). Wide enough not to be an icon, near the top, first two.
  const box = e => e.getBoundingClientRect();
  const inline = [...document.querySelectorAll(
    'header svg, nav svg, a[href="/"] svg, svg[class*=logo i], [class*=logo i] svg')]
    .filter(e => seen(e) && box(e).width >= 40 && box(e).top < 300)
    .sort((a, b) => box(a).top - box(b).top || box(a).left - box(b).left)
    .slice(0, 2).map(e => {
      const c = e.cloneNode(true), r = box(e);
      c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      if (!c.getAttribute('viewBox')) c.setAttribute('viewBox', `0 0 ${r.width} ${r.height}`);
      c.setAttribute('width', r.width);
      c.setAttribute('height', r.height);
      c.style.color = getComputedStyle(e).color;
      const dst = c.querySelectorAll('*');
      e.querySelectorAll('*').forEach((el, i) => {
        const k = getComputedStyle(el), d = dst[i];
        if (!d) return;
        if (k.fill && k.fill !== 'none') d.setAttribute('fill', k.fill);
        if (k.stroke && k.stroke !== 'none') d.setAttribute('stroke', k.stroke);
        if (k.opacity !== '1') d.setAttribute('opacity', k.opacity);
      });
      const label = e.getAttribute('aria-label') || (e.closest('a') || e).getAttribute('aria-label');
      return {w: Math.round(r.width), h: Math.round(r.height), label: (label || '').slice(0, 60),
        svg: new XMLSerializer().serializeToString(c).slice(0, 300000)};
    });
  for (const l of document.querySelectorAll('link[rel~=icon], link[rel=apple-touch-icon]'))
    add(l.href, l.rel, 0, 0, l.sizes && l.sizes.value);
  const og = document.querySelector('meta[property="og:image"]');
  if (og) add(og.content, 'og:image', 0, 0, '');
  const top = (m, n) => Object.entries(m).sort((a, b) => b[1].n - a[1].n).slice(0, n)
    .map(([k, v]) => ({value: k, share: v.n,
      roles: Object.entries(v.roles).sort((a, b) => b[1] - a[1]).map(x => x[0])}));
  const share = list => {
    const t = list.reduce((a, b) => a + b.share, 0) || 1;
    list.forEach(x => { x.share = Math.round(100 * x.share / t); });
    return list;
  };
  return {
    url: location.href,
    title: document.title,
    description: (document.querySelector('meta[name=description]') || {}).content || '',
    fonts: share(top(fonts, 6)),
    // per role, so a headline face is not lost under the body text's volume
    fonts_by_role: Object.fromEntries(['headings', 'text', 'buttons', 'navigation', 'links'].map(r => {
      const rows = Object.entries(fonts).filter(([, v]) => v.roles[r]).sort((a, b) => b[1].roles[r] - a[1].roles[r]);
      const t = rows.reduce((a, [, v]) => a + v.roles[r], 0) || 1;
      return [r, rows.slice(0, 2).map(([k, v]) => [k, Math.round(100 * v.roles[r] / t)])];
    }).filter(([, rows]) => rows.length)),
    webfonts: (() => { const o = {}; document.fonts.forEach(f => { if (f.status === 'loaded') (o[f.family.replace(/^["']|["']$/g, '')] ||= new Set()).add(f.weight); });
      return Object.entries(o).map(([k, w]) => k + ' ' + [...w].join('/')); })(),
    text_colours: share(top(ink, 6)),
    fills: share(top(fills, 8)),
    logos: logos.slice(0, 8),
    inline_svgs: inline,
    text: (document.body.innerText || '').slice(0, 30000),
  };
})()
"""


class _CDP:
    """Just enough of the DevTools protocol over one WebSocket: calls, and a handler per event."""

    def __init__(self, ws):
        self.ws, self.n, self.waiting, self.on, self.tasks = ws, 0, {}, {}, set()

    async def pump(self):
        import aiohttp

        async for msg in self.ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            d = json.loads(msg.data)
            if "id" in d:
                fut = self.waiting.pop(d["id"], None)
                if fut and not fut.done():
                    fut.set_result(d)
            elif d.get("method") in self.on:
                task = asyncio.ensure_future(self.on[d["method"]](d.get("params") or {}))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)

    async def call(self, method, params=None, timeout=30):
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.waiting[self.n] = fut
        await self.ws.send_str(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        d = await asyncio.wait_for(fut, timeout)
        if "error" in d:
            raise GrabError("the browser refused %s: %s" % (method, d["error"].get("message")))
        return d.get("result") or {}


async def _browse(url, size, settle_s=2.5, load_s=30):
    """Load `url` in headless Chromium at `size`, every request on the way checked against
    _web.public_url -- the page, its redirects and everything it loads: a request for an address
    that is not public fails. Returns (png bytes, BRAND_JS's facts, the requests refused)."""
    import aiohttp

    exe, prof = browser(), _profile_dir()
    env = dict(_env.ENV)
    if os.name != "nt":
        env["TMPDIR"] = prof
    flags = [
        "--headless",
        "--remote-debugging-port=0",
        "--user-data-dir=%s" % prof,
        "--window-size=%d,%d" % size,
        "--hide-scrollbars",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--mute-audio",
        "--lang=en-US",
        "--user-agent=%s" % _web.UA,
        "about:blank",
    ]
    proc = subprocess.Popen(
        [exe, *flags], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    refused, verdicts = [], {}

    async def allowed(u):
        host = urllib.parse.urlsplit(u).hostname or ""
        if host not in verdicts:
            verdicts[host] = (await asyncio.to_thread(_web.public_url, u))[0]
        return verdicts[host]

    try:
        port_file, t0 = os.path.join(prof, "DevToolsActivePort"), time.time()
        while not (os.path.exists(port_file) and os.path.getsize(port_file) > 0):
            if proc.poll() is not None or time.time() - t0 > 20:
                raise GrabError("the browser did not start")
            await asyncio.sleep(0.1)
        with open(port_file, encoding="utf-8") as f:
            port = int(f.readline().strip())
        async with aiohttp.ClientSession() as http:
            async with http.get("http://127.0.0.1:%d/json/list" % port) as r:
                tabs = await r.json()
            ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
            async with http.ws_connect(ws_url, max_msg_size=0) as ws:
                cdp = _CDP(ws)
                pump = asyncio.ensure_future(cdp.pump())
                loaded = asyncio.Event()

                async def paused(p):
                    u, rid = p["request"]["url"], p["requestId"]
                    ok = not u.startswith(("http:", "https:")) or await allowed(u)
                    if not ok:
                        refused.append(u)
                    with contextlib.suppress(GrabError, asyncio.TimeoutError):
                        if ok:
                            await cdp.call("Fetch.continueRequest", {"requestId": rid})
                        else:
                            await cdp.call(
                                "Fetch.failRequest",
                                {"requestId": rid, "errorReason": "AddressUnreachable"},
                            )

                async def on_load(_):
                    loaded.set()

                cdp.on = {"Fetch.requestPaused": paused, "Page.loadEventFired": on_load}
                await cdp.call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
                await cdp.call("Page.enable")
                await cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": size[0], "height": size[1], "deviceScaleFactor": 1, "mobile": False},
                )
                nav = await cdp.call("Page.navigate", {"url": url})
                if nav.get("errorText"):
                    raise GrabError("the browser could not open %s (%s)" % (url, nav["errorText"]))
                with contextlib.suppress(asyncio.TimeoutError):
                    # a page that never finishes loading is photographed as it stands
                    await asyncio.wait_for(loaded.wait(), load_s)
                await asyncio.sleep(settle_s)
                got = await cdp.call(
                    "Runtime.evaluate", {"expression": BRAND_JS, "returnByValue": True}
                )
                facts = got.get("result", {}).get("value") or {}
                shot = await cdp.call(
                    "Page.captureScreenshot",
                    {
                        "format": "png",
                        "clip": {"x": 0, "y": 0, "width": size[0], "height": size[1], "scale": 1},
                        "captureBeyondViewport": True,
                    },
                    timeout=60,
                )
                pump.cancel()
        return base64.b64decode(shot["data"]), facts, refused
    finally:
        proc.kill()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        shutil.rmtree(prof, ignore_errors=True)


def brand_lines(facts):
    """BRAND_JS's facts as a few lines for Claude."""

    def row(items):
        return (
            ", ".join(
                "%s %d%%%s"
                % (
                    x["value"],
                    x["share"],
                    " (%s)" % ", ".join(x["roles"][:3]) if x["roles"] else "",
                )
                for x in items
                if x.get("share", 0) >= 2
            )
            or "-"
        )

    lines = [
        "title: %s" % (facts.get("title") or "-")[:140],
        "fonts, by what they set: %s"
        % (
            "; ".join(
                "%s %s" % (r, ", ".join("%s %d%%" % (f, n) for f, n in rows))
                for r, rows in (facts.get("fonts_by_role") or {}).items()
            )
            or "-"
        ),
        "web fonts it loaded: %s (system-ui and -apple-system mean the reader's own system font)"
        % (", ".join(facts.get("webfonts") or []) or "none"),
        "text colours: %s" % row(facts.get("text_colours", [])),
        "painted colours (by area, buttons weighted up): %s" % row(facts.get("fills", [])),
    ]
    logos = [
        "%s (%s%s%s)"
        % (
            x["url"],
            x["how"],
            ", %dx%d" % (x["w"], x["h"]) if x.get("w") else "",
            ', "%s"' % x["alt"] if x.get("alt") else "",
        )
        for x in facts.get("logos") or []
    ]
    lines.append("logo and icon files: %s" % ("; ".join(logos) or "none found"))
    return lines


def page(root, url, name, size=(1920, 1080), dry=False):
    """The page as a browser sees it, into web/<name>.jpg (the manifest's web_<name>); what it is
    made of into web/<name>.json and its words into web/<name>.txt."""
    ok, why = _web.public_url(url)
    if not ok:
        raise GrabError(why)
    if dry:
        return {"would": "photograph %s at %dx%d into web/%s.jpg" % (url, size[0], size[1], name)}
    try:
        png, facts, refused = asyncio.run(_browse(url, size))
    except (OSError, asyncio.TimeoutError, StopIteration) as e:
        raise GrabError("the browser could not photograph %s: %s" % (url, e)) from None
    final = facts.get("url") or url
    if not _web.public_url(final)[0]:
        raise GrabError("%s led to %s, which is not on the public internet" % (url, final))
    im = Image.open(io.BytesIO(png)).convert("RGB")
    lo, hi = zip(*im.getextrema(), strict=True)
    if max(hi) - min(lo) < 8:
        raise GrabError("the page came out blank (%s): it may need a login or refuse robots" % url)
    d = os.path.join(root, "web")
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "jpg"):
        if os.path.exists(os.path.join(d, "%s.%s" % (name, ext))):
            os.remove(os.path.join(d, "%s.%s" % (name, ext)))
    im.save(os.path.join(d, name + ".jpg"), quality=90, optimize=True)
    text = facts.pop("text", "")
    # the logos the page draws inline, as pictures of their own: web/<name>_logo1.png ...
    extra, notes = {}, []
    work = tempfile.mkdtemp(prefix="wg-")
    try:
        for i, sv in enumerate(facts.pop("inline_svgs", None) or [], 1):
            key = "%s_logo%d" % (name, i)
            try:
                im = svg_raster(sv["svg"].encode("utf-8"), 1200, work)
            except GrabError:
                continue  # a sprite reference, or a mark that draws nothing out of its page
            path, w, h, _ = store(im, os.path.join(d, key))
            extra["web_" + key] = "web/" + os.path.basename(path)
            notes.append(
                "%s (SK.image('web_%s'), %dx%d%s)"
                % (extra["web_" + key], key, w, h, ', "%s"' % sv["label"] if sv["label"] else "")
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(d, name + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(facts | {"refused": refused}, f, indent=2, ensure_ascii=False)
    rel = "web/" + name + ".jpg"
    note_source(
        root, "web_" + name, url=url, final=final, kind="page", file=rel, w=size[0], h=size[1]
    )
    return {
        "image": "web_" + name,
        "file": rel,
        "w": size[0],
        "h": size[1],
        "kind": "page",
        "final": final,
        "facts": brand_lines(facts)
        + (
            ["drawn inline in its header, saved as pictures: %s" % "; ".join(notes)]
            if notes
            else []
        ),
        "extra": extra,
        "words": len(text.split()),
        "refused": len(refused),
    }


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
                m["images"].update(out.get("extra") or {})
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
    elif out["kind"] == "page":
        print(
            "%s %dx%d (the page %s): SK.image('%s', x, y, w). Read %s to see it; its words (%d) "
            "are in %s.txt. What it is made of, measured in the page:"
            % (
                out["file"],
                out["w"],
                out["h"],
                out["final"],
                out["image"],
                out["file"],
                out["words"],
                out["file"].rsplit(".", 1)[0],
            )
        )
        for line in out["facts"]:
            print("  " + line)
        if out["refused"]:
            print("  (%d requests to addresses off the public internet refused)" % out["refused"])
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
