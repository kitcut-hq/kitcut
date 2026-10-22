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
# A post on X is photographed through its embed page, which shows it whole and signed out (x.com
# itself asks for a login); the post is that page's one <article>
X_POST = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status(?:es)?/(\d{5,25})"
)
X_EMBED = "https://platform.twitter.com/embed/Tweet.html?id=%s&theme=light&dnt=true&lang=en"
CLIP_MARGIN = 24  # page px kept round the parts asked for (--keep)
CLIP_W = 1920  # a part is photographed at up to 2x, about this wide: sharp when the film zooms in
MAX_TALL = 6000  # px: the tallest photograph
MAX_BLOCKS = 200  # headings and paragraphs whose place in the photograph is written down


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


# A cookie or consent dialog over the page, accepted the way a reader would: the consent managers'
# own accept buttons first, then a button saying "Accept" (or "I agree", "Got it" ...) inside
# something that is about cookies or consent. Gallup's dialog covered the poll a research film
# showed (2026-10-21). Never a login, a paywall or a newsletter: those stay as they are.
CONSENT_JS = r"""
(() => {
  const done = [], shown = b => b && b.getClientRects().length > 0;
  const OWN = ['#onetrust-accept-btn-handler', '#accept-recommended-btn-handler',
    '#didomi-notice-agree-button', '.qc-cmp2-summary-buttons button[mode=primary]',
    '#truste-consent-button', '.fc-cta-consent', 'button[data-testid="uc-accept-all-button"]',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '#CybotCookiebotDialogBodyButtonAccept', '.cc-allow', '.cc-accept',
    '[data-cookiebanner="accept_button"]', '#gdpr-consent-accept'];
  for (const s of OWN) {
    const b = document.querySelector(s);
    if (shown(b)) { b.click(); done.push(s); }
  }
  if (done.length) return done;
  const SAYS = new RegExp('^(accept( all)?( cookies)?|accept and (close|continue)|' +
    'agree( and (close|continue))?|i agree|i accept|allow( all)?( cookies)?|got it|ok(ay)?|' +
    'i understand|yes,? i agree)$', 'i');
  const about = '[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],' +
    '[id*=gdpr i],[class*=gdpr i],[aria-label*=cookie i],[aria-label*=consent i],' +
    '[role=dialog],[aria-modal=true]';
  const buttons = 'button,a,[role=button],input[type=button],input[type=submit]';
  for (const root of document.querySelectorAll(about)) {
    if (root.matches('[role=dialog],[aria-modal=true]') &&
        !/cookie|consent|privacy/i.test(root.textContent.slice(0, 3000))) continue;
    for (const b of root.querySelectorAll(buttons)) {
      const t = (b.innerText || b.value || '').trim().replace(/\s+/g, ' ');
      if (t.length <= 40 && SAYS.test(t) && shown(b)) {
        b.click(); done.push('"' + t + '"'); return done;
      }
    }
  }
  return done;
})()
"""

# What is still over the page after that, when it is about cookies or consent (a consent manager
# drawn in a frame of its own, which the page's script cannot reach): hidden, and the page scrolls
# again. A full-window veil with no words of its own goes with it.
UNVEIL_JS = r"""
(() => {
  const vw = innerWidth, vh = innerHeight, gone = [], veils = [];
  const over = el => {
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    return w * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh);
  };
  const CMP = /cookie|consent|gdpr|cmp|sourcepoint|trustarc|didomi|onetrust|usercentrics/i;
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky' || cs.display === 'none') continue;
    const a = over(el);
    if (a < 0.12) continue;
    const cls = typeof el.className === 'string' ? el.className : '';
    const name = [el.id, cls, el.tagName === 'IFRAME' ? el.src : ''].join(' ');
    if (CMP.test(name) || /cookie|consent/i.test((el.textContent || '').slice(0, 3000))) {
      el.style.setProperty('display', 'none', 'important');
      gone.push((el.id || el.tagName.toLowerCase()).slice(0, 40));
    } else if (a > 0.85 && (el.innerText || '').trim().length < 20) veils.push(el);
  }
  if (gone.length) {
    for (const el of veils) el.style.setProperty('display', 'none', 'important');
    for (const e of [document.documentElement, document.body]) {
      e.style.setProperty('overflow', 'visible', 'important');
      if (getComputedStyle(e).position === 'fixed') {
        e.style.setProperty('position', 'static', 'important');
      }
    }
  }
  return gone;
})()
"""

# The parts of the page asked for (--keep): a CSS selector each, or "text=<words on the page>" for
# the smallest block holding them. mode 'find' scrolls the first into view (its pictures load);
# 'box' is the box round all of them, in the page's own px (x, y from the page's top-left).
PICK_JS = r"""
((sels, mode) => {
  const seen = e => { const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  // a header pinned to the window is drawn wherever the window is: never the part to keep
  const pinned = e => {
    for (let a = e; a && a !== document.body; a = a.parentElement) {
      const p = getComputedStyle(a).position;
      if (p === 'fixed' || p === 'sticky') return true;
    }
    return false;
  };
  const flat = s => (s || '').toLowerCase().replace(/\s+/g, ' ');
  const pick = s => {
    if (s.startsWith('text=')) {
      // the smallest block holding the words (a paragraph, a cell, a heading), not a word's span
      const want = flat(s.slice(5).trim());
      let best = null, size = Infinity;
      for (const el of document.querySelectorAll('body *')) {
        if (!flat(el.textContent).includes(want) || !seen(el)) continue;
        if (getComputedStyle(el).display.startsWith('inline') || pinned(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.width * r.height < size) { best = el; size = r.width * r.height; }
      }
      return best;
    }
    try { return [...document.querySelectorAll(s)].find(e => seen(e) && !pinned(e)) || null; }
    catch (e) { return null; }
  };
  const els = sels.map(pick), got = els.filter(Boolean), missing = sels.filter((s, i) => !els[i]);
  if (mode === 'find') {
    if (got.length) got[0].scrollIntoView({ block: 'start' });
    return { missing, n: got.length };
  }
  scrollTo(0, 0); // back to the top: a header pinned to the window is drawn there, over nothing
  if (!got.length) return { missing };
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of got) {
    const r = e.getBoundingClientRect();
    x0 = Math.min(x0, r.left + scrollX); y0 = Math.min(y0, r.top + scrollY);
    x1 = Math.max(x1, r.right + scrollX); y1 = Math.max(y1, r.bottom + scrollY);
  }
  // what is pinned to the window and lies over the kept parts (a header that shrank and stayed) is
  // hidden for the photograph, unless it is one of them
  for (const el of document.querySelectorAll('body *')) {
    const p = getComputedStyle(el).position;
    if (p !== 'fixed' && p !== 'sticky') continue;
    if (got.some(k => k.contains(el) || el.contains(k))) continue;
    const r = el.getBoundingClientRect();
    if (r.right + scrollX > x0 && r.left + scrollX < x1 && r.bottom + scrollY > y0 &&
        r.top + scrollY < y1) el.style.setProperty('visibility', 'hidden', 'important');
  }
  const d = document.documentElement;
  const doc = [Math.max(d.scrollWidth, innerWidth), Math.max(d.scrollHeight, innerHeight)];
  return { missing, box: [x0, y0, x1 - x0, y1 - y0], doc };
})
"""

# Where the page's headings and paragraphs are in the photograph (its px): what a film needs to push
# the camera onto the line it reads (SK.read's focus boxes) without guessing from the picture.
BLOCKS_JS = r"""
((cx, cy, cw, ch, s, most) => {
  const out = [], kinds = 'h1,h2,h3,h4,p,li,blockquote,figcaption,td,th,time,dd,dt,pre';
  for (const el of document.querySelectorAll(kinds)) {
    const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
    if (t.length < 3 || el.querySelector('p,li,h1,h2,h3,h4,blockquote,td')) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const x = r.left + scrollX - cx, y = r.top + scrollY - cy;
    if (x + r.width <= 0 || y + r.height <= 0 || x >= cw || y >= ch) continue;
    const box = [x, y, r.width, r.height].map(v => Math.round(v * s));
    out.push({ tag: el.tagName.toLowerCase(), text: t.slice(0, 140), box });
    if (out.length >= most) break;
  }
  return out;
})
"""


def clip_of(box, doc_w, doc_h):
    """The part of a page to photograph round `box` (x, y, w, h in the page's px): CLIP_MARGIN round
    it, inside the page, at a scale that makes it about CLIP_W wide (1x-2x) and no larger than
    MAX_SIDE x MAX_TALL. -> DevTools' clip {x, y, width, height, scale}."""
    x, y, w, h = box
    x0, y0 = max(0, x - CLIP_MARGIN), max(0, y - CLIP_MARGIN)
    x1, y1 = min(doc_w, x + w + CLIP_MARGIN), min(doc_h, y + h + CLIP_MARGIN)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    s = min(max(1.0, min(2.0, CLIP_W / w)), MAX_SIDE / w)
    h = min(h, MAX_TALL / s)
    return {"x": round(x0), "y": round(y0), "width": round(w), "height": round(h), "scale": s}


def trim(im, more, pad=16, tol=10):
    """A crop with the page's plain ground cut from round it (an X post's empty card below its
    replies): to what differs from the corner's colour, `pad` px kept. The blocks move with it."""
    from PIL import ImageChops  # noqa: PLC0415

    bg = Image.new("RGB", im.size, im.getpixel((0, 0)))
    box = (
        ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > tol else 0).getbbox()
    )
    if not box:
        return im
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(im.width, box[2] + pad), min(im.height, box[3] + pad)
    if (x1 - x0) * (y1 - y0) > 0.96 * im.width * im.height:
        return im
    for b in more.get("blocks") or []:
        b["box"][0] -= x0
        b["box"][1] -= y0
    return im.crop((x0, y0, x1, y1))


def page_url(url):
    """The address a page is photographed at: an X post through its embed page (and its <article>
    kept), anything else as it is. -> (url, keep)."""
    m = X_POST.match(url)
    if m:
        return X_EMBED % m.group(1), ["article"]
    return url, []


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


async def _browse(url, size, keep=(), settle_s=2.5, load_s=30):
    """Load `url` in headless Chromium at `size`, every request on the way checked against
    _web.public_url -- the page, its redirects and everything it loads: a request for an address
    that is not public fails. A cookie dialog is accepted (CONSENT_JS, UNVEIL_JS); `keep` (selectors
    or text=...) crops the photograph to those parts (clip_of). Returns (png bytes, BRAND_JS's
    facts, the requests refused, {consent, hidden, missing, clip, blocks})."""
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
                    host = urllib.parse.urlsplit(u).hostname or ""
                    say = {}
                    if ok and _web.ua_for(host) != _web.UA:  # a site that asks robots to say so
                        heads = {
                            k: v
                            for k, v in (p["request"].get("headers") or {}).items()
                            if k.lower() != "user-agent"
                        }
                        heads["User-Agent"] = _web.ua_for(host)
                        say = {"headers": [{"name": k, "value": v} for k, v in heads.items()]}
                    with contextlib.suppress(GrabError, asyncio.TimeoutError):
                        if ok:
                            await cdp.call("Fetch.continueRequest", {"requestId": rid, **say})
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

                async def js(expr):
                    got = await cdp.call(
                        "Runtime.evaluate", {"expression": expr, "returnByValue": True}
                    )
                    return got.get("result", {}).get("value")

                more = {"consent": await js(CONSENT_JS) or []}
                if more["consent"]:
                    await asyncio.sleep(1.5)  # the dialog closes, the page settles under it
                more["hidden"] = await js(UNVEIL_JS) or []
                sels = json.dumps(list(keep))
                clip = {"x": 0, "y": 0, "width": size[0], "height": size[1], "scale": 1}
                if keep:
                    found = await js("%s(%s, 'find')" % (PICK_JS, sels)) or {}
                    if found.get("n"):
                        await asyncio.sleep(1.2)  # what scrolling into view started loading
                    await js("%s(%s, 'box')" % (PICK_JS, sels))  # scrolls back to the top
                    await asyncio.sleep(0.6)  # a header that shrank on the way down grows back
                    got = await js("%s(%s, 'box')" % (PICK_JS, sels)) or {}
                    more["missing"] = got.get("missing") or []
                    if got.get("box"):
                        clip = clip_of(got["box"], *got["doc"])
                facts = await js(BRAND_JS) or {}
                more["clip"] = clip
                more["blocks"] = (
                    await js(
                        "%s(%s, %s, %s, %s, %s, %d)"
                        % (
                            BLOCKS_JS,
                            clip["x"],
                            clip["y"],
                            clip["width"],
                            clip["height"],
                            clip["scale"],
                            MAX_BLOCKS,
                        )
                    )
                    or []
                )
                shot = await cdp.call(
                    "Page.captureScreenshot",
                    {"format": "png", "clip": clip, "captureBeyondViewport": True},
                    timeout=60,
                )
                pump.cancel()
        return base64.b64decode(shot["data"]), facts, refused, more
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


def page(root, url, name, size=(1920, 1080), dry=False, keep=()):
    """The page as a browser sees it, into web/<name>.jpg (the manifest's web_<name>); what it is
    made of, and where its headings and paragraphs are in the photograph, into web/<name>.json and
    its words into web/<name>.txt. keep: the parts to crop it to (selectors, or text=...)."""
    asked = url
    url, own = page_url(url)
    keep = [str(k).strip() for k in keep or own if str(k).strip()][:8]
    ok, why = _web.public_url(url)
    if not ok:
        raise GrabError(why)
    if dry:
        return {
            "would": "photograph %s at %dx%d into web/%s.jpg%s"
            % (url, size[0], size[1], name, ", cropped to %s" % " + ".join(keep) if keep else "")
        }
    try:
        png, facts, refused, more = asyncio.run(_browse(url, size, keep))
    except (OSError, asyncio.TimeoutError, StopIteration) as e:
        raise GrabError("the browser could not photograph %s: %s" % (url, e)) from None
    final = facts.get("url") or url
    if not _web.public_url(final)[0]:
        raise GrabError("%s led to %s, which is not on the public internet" % (url, final))
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if keep:
        im = trim(im, more)
    im_size = im.size
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
    blocks, clip = more.get("blocks") or [], more["clip"]
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(
            facts | {"refused": refused, "clip": clip, "blocks": blocks},
            f,
            indent=2,
            ensure_ascii=False,
        )
    rel, (w, h) = "web/" + name + ".jpg", im_size
    note_source(
        root,
        "web_" + name,
        url=asked,
        final=final,
        kind="page",
        file=rel,
        w=w,
        h=h,
        **({"keep": keep} if keep else {}),
    )
    told = []
    if more.get("consent"):
        told.append("a cookie dialog was accepted (%s)" % ", ".join(more["consent"][:2]))
    if more.get("hidden"):
        told.append("a cookie dialog it could not answer was hidden (%s)" % more["hidden"][0])
    if keep and clip["scale"] == 1 and (clip["width"], clip["height"]) == tuple(size):
        told.append(
            "none of %s is on the page: this is the whole window; Read %s.txt for its words"
            % (" + ".join(keep), rel.rsplit(".", 1)[0])
        )
    elif keep:
        told.append(
            "cropped to %s at %gx%s"
            % (
                " + ".join(k for k in keep if k not in (more.get("missing") or [])),
                round(clip["scale"], 2),
                " (not on the page: %s)" % ", ".join(more["missing"])
                if more.get("missing")
                else "",
            )
        )
    if blocks:
        told.append(
            'where its %d headings and paragraphs are in the photograph (px): %s.json, "blocks" '
            "-- the boxes SK.read's focus takes" % (len(blocks), rel.rsplit(".", 1)[0])
        )
    return {
        "image": "web_" + name,
        "file": rel,
        "w": w,
        "h": h,
        "kind": "page",
        "final": final,
        "told": told,
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
    ap.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="SEL",
        help="page: crop to this part (a CSS selector, or text=<words on the page>); repeatable: "
        "the box round all of them (header + h1: the masthead down to the headline)",
    )
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
                out = page(root, a.page.strip(), a.name, a.size, a.dry_run, a.keep)
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
        for line in out["told"] + out["facts"]:
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
