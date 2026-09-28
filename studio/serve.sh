#!/usr/bin/env bash
# The studio on Linux (the Azure VM) -- the counterpart of serve.ps1, over systemd.
#
#   bash studio/serve.sh status                  health, release, both units
#   bash studio/serve.sh release [--ref REF]     snapshot REF (default studio-stable), test it,
#                                                make it current, then a gentle restart
#   bash studio/serve.sh restart                 drain, then restart the server (tunnel stays)
#   bash studio/serve.sh start                   start the tunnel and the server, and at every boot
#   bash studio/serve.sh stop                    drain, stop both, mark the studio offline
#   bash studio/serve.sh --dry-run <cmd>         say what would happen, touch nothing
#
# A restart is gentle, as on the laptop: the running server is asked to drain (no new films; the
# ones being made finish, up to DRAIN_MINUTES, default 20), films still queued are made by the
# next one. systemd (kitcut-studio.service, kitcut-tunnel.service; install.sh) keeps both alive
# between restarts, and brings them back after a crash or a reboot.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${STUDIO_PORT:-8765}"
DRAIN_MINUTES="${DRAIN_MINUTES:-20}"
DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
cmd="${1:-status}"; shift || true
REF="studio-stable"
[ "${1:-}" = "--ref" ] && REF="${2:?--ref needs a value}"

run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
setting() { grep -E "^\s*$1\s*=" "$REPO/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' \r"; }
health() { curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health"; }
running() { health 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("running") or 0)' 2>/dev/null || echo 0; }

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
    run "$REPO/.venv/bin/python" -X utf8 "$REPO/studio/release.py" --ref "$REF"
    drain
    run sudo systemctl restart kitcut-studio
    ;;
  restart)
    drain
    run sudo systemctl restart kitcut-studio
    ;;
  start)
    run sudo systemctl enable --now kitcut-tunnel kitcut-studio
    ;;
  stop)
    drain
    run sudo systemctl stop kitcut-studio kitcut-tunnel
    ;;
  *) sed -n 2,10p "$0"; exit 2 ;;
esac
[ "$DRY" = 1 ] || [ "$cmd" = status ] || { sleep 2; health && echo; }
