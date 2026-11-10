"""Google Trends' trending searches right now, per country, from its public RSS feed.

Prints, for each country: approximate traffic, the search, when it started trending, and the top
news headline Google attached to it. Mostly sports and celebrities; useful to catch a spike on a
name, not to find a beat.

Invoke as: python -I trends.py [GEO ...]      (default: US GB CA AU)
"""

# ruff: noqa: INP001, T201  (a helper beside a skill, not a package; printing is its output)

import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator

sys.stdout.reconfigure(encoding="utf-8")
NS = {"ht": "https://trends.google.com/trending/rss"}
FEED = "https://trends.google.com/trending/rss?geo={}"


def trending(geo: str) -> Iterator[tuple[str, str, str, str]]:
    """(traffic, search, started, top headline) for each trending search in one country."""
    req = urllib.request.Request(FEED.format(geo), headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
    # The URL is the fixed https feed above; only the country code varies.
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        root = ET.fromstring(r.read())  # noqa: S314  (Google's own feed)
    for item in root.iter("item"):
        news = item.find("ht:news_item", NS)
        headline = "" if news is None else news.findtext("ht:news_item_title", "", NS)
        yield (
            item.findtext("ht:approx_traffic", "", NS),
            item.findtext("title", ""),
            item.findtext("pubDate", "")[5:22],
            headline,
        )


def main(geos: list[str]) -> None:
    """Print the trending searches for each country."""
    for geo in geos:
        print(f"\n##### {geo}")
        for traffic, title, date, headline in trending(geo):
            print(f"{traffic:>8} | {title[:40]:40} | {date} | {headline[:80]}")


if __name__ == "__main__":
    main([g.upper() for g in sys.argv[1:]] or ["US", "GB", "CA", "AU"])
