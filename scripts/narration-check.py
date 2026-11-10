#!/usr/bin/env python
"""Is a film's narration its script, word for word?

A research film is narrated from a script whose every line was checked against its sources
(_narration.py says how such a script is written: L01, L02 ... with the spoken words in quotes).
The studio checks vo.json against it before it records (studio/validate.py); this is the same
check from the outside, on any film's words: its vo.json, its timeline, or the captions of the
finished video, which are what was actually heard, a line the voice dropped included.

    --script <doc.md>   the script (required)
    --vo <vo.json>      the narration the film was asked to say
    --timeline <timeline.json>   the narration as recorded (audio/vo/timeline.json)
    --vtt <film.vtt>    the finished film's captions (a URL is fine: the studio's film.vtt)
    --list              the script's lines as read, and nothing compared (what the check sees)

It prints the differences, each naming its script line, and exits 1 when there are any. Case,
punctuation, dashes and [voice tags] are not differences; a script line said as several narration
lines in a row is not one either (a line over the voice's 300 characters must be).

Invoke as:
    python scripts/narration-check.py --script projects/<id>/facts/<film>-script.md --list
    python scripts/narration-check.py --script <doc.md> --vtt https://media.kitcut.ai/films/<id>/film.vtt
"""

import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _narration as N  # noqa: E402

_CUE_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?\.\d{3}\s+-->")


def read(path_or_url):
    if re.match(r"^https?://", path_or_url):
        req = urllib.request.Request(
            path_or_url, headers={"User-Agent": "kitcut-narration-check/1"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 -- an http(s) URL, checked above
            return r.read().decode("utf-8", "replace")
    with open(_env.resolve(path_or_url), encoding="utf-8") as f:
        return f.read()


def vtt_text(text):
    """The words of a WebVTT file, cue after cue, as one line: captions are cut into cards that
    do not follow the narration's lines, so the comparison is on the words alone."""
    out, skip = [], True
    for raw in text.splitlines():
        line = raw.strip()
        if _CUE_TIME.match(line):
            skip = False
            continue
        if not line:
            skip = True
            continue
        if skip or line.startswith(("WEBVTT", "NOTE", "STYLE")):
            continue
        out.append(re.sub(r"<[^>]+>", "", line))
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--script", required=True, help="the word-for-word script (.md or .txt)")
    what = ap.add_mutually_exclusive_group()
    what.add_argument("--vo", help="a vo.json")
    what.add_argument("--timeline", help="an audio/vo/timeline.json")
    what.add_argument("--vtt", help="a WebVTT file or URL (the finished film's captions)")
    what.add_argument(
        "--list", action="store_true", help="print the script's lines; compare nothing"
    )
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    script = N.script_lines(read(a.script))
    if not script:
        print(
            "%s is not a word-for-word script: it needs at least %d lines that start with an id "
            "(L01, - L02. ...) and quote the words spoken" % (a.script, N.MIN_LINES)
        )
        return 2
    if a.list or not (a.vo or a.timeline or a.vtt):
        print(
            "%s: %s, %d words"
            % (a.script, N.summary(script), sum(len(N.words(t)) for _, t in script))
        )
        for lid, said in script:
            print("  %s  %s" % (lid, said))
        return 0
    if a.vo:
        said = [ln.get("text", "") for ln in json.loads(read(a.vo)).get("lines") or []]
        name = "vo.json line"
    elif a.timeline:
        said = [ln.get("text", "") for ln in json.loads(read(a.timeline)).get("lines") or []]
        name = "timeline line"
    else:
        said, name = [vtt_text(read(a.vtt))], "the captions"
    found = N.compare(script, said, name=name, first=0 if a.vo else 1)
    if (
        a.vtt
    ):  # the captions are one stream: which caption "line" holds two script lines means nothing
        found = [f for f in found if " joins " not in f]
    if not found:
        print("word for word: %s, %d narration line(s)" % (N.summary(script), len(said)))
        return 0
    print("%d difference(s) from %s (%s):" % (len(found), a.script, N.summary(script)))
    for f in found:
        print("  " + f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
