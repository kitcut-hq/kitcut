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




# Whisper emits punctuation as its OWN word wherever it did not decode a space
# before it: "60" + ",000", "U" + ".S.", "60" + "%", "go" + "-to". Joining
# words with spaces then puts a space inside the number -- "60 ,000" shipped
# on a caption card, and a dub sent "60 ,000" to its translator. The repair
# lives HERE, in the one loader every consumer shares, so captions, phrase
# anchors, outlines and dub units all see the same text. The raw words.json
# on disk stays verbatim ASR output; nothing is migrated.
#
# Gluing cannot break phrase matching: fold() strips whitespace and index()
# concatenates words with no separator, so "60"+",000" and "60,000" build the
# identical haystack. check-shorts.py pins that invariance.
#
# The glue set is measured, not assumed -- 358 such tokens across this repo's
# transcripts. Two families look like punctuation and must KEEP their space,
# which is why "glue anything that starts with punctuation" is the wrong rule:
# 57 standalone en/em dashes in the Ukrainian transcripts, where the dash is a
# word, and 19 opening guillemets («Дельта»). A leading "$" needs nothing --
# "$14" already arrives whole. Accepted risk, zero cases in the corpus: a
# genuinely negative number ("-20" meaning minus twenty) would weld onto the
# word before it; every leading-hyphen token measured is a suffix.
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


def glue_words(words):
    """Merge whisper's suffix tokens into the word before them, in the raw
    envelope. The merged word spans both timing windows (a caption spotlight
    on "60,000" must stay lit while ",000" is being said) and keeps the lower
    probability. Idempotent: a glued list has no suffix tokens left."""
    out = []
    for w in words:
        if out and glues_back(w["text"]):
            p = out[-1]
            p["text"] += w["text"]
            p["end"] = max(p["end"], w["end"])
            if "probability" in w or "probability" in p:
                p["probability"] = min(p.get("probability", 1.0),
                                       w.get("probability", 1.0))
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
        rec = {"text": t, "start": float(w["start"]), "end": float(w["end"])}
        if "probability" in w:
            rec["probability"] = w["probability"]
        out.append(rec)
    if not out:
        sys.exit("no words in %s" % path)
    return glue_words(out)


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
