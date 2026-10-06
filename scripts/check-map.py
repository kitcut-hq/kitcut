#!/usr/bin/env python
"""Self-test the map makers (place-map.py, and what it shares with route-map.py in _map.py).

A map is the one picture in a film its viewers can check against their own street, and every way
this code can be wrong is a quiet one: a pin a block off, a bay painted as land, a street name
lettered across another, an address in the wrong Stuart. None of them throws. This pins each
with a case small enough to read -- the rules against answers shaped like the ones OpenStreetMap
really gave, and one whole map drawn from a made-up town that lives in a temp folder -- so it
asks nobody: no Nominatim, no Overpass, no Census, a few seconds.

    how exactly an address was found   house / block / street / place, and a town alone refused
    which answer is the right town     "Stuart, FL 34997" must not answer Stuart, Iowa
    the sea                            from the coastline's direction alone: a shore, an island
    the names                          the address's own street first, none across another,
                                       spare spots for a film that frames the map its own way
    the tint                           changes a surface's hue, never how light it is
    a whole map                        the pin in the middle, on its street; a street the map
                                       does not have is refused, and says so the way the studio's
                                       map tool looks for ("no map:")

Invoke as:  python scripts/check-map.py
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import _map  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("place_map", os.path.join(HERE, "place-map.py"))
pm = importlib.util.module_from_spec(_spec)  # a hyphen in its name: not importable
_spec.loader.exec_module(pm)

fails = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  -- " + str(detail)))
    if not ok:
        fails.append(name)


def answer(**k):
    """A Nominatim answer, shaped like the real ones."""
    base = {"lat": "27.2", "lon": "-80.25", "display_name": "", "address": {}}
    base.update(k)
    return base


def town(lon0, lat0, coast=False):
    """OpenStreetMap's answer for a made-up town: Oak Lane east-west through (lon0, lat0), four
    more named streets, a few houses, a park, and (coast) a shore along its south."""
    d = 0.0022  # about 245 m north-south: the town fits a map 500 m to each edge
    way = lambda i, tags, pts: {  # noqa: E731
        "type": "way",
        "id": i,
        "tags": tags,
        "geometry": [{"lon": x, "lat": y} for x, y in pts],
    }
    els = [
        way(
            1,
            {"highway": "residential", "name": "Oak Lane"},
            [(lon0 - 3 * d, lat0), (lon0 + 3 * d, lat0)],
        ),
        way(
            2,
            {"highway": "residential", "name": "Elm Street"},
            [(lon0 - 3 * d, lat0 + d), (lon0 + 3 * d, lat0 + d)],
        ),
        way(
            3,
            {"highway": "secondary", "name": "North Main Avenue"},
            [(lon0 + d, lat0 - 2 * d), (lon0 + d, lat0 + 3 * d)],
        ),
        way(
            4,
            {"highway": "residential", "name": "Pine Court"},
            [(lon0 - d, lat0 - 2 * d), (lon0 - d, lat0 + 3 * d)],
        ),
        way(5, {"highway": "service", "service": "driveway"}, [(lon0, lat0), (lon0, lat0 + d / 4)]),
        way(
            6,
            {"highway": "footway", "footway": "sidewalk"},
            [(lon0 - d, lat0 + d / 9), (lon0 + d, lat0 + d / 9)],
        ),
    ]
    for k in range(6):  # houses along the lane
        x, y, s = lon0 - 2 * d + k * d * 0.7, lat0 + d * 0.25, d * 0.12
        els.append(
            way(
                20 + k,
                {"building": "house"},
                [(x, y), (x + s, y), (x + s, y + s), (x, y + s), (x, y)],
            )
        )
    px, py, ps = lon0 + 1.4 * d, lat0 + 1.3 * d, d * 1.1
    els.append(
        way(
            40,
            {"leisure": "park", "name": "Founders Park"},
            [(px, py), (px + ps, py), (px + ps, py + ps), (px, py + ps), (px, py)],
        )
    )
    if coast:  # drawn travelling east: the land is on its left, the north, and the sea to the south
        els.append(
            way(
                50,
                {"natural": "coastline"},
                [(lon0 - 5 * d, lat0 - 1.5 * d), (lon0 + 5 * d, lat0 - 1.5 * d)],
            )
        )
    return {"elements": els}


def seed(cache, place, osm, style, radius=None, px=None):
    """Put the answers a map of `place` would ask for where its caches look, so it asks nobody."""
    os.makedirs(cache, exist_ok=True)
    for text, got in place.items():
        params = {
            "q": text,
            "format": "json",
            "limit": 5,
            "accept-language": "en",
            "addressdetails": 1,
        }
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        with open(os.path.join(cache, "geo-%s.json" % key), "w", encoding="utf-8") as f:
            json.dump(got, f)
    if osm is None:
        return
    g = next(v for v in place.values() if v)[0]
    f = pm.frame_around(
        float(g["lon"]),
        float(g["lat"]),
        radius or style["radius_m"],
        px or style["px"],
        "place_map",
    )
    key = hashlib.sha1(pm.query(f).encode()).hexdigest()[:12]
    with open(os.path.join(cache, "osm-%s.json" % key), "w", encoding="utf-8") as fh:
        json.dump(osm, fh)


def main():
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    with open(_env.resolve(pm.STYLE), encoding="utf-8") as f:
        style = json.load(f)

    # ---- how exactly an address was found
    house = answer(
        place_rank=30, osm_type="way", address={"house_number": "11501", "road": "Buckingham Road"}
    )
    house["class"], house["type"] = "building", "yes"
    ranged = answer(
        place_rank=30,
        osm_type="way",
        address={"house_number": "2601", "road": "Northeast 29th Street"},
    )
    ranged["class"], ranged["type"] = "place", "house"
    node = dict(ranged, osm_type="node")
    street = answer(place_rank=26, osm_type="way", address={"road": "Oak Lane"})
    street["class"], street["type"] = "highway", "residential"
    venue = answer(place_rank=30, osm_type="way", address={"road": "The Embarcadero"})
    check(
        "a mapped building is the house; a number on the street's own way is placed along it",
        [pm._precision(g) for g in (house, ranged, node, street, venue)]
        == ["house", "block", "house", "street", "place"],
        [pm._precision(g) for g in (house, ranged, node, street, venue)],
    )
    check("a town alone is no place for a pin", pm._precision(answer(place_rank=16)) is None)

    iowa = answer(
        place_rank=26,
        display_name="Flagler Avenue, Stuart, Guthrie County, Iowa, 50250, United States",
        address={"road": "Flagler Avenue", "city": "Stuart", "ISO3166-2-lvl4": "US-IA"},
    )
    florida = answer(
        place_rank=30,
        osm_type="node",
        display_name="121, Southwest Flagler Avenue, Stuart, Martin County, Florida, 34994, United States",
        address={
            "house_number": "121",
            "road": "Southwest Flagler Avenue",
            "city": "Stuart",
            "ISO3166-2-lvl4": "US-FL",
        },
    )
    q = "121 SW Flagler Ave, Stuart, FL 34994"
    check(
        "the answer in the town the address names wins, wherever it stands in the list",
        pm._pick(q, [iowa, florida]) is florida,
    )
    check(
        "an answer in another town altogether is no answer",
        pm._pick("12 Oak Lane, Austin, TX", [iowa]) is None,
    )

    tmp = tempfile.mkdtemp(prefix="check-map-")
    got = pm.locate([26.1645, -80.1136], tmp)
    check(
        "[lat, lon] is taken as given",
        got["match"] == "point" and abs(got["lat"] - 26.1645) < 1e-9,
        got,
    )
    try:
        pm.locate("95.0, 10.0", tmp)
        check("a latitude past the pole is refused", False)
    except pm.NoPlace:
        check("a latitude past the pole is refused", True)
    check(
        '"Unit 12B" and "#4" are the door, not the place',
        pm.UNIT.sub("", "1482 N Main Blvd, Unit 12B, Austin") == "1482 N Main Blvd, Austin"
        and pm.UNIT.sub("", "12 Oak Ln #4, Austin") == "12 Oak Ln, Austin",
    )

    # ---- names as a map letters them
    names = {
        "Southwest Flagler Avenue": "SW Flagler Ave",
        "North Avenue": "North Ave",
        "Bay Street North": "Bay St N",
        "Northeast 29th Street": "NE 29th St",
        "Broadway": "Broadway",
        "Rue de la Paix": "Rue de la Paix",
        "The Embarcadero": "The Embarcadero",
    }
    check(
        "street names are shortened the way a map does it",
        all(pm.short_name(a) == b for a, b in names.items()),
        {a: pm.short_name(a) for a in names},
    )

    # ---- the frame
    f = pm.frame_around(-80.1136, 26.1645, 800, 3200, "m")
    u, v = f.uv(-80.1136, 26.1645)
    check(
        "the address is the middle of the picture, at the scale asked for",
        abs(u - 0.5) < 2e-3
        and abs(v - 0.5) < 2e-3
        and abs(f.W - 3200) <= 1
        and abs(f.m_per_px - 0.5) < 0.01,
        (u, v, f.W, f.m_per_px),
    )
    ring = pm.join([[(0, 0), (1, 0)], [(1, 1), (1, 0)], [(1, 1), (0, 1)], [(0, 0), (0, 1)]])
    check(
        "ways out of order and backwards join into one ring",
        len(ring) == 1 and ring[0][0] == ring[0][-1] and len(ring[0]) == 5,
        ring,
    )

    # ---- the sea: from the coastline's direction alone
    f = pm.frame_around(0.0, 0.0, 300, 600, "m")
    w, s, e, n = f.bounds
    east = [(w - 0.01, 0.0), (e + 0.01, 0.0)]  # travelling east: land on its left, the north
    m1 = pm.sea_mask(f, [east])
    m2 = pm.sea_mask(f, [east[::-1]])
    check(
        "a shore: land on the coastline's left, sea on its right, whichever way it was drawn",
        m1 is not None
        and m1[100, 300] < 0.1
        and m1[500, 300] > 0.9
        and m2[100, 300] > 0.9
        and m2[500, 300] < 0.1,
    )
    r = 0.001
    island = [
        (r, r),
        (-r, r),
        (-r, -r),
        (r, -r),
        (r, r),
    ]  # anticlockwise: the land inside is on its left
    m3 = pm.sea_mask(f, [island])
    check(
        "an island alone in the frame: land inside, sea all round",
        m3 is not None and m3[300, 300] < 0.1 and m3[30, 30] > 0.9,
    )
    check("no coastline, no sea", pm.sea_mask(f, []) is None)

    # ---- the tint: hue, never lightness
    plain = pm.palette(style)
    for tint, moves in (("#012169", False), ("#b5532a", True)):
        look = pm.palette(style, tint=tint)
        drift = max(
            abs(pm._lum(look[k]) - pm._lum(plain[k]))
            for k in ("land", "building", "casing", "water")
        )
        check("a tint of %s changes no surface's lightness" % tint, drift < 0.02, drift)
        if moves:
            check(
                "and a warm tint does change the land's hue",
                look["land"].lower() != plain["land"].lower(),
                look["land"],
            )
    for bad, why in (
        ({"tint": "navy"}, "a tint that is no colour"),
        ({"colors": {"sky": "#ffffff"}}, "a surface the map has not"),
        ({"tone": "sepia"}, "a tone there is not"),
    ):
        try:
            pm.palette(style, **bad)
            check("%s is refused" % why, False)
        except pm.NoPlace:
            check("%s is refused" % why, True)

    # ---- a whole map, of a made-up town, asking nobody
    lon0, lat0 = -97.75, 30.4
    cache = os.path.join(tmp, "route-map")
    oak = answer(
        lat=str(lat0),
        lon=str(lon0),
        place_rank=30,
        osm_type="way",
        display_name="12, Oak Lane, Testville, Travis County, Texas, 78700, United States",
    )
    oak["class"], oak["type"] = "place", "house"
    oak["address"] = {
        "house_number": "12",
        "road": "Oak Lane",
        "city": "Testville",
        "ISO3166-2-lvl4": "US-TX",
        "country_code": "us",
    }
    spec = {"at": "12 Oak Lane, Testville, TX", "px": 1200, "radius_m": 500, "tint": "#b5532a"}
    seed(cache, {spec["at"]: [oak]}, town(lon0, lat0, coast=True), style, 500, 1200)
    img, dat = os.path.join(tmp, "m.jpg"), os.path.join(tmp, "m.json")
    out = pm.make(spec, style, cache, img, dat, os.path.join(tmp, "p.jpg"))
    with open(dat, encoding="utf-8") as fh:
        d = json.load(fh)
    im = np.asarray(Image.open(img).convert("RGB")).astype(int)
    px = lambda u, v: im[int(v * d["h"]), int(u * d["w"])]  # noqa: E731
    close = lambda a, hexc: np.abs(a - (_map.rgb(hexc) * 255)).max() < 14  # noqa: E731
    check(
        "the map is the size asked for and the pin is its middle",
        abs(d["w"] - 1200) <= 1
        and abs(d["pin"]["u"] - 0.5) < 0.01
        and abs(d["pin"]["v"] - 0.5) < 0.01,
        d["pin"],
    )
    check(
        "it says how exactly the address was found",
        d["pin"]["match"] == "block" == out["match"] and "street" in out["how"],
    )
    check(
        "the address's own street is found by its name, as lines",
        d["pin"]["street"] == "Oak Lane"
        and d["pin"]["street_short"] == "Oak Ln"
        and len(d["pin"]["lines"]) == 1
        and len(d["pin"]["lines"][0]) >= 2,
        d["pin"],
    )
    check(
        "the pin stands on its street: the picture is road there",
        close(px(d["pin"]["u"], d["pin"]["v"]), d["look"]["road"]),
        px(d["pin"]["u"], d["pin"]["v"]),
    )
    st = d["streets"]
    check(
        "its own street is the first name, then the larger street",
        st
        and st[0]["name"] == "Oak Lane"
        and st[0].get("own")
        and st[1]["name"] == "North Main Avenue"
        and st[1]["short"] == "N Main Ave",
        [x["name"] for x in st],
    )
    check(
        "every name stands upright",
        all(-math.pi / 2 - 1e-3 < x["a"] <= math.pi / 2 + 1e-3 for x in st),
        [x["a"] for x in st],
    )
    gap = style["labels"]["apart"] * d["w"]
    spans = [
        np.array([x["u"] * d["w"], x["v"] * d["h"]])
        + np.linspace(-0.5, 0.5, 7)[:, None]
        * style["labels"]["char"]
        * d["w"]
        * len(x["short"])
        * np.array([math.cos(x["a"]), math.sin(x["a"])])
        for x in st
    ]
    near = min(
        np.hypot(*(a[:, None, :] - b[None, :, :]).reshape(-1, 2).T).min()
        for i, a in enumerate(spans)
        for b in spans[i + 1 :]
    )
    check("no name is lettered across another", near >= gap * 0.99, (near, gap))
    far = style["labels"]["alt_apart"] * d["w"]
    check(
        "a long street carries spare spots, well apart, for a film that frames the map its own way",
        any(x["alt"] for x in st)
        and all(
            math.hypot((a[0] - x["u"]) * d["w"], (a[1] - x["v"]) * d["h"]) >= far * 0.99
            for x in st
            for a in x["alt"]
        ),
        [len(x["alt"]) for x in st],
    )
    check(
        "a driveway and a sidewalk are not drawn; a park with a name is listed",
        len([x for x in st if x["name"]]) == 4
        and [a["name"] for a in d["areas"]] == ["Founders Park"],
        (len(st), d["areas"]),
    )
    check(
        "the sea is painted on the coastline's right: here the south, the town dry",
        close(px(0.5, 0.95), d["look"]["water"]) and close(px(0.25, 0.1), d["look"]["land"]),
        (px(0.5, 0.95), px(0.25, 0.1)),
    )
    check(
        "the map credits OpenStreetMap and carries its palette",
        d["credit"].endswith("OpenStreetMap")
        and d["ink"].startswith("#")
        and set(d["look"]) >= {"land", "road", "water"},
    )
    check("a tint reaches the picture", d["look"]["land"].lower() != plain["land"].lower())

    # a street the map does not have: refused, in the words the studio's map tool looks for
    spec2 = {"at": "9 Helmsman Court, Testville, TX", "px": 1200, "radius_m": 500}
    gone = dict(oak, display_name="Helmsman Court, Testville, Texas, United States", place_rank=26)
    gone["class"], gone["type"] = "highway", "residential"
    gone["address"] = {
        "road": "Helmsman Court",
        "city": "Testville",
        "ISO3166-2-lvl4": "US-TX",
        "country_code": "xx",
    }
    seed(cache, {spec2["at"]: [gone]}, None, style)
    try:
        pm.make(spec2, style, cache, img, dat)
        check("an address whose street is not on the map is refused", False)
    except pm.NoPlace as e:
        check(
            "an address whose street is not on the map is refused",
            "not on OpenStreetMap" in str(e),
            e,
        )
    r = subprocess.run(
        [
            *_env.PY,
            os.path.join(HERE, "place-map.py"),
            "--at",
            "95.0, 10.0",
            "--list",
            "--cache",
            tmp,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    check(
        'a place it cannot map exits saying "no map:"',
        r.returncode != 0 and (r.stderr.strip().splitlines() or [""])[-1].startswith("no map:"),
        r.stderr[-300:],
    )

    print("\nall passed" if not fails else "\n%d failed" % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
