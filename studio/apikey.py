"""Which Anthropic key the studio's Claude runs on, and what each one spent this month.

Two keys can be in the studio's .env:

    ANTHROPIC_CREDIT_KEY   a key whose organisation holds a monthly credit (the $100 a Max
                           plan comes with): used first, until that month's credit is gone
    ANTHROPIC_API_KEY      the paid key: everything after that, and everything when there is
                           no credit key

A run on the key (agent.claude_env, auth "api") gets the credit key unless this month's credit
is spent -- by our own count (STUDIO_CREDIT_USD, default 100, priced from the tokens) or because
the API said so ("credit balance is too low", which marks the month out: out()). The month
turns over on day STUDIO_CREDIT_RESET_DAY of the month (default 1, UTC), and the credit key is
tried again then.

The API cannot be asked what is left: the usage and cost reports need an Admin key, and an
individual organisation has none (measured 2026-11-02: 401 "The Admin API requires an Admin API
key or an organization-scoped API key"). So every run on a key charges its cost here
(charge()), one line in STUDIO_HOME/apikey/spend.jsonl, and the report reads that ledger.
Claude Code's own cost figure is list price, the same figure Anthropic bills.

Invoke as:
    python studio/apikey.py                 this month: spent per key, the credit left, the pace,
                                            the day it runs out at that pace
    python studio/apikey.py --month 2026-10 another month
    python studio/apikey.py --json          the same as JSON
    python studio/apikey.py --plan          which key the next run would get, and why; reads only
"""

import os
import re
import sys
import json
import argparse
import contextlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procs  # noqa: E402 -- stdlib only

CREDIT, PAID = "credit", "paid"
NAMES = {CREDIT: "ANTHROPIC_CREDIT_KEY", PAID: "ANTHROPIC_API_KEY"}
# the env var claude_env() leaves on a run's environment, so its cost can be charged to its key
TAG = "KITCUT_API_KEY_NAME"
# what the API says when an organisation's credit is gone (Claude Code passes it on as a
# billing_error, "Credit balance is too low" / "Your credit balance is too low to access...")
OUT = re.compile(r"credit balance|billing", re.I)


class CreditOut(RuntimeError):
    """The credit key's month is spent: the same run starts again on the paid key."""


def home():
    env = os.environ.get("STUDIO_HOME", "").strip()
    if env:
        return os.path.abspath(env)
    kit = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parent = os.path.dirname(kit)
    if os.path.basename(parent) == "releases":
        return os.path.dirname(parent)
    return os.path.join(parent, "kitcut-studio")


def _dir():
    return os.path.join(home(), "apikey")


def cap_usd():
    try:
        return float(os.environ.get("STUDIO_CREDIT_USD") or 100)
    except ValueError:
        return 100.0


def reset_day():
    try:
        return min(28, max(1, int(os.environ.get("STUDIO_CREDIT_RESET_DAY") or 1)))
    except ValueError:
        return 1


def period(at=None):
    """The credit month `at` falls in: (its name "YYYY-MM", start, end), UTC. The name is the
    month it starts in."""
    at = at or datetime.now(timezone.utc)
    day = reset_day()
    y, m = at.year, at.month
    if at.day < day:
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    start = datetime(y, m, day, tzinfo=timezone.utc)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return "%04d-%02d" % (y, m), start, datetime(ny, nm, day, tzinfo=timezone.utc)


def _start_of(name):
    y, m = (int(x) for x in name.split("-"))
    return datetime(y, m, reset_day(), tzinfo=timezone.utc)


def _state():
    with contextlib.suppress(OSError, ValueError):
        with open(os.path.join(_dir(), "state.json"), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    return {}


def rows(name=None):
    """The ledger's lines in credit month `name` (every line when None)."""
    out = []
    with contextlib.suppress(OSError):
        with open(os.path.join(_dir(), "spend.jsonl"), encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError):
                    r = json.loads(line)
                    if name is None or r.get("period") == name:
                        out.append(r)
    return out


def spent(key=CREDIT, name=None):
    name = name or period()[0]
    return round(sum(r.get("usd") or 0 for r in rows(name) if r.get("key") == key), 4)


def choose(at=None):
    """(which, the key, why) for the next run on the key: the credit key while its month lasts."""
    name = period(at)[0]
    credit, paid = procs.secret(NAMES[CREDIT]), procs.secret(NAMES[PAID])
    if not credit:
        return PAID, paid, "no %s" % NAMES[CREDIT]
    out = _state().get("out") or {}
    if out.get("period") == name:
        return (
            PAID,
            paid or credit,
            "the credit is spent this month (the API said so %s)" % (out.get("at", "")[:16]),
        )
    used = spent(CREDIT, name)
    if used >= cap_usd() and paid:
        return PAID, paid, "the credit is spent this month ($%.2f of $%.0f)" % (used, cap_usd())
    return CREDIT, credit, "$%.2f of $%.0f used this month" % (used, cap_usd())


def tag(env):
    """Which key an environment from claude_env() carries (None: not a key's)."""
    return (env or {}).get(TAG)


def charge(env_or_key, usd, what, film=None):
    """Put a run's cost on its key's line in the ledger. Never raises: a cost that cannot be
    written must not fail the film."""
    key = env_or_key if isinstance(env_or_key, str) else tag(env_or_key)
    if not key or not usd:
        return
    at = datetime.now(timezone.utc)
    row = {
        "at": at.isoformat(timespec="seconds"),
        "period": period(at)[0],
        "key": key,
        "usd": round(float(usd), 6),
        "what": what,
    }
    if film:
        row["film"] = film
    with contextlib.suppress(OSError):
        os.makedirs(_dir(), exist_ok=True)
        with open(os.path.join(_dir(), "spend.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


def out(why, env=None):
    """The API refused the credit key for want of credit: the rest of this month is on the paid
    key. True when that was the credit key (the caller then runs again), False otherwise."""
    if env is not None and tag(env) != CREDIT:
        return False
    if not OUT.search(why or "") or not procs.secret(NAMES[PAID]):
        return False
    at = datetime.now(timezone.utc)
    d = _state()
    d["out"] = {"period": period(at)[0], "at": at.isoformat(timespec="seconds"), "why": why[:300]}
    with contextlib.suppress(OSError):
        os.makedirs(_dir(), exist_ok=True)
        tmp = os.path.join(_dir(), "state.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, os.path.join(_dir(), "state.json"))
    print("apikey: the credit key is spent for %s: %s" % (d["out"]["period"], why[:160]))
    return True


def report(name=None, now=None):
    now = now or datetime.now(timezone.utc)
    cur, start, end = period(now)
    name = name or cur
    if name != cur:
        _, start, end = period(_start_of(name))
    rs = rows(name)
    by = {k: round(sum(r.get("usd") or 0 for r in rs if r.get("key") == k), 2) for k in NAMES}
    what = {}
    for r in rs:
        k = "%s %s" % (r.get("key"), r.get("what"))
        what[k] = round(what.get(k, 0) + (r.get("usd") or 0), 2)
    last = min(now, end)
    days = max((last - start).total_seconds() / 86400, 1 / 24)
    pace = by[CREDIT] / days
    left = round(max(0.0, cap_usd() - by[CREDIT]), 2)
    o = _state().get("out") or {}
    d = {
        "period": name,
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
        "cap_usd": cap_usd(),
        "credit_usd": by[CREDIT],
        "paid_usd": by[PAID],
        "credit_left_usd": 0.0 if o.get("period") == name else left,
        "credit_per_day_usd": round(pace, 2),
        "out": o if o.get("period") == name else None,
        "by": dict(sorted(what.items(), key=lambda kv: -kv[1])),
    }
    if name == cur and not d["out"] and pace > 0:
        runs_out = now + timedelta(days=left / pace)
        d["runs_out"] = runs_out.date().isoformat() if runs_out < end else None
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--month", help="a credit month, YYYY-MM (default: this one)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--plan", action="store_true", help="which key the next run gets, and why")
    a = ap.parse_args()
    kit = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    procs.load_secrets(os.environ.get("STUDIO_ENV_FILE") or os.path.join(kit, ".env"))
    if a.plan:
        which, key, why = choose()
        print("next run on the key: %s (%s)%s" % (which, why, "" if key else "  NO KEY SET"))
        return
    d = report(a.month)
    if a.json:
        print(json.dumps(d, indent=1))
        return
    print("credit month %s (%s to %s)" % (d["period"], d["from"], d["to"]))
    print(
        "  credit key: $%.2f of $%.0f, $%.2f left"
        % (d["credit_usd"], d["cap_usd"], d["credit_left_usd"])
    )
    print("  paid key:   $%.2f" % d["paid_usd"])
    print("  pace:       $%.2f a day on the credit" % d["credit_per_day_usd"])
    if d["out"]:
        print("  spent:      the API refused the credit key %s" % d["out"]["at"][:16])
    elif "runs_out" in d:
        print("  runs out:   %s" % (d["runs_out"] or "not this month, at this pace"))
    for k, v in d["by"].items():
        print("    %-28s $%.2f" % (k, v))


if __name__ == "__main__":
    main()
