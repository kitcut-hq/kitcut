#!/usr/bin/env python
"""What the map makers share: Web Mercator, OpenStreetMap's answers, and the pen.

Two scripts draw a real map for a film from OpenStreetMap's data: `route-map.py`
(a route on a paper relief map of a whole ride) and `place-map.py` (the streets
round one address, with the pin's place on it). They need the same four things,
and this is the one copy of each:

  * the pixel grid -- `Frame`: whole pixels at a (fractional) zoom covering a
    bbox, so a point's place on the picture is arithmetic, never a fit;
  * the fetchers -- `overpass()` (cached by the query's text; a busy server is
    retried on the next mirror) and `nominatim()` / `geocode()` (one request a
    second, cached), every answer kept on disk so a second run asks nobody;
  * the pen -- `_poly`, `_dashes`, `rgb`, `bgr8`: anti-aliased lines on an
    8-bit BGR image at sub-pixel positions;
  * `save_jpeg()`, which steps the quality down until the file fits the style's
    size limit.

Map data (c) OpenStreetMap contributors (ODbL): a film that shows a map made
with these credits OSM on it.
"""

import os
import sys
import json
import math
import time
import hashlib
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402, F401 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402

UA = "kitcut-route-map/1.0 (https://kitcut.ai)"


OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


GEOCODER = "https://nominatim.openstreetmap.org/search?%s"


EARTH_M = 6371008.8


def gx(lon, z):
    """Web Mercator x in pixels at zoom z (256 px tiles)."""
    return (lon + 180.0) / 360.0 * 256 * 2**z


def gy(lat, z):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 256 * 2**z


def lat_of(y, z):
    n = math.pi - 2 * math.pi * y / (256 * 2**z)
    return math.degrees(math.atan(math.sinh(n)))


def lon_of(x, z):
    return x / (256 * 2**z) * 360.0 - 180.0


def metres(a, b):
    """Great-circle distance between (lon, lat) points."""
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(h))


class Frame:
    """One map's pixel grid: whole pixels at zoom z covering bbox (w, s, e, n)."""

    def __init__(self, name, z, bbox):
        w, s, e, n = bbox
        self.name, self.z = name, z
        self.x0, self.y0 = math.floor(gx(w, z)), math.floor(gy(n, z))
        self.W = math.ceil(gx(e, z)) - self.x0
        self.H = math.ceil(gy(s, z)) - self.y0
        # the bounds the pixels really cover (a little wider than asked)
        self.bounds = (
            lon_of(self.x0, z),
            lat_of(self.y0 + self.H, z),
            lon_of(self.x0 + self.W, z),
            lat_of(self.y0, z),
        )
        self.m_per_px = 2 * math.pi * EARTH_M * math.cos(math.radians((s + n) / 2)) / (256 * 2**z)

    def px(self, lon, lat):
        return gx(lon, self.z) - self.x0, gy(lat, self.z) - self.y0

    def uv(self, lon, lat):
        x, y = self.px(lon, lat)
        return x / self.W, y / self.H


def _get(url, data=None, timeout=180):
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cached_json(path, fetch):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    doc = fetch()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return doc


def overpass(query, cache_dir, timeout=180):
    """An Overpass query, cached by its text. A busy server answers HTML, not
    JSON; that is retried on the next mirror rather than parsed. timeout: how
    long one try may take -- a few blocks of streets answer in seconds, so a
    small query gives up on a stuck server sooner than a whole ride's map."""
    key = hashlib.sha1(query.encode()).hexdigest()[:12]

    def fetch():
        last = None
        # the main server twice before the mirror, and the mirror on a short leash: on 2026-10-06
        # it accepted the connection and said nothing, and every turn it was given cost the full
        # three minutes while the main server was answering the same query in under a second
        for attempt, which in enumerate((0, 0, 1, 0, 1, 0)):
            try:
                body = _get(
                    OVERPASS[which],
                    urllib.parse.urlencode({"data": query}).encode(),
                    min(timeout, 45) if which else timeout,
                )
                return json.loads(body.decode("utf-8"))
            except Exception as e:  # noqa: BLE001 -- busy servers fail every way there is
                last = e
                print("  overpass busy (%s), retrying" % type(e).__name__)
                time.sleep(10 + 10 * attempt)
        sys.exit("Overpass did not answer: %s" % last)

    return cached_json(os.path.join(cache_dir, "osm-%s.json" % key), fetch)


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def blur(a, sigma):
    return cv2.GaussianBlur(a, (0, 0), sigma) if sigma > 0.05 else a


def _path_px(f, coords):
    return np.array([f.px(lon, lat) for lon, lat in coords], np.float64)


def _dashes(p, on, off):
    """A polyline cut into dash pieces of on/off pixels."""
    out, cur, left, drawing = [], [p[0]], on, True
    for a, b in zip(p, p[1:]):
        seg = b - a
        d = float(np.hypot(*seg))
        t = 0.0
        while d - t > left:
            t += left
            q = a + seg * (t / d)
            if drawing:
                cur.append(q)
                out.append(np.array(cur))
            cur = [q]
            drawing = not drawing
            left = off if not drawing else on
        left -= d - t
        if drawing:
            cur.append(b)
        else:
            cur = [b]
    if drawing and len(cur) > 1:
        out.append(np.array(cur))
    return out


def _poly(img, pts, color, w):
    if len(pts) < 2:
        return
    sh = 4
    p = np.round(pts * (1 << sh)).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(img, [p], False, color, max(1, int(round(w))), cv2.LINE_AA, sh)


def bgr8(h):
    c = (rgb(h) * 255).round().astype(int)
    return int(c[2]), int(c[1]), int(c[0])


def save_jpeg(bgr, path, style):
    q = style["jpeg_quality"]
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    while True:
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= style["max_bytes"] or q <= 70:
            return q
        q -= 4


def nominatim(params, cache_dir):
    """OSM's Nominatim answers to a search (a list, best first), cached by the search itself."""
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]

    def fetch():
        time.sleep(1.1)  # Nominatim's usage policy: at most one request a second
        return json.loads(
            _get(GEOCODER % urllib.parse.urlencode(params), timeout=30).decode("utf-8")
        )

    return cached_json(os.path.join(cache_dir, "geo-%s.json" % key), fetch)


def geocode(q, cache_dir, near=None):
    """A place name to (lon, lat) through OSM's Nominatim (one request a second, cached), biased
    to within ~60 km of `near` when given. [lat, lon] pairs pass straight through."""
    if isinstance(q, (list, tuple)) and len(q) == 2:
        return float(q[1]), float(q[0])
    q = str(q).strip()

    def ask(text):
        params = {
            "q": text,
            "format": "json",
            "limit": 5,
            "accept-language": "en",
            "addressdetails": 1,
        }
        if near:  # a bias, not a fence: the place a route goes to next is usually close
            d = 0.25
            params["viewbox"] = "%.4f,%.4f,%.4f,%.4f" % (
                near[0] - d,
                near[1] + d,
                near[0] + d,
                near[1] - d,
            )
        return nominatim(params, cache_dir)

    # "Rynok Square, Lviv" first answered the Rynok Square of Stryi, 60 km away -- whose address
    # says "Lviv Oblast". Of the answers, those whose town (city, town, village...) is the query's
    # last part win, then those whose address names it at all, then the nearest one
    parts = [p.strip() for p in q.split(",") if p.strip()]
    tries = [q] + ([parts[0] + " " + parts[-1], parts[0]] if len(parts) > 1 else [])
    town = parts[-1].lower() if len(parts) > 1 else ""
    keys = ("city", "town", "village", "municipality", "suburb", "city_district", "hamlet")
    for text in tries:
        got = ask(text)
        if not got:
            continue
        in_town = [
            g
            for g in got
            if town and town in {str((g.get("address") or {}).get(k, "")).lower() for k in keys}
        ]
        named = (
            in_town or [g for g in got if town and town in g.get("display_name", "").lower()] or got
        )
        if near:
            named.sort(key=lambda g: metres(near, (float(g["lon"]), float(g["lat"]))))
        best = (float(named[0]["lon"]), float(named[0]["lat"]))
        if near and metres(near, best) > 150_000:
            sys.exit(
                "%r is %d km from the place before it: give it as [lat, lon]"
                % (q, metres(near, best) / 1000)
            )
        return best
    sys.exit("no place called %r on OpenStreetMap: give it as [lat, lon]" % q)
