#!/usr/bin/env bash
# Build the production studio VM from nothing, from the laptop. Every step is idempotent, so a
# half-finished run is finished by running it again.
#
#   bash studio/deploy/provision.sh <vm> <size> [--data-gb 512] [--dry-run]
#   e.g. bash studio/deploy/provision.sh kitcut-studio-1 Standard_D8ads_v5
#
# 1. the VM (vm.sh create): Ubuntu 24.04, Standard HDD, SSH from this machine only
# 2. the data disk formatted and mounted at /srv/kitcut (checkout, studio home)
# 3. timezone America/Los_Angeles: the studio's daily caps count days in local time, as on the laptop
# 4. the checkout: pushed from this laptop (push.sh) -- KITCUT_BRANCH (default studio-poc) and the
#    studio-stable tag; the VM holds no GitHub credentials
# 5. the toolchain: scripts/setup-linux.sh --studio (ffmpeg, Edge, Python, Whisper models)
# 6. the studio's .env: only the keys the studio reads (procs.py), never STUDIO_ANNOUNCE -- that
#    is set at cutover, or a VM that booted would point kitcut.ai at itself -- plus the machine's
#    own settings (STUDIO_RENDER_ENCODE, VIDEDIT_WEBCODECS ...; deploy/README.md has the numbers)
# 7. the tunnel's credentials (~/.cloudflared), and the systemd units installed but not enabled
#
# It does not start the studio: that is the cutover (deploy/README.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
VM="${1:?vm name}"; SIZE="${2:?vm size}"; shift 2
DATA_GB=512
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --data-gb) DATA_GB="$2"; shift ;;
    --dry-run) DRY=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
ENV_SRC="${KITCUT_ENV_FILE:-$REPO_LOCAL/.env}"
[ -f "$ENV_SRC" ] || ENV_SRC="$(git -C "$REPO_LOCAL" worktree list | head -1 | cut -d' ' -f1)/.env"
BRANCH="${KITCUT_BRANCH:-studio-poc}"
# the keys studio/procs.py hands to steps, and the studio's own settings -- nothing else travels
KEYS="ANTHROPIC_API_KEY MONGODB_URI GOOGLE_SERVICE_ACCOUNT_KEY GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION GEMINI_API_KEY ELEVENLABS_API_KEY OPENROUTER_API_KEY STUDIO_TOKEN STUDIO_MEDIA_BASE STUDIO_MEDIA_SAS STUDIO_TTS_MODEL STUDIO_TUNNEL STUDIO_TUNNEL_HOST"
# this machine's own settings (measured on the VMs, 2026-09-28; deploy/README.md)
MACHINE_ENV="${KITCUT_MACHINE_ENV:-$HERE/machine.env}"

step() { printf '\n== %s ==\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
vm() { bash "$HERE/vm.sh" "$@"; }
on() { if [ "$DRY" = 1 ]; then echo "  would run on $VM: $*"; else vm ssh "$VM" "$@"; fi; }

step "1. the VM"
if az vm show -g "${KITCUT_RG:-kitcut-PROD}" -n "$VM" >/dev/null 2>&1; then
  echo "  exists: $VM ($(vm ip "$VM"))"
else
  run vm create "$VM" "$SIZE" --data-gb "$DATA_GB"
fi

step "2. data disk at /srv/kitcut"
on 'set -e
if ! mountpoint -q /srv/kitcut; then
  dev=$(lsblk -dpno NAME,SIZE,TYPE | awk -v s="'"$DATA_GB"'G" '"'"'$2==s && $3=="disk"{print $1}'"'"' | head -1)
  [ -n "$dev" ] || { echo "no '"$DATA_GB"' GB disk found" >&2; lsblk; exit 1; }
  sudo blkid "$dev" >/dev/null || sudo mkfs.ext4 -q -L kitcut "$dev"
  sudo mkdir -p /srv/kitcut
  grep -q "LABEL=kitcut" /etc/fstab || echo "LABEL=kitcut /srv/kitcut ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab >/dev/null
  sudo mount /srv/kitcut
fi
sudo chown "$(id -un):$(id -gn)" /srv/kitcut
df -h /srv/kitcut | tail -1'

step "3. timezone"
on 'sudo timedatectl set-timezone America/Los_Angeles && timedatectl | grep "Time zone"'

step "4. the checkout"
if [ "$DRY" = 1 ]; then echo "  would run: push.sh $VM $BRANCH"; else bash "$HERE/push.sh" "$VM" "$BRANCH"; fi

step "5. the toolchain"
on 'cd /srv/kitcut/repo && bash scripts/setup-linux.sh --studio 2>&1 | tail -4'

step "6. the studio's .env"
if [ "$DRY" = 1 ]; then echo "  would write $VM:/srv/kitcut/repo/.env from $ENV_SRC ($KEYS) + $MACHINE_ENV"; else
  {
    python3 - "$ENV_SRC" $KEYS <<'PY'
import sys
path, keys = sys.argv[1], set(sys.argv[2:])
for line in open(path, encoding="utf-8-sig"):
    k = line.split("=", 1)[0].strip()
    if k in keys:
        print(line.rstrip("\r\n"))
PY
    [ -f "$MACHINE_ENV" ] && grep -vE '^\s*(#|$)' "$MACHINE_ENV"
  } | vm ssh "$VM" 'umask 077 && cat > /srv/kitcut/repo/.env && grep -c = /srv/kitcut/repo/.env | sed "s/^/  keys: /"'
fi

step "7. tunnel credentials and the units"
if [ "$DRY" = 1 ]; then echo "  would copy ~/.cloudflared/*.json and cert.pem"; else
  tar -C "$HOME/.cloudflared" -cf - . | vm ssh "$VM" 'mkdir -p ~/.cloudflared && chmod 700 ~/.cloudflared && tar -xf - -C ~/.cloudflared && chmod 600 ~/.cloudflared/*'
fi
on 'bash /srv/kitcut/repo/studio/deploy/install.sh --home /srv/kitcut/studio'

echo
echo "provisioned $VM ($(vm ip "$VM" 2>/dev/null || echo '?')). Not started -- the cutover is in studio/deploy/README.md."
