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
#   bash studio/deploy/ops.sh drafts [--days N] [--json]   the YouTube drafts written lately: seconds
#                                                     to the words, to the thumbnail picks, to the
#                                                     pictures, cost (studio/draft_times.py). Reads only
#   bash studio/deploy/ops.sh usage [--hours N] [--at "HH:MM"] [--film ID]   who used the CPU and
#                                                     memory: by hour, the low points of memory, by
#                                                     film and by step (studio/deploy/usage.py)
#   bash studio/deploy/ops.sh usage install           install and (re)start the sampler behind it
#   bash studio/deploy/ops.sh resume <film-id> [--plan] [--finish]   pick up a film the studio
#                                                     stopped half-way (studio/resume.py), in the
#                                                     same film; --plan spends nothing
#   bash studio/deploy/ops.sh share <film-id>|--missing [--dry-run] [--limit N]   a finished film's
#                                                     share-page title, description and picture
#                                                     (studio/share.py); the price is printed
#                                                     first, and --dry-run stops there
#   bash studio/deploy/ops.sh share <film-id> --frame <seconds>|off   the film's own frame as its
#                                                     page's thumbnail, or the drawn one back; the
#                                                     words and the link preview stay, no cost
#   bash studio/deploy/ops.sh review <film-id> [--machine] [--api]   read a finished film for
#                                                     glitches as the studio reads one before it
#                                                     is done (studio/review.py): the whole of it
#                                                     a frame a second, then the moments worth a
#                                                     closer look. Prints what it finds; changes
#                                                     nothing. --machine: only what the drawing
#                                                     code shows, no Claude call
#   bash studio/deploy/ops.sh canon <p-id> [--show | --dry-run | --force]   a project's episode
#                                                     log (studio/canon.py): write the entries it
#                                                     lacks, oldest first; --show prints it
#   bash studio/deploy/ops.sh template push <templates/t-x/vN folder> | publish|retire|draft <t-x> <N>
#                                  | list | check      kitcut.ai's templates (studio/templates.py):
#                                                     push copies a version made on this laptop into
#                                                     the VM's home as a draft (a version never
#                                                     changes: it refuses one already there)
#   bash studio/deploy/ops.sh film "<what you want>" --template t-x [--attach file ...] [--frame 16:9] [--unlisted]
#                                                     a film remade from a template (a draft too: the
#                                                     VM itself may), its form's pictures uploaded first
#   bash studio/deploy/ops.sh film "<idea>" [--seconds N] [--look L] [--unlisted] [--api] [--no-watch]
#                                                    a film made on the VM itself
#                                                     (on the Claude login unless --api), followed;
#                                                     --no-watch prints its id and returns
#                                                     --attach file ...: photos and logos it may use,
#                                                     named upload1..N in the prompt, in that order
#                                                     --person "Name=photo.jpg" (up to 4), --style felt:
#                                                     people drawn into it as characters who talk
#   bash studio/deploy/ops.sh watch <film-id>...      follow films to the end (one line per change)
#   bash studio/deploy/ops.sh pull <film-id> [dest] [--all]   its outputs (or the whole folder) here
#   bash studio/deploy/ops.sh hide|show <film-id>     out of / back into the public gallery
#   bash studio/deploy/ops.sh unbrand <film-id> [--no-watch]   a finished Free-plan film drawn again
#                                                     without its mark and closing (studio/unbrand.py):
#                                                     a render, no Claude; followed to the end
#   bash studio/deploy/ops.sh notes <film-id> <notes.json> [--no-watch]   a round of changes to a
#                                                     finished film (studio/rounds.py): the notes in the
#                                                     file made into its next version; followed to the end.
#                                                     notes.json: [{"kind": "moment|spot|stretch|line|film",
#                                                     "t", "t2", "x", "y", "line", "words", "text"}, ...]
#   bash studio/deploy/ops.sh versions <film-id>      a film's versions, and how its last round ended
#   bash studio/deploy/ops.sh version <film-id> <n>   version n is the film again (nothing is rendered)
#   bash studio/deploy/ops.sh library-get <project> <dir>   a project's library to work on here:
#                                                     each member's latest version as
#                                                     <dir>/cast/<name>.js, cast.png, index.json
#   bash studio/deploy/ops.sh library-put <project> [--dry-run] [--replace] <cast/x.js>...
#                                                     a back-fill: cast files (places a series
#                                                     drew in film.js) into its library as the
#                                                     next versions (studio/library_put.py)
#   bash studio/deploy/ops.sh replace <film-id> <folder>   a remade film takes its place (same id
#                                                     and page; the old one to backups/)
#   bash studio/deploy/ops.sh delete <film-id>        a film deleted for good: its copy online, its
#                                                     record, its folder, what else names it. Nothing
#                                                     is kept. --dry-run says what would go
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
echo "units: $(for u in kitcut-tunnel kitcut-studio-boot kitcut-login-check.timer kitcut-usage; do printf '%s=%s ' $u $(systemctl is-active $u); done)"
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
# below 2 GB a film's Claude may not start at all ("Control request timeout: initialize", KI-045):
# say so loudly, and name what holds the memory
avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
if [ "$avail" -lt 2048 ]; then
  echo "WARNING: only $avail MB of memory available -- films may fail to start Claude (KI-045). Biggest:"
  ps -eo pid,rss,etime,args --sort=-rss | head -4 | cut -c1-160
fi
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

  usage)
    # who uses the machine: the sampler's timeline and the servers' steps log (deploy/usage.py)
    if [ "${1:-}" = install ]; then
      change_on "bash $REMOTE/studio/deploy/install.sh --home $HOME_DIR && sudo systemctl enable -q kitcut-usage.service && sudo systemctl restart kitcut-usage.service && systemctl is-active kitcut-usage.service"
    else
      on "STUDIO_HOME=$HOME_DIR python3 $REMOTE/studio/deploy/usage.py report$(printf ' %q' "$@")"
    fi
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
    # memory: uncapped -- this unit becomes the server itself; its films' steps have their own caps
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

  drafts)
    # where YouTube drafts spend their time, from their own records (studio/draft_times.py). Reads only
    args=""; for a in "$@"; do args="$args $(printf '%q' "$a")"; done
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR $REMOTE/.venv/bin/python -X utf8 studio/draft_times.py$args"
    ;;

  resume)
    id="${1:?resume <film-id> [--plan] [--finish [--patched]] [--minutes N]}"; shift
    [[ "$id" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $id"
    plan=0; how=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --plan) plan=1 ;; --finish) how="$how --finish" ;; --patched) how="$how --patched" ;;
        --minutes) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--minutes needs a number"; how="$how --minutes $2"; shift ;;
        *) die "resume <film-id> [--plan] [--finish [--patched]] [--minutes N]" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/resume.py $id $how"
    # the plan first, always: it spends nothing, and it refuses a film that may not be picked up
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE STUDIO_ENV_FILE=$REMOTE/.env $py --plan" || exit 1
    [ "$plan" = 1 ] && exit 0
    # a unit of its own with the servers' environment (UNIT_ENV): each step gets its cgroup
    # (Delegate), the log goes to the journal, and the film goes on if this laptop sleeps. Capped
    # like any job beside the live server (KI-045): a film peaks near 3 GB, the servers keep the rest
    unit="kitcut-resume-${id#studio-}"
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p Delegate=yes -p KillMode=control-group -p MemoryHigh=6G -p MemoryMax=8G $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  share)
    # a finished film's share (studio/share.py): the price first, always -- it spends nothing --
    # then the work in a unit of its own, like resume, so it goes on if this laptop sleeps
    use="share <film-id>|--missing [--dry-run] [--limit N] | share <film-id> --frame <seconds>|off"
    what="${1:?$use}"; shift
    if [ "$what" = "--missing" ]; then args="--missing"
    else
      [[ "$what" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $what"
      args="--film $what"
    fi
    only_price=0; frame=0
    while [ $# -gt 0 ]; do
      case "$1" in
        --dry-run) only_price=1 ;;
        --frame)
          [[ "$args" == --film* && "${2:-}" =~ ^(off|[0-9]+(\.[0-9]+)?)$ ]] || die "--frame needs a film id and seconds, or off"
          args="$args --frame $2"; frame=1; shift ;;
        --limit) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--limit needs a number"; args="$args --limit $2"; shift ;;
        *) die "$use" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/share.py $args"
    [ "$frame" = 1 ] || on "cd $REMOTE && STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE STUDIO_ENV_FILE=$REMOTE/.env $py --dry-run" || exit 1
    [ "$only_price" = 1 ] && exit 0
    unit="kitcut-share-$(date +%Y%m%d-%H%M%S)"
    # capped, and behind the films: an uncapped --missing grew to 15 GB of the VM's 16 on
    # 2026-09-29 and the films being made could not start Claude (KI-045)
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p MemoryHigh=2G -p MemoryMax=3G -p Nice=10 $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  review)
    # a finished film read for glitches (studio/review.py): its frames and the probe are rendered
    # beside the server, so in a capped unit like canon's, and not while a film records its voice
    use="review <film-id> [--machine] [--api]"
    id="${1:?$use}"; shift
    [[ "$id" =~ ^studio-[0-9]{8}-[0-9]{6}-[a-z0-9]+$ ]] || die "not a film id: $id"
    args="--film $id"
    while [ $# -gt 0 ]; do
      case "$1" in
        --machine) args="$args --machine" ;; --api) args="$args --auth api" ;;
        *) die "$use" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/review.py $args"
    unit="kitcut-review-$(date +%Y%m%d-%H%M%S)"
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p MemoryHigh=2G -p MemoryMax=3G -p Nice=10 $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  canon)
    # a project's episode log (studio/canon.py): --show reads it, --dry-run names the episodes
    # without an entry; else they are written, oldest first, in a capped unit like share's
    use="canon <p-id> [--show | --dry-run | --force]"
    proj="${1:?$use}"; shift
    [[ "$proj" =~ ^p-[a-z2-7]{10}$ ]] || die "not a project id: $proj"
    args="--project $proj --missing"; mode=write
    while [ $# -gt 0 ]; do
      case "$1" in
        --show) mode=show ;; --dry-run) mode=price ;; --force) args="$args --force" ;;
        *) die "$use" ;;
      esac
      shift
    done
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/canon.py $args"
    envs="STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE STUDIO_ENV_FILE=$REMOTE/.env"
    if [ "$mode" = show ]; then on "cd $REMOTE && $envs $py --show"; exit $?; fi
    on "cd $REMOTE && $envs $py --dry-run" || exit 1
    [ "$mode" = price ] && exit 0
    unit="kitcut-canon-$(date +%Y%m%d-%H%M%S)"
    change_on "sudo systemd-run --unit=$unit --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p MemoryHigh=1G -p MemoryMax=2G -p Nice=10 $UNIT_ENV $py"
    [ "$DRY" = 1 ] && exit 0
    follow "$unit"
    ;;

  film)
    use="film \"<idea>\" [--seconds N] [--look L] [--unlisted] [--api] [--no-watch] [--attach file ...] [--person Name=photo ...] [--style S] | film \"<what you want>\" --template t-x [--attach file ...] [--frame F]"
    idea=""; [[ "${1:-}" == --* ]] || { idea="${1:?$use}"; shift; }
    secs=30; auth=""; look=drawn; listed=1; follow=1; people=(); style=auto
    tpl=""; attach=(); frame=""
    while [ $# -gt 0 ]; do
      case "$1" in --seconds) secs="$2"; shift ;; --look) look="$2"; shift ;; --unlisted) listed=0 ;;
        --api) auth=', "auth": "api"' ;; --no-watch) follow=0 ;;
        --person) people+=("$2"); shift ;; --style) style="$2"; shift ;;
        --template) tpl="$2"; shift ;; --attach) attach+=("$2"); shift ;; --frame) frame="$2"; shift ;; esac
      shift
    done
    [ -n "$idea" ] || [ -n "$tpl" ] || die "$use"
    # --attach files (pictures, .md/.txt notes), each uploaded to the VM's studio first, as the
    # site does: a template's pictures, or the photos and logos a plain film is told to use. They
    # reach the film as upload1..N in the order given, so the prompt names them by number
    ids="[]"
    for f in ${attach[@]+"${attach[@]}"}; do
      [ -f "$f" ] || die "no file: $f"
      case "$f" in *.png|*.PNG) ct=image/png ;; *.webp|*.WEBP) ct=image/webp ;;
        *.md|*.MD) ct=text/markdown ;; *.txt|*.TXT) ct=text/plain ;; *) ct=image/jpeg ;; esac
      if [ "$DRY" = 1 ]; then up="up-dryrun"; echo "  would upload $f ($ct)"
      else
        up="$(on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/uploads -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: $ct' --data-binary @-" < "$f" | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or sys.exit(json.dumps(d)))')" || exit 1
      fi
      ids="$(python -c 'import json,sys; l=json.loads(sys.argv[1]); l.append(sys.argv[2]); print(json.dumps(l))' "$ids" "$up")"
    done
    if [ -n "$tpl" ]; then
      # a template's film (studio/templates.py): what you want in your own words
      body="$(python -c '
import json, sys
tid, _, ver = sys.argv[1].partition(":")
body = {"template": {"id": tid, **({"version": int(ver)} if ver else {})}, "prompt": sys.argv[2], "attachments": json.loads(sys.argv[3]), "listed": sys.argv[4] == "1"}
if sys.argv[5]:
    body["frame"] = sys.argv[5]
print(json.dumps(body))  # ASCII on the wire: a letter outside it (a dash, an accent) reached the studio broken from a Windows shell
' "$tpl" "$idea" "$ids" "$listed" "$frame")"
      body="${body%\}}$auth}"
      [ "$DRY" = 1 ] && { echo "  would POST a template film ($tpl) to the VM's studio"; exit 0; }
      id="$(printf '%s' "$body" | on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' --data-binary @-" | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or sys.exit(json.dumps(d)))')" || exit 1
      echo "film $id"
      [ "$follow" = 1 ] || exit 0
      exec bash "$0" watch "$id"
    fi
    # --person "Name=photo.jpg" (or just the photo), up to 4: a real person drawn into the film as a
    # character who talks (studio "people"), in --style (auto: the look's own). Each photo is uploaded
    # to the VM's studio first, as the site does; only with that person's permission.
    ppl="[]"
    for p in "${people[@]}"; do
      case "$p" in *=*) name="${p%%=*}"; f="${p#*=}" ;; *) name=""; f="$p" ;; esac
      [ -f "$f" ] || { echo "no photo: $f" >&2; exit 2; }
      case "$f" in *.png|*.PNG) ct=image/png ;; *.webp|*.WEBP) ct=image/webp ;; *) ct=image/jpeg ;; esac
      if [ "$DRY" = 1 ]; then up="up-dryrun"; echo "  would upload $f ($ct) as $name"
      else
        up="$(on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/uploads -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: $ct' --data-binary @-" < "$f" | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or sys.exit(json.dumps(d)))')"
      fi
      ppl="$(python -c 'import json,sys; l=json.loads(sys.argv[1]); l.append({"upload": sys.argv[2], "name": sys.argv[3]}); print(json.dumps(l))' "$ppl" "$up" "$name")"
    done
    # --look: drawn, painted, collage (the studio refuses one it does not have); --unlisted: link-only
    body="$(python -c 'import json,sys; ppl=json.loads(sys.argv[5]); att=json.loads(sys.argv[7]); print(json.dumps({"prompt": sys.argv[1], "seconds": int(sys.argv[2]), "look": sys.argv[3], "listed": sys.argv[4] == "1", **({"attachments": att} if att else {}), **({"people": ppl, "character_style": sys.argv[6]} if ppl else {})}))' "$idea" "$secs" "$look" "$listed" "$ppl" "$style" "$ids")"
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

  template)
    use="template push <folder .../templates/t-x/vN> | publish|retire|draft <t-x> <N> | list | check"
    sub="${1:?$use}"; shift
    py="$REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/templates.py"
    envs="STUDIO_HOME=$HOME_DIR STUDIO_REPO=$REMOTE"
    case "$sub" in
      push)
        dir="${1:?$use}"; v="$(basename "$dir")"; id="$(basename "$(dirname "$dir")")"
        [[ "$id" =~ ^t-[a-z0-9-]+$ && "$v" =~ ^v[0-9]+$ && -f "$dir/template.json" ]]           || die "not a template version folder: $dir"
        dest="$HOME_DIR/templates/$id/$v"
        on "test ! -e $dest" || die "$id $v is on the VM already: a version never changes (make v$((${v#v} + 1)))"
        if [ "$DRY" = 1 ]; then echo "  would copy $dir to $VM:$dest as a draft"; exit 0; fi
        tar -C "$dir" -cf - . | on "mkdir -p $dest && tar -xf - -C $dest && find $dest -type f -exec chmod a-w {} + && cd $REMOTE && $envs $py draft $id ${v#v} >/dev/null && $envs nice -n 10 $py preview $id ${v#v} && echo pushed $id $v as a draft, its preview drawn on this machine for the release check"
        ;;
      publish|retire|draft)
        [[ "${1:-}" =~ ^t-[a-z0-9-]+$ && "${2:-}" =~ ^[0-9]+$ ]] || die "$use"
        change_on "cd $REMOTE && $envs $py $sub $1 $2"
        ;;
      list) on "cd $REMOTE && $envs $py list" ;;
      check) on "cd $REMOTE && $envs nice -n 10 $py check" ;;
      *) die "$use" ;;
    esac
    ;;

  library-get)
    # the other half of library-put: what a project's library holds now, to improve a member
    # (a place, a character) outside any episode and put it back as the next version
    use="library-get <project> <dir>"
    project="${1:?$use}"; out="${2:?$use}"
    [[ "$project" =~ ^p-[a-z0-9]+$ ]] || die "not a project id: $project"
    mkdir -p "$out/cast"
    on "cd $HOME_DIR/library && d=\$(ls -d */$project 2>/dev/null) && [ \$(echo \"\$d\" | wc -l) = 1 ] || exit 3; cd \$d && python3 -c \"
import json, os, tarfile, sys
i = json.load(open('index.json'))
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as t:
    t.add('index.json')
    if os.path.exists('cast.png'): t.add('cast.png')
    for n, e in i['cast'].items():
        if not e.get('deleted'): t.add('cast/%s/v%d.js' % (n, e['version']), 'cast/%s.js' % n)
\"" | tar -xf - -C "$out" || die "no library for $project on $VM"
    echo "$out: $(ls "$out/cast" | tr '\n' ' ')"
    ;;

  library-put)
    # cast members written by hand (a series' places, from its episodes' film.js) into a project's
    # library, as a finished episode's keep() would: thumbnails, the sheet, the next version
    use="library-put <project> [--dry-run] [--replace] <cast/name.js>..."
    project="${1:?$use}"; shift
    [[ "$project" =~ ^p-[a-z0-9]+$ ]] || die "not a project id: $project"
    flags=""; files=()
    for a in "$@"; do
      case "$a" in
        --dry-run|--replace) flags="$flags $a" ;;
        *) [ -f "$a" ] || die "no file $a"; files+=("$a") ;;
      esac
    done
    [ "${#files[@]}" -gt 0 ] || die "$use"
    [ "$DRY" = 1 ] && flags="$flags --dry-run"
    stage="$HOME_DIR/tmp/library-put-$(date +%Y%m%d-%H%M%S)"
    on "mkdir -p $stage/cast"
    for f in "${files[@]}"; do on "cat > $stage/cast/$(basename "$f")" < "$f"; done
    names=$(for f in "${files[@]}"; do printf ' %s/cast/%s' "$stage" "$(basename "$f")"; done)
    on "sudo systemd-run --wait --pipe --quiet --uid=\$(id -un) --gid=\$(id -gn) --working-directory=$REMOTE -p MemoryHigh=2G -p MemoryMax=3G -p Nice=10 $UNIT_ENV $REMOTE/.venv/bin/python -X utf8 $REMOTE/studio/library_put.py --project $project$flags$names; rc=\$?; rm -rf $stage; exit \$rc"
    ;;

  replace)
    # a remade film (a folder here: a bakeoff film's projects/<id>/, or one `pull --all` brought)
    # takes the place of a film on the VM, under the same id and page: its picture, sound, source
    # files, review images and the log the page replays. The record keeps its person, project,
    # prompt and what it cost; its closing note and direction become the new film's. The old
    # folder goes to backups/; the files go online under new URLs (media.py --revision: the old
    # ones are cached for a year).
    id="${1:?replace <film-id> <folder of the remade film>}"; src="${2:?replace <film-id> <folder>}"
    [ -f "$src/outputs/film.mp4" ] && [ -f "$src/sketch.json" ] || die "$src has no outputs/film.mp4 and sketch.json"
    ev="$src/events.jsonl"; [ -f "$ev" ] || ev="$(dirname "$(dirname "$src")")/events.log"  # a bakeoff film's
    [ -f "$ev" ] || die "no events.jsonl for $src"
    on "test -f $HOME_DIR/projects/$id/studio.json" || die "no film $id on $VM"
    stamp=$(date +%Y%m%d-%H%M%S); stage="$HOME_DIR/tmp/replace-$id-$stamp"
    have=$(cd "$src" && for p in film.js vo.json score.json sfx.json sketch.json audio engine web outputs; do [ -e "$p" ] && printf '%s ' "$p"; done)
    echo "replace $id on $VM with $src: $have+ its events"
    echo "  the old one is kept in $HOME_DIR/backups/$id-$stamp.tar.gz"
    [ "$DRY" = 1 ] && { echo "  would copy, swap, republish under new URLs and update the record"; exit 0; }
    on "mkdir -p $stage $HOME_DIR/backups && tar -czf $HOME_DIR/backups/$id-$stamp.tar.gz -C $HOME_DIR/projects/$id --exclude=./temp ."
    (cd "$src" && tar -cf - --exclude=outputs/artifact --exclude=outputs/film_web.mp4 --exclude=outputs/card.jpg $have) | on "tar -xf - -C $stage"
    on "cat > $stage/events.jsonl" < "$ev"
    if [ -f "$src/studio.json" ]; then on "cat > $stage/source-studio.json" < "$src/studio.json"; fi
    on "ID=$id STAGE=$stage HAVE='$have' FROM='$(basename "$src")' STAMP=$stamp HOME_DIR=$HOME_DIR REMOTE=$REMOTE bash -s" <<'EOF'
set -e
cd "$HOME_DIR/projects/$ID"
rm -rf $HAVE
(cd "$STAGE" && tar -cf - --exclude=source-studio.json .) | tar -xf -
find "$HOME_DIR/library" -path '*/films/*' -name "$ID.jpg" -delete  # the library's cached poster
cd "$REMOTE"
# capped like every job beside the live servers (KI-045): a scope runs in the foreground, here
sudo systemd-run --scope --quiet --uid="$(id -un)" --gid="$(id -gn)" -p MemoryHigh=2G -p MemoryMax=3G \
  env STUDIO_HOME="$HOME_DIR" nice -n 10 .venv/bin/python studio/media.py --film "$ID" --revision </dev/null  # ffmpeg reads stdin: the rest of this script
STUDIO_HOME="$HOME_DIR" .venv/bin/python - <<'PY'
import asyncio, json, os, sys
sys.path.insert(0, "studio")
import agent
from film import Film
f = Film.open(os.environ["ID"])
src = os.path.join(os.environ["STAGE"], "source-studio.json")
new = json.load(open(src, encoding="utf-8")) if os.path.exists(src) else {}
fields = {k: new[k] for k in ("claude_said", "direction") if new.get(k)}
fields["replaced"] = {
    "from": os.environ["FROM"],
    "at": os.environ["STAMP"],
    "backup": "backups/%s-%s.tar.gz" % (f.id, os.environ["STAMP"]),
}
f.update(**fields)
asyncio.run(agent.save(f.id, fields))
print("record: " + ", ".join(sorted(fields)))
PY
rm -rf "$STAGE"
EOF
    ;;

  delete)
    # a film deleted for good (studio/delete_film.py), asked as this machine: its copy online, its
    # record, its folder and what else names it. Nothing is kept, so --dry-run first: it asks the
    # studio what would go (and whether it would be refused) and removes nothing.
    id="${1:?delete <film-id>}"
    body='{}'; [ "$DRY" = 1 ] && body='{"plan": true}'
    on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films/$id/delete -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' -d '$body'; echo"
    ;;

  unbrand)
    # a finished Free-plan film drawn again without its mark and closing (studio/unbrand.py): asked
    # as this machine, then followed to the end. The film plays as it was until the new one is in.
    id="${1:?unbrand <film-id> [--no-watch]}"; shift || true
    watch=1; [ "${1:-}" = "--no-watch" ] && watch=0
    change_on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films/$id/unbrand -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' -d '{}'; echo"
    if [ "$DRY" = 1 ] || [ "$watch" = 0 ]; then exit 0; fi
    on "$TOKEN_SH; last=''; while :; do
      d=\$(curl -s 'http://127.0.0.1:$PORT/api/films/$id?since=1000000' -H \"Authorization: Bearer \$TOKEN\")
      s=\$(printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"unbrand\"), \"branded\" if d.get(\"branded\") else \"clean\")' 2>/dev/null) || s='unreadable'
      [ \"\$s\" != \"\$last\" ] && echo \"\$(date +%T)  \$s\"; last=\$s
      case \"\$s\" in done*|failed*|None*) break ;; esac
      sleep 10
    done
    printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d.get(k) for k in (\"status\",\"branded\",\"unbrand\",\"video_url\",\"download_url\")}, indent=1))'"
    ;;

  notes)
    # a round of changes to a finished film (studio/rounds.py): its maker's notes, asked as this
    # machine, then followed to the end. The film plays as it is until the new version is in; a
    # round that fails leaves it untouched. The notes cross the wire as base64, so a quote or a
    # line break in one is nobody's shell syntax.
    id="${1:?notes <film-id> <notes.json> [--no-watch]}"; file="${2:?notes <film-id> <notes.json>}"
    [ -f "$file" ] || die "no file $file"
    watch=1; [ "${3:-}" = "--no-watch" ] && watch=0
    body=$(python - "$file" <<'PY'
import base64, json, sys, time
notes = json.load(open(sys.argv[1], encoding="utf-8"))
notes = notes.get("notes") if isinstance(notes, dict) else notes
for i, n in enumerate(notes, 1):
    n.setdefault("id", "n%d" % i)
print(base64.b64encode(json.dumps({"key": "ops-%d" % time.time(), "notes": notes}).encode()).decode())
PY
    ) || die "$file is not a list of notes"
    change_on "$TOKEN_SH; echo $body | base64 -d | curl -s -X POST http://127.0.0.1:$PORT/api/films/$id/versions -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' --data-binary @-; echo"
    if [ "$DRY" = 1 ] || [ "$watch" = 0 ]; then exit 0; fi
    on "$TOKEN_SH; last=''; while :; do
      d=\$(curl -s 'http://127.0.0.1:$PORT/api/films/$id/versions' -H \"Authorization: Bearer \$TOKEN\")
      s=\$(printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d.get(\"round\") or {}; l=d.get(\"last\") or {}; print(r.get(\"state\") or l.get(\"state\"), \"-\", r.get(\"now\") or \"\")' 2>/dev/null) || s='unreadable'
      [ \"\$s\" != \"\$last\" ] && echo \"\$(date +%T)  \$s\"; last=\$s
      case \"\$s\" in queued*|running*|finishing*) sleep 5 ;; *) break ;; esac
    done
    printf '%s' \"\$d\" | python3 -c 'import json,sys; d=json.load(sys.stdin); l=d.get(\"last\") or {}; print(json.dumps({\"version\": d.get(\"version\"), \"round\": {k: l.get(k) for k in (\"id\",\"state\",\"error\",\"summary\")}, \"answers\": l.get(\"answers\")}, indent=1, ensure_ascii=False))'"
    ;;

  versions)
    id="${1:?versions <film-id>}"
    on "$TOKEN_SH; curl -s 'http://127.0.0.1:$PORT/api/films/$id/versions' -H \"Authorization: Bearer \$TOKEN\" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({\"version\": d.get(\"version\"), \"versions\": [{k: v.get(k) for k in (\"n\",\"at\",\"rev\",\"kept\",\"summary\",\"round\")} for v in d.get(\"versions\") or []], \"round\": d.get(\"round\"), \"last\": d.get(\"last\"), \"words\": d.get(\"words\"), \"limits\": d.get(\"limits\"), \"error\": d.get(\"error\")}, indent=1, ensure_ascii=False))'"
    ;;

  version)
    id="${1:?version <film-id> <n>}"; n="${2:?version <film-id> <n>}"
    change_on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films/$id/versions/$n/current -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' -d '{}'; echo"
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

  *) sed -n 2,42p "$0"; exit 2 ;;
esac
