#!/usr/bin/env bash
# The laptop's half of "SSH for Claude cloud sessions" (studio/deploy/README.md): the cloud's own
# key pair, and the setup script to paste into the cloud environment's dialog at claude.ai/code.
# After that every session in the environment starts able to run
#
#   ssh kitcut-studio-1 '<command>'        (and so vm.sh ssh, ops.sh ...)
#
#   bash studio/deploy/cloud-env.sh <private dir>          # write <private dir>/setup-script.sh
#   bash studio/deploy/cloud-env.sh <private dir> --pub    # the public key line, for ssh-tunnel.sh key
#   bash studio/deploy/cloud-env.sh <private dir> --test   # the same connection, made from here
#
# <private dir> is OUTSIDE the repo (Documents/kitcut-access-cloud on the owner's laptop). It holds
#   gate.env          the secret ssh.kitcut.ai asks for        (ssh-lock.mjs --out)
#   kitcut-cloud      the cloud's private key, and .pub        (made here if missing)
#   host-key.pub      the VM's own public host key             (read over the VPN if missing)
#   setup-script.sh   the result: it carries the key and the secret, so it is as private as they are
#
# A cloud session can open HTTPS and nothing else (measured 2026-10-12: port 22 never opens, and the
# session's proxy resets anything that is not TLS), so SSH rides inside a WebSocket: cloudflared on
# the session's side, the VM's second tunnel on the other (ssh-tunnel.sh). --test proves everything
# except the session's proxy, which the measurement covered.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${KITCUT_SSH_HOST:-ssh.kitcut.ai}"
VM="${KITCUT_VM:-kitcut-studio-1}"
# A session names the studio as ops.sh's default does (kitcut-studio-1), whichever machine is behind
# ssh.kitcut.ai, so the script answers to that name and to the machine's own. The host key is pinned
# under one alias that does not change with the machine.
NAMES="kitcut-studio-1"; [ "$VM" = kitcut-studio-1 ] || NAMES="$NAMES $VM"
PIN="kitcut-studio"
ADMIN="kitcut"
DIR="${1:?cloud-env.sh <private dir> [--pub|--test]}"
mode="${2:-}"
die() { echo "cloud-env.sh: $*" >&2; exit 1; }

mkdir -p "$DIR"
[ -f "$DIR/kitcut-cloud" ] ||
  ssh-keygen -q -t ed25519 -N "" -C "claude-cloud@kitcut-studio" -f "$DIR/kitcut-cloud"
if [ "$mode" = --pub ]; then cat "$DIR/kitcut-cloud.pub"; exit 0; fi

[ -f "$DIR/gate.env" ] || die "$DIR/gate.env is missing: make the lock first (ssh-lock.mjs --out)"
gate="$(sed -n 's/^KITCUT_SSH_GATE=//p' "$DIR/gate.env" | tr -d '\r')"
[ -n "$gate" ] || die "$DIR/gate.env holds no KITCUT_SSH_GATE"
[ -f "$DIR/host-key.pub" ] ||
  bash "$HERE/vm.sh" ssh "$VM" 'cat /etc/ssh/ssh_host_ed25519_key.pub' > "$DIR/host-key.pub"
read -r hk_type hk_data _ < "$DIR/host-key.pub"
[ "$hk_type" = ssh-ed25519 ] || die "$DIR/host-key.pub is not an ed25519 host key"

# The connection a session makes, made from here with the pinned host key. The script is written
# only after it succeeds: a machine moved behind ssh.kitcut.ai (Azure -> kc-local, 2026-10-13) has
# another host key, and a script pinning the old one stops every session at "host key changed".
probe() {
  printf '%s %s %s\n' "$PIN" "$hk_type" "$hk_data" > "$DIR/known_hosts"
  ssh -i "$DIR/kitcut-cloud" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$DIR/known_hosts" -o HostKeyAlias="$PIN" -o ConnectTimeout=20 \
    -o ProxyCommand="cloudflared access ssh --hostname $HOST --header 'x-kitcut-gate: $gate'" \
    "$ADMIN@$HOST" 'echo "reached $(hostname) as $(whoami), from ${SSH_CONNECTION%% *}"'
}
if [ "$mode" = --test ]; then probe; exit 0; fi
[ -z "$mode" ] || die "unknown argument: $mode"
probe || die "$DIR/host-key.pub is not the key of the machine behind $HOST: delete it and run again with KITCUT_VM=<that machine>"

out="$DIR/setup-script.sh"
{
  cat <<EOF
#!/bin/bash
# KitCut: every session in this environment can reach the studio ($VM):  ssh kitcut-studio-1 '<command>'
# Generated $(date -u +%Y-%m-%d) by studio/deploy/cloud-env.sh (kitcut-hq/kitcut); change it there,
# not here. It carries a private key and the gate secret: keep this environment to yourself.
# A setup script that fails stops the session from starting, so this one always exits 0 and
# writes what happened to /var/log/kitcut-setup.log.
{
  set -u
  export DEBIAN_FRONTEND=noninteractive
  command -v ssh >/dev/null 2>&1 || { apt-get update -qq; apt-get install -y -qq openssh-client; }
  command -v cloudflared >/dev/null 2>&1 || {
    curl -fsSL --retry 3 -o /usr/local/bin/cloudflared \\
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 &&
      chmod 755 /usr/local/bin/cloudflared
  }
  install -d -m 700 /root/.ssh
  cat > /root/.ssh/kitcut-studio <<'KITCUT_KEY'
EOF
  tr -d '\r' < "$DIR/kitcut-cloud"
  cat <<EOF
KITCUT_KEY
  chmod 600 /root/.ssh/kitcut-studio
  echo '$PIN $hk_type $hk_data' > /root/.ssh/known_hosts.kitcut
  cat > /root/.ssh/config.kitcut <<'KITCUT_CONF'
Host $NAMES
  HostName $HOST
  HostKeyAlias $PIN
  User $ADMIN
  IdentityFile /root/.ssh/kitcut-studio
  IdentitiesOnly yes
  UserKnownHostsFile /root/.ssh/known_hosts.kitcut
  StrictHostKeyChecking yes
  ServerAliveInterval 30
  ProxyCommand /usr/local/bin/cloudflared access ssh --hostname $HOST --header "x-kitcut-gate: $gate"
KITCUT_CONF
  chmod 600 /root/.ssh/config.kitcut
  # Include applies to every host only from the top of the file
  if ! grep -qs '^Include /root/.ssh/config.kitcut' /root/.ssh/config; then
    { echo 'Include /root/.ssh/config.kitcut'; cat /root/.ssh/config 2>/dev/null; } > /root/.ssh/config.new
    mv /root/.ssh/config.new /root/.ssh/config
  fi
  chmod 600 /root/.ssh/config
  ssh -V; /usr/local/bin/cloudflared --version
} > /var/log/kitcut-setup.log 2>&1
exit 0
EOF
} > "$out"
chmod 600 "$out"
bash -n "$out" || die "the generated script does not parse"
echo "wrote $out ($(wc -l < "$out") lines): paste it into the environment's Setup script and save"
