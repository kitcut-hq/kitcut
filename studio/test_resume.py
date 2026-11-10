#!/usr/bin/env python
"""A finished film changed by hand may not be rendered over a version it never saw:
python studio/test_resume.py

resume.py --finish --patched renders whatever files are in the film's folder, so it is refused
for any film a round can change: a hand's files are that film's next version, made on a copy
(rounds.py, ops.sh take / put; test_rounds.py has those cases). It is left for a film made in
scenes, where the hand names the version it started from (--over N) and a film whose notes are
being worked on is left alone (KI-061). No Claude, no render: only what is refused, and why.
"""

import os
import sys
import tempfile

os.environ["STUDIO_HOME"] = tempfile.mkdtemp(prefix="studio-test-")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume  # noqa: E402


class Stub:
    """As much of a Film as refuse() reads."""

    id = "studio-20260101-000000-abcdef"

    def __init__(self, state="done", mode="scenes", **rec):
        self.state, self.mode, self.rec = state, mode, rec

    def record(self):
        return self.rec

    def path(self, *parts):
        return __file__  # every file Claude makes is there


def main():
    bad = []

    def check(ok, what, got=None):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what) + ("" if ok else "  <- %r" % (got,)))
        if not ok:
            bad.append(what)

    def why(film, over=None):
        return resume.refuse(film, True, True, over)

    v2 = [{"n": 1, "at": "2026-10-07T12:43:28"}, {"n": 2, "at": "2026-10-07T14:05:54"}]
    for film in (Stub(mode="film"), Stub(mode="film", version=2, versions=v2)):
        got = why(film, film.rec.get("version"))
        check(
            got is not None and "ops.sh take" in got and "ops.sh put" in got,
            "a film a round can change is never rendered in place (version %s): take and put"
            % (film.rec.get("version") or 1),
            got,
        )
    check(
        "finished film" in (why(Stub("failed", mode="film")) or ""),
        "one that is not finished is told that first",
    )
    first = Stub()
    check(why(first) is None, "a film nobody changed from notes is rendered as before", why(first))
    check(why(first, 1) is None, "and with --over 1", why(first, 1))
    check("version 1" in (why(first, 2) or ""), "--over a version it is not at", why(first, 2))

    noted = Stub(version=2, versions=v2)
    got = why(noted)
    check(
        got is not None and "version 2" in got and "--over 2" in got and "14:05:54" in got,
        "a film at version 2 is refused, told the version, when it was made and what to pass",
        got,
    )
    check(
        "version 2" in (why(noted, 1) or ""), "a copy taken at version 1 is refused", why(noted, 1)
    )
    check(why(noted, 2) is None, "files that started from version 2 are rendered", why(noted, 2))

    for state in ("queued", "running", "finishing"):
        busy = Stub(version=2, versions=v2, round={"id": "x.r2", "n": 3, "state": state})
        got = why(busy, 2)
        check(
            got is not None and "version 3 is being made" in got,
            "refused while its notes are worked on (%s), whatever --over says" % state,
            got,
        )
    over = Stub(version=2, versions=v2, round={"id": "x.r1", "n": 2, "state": "done"})
    check(why(over, 2) is None, "a round that is over holds nothing up", why(over, 2))

    check(
        "finished film" in (resume.refuse(Stub("failed", version=2), True, True, 2) or ""),
        "a film that is not finished is still refused first",
    )
    stopped = Stub("interrupted", mode="film", version=2, versions=v2)
    check(
        resume.refuse(stopped, True) is None,
        "picking up a stopped film (no --patched) asks for no version",
        resume.refuse(stopped, True),
    )
    print("\n%s" % ("FAILED: %d" % len(bad) if bad else "all passed"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
