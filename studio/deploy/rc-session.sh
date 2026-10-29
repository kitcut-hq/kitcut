#!/bin/bash
# A Claude session started ON this machine with Remote Control on, for a phone to pick up: the
# kind that can send files. Sessions started from the phone's "New session" (claude rc) cannot:
# SendUserFile answers "not on a project thread" there, on every machine and version measured
# (KI-069). A session started here with `claude --remote-control` delivers them.
#
#   bash studio/deploy/rc-session.sh new "<name>" ["first message"]   start one, print its link
#   bash studio/deploy/rc-session.sh list                             the ones running
#   bash studio/deploy/rc-session.sh stop <id>|--all                  end one, or all of them
#
# Each runs in a unit of its own (KI-068): MemoryMax=20% of the machine, no swap, an OOM kills
# the process and not the unit. DISABLE_AUTOUPDATER=1 because an interactive session updates
# itself even with autoUpdates false, and moved ~/.local/bin/claude (which the films use) from
# 2.1.296 to 2.1.312 the first time one was started (2026-10-28). Run it from a session on this
# machine, or from the laptop as `ops.sh rc session ...`.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# one tmux server per session, so each one lives in its own unit (a shared server would start
# every later session inside the first one's unit, under its cap)
tm() { local id="$1"; shift; tmux -L "$id" "$@"; }
CLAUDE="$HOME/.local/bin/claude"
die() { echo "rc-session.sh: $*" >&2; exit 1; }
shown() { tm "$1" capture-pane -p -J -t "$1" 2>/dev/null | grep -v '^[[:space:]]*$' || true; }

case "${1:-}" in
  new)
    name="${2:-}"; first="${3:-}"
    [ -n "$name" ] || die 'new "<name>" ["first message"]'
    id="rcs-$(date +%m%d-%H%M%S)"
    before="$(readlink -f "$CLAUDE")"
    sudo -n systemd-run --unit="kc-$id" --uid="$(id -un)" --gid="$(id -gn)" -q \
      -p Type=forking -p MemoryMax=20% -p MemorySwapMax=0 -p OOMPolicy=continue \
      -p WorkingDirectory="$REPO" -p Environment="HOME=$HOME" -p Environment=TERM=xterm-256color \
      -p Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" \
      -p Environment=DISABLE_AUTOUPDATER=1 -p Environment=TZ=America/Los_Angeles \
      -p UnsetEnvironment="CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY" \
      /usr/bin/tmux -L "$id" new-session -d -s "$id" -x 200 -y 50 -c "$REPO" \
      "$CLAUDE --remote-control $(printf %q "$name")"
    # first-run screens (theme, security notes, renderer offer) are answered once per user;
    # step through any that are left, then wait for the session's link
    link=""
    for _ in $(seq 1 30); do
      sleep 2
      screen="$(shown "$id")"
      link="$(grep -oE 'https://claude\.ai/code/session_[A-Za-z0-9]+' <<<"$screen" | tail -1 || true)"
      [ -n "$link" ] && break
      if grep -q 'Try the new fullscreen renderer' <<<"$screen"; then tm "$id" send-keys -t "$id" Down Enter
      elif grep -qE 'Press Enter to continue|Enter to confirm' <<<"$screen"; then tm "$id" send-keys -t "$id" Enter
      fi
    done
    [ "$(readlink -f "$CLAUDE")" = "$before" ] ||
      { ln -sfn "$before" "$CLAUDE"; echo "warning: the session moved $CLAUDE; put back to $before" >&2; }
    [ -n "$link" ] || { shown "$id" | tail -15 >&2; die "no Remote Control link after 60 s (unit kc-$id)"; }
    if [ -n "$first" ]; then
      sleep 2; tm "$id" send-keys -t "$id" -l "$first"; sleep 1; tm "$id" send-keys -t "$id" Enter
    fi
    echo "$id  $name"
    echo "$link"
    ;;
  list)
    for sock in /tmp/tmux-"$(id -u)"/rcs-*; do
      [ -S "$sock" ] || continue; id="$(basename "$sock")"
      tm "$id" has-session -t "$id" 2>/dev/null || continue
      link="$(shown "$id" | grep -oE 'https://claude\.ai/code/session_[A-Za-z0-9]+' | tail -1 || true)"
      echo "$id  $(systemctl is-active "kc-$id" 2>/dev/null)  ${link:-(no link on screen)}"
    done
    ;;
  stop)
    [ -n "${2:-}" ] || die "stop <id>|--all"
    if [ "$2" = --all ]; then ids="$(cd /tmp/tmux-"$(id -u)" 2>/dev/null && ls -d rcs-* 2>/dev/null || true)"; else ids="$2"; fi
    for id in $ids; do
      sudo -n systemctl stop "kc-$id" 2>/dev/null || true; tm "$id" kill-server 2>/dev/null || true
      rm -f /tmp/tmux-"$(id -u)"/"$id"; echo "stopped $id"
    done
    ;;
  *) die 'new "<name>" ["first message"] | list | stop <id>|--all' ;;
esac
