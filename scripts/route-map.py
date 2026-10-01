#!/usr/bin/env python
"""A real map for a film, and the route on it as numbers a film can draw.

A kitcut.ai film that replays a ride the way Strava does -- a dot running along
the road, the line growing behind it, distance and climb counting up -- needs
two things its Claude cannot get for itself: a map of the real place, and the
route as coordinates that land exactly on that map. This makes both.

The map is a terrain map made of stacked paper: one sheet per elevation band
(real elevation, AWS Terrain Tiles), each casting a soft shadow, with the
streets, trails, parks, coast and piers of OpenStreetMap printed on top. It
carries no labels and no orange: the film adds its own labels in its own look,
and the route it draws must be the only warm line. Every colour and size is in
the style (`config/maps/*.json`), never here.

Several maps of one area can be made at different zooms -- an overview and a
sharper detail of the part the camera flies close to. They share Web Mercator,
so a detail drawn over its rectangle of the overview lines up pixel for pixel;
the data sheet says where that rectangle is. Route legs come from OSM way ids
(a named fire road, in order) or from a bike router between points, are
sampled every few metres for elevation, and are written as [u, v, ft, mi] rows:
u, v the point as fractions of the base map's width and height.

Outputs, under the manifest's `out`:
    <map>.jpg       each map, under the upload size limit
    route.md        the data sheet a film is given: maps, alignment, legs, places
    route.json      the same, for scripts
    preview.jpg     the base map with every leg drawn on it -- check this first

`--list` prices it without rendering: map sizes, tiles to fetch, each leg's
length and climb. `--preview` renders the maps at a quarter of their size.

Map data (c) OpenStreetMap contributors (ODbL); elevation from AWS Terrain
Tiles (USGS 3DEP and others). A film that shows the map credits OSM.

Invoke as:  python scripts/route-map.py --manifest projects/<id>/route-map.json [--list]
"""

import os
import sys
import json
import math
import time
import hashlib
import re
import argparse
import threading
import urllib.parse
import urllib.request
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402

import _project  # noqa: E402

ROOT = _env.ROOT
UA = "kitcut-route-map/1.0 (https://kitcut.ai)"
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
BIKE_ROUTER = "https://routing.openstreetmap.de/routed-bike/route/v1/driving/%s?overview=full&geometries=geojson"
# a route between places: by bike or on foot (routing.openstreetmap.de's OSRM profiles)
ROUTERS = {
    "bike": BIKE_ROUTER,
    "foot": "https://routing.openstreetmap.de/routed-foot/route/v1/driving/%s?overview=full&geometries=geojson",
}
GEOCODER = "https://nominatim.openstreetmap.org/search?%s"
# a route with no clock of its own is given one: this pace on the flat, slower uphill (each 1 % of
# grade costs SLOW_PER_PCT of the pace), a little faster down -- a replay then dwells on the climbs
PACE_KMH = {"bike": 20.0, "foot": 8.0}
SLOW_PER_PCT, DOWNHILL = 0.09, 1.25
EARTH_M = 6371008.8
NODATA = (
    -1000.0
)  # metres: the terrain set's "no data" is -32768; nothing on land or sea is this low
M_PER_FT, M_PER_MI = 0.3048, 1609.344


# ------------------------------------------------------------------ geometry


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


# --------------------------------------------------------------------- fetch


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


def overpass(query, cache_dir):
    """An Overpass query, cached by its text. A busy server answers HTML, not
    JSON; that is retried on the next mirror rather than parsed."""
    key = hashlib.sha1(query.encode()).hexdigest()[:12]

    def fetch():
        last = None
        for attempt in range(6):
            url = OVERPASS[attempt % len(OVERPASS)]
            try:
                body = _get(url, urllib.parse.urlencode({"data": query}).encode())
                return json.loads(body.decode("utf-8"))
            except Exception as e:  # noqa: BLE001 -- busy servers fail every way there is
                last = e
                print("  overpass busy (%s), retrying" % type(e).__name__)
                time.sleep(10 + 10 * attempt)
        sys.exit("Overpass did not answer: %s" % last)

    return cached_json(os.path.join(cache_dir, "osm-%s.json" % key), fetch)


def terrain(style, frames, cache):
    """The elevation mosaic (metres) covering every frame, at the style's
    terrain zoom, with its origin in that zoom's pixels."""
    # never finer than one zoom above the sharpest map: a long route's map is far out, and its
    # mosaic at z15 passed OpenCV's 32767-pixel limit
    tz = min(style["terrain"]["zoom"], max(math.ceil(f.z) + 1 for f in frames))
    url = style["terrain"]["url"]
    xs, ys = [], []
    for f in frames:
        k = 2.0 ** (tz - f.z)
        xs += [f.x0 * k, (f.x0 + f.W) * k]
        ys += [f.y0 * k, (f.y0 + f.H) * k]
    tx0, tx1 = int(min(xs) // 256) - 1, int(max(xs) // 256) + 1
    ty0, ty1 = int(min(ys) // 256) - 1, int(max(ys) // 256) + 1
    jobs = [(x, y) for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1)]

    def tile(z, x, y):
        p = os.path.join(cache, str(z), str(x), "%d.png" % y)
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            body = _get(url.format(z=z, x=x, y=y), timeout=60)
            part = "%s.%d.part" % (p, threading.get_ident())  # siblings share a parent tile
            with open(part, "wb") as f:
                f.write(body)
            try:
                os.replace(part, p)
            except OSError:  # another thread put it there first (Windows will not replace it)
                if not os.path.exists(p):
                    raise
                os.remove(part)
        a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
        return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768

    def one(xy):
        """A tile's elevation. Where the set has no data at this zoom it sends a flat black tile
        (-32768 m: around Lviv at z15, a whole row of them), so the tile is taken from the zoom
        above, up to three levels out, enlarged; the odd hole left is filled later."""
        x, y = xy
        e = tile(tz, x, y)
        k = 1
        while (e < NODATA).mean() > 0.5 and k <= 3:
            px, py, n = x >> k, y >> k, 256 >> k
            parent = tile(tz - k, px, py)
            ox, oy = (x - (px << k)) * n, (y - (py << k)) * n
            up = cv2.resize(
                parent[oy : oy + n, ox : ox + n], (256, 256), interpolation=cv2.INTER_CUBIC
            )
            e = np.where(e < NODATA, up, e)
            k += 1
        return xy, e

    mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    with cf.ThreadPoolExecutor(12) as ex:
        for (x, y), e in ex.map(one, jobs):
            mos[(y - ty0) * 256 : (y - ty0 + 1) * 256, (x - tx0) * 256 : (x - tx0 + 1) * 256] = e
    holes = mos < NODATA
    if holes.any():  # what no zoom had: the nearest elevation that is real
        from scipy import ndimage  # noqa: PLC0415 -- only a set with holes needs it

        idx = ndimage.distance_transform_edt(holes, return_distances=False, return_indices=True)
        mos = mos[tuple(idx)]
        print("terrain   %.2f%% had no data: filled from the nearest" % (100 * holes.mean()))
    return mos, tx0 * 256, ty0 * 256, tz


def elevation_at(mosaic, lon, lat):
    mos, ox, oy, tz = mosaic
    x, y = gx(lon, tz) - ox - 0.5, gy(lat, tz) - oy - 0.5
    i, j = int(math.floor(y)), int(math.floor(x))
    fy, fx = y - i, x - j
    a = mos[i : i + 2, j : j + 2]
    return float(
        a[0, 0] * (1 - fx) * (1 - fy)
        + a[0, 1] * fx * (1 - fy)
        + a[1, 0] * (1 - fx) * fy
        + a[1, 1] * fx * fy
    )


# --------------------------------------------------------------------- route


def chain_ways(ways, ids, start):
    """OSM ways in the given order, each turned to continue from the last."""
    by = {w["id"]: [(p["lon"], p["lat"]) for p in w["geometry"]] for w in ways}
    missing = [i for i in ids if i not in by]
    if missing:
        sys.exit("OSM has no way %s" % missing)
    pts = []
    at = tuple(start) if start else None
    for i in ids:
        g = by[i]
        if at is not None and metres(g[-1], at) < metres(g[0], at):
            g = g[::-1]
        if pts and metres(pts[-1], g[0]) > 25:
            sys.exit(
                "way %d does not join the one before it (%.0f m apart)" % (i, metres(pts[-1], g[0]))
            )
        pts += g[1:] if pts else g
        at = g[-1]
    return pts


def read_gpx(path):
    """A GPX track as (lon, lat, elevation or None, unix seconds or None) rows."""
    import xml.etree.ElementTree as ET
    from datetime import datetime

    out = []
    for _, el in ET.iterparse(path):
        if el.tag.rsplit("}", 1)[-1] != "trkpt":
            continue
        ele = t = None
        for c in el:
            tag = c.tag.rsplit("}", 1)[-1]
            if tag == "ele" and c.text:
                ele = float(c.text)
            elif tag == "time" and c.text:
                t = datetime.fromisoformat(c.text.strip().replace("Z", "+00:00")).timestamp()
        out.append((float(el.get("lon")), float(el.get("lat")), ele, t))
        el.clear()
    if not out:
        sys.exit("%s has no track points" % path)
    return out


def passes(pts, at, within_m):
    """Indices where the track comes nearest to `at`, one per pass within within_m."""
    d = [metres(p, at) for p in pts]
    out, i = [], 0
    while i < len(d):
        if d[i] < within_m:
            j = i
            while j < len(d) and d[j] < within_m:
                j += 1
            out.append(min(range(i, j), key=d.__getitem__))
            i = j
        else:
            i += 1
    return out


def leg_points(leg, cache_dir):
    """The leg as (lon, lat, elevation or None, seconds or None) rows."""
    r = leg["route"]
    if "gpx" in r:
        pts = read_gpx(_env.resolve(r["gpx"], _env.workspace()))
        near = r.get("near_m", 300)
        if r.get("from_near"):
            got = passes(pts, r["from_near"], near)
            if not got:
                sys.exit("the track never comes within %d m of from_near" % near)
            pts = pts[got[0] :]
        if r.get("to_near"):
            got = passes(pts, r["to_near"], near)
            if not got:
                sys.exit("the track never comes within %d m of to_near" % near)
            pts = pts[: got[-1] + 1]
        if r.get("start_at"):  # the pin itself, a few metres off the road the track ran on
            pts = [(r["start_at"][0], r["start_at"][1], pts[0][2], pts[0][3])] + pts
        if r.get("end_at"):
            pts = pts + [(r["end_at"][0], r["end_at"][1], pts[-1][2], pts[-1][3])]
        return pts
    if "osm_ways" in r:
        q = "[out:json][timeout:60];way(id:%s);out geom tags;" % ",".join(map(str, r["osm_ways"]))
        ways = overpass(q, cache_dir)["elements"]
        return [
            (lon, lat, None, None) for lon, lat in chain_ways(ways, r["osm_ways"], r.get("start"))
        ]
    if r.get("router") == "bike":
        coords = ";".join("%.7f,%.7f" % (lon, lat) for lon, lat in r["points"])
        key = hashlib.sha1(coords.encode()).hexdigest()[:12]
        doc = cached_json(
            os.path.join(cache_dir, "bike-%s.json" % key),
            lambda: json.loads(_get(BIKE_ROUTER % coords).decode("utf-8")),
        )
        if doc.get("code") != "Ok":
            sys.exit("the bike router refused %s: %s" % (leg["name"], doc.get("message")))
        return [(c[0], c[1], None, None) for c in doc["routes"][0]["geometry"]["coordinates"]]
    if "points" in r:
        return [(p[0], p[1], None, None) for p in r["points"]]
    sys.exit("leg %s: a route is gpx, osm_ways, router: bike, or points" % leg["name"])


def _gauss(a, sig):
    if sig <= 0.5:
        return a
    k = np.arange(-int(3 * sig), int(3 * sig) + 1)
    w = np.exp(-0.5 * (k / sig) ** 2)
    w /= w.sum()
    return np.convolve(np.pad(a, len(k) // 2, mode="edge"), w, mode="valid")


def on_ways(pts, ways, within_m=12.0):
    """Which of pts (lon, lat, ...) lie on any of ways (lists of (lon, lat)): within within_m of
    one of their segments."""
    lat0 = math.radians(sum(p[1] for p in pts) / len(pts))
    kx, ky = EARTH_M * math.cos(lat0) * math.pi / 180, EARTH_M * math.pi / 180
    P = np.array([[p[0] * kx, p[1] * ky] for p in pts])
    hit = np.zeros(len(P), bool)
    for w in ways:
        W = np.array([[q[0] * kx, q[1] * ky] for q in w])
        for a, b in zip(W, W[1:]):
            ab = b - a
            L2 = float(ab @ ab) or 1e-9
            t = np.clip(((P - a) @ ab) / L2, 0, 1)
            d = np.hypot(*(P - (a + t[:, None] * ab)).T)
            hit |= d < within_m
    return hit


def sample(pts, mosaic, step_m, smooth_m, source, decks=None):
    """The line every step_m metres: (lon, lat, metres along, elevation, seconds).
    Elevation is the track's own (source "track", when it has one) or the
    terrain's, smoothed along the line so noise is not counted as climb --
    drawn level across decks (bridges and tunnels), where the terrain is the
    water below or the hill above: the Golden Gate counted 900 ft of climb
    that no rider makes. Seconds are the track's clock from its first point,
    or None."""
    out = [(pts[0][0], pts[0][1], 0.0, pts[0][2], pts[0][3])]
    run = 0.0
    for a, b in zip(pts, pts[1:]):
        d = metres(a, b)
        if d < 1e-6:
            continue
        n = max(1, int(math.ceil(d / step_m)))
        for k in range(1, n + 1):
            t = k / n
            ele = None if a[2] is None or b[2] is None else a[2] + (b[2] - a[2]) * t
            sec = None if a[3] is None or b[3] is None else a[3] + (b[3] - a[3]) * t
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, run + d * t, ele, sec))
        run += d
    if source == "track" and all(p[3] is not None for p in out):
        ele = np.array([p[3] for p in out], np.float64)
    else:
        ele = np.array([elevation_at(mosaic, p[0], p[1]) for p in out], np.float64)
        if decks:  # the terrain under a bridge is the water, over a tunnel the hill: draw it level
            on = on_ways(out, decks)
            if on.any() and not on.all():
                idx = np.arange(len(ele))
                ele[on] = np.interp(idx[on], idx[~on], ele[~on])
    ele = _gauss(ele, smooth_m / step_m)
    t0 = out[0][4]
    return [
        (p[0], p[1], p[2], float(e), None if p[4] is None or t0 is None else p[4] - t0)
        for p, e in zip(out, ele)
    ]


def leg_stats(s):
    ele = np.array([p[3] for p in s])
    dist = np.array([p[2] for p in s])
    st = {
        "length_m": float(dist[-1]),
        "start_m": float(ele[0]),
        "end_m": float(ele[-1]),
        "min_m": float(ele.min()),
        "max_m": float(ele.max()),
        "gain_m": float(np.clip(np.diff(ele), 0, None).sum()),
        "loss_m": float(np.clip(-np.diff(ele), 0, None).sum()),
    }
    # steepest 200 m, the grade a rider feels rather than one noisy sample
    best, j = 0.0, 0
    for i in range(len(s)):
        while j < len(s) and dist[j] - dist[i] < 200:
            j += 1
        if j < len(s):
            best = max(best, (ele[j] - ele[i]) / (dist[j] - dist[i]) * 100)
    st["max_grade_pct"] = float(best)
    if s[-1][4] is not None:
        sec = np.array([p[4] for p in s])
        st["elapsed_s"] = float(sec[-1])
        # moving: time spent on steps covered faster than 1 m/s
        dd, dt = np.diff(dist), np.diff(sec)
        st["moving_s"] = float(dt[(dt > 0) & (dd / np.maximum(dt, 1e-6) > 1.0)].sum())
    return st


def keep(s, frame, tol_px, max_gap_m, must):
    """Which samples the data sheet keeps: the shape to within tol_px on the
    sharpest map (Douglas-Peucker), no gap longer than max_gap_m so the climb
    and the clock stay true between rows, and every index in must."""
    xy = np.array([frame.px(p[0], p[1]) for p in s])
    keep_ = np.zeros(len(s), bool)
    keep_[[0, -1]] = True
    stack = [(0, len(s) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, ab = xy[i], xy[j] - xy[i]
        L = float(np.hypot(*ab))
        seg = xy[i + 1 : j] - a
        if L < 1e-9:
            dist = np.hypot(seg[:, 0], seg[:, 1])
        else:
            dist = np.abs(seg[:, 0] * ab[1] - seg[:, 1] * ab[0]) / L
        k = int(np.argmax(dist))
        if dist[k] > tol_px:
            m = i + 1 + k
            keep_[m] = True
            stack += [(i, m), (m, j)]
    for i in must:
        keep_[i] = True
    idx = [int(i) for i in np.flatnonzero(keep_)]
    out = [idx[0]]
    for i in idx[1:]:
        while s[i][2] - s[out[-1]][2] > max_gap_m:
            nxt = out[-1] + 1
            while nxt < i and s[nxt][2] - s[out[-1]][2] < max_gap_m:
                nxt += 1
            out.append(nxt)
        out.append(i)
    return sorted(set(out))


def rows(s, base, idx, units, decimals=5):
    """[u, v, elevation, distance(, seconds)] for the kept samples. Four
    decimals put a point within a pixel of a 4000 px map."""
    to_e = (lambda x: x / M_PER_FT) if units == "imperial" else (lambda x: x)
    to_d = (lambda x: x / M_PER_MI) if units == "imperial" else (lambda x: x / 1000)
    out = []
    for i in idx:
        p = s[i]
        u, v = base.uv(p[0], p[1])
        r = [round(u, decimals), round(v, decimals), int(round(to_e(p[3]))), round(to_d(p[2]), 2)]
        if p[4] is not None:
            r.append(int(round(p[4])))
        out.append(r)
    return out


# ---------------------------------------------------------------------- draw


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def blur(a, sigma):
    return cv2.GaussianBlur(a, (0, 0), sigma) if sigma > 0.05 else a


def shift(a, dx, dy):
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        a, m, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )


def coast_chain(osm):
    """The longest coastline in the OSM answer, its ways joined end to end
    (OSM draws a coastline with the land on its left)."""
    ways = [
        [(g["lon"], g["lat"]) for g in e["geometry"]]
        for e in osm
        if e.get("tags", {}).get("natural") == "coastline" and "geometry" in e
    ]
    chains = []
    for w in ways:
        chains.append(list(w))
    merged = True
    while merged:
        merged = False
        for i in range(len(chains)):
            for j in range(len(chains)):
                if i != j and chains[i][-1] == chains[j][0]:
                    chains[i] += chains[j][1:]
                    del chains[j]
                    merged = True
                    break
            if merged:
                break
    if not chains:
        return None
    return max(chains, key=lambda c: sum(metres(a, b) for a, b in zip(c, c[1:])))


def sea_mask(f, chain, sea_at):
    """1 at sea, 0 on land, anti-aliased: the coastline closed round a rectangle
    far outside the frame, on whichever side holds sea_at."""
    if chain is None:
        return np.zeros((f.H, f.W), np.float32)
    p = _path_px(f, chain)
    big = max(f.W, f.H) * 3.0
    corners = [
        (-big, -big),
        (f.W + big, -big),
        (f.W + big, f.H + big),
        (-big, f.H + big),
    ]  # clockwise on screen

    def onto(pt):
        """The nearest point on the far rectangle, and its place round it (0..4)."""
        x, y = pt
        cands = [
            (abs(y + big), (min(max(x, -big), f.W + big), -big), 0 + (x + big) / (f.W + 2 * big)),
            (
                abs(f.W + big - x),
                (f.W + big, min(max(y, -big), f.H + big)),
                1 + (y + big) / (f.H + 2 * big),
            ),
            (
                abs(f.H + big - y),
                (min(max(x, -big), f.W + big), f.H + big),
                2 + (f.W + big - x) / (f.W + 2 * big),
            ),
            (
                abs(x + big),
                (-big, min(max(y, -big), f.H + big)),
                3 + (f.H + big - y) / (f.H + 2 * big),
            ),
        ]
        _, q, t = min(cands, key=lambda c: c[0])
        return q, t

    q_end, t_end = onto(p[-1])
    q_start, t_start = onto(p[0])
    sx, sy = f.px(*sea_at)
    best = None
    for direction in (1, -1):  # round the rectangle clockwise, then anticlockwise
        ring = [tuple(x) for x in p] + [q_end]
        span = ((t_start - t_end) if direction == 1 else (t_end - t_start)) % 4
        c = math.floor(t_end) + 1 if direction == 1 else math.ceil(t_end) - 1
        for _ in range(4):
            if (((c - t_end) if direction == 1 else (t_end - c)) % 4) >= span:
                break
            ring.append(corners[c % 4])
            c += direction
        ring.append(q_start)
        poly = np.round(np.array(ring) * 16).astype(np.int64)
        m = np.zeros((f.H, f.W), np.uint8)
        cv2.fillPoly(m, [poly.astype(np.int32).reshape(-1, 1, 2)], 255, cv2.LINE_AA, 4)
        inside = 0 <= sx < f.W and 0 <= sy < f.H and m[int(sy), int(sx)] > 127
        if inside or best is None:
            best = m
        if inside:
            break
    return best.astype(np.float32) / 255.0


def relief(f, mosaic, style, sea):
    """The paper layers, ocean and grain, as float RGB in 0..1. sea: the
    frame's sea mask -- the coastline decides the shore, never the terrain
    tiles, whose bathymetry here puts islands in the bay."""
    mos, ox, oy, tz = mosaic
    k = 2.0 ** (tz - f.z)
    xs = ((f.x0 + np.arange(f.W, dtype=np.float64) + 0.5) * k - ox - 0.5).astype(np.float32)
    ys = ((f.y0 + np.arange(f.H, dtype=np.float64) + 0.5) * k - oy - 0.5).astype(np.float32)
    mx, my = np.meshgrid(xs, ys)
    E = cv2.remap(mos, mx, my, cv2.INTER_CUBIC)
    del mx, my
    sc = 2.0 ** (f.z - 16)  # style sizes are at zoom 16
    E = blur(E, style["terrain"]["smooth_px"] / k)
    land_m = 1.0 - sea

    gyy, gxx = np.gradient(E)
    gyy /= f.m_per_px
    gxx /= f.m_per_px
    edge_w = np.maximum(np.hypot(gxx, gyy) * f.m_per_px, 0.05)  # metres per pixel across a contour

    # hillshade (light from the style's azimuth), used faintly inside each sheet
    hs_cfg = style["hillshade"]
    az, alt = math.radians(360 - hs_cfg["azimuth"] + 90), math.radians(hs_cfg["altitude"])
    slope = np.arctan(np.hypot(gxx, gyy))
    aspect = np.arctan2(-gyy, gxx)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip(hs, 0, 1).astype(np.float32)
    del slope, aspect, gxx, gyy

    land = style["land"]
    ocean = style["ocean"]
    sh = style["shadow"]
    dx, dy, bs, strength = sh["dx"] * sc, sh["dy"] * sc, sh["blur"] * sc, sh["strength"]
    rim = style["rim"]

    def sheet(img, a, col, shadow=1.0):
        cast = blur(shift(a, dx, dy), bs) * (1 - a)
        img *= (1 - strength * shadow * cast)[..., None]
        img = img * (1 - a[..., None]) + rgb(col) * a[..., None]
        lit = np.clip(a - shift(a, rim["px"] * sc, rim["px"] * sc), 0, 1) * rim["strength"]
        return img + (1 - img) * lit[..., None]

    # the sea: shelves of paper stepping out from the shore, the deepest underneath
    img = np.empty((f.H, f.W, 3), np.float32)
    img[:] = rgb(ocean["colors"][-1])
    off = cv2.distanceTransform((sea > 0.5).astype(np.uint8), cv2.DIST_L2, 5) * f.m_per_px
    for d, col in sorted(zip(ocean["bands_m"], ocean["colors"]), reverse=True):
        a = np.clip((d - off) / f.m_per_px + 0.5, 0, 1).astype(np.float32)
        img = sheet(img, a, col, ocean.get("shadow", 0.6))
    del off

    # the sheets follow this map's own heights: a whole map at 250-400 m (Lviv) was one sage colour
    # at 50 m a sheet; its lowest land is the first sheet and its highest the last, at a round step
    # (a coastal map from 0 to 650 m keeps the style's 50 m)
    on_land = E[land_m > 0.5]
    lo, hi = (
        (float(np.percentile(on_land, 1)), float(np.percentile(on_land, 99.5)))
        if on_land.size
        else (0.0, 1.0)
    )
    raw = max((hi - max(lo, 0.0)) / (len(land["colors"]) - 1), 1.0)
    step = min((k for k in (2, 5, 10, 20, 25, 50, 100, 200, 250, 500) if k >= raw), default=500)
    step = min(step, land["step_m"]) if lo < land["step_m"] else step
    base = max(0.0, math.floor(lo / step) * step)
    levels = [0.0] + [base + step * i for i in range(1, len(land["colors"]))]
    for i, lvl in enumerate(levels):
        if i and E.max() < lvl:
            break
        a = (
            land_m
            if i == 0
            else (np.clip((E - lvl) / edge_w + 0.5, 0, 1) * land_m).astype(np.float32)
        )
        if i == 0:  # the coast: a thin darker line where the land sheet ends
            line = np.clip(blur(a, ocean["shore_px"] * sc) - a, 0, 1) * 2.2
            img = img * (1 - line[..., None]) + rgb(ocean["shore"]) * line[..., None]
        img = sheet(img, a, land["colors"][i])

    shade = 1 - hs_cfg["strength"] * (1 - hs)[..., None] * land_m[..., None]
    img *= shade

    g = style["grain"]
    rng = np.random.default_rng(g["seed"])
    fine = blur(rng.standard_normal((f.H, f.W)).astype(np.float32), 0.8 * max(sc, 0.5))
    fine /= fine.std() + 1e-6
    coarse = blur(rng.standard_normal((f.H, f.W)).astype(np.float32), g["coarse_px"] * sc)
    coarse /= coarse.std() + 1e-6
    img *= (1 + g["fine"] * fine + g["coarse"] * coarse)[..., None]
    return np.clip(img, 0, 1)


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


def print_osm(img, f, osm, style):
    """Parks, the pier and the streets, on an 8-bit BGR image."""
    sc = 2.0 ** (f.z - 16)
    roads = style["roads"]
    named = [
        (name, re.compile(c["name_like"]), c["highway"])
        for name, c in roads["classes"].items()
        if "name_like" in c
    ]
    cls_of = {}
    for name, c in roads["classes"].items():
        if "name_like" not in c:
            for h in c["highway"]:
                cls_of[h] = name
    ways = {name: [] for name in roads["order"]}
    parks, piers = [], []
    W, H = f.W, f.H
    for e in osm:
        if e["type"] != "way" or "geometry" not in e:
            continue
        t = e.get("tags", {})
        p = _path_px(f, [(g["lon"], g["lat"]) for g in e["geometry"]])
        if (
            p[:, 0].max() < -50
            or p[:, 0].min() > W + 50
            or p[:, 1].max() < -50
            or p[:, 1].min() > H + 50
        ):
            continue
        if t.get("leisure") == "park":
            parks.append(p)
        elif t.get("man_made") == "pier":
            piers.append(p)
        elif t.get("highway"):
            hit = next(
                (n for n, rx, hw in named if t["highway"] in hw and rx.search(t.get("name", ""))),
                None,
            )
            hit = hit or cls_of.get(t["highway"])
            if hit in ways:
                ways[hit].append(p)

    pk = style["parks"]
    over = img.copy()
    for p in parks:
        if np.allclose(p[0], p[-1]) and len(p) > 3:
            cv2.fillPoly(
                over,
                [np.round(p * 16).astype(np.int32).reshape(-1, 1, 2)],
                bgr8(pk["color"]),
                cv2.LINE_AA,
                4,
            )
    cv2.addWeighted(over, pk["alpha"], img, 1 - pk["alpha"], 0, img)

    pr = style["pier"]
    for p in piers:
        if np.allclose(p[0], p[-1]) and len(p) > 3:
            q = np.round(p * 16).astype(np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(img, [q], bgr8(pr["color"]), cv2.LINE_AA, 4)
            cv2.polylines(img, [q], True, bgr8(pr["edge"]), 1, cv2.LINE_AA, 4)
        else:
            _poly(img, p, bgr8(pr["edge"]), pr["px"] * sc + 2)
            _poly(img, p, bgr8(pr["color"]), pr["px"] * sc)

    def width(x):
        return max(roads["min_w"], x * sc)

    for name in roads["order"]:  # casings, low classes first
        c = roads["classes"][name]
        if "case" in c:
            for p in ways[name]:
                _poly(img, p, bgr8(c["case"]), width(c["w"]) + 2 * width(c["case_w"]))
    for name in roads["order"]:
        c = roads["classes"][name]
        for p in ways[name]:
            if "dash" in c:
                on, off = (d * max(sc, 0.6) for d in c["dash"])
                for piece in _dashes(p, on, off):
                    _poly(img, piece, bgr8(c["fill"]), width(c["w"]))
            else:
                _poly(img, p, bgr8(c["fill"]), width(c["w"]))


def save_jpeg(bgr, path, style):
    q = style["jpeg_quality"]
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    while True:
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= style["max_bytes"] or q <= 70:
            return q
        q -= 4


# ---------------------------------------------------------------------- doc


def fmt_rows(r):
    return "[" + ",".join("[" + ",".join(str(x) for x in row) + "]" for row in r) + "]"


def hms(sec):
    sec = int(round(sec))
    return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60)


def write_doc(m, frames, base, legs, places, out_dir, units):
    unit_e, unit_d = ("ft", "mi") if units == "imperial" else ("m", "km")
    to_e = (lambda x: x / M_PER_FT) if units == "imperial" else (lambda x: x)
    to_d = (lambda x: x / M_PER_MI) if units == "imperial" else (lambda x: x / 1000)
    uploads = m.get("uploads", {})
    bname = uploads.get(base.name, base.name)
    L = ["# %s" % m.get("title", "Route data"), ""]
    L.append(
        "Real map pictures and the real route on them. Every position below is a fraction of "
        "the picture %s: on screen, x = mapX + u * mapW and y = mapY + v * mapH for the "
        "rectangle you draw it in. North is up. Draw the route from these numbers so it sits "
        "exactly on the roads; never redraw or guess the line." % bname
    )
    L += ["", "## The map pictures"]
    for f in frames:
        u0, v0 = base.uv(f.bounds[0], f.bounds[3])
        u1, v1 = base.uv(f.bounds[2], f.bounds[1])
        line = "- %s: %d x %d px, %.1f m per pixel" % (
            uploads.get(f.name, f.name),
            f.W,
            f.H,
            f.m_per_px,
        )
        if f is base:
            line += ", the whole area"
        else:
            line += (
                ", the same map at %.0fx the detail. Drawn over the rectangle u %.5f..%.5f, "
                "v %.5f..%.5f of %s it lines up with it exactly; draw it there whenever the camera "
                "is close, so the paper stays crisp"
                % (2.0 ** (f.z - base.z), u0, u1, v0, v1, bname)
            )
        L.append(line + ".")
    L.append(
        m.get(
            "map_note",
            "- No labels and no orange on the maps: label places yourself, in the film's own look.",
        )
    )
    if places:
        L += ["", "## Places (u, v)"]
        for p in places:
            u, v = base.uv(*p["at"])
            L.append(
                "- %s: %.5f, %.5f%s"
                % (p["name"], u, v, " -- " + p["note"] if p.get("note") else "")
            )
    for leg, s, st, r, marks in legs:
        L += ["", "## %s" % leg.get("title", leg["name"])]
        bits = [
            "%.1f %s" % (to_d(st["length_m"]), unit_d),
            "climbs %d %s and drops %d %s"
            % (to_e(st["gain_m"]), unit_e, to_e(st["loss_m"]), unit_e),
            "from %d %s, highest %d %s" % (to_e(st["start_m"]), unit_e, to_e(st["max_m"]), unit_e),
            "steepest 200 m %.0f%%" % st["max_grade_pct"],
        ]
        if "elapsed_s" in st:
            bits.append("ridden in %s (moving %s)" % (hms(st["elapsed_s"]), hms(st["moving_s"])))
        L.append("; ".join(bits) + ".")
        if leg.get("note"):
            L.append(leg["note"])
        cols = "u, v, elevation in %s, %s from the start" % (unit_e, unit_d)
        if r and len(r[0]) > 4:
            cols += ", seconds on the ride's own clock"
        L.append(
            "Rows are [%s]. Between rows the line is straight; interpolate distance, elevation and "
            "clock linearly along it." % cols
        )
        for name, at in marks:
            L.append(
                "- %s: row %s"
                % (name, ", then row ".join("%d (%.2f %s)" % (i, r[i][3], unit_d) for i in at))
            )
        L += ["", "const %s = %s;" % (leg["name"].upper(), fmt_rows(r))]
    L += [
        "",
        m.get(
            "credit",
            "Map data (c) OpenStreetMap contributors: credit it in small type wherever the map is on screen.",
        ),
    ]
    text = "\n".join(L) + "\n"
    with open(os.path.join(out_dir, "route.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def draw_preview(bgr, f, legs, places, path, scale):
    small = cv2.resize(bgr, (int(f.W * scale), int(f.H * scale)), interpolation=cv2.INTER_AREA)
    colors = [(0, 82, 252), (180, 60, 220), (40, 140, 40)]
    for i, (leg, s, st, r, marks) in enumerate(legs):
        p = np.array([[row[0] * f.W * scale, row[1] * f.H * scale] for row in r])
        _poly(small, p, (255, 255, 255), 6)
        _poly(small, p, colors[i % len(colors)], 3)
        for name, at in marks:
            for k in at:
                x, y = r[k][0] * f.W * scale, r[k][1] * f.H * scale
                cv2.circle(small, (int(x), int(y)), 5, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(small, (int(x), int(y)), 5, (30, 30, 30), 1, cv2.LINE_AA)
    for p in places:
        x, y = f.px(*p["at"])
        cv2.circle(small, (int(x * scale), int(y * scale)), 6, (20, 20, 20), -1, cv2.LINE_AA)
    cv2.imwrite(path, small, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ---------------------------------------------------------------------- film


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
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]

        def fetch():
            time.sleep(1.1)  # Nominatim's usage policy: at most one request a second
            return json.loads(
                _get(GEOCODER % urllib.parse.urlencode(params), timeout=30).decode("utf-8")
            )

        return cached_json(os.path.join(cache_dir, "geo-%s.json" % key), fetch)

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


def routed(points, mode, cache_dir):
    """A route along real roads and trails through points [(lon, lat)...], by bike or on foot."""
    coords = ";".join("%.6f,%.6f" % p for p in points)
    key = hashlib.sha1((mode + coords).encode()).hexdigest()[:12]
    doc = cached_json(
        os.path.join(cache_dir, "%s-%s.json" % (mode, key)),
        lambda: json.loads(_get(ROUTERS[mode] % coords, timeout=90).decode("utf-8")),
    )
    if doc.get("code") != "Ok":
        sys.exit(
            "the %s router found no route through those places: %s" % (mode, doc.get("message"))
        )
    return [(c[0], c[1], None, None) for c in doc["routes"][0]["geometry"]["coordinates"]]


def auto_frame(pts, name, margin_frac, margin_min_m, max_mp, max_zoom):
    """One map around the whole route: its extent plus a margin on every side (room for a camera
    that follows the dot to stay inside the map), at the sharpest zoom that stays under max_mp."""
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    w, e, s, n = min(lons), max(lons), min(lats), max(lats)
    mid = (s + n) / 2
    span_m = max(metres((w, mid), (e, mid)), metres((w, s), (w, n)), 1.0)
    pad = max(margin_frac * span_m, margin_min_m)
    dlat = pad / 111_320.0
    dlon = pad / (111_320.0 * math.cos(math.radians(mid)))
    bbox = [w - dlon, s - dlat, e + dlon, n + dlat]
    probe = Frame(name, 16, bbox)
    z = min(max_zoom, 16 + 0.5 * math.log2(max_mp * 1e6 / (probe.W * probe.H)))
    return Frame(name, round(z, 3), bbox), bbox


def synth_clock(s, mode):
    """Seconds for a route with no clock: PACE_KMH on the flat, slower up, faster down."""
    v0 = PACE_KMH[mode] / 3.6
    out, t = [0.0], 0.0
    for a, b in zip(s, s[1:]):
        d = b[2] - a[2]
        g = (b[3] - a[3]) / d * 100 if d > 0 else 0.0
        v = v0 / (1 + SLOW_PER_PCT * g) if g > 0 else min(v0 * DOWNHILL, v0 * (1 - 0.03 * g))
        t += d / max(v, 0.5)
        out.append(t)
    return [(p[0], p[1], p[2], p[3], c) for p, c in zip(s, out)]


def climb_marks(s):
    """The top (the highest point) and where the climb to it starts: the last point before the top
    within a tenth of the climb's height of the lowest point before it."""
    ele = np.array([p[3] for p in s])
    top = int(np.argmax(ele))
    if top == 0:
        return 0, 0
    low = float(ele[: top + 1].min())
    within = np.flatnonzero(ele[: top + 1] <= low + 0.1 * (ele[top] - low))
    return int(within[-1]), top


def film(spec, style, out_img, out_data, tile_cache, cache_dir):
    """A film's route: the map picture (out_img) and its data (out_data, SK.DATA.route), from a
    GPX or places routed along real roads and trails. Returns a short summary for the caller."""
    mode = spec.get("mode") or "bike"
    if mode not in ROUTERS:
        sys.exit("mode is %s" % " or ".join(ROUTERS))
    near = None
    if spec.get("gpx"):
        pts = read_gpx(spec["gpx"])
        near = pts[0][:2]
        for key, first in (("start_at", True), ("finish_at", False)):
            if spec.get(key):
                at = geocode(spec[key], cache_dir, near)
                got = passes(pts, at, spec.get("near_m", 400))
                if not got:
                    sys.exit(
                        "the track never comes within %d m of %s"
                        % (spec.get("near_m", 400), spec[key])
                    )
                pts = pts[got[0] :] if first else pts[: got[-1] + 1]
                pin = (at[0], at[1], pts[0 if first else -1][2], pts[0 if first else -1][3])
                pts = [pin] + pts if first else pts + [pin]
    elif spec.get("points"):
        places = []
        for q in spec["points"]:
            places.append(geocode(q, cache_dir, places[-1] if places else None))
        if len(places) < 2:
            sys.exit("a route needs two places at least")
        pts = routed(places, mode, cache_dir)
        near = places[0]
    else:
        sys.exit("give the route: gpx, or points (two places at least)")
    if len(pts) < 2:
        sys.exit("the route has fewer than two points")
    span = max(
        metres((min(p[0] for p in pts), pts[0][1]), (max(p[0] for p in pts), pts[0][1])),
        metres((pts[0][0], min(p[1] for p in pts)), (pts[0][0], max(p[1] for p in pts))),
    )
    if span > 400_000:
        sys.exit("the route spans %d km: is every place where it should be?" % (span / 1000))

    f, bbox = auto_frame(
        pts,
        spec.get("image") or "route_map",
        spec.get("margin", 0.25),
        spec.get("margin_min_m", 2000),
        spec.get("max_mp", 32),
        spec.get("max_zoom", 16.0),
    )
    mosaic = terrain(style, [f], tile_cache)
    w, s_, e, n = f.bounds
    bb = "%.5f,%.5f,%.5f,%.5f" % (s_, w, n, e)
    hw = "|".join(h for c in style["roads"]["classes"].values() for h in c["highway"])
    q = (
        '[out:json][timeout:180];(way["highway"~"^(%s)$"](%s);way["leisure"="park"](%s);'
        'way["man_made"="pier"](%s);way["natural"="coastline"](%s););out geom tags;'
        % (hw, bb, bb, bb, bb)
    )
    osm = overpass(q, cache_dir)["elements"]
    decks = [
        [(g["lon"], g["lat"]) for g in el["geometry"]]
        for el in osm
        if "geometry" in el
        and el.get("tags", {}).get("highway")
        and (
            el["tags"].get("bridge") not in (None, "no")
            or el["tags"].get("tunnel") not in (None, "no")
        )
    ]
    s = sample(pts, mosaic, 10, 40, "track" if spec.get("gpx") else "terrain", decks)
    timed = s[-1][4] is not None and s[-1][4] > 0
    if not timed:
        s = synth_clock(s, mode)
    st = leg_stats(s)
    climb, top = climb_marks(s)
    units = spec.get("units") or "metric"
    idx = keep(
        s, f, spec.get("tolerance_px", 3.0), spec.get("max_gap_m", 300), [0, climb, top, len(s) - 1]
    )
    rows_ = rows(s, f, idx, units, 4)
    pos = {i: k for k, i in enumerate(idx)}

    # the map: sea from the coastline (the deepest point the terrain knows, when it is below sea level)
    mos = mosaic[0]
    sea_at = None
    if float(mos.min()) < -5:
        iy, ix = np.unravel_index(int(np.argmin(mos)), mos.shape)
        sea_at = [lon_of(mosaic[1] + ix, mosaic[3]), lat_of(mosaic[2] + iy, mosaic[3])]
    coast = coast_chain(osm)
    img = relief(
        f,
        mosaic,
        style,
        sea_mask(f, coast, sea_at) if (coast and sea_at) else np.zeros((f.H, f.W), np.float32),
    )
    bgr = np.ascontiguousarray((img[..., ::-1] * 255).round().astype(np.uint8))
    del img
    print_osm(bgr, f, osm, style)
    os.makedirs(os.path.dirname(os.path.abspath(out_img)), exist_ok=True)
    save_jpeg(bgr, out_img, style)
    del bgr

    # places to label: the route's own, and any named ones that fall on the map
    named = []
    for q_ in spec.get("places") or []:
        lon, lat = geocode(q_, cache_dir, near)
        u, v = f.uv(lon, lat)
        if 0 <= u <= 1 and 0 <= v <= 1:
            named.append(
                {
                    "name": q_ if isinstance(q_, str) else "%.4f, %.4f" % tuple(q_),
                    "u": round(u, 4),
                    "v": round(v, 4),
                }
            )
        else:
            print("  %s is off the map: left out" % (q_,))
    to_e = (lambda x: x / M_PER_FT) if units == "imperial" else (lambda x: x)
    to_d = (lambda x: x / M_PER_MI) if units == "imperial" else (lambda x: x / 1000)
    loop = metres(pts[0], pts[-1]) < 300
    data = {
        "_about": "The route on its map (scripts/route-map.py --film): rows are [u, v, elevation, "
        "distance from the start, seconds on the route's clock], u and v fractions of the map picture. "
        "Map data (c) OpenStreetMap contributors.",
        "image": spec.get("image") or "route_map",
        "w": f.W,
        "h": f.H,
        "m_per_px": round(f.m_per_px, 3),
        # west, south, east, north: a film places any [lat, lon] on the map with Web Mercator
        "bounds": [round(x, 6) for x in f.bounds],
        "units": {
            "dist": "mi" if units == "imperial" else "km",
            "ele": "ft" if units == "imperial" else "m",
        },
        "timed": timed,
        "loop": loop,
        "rows": rows_,
        "marks": {"start": 0, "climb": pos[climb], "top": pos[top], "finish": len(rows_) - 1},
        "places": named,
        "stats": {
            "distance": round(to_d(st["length_m"]), 1),
            "gain": int(round(to_e(st["gain_m"]), -1)),
            "top": int(round(to_e(st["max_m"]))),
            "climb_gain": int(round(to_e(s[top][3] - s[climb][3]))),
            "climb_distance": round(to_d(s[top][2] - s[climb][2]), 1),
            "seconds": int(round(s[-1][4])),
        },
    }
    with open(out_data, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
    return {
        "map": "%s, %d x %d px, %.1f m a pixel" % (os.path.basename(out_img), f.W, f.H, f.m_per_px),
        "rows": len(rows_),
        "stats": data["stats"],
        "units": data["units"],
        "loop": loop,
        "timed": timed,
        "marks": data["marks"],
        "places": named,
        "bbox": [round(x, 5) for x in bbox],
    }


# ---------------------------------------------------------------------- main


def build_legs(m, frames, base, mosaic, cache_dir, units):
    sharp = max(frames, key=lambda f: f.z)
    legs = []
    for leg in m["legs"]:
        pts = leg_points(leg, cache_dir)
        s = sample(
            pts,
            mosaic,
            leg.get("sample_m", 10),
            leg.get("smooth_m", 40),
            leg.get("elevation", "track"),
        )
        st = leg_stats(s)
        found, must = [], []
        for mk in leg.get("marks", []):
            at = passes(s, mk["at"], mk.get("within_m", 120))
            if not at:
                sys.exit(
                    "leg %s never comes within %d m of the mark %r"
                    % (leg["name"], mk.get("within_m", 120), mk["name"])
                )
            found.append((mk["name"], at))
            must += at
        idx = keep(s, sharp, leg.get("tolerance_px", 2.0), leg.get("max_gap_m", 250), must)
        r = rows(s, base, idx, units, leg.get("decimals", 5))
        pos = {i: k for k, i in enumerate(idx)}
        marks = [(name, [pos[i] for i in at]) for name, at in found]
        legs.append((leg, s, st, r, marks))
        t = (
            " %s elapsed, %s moving" % (hms(st["elapsed_s"]), hms(st["moving_s"]))
            if "elapsed_s" in st
            else ""
        )
        print(
            "leg %-8s %5.2f km  %4.0f -> %4.0f m  +%4.0f / -%4.0f m  max %3.0f m  steepest %4.1f%%%s  %d rows, %d characters"
            % (
                leg["name"],
                st["length_m"] / 1000,
                st["start_m"],
                st["end_m"],
                st["gain_m"],
                st["loss_m"],
                st["max_m"],
                st["max_grade_pct"],
                t,
                len(r),
                len(fmt_rows(r)),
            )
        )
        for name, at in marks:
            print("    %-34s row %s" % (name, ", ".join("%d (%.2f)" % (k, r[k][3]) for k in at)))
    return legs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", help="a project's route-map.json")
    ap.add_argument(
        "--list", action="store_true", help="price it: sizes, tiles, legs; render nothing"
    )
    ap.add_argument(
        "--preview", action="store_true", help="render at a quarter size, to check the look"
    )
    ap.add_argument("--film", metavar="SPEC", help="a film's route (the studio's route tool)")
    ap.add_argument("--out-image", help="--film: where the map picture goes")
    ap.add_argument("--out-data", help="--film: where its data goes (SK.DATA.route)")
    ap.add_argument("--style", default="config/maps/paper-relief.json")
    ap.add_argument("--cache", help="where tiles and answers are kept (default: temp/)")
    _env.add_workspace_arg(ap)
    a = ap.parse_args()
    _env.set_workspace(a.workspace)
    if a.film:
        with open(a.film, encoding="utf-8") as f:
            spec = json.load(f)
        with open(_env.resolve(a.style), encoding="utf-8") as f:
            style = json.load(f)
        cache = a.cache or os.path.join(_env.workspace(), "temp")
        t0 = time.time()
        out = film(
            spec,
            style,
            a.out_image,
            a.out_data,
            os.path.join(cache, "terrain", "terrarium"),
            os.path.join(cache, "route-map"),
        )
        print("route-map --film ran in %.0f s" % (time.time() - t0))
        print(json.dumps(out))
        return
    if not a.manifest:
        ap.error("--manifest or --film")

    mpath = _env.resolve(a.manifest, _env.workspace())
    if not os.path.exists(mpath):  # a committed example lives with the tooling
        mpath = _env.resolve(a.manifest)
    with open(mpath, encoding="utf-8") as f:
        m = json.load(f)
    with open(_env.resolve(m.get("style", "config/maps/paper-relief.json")), encoding="utf-8") as f:
        style = json.load(f)
    pid = _project.project_id(m, mpath)
    out_dir = _env.resolve(m["out"], _env.workspace())
    cache_dir = os.path.join(_env.workspace(), "temp", "route-map")  # keyed by the query
    tile_cache = os.path.join(ROOT, "temp", "terrain", "terrarium")
    units = m.get("units", "imperial")

    full = [Frame(x["name"], x["zoom"], x["bbox"]) for x in m["maps"]]
    base_name = m.get("base", full[0].name)
    base_full = next(f for f in full if f.name == base_name)
    for f in full:
        mb = f.W * f.H / 1e6
        print(
            "%-9s z%-5g %5d x %-5d %5.1f MP  %.1f m/px%s"
            % (
                f.name,
                f.z,
                f.W,
                f.H,
                mb,
                f.m_per_px,
                "  !! over the studio's 40 MP limit" if mb > 40 else "",
            )
        )

    mosaic = terrain(style, full, tile_cache)
    print("terrain   %d x %d px at z%d" % (mosaic[0].shape[1], mosaic[0].shape[0], mosaic[3]))
    legs = build_legs(m, full, base_full, mosaic, cache_dir, units)
    places = m.get("places", [])
    if a.list:
        return

    frames = [Frame(x["name"], x["zoom"] - 2, x["bbox"]) for x in m["maps"]] if a.preview else full
    os.makedirs(out_dir, exist_ok=True)
    w, s_, e, n = (
        min(f.bounds[0] for f in frames),
        min(f.bounds[1] for f in frames),
        max(f.bounds[2] for f in frames),
        max(f.bounds[3] for f in frames),
    )
    bb = "%.5f,%.5f,%.5f,%.5f" % (s_, w, n, e)
    hw = "|".join(h for c in style["roads"]["classes"].values() for h in c["highway"])
    q = (
        '[out:json][timeout:180];(way["highway"~"^(%s)$"](%s);way["leisure"="park"](%s);'
        'way["man_made"="pier"](%s);way["natural"="coastline"](%s););out geom tags;'
        % (hw, bb, bb, bb, bb)
    )
    osm = overpass(q, cache_dir)["elements"]
    coast = coast_chain(osm)
    sea_at = m.get("sea_at") or [w, s_]
    print(
        "osm       %d ways, coastline %s"
        % (len(osm), "%d points" % len(coast) if coast else "none")
    )

    made = {}
    for f in frames:
        t0 = time.time()
        img = relief(f, mosaic, style, sea_mask(f, coast, sea_at))
        bgr = np.ascontiguousarray((img[..., ::-1] * 255).round().astype(np.uint8))
        del img
        print_osm(bgr, f, osm, style)
        path = os.path.join(out_dir, "%s%s.jpg" % (f.name, "-preview" if a.preview else ""))
        q_used = save_jpeg(bgr, path, style)
        made[f.name] = path
        print(
            "wrote     %s  %.1f MB (q%d, %.0f s)"
            % (path, os.path.getsize(path) / 1e6, q_used, time.time() - t0)
        )
        if f.name == base_name:
            draw_preview(
                bgr, f, legs, places, os.path.join(out_dir, "preview.jpg"), min(1.0, 1600 / f.H)
            )
        del bgr
    if a.preview:
        return

    doc = write_doc(m, full, base_full, legs, places, out_dir, units)
    data = {
        "maps": {
            f.name: {
                "file": os.path.basename(made[f.name]),
                "zoom": f.z,
                "w": f.W,
                "h": f.H,
                "bounds": f.bounds,
            }
            for f in full
        },
        "base": base_name,
        "legs": {
            leg["name"]: {"stats": st, "marks": dict(mk), "rows": r} for leg, s, st, r, mk in legs
        },
        "places": places,
    }
    with open(os.path.join(out_dir, "route.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    print("wrote     %s (%d characters)" % (os.path.join(out_dir, "route.md"), len(doc)))
    for name, path in made.items():
        _project.record(
            pid, "route map", out=path, script=__file__, kind="map", manifest=mpath, note=name
        )
    _project.record(
        pid,
        "route data",
        out=os.path.join(out_dir, "route.md"),
        script=__file__,
        kind="data",
        manifest=mpath,
    )


if __name__ == "__main__":
    main()
