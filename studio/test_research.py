"""A research film's documents and sources, checked for an agent (scripts/_research.py, the
studio's /api/research endpoints), with no network: python studio/test_research.py

Numbers as a narrator says them, backed or not by the fact sheet; a fact sheet's rows without a
label, a url or a quote; a "must not say" phrase said; a chart value from nowhere; a quote found,
paraphrased, invented, or on a page that will not open; then both endpoints end to end.
"""

import os
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-research-test-")
os.environ["STUDIO_HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402 -- imports agent, which imports _env first

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _research as R  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

FACT = """# Fact sheet

## The money

| number | what | label | source | url | quote |
|---|---|---|---|---|---|
| $16.3B | revenue, first half | REPORTED | WSJ | https://example.com/a | revenue rose to $16.3 billion in six months |
| $965B | Series H valuation | CLAIM | Anthropic | https://example.com/b | a post-money valuation of $965 billion |
| ~810,000 | homes a gigawatt supplies | ESTIMATE (our arithmetic) | EIA | | |
| 2.2% | what innovators keep | MEASURED | NBER | | |
| 42% | share of compute | | SemiAnalysis | https://example.com/c | 42% of compute |

## The film must not say

- "lost $80 billion" without the non-cash part.
- That Anthropic is profitable without "adjusted".
"""
CHART = """## C1. Revenue · L01

| period | $ billion | label |
|---|---|---|
| H1 2026 | 16.3 | REPORTED |
| H2 2026 | 31.0 | ESTIMATE |
"""
SCRIPT = """## OPENING

- L01. *Chart C1.*
  "Revenue was sixteen point three billion dollars in six months, at a nine hundred and sixty-five billion dollar valuation."
- L02. *The homes.*
  "One gigawatt powers about eight hundred thousand homes, in twenty twenty-six."
- L03. *The loss.*
  "It lost eighty billion dollars, and seventy-three point five percent of it is gone."
"""


def main():
    fails = []

    def check(ok, what, detail=""):
        print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)))
        if not ok:
            fails.append(what)

    said = R.spoken_numbers
    check(said("sixteen point three billion")[0][0] == 16.3e9, "a decimal and a scale, in words")
    check(said("nine hundred and sixty-five billion")[0][0] == 965e9, "hundreds, and, hyphens")
    check(said("a hundred and eleven billion")[0][0] == 111e9, '"a hundred"')
    check(said("sixty-one and a half billion")[0][0] == 61.5e9, '"and a half"')
    check(
        said("in twenty twenty-six and two thousand and twenty-five") == [], "years are not facts"
    )
    check(said("one of those numbers, two of them") == [], "nor the small counts of speech")
    check([v for v, _ in said("2,061 gigawatts, 42 percent")] == [2061, 42], "digits too")
    check(16.3e9 in R.written_numbers("$16.3B") and 30 in R.written_numbers("~30x"), "as written")

    got = R.check(FACT, CHART, SCRIPT)
    kinds = [(f["kind"], f["where"]) for f in got["findings"]]
    whats = " | ".join(f["what"] for f in got["findings"])
    check(
        got["script"]["lines"] == 3 and got["script"]["words"] > 30,
        "the script is read",
        got["script"],
    )
    check(("number", "L01") not in kinds, "backed numbers pass", whats)
    check(("number", "L02") not in kinds, "a hedged rounding passes (about 810,000)", whats)
    check(
        any(
            k == ("number", "L03") and "seventy three point five" in f["what"]
            for k, f in zip(kinds, got["findings"], strict=True)
        ),
        "a number from nowhere is named",
        whats,
    )
    check(
        any(f["kind"] == "must_not" and "lost $80 billion" in f["what"] for f in got["findings"]),
        "a must-not phrase said",
        whats,
    )
    check(
        not any(f["kind"] == "must_not" and "adjusted" in f["what"] for f in got["findings"]),
        "a quoted word inside a rule is not a phrase",
        whats,
    )
    check(
        any(f["kind"] == "label" and "42%" in f["what"] for f in got["findings"]),
        "a row with no label",
        whats,
    )
    check(
        any(f["kind"] == "source" and "2.2%" in f["what"] for f in got["findings"]),
        "a MEASURED row with no url",
        whats,
    )
    check(
        not any("810,000" in f["what"] for f in got["findings"]), "an ESTIMATE needs no url", whats
    )
    check(
        any(f["kind"] == "chart" and "31.0" in f["what"] for f in got["findings"]),
        "a chart value from nowhere",
        whats,
    )
    check(
        not any(f["kind"] == "chart" and "16.3" in f["what"] for f in got["findings"]),
        "a chart value in $ billion is backed",
        whats,
    )

    rows = R.rows_of(FACT)
    check(
        [r["url"] for r in rows]
        == ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        "rows with a url and a quote",
        rows,
    )
    pages = {
        "https://example.com/a": "Its revenue rose to $16.3 billion in six months, the draft shows.",
        "https://example.com/b": "Investors put the company at $965 billion after the round.",
    }

    def fetch(url):
        if url not in pages:
            raise OSError("403 Forbidden")
        return pages[url]

    res = {r["url"]: r for r in R.sources(rows, fetch=fetch)}
    check(res["https://example.com/a"]["state"] == "found", "a quote on its page", res)
    check(
        res["https://example.com/b"]["state"] == "number", "a paraphrase whose number is there", res
    )
    check(
        res["https://example.com/c"]["state"] == "unreadable"
        and "403" in res["https://example.com/c"]["note"],
        "a page that will not open",
        res,
    )
    check(
        R.find_quote("the cat sat on the mat today", "the cat sat on a mat")[0] == "close",
        "something close",
    )
    check(
        R.find_quote("nothing like it here", "revenue rose to $16.3 billion")[0] == "missing",
        "an invented quote",
    )

    async def endpoints():
        async with TestClient(TestServer(server.make_app("t"))) as c:
            auth = {"Authorization": "Bearer t"}
            r = await c.post(
                "/api/research/check",
                data=json.dumps({"fact": FACT, "chart": CHART, "script": SCRIPT}),
                headers=auth,
            )
            body = await r.json()
            check(
                r.status == 200 and body["script"]["lines"] == 3 and body["findings"],
                "POST /api/research/check",
                body,
            )
            r = await c.post("/api/research/check", data="{}", headers={})
            check(r.status == 401, "only with the token")
            r = await c.post(
                "/api/research/sources", data=json.dumps({"sources": "x"}), headers=auth
            )
            check(r.status == 400, "sources must be a list")
            r = await c.post(
                "/api/research/sources",
                data=json.dumps({"sources": [{"url": "http://127.0.0.1/x", "quote": "a b c"}]}),
                headers=auth,
            )
            body = await r.json()
            check(
                r.status == 200 and body["sources"][0]["state"] == "unreadable",
                "a private address is never read",
                body,
            )

    asyncio.run(endpoints())
    print("\n%d failed" % len(fails) if fails else "\nall passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
