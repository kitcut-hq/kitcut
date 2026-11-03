#!/usr/bin/env python
"""The credit key and the paid key, checked without the API: python studio/test_apikey.py

    choose    no credit key -> paid; credit key -> credit; our count at the cap -> paid; the
              API's "credit balance is too low" -> paid for the rest of that month, credit
              again the next
    env       claude_env(auth "api") hands Claude Code the chosen key and tags it
    ledger    charge() writes a line per run to the key it ran on; nothing for the login
    report    spent, left, the pace and the day it runs out; another month on its own
    period    the month turns over on STUDIO_CREDIT_RESET_DAY

Seconds; no key, no network.
"""

import os
import sys
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

HOME = tempfile.mkdtemp(prefix="studio-apikey-")
os.environ["STUDIO_HOME"] = HOME
os.environ.pop("STUDIO_CREDIT_USD", None)
os.environ.pop("STUDIO_CREDIT_RESET_DAY", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import procs  # noqa: E402
import apikey  # noqa: E402

bad = []


def check(ok, what, got=None):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  (got %r)" % (got,)))
    if not ok:
        bad.append(what)


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def reset():
    shutil.rmtree(os.path.join(HOME, "apikey"), ignore_errors=True)
    procs.SECRETS.clear()


def test_choose():
    reset()
    procs.SECRETS["ANTHROPIC_API_KEY"] = "sk-paid"
    w, k, _ = apikey.choose()
    check((w, k) == ("paid", "sk-paid"), "choose: no credit key -> the paid key", (w, k))
    procs.SECRETS["ANTHROPIC_CREDIT_KEY"] = "sk-credit"
    w, k, _ = apikey.choose()
    check((w, k) == ("credit", "sk-credit"), "choose: a credit key goes first", (w, k))
    apikey.charge("credit", 99.5, "film", "f1")
    check(apikey.choose()[0] == "credit", "choose: $99.50 of $100 is still the credit's")
    apikey.charge("credit", 0.6, "film", "f2")
    w, _, why = apikey.choose()
    check(w == "paid" and "$100.10" in why, "choose: past the cap -> the paid key", (w, why))
    reset()
    procs.SECRETS.update(ANTHROPIC_API_KEY="sk-paid", ANTHROPIC_CREDIT_KEY="sk-credit")
    env = {apikey.TAG: "paid"}
    check(
        not apikey.out("Credit balance is too low", env),
        "out: the paid key's refusal is not the credit's",
    )
    env = {apikey.TAG: "credit"}
    check(not apikey.out("overloaded", env), "out: another error does not spend the month")
    check(
        apikey.out("Your credit balance is too low to access the API", env),
        "out: the credit's refusal",
    )
    check(apikey.choose()[0] == "paid", "choose: the API said spent -> paid for the month")
    nxt = apikey.period()[2] + timedelta(days=1)  # the next credit month
    check(apikey.choose(nxt)[0] == "credit", "choose: next month the credit key again")
    procs.SECRETS.pop("ANTHROPIC_API_KEY")
    reset()
    procs.SECRETS["ANTHROPIC_CREDIT_KEY"] = "sk-credit"
    check(
        not apikey.out("credit balance is too low", {apikey.TAG: "credit"}),
        "out: no paid key, nothing to go on to",
    )


def test_env():
    reset()
    procs.SECRETS.update(ANTHROPIC_API_KEY="sk-paid", ANTHROPIC_CREDIT_KEY="sk-credit")
    import agent

    env = agent.claude_env(None, "api")
    check(env.get("ANTHROPIC_API_KEY") == "sk-credit", "env: Claude Code gets the credit key")
    check(apikey.tag(env) == "credit", "env: tagged credit", apikey.tag(env))
    apikey.charge(env, 1.25, "film", "f1")
    apikey.charge({}, 2.0, "film", "f2")  # the login's: no tag, no line
    rs = apikey.rows()
    check(
        len(rs) == 1 and rs[0]["key"] == "credit" and rs[0]["film"] == "f1",
        "ledger: one line, the key's",
        rs,
    )
    apikey.charge("credit", 0, "film")
    check(len(apikey.rows()) == 1, "ledger: nothing for a run that cost nothing")


def test_report():
    reset()
    now = datetime.now(timezone.utc)
    name, start, end = apikey.period(now)
    apikey.charge("credit", 30.0, "film", "f1")
    apikey.charge("credit", 2.5, "youtube-draft", "f1")
    apikey.charge("paid", 4.0, "film", "f2")
    d = apikey.report()
    check(d["credit_usd"] == 32.5 and d["paid_usd"] == 4.0, "report: spent per key", d)
    check(d["credit_left_usd"] == 67.5, "report: left", d["credit_left_usd"])
    check(d["by"].get("credit film") == 30.0, "report: by what", d["by"])
    check("runs_out" in d, "report: a run-out day at this pace", d)
    other = apikey.report("2020-01")
    check(
        other["credit_usd"] == 0 and other["from"] == "2020-01-01", "report: another month", other
    )


def test_period():
    check(apikey.period(at("2026-11-02"))[0] == "2026-11", "period: the calendar month by default")
    check(
        apikey.period(at("2026-12-31"))[2] == at("2027-01-01"), "period: December ends in January"
    )
    os.environ["STUDIO_CREDIT_RESET_DAY"] = "15"
    try:
        n, s, e = apikey.period(at("2026-11-02"))
        check(
            (n, s, e) == ("2026-10", at("2026-10-15"), at("2026-11-15")),
            "period: reset on the 15th",
            (n, s, e),
        )
        check(
            apikey.period(at("2026-01-03"))[0] == "2025-12",
            "period: before the 15th of January is December's",
        )
    finally:
        os.environ.pop("STUDIO_CREDIT_RESET_DAY")


if __name__ == "__main__":
    try:
        test_choose()
        test_report()
        test_period()
        test_env()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print("\n%s" % ("FAILED: %s" % ", ".join(bad) if bad else "all apikey checks pass"))
    sys.exit(1 if bad else 0)
