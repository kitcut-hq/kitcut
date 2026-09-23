"""Chapter-marker rules, shared by yt-set-chapters.py and yt-audit-chapters.py.

Pure text in, verdicts out -- no API calls, so it is cheap to test.

WHAT YOUTUBE ACTUALLY ENFORCES, measured across 46 published videos on
@instafill_ai by diffing each description against the chapters YouTube really
renders (yt-dlp's `chapters` field reads them off the watch page):

  - A gap under 10s renders FINE. QJwxbW7dWwA carries a 4-second chapter
    (195s-199s) and all 13 of its marks appear.
  - A first mark after 00:00 renders FINE. YouTube synthesises a leading
    "<Untitled Chapter 1>" covering 0 -> the first mark. Ugly, not fatal.
  - Out-of-order marks render FINE. knOiq9MZ4oI lists 01:16 before 01:05 and
    still shows 10 chapters.

The widely-repeated "must start at 0:00, minimum three, at least 10s apart"
rules were coded here first from memory and were WRONG on 11 of those 46
videos -- every single one flagged "broken" was in fact rendering correctly.
So these are advisory only. Nothing in this module should refuse a list on
their account; the authority on whether a video has chapters is the watch page,
not this file.

The >=3 minimum is left as a hard rule because it is the one condition no
published video here contradicts -- but it is inherited from documentation and
is NOT independently measured. Treat it with the same suspicion as the rest if
it ever gets in the way.
"""

import re

# A chapter line as it appears in a description: timestamp, whitespace, title.
CHAPTER_LINE = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(\S.*)$")

MIN_CHAPTERS = 3
MIN_GAP_S = 10


def parse_ts(ts):
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def fmt_ts(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_marks(text):
    """[(seconds, whole_line)] for every chapter-shaped line in `text`."""
    out = []
    for raw in text.split("\n"):
        m = CHAPTER_LINE.match(raw)
        if m:
            out.append((parse_ts(m.group(1)), raw.strip()))
    return out


def fatal(marks):
    """Reasons YouTube would render nothing. See the module docstring: only
    the count is treated as fatal, and even that is documentation, not
    measurement.
    """
    if len(marks) < MIN_CHAPTERS:
        return [f"only {len(marks)} chapters; YouTube documents a minimum of {MIN_CHAPTERS}"]
    return []


def advisories(marks):
    """Cosmetic or stylistic notes. NONE of these stop chapters rendering --
    each was checked against a published video that breaks it and works.
    """
    notes = []
    if marks and marks[0][0] != 0:
        notes.append(
            f"first mark is at {fmt_ts(marks[0][0])}; YouTube will "
            f"prepend an '<Untitled Chapter 1>' covering the gap"
        )
    for (a, la), (b, lb) in zip(marks, marks[1:]):
        if b < a:
            notes.append(f"out of order: {la!r} before {lb!r}")
        elif b - a < MIN_GAP_S:
            notes.append(
                f"{b - a}s chapter: {la!r} -> {lb!r} (renders, but is a very short section)"
            )
    return notes


def find_block(description):
    """(start, end) line span of a chapter block, or None.

    A block is >=MIN_CHAPTERS contiguous chapter lines -- contiguous so that a
    stray "call me at 5:30" in prose is not mistaken for one.
    """
    lines = description.split("\n")
    run_start, best = None, None
    for i, line in enumerate(lines + [""]):  # sentinel flushes a trailing run
        if CHAPTER_LINE.match(line):
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= MIN_CHAPTERS:
                best = (run_start, i)
            run_start = None
    return best


def block_text(description):
    """The existing chapter block verbatim, or None."""
    span = find_block(description)
    if not span:
        return None
    return "\n".join(description.split("\n")[span[0] : span[1]])


def splice(description, block):
    """Replace an existing chapter block, or append after a blank line.

    Returns (new_description, replaced_block_or_None) -- the caller has to know
    whether this destroyed someone's hand-written chapters.
    """
    lines = description.split("\n")
    span = find_block(description)
    if span:
        old = "\n".join(lines[span[0] : span[1]])
        lines[span[0] : span[1]] = block.split("\n")
        return "\n".join(lines), old
    sep = "" if not description.strip() else description.rstrip() + "\n\n"
    return sep + block + "\n", None
