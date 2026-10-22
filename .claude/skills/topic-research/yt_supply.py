"""Print a saved market-data search_videos result as one line per video.

The search_videos tool saves big answers to a file instead of returning them; this reads that file
and prints, per query: views, views a day, publish date, length, language, channel and title,
in the order the tool ranked them.

Invoke as: python -I yt_supply.py <saved result> [<saved result> ...]
"""

# ruff: noqa: INP001, T201  (a helper beside a skill, not a package; printing is its output)

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def line(v: dict) -> str:
    """One video as a fixed-width line."""
    views, per_day = v.get("views", 0), int(v.get("views_per_day") or 0)
    when, secs = v.get("published_at", "")[:10], v.get("duration_seconds", 0)
    lang, channel, title = v.get("language") or "", v.get("channel", "")[:22], v.get("title", "")
    return f"{views:>10,} {per_day:>8,}/d {when} {secs:>6}s {lang:6}| {channel:22} | {title[:90]}"


def main(paths: list[str]) -> None:
    """Print every query in every saved result."""
    for path in paths:
        with Path(path).open(encoding="utf-8") as f:
            data = json.load(f)
        for result in data.get("results", []):
            print(f"\n=== {result.get('query')} | about {result.get('total_estimate')} results")
            for v in result.get("videos", []):
                print(line(v))


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(__doc__)
    main(sys.argv[1:])
