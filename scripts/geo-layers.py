#!/usr/bin/env python
"""Real maps of real data, as stacked pictures a film animates.

A data Short ("every oil well in Los Angeles", "every earthquake since 1990",
"half of California lives in the red") lives or dies on its map. A map the
film's Claude draws for itself is a cartoon of the place; this renders the
place: public-domain USGS imagery (satellite) or shaded relief under the data,
toned down so the data reads, and every data layer on its own transparent
sheet aligned to the base pixel for pixel. The film then reveals, zooms and
counts; it never redraws the map.

Each view of the manifest is one bbox at one size, all Web Mercator:

    base.jpg            the basemap (imagery | relief), toned per the view
    <layer>.png         each layer alone, transparent, same size
    preview.jpg         base + every layer, for a look before a film is made
    sheet.md            where things are: the bbox, each layer's count, and
                        each named place as u, v (fractions of width, height)

Layers are points (a JSON list of records or a GeoJSON of points, filtered by
`where` and `in_file`, sized and coloured by field), polygons (GeoJSON, filled
and/or stroked, filtered the same way) and lines. Styling is all manifest.

`--list` prices the job without fetching a tile: each view's zoom, tile count,
output size and how many records each layer keeps. `--preview` writes only
preview.jpg at a quarter size.

Bases: `s2` (Sentinel-2 cloudless 2016, EOX, CC BY 4.0: credit it), `imagery`,
`relief`, `topo` (USGS The National Map, public domain), `naip` (USDA aerial
photos at 0.6 m, public domain, for street-level views; at most 4000 px a side). sheet.md names the
credit each view needs.

Invoke as:  python scripts/geo-layers.py --manifest projects/<id>/geo-<film>.json [--list] [--only <view>]
"""

import os
import sys
import json
import math
import time
import argparse
import urllib.error
import urllib.parse
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402
from PIL import Image  # noqa: E402

import _project  # noqa: E402
from _map import gx, gy, _get, rgb, bgr8  # noqa: E402

ROOT = _env.ROOT
# Each base: tile url, deepest zoom it serves, the credit a film shows.
# s2 is the 2016 Sentinel-2 cloudless mosaic, the one EOX licenses CC BY 4.0 (later years are
# NC-SA); it has the sea, which USGS imagery paints black. USGS imagery is the sharper one up close.
TILES = {
    "s2": (
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
        14,
    ),
    "imagery": (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        16,
    ),
    "relief": (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}",
        13,
    ),
    "topo": (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
        16,
    ),
}
CREDITS = {
    "s2": "Sentinel-2 cloudless 2016 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2016), CC BY 4.0",
    "imagery": "USGS The National Map (public domain)",
    "relief": "USGS The National Map (public domain)",
    "topo": "USGS The National Map (public domain)",
    "naip": "USDA NAIP via USGS The National Map (public domain)",
}


def zoom_for(bbox, width_px, max_z):
    w, s, e, n = bbox
    for z in range(3, max_z + 1):
        if (gx(e, z) - gx(w, z)) >= width_px:
            return z
    return max_z


def size_at(bbox, z):
    w, s, e, n = bbox
    return gx(e, z) - gx(w, z), gy(s, z) - gy(n, z)


def tile_range(bbox, z):
    w, s, e, n = bbox
    return (
        int(gx(w, z) // 256),
        int(gx(e, z) // 256),
        int(gy(n, z) // 256),
        int(gy(s, z) // 256),
    )


NAIP = (
    "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
)


def merc(lon, lat):
    return lon * 20037508.34 / 180, math.log(math.tan((90 + lat) * math.pi / 360)) * 6378137


def fetch_naip(view, cache):
    """USDA NAIP aerial photos (0.6 m, public domain) for street-level views: one export, cached."""
    w, s, e, n = view["bbox"]
    x0, y0 = merc(w, s)
    x1, y1 = merc(e, n)
    W = view["width_px"]
    H = int(round(W * (y1 - y0) / (x1 - x0)))
    key = f"{w}_{s}_{e}_{n}_{W}x{H}".replace("-", "m")
    p = os.path.join(cache, "naip", key + ".jpg")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        q = urllib.parse.urlencode(
            dict(
                bbox=f"{x0},{y0},{x1},{y1}",
                bboxSR=3857,
                imageSR=3857,
                size=f"{W},{H}",
                format="jpg",
                f="image",
            )
        )
        for attempt in range(6):
            try:
                b = _get(NAIP + "?" + q)
                if b[:2] == bytes([0xFF, 0xD8]):  # a JPEG, not an error page
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(3 * (attempt + 1))
        else:
            raise SystemExit(f"NAIP export failed for {view['name']}")
        open(p, "wb").write(b)
    return cv2.imdecode(np.frombuffer(open(p, "rb").read(), np.uint8), cv2.IMREAD_COLOR), "naip"


def fetch_base(view, cache):
    kind = view.get("base", "imagery")
    if kind == "naip":
        return fetch_naip(view, cache)
    url, max_z = TILES[kind]
    z = view.get("zoom") or zoom_for(view["bbox"], view["width_px"], max_z)
    x0, x1, y0, y1 = tile_range(view["bbox"], z)
    d = os.path.join(cache, kind, str(z))
    os.makedirs(d, exist_ok=True)

    def one(xy):
        x, y = xy
        p = os.path.join(d, f"{x}_{y}.jpg")
        if not os.path.exists(p):
            for attempt in range(6):
                try:
                    b = _get(url.format(z=z, x=x, y=y))
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        b = b""  # no tile there (open ocean, or a level the service skips): an empty marker
                        break
                    if attempt == 5:
                        raise
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    if attempt == 5:
                        raise
                time.sleep(1.5 * (attempt + 1))
            with open(p, "wb") as f:
                f.write(b)
        if os.path.getsize(p) == 0:
            return x, y, None
        im = cv2.imdecode(np.frombuffer(open(p, "rb").read(), np.uint8), cv2.IMREAD_COLOR)
        return x, y, im

    canvas = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256, 3), np.uint8)
    jobs = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    missing = []
    with cf.ThreadPoolExecutor(4) as ex:
        for x, y, im in ex.map(one, jobs):
            if im is not None:
                canvas[(y - y0) * 256 : (y - y0 + 1) * 256, (x - x0) * 256 : (x - x0 + 1) * 256] = (
                    cv2.resize(im, (256, 256))
                )
            else:
                missing.append((x, y))
    if (
        missing
    ):  # holes are open sea on these services: the view's `sea` colour, else the commonest pixel
        if view.get("sea"):
            sea = np.array(bgr8(view["sea"]), np.uint8)
        else:
            vals, counts = np.unique(canvas.reshape(-1, 3), axis=0, return_counts=True)
            sea = vals[counts.argmax()]
        for x, y in missing:
            canvas[(y - y0) * 256 : (y - y0 + 1) * 256, (x - x0) * 256 : (x - x0 + 1) * 256] = sea
    w, s, e, n = view["bbox"]
    cx0, cy0 = int(gx(w, z) - x0 * 256), int(gy(n, z) - y0 * 256)
    cw, ch = size_at(view["bbox"], z)
    crop = canvas[cy0 : cy0 + int(ch), cx0 : cx0 + int(cw)]
    W = view["width_px"]
    H = int(round(W * ch / cw))
    return cv2.resize(crop, (W, H), interpolation=cv2.INTER_AREA), z


def tone(img, t):
    f = img.astype(np.float32) / 255
    if t.get("saturation", 1) != 1:
        g = f.mean(axis=2, keepdims=True)
        f = g + (f - g) * t["saturation"]
    f = f * t.get("brightness", 1)
    if t.get("contrast", 1) != 1:
        f = (f - 0.5) * t["contrast"] + 0.5
    if t.get("tint"):
        c = rgb(t["tint"])[::-1]
        f = f * (1 - t.get("tint_mix", 0.3)) + c * t.get("tint_mix", 0.3)
    if t.get("vignette"):
        h, w = f.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        f = f * (1 - t["vignette"] * np.clip(r - 0.5, 0, 1))[..., None]
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


class Proj:
    def __init__(self, bbox, W, H):
        self.w, self.s, self.e, self.n = bbox
        self.W, self.H = W, H
        self.x0, self.x1 = gx(self.w, 0), gx(self.e, 0)
        self.y0, self.y1 = gy(self.n, 0), gy(self.s, 0)

    def px(self, lon, lat):
        return (
            (gx(lon, 0) - self.x0) / (self.x1 - self.x0) * self.W,
            (gy(lat, 0) - self.y0) / (self.y1 - self.y0) * self.H,
        )

    def uv(self, lon, lat):
        x, y = self.px(lon, lat)
        return round(x / self.W, 4), round(y / self.H, 4)


def path(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def records(layer):
    data = json.load(open(path(layer["src"]), encoding="utf-8"))
    feats = data["features"] if isinstance(data, dict) and "features" in data else data
    out = []
    keep = None
    if layer.get("in_file"):
        keep = set(json.load(open(path(layer["in_file"]["file"]), encoding="utf-8")))
    for f in feats:
        props = f.get("properties", f) if isinstance(f, dict) else f
        ok = all(
            props.get(k) in (v if isinstance(v, list) else [v])
            for k, v in layer.get("where", {}).items()
        )
        for k, v in layer.get("min", {}).items():
            ok = ok and props.get(k) not in (None, "") and float(props[k]) >= v
        if keep is not None:
            inn = props.get(layer["in_file"]["field"]) in keep
            ok = ok and (inn if not layer["in_file"].get("exclude") else not inn)
        if ok:
            out.append(f)
    return out


def point_ll(f, layer):
    if f.get("geometry"):
        lon, lat = f["geometry"]["coordinates"][:2]
        return lon, lat
    return float(f[layer.get("lon", "longitude")]), float(f[layer.get("lat", "latitude")])


def draw_points(layer, pr, W, H, scale):
    rgba = np.zeros((H, W, 4), np.float32)
    col = np.array(rgb(layer.get("color", "#ffb020"))[::-1], np.float32)
    acc = np.zeros((H, W), np.float32)
    for f in records(layer):
        lon, lat = point_ll(f, layer)
        x, y = pr.px(lon, lat)
        r = layer.get("radius", 3)
        if layer.get("radius_by"):
            rb = layer["radius_by"]
            props = f.get("properties", f)
            v = float(props[rb["field"]])
            r = rb["base"] * (rb.get("mult", 2.0) ** (v - rb["at"]))
            r = min(r, rb.get("max", 60))
        r *= scale
        cv2.circle(
            acc,
            (int(round(x * 4)), int(round(y * 4))),
            max(1, int(round(r * 4))),
            1.0,
            -1,
            cv2.LINE_AA,
            2,
        )
    a = np.clip(acc, 0, 1) * layer.get("alpha", 0.9)
    if layer.get("glow"):
        g = cv2.GaussianBlur(acc, (0, 0), layer["glow"] * scale) * layer.get("glow_strength", 1.2)
        a = np.clip(a + np.clip(g, 0, 1) * 0.6, 0, 1)
    rgba[..., :3] = col
    rgba[..., 3] = a
    return rgba


def rings_of(geom):
    t = geom["type"]
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return geom["coordinates"]
    if t == "LineString":
        return [[geom["coordinates"]]]
    if t == "MultiLineString":
        return [[c] for c in geom["coordinates"]]
    return []


def draw_polys(layer, pr, W, H, scale):
    fill = np.zeros((H, W), np.uint8)
    edge = np.zeros((H, W), np.uint8)
    S = 4
    for f in records(layer):
        for poly in rings_of(f["geometry"]):
            pts = [
                np.array(
                    [[pr.px(lon, lat)[0] * S, pr.px(lon, lat)[1] * S] for lon, lat in ring[:]],
                    np.int32,
                )
                for ring in poly
            ]
            if layer.get("fill") and f["geometry"]["type"].endswith("Polygon"):
                cv2.fillPoly(fill, pts, 255, cv2.LINE_AA, 2)
            if layer.get("stroke"):
                cv2.polylines(
                    edge,
                    pts,
                    f["geometry"]["type"].endswith("Polygon"),
                    255,
                    max(1, int(layer.get("stroke_px", 2) * scale)),
                    cv2.LINE_AA,
                    2,
                )
    rgba = np.zeros((H, W, 4), np.float32)
    a = np.zeros((H, W), np.float32)
    colr = np.zeros((H, W, 3), np.float32)
    if layer.get("fill"):
        fa = fill.astype(np.float32) / 255 * layer.get("fill_alpha", 0.75)
        colr += np.array(rgb(layer["fill"])[::-1], np.float32) * fa[..., None]
        a += fa
    if layer.get("stroke"):
        ea = edge.astype(np.float32) / 255 * layer.get("stroke_alpha", 1.0)
        if layer.get("glow"):
            ea = np.clip(ea + cv2.GaussianBlur(ea, (0, 0), layer["glow"] * scale) * 0.8, 0, 1)
        colr = (
            colr * (1 - ea[..., None])
            + np.array(rgb(layer["stroke"])[::-1], np.float32) * ea[..., None]
        )
        a = a * (1 - ea) + ea
    rgba[..., :3] = np.where(a[..., None] > 0, colr / np.maximum(a[..., None], 1e-6), 0)
    rgba[..., 3] = np.clip(a, 0, 1)
    return rgba


def save_png(rgba, p):
    out = np.zeros(rgba.shape, np.uint8)
    out[..., :3] = np.clip(rgba[..., :3] * 255, 0, 255)
    out[..., 3] = np.clip(rgba[..., 3] * 255, 0, 255)
    Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGRA2RGBA)).save(p, optimize=True)


def comp(base, layers):
    f = base.astype(np.float32) / 255
    for L in layers:
        a = L[..., 3:4]
        f = f * (1 - a) + L[..., :3] * a
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


def run_view(view, out, cache, preview, lines):
    W = view["width_px"] // (4 if preview else 1)
    v = dict(view, width_px=W)
    base, z = fetch_base(v, cache)
    H = base.shape[0]
    pr = Proj(view["bbox"], W, H)
    scale = W / view["width_px"] * view.get("mark_scale", 1.0)
    if view.get("sea"):  # imagery paints open sea black: one even sea colour instead
        dark = base.astype(np.int32).sum(axis=2) < view.get("sea_below", 24)
        dark = cv2.morphologyEx(
            dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
        ).astype(bool)
        base[dark] = bgr8(view["sea"])
    base = tone(base, view.get("tone", {}))
    if view.get(
        "focus"
    ):  # dim everything outside a region (the state, the county) so it reads first
        fm = view["focus"]
        mask = draw_polys(
            {"src": fm["src"], "fill": "#ffffff", "fill_alpha": 1.0}, pr, W, H, scale
        )[..., 3]
        mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, 2 * scale))
        k = fm.get("outside", 0.35)
        f = base.astype(np.float32) * (k + (1 - k) * mask[..., None])
        base = np.clip(f, 0, 255).astype(np.uint8)
    d = os.path.join(out, view["name"])
    os.makedirs(d, exist_ok=True)
    rendered = []
    lines += [
        f"## View `{view['name']}`",
        "",
        f"- size: {W} x {H} px, zoom {z}, base {view.get('base', 'imagery')}: credit {CREDITS[view.get('base', 'imagery')]}",
        f"- bbox (lon/lat W,S,E,N): {view['bbox']}",
    ]
    for L in view.get("layers", []):
        fn = draw_points if L["type"] == "points" else draw_polys
        rgba = fn(L, pr, W, H, scale)
        rendered.append(rgba)
        n = len(records(L))
        lines.append(f"- layer `{L['name']}.png`: {L['type']}, {n} records -- {L.get('what', '')}")
        if not preview:
            save_png(rgba, os.path.join(d, L["name"] + ".png"))
    for pl in view.get("places", []):
        u, vv = pr.uv(pl["lon"], pl["lat"])
        lines.append(f"- place `{pl['name']}`: u={u}, v={vv}")
    lines.append("")
    pv = comp(base, rendered)
    if preview:
        cv2.imwrite(os.path.join(d, "preview.jpg"), pv, [cv2.IMWRITE_JPEG_QUALITY, 85])
    else:
        cv2.imwrite(os.path.join(d, "base.jpg"), base, [cv2.IMWRITE_JPEG_QUALITY, 90])
        small = cv2.resize(pv, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(d, "preview.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imwrite(os.path.join(d, "composite.jpg"), pv, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--list",
        action="store_true",
        help="price it: zoom, tiles, sizes, layer counts; fetch nothing",
    )
    ap.add_argument("--preview", action="store_true", help="only preview.jpg at a quarter size")
    ap.add_argument("--only", help="one view by name")
    a = ap.parse_args()
    m = json.load(open(path(a.manifest), encoding="utf-8"))
    out = path(m["out"])
    cache = path(m.get("tile_cache", "temp/geo-tiles"))
    views = [v for v in m["views"] if not a.only or v["name"] == a.only]
    if a.list:
        for v in views:
            kind = v.get("base", "imagery")
            if kind == "naip":
                print(f"{v['name']}: naip, one export, {v['width_px']} wide")
                for L in v.get("layers", []):
                    print(f"   {L['name']}: {L['type']}, {len(records(L))} records")
                continue
            z = v.get("zoom") or zoom_for(v["bbox"], v["width_px"], TILES[kind][1])
            x0, x1, y0, y1 = tile_range(v["bbox"], z)
            cw, ch = size_at(v["bbox"], z)
            H = int(round(v["width_px"] * ch / cw))
            print(
                f"{v['name']}: {kind} z{z}, {(x1 - x0 + 1) * (y1 - y0 + 1)} tiles, {v['width_px']}x{H}"
            )
            for L in v.get("layers", []):
                print(f"   {L['name']}: {L['type']}, {len(records(L))} records")
        return
    lines = [
        f"# Map sheet: {m.get('title', a.manifest)}",
        "",
        "u, v are fractions of the picture's width and height from its top-left.",
        "",
    ]
    for v in views:
        d = run_view(v, out, cache, a.preview, lines)
        print("wrote", d)
    if not a.preview:
        open(os.path.join(out, "sheet.md"), "w", encoding="utf-8").write("\n".join(lines))
        if m.get("project"):
            for v in views:
                _project.record(
                    m["project"],
                    "map layers",
                    out=os.path.join(out, v["name"], "composite.jpg"),
                    script="geo-layers.py",
                    argv=sys.argv[1:],
                    kind="map",
                    manifest=a.manifest,
                )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
