#!/usr/bin/env bash
# Install the studio's two systemd units on this machine (run on the VM, as the checkout's owner).
#
#   bash studio/deploy/install.sh [--home /srv/kitcut/studio] [--dry-run]
#
# Fills the unit templates beside this file with this checkout's path, the studio home and the
# current user and installs them into /etc/systemd/system. It neither starts nor enables them: the
# tunnel may run on one machine only, and a studio that came up at boot would announce itself to
# kitcut.ai -- `serve.sh start` (enable --now) is the cutover (studio/deploy/README.md).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOME_DIR="$(dirname "$REPO")/studio"
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --home) HOME_DIR="$2"; shift ;;
    --dry-run) DRY=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
USER_NAME="$(id -un)"
[ "$USER_NAME" != root ] || { echo "run as the checkout's owner, not root" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }

run mkdir -p "$HOME_DIR"
chmod +x "$REPO"/studio/deploy/*.sh "$REPO"/studio/serve.sh
for unit in kitcut-studio.service kitcut-tunnel.service; do
  body="$(sed -e "s#@REPO@#$REPO#g" -e "s#@HOME@#$HOME_DIR#g" -e "s#@USER@#$USER_NAME#g" \
    "$REPO/studio/deploy/$unit")"
  if [ "$DRY" = 1 ]; then
    echo "  would write /etc/systemd/system/$unit:"; echo "$body" | sed 's/^/    /'
  else
    echo "$body" | sudo tee "/etc/systemd/system/$unit" >/dev/null
  fi
done
run sudo systemctl daemon-reload
echo "installed (not enabled, not started): studio home $HOME_DIR, code $REPO"
