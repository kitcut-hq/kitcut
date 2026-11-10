#!/usr/bin/env python
"""Every place of one kind in a city, as dots on the city's real map.

"Look how many coffee shops there are" is a claim a film should prove, and a
handful of search pins proves nothing: a search shows twenty. This asks
OpenStreetMap for every place carrying a tag (amenity=cafe, amenity=pharmacy,
shop=bakery...) inside a city's real boundary and draws each as a dot over that
city's land, water and main roads, so the shape of the city comes out of the
places themselves.

Two pictures and a data sheet, so a film can show the map bare and let the dots
arrive in its own time:

    <name>-base.jpg   the city with no dots: land, the boundary, water, roads
    <name>.jpg        the same with every dot drawn
    <name>.json       the count, the busiest names (brand, else name), when
                      OpenStreetMap's data was taken, and every dot as [u, v]
                      fractions of the picture, nearest the centre first

The map carries no lettering except the OpenStreetMap credit: the film writes
its own words. Every colour and size is in the style (`config/maps/dots.json`).

A count from OpenStreetMap is what volunteers have mapped, not a census: say
"marked on OpenStreetMap", never "there are exactly".

`--list` prices it without drawing: the area matched, the count, the top
names, and the picture's size.

Map data (c) OpenStreetMap contributors (ODbL).

Invoke as:  python scripts/dot-map.py --manifest projects/<id>/<name>.json [--list]
            python scripts/dot-map.py --area "Kyiv" --tag amenity=cafe --out temp/dot-map [--list]
"""

import os
import sys
import json
import math
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import _project  # noqa: E402
from _map import bgr8, gx, gy, lat_of, lon_of, nominatim, overpass, save_jpeg  # noqa: E402

ROOT = _env.ROOT
STYLE = os.path.join(ROOT, "config", "maps", "dots.json")


def area_relation(area, cache):
    """The OSM relation id of a city: an int passes through, a name goes to Nominatim."""
    if isinstance(area, int) or str(area).isdigit():
        return int(area), str(area)
    hits = nominatim({"q": area, "format": "json", "limit": 10}, cache)
    for h in hits:
        if h.get("osm_type") == "relation" and h.get("class") in ("boundary", "place"):
            return int(h["osm_id"]), h.get("display_name", area)
    sys.exit("No boundary on OpenStreetMap for %r: pass its relation id instead" % area)


def tag_filter(tags):
    """[{"amenity": "cafe"}] -> the Overpass selectors, one per tag."""
    out = []
    for t in tags:
        for k, v in t.items():
            out.append('nwr["%s"="%s"](area.a);' % (k, v))
    return "".join(out)


def rings(ways):
    """Closed rings from a multipolygon's member ways, stitched end to end."""
    segs = [list(w) for w in ways if len(w) > 1]
    done = []
    while segs:
        ring = segs.pop(0)
        grown = True
        while ring[0] != ring[-1] and grown:
            grown = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                grown = True
                break
        if len(ring) > 3:
            done.append(ring)
    return done


def geom(el):
    return [(p["lon"], p["lat"]) for p in el.get("geometry", []) if p]


def outer_rings(el):
    if el["type"] == "way":
        g = geom(el)
        return [g] if len(g) > 3 and g[0] == g[-1] else []
    return rings(
        [
            geom(m)
            for m in el.get("members", [])
            if m.get("role") in ("outer", "") and m.get("geometry")
        ]
    )


def inner_rings(el):
    if el["type"] != "relation":
        return []
    return rings(
        [geom(m) for m in el.get("members", []) if m.get("role") == "inner" and m.get("geometry")]
    )


class Canvas:
    """A W x H picture holding the bbox (w, s, e, n) at the largest zoom that fits, centred."""

    def __init__(self, bbox, W, H, margin):
        w, s, e, n = bbox
        z0 = 10
        bw, bh = gx(e, z0) - gx(w, z0), gy(s, z0) - gy(n, z0)
        self.z = z0 + math.log2(min(W * (1 - 2 * margin) / bw, H * (1 - 2 * margin) / bh))
        cx, cy = (gx(w, self.z) + gx(e, self.z)) / 2, (gy(s, self.z) + gy(n, self.z)) / 2
        self.x0, self.y0, self.W, self.H = cx - W / 2, cy - H / 2, W, H

    def px(self, lon, lat):
        return gx(lon, self.z) - self.x0, gy(lat, self.z) - self.y0

    def pts(self, coords, sh=4):
        p = np.array([self.px(lo, la) for lo, la in coords], np.float64)
        return np.round(p * (1 << sh)).astype(np.int32).reshape(-1, 1, 2)


def fill(img, cv, ring_list, color, holes=()):
    if not ring_list:
        return
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [cv.pts(r) for r in ring_list], 255, cv2.LINE_AA, 4)
    if holes:
        cv2.fillPoly(mask, [cv.pts(r) for r in holes], 0, cv2.LINE_AA, 4)
    a = (mask.astype(np.float32) / 255.0)[..., None]
    img[:] = (img * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


def load_spec(a):
    if a.manifest:
        with open(a.manifest, encoding="utf-8") as f:
            spec = json.load(f)
        base = os.path.dirname(os.path.abspath(a.manifest))
        spec.setdefault("name", os.path.splitext(os.path.basename(a.manifest))[0])
        spec["out"] = _env.resolve(spec.get("out", "."), base)
        return spec
    if not (a.area and a.tag):
        sys.exit("--manifest, or --area with --tag")
    tags = [dict([t.split("=", 1)]) for t in a.tag]
    return {
        "area": a.area,
        "tags": tags,
        "name": a.name or "dots",
        "out": _env.resolve(a.out or os.path.join("temp", "dot-map")),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", help="a project's dot-map spec (area, tags, out, tone, px)")
    ap.add_argument("--area", help="a city's name, or its OpenStreetMap relation id")
    ap.add_argument("--tag", action="append", help="key=value, e.g. amenity=cafe (repeatable)")
    ap.add_argument("--name", help="--area: the file name stem (default: dots)")
    ap.add_argument("--out", help="--area: the folder the map goes in (default: temp/dot-map)")
    ap.add_argument("--tone", help="light or dark (default: the spec's, else light)")
    ap.add_argument(
        "--list", action="store_true", help="price it: match, count, names; draw nothing"
    )
    ap.add_argument("--style", default=STYLE)
    ap.add_argument("--cache", default=os.path.join(ROOT, "temp", "osm-cache"))
    ap.add_argument("--workspace", metavar="DIR", help=argparse.SUPPRESS)
    a = ap.parse_args()

    with open(a.style, encoding="utf-8") as f:
        style = json.load(f)
    spec = load_spec(a)
    os.makedirs(a.cache, exist_ok=True)
    rel, label = area_relation(spec["area"], a.cache)
    W, H = spec.get("px", style["px"])
    tone = style["tones"][a.tone or spec.get("tone", "light")]

    places = overpass(
        "[out:json][timeout:170];rel(%d);map_to_area->.a;(%s);out center tags;"
        % (rel, tag_filter(spec["tags"])),
        a.cache,
    )
    dots, names = [], {}
    for el in places["elements"]:
        p = el.get("center") or el
        if "lat" not in p:
            continue
        t = el.get("tags", {})
        n = t.get("brand") or t.get("name") or ""
        if n:
            names[n] = names.get(n, 0) + 1
        dots.append((p["lon"], p["lat"]))
    top = sorted(names.items(), key=lambda kv: -kv[1])[:15]
    stamp = places.get("osm3s", {}).get("timestamp_osm_base", "")
    print(
        "%s (relation %d): %d places tagged %s, OSM data of %s"
        % (label, rel, len(dots), spec["tags"], stamp)
    )
    print("  busiest names: " + ", ".join("%s %d" % kv for kv in top[:10]))
    print("  picture: %dx%d -> %s" % (W, H, spec["out"]))
    if a.list:
        return

    boundary = overpass("[out:json][timeout:120];rel(%d);out geom;" % rel, a.cache)["elements"][0]
    city = outer_rings(boundary)
    lons = [lo for r in city for lo, _ in r]
    lats = [la for r in city for _, la in r]
    bbox = (min(lons), min(lats), max(lons), max(lats))
    cv = Canvas(bbox, W, H, style["margin"])
    # what lies round the city too, out to the picture's edges
    vw, vn = cv.x0, cv.y0
    view = (lat_of(vn + H, cv.z), lon_of(vw, cv.z), lat_of(vn, cv.z), lon_of(vw + W, cv.z))
    bb = "%.5f,%.5f,%.5f,%.5f" % view
    water = overpass(
        '[out:json][timeout:170];(way["natural"="water"](%s);rel["natural"="water"](%s);'
        'way["waterway"="riverbank"](%s);rel["waterway"="riverbank"](%s););out geom;'
        % (bb, bb, bb, bb),
        a.cache,
    )["elements"]
    kinds = list(style["roads"].keys())
    kinds = [k for k in kinds if not k.startswith("_")]
    roads = overpass(
        '[out:json][timeout:170];way["highway"~"^(%s)$"](%s);out geom;' % ("|".join(kinds), bb),
        a.cache,
    )["elements"]

    s = W / 1920.0
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = bgr8(tone["outside"])
    fill(img, cv, city, bgr8(tone["land"]), inner_rings(boundary))
    for el in water:
        fill(img, cv, outer_rings(el), bgr8(tone["water"]), inner_rings(el))
    for k in kinds:
        w = max(1, int(round(style["roads"][k] * s)))
        col = bgr8(tone["road_major"] if k in ("trunk", "motorway", "primary") else tone["road"])
        for el in roads:
            if el.get("tags", {}).get("highway") == k and el.get("geometry"):
                cv2.polylines(img, [cv.pts(geom(el))], False, col, w, cv2.LINE_AA, 4)
    for r in city:
        cv2.polylines(
            img,
            [cv.pts(r)],
            True,
            bgr8(tone["edge"]),
            max(1, int(round(style["edge_w"] * s))),
            cv2.LINE_AA,
            4,
        )

    os.makedirs(spec["out"], exist_ok=True)
    stem = os.path.join(spec["out"], spec["name"])

    def credit(bgr):
        im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(im)
        font = ImageFont.truetype(
            os.path.join(ROOT, "fonts", "Montserrat-Medium.ttf"), int(style["credit_px"] * s)
        )
        t = style["credit"]
        tw = d.textlength(t, font=font)
        d.text((W - tw - 14 * s, H - 26 * s), t, font=font, fill=tone["edge"])
        return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)

    save_jpeg(credit(img), stem + "-base.jpg", style)

    over = img.copy()
    r = style["dot_r"] * s
    sh = 4
    for lo, la in dots:
        x, y = cv.px(lo, la)
        c = (int(round(x * (1 << sh))), int(round(y * (1 << sh))))
        cv2.circle(
            over,
            c,
            int(round((r + style["dot_edge_w"] * s) * (1 << sh))),
            bgr8(tone["dot_edge"]),
            -1,
            cv2.LINE_AA,
            sh,
        )
        cv2.circle(over, c, int(round(r * (1 << sh))), bgr8(tone["dot"]), -1, cv2.LINE_AA, sh)
    al = style["dot_alpha"]
    out = (img * (1 - al) + over * al).astype(np.uint8)
    save_jpeg(credit(out), stem + ".jpg", style)

    uv = []
    for lo, la in dots:
        x, y = cv.px(lo, la)
        uv.append([round(x / W, 5), round(y / H, 5)])
    uv.sort(key=lambda p: (p[0] - 0.5) ** 2 + (p[1] - 0.5) ** 2)
    data = {
        "area": label,
        "relation": rel,
        "tags": spec["tags"],
        "count": len(dots),
        "osm_data_of": stamp,
        "top_names": top,
        "px": [W, H],
        "credit": style["credit"],
        "note": "what OpenStreetMap's volunteers have marked, not a census",
        "dots_uv": uv,
    }
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("wrote %s.jpg, %s-base.jpg, %s.json" % (stem, stem, stem))

    if a.manifest:
        pid = _project.project_id(spec, a.manifest)
        _project.record(
            pid, "dot map", out=stem + ".jpg", script=__file__, kind="map", manifest=a.manifest
        )


if __name__ == "__main__":
    main()
