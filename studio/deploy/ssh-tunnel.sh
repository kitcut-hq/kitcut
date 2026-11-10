#!/usr/bin/env bash
# The second Cloudflare tunnel on the studio VM: ssh.kitcut.ai -> this machine's sshd, so a Claude
# cloud session (which can open HTTPS and nothing else) can reach it. Runs ON the VM as the
# checkout's owner; from the laptop, pipe it over:
#
#   bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- closed' < studio/deploy/ssh-tunnel.sh
#   bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- up'     < studio/deploy/ssh-tunnel.sh
#   bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- status' < studio/deploy/ssh-tunnel.sh
#   bash studio/deploy/vm.sh ssh kitcut-studio-1 'bash -s -- down'   < studio/deploy/ssh-tunnel.sh
#
# closed  the tunnel and its address exist but answer 404: nothing behind it. This is the state to
#         prove the lock in (ssh-lock.mjs --probe) before sshd is put there.
# up      the address leads to sshd on 127.0.0.1:22. Only after the probe passed.
# down    stops and disables the unit; the address then answers Cloudflare's own error.
# key     'bash -s -- key "<public key line>"': lets that key in, through this tunnel only
#         (cloud-env.sh makes the pair). To take the access away: delete its line from
#         ~/.ssh/authorized_keys, or `down`.
# status  what is running and where it points; changes nothing.
#
# The order is lock, closed, probe, up (README, "SSH for Claude cloud sessions"): an address with a
# tunnel and no lock is the VM's SSH port on the internet.
#
# It is a SEPARATE tunnel with its own unit, so the studio's tunnel (kitcut-tunnel, studio.kitcut.ai)
# is never restarted for it. Everything it owns is in /srv/kitcut/ssh-tunnel, and its config is
# passed with --config: a config.yml in ~/.cloudflared would be read by the studio's tunnel at its
# next start and take the site down.
set -euo pipefail
HOST="${KITCUT_SSH_HOST:-ssh.kitcut.ai}"
NAME=kitcut-ssh
DIR=/srv/kitcut/ssh-tunnel
UNIT=kitcut-ssh-tunnel
mode="${1:-status}"
CF="$(command -v cloudflared)" || { echo "cloudflared is not installed" >&2; exit 1; }
[ "$(id -un)" != root ] || { echo "run as the checkout's owner, not root" >&2; exit 1; }

points_at() { sed -n 's/^ *service: *//p' "$DIR/config.yml" 2>/dev/null | head -1; }

case "$mode" in
  closed|up)
    mkdir -p "$DIR"; chmod 700 "$DIR"
    [ -f "$DIR/creds.json" ] || "$CF" tunnel create --credentials-file "$DIR/creds.json" "$NAME"
    chmod 600 "$DIR/creds.json"
    id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["TunnelID"])' "$DIR/creds.json")"
    target="ssh://127.0.0.1:22"
    [ "$mode" = up ] || target="http_status:404"
    cat > "$DIR/config.yml" <<EOF
# written by studio/deploy/ssh-tunnel.sh $mode
tunnel: $id
credentials-file: $DIR/creds.json
ingress:
  - hostname: $HOST
    service: $target
  - service: http_status:404
EOF
    "$CF" tunnel route dns "$id" "$HOST"
    sudo tee "/etc/systemd/system/$UNIT.service" >/dev/null <<EOF
# ssh.kitcut.ai -> this machine's sshd, for Claude cloud sessions. Written by
# studio/deploy/ssh-tunnel.sh; a separate tunnel from the studio's (kitcut-tunnel).
[Unit]
Description=KitCut SSH tunnel for Claude cloud sessions (cloudflared, $HOST)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
Group=$(id -gn)
ExecStart=$CF tunnel --no-autoupdate --config $DIR/config.yml run
Restart=always
RestartSec=5
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --quiet "$UNIT"
    sudo systemctl restart "$UNIT"
    for _ in $(seq 1 20); do
      sudo journalctl -u "$UNIT" --since -30s --no-pager -q | grep -q 'Registered tunnel connection' && break
      sleep 1
    done
    ;;
  down)
    sudo systemctl disable --now --quiet "$UNIT"
    ;;
  key)
    # the cloud's own public key, usable only by a connection that arrives through this tunnel
    # (cloudflared connects to sshd from 127.0.0.1), so a copy of the private key is worth nothing
    # from the VPN or anywhere else
    pub="${2:?key '<type> <base64> <comment>'}"
    read -r ktype kdata kname <<<"$pub"
    case "$ktype" in ssh-ed25519|ssh-rsa|ecdsa-*) ;; *) echo "not a public key: $ktype" >&2; exit 2 ;; esac
    auth="$HOME/.ssh/authorized_keys"
    if grep -qF "$kdata" "$auth"; then
      echo "key already there: $kname"
    else
      printf 'from="127.0.0.1,::1" %s %s %s\n' "$ktype" "$kdata" "$kname" >> "$auth"
      echo "key added: $kname"
    fi
    echo "keys on this machine: $(awk '{print $NF}' "$auth" | paste -sd' ')"
    ;;
  status) ;;
  *) echo "ssh-tunnel.sh closed|up|down|key '<public key>'|status" >&2; exit 2 ;;
esac

echo "unit: $(systemctl is-active "$UNIT" 2>/dev/null || true), $(systemctl is-enabled "$UNIT" 2>/dev/null || true)"
echo "$HOST -> $(points_at || true)"
echo "connections in the last minute: $(sudo journalctl -u "$UNIT" --since -60s --no-pager -q 2>/dev/null | grep -c 'Registered tunnel connection' || true)"
echo "the studio's tunnel: $(systemctl is-active kitcut-tunnel)"
