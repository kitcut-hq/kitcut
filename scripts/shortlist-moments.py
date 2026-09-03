#!/usr/bin/env python
"""Verify that a real SELECTION happened before any short is cut.

The stage this enforces: before a clips manifest exists, the picker writes
`projects/<id>/shortlist.json` -- every candidate moment considered, each with
its quote, its hook, answers to the four hook tests, a picture note, and a
verdict with reasoning. This tool then does the half a machine can do: it
resolves every phrase in the transcript, prices every hook offset against the
3.0s gate, checks durations, and REFUSES the shortlist when the process was
skipped -- too few candidates, no rejects (a shortlist with no rejects is a
decision, not a selection), unanswered tests, or phrases that do not resolve.

Why staged at all: on 2026-09-03 the all-at-once flow picked twice from one
Bloomberg episode and both picks were rejected by the user after rendering --
an anchor posing a question, then a Treasury Secretary saying nothing
falsifiable. The candidate that survived (Dell, "considered dead", +1.8s) had
been sitting at the top of the payoff table the whole time. Both bad picks
fail the four tests ON PAPER, before any encode; the selection stage makes
writing that paper mandatory. The four tests live in the video-shorts skill
(`## The hook gate`); this tool checks they were ANSWERED, the skill teaches
how to answer them honestly.

The shortlist file:

    { "video": "<id>",
      "source_words": "projects/<id>/transcripts/<id>.words.json",
      "candidates": [
        { "id": "slug",
          "start_text": "...", "end_text": "...", "hook": "...",
          "tests": { "disagree": "...", "audience": "...",
                     "ends_on_claim": "...", "falsifiable": "..." },
          "picture": "held shot? layout? evidence, not hope",
          "verdict": "pick" | "backup" | "reject",
          "why": "..." } ] }

Free by nature -- reads, prices, writes nothing.

Invoke as:  python scripts/shortlist-moments.py --shortlist projects/<id>/shortlist.json
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module  # noqa: E402

_outline = import_module("transcript-outline")

TESTS = ("disagree", "audience", "ends_on_claim", "falsifiable")
HOOK_MAX_S = 3.0          # must match cut-clips.py's gate
MIN_CANDIDATES = 5        # fewer than this is a hunch, not a selection
MIN_REJECTS = 2           # no documented rejects = alternatives never priced


def check_candidate(c, words, errs):
    cid = c.get("id", "?")
    for k in ("id", "start_text", "hook", "verdict", "why"):
        if not str(c.get(k, "")).strip():
            errs.append("%s: missing %r" % (cid, k))
    if not (c.get("end_text") or c.get("end_before_text")):
        errs.append("%s: needs end_text or end_before_text" % cid)
    if c.get("verdict") not in ("pick", "backup", "reject"):
        errs.append("%s: verdict must be pick/backup/reject" % cid)
    tests = c.get("tests") or {}
    for t in TESTS:
        if not str(tests.get(t, "")).strip():
            errs.append("%s: test %r unanswered -- the tests are the "
                        "selection; see the video-shorts skill" % (cid, t))
    if not str(c.get("picture", "")).strip():
        errs.append("%s: no picture note -- a pick that has not looked at "
                    "the footage is half a pick (two-box, b-roll and boxed "
                    "shots all killed candidates before)" % cid)

    # the mechanical half: resolve and price
    row = dict(id=cid, verdict=c.get("verdict", "?"))
    s = _outline.find(words, c["start_text"]) if c.get("start_text") else None
    ekey = "end_text" if c.get("end_text") else "end_before_text"
    e = _outline.find(words, c[ekey]) if c.get(ekey) else None
    h = _outline.find(words, c["hook"]) if c.get("hook") else None
    for name, hit, phrase in (("start_text", s, c.get("start_text")),
                              (ekey, e, c.get(ekey)),
                              ("hook", h, c.get("hook"))):
        if phrase and hit is None:
            errs.append("%s: %s does not resolve in the transcript: %r"
                        % (cid, name, phrase))
    if s and e:
        end = e[0] if ekey == "end_before_text" else e[1]
        row["dur"] = end - s[0]
        if row["dur"] <= 0:
            errs.append("%s: end resolves BEFORE the start (%.1fs) -- on a "
                        "podcast with a cold-open trailer the same phrase "
                        "plays twice, and the matcher takes the first hit; "
                        "anchor on words unique to the body instance"
                        % (cid, row["dur"]))
        elif (c.get("verdict") in ("pick", "backup")
                and not 10.0 <= row["dur"] <= 75.0):
            # a reject documents consideration and needs real quotes, not
            # renderable boundaries -- only what might ship must fit a short
            errs.append("%s: %.1fs is outside the 10-75s a short can carry"
                        % (cid, row["dur"]))
    if s and h:
        row["hook_at"] = h[0] - s[0]
        if row["hook_at"] < 0:
            errs.append("%s: hook resolves BEFORE the start" % cid)
        elif row["hook_at"] > HOOK_MAX_S and c.get("verdict") == "pick":
            errs.append("%s: hook +%.1fs fails the %.1fs gate -- re-anchor "
                        "or reject; do not carry it to the manifest"
                        % (cid, row["hook_at"], HOOK_MAX_S))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shortlist", required=True,
                    help="projects/<id>/shortlist.json")
    args = ap.parse_args()

    sl = json.load(open(_env.resolve(args.shortlist), encoding="utf-8"))
    words = _outline.load_words(_env.resolve(sl["source_words"]))
    cands = sl.get("candidates") or []
    errs, rows = [], []
    for c in cands:
        rows.append(check_candidate(c, words, errs))

    verdicts = [c.get("verdict") for c in cands]
    if len(cands) < MIN_CANDIDATES:
        errs.append("only %d candidate(s) -- a selection needs at least %d "
                    "considered, including the ones that lose"
                    % (len(cands), MIN_CANDIDATES))
    if verdicts.count("reject") < MIN_REJECTS:
        errs.append("only %d reject(s) documented -- if nothing lost, "
                    "nothing was compared" % verdicts.count("reject"))
    if verdicts.count("pick") == 0:
        errs.append("no candidate marked pick")

    print("%-28s %-7s %6s %9s" % ("candidate", "verdict", "dur", "hook"))
    for r in sorted(rows, key=lambda r: r.get("hook_at", 99)):
        print("%-28s %-7s %5.1fs %8s"
              % (r["id"], r["verdict"], r.get("dur", -1),
                 ("+%.1fs" % r["hook_at"]) if "hook_at" in r else "?"))
    if errs:
        print()
        for e in errs:
            print("FAIL %s" % e)
        sys.exit("%d problem(s) -- the selection stage is not done" % len(errs))
    print("\nshortlist OK: %d candidates, %d pick(s), %d backup(s), "
          "%d reject(s)" % (len(cands), verdicts.count("pick"),
                            verdicts.count("backup"), verdicts.count("reject")))


if __name__ == "__main__":
    main()
