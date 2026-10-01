#!/usr/bin/env python
"""Where a film's YouTube draft spent its time, for every draft written in the last days: how long
until the words (title, description, tags) were out, until the thumbnails' picks were, how long
the four thumbnail pictures took to make, what it cost and what was put right. Read from the
drafts' own records, so "why is it slow" is answered from real numbers.

    python studio/draft_times.py [--days 7] [--json]

The records (ytdraft.py, thumbs.py) under STUDIO_HOME/projects/<film>/youtube/:
    draft-<channel>.json   seconds: until the words (since 2026-10-01: before it, the whole draft);
                           seconds_thumbnails: until the picks; cost_usd; notes; effort; at
    thumbs-<channel>.json  seconds: making the four pictures
On the Azure VM: `bash studio/deploy/ops.sh drafts [--days N]`. Reads only.
"""

import os
import sys
import json
import time
import argparse


def rows(home, days):
    root = os.path.join(home, "projects")
    since = time.time() - days * 86400
    out = []
    try:
        films = os.listdir(root)
    except OSError:
        return out
    for film in films:
        yt = os.path.join(root, film, "youtube")
        try:
            names = os.listdir(yt)
        except OSError:
            continue
        for name in names:
            if not (name.startswith("draft-") and name.endswith(".json")):
                continue
            path = os.path.join(yt, name)
            if os.path.getmtime(path) < since:
                continue
            channel = name[len("draft-") : -len(".json")]
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            th = {}
            try:
                with open(os.path.join(yt, "thumbs-%s.json" % channel), encoding="utf-8") as f:
                    th = json.load(f)
            except (OSError, ValueError):
                pass
            out.append(
                {
                    "at": d.get("at") or "",
                    "film": film,
                    "channel": channel,
                    "words_s": d.get("seconds"),
                    "picks_s": d.get("seconds_thumbnails"),
                    "pictures_s": th.get("seconds"),
                    "effort": d.get("effort") or "",
                    "cost_usd": d.get("cost_usd"),
                    "notes": "; ".join(d.get("notes") or [])[:80],
                }
            )
    return sorted(out, key=lambda r: r["at"], reverse=True)


def show(v):
    return "-" if v is None else ("%.1f" % v if isinstance(v, float) else str(v))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    home = os.environ.get("STUDIO_HOME") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "studio-home"
    )
    rs = rows(home, a.days)
    if a.json:
        print(json.dumps(rs, indent=1, ensure_ascii=False))
        return
    if not rs:
        print("no drafts written in the last %g days" % a.days)
        return
    print(
        "%-19s %-29s %-10s %7s %7s %9s %-6s %8s  %s"
        % ("at", "film", "channel", "words", "picks", "pictures", "effort", "cost", "notes")
    )
    for r in rs:
        print(
            "%-19s %-29s %-10s %7s %7s %9s %-6s %8s  %s"
            % (
                r["at"],
                r["film"][:29],
                r["channel"][:10],
                show(r["words_s"]),
                show(r["picks_s"]),
                show(r["pictures_s"]),
                r["effort"],
                "-" if r["cost_usd"] is None else "$%.3f" % r["cost_usd"],
                r["notes"],
            )
        )

    def mid(k):
        v = sorted(x[k] for x in rs if isinstance(x[k], (int, float)))
        return ("%.1f s" % v[len(v) // 2]) if v else "-"

    print(
        "\n%d drafts; median words %s, picks %s, pictures %s"
        % (len(rs), mid("words_s"), mid("picks_s"), mid("pictures_s"))
    )


if __name__ == "__main__":
    sys.exit(main())
