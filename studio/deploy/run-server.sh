#!/usr/bin/env bash
# ExecStart of kitcut-studio.service: the server from the current release (studio/release.py),
# or from the working tree when no release is built yet -- the same choice serve.ps1 makes.
set -euo pipefail
REPO="${STUDIO_REPO:?}"
HOME_DIR="${STUDIO_HOME:?}"
code="$REPO"
if [ -f "$HOME_DIR/releases/current" ]; then
  code="$HOME_DIR/releases/$(head -1 "$HOME_DIR/releases/current" | tr -d '[:space:]')"
  [ -f "$code/studio/server.py" ] || { echo "the current release is missing: $code" >&2; exit 1; }
fi
cd "$code"
exec "$REPO/.venv/bin/python" -X utf8 "$code/studio/server.py" --port "${STUDIO_PORT:-8765}"
