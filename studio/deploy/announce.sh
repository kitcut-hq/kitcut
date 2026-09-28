#!/usr/bin/env bash
# ExecStartPost / ExecStopPost of kitcut-studio.service: tell kitcut.ai (MongoDB,
# kitcut.studio_hosts) that the studio is up at https://$STUDIO_TUNNEL_HOST, or offline.
# agent.py refuses unless the .env sets STUDIO_ANNOUNCE=1, which only the production VM does.
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
  "$py" -X utf8 "$REPO/studio/agent.py" --announce off || true
fi
exit 0  # the site not hearing is not a reason to fail the server
