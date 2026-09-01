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
import sys, os, json, argparse, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import




def rejoin(words):
    """Put back together the names Whisper's tokeniser took apart.

    A hyphenated or dotted name arrives as several "words": W / -9,
    flat / -to / -fillable, Instafill / .ai, lead / -based. Nothing downstream
    knows they belong together, so captions render "W -9" and "Instafill .ai"
    with a space in front of the punctuation -- which looks like a typo to
    every viewer, and is burned into the picture.

    The join happens HERE, in the envelope loader, rather than in
    transcribe-words.py, so that transcripts already paid for are fixed on read
    instead of re-transcribed. Merging is safe for timing: the pieces are
    adjacent by construction, so the joined word simply spans both.
    """
    out = []
    for w in words:
        t = w["text"]
        glue = (out and t and (
            # ".ai", "-9", "-fillable" -- punctuation LEADING a real fragment
            (t[0] in "-." and len(t) > 1 and t[1].isalnum())
            # "flat-" waiting for its other half
            or out[-1]["text"].endswith("-")))
        if glue:
            out[-1]["text"] += t
            out[-1]["end"] = w["end"]
            continue
        out.append(dict(w))
    return out


def load_words(path):
    d = json.load(open(path, encoding="utf-8"))
    words = d["words"] if isinstance(d, dict) else d
    out = []
    for w in words:
        # transcribe-words.py writes "text"; tolerate "word" from other tools
        t = w.get("text", w.get("word"))
        if t is None:
            continue
        out.append({"text": t, "start": float(w["start"]), "end": float(w["end"])})
    if not out:
        sys.exit("no words in %s" % path)
    return rejoin(out)


def fold(s, loose=True):
    """Normalise for matching. Whitespace always goes -- the words carry no
    spaces of their own, so a spaced query would never match otherwise."""
    s = unicodedata.normalize("NFC", s)
    s = "".join(ch for ch in s if not ch.isspace())
    if loose:
        s = s.casefold()
        # apostrophes and dashes vary between the ASR output and what you type
        for a, b in (("’", "'"), ("ʼ", "'"), ("`", "'"),
                     ("–", "-"), ("—", "-")):
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
        return [{"text": t, "start": w["start"], "end": w["end"]}
                for t, w in zip(new, old)]

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
            span = find_span(words[at:], phrase,
                             nth=(nth if nth is not None else 0))
            if span is None:
                break
            i, j = span[0] + at, span[1] + at
            new = repl.split()
            words[i:j + 1] = _retime(words[i:j + 1], new)
            hits += 1
            at = i + len(new)
            if nth is not None:
                break
        if not hits:
            sys.exit("corrections: %r matches nothing in the transcript -- it "
                     "has already been fixed, or the transcript changed under "
                     "it" % phrase)
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
    ap.add_argument("--nth", type=int, default=0,
                    help="use the Nth occurrence (0-based); applies to every "
                         "--find phrase in the call, not per phrase")
    ap.add_argument("--exact", action="store_true",
                    help="match case and punctuation too")
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
