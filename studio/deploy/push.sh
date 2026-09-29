#!/usr/bin/env bash
# Put code on the studio VM: push a branch (and the studio-stable tag) from this laptop into a bare
# repo on the VM, then move the VM's checkout to it. The VM holds no GitHub credentials at all
# (and kitcut-hq/kitcut has deploy keys disabled): code only ever arrives from here.
#
#   bash studio/deploy/push.sh <vm> [branch] [commit]   default branch: studio-poc
#
# With a commit, that commit is what the VM's branch becomes (ops.sh ship passes the one it ships);
# without, this clone's own branch -- which in a worktree, or any clone that has not pulled, is an
# older commit than origin's, and the VM would then run an older serve.sh than the one shipped.
#
# Then ship it: bash studio/deploy/vm.sh ssh <vm> 'bash /srv/kitcut/repo/studio/serve.sh release'
set -euo pipefail
unset MSYS_NO_PATHCONV  # git (a Windows exe) must still get /c/... paths translated; vm.sh sets its own
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
VM="${1:?vm name}"
BRANCH="${2:-studio-poc}"
REV="${3:-refs/heads/$BRANCH}"
KEY="${KITCUT_SSH_KEY:-$HOME/.ssh/kitcut-studio}"
vm() { bash "$HERE/vm.sh" "$@"; }

ip="$(vm ip "$VM")"
export GIT_SSH_COMMAND="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HOME/.ssh/known_hosts.kitcut"
# The VM's repo refuses to move a branch or a tag backwards, whoever pushes. On 2026-09-28 a clone
# that had not pulled force-pushed an older studio-poc from its own old push.sh, the checkout went
# back with it, and its old serve.sh drained the live studio. A check in this script would not
# have helped -- the stale clone runs its own copy -- so the refusal lives on the VM (git's
# receive.denyNonFastForwards); set again here each time, and a rebuilt VM gets it on first push.
vm ssh "$VM" '[ -d /srv/kitcut/git ] || git init -q --bare /srv/kitcut/git
git -C /srv/kitcut/git config receive.denyNonFastForwards true'
refs=("$REV:refs/heads/$BRANCH")
git -C "$REPO_LOCAL" rev-parse -q --verify refs/tags/studio-stable >/dev/null &&
  refs+=("+refs/tags/studio-stable:refs/tags/studio-stable")
git -C "$REPO_LOCAL" push -q --force "ssh://kitcut@$ip/srv/kitcut/git" "${refs[@]}" || {
  echo "push.sh: the VM refused -- it has newer code than this clone ($(git -C "$REPO_LOCAL" rev-parse --short "$REV")):" \
    "pull origin, then ship. (To go back to an older release: ops.sh rollback <sha12>.)" >&2
  exit 1
}
vm ssh "$VM" 'set -e
if [ ! -d /srv/kitcut/repo/.git ]; then git clone -q /srv/kitcut/git /srv/kitcut/repo; fi
cd /srv/kitcut/repo
git fetch -q --force --tags origin
# the checkout only ever mirrors what was pushed (its .env and .venv are untracked)
git checkout -q -f -B '"$BRANCH"' origin/'"$BRANCH"'
echo "  $(hostname): $(git log --oneline -1)"'
