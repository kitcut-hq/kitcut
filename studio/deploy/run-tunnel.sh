#!/usr/bin/env bash
# ExecStart of kitcut-tunnel.service. Reads only the tunnel's NAME from the studio's .env -- an
# EnvironmentFile= would hand cloudflared every secret in it.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
name="$(grep -E '^\s*STUDIO_TUNNEL\s*=' "$REPO/.env" | tail -1 | cut -d= -f2- | tr -d "\"' \r")"
[ -n "$name" ] || { echo "STUDIO_TUNNEL is not set in $REPO/.env" >&2; exit 1; }
exec cloudflared tunnel --no-autoupdate run --url "http://127.0.0.1:${STUDIO_PORT:-8765}" "$name"
