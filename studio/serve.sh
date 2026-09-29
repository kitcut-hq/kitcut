#!/usr/bin/env bash
# The studio on Linux (the Azure VM) -- the counterpart of serve.ps1, over systemd.
#
#   bash studio/serve.sh status                  health, release, both units
#   bash studio/serve.sh release [--ref REF]     snapshot REF (default studio-stable), test it,
#                                                make it current, then a gentle restart
#   bash studio/serve.sh use <sha12>             make a release already built current, then a
#                                                gentle restart (a rollback)
#   bash studio/serve.sh restart                 drain, then restart the server (tunnel stays)
#   bash studio/serve.sh start                   start the tunnel and the server, and at every boot
#   bash studio/serve.sh stop                    drain, stop both, mark the studio offline
#   bash studio/serve.sh --dry-run <cmd>         say what would happen, touch nothing
#
# A restart is gentle, as on the laptop: the running server is asked to drain (no new films; the
# ones being made finish, up to DRAIN_MINUTES, default 20), films still queued are made by the
# next one. systemd (kitcut-studio.service, kitcut-tunnel.service; install.sh) keeps both alive
# between restarts, and brings them back after a crash or a reboot. release, use, restart and stop
# run one at a time (deploy.lock in the studio's home); a second one stops at once.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${STUDIO_PORT:-8765}"
DRAIN_MINUTES="${DRAIN_MINUTES:-20}"
DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
cmd="${1:-status}"; shift || true
REF="studio-stable"
[ "${1:-}" = "--ref" ] && REF="${2:?--ref needs a value}"

# The studio's home, where releases are built and read: the unit's (install.sh) unless set. Without
# it release.py falls back to <checkout>/../kitcut-studio and builds where the server never looks --
# a ship on 2026-09-28 restarted the studio onto its old code that way, and killed a film for it.
if [ -z "${STUDIO_HOME:-}" ]; then
  STUDIO_HOME="$(systemctl show kitcut-studio -p Environment --value 2>/dev/null | tr ' ' '\n' | sed -n 's/^STUDIO_HOME=//p')"
fi
[ -n "${STUDIO_HOME:-}" ] || { echo "serve.sh: no STUDIO_HOME (set it, or install the unit: deploy/install.sh)" >&2; exit 1; }
export STUDIO_HOME

run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
setting() { grep -E "^\s*$1\s*=" "$REPO/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' \r"; }
health() { curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health"; }
running() { health 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("running") or 0)' 2>/dev/null || echo 0; }
live_release() { health 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("release",""))' 2>/dev/null || true; }
current() { head -1 "$STUDIO_HOME/releases/current" 2>/dev/null | tr -d '[:space:]'; }

# One deploy at a time. Three ships overlapped on 2026-09-28, each draining and restarting on its
# own; a second one now stops at once and says who holds the lock (the kernel frees it when the
# holder exits, however it exits).
LOCK="$STUDIO_HOME/deploy.lock"
lock() {
  [ "$DRY" = 1 ] && return 0
  exec 9>>"$LOCK"
  flock -n 9 || { echo "serve.sh: another deploy is running -- $(cat "$LOCK")" >&2; exit 1; }
  local from="${SSH_CLIENT:-local}"
  echo "pid $$, '$cmd', since $(date '+%F %T'), from ${from%% *}" > "$LOCK"
}

drain() {
  health >/dev/null 2>&1 || return 0
  [ "$(running)" = 0 ] && return 0
  run curl -fsS --max-time 5 -X POST -H "Authorization: Bearer $(setting STUDIO_TOKEN)" \
    "http://127.0.0.1:$PORT/api/admin/drain" >/dev/null || { echo "could not ask the server to drain" >&2; return 0; }
  [ "$DRY" = 1 ] && return 0
  local until=$(( $(date +%s) + DRAIN_MINUTES * 60 ))
  while [ "$(date +%s)" -lt "$until" ]; do
    n="$(running)"; [ "$n" = 0 ] && return 0
    echo "  draining: $n film(s) still being made..."
    sleep 10
  done
  echo "films still running after $DRAIN_MINUTES min; restarting anyway (they will be marked interrupted)" >&2
}

case "$cmd" in
  status)
    health && echo || echo "server: not answering on 127.0.0.1:$PORT"
    systemctl --no-pager --lines=0 status kitcut-studio kitcut-tunnel || true
    ;;
  release)
    lock
    echo "building into $STUDIO_HOME/releases"
    run "$REPO/.venv/bin/python" -X utf8 "$REPO/studio/release.py" --ref "$REF"
    [ "$DRY" = 1 ] && { echo "  would drain and restart onto $REF"; exit 0; }
    want="$(git -C "$REPO" rev-parse "$REF^{commit}" | cut -c1-12)"
    # the server comes back on what was just built, or is not touched at all
    [ "$(current)" = "$want" ] || { echo "serve.sh: $STUDIO_HOME/releases/current is '$(current)', not $want -- not restarting" >&2; exit 1; }
    [ "$(live_release)" = "$want" ] && { echo "release $want is already live: nothing to restart"; exit 0; }
    drain
    run sudo systemctl restart kitcut-studio
    ;;
  use)
    rel="${1:?use <sha12> (see: release.py --list)}"
    lock
    [ -f "$STUDIO_HOME/releases/$rel/studio/server.py" ] || { echo "serve.sh: no release '$rel' built in $STUDIO_HOME/releases" >&2; exit 1; }
    run sh -c "echo '$rel' > '$STUDIO_HOME/releases/current.tmp' && mv '$STUDIO_HOME/releases/current.tmp' '$STUDIO_HOME/releases/current'"
    drain
    run sudo systemctl restart kitcut-studio
    ;;
  restart)
    lock
    drain
    run sudo systemctl restart kitcut-studio
    ;;
  start)
    run sudo systemctl enable --now kitcut-tunnel kitcut-studio
    ;;
  stop)
    lock
    drain
    run sudo systemctl stop kitcut-studio kitcut-tunnel
    ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
[ "$DRY" = 1 ] || [ "$cmd" = status ] || { sleep 2; health && echo; }
