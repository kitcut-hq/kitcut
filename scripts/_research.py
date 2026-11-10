"""A research film's three documents, checked by a machine before a film is made of them.

A research film is made from a fact sheet (doc1), its chart data (doc2) and a script said word for
word (doc3: _narration.py). When a person writes them, a person re-reads every number's page; on
the Anthropic IPO film (2026-10-21) that re-read found six numbers that were wrong. When an agent
writes them unattended (docs/autonomous-research-films.md), these checks are what stands between
its research and a film with a wrong number in it. They use no AI: they find what does not add up
and say where, and the agent fixes it.

check(fact, chart, script) reads the three documents:
  - the script parses as word for word, and how long it runs (about WPM words a minute);
  - every number the narration says -- as words ("sixteen point three billion") or digits -- is a
    number of the fact sheet, give or take TOL;
  - every row of the fact sheet's tables has a label (FILED MEASURED REPORTED CLAIM ESTIMATE), a
    source and, unless it is an ESTIMATE, a url and a quote, so its page can be read again;
  - no phrase from its "The film must not say" section is in the narration;
  - every value of the chart data is a number of the fact sheet.

sources(rows) reads the pages: for each {url, quote, number?}, is the quote on its page (or
something close, or at least the number), with a plain fetch first and a real browser for a page
that refuses robots. Public addresses only (_web.py).

Pure functions on text, except sources(), which fetches.
"""

import re
import difflib
import html
import math

import _narration as N

WPM = 165  # the research voice (Orus, "letting each number land"): film 31 ran 1,956 words in 13:00
TOL = 0.006  # a spoken number matches a fact within this share (rounding "4.6" of 4.62)
LABELS = ("FILED", "MEASURED", "REPORTED", "CLAIM", "ESTIMATE")
MAX_SOURCES = 20  # pages one call reads (an MCP call has 120 s)

# ------------------------------------------------------------------ numbers, as said and as written
_UNITS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {
    w: 10 * i
    for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split())
    if w != "_"
}
_SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_ORD = {
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fifteenth": 15,
    "twentieth": 20,
}
_SUFFIX = {"k": 1e3, "m": 1e6, "mn": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12, "tn": 1e12}
_DIGITS = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)(?:\s*(trillion|billion|million|thousand|tn|bn|mn|[kmbt])\b)?"
)
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?|[a-z]+")


def _small(tok, i):
    """A number under a thousand said in words from tok[i]: (value, next index) or None."""
    v, j, seen = 0, i, False
    if j + 1 < len(tok) and tok[j] == "a" and tok[j + 1] in ("hundred", "thousand"):
        tok = [*tok[:j], "one", *tok[j + 1 :]]  # "a hundred and eleven billion"
    if j < len(tok) and tok[j] in _UNITS:
        v, j, seen = _UNITS[tok[j]], j + 1, True
        if j < len(tok) and tok[j] == "hundred":
            v, j = v * 100, j + 1
            if (
                j + 1 < len(tok)
                and tok[j] == "and"
                and (tok[j + 1] in _UNITS or tok[j + 1] in _TENS)
            ):
                j += 1
            if j < len(tok) and tok[j] in _TENS:
                v, j = v + _TENS[tok[j]], j + 1
                if j < len(tok) and tok[j] in _UNITS and _UNITS[tok[j]] < 10:
                    v, j = v + _UNITS[tok[j]], j + 1
            elif j < len(tok) and tok[j] in _UNITS:
                v, j = v + _UNITS[tok[j]], j + 1
    elif j < len(tok) and tok[j] in _TENS:
        v, j, seen = _TENS[tok[j]], j + 1, True
        if j < len(tok) and tok[j] in _UNITS and 0 < _UNITS[tok[j]] < 10:
            v, j = v + _UNITS[tok[j]], j + 1
    return (v, j) if seen else None


def spoken_numbers(text):
    """The numbers a line says, in words or digits: [(value, words as said)], years and the small
    counts of ordinary speech ("one of those numbers") left out."""
    t = re.sub(r"\[[^\]]{1,40}\]", " ", text or "").lower().replace("’", "'")
    tok = _TOKEN.findall(re.sub(r"[‐-―-]", " ", t))
    out, i = [], 0
    while i < len(tok):
        t, start = tok[i], i
        if t in _ORD:
            out.append((float(_ORD[t]), t))
            i += 1
            continue
        if t[0].isdigit():
            v, i = float(t.replace(",", "")), i + 1
            if i < len(tok) and tok[i] in _SCALES:
                v, i = v * _SCALES[tok[i]], i + 1
            elif i < len(tok) and tok[i] in _SUFFIX:
                v, i = v * _SUFFIX[tok[i]], i + 1
            big = v > 12 and not (1900 <= v <= 2100 and t.isdigit())  # a year: 2026, not 2,061
            if big or "." in t:
                out.append((v, " ".join(tok[start:i])))
            continue
        got = _small(tok, i)
        if not got:
            i += 1
            continue
        v, i = got
        # "twenty twenty-six", "nineteen eighty": a year said in two halves
        nxt = _small(tok, i) if 10 <= v < 100 and i < len(tok) and tok[i] not in _UNITS else None
        if nxt and v >= 10 and nxt[0] < 100 and "hundred" not in tok[start:i]:
            year = v * 100 + nxt[0]
            if 1900 <= year <= 2100:
                i = nxt[1]
                continue
        dec = ""
        if i + 1 < len(tok) and tok[i] == "point" and tok[i + 1] in _UNITS:
            i += 1
            while i < len(tok) and tok[i] in _UNITS and _UNITS[tok[i]] < 10:
                dec, i = dec + str(_UNITS[tok[i]]), i + 1
        if dec:
            v = float("%d.%s" % (v, dec))
        # "one dollar and seventy cents"
        if i + 1 < len(tok) and tok[i] in ("dollar", "dollars") and tok[i + 1] == "and":
            cents = _small(tok, i + 2)
            if cents and cents[1] < len(tok) and tok[cents[1]] == "cents":
                v, i = v + cents[0] / 100, cents[1] + 1
        if (
            i + 2 < len(tok)
            and tok[i] == "and"
            and tok[i + 1] == "a"
            and tok[i + 2] in ("half", "quarter")
        ):
            v, i = v + (0.5 if tok[i + 2] == "half" else 0.25), i + 3
        scaled = False
        while i < len(tok) and tok[i] in _SCALES:
            v, i, scaled = v * _SCALES[tok[i]], i + 1, True
        # "two thousand and twenty-five", a year
        if scaled and i + 1 < len(tok) and tok[i] == "and" and v in (1e3, 2e3):
            more = _small(tok, i + 1)
            if more and 1900 <= v + more[0] <= 2100:
                i = more[1]
                continue
        if 1900 <= v <= 2100 and not scaled and not dec:
            continue
        if v > 12 or dec or scaled:
            out.append((v, " ".join(tok[start:i])))
    return out


HEDGE = {
    "about",
    "around",
    "nearly",
    "almost",
    "roughly",
    "some",
    "over",
    "approximately",
    "than",
    "under",
}


def hedged(text, as_said):
    """Does a hedge ("about", "nearly", "more than") come just before these words in the line?"""
    t = " ".join(re.findall(r"[a-z0-9]+", (text or "").lower().replace("-", " ")))
    k = t.find(" ".join(re.findall(r"[a-z0-9]+", as_said)))
    return k > 0 and bool(HEDGE & set(t[:k].split()[-3:]))


def rounds_to(v, facts):
    """v is a fact rounded to one or two significant figures (810,000 said as "about eight hundred
    thousand")."""
    for f in facts:
        if f and abs(v - f) <= 0.03 * abs(f):  # a rounding, not another number nearby
            for sig in (1, 2):
                k = 10 ** (math.floor(math.log10(abs(f))) - sig + 1)
                if abs(v - round(f / k) * k) <= TOL * abs(v):
                    return True
    return False


def written_numbers(text):
    """Every number a document writes, with its scale: "$16.3B" 16.3e9, "1.5 trillion" 1.5e12,
    "2,061 GW" 2061, "93-98%" 93 and 98. -> [float]."""
    out = []
    for m in _DIGITS.finditer((text or "").lower()):
        v = float(m.group(1).replace(",", ""))
        s = m.group(2)
        out.append(v * (_SCALES.get(s) or _SUFFIX.get(s) or 1))
        out.append(v)  # "$16.3B" also backs "sixteen point three" said before "billion dollars"
    return out


def backed(v, facts):
    return any(abs(v - f) <= TOL * max(abs(f), 1e-9) for f in facts)


# ------------------------------------------------------------------ the documents
def tables(text):
    """Every markdown table: [(the heading above it, [column names], [rows as {column: cell}])]."""
    out, head, rows, cols, sect = [], None, [], None, ""
    for raw in (text or "").splitlines() + [""]:
        line = raw.strip()
        if line.startswith("#"):
            sect = line.lstrip("#").strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cols is None:
                cols, head = [c.lower() for c in cells], sect
            elif not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                rows.append(dict(zip(cols, cells, strict=False)))
            continue
        if cols is not None:
            out.append((head, cols, rows))
        cols, rows = None, []
    return out


def section(text, title):
    """The text under the first heading whose words hold `title` (a regex), to the next heading."""
    out, on = [], False
    for line in (text or "").splitlines():
        if line.lstrip().startswith("#"):
            if on:
                break
            on = bool(re.search(title, line, re.I))
            continue
        if on:
            out.append(line)
    return "\n".join(out)


def _quoted(text):
    return [q.strip() for q in re.findall(r"[\"“]([^\"”]{3,200})[\"”]", text or "")]


def check(fact, chart, script):
    """The three documents, read together -> {script: {...}, findings: [{kind, where, what}]}."""
    findings = []

    def say(kind, where, what):
        findings.append({"kind": kind, "where": where, "what": what})

    lines = N.script_lines(script)
    words = sum(len(N.words(t)) for _, t in lines)
    if not lines:
        say(
            "script",
            "doc3",
            "not a word-for-word script: it needs lines that start with an id (- L01.) and quote "
            "the words spoken",
        )
    facts = written_numbers(fact)
    if not facts:
        say("facts", "doc1", "the fact sheet has no numbers")
    for lid, said in lines:
        for v, as_said in spoken_numbers(said):
            if not backed(v, facts) and not (hedged(said, as_said) and rounds_to(v, facts)):
                say(
                    "number",
                    lid,
                    '%s says "%s" (%s): no number in the fact sheet is that'
                    % (lid, as_said, _fmt(v)),
                )
    for head, cols, rows in tables(fact):
        if "label" not in cols:
            continue
        where = "doc1, %s" % (head or "a table")
        if not ("url" in cols and "quote" in cols):
            say(
                "sources",
                where,
                "this table has no url and quote columns: its numbers cannot be read again on "
                "their pages (check_sources)",
            )
        for r in rows:
            label = (r.get("label") or "").upper()
            first = (r.get("number") or r.get(cols[0]) or "?")[:40]
            kinds = [k for k in LABELS if k in label]
            if "DEFINITION" in label:
                continue
            if not kinds:
                say("label", where, '"%s": no label (one of %s)' % (first, ", ".join(LABELS)))
            if not (r.get("source") or "").strip() and kinds != ["ESTIMATE"]:
                say("source", where, '"%s": no source' % first)
            if "url" in cols and kinds and kinds != ["ESTIMATE"]:
                if not re.match(r"https?://", r.get("url") or ""):
                    say("source", where, '"%s": no url to read it again on' % first)
                elif not (r.get("quote") or "").strip(' "'):
                    say("source", where, '"%s": no quote of the words that carry it' % first)
    must_not = [
        q
        for line in section(fact, r"must not say").splitlines()
        for q in _quoted(line)[:1]
        if re.match(r"\s*[-*]\s*[\"“]", line)
    ]
    told = " %s " % _canon(" ".join(t for _, t in lines))
    for phrase in must_not:
        w = _canon(phrase)
        if w and " %s " % w in told:
            say(
                "must_not",
                "doc3",
                'the narration says "%s", which the fact sheet says the film must not' % phrase,
            )
    for head, cols, rows in tables(chart):
        for r in rows:
            for col, cell in list(r.items())[1:]:  # the first column names the row (H1 2026)
                if any(k in cell.upper() for k in LABELS) or "arithmetic" in cell:
                    continue  # the label, and how an estimate was made
                unit = next((n for w, n in _SCALES.items() if w in col), 1)  # "$ billion"
                if any(
                    x and not (backed(x, facts) or backed(x * unit, facts))
                    for x in written_numbers(cell)
                ):
                    say(
                        "chart",
                        "doc2, %s" % (head or "a table"),
                        "%s: not in the fact sheet" % cell[:60],
                    )
    seen, uniq = set(), []
    for f in findings:
        k = (f["kind"], f["where"], f["what"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    minutes = words / WPM if words else 0
    return {
        "script": {
            "lines": len(lines),
            "first": lines[0][0] if lines else None,
            "last": lines[-1][0] if lines else None,
            "words": words,
            "minutes": round(minutes, 1),
            # what to ask the studio for: a little over the narration, never under it
            "seconds": int(math.ceil(minutes * 60 * 1.06 / 5.0) * 5) if words else 0,
        },
        "findings": uniq,
    }


def _canon(text):
    """A line's words with each number as its value ("lost $80 billion" and "lost eighty billion
    dollars" both hold "lost #8e+10"): a phrase is found however its numbers are said."""
    t = " ".join(N.words(text))
    for v, as_said in sorted(spoken_numbers(text), key=lambda x: -len(x[1])):
        t = t.replace(" ".join(N.words(as_said)), "#%g" % v)
    return " ".join(w for w in t.split() if w not in ("dollars", "dollar"))


def _fmt(v):
    for s, n in (("trillion", 1e12), ("billion", 1e9), ("million", 1e6)):
        if abs(v) >= n:
            return ("%g " % (v / n)) + s
    return "%g" % v


# ------------------------------------------------------------------ the pages
def _plain(markup):
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)\b.*?</\1>", " ", markup)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return html.unescape(t)


def _toks(text):
    t = (text or "").replace("’", "'").replace("“", '"').replace("”", '"').lower()
    t = re.sub(r"[‐-―]", "-", t)
    return [w.strip(".,;:'\"()[]") for w in re.findall(r"[^\s]+", t) if w.strip(".,;:'\"()[]")]


def find_quote(page, quote):
    """Is `quote` in `page` (both text)? -> ("found" | "close" | "missing", the page's words
    there)."""
    p, q = _toks(page), _toks(quote)
    if not q:
        return "missing", ""
    n = len(q)
    for i in range(len(p) - n + 1):
        if p[i : i + n] == q:
            return "found", " ".join(p[i : i + n])
    # where its rarest words are: a figure, a name
    anchors = sorted({w for w in q if any(c.isdigit() for c in w)} or {max(q, key=len)})
    best, where = 0.0, ""
    for i, w in enumerate(p):
        if w in anchors:
            lo = max(0, i - n)
            win = p[lo : i + n]
            m = difflib.SequenceMatcher(None, q, win, autojunk=False)
            r = sum(b.size for b in m.get_matching_blocks()) / n
            if r > best:
                a = m.get_matching_blocks()
                best, where = r, " ".join(win[a[0].b : a[-2].b + a[-2].size] if len(a) > 1 else win)
    return (
        ("close", where[:300]) if best >= 0.75 else ("missing", where[:300] if best >= 0.4 else "")
    )


def sources(rows, fetch=None, browse=None, budget_s=90):
    """Each row {url, quote, number?, id?} read on its page -> [{id, url, state, page, note}].
    state:
    found | close | number (the quote is not there, its number is) | missing | unreadable.
    fetch(url) -> text or raises; browse(url) -> text or raises (the real browser, for a page that
    refuses a plain fetch). Pages are read once each; at most MAX_SOURCES rows."""
    import time  # noqa: PLC0415

    t0, pages, out = time.time(), {}, []
    for k, r in enumerate(rows[:MAX_SOURCES]):
        url, quote = str(r.get("url") or ""), str(r.get("quote") or "")
        rid = r.get("id") or "row %d" % (k + 1)
        if not re.match(r"https?://", url):
            out.append({"id": rid, "url": url, "state": "unreadable", "page": "", "note": "no url"})
            continue
        if url not in pages:
            if time.time() - t0 > budget_s:
                out.append(
                    {
                        "id": rid,
                        "url": url,
                        "state": "unreadable",
                        "page": "",
                        "note": "out of time: send it again",
                    }
                )
                continue
            text, note = "", ""
            for how in (fetch, browse):
                if how is None:
                    continue
                try:
                    text = how(url) or ""
                except Exception as e:  # noqa: BLE001 -- a page that cannot be read is an answer
                    note = str(e)[:160]
                    continue
                if text and find_quote(text, quote)[0] != "missing":
                    break
            pages[url] = (text, note)
        text, note = pages[url]
        if not text:
            out.append(
                {"id": rid, "url": url, "state": "unreadable", "page": "", "note": note or "empty"}
            )
            continue
        state, seen = find_quote(text, quote)
        if state == "missing" and r.get("number"):
            nums = written_numbers(text)
            if any(backed(v, nums) for v in written_numbers(str(r["number"]))):
                state, note = "number", "the quote is not on the page, but its number is"
        out.append(
            {
                "id": rid,
                "url": url,
                "state": state,
                "page": seen,
                "note": note if state == "unreadable" else "",
            }
        )
    return out


def rows_of(fact):
    """The fact sheet's rows that can be read again on their pages: [{id, url, quote, number}]."""
    out = []
    for head, cols, rows in tables(fact):
        if not {"url", "quote"} <= set(cols):
            continue
        for r in rows:
            if re.match(r"https?://", r.get("url") or "") and (r.get("quote") or "").strip(' "'):
                num = r.get("number") or r.get(cols[0]) or ""
                out.append(
                    {
                        "id": "%s: %s" % (head or "doc1", num[:40]),
                        "url": r["url"],
                        "quote": r["quote"].strip(' "“”'),
                        "number": num,
                    }
                )
    return out
