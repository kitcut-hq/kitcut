"""What is hot and what is climbing on Hacker News right now, as one ranked table.

Reads the official HN API (front-page order) and Algolia's HN search (points, comments and age
for the front page, the last 24 hours' big stories and the last 8 hours' climbers), merges them
by story, and ranks by points per hour since posting, the measure of "fast-growing" that needs
no memory between runs. Public APIs, no key, no sign-in, stdlib only.

Invoke as: python3 -I hn.py [--limit 40] [--json]
"""

# ruff: noqa: INP001, T201  (a helper beside a routine, not a package; printing is its output)

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

FIREBASE_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
ALGOLIA = "https://hn.algolia.com/api/v1"
TRIES = 2


def get(url: str) -> object:
    """GET a JSON document, with one retry."""
    req = urllib.request.Request(url, headers={"User-Agent": "kitcut-hn-scout/1"})  # noqa: S310
    for attempt in range(1, TRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
                return json.load(r)
        except OSError:
            if attempt == TRIES:
                raise
            time.sleep(2)
    return None


def main() -> None:
    """Fetch, merge, rank, print."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=40, help="rows to print (default 40)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args()

    now = int(time.time())
    urls = {
        "top": FIREBASE_TOP,
        "front": f"{ALGOLIA}/search?tags=front_page&hitsPerPage=60",
        "day": f"{ALGOLIA}/search_by_date?tags=story&hitsPerPage=60"
        f"&numericFilters=created_at_i>{now - 86400},points>100",
        "rising": f"{ALGOLIA}/search_by_date?tags=story&hitsPerPage=60"
        f"&numericFilters=created_at_i>{now - 8 * 3600},points>15",
    }
    try:
        with ThreadPoolExecutor(4) as pool:
            got = dict(zip(urls, pool.map(get, urls.values()), strict=True))
    except OSError as e:
        sys.exit(
            f"HN unreachable from here ({e}). Read the same data with WebFetch instead:\n"
            + "\n".join(urls.values())
        )

    rank = {str(i): n for n, i in enumerate(got["top"][:90], 1)}
    stories: dict[str, dict] = {}
    for src in ("front", "day", "rising"):
        for h in got[src].get("hits", []):
            sid = h["objectID"]
            age_h = max((now - h["created_at_i"]) / 3600, 0.5)
            pts, com = h.get("points") or 0, h.get("num_comments") or 0
            s = stories.setdefault(
                sid,
                {
                    "id": sid,
                    "title": h.get("title") or "",
                    "domain": urlparse(h.get("url") or "").netloc.removeprefix("www."),
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                    "hn": f"https://news.ycombinator.com/item?id={sid}",
                    "points": pts,
                    "comments": com,
                    "age_h": round(age_h, 1),
                    "pts_per_h": round(pts / age_h, 1),
                    "com_per_h": round(com / age_h, 1),
                    "front_rank": rank.get(sid),
                    "seen_in": [],
                },
            )
            s["seen_in"].append(src)

    rows = sorted(stories.values(), key=lambda s: -s["pts_per_h"])[: args.limit]
    if args.json:
        print(json.dumps({"fetched_utc": now, "stories": rows}, indent=1))
        return
    print(f"HN at {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}, ranked by points/hour")
    print(f"{'pts/h':>6} {'pts':>5} {'com':>4} {'age':>5} {'rank':>4}  title  (domain)  hn")
    for s in rows:
        r = s["front_rank"] or "-"
        print(
            f"{s['pts_per_h']:>6} {s['points']:>5} {s['comments']:>4} {s['age_h']:>4}h {r:>4}  "
            f"{s['title']}  ({s['domain']})  {s['hn']}"
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
