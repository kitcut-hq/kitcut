#!/usr/bin/env python
"""The Claude Code status line for this repo: the session, not the render.

    video-editing | @ main | Fable 5 (1M context) | effort: xhigh | ctx: 33% (329k) | 5h: 25% 3h1m | wk: 60% 2d18h

Wired up in `.claude/settings.json`. Claude Code hands a JSON blob on stdin
(model, workspace, context_window, rate_limits -- a captured sample lives in
this docstring's history) and prints the first stdout line under the prompt.
This replaced render-status.py as the status line: render progress on the
prompt turned out to be noise, and the session numbers -- context left, the
5-hour and weekly rate windows -- are the ones worth glancing at. Watching a
render is now `python scripts/render-status.py`, by hand.

Two rules, both because of where this runs:

  * **stdlib only, and no `_env` import.** It is re-run on every status-line
    refresh; the repo's usual re-exec into `.venv` would spawn a subprocess
    each time.
  * **it never fails.** Any exception would blank the status line, so the
    body is guarded and every segment degrades to absence, not to an error.

Invoke as:  (the Claude Code status line runs it; not invoked by hand)
"""
import sys, os, json, time, subprocess

# cp1252 cannot encode the branch glyph; reconfigure before the first print.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


RESET = "\x1b[0m"


def c(text, code):
    """ANSI-wrap one segment; the status line renders escape codes."""
    return "\x1b[%sm%s%s" % (code, text, RESET)


def meter(pct):
    """Green while comfortable, yellow when notable, red near the wall."""
    return "92" if pct < 50 else ("93" if pct < 80 else "91")


def kfmt(n):
    if n >= 1_000_000:
        v = n / 1_000_000.0
        return ("%dM" if v == int(v) else "%.1fM") % v
    return "%dk" % round(n / 1000.0)


def until(epoch):
    """'3h1m' / '2d18h' -- the two largest units of time left until epoch."""
    left = int(epoch) - int(time.time())
    if left <= 0:
        return "now"
    d, rem = divmod(left, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return "%dd%dh" % (d, h)
    if h:
        return "%dh%dm" % (h, m)
    return "%dm" % max(m, 1)


def git_branch(cwd):
    try:
        p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=cwd or None, capture_output=True, text=True,
                           timeout=2)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    seg = []

    ws = payload.get("workspace") or {}
    proj = ws.get("project_dir") or ws.get("current_dir") or payload.get("cwd")
    if proj:
        seg.append(c(os.path.basename(proj.rstrip("\\/")) or proj, "96"))

    branch = git_branch(proj)
    if branch:
        seg.append(c("⎇ " + branch, "92"))

    model = (payload.get("model") or {}).get("display_name")
    cw = payload.get("context_window") or {}
    size = cw.get("context_window_size")
    if model:
        seg.append(c("%s (%s context)" % (model, kfmt(size))
                     if size else model, "95"))

    effort = (payload.get("effort") or {}).get("level")
    if effort:
        seg.append(c("effort: %s" % effort, "94"))

    # used_percentage is input-only by definition, so the token figure beside
    # it is total_input_tokens alone -- keeping the two numbers on one basis
    pct = cw.get("used_percentage")
    used = cw.get("total_input_tokens") or 0
    if pct is not None:
        seg.append(c("ctx: %d%%%s"
                     % (pct, " (%s)" % kfmt(used) if used else ""), meter(pct)))

    rl = payload.get("rate_limits") or {}
    for key, label in (("five_hour", "5h"), ("seven_day", "wk")):
        w = rl.get(key) or {}
        if w.get("used_percentage") is not None:
            part = "%s: %d%%" % (label, w["used_percentage"])
            if w.get("resets_at"):
                part += " " + until(w["resets_at"])
            seg.append(c(part, meter(w["used_percentage"])))

    print((" %s " % c("|", "90")).join(seg))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                     # never blank the status line
        print("statusline: %s" % e)
