"""Turn the Etsy CSVs into the two tables advice is built on.

`etsy_insights.py report` leaves every term Etsy returned and every listing it
shows as the competition. This groups them:

  families       the terms summed into product families, with the share of each
                 family's searches that names somebody else's character or brand
  price-classes  the competing listings split into instant templates and
                 made-to-order work, with the prices each class asks

The grouping is regexes in a JSON file beside the seed list (`--rules`), so a
new research topic brings its own families and nothing here changes.

    python market/etsy/analyze.py --rules market/etsy/seeds/video-services.families.json
    python market/etsy/analyze.py --rules <rules.json> --verbose     # the terms behind each family

Standard library only, like the fetcher. Writes `data/families.csv` and
`data/price_classes.csv`.
"""

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
HIGH = {"High", "Very High"}
QUARTILE_MIN = 4  # fewer listings than this and a quartile is one listing's price


def number(text: str) -> int:
    """Read a count out of a CSV cell; an empty cell is nothing."""
    try:
        return int(float(text))
    except ValueError:
        return 0


def money(text: str) -> float:
    """Read a price like `$1,234.50`."""
    found = re.search(r"[\d,.]+", text or "")
    return float(found.group().replace(",", "")) if found else 0.0


def read(name: str) -> list[dict]:
    """Load one of the report CSVs."""
    path = DATA / name
    if not path.exists():
        raise SystemExit(f"{path} is missing: run etsy_insights.py report first")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write(name: str, rows: list[dict]) -> Path:
    """Write rows as a CSV Excel opens cleanly."""
    path = DATA / name
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)
    return path


def families(rules: dict, *, verbose: bool) -> list[dict]:
    """Sum every term Etsy returned into the first family whose pattern it matches."""
    licensed = re.compile(rules["licensed"])
    physical = re.compile(rules["physical"])
    patterns = [(name, re.compile(rx)) for name, rx in rules["families"]]

    terms: dict[str, dict] = {}
    for name in ("similar.csv", "seeds.csv"):  # a seed's own row is the exact one: it wins
        for row in read(name):
            term = row["term"].lower()
            terms[term] = {
                "term": term,
                "searches": number(row["searches_30d"]),
                "conversion": row["conversion"],
            }

    grouped: dict[str, list[dict]] = {name: [] for name, _ in patterns}
    for term, row in terms.items():
        if physical.search(term):
            continue
        for name, pattern in patterns:
            if pattern.search(term):
                grouped[name].append(row)
                break

    out = []
    for name, rows in grouped.items():
        rows.sort(key=lambda r: -r["searches"])
        total = sum(r["searches"] for r in rows)
        clean = [r for r in rows if not licensed.search(r["term"])]
        clean_total = sum(r["searches"] for r in clean)
        high = sum(r["searches"] for r in rows if r["conversion"] in HIGH)
        out.append(
            {
                "family": name,
                "terms": len(rows),
                "searches_30d": total,
                "searches_without_licensed": clean_total,
                "licensed_share_pct": round(100 * (total - clean_total) / total) if total else 0,
                "high_conversion_share_pct": round(100 * high / total) if total else 0,
                "top_terms": "; ".join(f"{r['term']} {r['searches']}" for r in clean[:8]),
            }
        )
        if verbose:
            print(f"\n{name}")
            for r in rows[:25]:
                flag = "licensed" if licensed.search(r["term"]) else ""
                print(f"  {r['term'][:60]:60} {r['searches']:>6} {r['conversion']:10} {flag}")
    out.sort(key=lambda r: -r["searches_30d"])
    return out


def price_classes(rules: dict) -> list[dict]:
    """Split the competing listings by how they are made and report what each class asks."""
    classes = {name: re.compile(rx, re.IGNORECASE) for name, rx in rules["listing_classes"].items()}

    def klass(title: str) -> str:
        if not classes["video"].search(title):
            return "not video"
        if classes["template"].search(title):
            return "video template"
        if classes["made_to_order"].search(title):
            return "video made to order"
        return "video, unclear"

    seen: dict[str, dict] = {}
    for row in read("listings.csv"):  # one listing answers many searches; count it once
        seen.setdefault(row["url"], row)

    prices = defaultdict(list)
    shops = defaultdict(set)
    for row in seen.values():
        name = klass(row["title"])
        prices[name].append(money(row["price"]))
        shops[name].add(row["shop"])

    out = []
    for name, values in sorted(prices.items(), key=lambda kv: statistics.median(kv[1])):
        enough = len(values) >= QUARTILE_MIN
        quartiles = statistics.quantiles(values, n=4) if enough else [values[0]] * 3
        out.append(
            {
                "class": name,
                "listings": len(values),
                "shops": len(shops[name]),
                "price_p25": round(quartiles[0], 2),
                "price_median": round(quartiles[1], 2),
                "price_p75": round(quartiles[2], 2),
                "price_max": round(max(values), 2),
            }
        )
    return out


def main() -> None:
    """Build both tables and print them."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--rules", required=True, help="the family and class patterns (JSON)")
    parser.add_argument("--verbose", action="store_true", help="print the terms behind each family")
    args = parser.parse_args()
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))

    fam = families(rules, verbose=args.verbose)
    print(
        f"\n{'family':40} {'terms':>5} {'searches':>8} {'unlicensed':>10} "
        f"{'licensed':>8} {'high conv':>9}"
    )
    for r in fam:
        print(
            f"{r['family']:40} {r['terms']:>5} {r['searches_30d']:>8} "
            f"{r['searches_without_licensed']:>10} {r['licensed_share_pct']:>7}% "
            f"{r['high_conversion_share_pct']:>8}%"
        )
    print(write("families.csv", fam))

    cls = price_classes(rules)
    print(f"\n{'class':22} {'listings':>8} {'shops':>6} {'p25':>8} {'median':>8} {'p75':>8}")
    for r in cls:
        print(
            f"{r['class']:22} {r['listings']:>8} {r['shops']:>6} "
            f"${r['price_p25']:>7.2f} ${r['price_median']:>7.2f} ${r['price_p75']:>7.2f}"
        )
    print(write("price_classes.csv", cls))


if __name__ == "__main__":
    main()
