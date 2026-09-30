#!/usr/bin/env bash
# Everyday work on the production studio VM, from the laptop (over the WireGuard VPN). vm.sh is the
# machine itself (create, resize, delete); this is the studio on it. Nobody logs into the VM.
#
#   bash studio/deploy/ops.sh status                  health, the servers and their films, disks,
#                                                     the daily login check, errors in the last day
#   bash studio/deploy/ops.sh logs [studio|tunnel|login] [-n N] [-f]   studio: every server unit
#   bash studio/deploy/ops.sh ship [<commit>]         tag studio-stable, push, build and test the
#                                                     release on the VM, start its server beside the
#                                                     running one, return once it leads. Films being
#                                                     made carry on: the old server finishes them
#   bash studio/deploy/ops.sh releases                what is built there, and which one leads
#   bash studio/deploy/ops.sh rollback <sha12>        back to a release already built (no rebuild):
#                                                     a switch like a ship, nothing is stopped
#   bash studio/deploy/ops.sh migrate [<commit>]      ONCE: from the legacy one-server unit to one
#                                                     server per release (deploy/README.md); waits,
#                                                     on the VM, for the running films to finish
#   bash studio/deploy/ops.sh claude-log <film-id> [--all] [--grep T]   what Claude did, its API
#                                                     errors and waits, Claude Code's debug log
#   bash studio/deploy/ops.sh resume <film-id> [--plan] [--finish]   pick up a film the studio
#                                                     stopped half-way (studio/resume.py), in the
#                                                     same film; --plan spends nothing
#   bash studio/deploy/ops.sh share <film-id>|--missing [--dry-run] [--limit N]   a finished film's
#                                                     share-page title, description and picture
#                                                     (studio/share.py); the price is printed
#                                                     first, and --dry-run stops there
#   bash studio/deploy/ops.sh film "<idea>" [--seconds N] [--look L] [--unlisted] [--api] [--no-watch]
#                                                    a film made on the VM itself
#                                                     (on the Claude login unless --api), followed;
#                                                     --no-watch prints its id and returns
#   bash studio/deploy/ops.sh watch <film-id>...      follow films to the end (one line per change)
#   bash studio/deploy/ops.sh pull <film-id> [dest] [--all]   its outputs (or the whole folder) here
#   bash studio/deploy/ops.sh hide|show <film-id>     out of / back into the public gallery
#   bash studio/deploy/ops.sh forward [port]          the VM's studio on this laptop's 127.0.0.1:port
#                                                     (default 8765), as if it ran here
#   bash studio/deploy/ops.sh snapshot [--keep N]     an incremental snapshot of the data disk
#                                                     (films, checkout, .env), keep the newest N (7)
#   bash studio/deploy/ops.sh snapshots               list them
#
# Add --dry-run before the command to see what a changing one would do. KITCUT_VM names another VM.
set -euo pipefail
unset MSYS_NO_PATHCONV  # git (a Windows exe) needs /c/... translated; vm.sh sets its own
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_LOCAL="$(cd "$HERE/../.." && pwd)"
VM="${KITCUT_VM:-kitcut-studio-1}"
RG="${KITCUT_RG:-kitcut-PROD}"
PORT=8765
REMOTE=/srv/kitcut/repo
HOME_DIR=/srv/kitcut/studio
DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
cmd="${1:-status}"; shift || true

die() { echo "ops.sh: $*" >&2; exit 1; }
on() { bash "$HERE/vm.sh" ssh "$VM" "$@"; }
change() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
change_on() { if [ "$DRY" = 1 ]; then echo "  would run on $VM: $*"; else on "$@"; fi; }
# the remote side reads the token itself: it never crosses the wire or lands in a log here
TOKEN_SH="TOKEN=\$(grep -E '^STUDIO_TOKEN=' $REMOTE/.env | tail -1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^[\"\x27]//' -e 's/[\"\x27]\$//')"
az_() { MSYS_NO_PATHCONV=1 az "$@"; }

# The commit to ship: only what the team can see (on origin/studio-poc). Sets sha.
resolve() {
  local ref="${1:-origin/studio-poc}"
  git -C "$REPO_LOCAL" fetch -q origin
  sha="$(git -C "$REPO_LOCAL" rev-parse --verify "$ref^{commit}")" || die "no commit $ref"
  git -C "$REPO_LOCAL" merge-base --is-ancestor "$sha" origin/studio-poc ||
    die "$ref (${sha:0:12}) is not on origin/studio-poc -- merge and push it first"
}
# What the VM runs now, in one call: whether the legacy one-server unit is still installed
# ("loaded" until ops.sh migrate), and its /api/health. Sets legacy, health, leader.
vm_state() {
  local out=""
  out="$(on "systemctl show kitcut-studio.service -p LoadState --value; curl -s --max-time 5 http://127.0.0.1:$PORT/api/health; echo")" ||
    { [ "$DRY" = 1 ] || die "cannot reach $VM"; echo "  (cannot reach $VM: its state is not checked in this dry run)"; }
  legacy="$(printf '%s\n' "$out" | sed -n 1p | tr -d '\r')"
  health="$(printf '%s\n' "$out" | sed -n 2p)"
  leader="$(printf '%s' "$health" | release_of)"
}
release_of() { python -c 'import json,sys; print(json.load(sys.stdin).get("release", ""))' 2>/dev/null || true; }
# a /api/health reply (stdin): the leader's release, and every server with its films
servers() {
  python -c '
import json, sys
try:
    h = json.load(sys.stdin)
except ValueError:
    sys.exit("  (no answer from the studio)")
print("  leader runs %s: %s running, %s queued" % (h.get("release"), h.get("running"), h.get("queued")))
for i in h.get("instances") or []:
    print("  %-34s %-12s %-10s %-6s %s running" % (i.get("id"), i.get("release"), i.get("mode"), "leader" if i.get("leader") else "", i.get("running")))
'
}
# Tag studio-stable and put the commit on the VM (push.sh: the VM holds no GitHub credentials).
# The commit itself, not this clone's studio-poc (behind origin's in a worktree).
deliver() {
  echo "shipping ${sha:0:12}: $(git -C "$REPO_LOCAL" log --format=%s -1 "$sha")"
  change git -C "$REPO_LOCAL" tag -f studio-stable "$sha"
  change git -C "$REPO_LOCAL" push -q -f origin refs/tags/studio-stable
  if [ "$DRY" = 1 ]; then echo "  would run: push.sh $VM studio-poc $sha"; else bash "$HERE/push.sh" "$VM" studio-poc "$sha"; fi
}
# Follow a transient unit on the VM to its end (Ctrl+C stops the following, not the unit).
follow() {
  echo "following $1 (Ctrl+C stops following, not the work; ops.sh logs shows the servers)"
  # the unit's own Result decides the exit, not the journal follower's (killing it could leak a
  # non-zero status: a resume that finished its film was reported as failed, 2026-09-29)
  on "journalctl -u $1 -f -n 100 --no-pager -o cat & j=\$!
    while systemctl is-active -q $1; do sleep 5; done; sleep 2
    kill \$j 2>/dev/null; wait \$j 2>/dev/null
    r=\$(systemctl show $1 -p Result --value); echo \"$1: \${r:-success}\"
    if [ \"\${r:-success}\" = success ]; then exit 0; else exit 1; fi"
}
# the server units' environment (kitcut-studio@.service) for a transient unit: keep in sync with it
UNIT_ENV="--setenv=STUDIO_HOME=$HOME_DIR --setenv=STUDIO_REPO=$REMOTE --setenv=STUDIO_ENV_FILE=$REMOTE/.env"
UNIT_ENV="$UNIT_ENV --setenv=TZ=America/Los_Angeles --setenv=PYTHONUNBUFFERED=1 --setenv=HF_HOME=$REMOTE/../hf"
UNIT_ENV="$UNIT_ENV --setenv=PATH=\$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

case "$cmd" in
  status)
    printf 'VM %s: %s\n' "$VM" "$(az_ vm show -d -g "$RG" -n "$VM" --query powerState -o tsv 2>/dev/null || echo '?')"
    on "HOME_DIR=$HOME_DIR bash -s" <<'EOF'
h=$(curl -s --max-time 5 http://127.0.0.1:8765/api/health || true)
python3 - "$h" <<'PY'
import json, sys
try:
    h = json.loads(sys.argv[1])
except ValueError:
    print("studio: NOT ANSWERING on 127.0.0.1:8765"); sys.exit()
s = h["slots"]
print("studio: release %s  running %s  queued %s%s" % (h["release"], h["running"], h["queued"], "  DRAINING" if h.get("draining") else ""))
print("  pools: " + "  ".join("%s %d/%d (+%d waiting)" % (k, v["used"], v["capacity"], v["waiting"]) for k, v in s.items()))
# one server per release: the leader takes new films, an old one only finishes its own, then exits
for i in h.get("instances") or []:
    print("  server %-34s %-12s %-10s %-6s %s running" % (i.get("id"), i.get("release"), i.get("mode"), "leader" if i.get("leader") else "", i.get("running")))
PY
public=$(curl -s --max-time 8 https://studio.kitcut.ai/api/health | python3 -c 'import json,sys; print(json.load(sys.stdin)["release"])' 2>/dev/null || echo "NOT REACHABLE")
echo "studio.kitcut.ai: $public"
echo "units: $(for u in kitcut-tunnel kitcut-studio-boot kitcut-login-check.timer; do printf '%s=%s ' $u $(systemctl is-active $u); done)"
systemctl list-units --all --no-legend --plain 'kitcut-studio@*' kitcut-studio.service | awk '{ printf "  %s %s/%s\n", $1, $3, $4 }'
python3 - <<'PY'
import glob, json, os
home = os.environ["HOME_DIR"]
live = []
for p in glob.glob(home + "/projects/*/studio.json"):
    try:
        s = json.load(open(p))
    except (OSError, ValueError):
        continue
    if s.get("state") in ("queued", "claude", "finishing"):
        live.append("  %s  %-9s %3ss  %s  %-24s %s" % (os.path.basename(os.path.dirname(p)), s["state"], s.get("length", "?"), s.get("auth", "?"), s.get("server") or "", (s.get("prompt") or "")[:50]))
print("films in progress: %d" % len(live))
print("\n".join(sorted(live)))
PY
at=$(systemctl show kitcut-login-check.service -p ExecMainExitTimestamp --value)
res=$(systemctl show kitcut-login-check.service -p Result --value)
next=$(systemctl show kitcut-login-check.timer -p NextElapseUSecRealtime --value)
if [ -n "$at" ]; then echo "login check: $res at $at (next $next)"; else echo "login check: not run yet (first $next)"; fi
echo "disks: $(df -h / | awk 'NR==2{print "system "$3"/"$2}')  $(df -h /srv/kitcut | awk 'NR==2{print "data "$3"/"$2}')   load $(cut -d' ' -f1-3 /proc/loadavg)   mem free $(free -g | awk '/Mem:/{print $7}') GB"
n=$(journalctl -u 'kitcut-studio@*' -u kitcut-studio -u kitcut-tunnel --since -24h -p err --no-pager -q | wc -l)
echo "errors in the last 24 h: $n"
[ "$n" = 0 ] || journalctl -u 'kitcut-studio@*' -u kitcut-studio -u kitcut-tunnel --since -24h -p err --no-pager -q | tail -5 | cut -c1-200
EOF
    ;;

  logs)
    # studio: every server, one unit per release (kitcut-studio@<instance>), and the legacy unit's
    # history; with-unit prefixes each line with its unit, so two servers' lines can be told apart
    unit="'kitcut-studio@*' -u kitcut-studio -o with-unit"; n=100; follow=""
    while [ $# -gt 0 ]; do
      case "$1" in
        studio) ;; tunnel) unit=kitcut-tunnel ;; login) unit=kitcut-login-check ;;
        -n) n="$2"; shift ;; -f) follow="-f" ;; *) die "logs [studio|tunnel|login] [-n N] [-f]" ;;
      esac
      shift
    done
    on "journalctl -u $unit -n $n --no-pager $follow"
    ;;

  ship)
    resolve "${1:-}"
    vm_state
    [ "$legacy" != loaded ] ||
      die "$VM still runs the legacy one-server unit, which a ship would restart: ops.sh migrate (once; deploy/README.md)"
    echo "on $VM now:"; printf '%s' "$health" | servers || true
    # The releases share one venv ($REMOTE/.venv): a changed dependency, once installed, changes
    # what the old server's films run too, in the middle of those films
    if [[ "$leader" =~ ^[0-9a-f]{12}$ ]] && git -C "$REPO_LOCAL" cat-file -e "$leader^{commit}" 2>/dev/null; then
      changed="$(git -C "$REPO_LOCAL" diff --name-only "$leader" "$sha" -- '*requirements*.txt')"
      [ -z "$changed" ] || echo "ops.sh: WARNING: ${changed//$'\n'/ } changed since $leader. Every release shares $REMOTE/.venv, so installing them changes the steps of the films the old server is still making -- ship this at a quiet moment (ops.sh status shows no films)." >&2
    else
      echo "ops.sh: warning: cannot compare requirements*.txt with the leader's release '${leader:-?}'" >&2
    fi
    deliver
    # release.py builds into the home the servers read (STUDIO_HOME: the units', named here as well)
    # and tests the snapshot; serve.sh then starts its server beside the running one and returns
    # once it leads. Nothing is drained or restarted: films being made finish on the old server.
    change_on "cd $REMOTE && STUDIO_HOME=$HOME_DIR bash studio/serve.sh release"
    if [ "$DRY" = 0 ]; then
      # the health's release is the leader's, whichever server answers: here, and through the tunnel
      out="$(on "curl -s --max-time 5 http://127.0.0.1:$PORT/api/health; echo; curl -s --max-time 8 https://studio.kitcut.ai/api/health; echo")"
      got="$(printf '%s\n' "$out" | sed -n 1p | release_of)"
      pub="$(printf '%s\n' "$out" | sed -n 2p | release_of)"
      printf '%s\n' "$out" | sed -n 1p | servers || true
      [ "$got" = "${sha:0:12}" ] || die "the studio reports ${got:-nothing}, expected ${sha:0:12}"
      echo "live: $got   studio.kitcut.ai: ${pub:-NOT REACHABLE}"
      [ "$pub" = "$got" ] || echo "ops.sh: warning: studio.kitcut.ai does not report $got" >&2
    fi
    ;;

  migrate)
    # ONCE: the legacy one-server unit becomes one server per release (deploy/README.md, "The
    # migration"). The code first (push.sh), then the units (install.sh), then serve.sh migrate on
    # the VM in a unit of its own: it waits for the legacy server's films with no timeout, which
    # can take hours, so it must not depend on this laptop staying awake.
    ref=""
    for a in "$@"; do case "$a" in --dry-run) DRY=1 ;; *) ref="$a" ;; esac; done
    resolve "$ref"
    vm_state
    [ "$legacy" = loaded ] || [ "$DRY" = 1 ] ||
      die "$VM has no legacy kitcut-studio unit: already migrated (ops.sh ship ships)"
    echo "on $VM now:"; printf '%s' "$health" | servers || true
    deliver
    change_on "bash $REMOTE/studio/deploy/install.sh --home $HOME_DIR"
    unit="kitcut-migrate-$(date +%Y%m%d-%H%M%S)"
    if [ "$DRY" = 1 ]; then
      # what the VM's own scripts would do -- only once they are the ones that know how
      if on "grep -q 'kitcut-studio@' $REMOTE/studio/deploy/install.sh" 2>/dev/null; then
        on "bash $REMOTE/studio/deploy/install.sh --home $HOME_DIR --dry-run
          cd $REMOTE && STUDIO_HOME=$HOME_DIR bash studio/serve.sh --dry-run migrate"
      else
        echo "  would run on $VM, detached ($unit): STUDIO_HOME=$HOME_DIR bash studio/serve.sh migrate"
      fi
      exit 0
    fi
    on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE $UNIT_ENV bash $REMOTE/studio/serve.sh migrate"
    follow "$unit"
    ;;

  releases)
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR .venv/bin/python -X utf8 studio/release.py --list"
    ;;

  rollback)
    # a switch like a ship: a server of the older release starts beside the running one and leads;
    # the one it replaces finishes its films
    rel="${1:?rollback <sha12> (see: ops.sh releases)}"
    [[ "$rel" =~ ^[0-9a-f]{12}$ ]] || die "not a release: $rel"
    on "test -f $HOME_DIR/releases/$rel/studio/server.py" || die "no release $rel built on $VM"
    change_on "cd $REMOTE && STUDIO_HOME=$HOME_DIR bash studio/serve.sh use $rel"
    ;;

  claude-log)
    # what Claude did on a film and what went wrong: its transcript and Claude Code's debug log,
    # read on the VM into one short page (studio/claude_log.py). Reads only
    id="${1:?claude-log <film-id> [--all] [--debug N] [--grep TEXT]}"; shift
    [[ "$id" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $id"
    args=""; for a in "$@"; do args="$args $(printf '%q' "$a")"; done  # quoted for the VM's shell
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR $REMOTE/.venv/bin/python -X utf8 studio/claude_log.py $id$args"
    ;;

  resume)
    id="${1:?resume <film-id> [--plan] [--finish] [--minutes N]}"; shift
    [[ "$id" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $id"
    plan=0; how=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --plan) plan=1 ;; --finish) how="$how --finish" ;;
        --minutes) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--minutes needs a number"; how="$how --minutes $2"; shift ;;
        *) die "resume <film-id> [--plan] [--finish] [--minutes N]" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/resume.py $id $how"
    # the plan first, always: it spends nothing, and it refuses a film that may not be picked up
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE STUDIO_ENV_FILE=$REMOTE/.env $py --plan" || exit 1
    [ "$plan" = 1 ] && exit 0
    # a unit of its own with the servers' environment (UNIT_ENV): each step gets its cgroup
    # (Delegate), the log goes to the journal, and the film goes on if this laptop sleeps
    unit="kitcut-resume-${id#studio-}"
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p Delegate=yes -p KillMode=control-group $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  share)
    # a finished film's share (studio/share.py): the price first, always -- it spends nothing --
    # then the work in a unit of its own, like resume, so it goes on if this laptop sleeps
    use="share <film-id>|--missing [--dry-run] [--limit N]"
    what="${1:?$use}"; shift
    if [ "$what" = "--missing" ]; then args="--missing"
    else
      [[ "$what" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $what"
      args="--film $what"
    fi
    only_price=0
    while [ $# -gt 0 ]; do
      case "$1" in
        --dry-run) only_price=1 ;;
        --limit) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--limit needs a number"; args="$args --limit $2"; shift ;;
        *) die "$use" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/share.py $args"
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE STUDIO_ENV_FILE=$REMOTE/.env $py --dry-run" || exit 1
    [ "$only_price" = 1 ] && exit 0
    unit="kitcut-share-$(date +%Y%m%d-%H%M%S)"
    # capped, and behind the films: an uncapped --missing grew to 15 GB of the VM's 16 on
    # 2026-09-29 and the films being made could not start Claude (KI-045)
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p MemoryHigh=2G -p MemoryMax=3G -p Nice=10 $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  film)
    idea="${1:?film \"<idea>\" [--seconds N] [--look L] [--unlisted] [--api] [--no-watch]}"; shift
    secs=30; auth=""; look=drawn; listed=1; follow=1
    while [ $# -gt 0 ]; do
      case "$1" in --seconds) secs="$2"; shift ;; --look) look="$2"; shift ;; --unlisted) listed=0 ;;
        --api) auth=', "auth": "api"' ;; --no-watch) follow=0 ;; esac
      shift
    done
    # --look: drawn, painted, collage (the studio refuses one it does not have); --unlisted: link-only
    body="$(python -c 'import json,sys; print(json.dumps({"prompt": sys.argv[1], "seconds": int(sys.argv[2]), "look": sys.argv[3], "listed": sys.argv[4] == "1"}))' "$idea" "$secs" "$look" "$listed")"
    body="${body%\}}$auth}"
    [ "$DRY" = 1 ] && { echo "  would POST $body to the VM's studio"; exit 0; }
    id="$(printf '%s' "$body" | on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' --data-binary @-" | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or sys.exit(json.dumps(d)))')"
    echo "film $id"
    # --no-watch: to start several, start each this way and `watch` them together. Never put a
    # following `film` in the background of a shell that exits: the POST may already have gone
    # when the shell kills it, and a retry then makes the film twice (2026-09-29: two Apollo 13s)
    [ "$follow" = 1 ] || exit 0
    exec bash "$0" watch "$id"
    ;;

  watch)
    id="${1:?watch <film-id>...}"
    if [ $# -gt 1 ]; then
      # several: one line per film whose status or stage changed, until every one has finished
      on "$TOKEN_SH; declare -A last; while :; do
        open=0
        for i in $*; do
          s=\$(curl -s http://127.0.0.1:$PORT/api/films/\$i -H \"Authorization: Bearer \$TOKEN\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"status\"), d.get(\"stage\"), round(d.get(\"cost_usd\") or 0, 2), (d.get(\"error\") or \"\")[:100])' 2>/dev/null) || s='unreadable'
          k=\"\${s%% *} \$(echo \"\$s\" | cut -d' ' -f2)\"
          [ \"\$k\" != \"\${last[\$i]:-}\" ] && echo \"\$(date +%T)  \$i  \$s\"; last[\$i]=\$k
          case \"\$s\" in done*|error*|cancelled*|lost*) ;; *) open=1 ;; esac
        done
        [ \$open = 0 ] && break
        sleep 30
      done"
      exit 0
    fi
    on "$TOKEN_SH; last=''; while :; do
      d=\$(curl -s http://127.0.0.1:$PORT/api/films/$id -H \"Authorization: Bearer \$TOKEN\")
      s=\$(printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"status\"), d.get(\"stage\"), d.get(\"wait\") or \"\")' 2>/dev/null) || s='unreadable'
      [ \"\$s\" != \"\$last\" ] && echo \"\$(date +%T)  \$s\"; last=\$s
      case \"\$s\" in done*|error*|cancelled*|lost*) break ;; esac
      sleep 10
    done
    printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d.get(k) for k in (\"status\",\"seconds\",\"cost_usd\",\"stages\",\"video_url\",\"error\")}, indent=1))'"
    ;;

  pull)
    id="${1:?pull <film-id> [dest] [--all]}"; dest="${2:-$REPO_LOCAL/temp/vm-films}"
    what=outputs; [ "${3:-${2:-}}" = "--all" ] && what="." && dest="${dest%--all}"
    [ "$dest" = "--all" ] || [ -z "$dest" ] && dest="$REPO_LOCAL/temp/vm-films"
    mkdir -p "$dest/$id"
    on "cd $HOME_DIR/projects/$id && tar -cf - $what" | tar -xf - -C "$dest/$id"
    echo "$(du -sh "$dest/$id" | cut -f1)  $dest/$id"
    ;;

  hide|show)
    id="${1:?$cmd <film-id>}"; flag=$([ "$cmd" = hide ] && echo true || echo false)
    change_on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/admin/films/$id/hidden -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' -d '{\"hidden\": $flag}'; echo"
    ;;

  forward)
    p="${1:-8765}"
    echo "the VM's studio on http://127.0.0.1:$p (Ctrl+C to stop). Requests arrive from the VM's own"
    echo "loopback, so they count as 'this machine': films on the Claude login, admin routes allowed."
    exec bash "$HERE/vm.sh" ssh "$VM" -N -L "$p:127.0.0.1:$PORT"
    ;;

  snapshot)
    keep=7; [ "${1:-}" = "--keep" ] && keep="$2"
    disk="$(az_ disk show -g "$RG" -n "$VM-data" --query id -o tsv)"
    name="$VM-data-$(date +%Y%m%d-%H%M)"
    # incremental: billed for what changed since the last one, not the disk's 512 GB
    change az_ snapshot create -g "$RG" -n "$name" --source "$disk" --incremental true \
      --sku Standard_LRS --tags app=kitcut-studio-snapshot --output none
    [ "$DRY" = 1 ] || echo "snapshot: $name"
    old="$(az_ snapshot list -g "$RG" --query "sort_by([?tags.app=='kitcut-studio-snapshot'], &timeCreated)[].name" -o tsv | head -n -"$keep")"
    for s in $old; do change az_ snapshot delete -g "$RG" -n "$s"; echo "  pruned $s"; done
    ;;

  snapshots)
    az_ snapshot list -g "$RG" --query "sort_by([?tags.app=='kitcut-studio-snapshot'], &timeCreated)[].{name:name, created:timeCreated, gb:diskSizeGb}" -o table
    ;;

  *) sed -n 2,38p "$0"; exit 2 ;;
esac
