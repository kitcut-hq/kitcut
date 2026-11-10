#!/usr/bin/env python
"""A research film's documents and sources, checked before a film is made of them.

The checks an agent runs on its own research when nobody re-reads it (docs/autonomous-research-
films.md); _research.py says what each one looks at. Free: no AI, no credits. --sources reads
pages on the public internet only.

    --fact doc1.md --chart doc2.md --script doc3.md
                        the documents together: the script's length, every spoken number backed
                        by the fact sheet, labels, sources, "must not say", chart values
    --fact doc1.md --sources
                        every fact-sheet row with a url and a quote, read on its page: the quote is
                        there, something close is, only its number is, or it is not (at most
                        _research.MAX_SOURCES rows a run; --skip N for the next ones)
    --input req.json    the same from one JSON file -- {"fact", "chart", "script"}, or {"sources":
                        [{url, quote, number?, id?}], "skip"} or {"fact", "skip"} to read pages --
                        answered as JSON (the studio's /api/research endpoints run this)
    --json              answer as JSON

Exit 0 when nothing was found, 1 when something was, 2 when the input is wrong.

Invoke as:
    python scripts/research-check.py --fact doc1.md --chart doc2.md --script doc3.md
    python scripts/research-check.py --fact facts/31-facts.md --sources
"""

import argparse
import asyncio
import importlib
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _research as R  # noqa: E402
import _web  # noqa: E402

TEXT_MAX = 400_000  # a filing's words, read in the browser


def fetch(url):
    """A page's words by a plain fetch (the SEC hears who we are)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    body, ctype, _ = _web.fetch(url, ua=_web.ua_for(host))
    text = body.decode("utf-8", "replace")
    return R._plain(text) if "html" in (ctype or "") or "<html" in text[:2000].lower() else text


def browse(url):
    """A page's words as a real browser sees them: for a page that refuses a plain fetch."""
    grab = importlib.import_module("web-grab")
    _, facts, _, _ = asyncio.run(grab._browse(url, (1280, 1600), settle_s=2.0, text_max=TEXT_MAX))
    return facts.get("text") or ""


def read(path):
    with open(_env.resolve(path), encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fact", help="doc1, the fact sheet")
    ap.add_argument("--chart", help="doc2, the chart data")
    ap.add_argument("--script", help="doc3, the script, word for word")
    ap.add_argument(
        "--sources", action="store_true", help="read the fact sheet's rows on their pages"
    )
    ap.add_argument("--skip", type=int, default=0, help="--sources: start after this many rows")
    ap.add_argument("--input", help="a JSON request (the studio's endpoints)")
    ap.add_argument("--no-browser", action="store_true", help="--sources: plain fetches only")
    ap.add_argument("--json", action="store_true", help="answer as JSON")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    req = None
    if a.input:
        try:
            req = json.loads(read(a.input))
        except (OSError, ValueError) as e:
            print(json.dumps({"error": "the request is not JSON: %s" % e}))
            return 2
    if req is not None and ("sources" in req or "skip" in req) or a.sources:
        if req is not None:
            rows = req.get("sources") if "sources" in req else R.rows_of(req.get("fact") or "")
            a.skip = max(0, int(req.get("skip") or 0))
        else:
            rows = R.rows_of(read(a.fact)) if a.fact else None
        if not isinstance(rows, list):
            print("--sources needs --fact (or an --input with sources)")
            return 2
        rows = [r for r in rows if isinstance(r, dict)][a.skip :]
        got = R.sources(rows, fetch=fetch, browse=None if a.no_browser else browse)
        out = {
            "sources": got,
            "left": max(0, len(rows) - R.MAX_SOURCES),
            "next_skip": a.skip + len(got),
        }
        bad = [g for g in got if g["state"] not in ("found", "close")]
    else:
        docs = req or {
            "fact": read(a.fact) if a.fact else "",
            "chart": read(a.chart) if a.chart else "",
            "script": read(a.script) if a.script else "",
        }
        if not all(isinstance(docs.get(k, ""), str) for k in ("fact", "chart", "script")):
            print(json.dumps({"error": "fact, chart and script are texts"}))
            return 2
        out = R.check(docs.get("fact", ""), docs.get("chart", ""), docs.get("script", ""))
        bad = out["findings"]
    if a.json or a.input:
        print(json.dumps(out, ensure_ascii=False))
        return 1 if bad else 0
    if "sources" in out:
        for g in out["sources"]:
            print("%-10s %s  %s" % (g["state"], g["id"][:60], g["url"][:90]))
            if g["state"] in ("close", "missing") and g["page"]:
                print("           the page: %s" % g["page"][:160])
            if g["note"]:
                print("           %s" % g["note"])
        if out["left"]:
            print("%d more rows: run again with --skip %d" % (out["left"], a.skip + R.MAX_SOURCES))
        return 1 if bad else 0
    s = out["script"]
    print(
        "script: %d lines (%s to %s), %d words, about %.1f minutes: ask for %d s"
        % (s["lines"], s["first"], s["last"], s["words"], s["minutes"], s["seconds"])
    )
    for f in out["findings"]:
        print("  %-9s %s" % (f["kind"], f["what"]))
    print("nothing found" if not out["findings"] else "%d finding(s)" % len(out["findings"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
