#!/usr/bin/env bash
# ExecStart of the studio's units: the server, from a frozen release (studio/release.py).
#
#   run-server.sh <instance>   kitcut-studio@<instance>: the release the instance is named after,
#                              STUDIO_HOME/releases/<first 12 characters> (instance =
#                              <sha12>-<YYYYmmddHHMMSS>, serve.sh switch). Never releases/current:
#                              two instances of two releases run side by side during a ship, and a
#                              crashed old one must come back on its own code, not the newest.
#   run-server.sh              the legacy kitcut-studio.service, until `serve.sh migrate`: the
#                              current release, or the working tree when none is built -- the same
#                              choice serve.ps1 makes
set -euo pipefail
REPO="${STUDIO_REPO:?}"
HOME_DIR="${STUDIO_HOME:?}"
instance="${1:-}"
code="$REPO"
if [ -n "$instance" ]; then
  # exit 78: the unit's RestartPreventExitStatus -- a missing release does not come back by retrying
  [[ "$instance" =~ ^[0-9a-f]{12}(-|$) ]] || { echo "not an instance name: '$instance' (<sha12>-<YYYYmmddHHMMSS>)" >&2; exit 78; }
  code="$HOME_DIR/releases/${instance:0:12}"
  [ -f "$code/studio/server.py" ] || { echo "instance $instance: release ${instance:0:12} is not built ($code); serve.sh switch builds nothing" >&2; exit 78; }
  export STUDIO_INSTANCE="$instance"  # peers.py: the server's id is <instance>.<pid>
elif [ -f "$HOME_DIR/releases/current" ]; then
  code="$HOME_DIR/releases/$(head -1 "$HOME_DIR/releases/current" | tr -d '[:space:]')"
  [ -f "$code/studio/server.py" ] || { echo "the current release is missing: $code" >&2; exit 1; }
fi
cd "$code"
exec "$REPO/.venv/bin/python" -X utf8 "$code/studio/server.py" --port "${STUDIO_PORT:-8765}"
