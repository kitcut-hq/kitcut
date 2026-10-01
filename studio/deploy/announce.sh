#!/usr/bin/env bash
# ExecStartPost / ExecStopPost of the studio's server units: tell kitcut.ai (MongoDB,
# kitcut.studio_hosts) that the studio is up at https://$STUDIO_TUNNEL_HOST, or offline.
# agent.py refuses unless the .env sets STUDIO_ANNOUNCE=1, which only the production VM does.
#
#   announce.sh up
#   announce.sh off [<unit>]    <unit>: the one stopping (%n); default: this process's own unit,
#                               read from its cgroup (the legacy kitcut-studio.service passes none)
#
# Several servers run side by side, one unit per release (kitcut-studio@<instance>), and an old one
# exits by itself once its films are done -- while the new one serves. So "off" is said only when
# no other studio server unit is up (the one stopping is "deactivating" by now, never "active"):
# otherwise every ship would mark the public studio offline an hour later.
set -uo pipefail
REPO="${STUDIO_REPO:?}"
setting() { grep -E "^\s*$1\s*=" "$REPO/.env" | tail -1 | cut -d= -f2- | tr -d "\"' \r"; }
py="$REPO/.venv/bin/python"
if [ "${1:-}" = "up" ]; then
  for _ in $(seq 60); do
    curl -fsS "http://127.0.0.1:${STUDIO_PORT:-8765}/api/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  host="$(setting STUDIO_TUNNEL_HOST)"
  [ -n "$host" ] || { echo "STUDIO_TUNNEL_HOST is not set; not announcing" >&2; exit 0; }
  "$py" -X utf8 "$REPO/studio/agent.py" --announce "https://$host" || true
else
  self="${2:-$(grep -o 'kitcut-studio[^/]*\.service' /proc/self/cgroup 2>/dev/null | tail -1)}"
  # every studio server unit systemd knows of (the legacy one too, during the migration), and
  # whether it is up; "activating" includes one waiting out RestartSec after a crash
  others="$(systemctl list-units --all --no-legend --plain --type=service \
    'kitcut-studio@*' kitcut-studio.service 2>/dev/null |
    awk -v self="$self" '$1 != self && ($3 == "active" || $3 == "activating" || $3 == "reloading") { printf "%s ", $1 }')"
  if [ -n "$others" ]; then
    echo "${self:-this unit} stopped; not announcing offline: still up: $others"
    exit 0
  fi
  "$py" -X utf8 "$REPO/studio/agent.py" --announce off || true
fi
exit 0  # the site not hearing is not a reason to fail the server
