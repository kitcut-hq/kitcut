#!/usr/bin/env python
"""Read a word-level transcript for skimming, and locate phrases in it.

Two jobs, both about turning `transcripts/<id>.words.json` into timestamps you
can cut on:

  --outline            dump the transcript as [mm:ss] lines of ~N seconds each,
                       cheap to read end to end when picking episodes
  --find "<phrase>"    report the start/end time of a phrase

Matching ignores whitespace and is case/punctuation-insensitive by default, so
a phrase pasted from the outline and a phrase typed by hand both hit the same
span.

Invoke as:  python scripts/transcript-outline.py ...
"""

import sys
import os
import json
import argparse
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import


# Whisper's tokeniser takes words apart, in two directions, and joining the
# pieces with a space burns a typo into the picture: "60 ,000", "U .S.",
# "Instafill .ai", "W -9", "flat- to- fillable". It reached a shipped caption
# card as "15 ,000", and a dub sent "60 ,000" to its translator.
#
# The repair lives HERE, in the one loader every consumer shares, so captions,
# phrase anchors, outlines and dub units all see the same text, and transcripts
# already paid for are fixed on read instead of re-transcribed. The raw
# words.json on disk stays verbatim ASR output; nothing is migrated.
#
# Joining cannot break phrase matching: fold() strips whitespace and index()
# concatenates words with no separator, so "60"+",000" and "60,000" build the
# identical haystack. check-shorts.py pins that invariance.
#
# The set is measured, not assumed -- 358 leading-punctuation tokens across
# this repo's transcripts. Two families LOOK like punctuation and must keep
# their space, which is why "join anything that starts with punctuation" is
# the wrong rule: 57 standalone en/em dashes in the Ukrainian transcripts,
# where the dash is a word, and 19 opening guillemets («Дельта»). A leading
# "$" needs nothing -- "$14" already arrives whole. Accepted risk, zero cases
# in the corpus: a genuinely negative number ("-20" meaning minus twenty)
# would weld onto the word before it; every leading-hyphen token measured is
# a suffix.
GLUE_BACK = ",.!?;:%)]}»…&-'’”"
# ...and of those, only "%" is still glue when it stands alone. A lone "&" is
# "Point & Figure"; a lone "-" is a dash. A suffix is a suffix only if it has
# something after the punctuation.
GLUE_SOLO_OK = "%"


def glues_back(tok, apo=""):
    """True when tok is a suffix of the word before it, joined with no space."""
    if not tok:
        return False
    c = tok[0]
    if c not in GLUE_BACK and (not apo or c != apo):
        return False
    return len(tok) > 1 or c in GLUE_SOLO_OK


def rejoin(words):
    """Put the pieces back together, in the raw envelope.

    Two rules, and each catches what the other misses -- they were written by
    two sessions against different footage and neither alone is enough:

      * a token that is a SUFFIX of the word before it (",000", ".S.", ".ai",
        "-9", "-fillable", a solo "%") joins backwards, per glues_back()
      * a word left hanging on a trailing hyphen ("flat-" waiting for "to")
        takes the next word, whatever it starts with

    The joined word spans both timing windows -- a caption spotlight on
    "60,000" must stay lit while ",000" is being said -- and keeps the lower
    probability. Idempotent: a joined list has no suffix tokens left.
    """
    out = []
    for w in words:
        t = w["text"]
        if out and t and (glues_back(t) or out[-1]["text"].endswith("-")):
            p = out[-1]
            p["text"] += t
            p["end"] = max(p["end"], w["end"])
            if "probability" in w or "probability" in p:
                p["probability"] = min(p.get("probability", 1.0), w.get("probability", 1.0))
            continue
        out.append(dict(w))
    return out


# the name this repo's shorts tooling imports; one function, two doors
glue_words = rejoin


def load_words(path):
    d = json.load(open(path, encoding="utf-8"))
    words = d["words"] if isinstance(d, dict) else d
    out = []
    for w in words:
        # transcribe-words.py writes "text"; tolerate "word" from other tools
        t = w.get("text", w.get("word"))
        if t is None:
            continue
        rec = {"text": t, "start": float(w["start"]), "end": float(w["end"])}
        if "probability" in w:
            rec["probability"] = w["probability"]
        out.append(rec)
    if not out:
        sys.exit("no words in %s" % path)
    return rejoin(out)


def fold(s, loose=True):
    """Normalise for matching. Whitespace always goes -- the words carry no
    spaces of their own, so a spaced query would never match otherwise.
    """
    s = unicodedata.normalize("NFC", s)
    s = "".join(ch for ch in s if not ch.isspace())
    if loose:
        s = s.casefold()
        # apostrophes and dashes vary between the ASR output and what you type
        for a, b in (("’", "'"), ("ʼ", "'"), ("`", "'"), ("–", "-"), ("—", "-")):
            s = s.replace(a, b)
        s = "".join(ch for ch in s if ch.isalnum() or ch in "'-")
    return s


def index(words, loose=True):
    """Concatenated haystack plus, per character, the word that produced it."""
    hay, owner = [], []
    for i, w in enumerate(words):
        f = fold(w["text"], loose)
        hay.append(f)
        owner.extend([i] * len(f))
    return "".join(hay), owner


def find(words, phrase, loose=True, nth=0):
    hay, owner = index(words, loose)
    needle = fold(phrase, loose)
    if not needle:
        return None
    pos = -1
    for _ in range(nth + 1):
        pos = hay.find(needle, pos + 1)
        if pos < 0:
            return None
    return words[owner[pos]]["start"], words[owner[pos + len(needle) - 1]]["end"]


def find_span(words, phrase, loose=True, nth=0):
    """Like find(), but the word INDICES the phrase covers."""
    hay, owner = index(words, loose)
    needle = fold(phrase, loose)
    if not needle:
        return None
    pos = -1
    for _ in range(nth + 1):
        pos = hay.find(needle, pos + 1)
        if pos < 0:
            return None
    return owner[pos], owner[pos + len(needle) - 1]


def _retime(old, new):
    """Give the replacement words times taken from the words they replace.

    The obvious implementation -- spread the new words evenly across the span
    from the first old word's start to the last one's end -- is WRONG, and
    wrong in a way that only shows up two passes later. A corrected phrase is
    usually a whole sentence, a sentence contains pauses, and spreading across
    the span drops words INTO those pauses. The pause cut then removes the
    silence, the remap drops every word that was sitting in it, and the film
    ends up captioned "So you just tool." where the speaker said "So you can
    just open this tool." Nothing errors; the words are simply gone.

    So: when the correction is one-for-one -- which every case-and-punctuation
    fix is -- each word keeps ITS OWN times exactly. Otherwise the replacement
    is laid out along the SPOKEN time only, walking the old words' spans and
    skipping the gaps between them, so no word can ever land in a silence.
    """
    if not new:
        return []
    if len(new) == len(old):
        return [{"text": t, "start": w["start"], "end": w["end"]} for t, w in zip(new, old)]

    spans = [(w["start"], w["end"]) for w in old]
    spoken = sum(e - s for s, e in spans) or 1e-6

    def at(p):
        acc = 0.0
        for s, e in spans:
            d = e - s
            if p <= acc + d:
                return s + max(0.0, min(p - acc, d))
            acc += d
        return spans[-1][1]

    lens = [len(t) for t in new]
    total = float(sum(lens)) or 1.0
    out, pos = [], 0.0
    for k, tok in enumerate(new):
        a = at(pos)
        pos += spoken * lens[k] / total
        b = spans[-1][1] if k == len(new) - 1 else at(pos)
        out.append({"text": tok, "start": a, "end": max(b, a + 0.01)})
    return out


def apply_corrections(words, specs, verbose=False):
    """Rewrite what the model heard into what was said.

    An ASR transcript is not a draft you get to re-run cheaply -- large-v3 on a
    CPU is most of an hour -- and a handful of its mistakes are the ones that
    end up burned into a picture: a duplicated word, a sentence the model left
    unpunctuated and uncapitalised, a name that came out wrong on one of its
    three appearances. Those are per-video facts, so they live in the video's
    manifest, matched by QUOTING what is currently there:

        {"find": "request for for tenancy approval",
         "replace": "Request for Tenancy Approval",
         "why": "he says 'for' twice"}

    Every occurrence is corrected unless `nth` names one. An empty `replace`
    deletes the words. Timing is preserved exactly: the replacement spans the
    same interval the original did, split across its words in proportion to
    their length, so a correction can never drift the captions after it.

    A `find` that matches nothing is a FAILURE, not a no-op -- a correction
    that silently stops applying after a re-transcription is how a fix gets
    lost without anyone noticing.
    """
    for spec in specs or []:
        phrase = spec["find"]
        repl = spec.get("replace", "")
        nth = spec.get("nth")
        hits, at = 0, 0
        while True:
            # Search from AFTER the last replacement, never from the top. Most
            # corrections only change case and punctuation, which fold() throws
            # away -- so the corrected text still matches its own `find`, and
            # restarting the search would loop forever.
            span = find_span(words[at:], phrase, nth=(nth if nth is not None else 0))
            if span is None:
                break
            i, j = span[0] + at, span[1] + at
            new = repl.split()
            words[i : j + 1] = _retime(words[i : j + 1], new)
            hits += 1
            at = i + len(new)
            if nth is not None:
                break
        if not hits:
            sys.exit(
                "corrections: %r matches nothing in the transcript -- it "
                "has already been fixed, or the transcript changed under "
                "it" % phrase
            )
        if verbose:
            print("  corrected %dx %r -> %r" % (hits, phrase, repl))
    return words


def hhmmss(t):
    return "%02d:%05.2f" % (int(t) // 60, t % 60)


def outline(words, chunk):
    lines, buf, start = [], [], None
    for w in words:
        if start is None:
            start = w["start"]
        buf.append(w["text"])
        if w["end"] - start >= chunk:
            lines.append((start, " ".join(buf)))
            buf, start = [], None
    if buf:
        lines.append((start, " ".join(buf)))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", help="transcripts/<id>.words.json")
    ap.add_argument("--outline", action="store_true", help="dump timestamped lines")
    ap.add_argument("--chunk", type=float, default=12.0, help="seconds per outline line")
    ap.add_argument("--find", action="append", default=[], metavar="PHRASE")
    ap.add_argument(
        "--nth",
        type=int,
        default=0,
        help="use the Nth occurrence (0-based); applies to every "
        "--find phrase in the call, not per phrase",
    )
    ap.add_argument("--exact", action="store_true", help="match case and punctuation too")
    ap.add_argument("-o", "--out", help="write the outline here instead of stdout")
    args = ap.parse_args()

    words = load_words(args.words)

    if args.outline or not args.find:
        lines = ["[%s] %s" % (hhmmss(t), s) for t, s in outline(words, args.chunk)]
        text = "\n".join(lines)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(text + "\n")
            print("%s  (%d lines, %.1fs)" % (args.out, len(lines), words[-1]["end"]))
        else:
            print(text)

    rc = 0
    for phrase in args.find:
        hit = find(words, phrase, loose=not args.exact, nth=args.nth)
        if hit is None:
            print("not found: %s" % phrase)
            rc = 1
            continue
        a, b = hit
        print("%8.2f %8.2f   %s -> %s   %s" % (a, b, hhmmss(a), hhmmss(b), phrase))
    sys.exit(rc)


if __name__ == "__main__":
    main()
