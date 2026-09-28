#!/usr/bin/env bash
# Put code on the studio VM: push a branch (and the studio-stable tag) from this laptop into a bare
# repo on the VM, then move the VM's checkout to it. The VM holds no GitHub credentials at all
# (and kitcut-hq/kitcut has deploy keys disabled): code only ever arrives from here.
#
#   bash studio/deploy/push.sh <vm> [branch]     default branch: studio-poc
#
# Then ship it: bash studio/deploy/vm.sh ssh <vm> 'bash /srv/kitcut/repo/studio/serve.sh release'
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
VM="${1:?vm name}"
BRANCH="${2:-studio-poc}"
KEY="${KITCUT_SSH_KEY:-$HOME/.ssh/kitcut-studio}"
vm() { bash "$HERE/vm.sh" "$@"; }

ip="$(vm ip "$VM")"
export GIT_SSH_COMMAND="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HOME/.ssh/known_hosts.kitcut"
vm ssh "$VM" '[ -d /srv/kitcut/git ] || git init -q --bare /srv/kitcut/git'
refs=("refs/heads/$BRANCH:refs/heads/$BRANCH")
git -C "$REPO_LOCAL" rev-parse -q --verify refs/tags/studio-stable >/dev/null &&
  refs+=("+refs/tags/studio-stable:refs/tags/studio-stable")
git -C "$REPO_LOCAL" push -q --force "ssh://kitcut@$ip/srv/kitcut/git" "${refs[@]}"
vm ssh "$VM" 'set -e
if [ ! -d /srv/kitcut/repo/.git ]; then git clone -q /srv/kitcut/git /srv/kitcut/repo; fi
cd /srv/kitcut/repo
git fetch -q --force --tags origin
# the checkout only ever mirrors what was pushed (its .env and .venv are untracked)
git checkout -q -f -B '"$BRANCH"' origin/'"$BRANCH"'
echo "  $(hostname): $(git log --oneline -1)"'
