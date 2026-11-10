#!/usr/bin/env python
"""A real street map of the place a film names, and where on it the address is.

A film that says "find us at 12 Oak Lane" and then shows a map owes its viewer
the real one: the people it is for live there, and a ruled grid with a pin on it
reads as a fake the moment they look for their own street. This makes the real
map from OpenStreetMap -- the streets, buildings, parks and water of the few
blocks round one address -- and says exactly where on the picture the address
is, which street it stands on, and where each street's name can be lettered.

The picture carries no lettering and no pin. The film letters the street names
in its own type (the data sheet gives each name a spot on a straight stretch of
its street, and the angle the street runs at) and drops its own pin, so the map
sits in the film's look; `tone` (light or dark), `tint` (the film's own colour,
which every surface leans toward) and `colors` (any surface outright) are what
make it the film's. Every colour and width is in the style
(`config/maps/street.json`), widths in metres on the ground.

How well the address was found is part of the answer, never hidden:
    house   the address itself is on OpenStreetMap: the pin is the house
    block   the street is, the number is not, and the US Census address ranges
            place it along the street: right to within a house or two
    street  only the street is known: the pin marks the street, not a house
    place   a named place (a venue, a park, a building)
    point   the [lat, lon] given
An address whose street is not on the map at all is refused: a pin on bare land
is a worse lie than no map.

Outputs:
    <image>.jpg     the map, a square of `px` pixels, the address at its centre
    <data>.json     SK.DATA.place: the pin (u, v fractions of the picture), its
                    street as lines, the street names with their spots, parks
                    and water with names, bounds, metres a pixel
                    (each with spare spots, for a film that frames the map its own way)
    preview.jpg     (--manifest, or --out-preview) the map with the pin and the
                    names drawn on it -- check this first

`--list` prices it without drawing: what the address matched and how well, the
map's size and scale, and what OpenStreetMap has there.

Map data (c) OpenStreetMap contributors (ODbL). A film that shows the map
credits OpenStreetMap on it.

Invoke as:  python scripts/place-map.py --at "<address>" --list
            python scripts/place-map.py --manifest projects/<id>/place-map.json [--list]
"""

import os
import re
import sys
import json
import math
import time
import hashlib
import argparse
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import _project  # noqa: E402
from _map import (  # noqa: E402 -- the grid, the fetchers and the pen route-map.py shares
    EARTH_M,
    Frame,
    _dashes,
    _get,
    _poly,
    bgr8,
    cached_json,
    gx,
    gy,
    lat_of,
    lon_of,
    metres,
    nominatim,
    overpass,
    rgb,
    save_jpeg,
)

ROOT = _env.ROOT
STYLE = "config/maps/street.json"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?%s"
# "Apt 4", "#12", "Suite 200": the map knows the building, never the door
UNIT = re.compile(r",?\s*(?:#\s*|\b(?:apt|apartment|unit|suite|ste)\b\.?\s*#?\s*)[\w-]+", re.I)
HOUSE_NO = re.compile(r"^\s*\d+[A-Za-z]?(?:-\d+)?\s+")
LATLON = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
HOW = {
    "house": "the address itself is on OpenStreetMap: the pin is the house",
    "block": "OpenStreetMap has the street, and the number is placed along it from its address "
    "range: the pin is right to within a house or two, and stands on the street",
    "street": "OpenStreetMap has the street but not the number: the pin marks the street, not a "
    "house -- letter the street, never point at one house",
    "place": "the pin is the named place",
    "point": "the pin is the [lat, lon] given",
}
GREEN = {
    "leisure": {
        "park",
        "garden",
        "golf_course",
        "pitch",
        "playground",
        "nature_reserve",
        "dog_park",
        "common",
    },
    "landuse": {
        "grass",
        "forest",
        "meadow",
        "recreation_ground",
        "cemetery",
        "village_green",
        "orchard",
        "allotments",
    },
    "natural": {"wood", "scrub", "grassland", "heath", "wetland"},
}
SAND = {"beach", "sand"}
WATER_USE = {"reservoir", "basin"}


class NoPlace(Exception):
    """The address cannot be put on the map truthfully; str() says why and what to give instead."""


# -------------------------------------------------------------------- locate


def _precision(g):
    """How exactly a Nominatim answer names a spot: house, block, place, street -- or None (a
    town). A house number that answers as a "place/house" on a WAY is not a mapped house: the way
    is the street, and the number was placed along it from its address range."""
    rank = int(g.get("place_rank") or 0)
    if rank >= 28:
        if not (g.get("address") or {}).get("house_number"):
            return "place"
        ranged = (
            g.get("class") == "place" and g.get("type") == "house" and g.get("osm_type") == "way"
        )
        return "block" if ranged else "house"
    if rank in (26, 27):
        return "street"
    return None


def _pick(q, got):
    """Of Nominatim's answers, the one that is in the town the query names (its words after the
    first comma: "Stuart, FL 34997" must not answer Stuart, Iowa), then the most exact."""
    words = {w for part in q.lower().split(",")[1:] for w in re.findall(r"[a-z]{2,}|\d{4,}", part)}
    best = None
    for i, g in enumerate(got):
        kind = _precision(g)
        if not kind:
            continue
        hay = "%s %s" % (
            g.get("display_name", ""),
            " ".join(str(v) for v in (g.get("address") or {}).values()),
        )
        hit = len(words & set(re.findall(r"[a-z]{2,}|\d{4,}", hay.lower())))
        if words and not hit:
            continue
        key = (hit, {"house": 4, "block": 3, "place": 2, "street": 1}[kind], -i)
        if best is None or key > best[0]:
            best = (key, g)
    return best[1] if best else None


def census(address, cache_dir):
    """A US street address to (lon, lat, matched) by the Census Bureau's address ranges, or None:
    a second opinion that is never allowed to fail the map."""
    params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    try:
        doc = cached_json(
            os.path.join(cache_dir, "census-%s.json" % key),
            lambda: json.loads(
                _get(CENSUS % urllib.parse.urlencode(params), timeout=40).decode("utf-8")
            ),
        )
    except Exception as e:  # noqa: BLE001 -- a slow or absent second opinion is no opinion
        print("  census geocoder did not answer (%s)" % type(e).__name__)
        return None
    hits = (doc.get("result") or {}).get("addressMatches") or []
    if not hits:
        return None
    c = hits[0]["coordinates"]
    return float(c["x"]), float(c["y"]), hits[0].get("matchedAddress") or ""


def locate(at, cache_dir):
    """An address, a place's name or [lat, lon] -> where it is and how exactly that is known:
    {lon, lat, match, name, road, number, city, country}. Raises NoPlace."""
    if isinstance(at, (list, tuple)) and len(at) == 2:
        at = "%s, %s" % (at[0], at[1])
    q = " ".join(str(at or "").split())
    if not q:
        raise NoPlace("give the address: a street address, a place's name, or [lat, lon]")
    m = LATLON.match(q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-85 <= lat <= 85 and -180 <= lon <= 180):
            raise NoPlace("%r is not a [lat, lon]" % q)
        return {"lon": lon, "lat": lat, "match": "point", "name": "%.5f, %.5f" % (lat, lon)}
    bare = UNIT.sub("", q)
    no = HOUSE_NO.match(bare)
    tries = [q, bare] + ([bare[no.end() :]] if no else [])
    g = None
    for text in dict.fromkeys(tries):
        got = nominatim(
            {"q": text, "format": "json", "limit": 5, "accept-language": "en", "addressdetails": 1},
            cache_dir,
        )
        g = _pick(text, got)
        if g:
            break
    if g is None:
        raise NoPlace(
            "%r is not on OpenStreetMap (neither the address nor its street). Give [lat, lon] "
            "only when the event's own page publishes its coordinates and its street is on the "
            "map; otherwise show the address in type and draw no map." % q
        )
    a = g.get("address") or {}
    out = {
        "lon": float(g["lon"]),
        "lat": float(g["lat"]),
        "match": _precision(g),
        "name": g.get("display_name", ""),
        "road": a.get("road") or a.get("pedestrian") or a.get("footway") or "",
        "number": a.get("house_number") or "",
        "city": next(
            (a[k] for k in ("city", "town", "village", "hamlet", "suburb", "county") if a.get(k)),
            "",
        ),
        "country": a.get("country_code") or "",
    }
    if out["match"] == "street" and no and out["country"] == "us":
        c = census(bare, cache_dir)
        # the same street, or it is another opinion about another place
        if c and metres((out["lon"], out["lat"]), c[:2]) < 3000:
            out.update(lon=c[0], lat=c[1], match="block", street_at=(out["lon"], out["lat"]))
    return out


# ---------------------------------------------------------------------- data


def frame_around(lon, lat, radius_m, px, name):
    """A square of px pixels with (lon, lat) at its centre and radius_m from there to each edge."""
    m_per_px = 2.0 * radius_m / px
    z = math.log2(2 * math.pi * EARTH_M * math.cos(math.radians(lat)) / (256 * m_per_px))
    cx, cy, h = gx(lon, z), gy(lat, z), px / 2
    return Frame(
        name, z, (lon_of(cx - h, z), lat_of(cy + h, z), lon_of(cx + h, z), lat_of(cy - h, z))
    )


def query(f, pad_m=40):
    """Everything the map draws inside the frame (and a little past its edges), in one question."""
    w, s, e, n = f.bounds
    dlat = pad_m / 111_320.0
    dlon = pad_m / (111_320.0 * math.cos(math.radians((s + n) / 2)))
    bb = "%.5f,%.5f,%.5f,%.5f" % (s - dlat, w - dlon, n + dlat, e + dlon)
    area = {
        "leisure": "|".join(sorted(GREEN["leisure"])),
        "landuse": "|".join(sorted(GREEN["landuse"] | WATER_USE)),
        "natural": "|".join(sorted(GREEN["natural"] | SAND | {"water", "coastline"})),
    }
    parts = ['way["highway"](%s);' % bb, 'way["building"](%s);' % bb]
    parts.append('relation["building"]["type"="multipolygon"](%s);' % bb)
    for k, v in area.items():
        parts.append('way["%s"~"^(%s)$"](%s);' % (k, v, bb))
        parts.append('relation["%s"~"^(%s)$"]["type"="multipolygon"](%s);' % (k, v, bb))
    parts.append('way["waterway"~"^(river|stream|canal|drain|ditch)$"](%s);' % bb)
    parts.append('way["railway"~"^(rail|light_rail|tram|narrow_gauge)$"](%s);' % bb)
    parts.append('way["man_made"="pier"](%s);' % bb)
    return "[out:json][timeout:120];(%s);out geom;" % "".join(parts)


def to_px(f, pts):
    """(lon, lat) points to the frame's pixels, as an N x 2 float array."""
    a = np.asarray(pts, np.float64).reshape(-1, 2)
    n = 256.0 * 2.0**f.z
    r = np.radians(a[:, 1])
    y = (1 - np.log(np.tan(r) + 1 / np.cos(r)) / math.pi) / 2 * n - f.y0
    return np.stack([(a[:, 0] + 180.0) / 360.0 * n - f.x0, y], 1)


def join(ways):
    """Ways (lists of (lon, lat)) joined end to end into rings or chains, each turned to fit."""
    left = [list(w) for w in ways if len(w) > 1]
    out = []
    while left:
        cur = left.pop()
        grew = True
        while grew and cur[0] != cur[-1]:
            grew = False
            for i, w in enumerate(left):
                if w[0] == cur[-1]:
                    cur += w[1:]
                elif w[-1] == cur[-1]:
                    cur += w[-2::-1]
                elif w[-1] == cur[0]:
                    cur = w[:-1] + cur
                elif w[0] == cur[0]:
                    cur = w[:0:-1] + cur
                else:
                    continue
                del left[i]
                grew = True
                break
        out.append(cur)
    return out


def _geom(e):
    return [(g["lon"], g["lat"]) for g in e.get("geometry") or () if g]


def _kind(t):
    """What an area's tags make it on this map: water, sand, green, building -- or None."""
    if t.get("natural") == "water" or t.get("landuse") in WATER_USE:
        return "water"
    if t.get("natural") in SAND:
        return "sand"
    if t.get("building") and t["building"] != "no":
        return "building"
    if any(t.get(k) in v for k, v in GREEN.items()):
        return "green"
    return None


def layers(f, osm, style):
    """OpenStreetMap's answer sorted into what the map draws, in the frame's pixels:
    areas {kind: [[ring, ...], ...]} (a polygon is its rings, holes among them), roads
    {class: [(line, tags)]}, waterways [(metres, line)], rails, piers, coast chains (lon, lat) and
    the named areas [(kind, name, centre, pixels)]."""
    W, H = f.W, f.H
    roads = style["roads"]
    cls_of = {h: name for name, c in roads["classes"].items() for h in c["highway"]}
    skip = roads.get("skip") or {}
    L = {
        "areas": {"water": [], "sand": [], "green": [], "building": []},
        "roads": {name: [] for name in roads["order"]},
        "waterways": [],
        "rails": [],
        "piers": [],
        "coast": [],
        "named": [],
    }

    def seen(p, pad=60):
        return not (
            p[:, 0].max() < -pad
            or p[:, 0].min() > W + pad
            or p[:, 1].max() < -pad
            or p[:, 1].min() > H + pad
        )

    def area(kind, rings, t):
        px = [to_px(f, r) for r in rings if len(r) > 2]
        if not px or not any(seen(p) for p in px):
            return
        L["areas"][kind].append(px)
        name = t.get("name:en") or t.get("name")
        if name and kind in ("green", "water"):
            big = max(px, key=len)
            inside = np.clip(big, [0, 0], [W, H])
            a = abs(float(cv2.contourArea(inside.astype(np.float32))))
            c = inside.mean(0)
            if a > (0.012 * W) ** 2 * 9:
                L["named"].append((kind, name, (float(c[0]), float(c[1])), a))

    for e in osm:
        t = e.get("tags") or {}
        if e["type"] == "relation":
            kind = _kind(t)
            if kind:
                rings = join([_geom(m) for m in e.get("members") or () if m.get("type") == "way"])
                area(kind, rings, t)
            continue
        pts = _geom(e)
        if e["type"] != "way" or len(pts) < 2:
            continue
        if t.get("natural") == "coastline":
            L["coast"].append(pts)
            continue
        closed = pts[0] == pts[-1] and len(pts) > 3
        hw = t.get("highway")
        if hw:
            if t.get(hw) in skip.get(hw, ()) or (closed and t.get("area") == "yes"):
                continue
            name = cls_of.get(hw)
            p = to_px(f, pts)
            if name in L["roads"] and seen(p):
                L["roads"][name].append((p, t))
            continue
        if t.get("waterway"):
            p = to_px(f, pts)
            if seen(p):
                w = style["waterways_m"].get(t["waterway"], 2.0)
                try:
                    w = max(w, float(str(t.get("width", "")).split()[0]))
                except (ValueError, IndexError):
                    pass
                L["waterways"].append((min(w, 60.0), p))
            continue
        if t.get("railway"):
            p = to_px(f, pts)
            if seen(p) and t.get("tunnel") in (None, "no"):
                L["rails"].append(p)
            continue
        if t.get("man_made") == "pier":
            p = to_px(f, pts)
            if seen(p):
                L["piers"].append((p, closed))
            continue
        kind = _kind(t)
        if kind and closed:
            area(kind, [pts], t)
    return L


def sea_mask(f, coast):
    """1 at sea, 0 on land (float, soft-edged), from OSM's coastlines alone: a coastline is drawn
    with the land on its left, so the pixels just right of it are sea. The lines cut the frame into
    regions and each region takes the side most of its shore says it is -- no need to know where
    the open sea lies, and a bay with islands, or a river mouth with both banks in frame, comes out
    right. None when no coastline crosses the frame."""
    chains = [to_px(f, c) for c in join(coast)]
    chains = [
        p
        for p in chains
        if not (
            p[:, 0].max() < 0 or p[:, 0].min() > f.W or p[:, 1].max() < 0 or p[:, 1].min() > f.H
        )
    ]
    if not chains:
        return None
    line = np.zeros((f.H, f.W), np.uint8)
    for p in chains:
        cv2.polylines(line, [np.round(p).astype(np.int32).reshape(-1, 1, 2)], False, 255, 2)
    n, lab = cv2.connectedComponents((line == 0).astype(np.uint8), connectivity=4)
    votes = np.zeros((n, 2), np.int64)  # [land, sea] per region
    for p in chains:
        d = np.diff(p, axis=0)
        ln = np.hypot(d[:, 0], d[:, 1])
        ok = ln > 1e-6
        mid = (p[:-1] + p[1:])[ok] / 2
        nrm = np.stack([-d[ok, 1], d[ok, 0]], 1) / ln[ok, None]  # to the right of travel, y down
        for side, col in ((-1, 0), (1, 1)):
            q = np.round(mid + side * 5 * nrm).astype(np.int64)
            inb = (q[:, 0] >= 0) & (q[:, 0] < f.W) & (q[:, 1] >= 0) & (q[:, 1] < f.H)
            ids = lab[q[inb, 1], q[inb, 0]]
            w = np.maximum(np.round(ln[ok][inb]), 1).astype(np.int64)  # a long shore says more
            np.add.at(votes[:, col], ids, w)
    wet = np.flatnonzero((votes[:, 1] > votes[:, 0]) & (np.arange(n) > 0))
    if not len(wet):
        return None
    sea = np.isin(lab, wet).astype(np.uint8) * 255
    sea = cv2.dilate(sea, np.ones((3, 3), np.uint8))  # the line itself is shore, not land
    return cv2.GaussianBlur(sea, (0, 0), 0.8).astype(np.float32) / 255.0


# --------------------------------------------------------------------- paint


def _mix(a, b, k):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in (rgb(a) * (1 - k) + rgb(b) * k) * 255)


def _lum(c):
    return float(rgb(c) @ np.array([0.2126, 0.7152, 0.0722], np.float32))


def _as_light_as(tint, base):
    """The tint, made as light (or as dark) as base by adding white or black: its hue with base's
    lightness. A brand's navy mixed straight into a pale map turned its houses to slate; this way a
    tint can only change a surface's hue, never how light it is."""
    want, have = _lum(base), _lum(tint)
    if have < want:
        return _mix(tint, "#ffffff", (want - have) / max(1 - have, 1e-6))
    return _mix(tint, "#000000", (have - want) / max(have, 1e-6))


def palette(style, tone=None, tint=None, colors=None):
    """The map's colours: a tone, leaned toward the film's tint, any surface replaced outright."""
    tones = style["tones"]
    if tone not in (None, *tones):
        raise NoPlace("tone is %s" % " or ".join(tones))
    look = dict(tones[tone or "light"])
    hexc = re.compile(r"^#[0-9a-fA-F]{6}$")
    if tint:
        if not hexc.match(str(tint)):
            raise NoPlace("tint is a colour like #235aa6")
        for k, v in style["tint"].items():
            if k in look and isinstance(v, (int, float)):
                look[k] = _mix(look[k], _as_light_as(tint, look[k]), v)
    for k, v in (colors or {}).items():
        if k not in look:
            raise NoPlace("colors: no surface called %r (there is %s)" % (k, ", ".join(look)))
        if not hexc.match(str(v)):
            raise NoPlace("colors.%s is a colour like #235aa6" % k)
        look[k] = v
    return look


def _fill(img, rings, color):
    """One polygon, its holes cut out (even-odd over its rings), anti-aliased."""
    cv2.fillPoly(
        img,
        [np.round(r * 16).astype(np.int32).reshape(-1, 1, 2) for r in rings],
        color,
        cv2.LINE_AA,
        4,
    )


def paint(f, L, look, style):
    """The map, as an 8-bit BGR image: land, sand, green, water, the sea, buildings, rails, roads."""
    mpp = f.m_per_px
    img = np.empty((f.H, f.W, 3), np.uint8)
    img[:] = bgr8(look["land"])
    for kind in ("sand", "green", "water"):
        col = bgr8(look[kind])
        for rings in L["areas"][kind]:
            _fill(img, rings, col)
    sea = sea_mask(f, L["coast"])
    if sea is not None:
        a = sea[..., None]
        img[:] = np.round(img * (1 - a) + np.array(bgr8(look["water"]), np.float32) * a)
    for w_m, p in L["waterways"]:
        _poly(img, p, bgr8(look["water"]), max(1.5, w_m / mpp))
    for p, closed in L["piers"]:
        if closed:
            _fill(img, [p], bgr8(look["pier"]))
        else:
            _poly(img, p, bgr8(look["pier"]), max(2.0, 4.0 / mpp))
    fill, edge = bgr8(look["building"]), bgr8(look["building_edge"])
    for rings in L["areas"]["building"]:
        _fill(img, rings, fill)
        cv2.polylines(
            img,
            [np.round(r * 16).astype(np.int32).reshape(-1, 1, 2) for r in rings],
            True,
            edge,
            1,
            cv2.LINE_AA,
            4,
        )
    rail = style["rail"]
    for p in L["rails"]:
        for piece in _dashes(p, rail["dash_m"][0] / mpp, rail["dash_m"][1] / mpp):
            _poly(img, piece, bgr8(look["rail"]), max(1.5, rail["w_m"] / mpp))

    roads = style["roads"]

    def width(m):
        return max(roads["min_px"], m / mpp)

    for name in roads["order"]:  # every casing first, the small streets under the large
        c = roads["classes"][name]
        if "case_m" in c:
            for p, _ in L["roads"][name]:
                _poly(img, p, bgr8(look["casing"]), width(c["w_m"]) + 2 * width(c["case_m"]))
    for name in roads["order"]:
        c = roads["classes"][name]
        col = bgr8(look[c["fill"]])
        for p, _ in L["roads"][name]:
            if "dash_m" in c:
                for piece in _dashes(p, c["dash_m"][0] / mpp, c["dash_m"][1] / mpp):
                    _poly(img, piece, col, width(c["w_m"]))
            else:
                _poly(img, p, col, width(c["w_m"]))
    return img


# -------------------------------------------------------------------- streets


def _names(t):
    return {str(t[k]).casefold() for k in ("name", "name:en") if t.get(k)}


COMPASS = {
    "north": "N",
    "south": "S",
    "east": "E",
    "west": "W",
    "northeast": "NE",
    "northwest": "NW",
    "southeast": "SE",
    "southwest": "SW",
}
STREET_TYPE = {
    "street": "St",
    "avenue": "Ave",
    "boulevard": "Blvd",
    "drive": "Dr",
    "road": "Rd",
    "court": "Ct",
    "lane": "Ln",
    "place": "Pl",
    "highway": "Hwy",
    "parkway": "Pkwy",
    "terrace": "Ter",
    "circle": "Cir",
    "trail": "Trl",
    "square": "Sq",
    "expressway": "Expy",
    "freeway": "Fwy",
    "turnpike": "Tpke",
}


def short_name(name):
    """A street's name the way a map letters it: "Southwest Flagler Avenue" -> "SW Flagler Ave".
    Only a leading compass word with a name after it and a trailing street type are shortened, so
    "North Avenue" stays a name ("North Ave") and a name in another language is left alone."""
    w = name.split()
    if len(w) >= 3 and w[0].lower() in COMPASS:
        w[0] = COMPASS[w[0].lower()]
    if len(w) >= 3 and w[-1].lower() in COMPASS:  # "Bay Street North"
        w[-1] = COMPASS[w[-1].lower()]
        if w[-2].lower() in STREET_TYPE:
            w[-2] = STREET_TYPE[w[-2].lower()]
    elif len(w) >= 2 and w[-1].lower() in STREET_TYPE:
        w[-1] = STREET_TYPE[w[-1].lower()]
    return " ".join(w)


def _nearest(p, q):
    """The point of polyline p nearest q, and its distance."""
    a, b = p[:-1], p[1:]
    d = b - a
    den = np.maximum((d * d).sum(1), 1e-9)
    u = np.clip(((q - a) * d).sum(1) / den, 0, 1)
    c = a + d * u[:, None]
    dist = np.hypot(*(c - q).T)
    i = int(np.argmin(dist))
    return c[i], float(dist[i])


def _resample(p, step):
    """A polyline's points every `step` pixels along it."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] < step:
        return p
    at = np.arange(0.0, cum[-1], step)
    return np.stack([np.interp(at, cum, p[:, 0]), np.interp(at, cum, p[:, 1])], 1)


def own_street(f, L, style, pin_px, want, strict):
    """The street the address is on: (name, [line, ...] nearest first), by the name the geocoder
    gave. strict (the pin was placed BY its street: a number along it, or the street alone): only
    that name will do -- the nearest other street would put the address on a street it is not on.
    Otherwise (a mapped building, a place, a point) the nearest named street within
    labels.own_within_m stands in. ("", []) when there is none."""
    reach = style["labels"]["own_within_m"] / f.m_per_px
    named, streets = {}, set()
    for cls, ways in L["roads"].items():
        for p, t in ways:
            if t.get("name"):
                named.setdefault(t["name"], []).append((p, t))
                if style["roads"]["classes"][cls].get("rank"):
                    streets.add(t["name"])  # a path or a service way is nobody's nearest street
    hit = None
    if want:
        hit = next(
            (n for n, ws in named.items() if any(want.casefold() in _names(t) for _, t in ws)), None
        )
    if hit is None and not strict:
        near = [(min(_nearest(p, pin_px)[1] for p, _ in named[n]), n) for n in streets]
        near = [x for x in near if x[0] <= reach]
        hit = min(near)[1] if near else None
    if hit is None:
        return "", []
    lines = sorted((p for p, _ in named[hit]), key=lambda p: _nearest(p, pin_px)[1])
    return hit, lines


def label_spots(f, L, style, pin_px, own):
    """Where each street's name can be lettered: [{name, kind, x, y, a, len, own}] -- a point on
    a straight stretch of the street, the angle it runs at there (radians, clockwise, upright) and
    how long the stretch is, the pin's own street first, then the larger and the nearer."""
    lab = style["labels"]
    W, H = f.W, f.H
    step, half = 24.0, 4
    edge = lab["margin"] * W
    cands, ranks = {}, {}
    for cls, ways in L["roads"].items():
        rank = style["roads"]["classes"][cls].get("rank") or 0
        if not rank:
            continue
        for p, t in ways:
            name = t.get("name")
            if not name:
                continue
            ranks[name] = max(rank, ranks.get(name, 0))
            q = _resample(p, step)
            if len(q) < 2 * half + 1:
                continue
            ring = (lab["own_ring"] if name == own else lab["ring"]) * W
            need = lab["char"] * W * len(short_name(name))  # the length its lettering takes
            for i in range(half, len(q) - half):
                x, y = q[i]
                if not (edge <= x <= W - edge and edge <= y <= H - edge):
                    continue
                a, b = q[i - half], q[i + half]
                chord = float(np.hypot(*(b - a)))
                if chord / (2 * half * step) < lab["straight"]:
                    continue
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                # how far the street keeps this heading, both ways
                run = 2 * half * step
                for sgn in (-1, 1):
                    j = i + sgn * half
                    while 0 <= j + sgn < len(q):
                        d = q[j + sgn] - q[j]
                        turn = abs(
                            (math.atan2(sgn * d[1], sgn * d[0]) - ang + math.pi) % math.tau
                            - math.pi
                        )
                        inside = 0 <= q[j + sgn][0] <= W and 0 <= q[j + sgn][1] <= H
                        if turn > 0.21 or not inside:
                            break
                        run += step
                        j += sgn
                dist = float(np.hypot(x - pin_px[0], y - pin_px[1]))
                # near its ring round the pin, on a stretch long enough to hold the whole name
                score = abs(dist - ring) + max(0.0, need - run) * 1.5
                if ang > math.pi / 2:
                    ang -= math.pi
                elif ang <= -math.pi / 2:
                    ang += math.pi
                cands.setdefault(name, []).append(
                    {
                        "name": name,
                        "kind": cls,
                        "x": float(x),
                        "y": float(y),
                        "a": ang,
                        "len": run,
                        "need": need,
                        "dist": dist,
                        "score": score,
                    }
                )

    def span(c):  # the lettering as points along its line
        k = np.linspace(-0.5, 0.5, 7)[:, None] * c["need"]
        return np.array([c["x"], c["y"]]) + k * np.array([math.cos(c["a"]), math.sin(c["a"])])

    gap = lab["apart"] * W
    # the pin stands on its tip: nothing is lettered under it
    taken = [np.array([[pin_px[0], pin_px[1] - k * gap] for k in (0.0, 0.5, 1.0, 1.5)])]
    order = sorted(cands, key=lambda n: (n != own, -ranks[n], min(c["dist"] for c in cands[n])))
    out = []
    for name in order:
        if len(out) >= lab["n"]:
            break
        for c in sorted(cands[name], key=lambda c: c["score"])[:80]:
            pts = span(c)
            if all(
                np.hypot(*(pts[:, None, :] - o[None, :, :]).reshape(-1, 2).T).min() >= gap
                for o in taken
            ):
                taken.append(pts)
                out.append(c)
                break
        else:
            continue
        # other stretches of the same street, well apart: a film frames the map as it likes, and
        # the first spot may be off its frame or under a card -- it letters the next one then
        c["alt"] = []
        for d in sorted(cands[name], key=lambda d: d["score"]):
            if len(c["alt"]) >= lab["alt"]:
                break
            far = all(
                math.hypot(d["x"] - o["x"], d["y"] - o["y"]) >= lab["alt_apart"] * W
                for o in [c, *c["alt"]]
            )
            if far and d["len"] >= 0.85 * d["need"]:
                c["alt"].append(d)
    return out


# ---------------------------------------------------------------------- make


def make(spec, style, cache_dir, out_img=None, out_data=None, out_preview=None, dry=False):
    """A place's map (out_img) and its data (out_data, SK.DATA.place). Returns the summary the
    caller prints; with dry, everything but the picture and the files."""
    px = int(spec.get("px") or style["px"])
    radius = float(spec.get("radius_m") or style["radius_m"])
    if not (800 <= px <= 6000 and 150 <= radius <= 5000):
        raise NoPlace("px is 800 to 6000 and radius_m 150 to 5000")
    look = palette(style, spec.get("tone"), spec.get("tint"), spec.get("colors"))
    image = spec.get("image") or "place_map"
    place = locate(spec.get("at"), cache_dir)
    for _ in range(2):
        f = frame_around(place["lon"], place["lat"], radius, px, image)
        osm = overpass(query(f), cache_dir, timeout=50)["elements"]
        L = layers(f, osm, style)
        pin = np.array(f.px(place["lon"], place["lat"]))
        own, lines = own_street(
            f, L, style, pin, place.get("road"), place["match"] in ("block", "street")
        )
        on_it = lines and _nearest(lines[0], pin)[1] * f.m_per_px <= 80
        if place["match"] != "block" or not place.get("street_at") or on_it:
            break
        # the Census put the number somewhere this street is not: the street is what is known
        at = place.pop("street_at")
        place.update(lon=at[0], lat=at[1], match="street")
    n_roads = sum(len(v) for v in L["roads"].values())
    if not n_roads:
        raise NoPlace(
            "OpenStreetMap has no streets within %d m of %s: show the address in type and draw "
            "no map" % (radius, place["name"])
        )
    if place["match"] in ("block", "street") and not lines:
        raise NoPlace(
            "the street of %r (%s) is not on OpenStreetMap: show the address in type and draw no "
            "map" % (spec.get("at"), place.get("road") or "no name")
        )
    on = None
    if lines:
        on, _ = _nearest(lines[0], pin)
        if place["match"] == "street":  # the pin marks the street: stand it on the street
            pin = on
    spots = label_spots(f, L, style, pin, own)
    uv = lambda x, y: [round(float(x) / f.W, 4), round(float(y) / f.H, 4)]  # noqa: E731
    keep = []
    for p in lines[:8]:
        q = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), 1.5, False).reshape(-1, 2)
        if (q[:, 0].max() >= 0 and q[:, 0].min() <= f.W) and (
            q[:, 1].max() >= 0 and q[:, 1].min() <= f.H
        ):
            keep.append([uv(x, y) for x, y in q])
    named = sorted(L["named"], key=lambda n: -n[3])[:8]
    lon, lat = lon_of(pin[0] + f.x0, f.z), lat_of(pin[1] + f.y0, f.z)
    data = {
        "_about": "A real street map of the place and where the address is on it "
        "(scripts/place-map.py): u, v are fractions of the map picture, a an angle in radians "
        "(clockwise). Map data (c) OpenStreetMap contributors: credit OpenStreetMap on the map.",
        "image": image,
        "w": f.W,
        "h": f.H,
        "m_per_px": round(f.m_per_px, 4),
        "bounds": [round(x, 6) for x in f.bounds],
        "pin": {
            "u": round(float(pin[0]) / f.W, 4),
            "v": round(float(pin[1]) / f.H, 4),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "match": place["match"],
            "found": place["name"],
            "street": own,
            "street_short": short_name(own),
            "on": uv(*on) if on is not None else None,
            "lines": keep,
        },
        "streets": [
            {
                "name": s["name"],
                "short": short_name(s["name"]),
                "kind": s["kind"],
                "u": round(s["x"] / f.W, 4),
                "v": round(s["y"] / f.H, 4),
                "a": round(s["a"], 3),
                "len": int(s["len"]),
                "alt": [
                    [
                        round(d["x"] / f.W, 4),
                        round(d["y"] / f.H, 4),
                        round(d["a"], 3),
                        int(d["len"]),
                    ]
                    for d in s.get("alt") or ()
                ],
                **({"own": True} if s["name"] == own else {}),
            }
            for s in spots
        ],
        "areas": [{"name": n, "kind": k, "u": uv(*c)[0], "v": uv(*c)[1]} for k, n, c, _ in named],
        # what the map is painted in, and an ink that reads on it: a film letters the map in these
        "look": {k: look[k] for k in ("land", "road", "building", "green", "water")},
        "ink": _mix(
            look["land"], "#18212c" if float(rgb(look["land"]).mean()) > 0.5 else "#ffffff", 0.74
        ),
        "credit": "© OpenStreetMap",
    }
    summary = {
        "map": "%s, %d x %d px, %.2f m a pixel, %d m from the pin to each edge"
        % (os.path.basename(out_img) if out_img else image, f.W, f.H, f.m_per_px, radius),
        "match": place["match"],
        "how": HOW[place["match"]],
        "found": place["name"],
        "pin": [data["pin"]["u"], data["pin"]["v"]],
        "latlon": [data["pin"]["lat"], data["pin"]["lon"]],
        "street": own,
        "streets": [s["name"] for s in spots],
        "areas": ["%s (%s)" % (n, k) for k, n, _, _ in named],
        "has": {
            "streets": n_roads,
            "buildings": len(L["areas"]["building"]),
            "parks": len(L["areas"]["green"]),
            "water": len(L["areas"]["water"]) + len(L["waterways"]),
            "coast": bool(L["coast"]),
        },
    }
    if dry:
        return summary
    bgr = paint(f, L, look, style)
    os.makedirs(os.path.dirname(os.path.abspath(out_img)), exist_ok=True)
    save_jpeg(bgr, out_img, style)
    with open(out_data, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)
    if out_preview:
        draw_preview(bgr, data, out_preview)
    return summary


def draw_preview(bgr, data, path):
    """The map with the pin, its street and every name on it: what a film would letter, to check."""
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    W, H = im.size
    d = ImageDraw.Draw(im)
    for line in data["pin"]["lines"]:
        d.line([(u * W, v * H) for u, v in line], fill=(35, 90, 166, 255), width=max(6, W // 400))
    size = max(18, W // 85)
    try:
        font = ImageFont.truetype(os.path.join(ROOT, "fonts", "Montserrat-Medium.ttf"), size)
    except OSError:
        font = ImageFont.load_default()
    for s in data["streets"]:
        box = d.textbbox((0, 0), s["short"], font=font)
        tw, th = box[2] - box[0] + 16, box[3] - box[1] + 14
        tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text(
            (8 - box[0], 7 - box[1]),
            s["short"],
            font=font,
            fill=(29, 58, 99, 255) if s.get("own") else (70, 78, 90, 255),
            stroke_width=3,
            stroke_fill=(255, 255, 255, 255),
        )
        tile = tile.rotate(-math.degrees(s["a"]), expand=True, resample=Image.BICUBIC)
        im.alpha_composite(
            tile, (int(s["u"] * W - tile.width / 2), int(s["v"] * H - tile.height / 2))
        )
    for a in data["areas"]:
        d.text((a["u"] * W, a["v"] * H), a["name"], font=font, fill=(60, 110, 80, 255), anchor="mm")
    x, y, r = data["pin"]["u"] * W, data["pin"]["v"] * H, max(14, W // 110)
    d.polygon(
        [(x, y), (x - r * 0.75, y - r * 1.6), (x + r * 0.75, y - r * 1.6)], fill=(29, 58, 99, 255)
    )
    d.ellipse([x - r, y - r * 3.1, x + r, y - r * 1.1], fill=(29, 58, 99, 255))
    d.ellipse([x - r * 0.4, y - r * 2.5, x + r * 0.4, y - r * 1.7], fill=(255, 255, 255, 255))
    d.text((12, H - 12), data["credit"], font=font, fill=(90, 98, 110, 255), anchor="ls")
    im.convert("RGB").save(path, "JPEG", quality=88)


def say(summary):
    h = summary["has"]
    print("found     %s" % summary["found"])
    print("match     %s -- %s" % (summary["match"], summary["how"]))
    print(
        "pin       lat %.6f, lon %.6f; on the picture at u %.4f, v %.4f"
        % (*summary["latlon"], *summary["pin"])
    )
    print("map       %s" % summary["map"])
    print(
        "has       %d streets, %d buildings, %d parks, %d waters%s"
        % (
            h["streets"],
            h["buildings"],
            h["parks"],
            h["water"],
            ", a coastline" if h["coast"] else "",
        )
    )
    print("street    %s" % (summary["street"] or "(none: the pin is not on a named street)"))
    print("names     %s" % ", ".join(summary["streets"]))
    if summary["areas"]:
        print("areas     %s" % ", ".join(summary["areas"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", help="a project's place-map.json")
    ap.add_argument("--at", help='an address, a place name or "lat, lon" (instead of a manifest)')
    ap.add_argument("--out", help="--at: the folder the map goes in (default: temp/place-map)")
    ap.add_argument("--radius", type=float, help="metres from the pin to each edge")
    ap.add_argument("--px", type=int, help="the picture's size, pixels a side")
    ap.add_argument("--tone", help="light or dark")
    ap.add_argument("--tint", help="the film's own colour, #rrggbb: every surface leans to it")
    ap.add_argument(
        "--list",
        action="store_true",
        help="price it: the match, the map, what is there; draw nothing",
    )
    ap.add_argument("--film", metavar="SPEC", help="a film's place (the studio's map tool)")
    ap.add_argument("--out-image", help="--film: where the map picture goes")
    ap.add_argument("--out-data", help="--film: where its data goes (SK.DATA.place)")
    ap.add_argument("--out-preview", help="--film: also the map with pin and names drawn on it")
    ap.add_argument("--style", default=STYLE)
    ap.add_argument("--cache", help="where OpenStreetMap's answers are kept (default: temp/)")
    _env.add_workspace_arg(ap)
    a = ap.parse_args()
    _env.set_workspace(a.workspace)
    cache = os.path.join(a.cache or os.path.join(_env.workspace(), "temp"), "route-map")
    t0 = time.time()
    try:
        if a.film:
            with open(a.film, encoding="utf-8") as f:
                spec = json.load(f)
            with open(_env.resolve(a.style), encoding="utf-8") as f:
                style = json.load(f)
            out = make(spec, style, cache, a.out_image, a.out_data, a.out_preview)
            print("place-map --film ran in %.0f s" % (time.time() - t0))
            print(json.dumps(out, ensure_ascii=False))
            return
        if a.manifest:
            mpath = _env.resolve(a.manifest, _env.workspace())
            if not os.path.exists(mpath):  # a committed example lives with the tooling
                mpath = _env.resolve(a.manifest)
            with open(mpath, encoding="utf-8") as f:
                spec = json.load(f)
            pid = _project.project_id(spec, mpath)
            out_dir = _env.resolve(spec["out"], _env.workspace())
        elif a.at:
            spec, pid, mpath = {"at": a.at}, None, None
            out_dir = _env.resolve(a.out or "temp/place-map", _env.workspace())
        else:
            ap.error("--manifest, --at or --film")
        for k, v in (("radius_m", a.radius), ("px", a.px), ("tone", a.tone), ("tint", a.tint)):
            if v:
                spec[k] = v
        with open(_env.resolve(spec.get("style", a.style)), encoding="utf-8") as f:
            style = json.load(f)
        name = spec.get("image") or "place_map"
        img, dat = os.path.join(out_dir, name + ".jpg"), os.path.join(out_dir, "place.json")
        out = make(spec, style, cache, img, dat, os.path.join(out_dir, "preview.jpg"), dry=a.list)
    except NoPlace as e:  # "no map:" is how the studio's map tool tells this from a failure
        sys.exit("no map: %s" % e)
    say(out)
    if a.list:
        return
    print("wrote     %s  %.1f MB (%.0f s)" % (img, os.path.getsize(img) / 1e6, time.time() - t0))
    print("wrote     %s, %s" % (dat, os.path.join(out_dir, "preview.jpg")))
    if pid:
        _project.record(pid, "place map", out=img, script=__file__, kind="map", manifest=mpath)
        _project.record(pid, "place data", out=dat, script=__file__, kind="data", manifest=mpath)


if __name__ == "__main__":
    main()
