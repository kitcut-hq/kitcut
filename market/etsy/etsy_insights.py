"""Etsy keyword research from the seller's own Marketplace Insights data.

Etsy's Shop Manager has a keyword tool (Marketplace Insights) with no export.
This reads the same data the page reads, for a list of search terms, and writes
it as JSON (one file per term, cached) and as CSV reports:

  per term      searches in the last 30 days, competing listings, conversion
                rating, the median price band of recent purchases, week-on-week
                change, the 20 listings Etsy shows as the competition
  similar       the "Similar terms" and "Exploratory ideas" lists (the page
                shows 9 rows at a time; the call returns all of them)
  trend         12 months of monthly search volume (seasonality)

It needs the signed-in seller's cookie. Put the request headers in
market/etsy/local/headers.txt (gitignored), one "name: value" per line, at
least `cookie:` and `user-agent:` -- copy them from any www.etsy.com request in
the browser's DevTools (Copy as cURL). The file is handed to curl with
-H @file, so the cookie never appears on a command line. The cookie's
session-binding part expires after 16 minutes but Etsy re-issues it; the
session key itself lasts months.

Requests go through curl, not urllib: Etsy sits behind DataDome, which
fingerprints the TLS handshake, and curl's is one it lets through. The public
shop pages (etsy.com/search, /listing) answer 403 with a captcha -- do not add
them here. Requests are spaced out on purpose; this is the seller's own
session and there is no reason to hammer it.

Invoke as:
    python market/etsy/etsy_insights.py check
    python market/etsy/etsy_insights.py terms --file market/etsy/seeds/video-services.txt --plan
    python market/etsy/etsy_insights.py terms "video invitation" "save the date video"
    python market/etsy/etsy_insights.py trend --file market/etsy/seeds/video-services.txt
    python market/etsy/etsy_insights.py report
"""

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "local"
DATA = HERE / "data"
BASE = "https://www.etsy.com"
INSIGHTS = BASE + "/your/shops/me/marketplace-insights"
API = BASE + "/api/v3/ajax/bespoke/shop/{shop}/marketplace-insights"
LISTS = {"phrase": "Similar terms", "any_phrase": "Exploratory ideas"}
CONVERSION = {0: "Very Low", 1: "Low", 2: "Average", 3: "High", 4: "Very High"}
TREND_BATCH = 3  # chart-series-data answers for at most three terms a call
PAUSE = (1.2, 2.6)  # seconds between requests

AJAX = [
    "accept: */*",
    "content-type: application/json",
    "origin: " + BASE,
    "referer: " + INSIGHTS,
    "sec-fetch-dest: empty",
    "sec-fetch-mode: cors",
    "sec-fetch-site: same-origin",
    "x-detected-locale: USD|en-US|US",
    "x-transform-response: camel-case",
]
PAGE = [
    "accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "sec-fetch-dest: document",
    "sec-fetch-mode: navigate",
    "sec-fetch-site: same-origin",
    "upgrade-insecure-requests: 1",
]

_last = [0.0]


def slug(term: str) -> str:
    """Return the term as a file name."""
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def curl(url: str, headers: list[str], body: dict | None = None) -> str:
    """Make one spaced-out request with the session headers; return the body or exit."""
    hfile = LOCAL / "headers.txt"
    if not hfile.exists():
        raise SystemExit(f"no session headers: put cookie: and user-agent: lines in {hfile}")
    wait = random.uniform(*PAUSE) - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    cmd = [
        "curl",
        "-sS",
        "--compressed",
        "--max-time",
        "60",
        "-w",
        "\n%{http_code}",
        "-H",
        f"@{hfile}",
    ]
    for h in headers:
        cmd += ["-H", h]
    if body is not None:
        cmd += ["--data-raw", json.dumps(body)]
    out = subprocess.run(
        [*cmd, url], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    _last[0] = time.monotonic()
    text, _, status = out.stdout.rpartition("\n")
    if out.returncode or status != "200":
        hint = (
            " (captcha: the session was challenged, refresh the cookie)"
            if "captcha" in text
            else ""
        )
        raise SystemExit(f"HTTP {status or out.stderr.strip()} for {url}{hint}")
    return text


def embedded(html: str, key: str) -> dict:
    """Return the JSON object the page embeds under "key": {...}."""
    i = html.find(f'"{key}":')
    if i < 0:
        raise SystemExit(f"the page carries no {key!r}: signed out, or Etsy changed the page")
    return json.JSONDecoder().raw_decode(html[html.find("{", i) :])[0]


def load_page(term: str | None = None) -> tuple[str, str]:
    """Fetch the Insights landing or results page; returns (html, csrf nonce)."""
    url = INSIGHTS
    if term:
        url += "/search?" + urllib.parse.urlencode(
            {"query": term, "search_trigger": "results_search_bar"}
        )
    html = curl(url, PAGE)
    nonce = re.search(r'name="csrf_nonce" content="([^"]+)"', html)
    if not nonce:
        raise SystemExit("no csrf nonce on the page: the session is signed out")
    return html, nonce.group(1)


def shop_id() -> str:
    """Return the numeric shop id, read off the Insights page once and remembered."""
    cache = LOCAL / "shop.json"
    if cache.exists():
        return str(json.loads(cache.read_text(encoding="utf-8"))["shop_id"])
    html, _ = load_page()
    shop = embedded(html, "current_shop")
    cache.write_text(
        json.dumps({"shop_id": shop["shop_id"], "shop_name": shop.get("shop_name")}),
        encoding="utf-8",
    )
    return str(shop["shop_id"])


def read_terms(args: argparse.Namespace) -> list[str]:
    """Collect the terms from the command line and --file, in order, without repeats."""
    terms = list(args.terms)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            term = line.split("#")[0].strip()
            if term:
                terms.append(term)
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if not out:
        raise SystemExit("no terms: name some or pass --file")
    return out


def cmd_check(_args: argparse.Namespace) -> int:
    """Confirm the session is signed in and remember which shop it is."""
    html, _ = load_page()
    shop = embedded(html, "current_shop")
    print(f"signed in: shop {shop.get('shop_name')} ({shop['shop_id']})")
    (LOCAL / "shop.json").write_text(
        json.dumps({"shop_id": shop["shop_id"], "shop_name": shop.get("shop_name")}),
        encoding="utf-8",
    )
    return 0


def cmd_terms(args: argparse.Namespace) -> int:
    """Fetch stats, price band, competing listings and similar terms for each term."""
    terms = read_terms(args)
    out = DATA / "terms"
    todo = [t for t in terms if args.refresh or not (out / f"{slug(t)}.json").exists()]
    print(
        f"{len(terms)} terms, {len(terms) - len(todo)} cached, {len(todo)} to fetch = "
        f"{len(todo) * 3} requests, about {len(todo) * 3 * 2 // 60 + 1} min"
    )
    if args.plan:
        for t in todo:
            print("  ", t)
        return 0
    out.mkdir(parents=True, exist_ok=True)
    shop = shop_id()
    for n, term in enumerate(todo, 1):
        html, _ = load_page(term)
        page = embedded(html, "marketplace_insights_search")
        if page.get("isQuotaReached") or not page.get("isSearchAllowed", True):
            quota = page.get("quotaData")
            raise SystemExit(
                f"Etsy refused the lookup for {term!r}: weekly quota reached ({quota})"
            )
        record = {
            "term": term,
            "fetched": time.strftime("%Y-%m-%d"),
            "stats": page.get("stats"),
            "wow": page.get("wowData"),
            "price": (page.get("competitivePriceData") or {}).get("searchTermMedianPrice"),
            "daily": (page.get("dailyStats") or {}).get("stats"),
            "listings": (page.get("competitiveResearchListingCards") or {}).get("listingCards"),
            "similar": {},
        }
        for kind in LISTS:
            query = urllib.parse.urlencode(
                {"search_term_hash": "", "search_term": term, "search_term_type": kind}
            )
            url = f"{API.format(shop=shop)}/similar-search-terms?{query}"
            record["similar"][kind] = json.loads(curl(url, AJAX)).get("results") or []
        (out / f"{slug(term)}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        s = record["stats"] or {}
        p = record["price"] or {}
        band = f"{p.get('medianPriceLow') or '?'}-{p.get('medianPriceHigh') or '?'}"
        print(
            f"[{n}/{len(todo)}] {term}: {s.get('searchVolume')} searches, "
            f"{s.get('avgTotalListings')} listings, {CONVERSION.get(s.get('cvr'), '?')}, {band}, "
            f"{len(record['similar']['phrase'])}+{len(record['similar']['any_phrase'])} similar"
        )
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    """Fetch the search-volume series for each term, three terms a request."""
    terms = read_terms(args)
    out = DATA / "trend"
    todo = [t for t in terms if args.refresh or not (out / f"{slug(t)}.json").exists()]
    calls = -(-len(todo) // TREND_BATCH)
    print(
        f"{len(terms)} terms, {len(todo)} to fetch = {calls} requests "
        f"({TREND_BATCH} terms each), {args.days} days"
    )
    if args.plan or not todo:
        return 0
    out.mkdir(parents=True, exist_ok=True)
    shop = shop_id()
    _, nonce = load_page()
    url = f"{API.format(shop=shop)}/chart-series-data"
    for i in range(0, len(todo), TREND_BATCH):
        batch = todo[i : i + TREND_BATCH]
        body = {
            "search_terms": batch,
            "days": args.days,
            "include_trendline": False,
            "include_wow_data": False,
            "include_search_volume": True,
            "include_avg_total_listings": True,
        }
        data = json.loads(curl(url, [*AJAX, f"x-csrf-token: {nonce}"], body))
        totals = {t["searchTerm"].lower(): t for t in data.get("termSummaries") or []}
        got = set()
        for series in data.get("series") or []:
            if series.get("seriesType") != "search_volume":
                continue
            term = series["searchTerm"]
            got.add(term.lower())
            record = {
                "term": term,
                "fetched": time.strftime("%Y-%m-%d"),
                "days": data.get("days"),
                "granularity": data.get("granularity"),
                "last_bucket_partial": data.get("isLastBucketPartial"),
                "total": totals.get(term.lower()),
                "points": [{"label": p["label"], "value": p["value"]} for p in series["points"]],
            }
            (out / f"{slug(term)}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
            print(f"  {term}: " + " ".join(f"{p['value']}" for p in record["points"]))
        for t in batch:
            if t.lower() not in got:
                print(f"  {t}: no data")
    return 0


def cmd_report(_args: argparse.Namespace) -> int:
    """Write seeds.csv, similar.csv, listings.csv and trend.csv from the cache."""
    records = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "terms").glob("*.json"))
    ]
    if not records:
        raise SystemExit("nothing fetched yet: run `terms` first")
    seeds = {r["term"].lower() for r in records}

    def write(name: str, header: list[str], rows: list[list]) -> None:
        path = DATA / name
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        print(f"{path} ({len(rows)} rows)")

    rows = []
    for r in records:
        s, p, w = r.get("stats") or {}, r.get("price") or {}, r.get("wow") or {}
        vol, lst = s.get("searchVolume") or 0, s.get("avgTotalListings") or 0
        rows.append(
            [
                r["term"],
                vol,
                lst,
                round(vol / lst * 1000, 2) if lst else "",
                CONVERSION.get(s.get("cvr"), ""),
                f"{s['queryCvr'] * 100:.3f}" if s.get("queryCvr") is not None else "",
                p.get("medianPriceLow", ""),
                p.get("medianPriceHigh", ""),
                w.get("displayText", ""),
                r.get("fetched", ""),
            ]
        )
    rows.sort(key=lambda x: -x[1])
    write(
        "seeds.csv",
        [
            "term",
            "searches_30d",
            "listings",
            "searches_per_1000_listings",
            "conversion",
            "conversion_pct",
            "median_price_low",
            "median_price_high",
            "week_on_week",
            "fetched",
        ],
        rows,
    )

    merged: dict[str, dict] = {}
    for r in records:
        for kind, label in LISTS.items():
            for x in (r.get("similar") or {}).get(kind) or []:
                key = x["searchTerm"].lower()
                m = merged.setdefault(key, {"x": x, "lists": set(), "seeds": set()})
                m["lists"].add(label)
                m["seeds"].add(r["term"])
    rows = []
    for key, m in merged.items():
        x = m["x"]
        vol, lst = x.get("searchVolume") or 0, x.get("avgTotalListings") or 0
        rows.append(
            [
                x["searchTerm"],
                vol,
                lst,
                round(vol / lst * 1000, 2) if lst else "",
                CONVERSION.get(x.get("cvr"), ""),
                x.get("cvr", ""),
                "yes" if key in seeds else "",
                len(m["seeds"]),
                " | ".join(sorted(m["seeds"])),
                " + ".join(sorted(m["lists"])),
            ]
        )
    rows.sort(key=lambda x: -x[1])
    write(
        "similar.csv",
        [
            "term",
            "searches_30d",
            "listings",
            "searches_per_1000_listings",
            "conversion",
            "conversion_bucket",
            "is_seed",
            "seed_count",
            "seeds",
            "lists",
        ],
        rows,
    )

    rows = []
    for r in records:
        for rank, c in enumerate(r.get("listings") or [], 1):
            price = c.get("price") or {}
            rows.append(
                [
                    r["term"],
                    rank,
                    c.get("title"),
                    price.get("formattedPrice"),
                    price.get("formattedOriginalPrice") or "",
                    c.get("shopName"),
                    c.get("rating"),
                    c.get("numberOfReviews"),
                    c.get("badgeText") or "",
                    "yes" if c.get("isStarSeller") else "",
                    c.get("listingUrl"),
                ]
            )
    write(
        "listings.csv",
        [
            "term",
            "rank",
            "title",
            "price",
            "price_before_discount",
            "shop",
            "rating",
            "shop_reviews",
            "badge",
            "star_seller",
            "url",
        ],
        rows,
    )

    trends = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "trend").glob("*.json"))
    ]
    if trends:
        labels = [p["label"] for p in max(trends, key=lambda t: len(t["points"]))["points"]]
        rows = []
        for t in trends:
            by = {p["label"]: p["value"] for p in t["points"]}
            vals = [v for v in by.values() if v]
            peak = max(by, key=by.get) if vals else ""
            rows.append(
                [t["term"], (t.get("total") or {}).get("searchVolume", ""), peak]
                + [by.get(label, "") for label in labels]
            )
        rows.sort(key=lambda x: -(x[1] or 0))
        write("trend.csv", ["term", "searches_total", "peak", *labels], rows)
    return 0


def main() -> int:
    """Parse the command line and run one subcommand."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="confirm the session works and remember the shop id").set_defaults(
        fn=cmd_check
    )
    for name, fn, text in (
        ("terms", cmd_terms, "stats, prices, competition and similar terms per term"),
        ("trend", cmd_trend, "monthly search volume per term"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("terms", nargs="*", help="search terms")
        p.add_argument("--file", help="a text file of terms, one per line, # for comments")
        p.add_argument("--plan", action="store_true", help="say what would be fetched and stop")
        p.add_argument("--refresh", action="store_true", help="fetch again even if cached")
        if name == "trend":
            p.add_argument("--days", type=int, default=365, help="30 gives days, 365 gives months")
        p.set_defaults(fn=fn)
    sub.add_parser("report", help="write the CSV reports from everything cached").set_defaults(
        fn=cmd_report
    )
    args = ap.parse_args()
    LOCAL.mkdir(exist_ok=True)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
