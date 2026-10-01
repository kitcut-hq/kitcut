#!/usr/bin/env bash
# Install the studio's systemd units on this machine (run on the VM, as the checkout's owner): the
# server (a template, one instance per release), the unit that starts the current instance at
# boot, the tunnel, the daily Claude login check (a service and its timer) and the usage sampler
# (kitcut-usage.service: who uses the CPU and memory) -- plus the one kernel setting two servers on
# one port need.
#
#   bash studio/deploy/install.sh [--home /srv/kitcut/studio] [--dry-run]
#
# Fills the unit templates beside this file with this checkout's path, the studio home and the
# current user and installs them into /etc/systemd/system. It neither starts nor enables them: the
# tunnel may run on one machine only, and a studio that came up at boot would announce itself to
# kitcut.ai -- `serve.sh migrate` (once, from the legacy unit) or `serve.sh start` is the cutover
# (studio/deploy/README.md). Safe to run again at any time: an instance that is running keeps
# running, and picks up a changed unit file at its next start.
#
# It no longer installs the legacy kitcut-studio.service (one server, restarted on every ship):
# `serve.sh migrate` retires it, and re-installing it would bring it back.
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
put() {  # <path> <body>: a root-owned file, shown instead in a dry run
  if [ "$DRY" = 1 ]; then
    echo "  would write $1:"; echo "$2" | sed 's/^/    /'
  else
    echo "$2" | sudo tee "$1" >/dev/null
  fi
}

run mkdir -p "$HOME_DIR"
run chmod +x "$REPO"/studio/deploy/*.sh "$REPO"/studio/serve.sh
for unit in kitcut-studio@.service kitcut-studio-boot.service kitcut-tunnel.service \
  kitcut-login-check.service kitcut-login-check.timer kitcut-usage.service; do
  body="$(sed -e "s#@REPO@#$REPO#g" -e "s#@HOME@#$HOME_DIR#g" -e "s#@USER@#$USER_NAME#g" \
    "$REPO/studio/deploy/$unit")"
  put "/etc/systemd/system/$unit" "$body"
done
run sudo systemctl daemon-reload

# Two servers listen on 127.0.0.1:8765 during a ship (SO_REUSEPORT). When the old one closes its
# listener, the connections the kernel already queued on it are reset unless this migrates them
# to the other listener: a page's poll or a film's POST would fail at every ship. (Linux 5.14+.)
SYSCTL=/etc/sysctl.d/60-kitcut.conf
put "$SYSCTL" "# KitCut studio (studio/deploy/install.sh): a closing SO_REUSEPORT listener hands its
# queued connections to the other listener instead of resetting them (the old server, at a ship)
net.ipv4.tcp_migrate_req = 1"
run sudo sysctl -q -p "$SYSCTL"
[ "$DRY" = 1 ] || [ "$(sysctl -n net.ipv4.tcp_migrate_req)" = 1 ] ||
  { echo "net.ipv4.tcp_migrate_req did not take (kernel $(uname -r))" >&2; exit 1; }
echo "installed (not enabled, not started): studio home $HOME_DIR, code $REPO"
