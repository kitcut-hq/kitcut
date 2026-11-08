"""Derived layers for the population Short: the densest census tracts holding a
quarter and a half of California's 2020 population. Run with the repo venv:
    .venv/Scripts/python.exe projects/ca-data-shorts/prep_census.py
"""
import json, os
S = os.path.join(os.path.dirname(__file__), "sources")
tr = json.load(open(os.path.join(S, "ca_tracts.geojson")))
fs = [f for f in tr["features"] if f["properties"]["AREALAND"] > 0 and f["geometry"]]
P = sum(f["properties"]["POP100"] for f in tr["features"])
A = sum(f["properties"]["AREALAND"] for f in tr["features"])
fs.sort(key=lambda f: -f["properties"]["POP100"] / f["properties"]["AREALAND"])
c = a = 0
stats = {}
for f in fs:
    c += f["properties"]["POP100"]; a += f["properties"]["AREALAND"]
    f["properties"]["band"] = "q25" if c <= P * 0.25 else ("q50" if c <= P * 0.5 else "rest")
    for k in (0.25, 0.5):
        if c >= P * k and k not in stats:
            stats[k] = dict(pop=c, km2=round(a / 1e6), share=round(100 * a / A, 2))
json.dump({"type": "FeatureCollection", "features": [f for f in fs if f["properties"]["band"] != "rest"]},
          open(os.path.join(S, "tracts_half.geojson"), "w"))
json.dump({"population_2020": P, "land_km2": round(A / 1e6), "bands": {str(k): v for k, v in stats.items()}},
          open(os.path.join(S, "census_stats.json"), "w"), indent=1)
print(json.dumps(stats))
co = json.load(open(os.path.join(S, "ca_counties.geojson")))
la = [f for f in co["features"] if f["properties"]["NAME"].startswith("Los Angeles")]
json.dump({"type": "FeatureCollection", "features": la}, open(os.path.join(S, "la_county.geojson"), "w"))
