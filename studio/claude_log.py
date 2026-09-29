#!/usr/bin/env python
"""What Claude did on a film, and what went wrong, read from its own logs in one short page.

    python studio/claude_log.py <film-id>              the last 25 replies, every API error, the
                                                       reply it is waiting for now, the debug log's
                                                       warnings and errors
    python studio/claude_log.py <film-id> --all        every reply
    python studio/claude_log.py <film-id> --debug 80   80 lines of the debug log (0: none)
    python studio/claude_log.py <film-id> --grep TEXT  debug-log lines with TEXT, whatever level

Two sources, both outside the film (Claude never reads them):
    the transcript   STUDIO_HOME/claude/<film>/projects/.../<session>.jsonl (a film on the key;
                     on the machine's login, ~/.claude/projects/...): one row per message, with
                     its time, its token counts and the API errors Claude Code retried
    the debug log    STUDIO_HOME/claude/<film>/logs/claude-<start>.log, one per run of Claude Code
                     (agent.run_claude passes --debug-file): its requests, retries and timeouts

A reply's wait is the time from the message before it (the prompt or a tool's result) to the reply,
which is what a stalled film is made of: on 2026-09-28 film llwtme waited an hour, twice, for one
reply, and all the transcript said was "Request timed out." -- this is how to see that in seconds.
On the Azure VM: `bash studio/deploy/ops.sh claude-log <film-id> [flags]`. Reads only.
"""

import os
import re
import sys
import json
import glob
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from film import Film  # noqa: E402

# the debug-log lines worth a person's attention (the rest is Claude Code's own chatter)
NOTABLE = re.compile(
    r"\[(ERROR|WARN)|error|retry|retrying|timed? ?out|timeout|abort|ECONN|ETIMEDOUT|socket|"
    r"overloaded|\b(4\d\d|5\d\d)\b|rate.?limit|stream (ended|closed)|compact",
    re.IGNORECASE,
)


def transcript(film):
    """The session's transcript: the film's own config folder (on the key), else the login's."""
    sid = film.record().get("claude_session")
    if not sid:
        return None
    for root in (film.claude_dir, os.path.expanduser("~/.claude")):
        hits = glob.glob(os.path.join(root, "projects", "*", sid + ".jsonl"))
        if hits:
            return hits[0]
    return None


def debug_logs(film):
    return sorted(glob.glob(os.path.join(film.claude_dir, "logs", "claude-*.log")))


def _when(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


def _did(content):
    """What one reply did, in a few words: its tool calls, or that it spoke."""
    out = []
    for b in content if isinstance(content, list) else []:
        t = b.get("type")
        if t == "tool_use":
            inp = b.get("input") or {}
            what = inp.get("file_path") or inp.get("retake_line") or inp.get("times") or ""
            what = os.path.basename(str(what)) if isinstance(what, str) else str(what)
            out.append(
                "%s%s"
                % (b.get("name", "").replace("mcp__studio__", ""), "(%s)" % what if what else "")
            )
        elif t == "text" and b.get("text", "").strip():
            x = b["text"].strip()
            # a short one is often Claude Code's own marker ("API Error: ...", an interruption)
            out.append("said %r" % x if len(x) <= 60 else "said %d chars" % len(x))
        elif t == "thinking":
            out.append("thought")
    return ", ".join(out)


def replies(rows):
    """One entry per API reply (a reply's blocks share a message id), and the errors between."""
    out, last_input, seen = [], None, {}
    for r in rows:
        when = _when(r.get("timestamp"))
        msg = r.get("message") or {}
        if r.get("type") == "user":
            last_input = when
        elif r.get("type") == "assistant" and msg.get("id"):
            e = seen.get(msg["id"])
            if e is None:
                e = seen[msg["id"]] = {
                    "kind": "reply",
                    "at": when,
                    "waited": (when - last_input).total_seconds() if when and last_input else None,
                    "did": [],
                    "usage": {},
                }
                out.append(e)
            d = _did(msg.get("content"))
            if d:
                e["did"].append(d)
            if msg.get("usage"):
                e["usage"] = msg["usage"]
        elif r.get("type") == "system" and r.get("subtype") == "api_error":
            err = r.get("error") or {}
            out.append(
                {
                    "kind": "error",
                    "at": when,
                    "text": err.get("message") or json.dumps(err)[:120],
                    "attempt": "%s/%s" % (r.get("retryAttempt"), r.get("maxRetries")),
                }
            )
    pending = None
    if rows:
        tail = [r for r in rows if r.get("type") in ("user", "assistant")]
        if tail and tail[-1].get("type") == "user":
            pending = last_input
    return out, pending


def show(film, all_=False, debug=40, grep=None):
    rec = film.record()
    print(
        "%s  %s  %ss  %s  claude $%.2f"
        % (
            film.id,
            rec.get("state"),
            rec.get("length"),
            rec.get("auth"),
            rec.get("claude_cost_usd") or 0,
        )
    )
    path = transcript(film)
    if not path:
        print("  no transcript (no Claude session recorded yet)")
    else:
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        items, pending = replies(rows)
        n = sum(1 for i in items if i["kind"] == "reply")
        errs = [i for i in items if i["kind"] == "error"]
        print("  transcript %s: %d replies, %d API errors" % (path, n, len(errs)))
        shown = items if all_ else items[-25:]
        if len(shown) < len(items):
            print("  ... %d earlier" % (len(items) - len(shown)))
        for i in shown:
            at = i["at"].strftime("%H:%M:%S") if i["at"] else "?"
            if i["kind"] == "error":
                print("  %s  ERROR  %s (retry %s)" % (at, i["text"], i["attempt"]))
                continue
            u = i["usage"]
            ctx = sum(
                u.get(k) or 0
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            )
            w = i["waited"]
            print(
                "  %s  %6s  ctx %4dk  out %6s  %s"
                % (
                    at,
                    "%.0fs" % w if w is not None else "",
                    ctx // 1000,
                    u.get("output_tokens", ""),
                    "; ".join(i["did"])[:110],
                )
            )
        if pending:
            mins = (datetime.now().astimezone() - pending).total_seconds() / 60
            print(
                "  WAITING for Claude's reply since %s (%.0f min)"
                % (pending.strftime("%H:%M:%S"), mins)
            )
    logs = debug_logs(film)
    if not logs:
        print("  no debug log (runs before 2026-09-29 did not write one)")
        return
    newest = logs[-1]
    with open(newest, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    pick = [x for x in lines if (grep.lower() in x.lower() if grep else NOTABLE.search(x))]
    print(
        "  debug log %s: %d lines, %d %s%s"
        % (
            newest,
            len(lines),
            len(pick),
            "matching %r" % grep if grep else "notable",
            " (of %d runs)" % len(logs) if len(logs) > 1 else "",
        )
    )
    if debug:
        for x in pick[-debug:]:
            print("    " + x[:220])


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("film")
    ap.add_argument("--all", action="store_true", help="every reply, not the last 25")
    ap.add_argument("--debug", type=int, default=40, help="debug-log lines to show (0: none)")
    ap.add_argument("--grep", help="debug-log lines containing this, instead of the notable ones")
    args = ap.parse_args()
    film = Film.open(args.film)
    if film is None:
        sys.exit("no film %s" % args.film)
    show(film, args.all, args.debug, args.grep)


if __name__ == "__main__":
    main()
