#!/usr/bin/env bash
# Build the production studio VM from nothing, from the laptop. Every step is idempotent, so a
# half-finished run is finished by running it again.
#
#   bash studio/deploy/provision.sh <vm> <size> [--data-gb 512] [--attach <disk>] [--drill]
#                                   [--env-file <path> | --env-from-vm <vm>] [--dry-run]
#   e.g. bash studio/deploy/provision.sh kitcut-studio-1 Standard_D4ads_v5
#        bash studio/deploy/provision.sh kitcut-studio-2 Standard_D4ads_v5 --drill --env-from-vm kitcut-studio-1
#
# 1. the VM (vm.sh create): Ubuntu 24.04, Standard HDD, no public IP -- on the WireGuard VPN
#    (vm.sh network). The data disk: the one named <vm>-data when it exists (a rebuild keeps the
#    films, the checkout and the .env), --attach <disk> for one restored from Azure Backup, else
#    a new empty one (the home then comes back from the mirror: ops.sh restore --all)
# 2. the data disk formatted (only if it holds no filesystem) and mounted at /srv/kitcut
# 3. timezone America/Los_Angeles: the studio's daily caps count days in local time, as on the laptop
# 4. the checkout: pushed from this laptop (push.sh) -- KITCUT_BRANCH (default studio-poc) and the
#    studio-stable tag; the VM holds no GitHub credentials
# 5. the toolchain: scripts/setup-linux.sh --studio (ffmpeg, Edge, Python, Whisper models, rclone),
#    and models/ from the mirror when there is one (the instrument samples), else this laptop's
# 6. the studio's .env. The one on the data disk is KEPT as it is: it is the only file that holds
#    every key the machine uses, and writing it again from a laptop once dropped the films'
#    storage keys (KI-065). Only a machine with none gets one: from the key vault
#    (kitcut-kv-prod, secret studio-env: `ops.sh secrets push` keeps it current), or --env-file,
#    or --env-from-vm (another studio VM's, piped through this laptop, never written here)
# 7. the tunnel's credentials (~/.cloudflared): the VM's own are kept; else the key vault's, else
#    this laptop's copy, wherever under ~/.cloudflared it sits. Then the systemd units, and the
#    ones that are safe on any machine enabled: the login check, the usage sampler, the cleanup
#
# --drill builds a rehearsal: a machine made from the mirror to prove the mirror, which must not
# act as the studio (studio/restore.py says why). Its .env is the source's with the database,
# the announcement, the tunnel, the site's token and the films' bucket taken out, the bucket key
# kept only as the mirror's (to read it), and STUDIO_DRILL=1; it gets no tunnel credentials and
# nothing that writes outside itself is enabled. It ends with `restore.py --check-drill`.
#
# It does not start the studio, nor the tunnel, nor the mirror's timers: those are the cutover
# (deploy/README.md, "If the machine is gone"), after the home is known to be whole.
set -euo pipefail
unset MSYS_NO_PATHCONV  # git (a Windows exe) must still get /c/... paths translated; vm.sh sets its own
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
VM="${1:?vm name}"; SIZE="${2:?vm size}"; shift 2
DATA_GB=512
DRY=0
DRILL=0
ATTACH=""
ENV_FILE=""
ENV_VM=""
while [ $# -gt 0 ]; do
  case "$1" in
    --data-gb) DATA_GB="$2"; shift ;;
    --attach) ATTACH="$2"; shift ;;
    --drill) DRILL=1 ;;
    --env-file) ENV_FILE="$2"; shift ;;
    --env-from-vm) ENV_VM="$2"; shift ;;
    --dry-run) DRY=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
[ -z "$ENV_FILE" ] || [ -f "$ENV_FILE" ] || { echo "no such file: $ENV_FILE" >&2; exit 2; }
[ "$ENV_VM" != "$VM" ] || { echo "--env-from-vm names this very machine" >&2; exit 2; }
BRANCH="${KITCUT_BRANCH:-studio-poc}"
VAULT="${KITCUT_VAULT:-kitcut-kv-prod}"
# what a rehearsal's .env must not have (restore.not_a_drill checks the same): the live database,
# the announcement, the tunnel, the site's token, the films' bucket and where they are published
DRILL_DROP="MONGODB_URI STUDIO_ANNOUNCE STUDIO_TUNNEL STUDIO_TUNNEL_HOST KITCUT_SITE_TOKEN STUDIO_MEDIA_BASE STUDIO_MEDIA_OLD_BASE STUDIO_MEDIA_SAS STUDIO_OWN_VOICE"
# this machine's own settings (measured on the VMs, 2026-09-28; deploy/README.md)
MACHINE_ENV="${KITCUT_MACHINE_ENV:-$HERE/machine.env}"
az_() { MSYS_NO_PATHCONV=1 az "$@"; }

# a python that runs (on Windows `python3` is often only the Microsoft Store stub)
PY="$(for p in python3 python; do "$p" -c '' >/dev/null 2>&1 && { echo "$p"; break; }; done)"
[ -n "$PY" ] || { echo "no python on PATH" >&2; exit 1; }

step() { printf '\n== %s ==\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
vm() { bash "$HERE/vm.sh" "$@"; }
on() { if [ "$DRY" = 1 ]; then echo "  would run on $VM: $*"; else vm ssh "$VM" "$@"; fi; }

step "1. the VM"
if az vm show -g "${KITCUT_RG:-kitcut-PROD}" -n "$VM" >/dev/null 2>&1; then
  echo "  exists: $VM ($(vm ip "$VM"))"
else
  # the data disk outlives the machine: a rebuild reattaches it, films, checkout and .env included
  if [ -n "$ATTACH" ]; then
    run vm create "$VM" "$SIZE" --attach "$ATTACH"
  elif az disk show -g "${KITCUT_RG:-kitcut-PROD}" -n "$VM-data" >/dev/null 2>&1; then
    run vm create "$VM" "$SIZE" --attach "$VM-data"
  else
    run vm create "$VM" "$SIZE" --data-gb "$DATA_GB"
  fi
  # a machine built again at the address of the one before it has another host key, and ssh
  # (vm.sh: accept-new into known_hosts.kitcut) would refuse it as the old one's impostor
  if [ "$DRY" = 0 ]; then
    ip="$(vm ip "$VM" 2>/dev/null || true)"
    [ -z "$ip" ] || ssh-keygen -R "$ip" -f "$HOME/.ssh/known_hosts.kitcut" >/dev/null 2>&1 || true
  fi
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
# What production last ran: origin's studio-stable tag (ops.sh ship moves it), else origin's branch.
# Not this clone's own branch -- in a worktree, or a clone that has not pulled, that is an older
# commit (KI-065). And not the branch's head when the tag is behind it: the checkout's release.py
# then lists tests the tagged release does not have, and `serve.sh release` stops on the first
# (the first rehearsal, 2026-10-12: "can't open file .../test_restore.py").
git -C "$REPO_LOCAL" fetch -q --force --tags origin
REV="$(git -C "$REPO_LOCAL" ls-remote --tags origin refs/tags/studio-stable | cut -f1)"
[ -n "$REV" ] && git -C "$REPO_LOCAL" tag -f studio-stable "$REV" >/dev/null ||
  REV="$(git -C "$REPO_LOCAL" rev-parse --verify "origin/$BRANCH^{commit}")"
if [ "$DRY" = 1 ]; then echo "  would run: push.sh $VM $BRANCH ${REV:0:12}"; else bash "$HERE/push.sh" "$VM" "$BRANCH" "$REV"; fi

step "5. the toolchain"
on 'cd /srv/kitcut/repo && HF_HOME=/srv/kitcut/hf bash scripts/setup-linux.sh --studio 2>&1 | tail -4'
# the instrument samples every ensemble uses, from this laptop's cache (14 MB): a release's
# test_direction refuses to go current without them ("every ensemble instrument is cached")
SOUNDFONTS="$(git -C "$REPO_LOCAL" worktree list | head -1 | cut -d' ' -f1)/models/soundfonts"
if [ "$DRY" = 1 ]; then echo "  would copy $SOUNDFONTS"; elif [ -d "$SOUNDFONTS" ]; then
  tar -C "$(dirname "$(dirname "$SOUNDFONTS")")" -cf - models/soundfonts |
    vm ssh "$VM" 'tar -xf - -C /srv/kitcut/repo && echo "  soundfonts: $(ls /srv/kitcut/repo/models/soundfonts/*/ | wc -l) instruments"'
fi

step "6. the studio's .env"
# stdin: a .env as the source has it; stdout: as this machine gets it. A rehearsal's loses what
# would let it act as the studio (DRILL_DROP), keeps the bucket key only as the mirror's -- to
# read it -- and says what it is. Nothing is written on this laptop: the file goes through a pipe.
env_for_this_machine() {
  "$PY" -c '
import sys
drill, drop = sys.argv[1] == "1", set(sys.argv[2].split())
lines = sys.stdin.read().replace("\r", "").splitlines()
keys = {l.split("=", 1)[0].strip() for l in lines if "=" in l and not l.lstrip().startswith("#")}
own = "STUDIO_BACKUP_R2_KEY_ID" in keys  # the mirror already has a key of its own
out = []
for l in lines:
    k = l.split("=", 1)[0].strip()
    if drill and (k in drop or k == "STUDIO_DRILL"):
        continue
    if drill and k.startswith("STUDIO_R2_"):
        if own:
            continue
        l = "STUDIO_BACKUP_R2_" + l.lstrip()[len("STUDIO_R2_"):]
    out.append(l)
if drill:
    out.append("STUDIO_DRILL=1")
print("\n".join(out))
' "$DRILL" "$DRILL_DROP"
}
env_source() {
  if [ -n "$ENV_FILE" ]; then cat "$ENV_FILE"
  elif [ -n "$ENV_VM" ]; then vm ssh "$ENV_VM" 'cat /srv/kitcut/repo/.env'
  else
    # the key vault's copy (ops.sh secrets push), through a private folder that is removed at once
    local tmp; tmp="$(mktemp -d)"; chmod 700 "$tmp"
    az_ keyvault secret download --vault-name "$VAULT" --name studio-env --file "$tmp/env" --encoding utf-8 >/dev/null &&
      cat "$tmp/env"
    local rc=$?; rm -rf "$tmp"; return $rc
  fi
}
if [ -n "$ENV_FILE" ]; then from="$ENV_FILE"; elif [ -n "$ENV_VM" ]; then from="$ENV_VM's own"; else from="the key vault ($VAULT, studio-env)"; fi
if [ "$DRY" = 1 ]; then
  echo "  would keep $VM's own .env when it has one (unless --drill), else write it from $from"
elif [ "$DRILL" = 0 ] && vm ssh "$VM" 'test -s /srv/kitcut/repo/.env'; then
  echo "  kept: the machine's own .env ($(vm ssh "$VM" 'grep -c = /srv/kitcut/repo/.env') settings)"
else
  env_source | env_for_this_machine | vm ssh "$VM" 'set -e; umask 077; cd /srv/kitcut/repo
    cat > .env.new
    # a source that could not be read arrives empty: the machine is left without a .env, never
    # with a hollow one that starts a studio missing its keys
    [ "$(grep -c = .env.new)" -ge 8 ] || { rm -f .env.new; echo "  the .env that arrived is empty or too short: not written" >&2; exit 1; }
    mv .env.new .env && grep -c = .env | sed "s/^/  settings: /"' ||
    { echo "provision.sh: no .env from $from. Give one with --env-file or --env-from-vm, or store it first: ops.sh secrets push" >&2; exit 1; }
fi

step "7. tunnel credentials and the units"
if [ "$DRILL" = 1 ]; then
  echo "  a rehearsal: no tunnel credentials (two connectors would split the films between two disks)"
elif [ "$DRY" = 1 ]; then
  echo "  would give $VM the tunnel credentials when it has none: the key vault's, else this laptop's"
elif vm ssh "$VM" 'ls ~/.cloudflared/*.json >/dev/null 2>&1'; then
  echo "  the VM already holds the tunnel credentials"
else
  tmp="$(mktemp -d)"; chmod 700 "$tmp"
  name="$(az_ keyvault secret show --vault-name "$VAULT" --name studio-tunnel-credentials --query tags.file -o tsv 2>/dev/null || true)"
  if [ -n "$name" ] &&
    az_ keyvault secret download --vault-name "$VAULT" --name studio-tunnel-credentials --file "$tmp/$name" --encoding utf-8 >/dev/null 2>&1 &&
    az_ keyvault secret download --vault-name "$VAULT" --name studio-tunnel-cert --file "$tmp/cert.pem" --encoding utf-8 >/dev/null 2>&1; then
    echo "  tunnel credentials: from the key vault"
    src="$tmp"
  else
    # this laptop's copy. Since the move it sits in ~/.cloudflared/backup-*/, so that the laptop
    # cannot start a second connector -- and a version of this script that left those folders
    # out would have rebuilt the machine without its tunnel (KI-065)
    src="$(for d in "$HOME/.cloudflared" "$HOME"/.cloudflared/backup-*/; do
      ls "$d"/*.json >/dev/null 2>&1 && echo "${d%/}"; done | tail -1)"
    [ -n "$src" ] || { rm -rf "$tmp"; echo "provision.sh: no tunnel credentials in the key vault nor under ~/.cloudflared" >&2; exit 1; }
    echo "  tunnel credentials: from this laptop ($src)"
  fi
  tar -C "$src" -cf - --exclude='backup-*' . |
    vm ssh "$VM" 'mkdir -p ~/.cloudflared && chmod 700 ~/.cloudflared && tar -xf - -C ~/.cloudflared && chmod 600 ~/.cloudflared/*'
  rm -rf "$tmp"
fi
on 'bash /srv/kitcut/repo/studio/deploy/install.sh --home /srv/kitcut/studio'
# what is safe on any machine: who uses it, and the removal of finished films' working pictures.
# The login check writes into the site's database, so not on a rehearsal. The tunnel, the boot
# unit and the mirror's timers are the cutover's (serve.sh start, ops.sh backup install).
if [ "$DRILL" = 1 ]; then
  on 'sudo systemctl enable -q --now kitcut-usage.service kitcut-prune.timer'
  on 'cd /srv/kitcut/repo && STUDIO_HOME=/srv/kitcut/studio STUDIO_REPO=/srv/kitcut/repo .venv/bin/python -X utf8 studio/restore.py --check-drill'
else
  on 'sudo systemctl enable -q --now kitcut-usage.service kitcut-prune.timer kitcut-login-check.timer'
fi

echo
if [ "$DRILL" = 1 ]; then
  echo "provisioned $VM ($(vm ip "$VM" 2>/dev/null || echo '?')) as a rehearsal. Next: KITCUT_VM=$VM ops.sh restore --all --drill, then restore --settle (deploy/README.md)."
else
  echo "provisioned $VM ($(vm ip "$VM" 2>/dev/null || echo '?')). Not started -- the cutover is in studio/deploy/README.md, \"If the machine is gone\"."
fi
