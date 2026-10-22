"""A narration written word for word, and whether what a film says is it.

A research film's narration is written and checked against its sources before the film is made:
every number in it was read on its source's page. Its script names each spoken line (L01, L02 ...)
with what is on screen, and the film must say exactly those lines, in order. Twice that was not
what came back: the pilot of the Anthropic IPO film (2026-10-21) dropped a line, the valuation
history, because the studio's prompt told its Claude that a script's words may be cut to fit; and
the full film split a line in two at the voice's 300-character limit. So this reads such a script
and compares a narration with it, word by word, before anything is recorded.

A script line is an id at the start of a line -- L01, "- L01.", "**L01**:", "L1)" -- and the words
spoken are the double-quoted text that follows it, on that line or the ones under it, up to the
next id or heading. Stage directions in *italics* are left out, quotes inside them included:

    - L03. *Three large cards counting up: $16.3B, $80.7B, $600B+.*
      "One of those numbers is not what it looks like. Another is bigger than it looks."

A line with no quotes at all is taken whole (its italics removed). A document is a word-for-word
script when it holds at least MIN_LINES such lines.

The comparison is on words: case, punctuation, quote styles, dashes and [voice tags] do not count,
so the narration may punctuate for the voice. A script line may be spoken as several narration
lines in a row (a long one must be, at the voice's limit), but one narration line may not hold two
script lines, which would lose the pause between them.

Pure text in, sentences out; stdlib only, so the studio's checker (studio/validate.py) and
narration-check.py share it.
"""

import re
import difflib

MIN_LINES = 3
MAX_TOLD = 12  # differences told at once: the rest are "and N more"

_ID = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?(L\d{1,3})(?:\*\*|__)?\s*[.:)\]-]?\s*(.*)$")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_ITALIC = re.compile(
    r"(?<![*\w])\*(?!\*)(.+?)(?<!\*)\*(?![*\w])|(?<![_\w])_(?!_)(.+?)(?<!_)_(?![_\w])", re.S
)
_TAG = re.compile(r"\[[^\]]{1,40}\]")
_OPEN, _CLOSE = '"“„', '"”'
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def script_lines(text):
    """[(id, spoken words)] of a word-for-word script, in its order; [] when the text is not one."""
    blocks, cur, gap = [], None, False
    for raw in (text or "").splitlines():
        m = _ID.match(raw)
        if m:
            cur, gap = [m.group(1), [m.group(2)]], False
            blocks.append(cur)
        elif _HEADING.match(raw) or (gap and raw.strip() and not raw[:1].isspace()):
            cur = None  # a heading, or a paragraph of its own after a blank line: not the line's
        elif cur is not None:
            gap = not raw.strip()
            cur[1].append(raw)
    out = []
    for lid, parts in blocks:
        body = _ITALIC.sub(" ", "\n".join(parts))
        a = min((body.find(q) for q in _OPEN if q in body), default=-1)
        b = max((body.rfind(q) for q in _CLOSE), default=-1)
        said = body[a + 1 : b] if 0 <= a < b else body
        said = " ".join(said.split()).strip(" -")
        if said:
            out.append((lid.upper(), said))
    return out if len(out) >= MIN_LINES else []


def words(text):
    """The words of a line as compared: lower case, no punctuation, no [voice tags]."""
    t = _TAG.sub(" ", text or "")
    t = t.replace("’", "'").replace("‘", "'").lower()
    t = re.sub(r"[‐-―-]", " ", t)  # "sixty-one" and "sixty one" are the same words
    return _WORD.findall(t)


def _quote(ws, n=12):
    s = " ".join(ws[:n])
    return '"%s%s"' % (s, " ..." if len(ws) > n else "")


def compare(script, said, name="narration line", first=1):
    """What differs between a script ([(id, words)], script_lines) and a narration (its lines'
    texts, in order), as sentences naming the script line each is in; [] when it is word for word.
    name and first say how a narration line is called: "vo.json line" from 0, for the studio."""
    sw, sid = [], []  # the script's words, and the index of the script line each is in
    for k, (_, line) in enumerate(script):
        ws = words(line)
        sw += ws
        sid += [k] * len(ws)
    vw, vid = [], []  # the narration's words, and the narration line each is in
    for k, line in enumerate(said):
        ws = words(line)
        vw += ws
        vid += [k] * len(ws)
    out = []
    ops = difflib.SequenceMatcher(None, sw, vw, autojunk=False).get_opcodes()
    for op, i0, i1, j0, j1 in ops:
        if op == "insert":
            near = script[sid[i0 - 1]][0] if i0 else script[0][0]
            out.append(
                "%s %d adds %s (after %s's words), which the script does not say"
                % (name, vid[j0] + first, _quote(vw[j0:j1]), near)
            )
        elif op == "replace":
            ids = sorted({script[k][0] for k in sid[i0:i1]})
            out.append(
                "%s says %s where the script says %s"
                % ("/".join(ids), _quote(vw[j0:j1]), _quote(sw[i0:i1]))
            )
        elif op == "delete":
            for k in sorted(set(sid[i0:i1])):
                mine = [w for w, s in zip(sw[i0:i1], sid[i0:i1], strict=True) if s == k]
                if len(mine) == len(words(script[k][1])):
                    out.append("%s is missing: %s" % (script[k][0], _quote(mine)))
                else:
                    out.append("%s leaves out %s" % (script[k][0], _quote(mine)))
    # one narration line may not hold two script lines: the pause between them is lost
    owner = {}  # narration line -> the script lines its matched words belong to
    for op, i0, i1, j0, _ in ops:
        if op == "equal":
            for n in range(i1 - i0):
                owner.setdefault(vid[j0 + n], set()).add(sid[i0 + n])
    for k in sorted(owner):
        if len(owner[k]) > 1:
            ids = [script[s][0] for s in sorted(owner[k])]
            out.append(
                "%s %d joins %s: give each script line a narration line of its own"
                % (name, k + first, " and ".join(ids))
            )
    if len(out) > MAX_TOLD:
        out = out[:MAX_TOLD] + ["... and %d more differences" % (len(out) - MAX_TOLD)]
    return out


MIN_SHARE = (
    0.3  # of a narration's words found in the script, in order: under it, it is another text
)


def covered(script, said):
    """Which script lines a narration says: (first, last) indices into script, or None when it is
    not this script at all (under MIN_SHARE of its words follow it: a translation, another film).
    """
    sw, sid = [], []
    for k, (_, line) in enumerate(script):
        ws = words(line)
        sw += ws
        sid += [k] * len(ws)
    vw = [w for line in said for w in words(line)]
    if not vw or not sw:
        return None
    blocks = difflib.SequenceMatcher(None, sw, vw, autojunk=False).get_matching_blocks()
    hit = [sid[b.a + n] for b in blocks for n in range(b.size)]
    if len(hit) < MIN_SHARE * len(vw):
        return None
    return min(hit), max(hit)


def check(script, said, name="narration line", first=1):
    """compare() over the stretch of the script a narration covers: a pilot that says L01 to L08
    passes, one that drops L07 between them does not. -> (differences, (first, last) | None)."""
    span = covered(script, said)
    if span is None:
        return [], None
    return compare(script[span[0] : span[1] + 1], said, name, first), span


def summary(script):
    """How long a script is, as "72 lines, L01 to L72"."""
    return "%d lines, %s to %s" % (len(script), script[0][0], script[-1][0])
