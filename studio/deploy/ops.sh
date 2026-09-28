#!/usr/bin/env bash
# Everyday work on the production studio VM, from the laptop (over the WireGuard VPN). vm.sh is the
# machine itself (create, resize, delete); this is the studio on it. Nobody logs into the VM.
#
#   bash studio/deploy/ops.sh status                  health, release, films in progress, disks,
#                                                     the daily login check, errors in the last day
#   bash studio/deploy/ops.sh logs [studio|tunnel|login] [-n N] [-f]
#   bash studio/deploy/ops.sh ship [<commit>]         tag studio-stable, push, build the release on
#                                                     the VM, drain, restart, prove the new release
#   bash studio/deploy/ops.sh releases                what is built there, and which is current
#   bash studio/deploy/ops.sh rollback <sha12>        back to a release already built (no rebuild)
#   bash studio/deploy/ops.sh film "<idea>" [--seconds N] [--api]   a film made on the VM itself
#                                                     (on the Claude login unless --api), followed
#   bash studio/deploy/ops.sh watch <film-id>         follow a film to the end
#   bash studio/deploy/ops.sh pull <film-id> [dest] [--all]   its outputs (or the whole folder) here
#   bash studio/deploy/ops.sh hide|show <film-id>     out of / back into the public gallery
#   bash studio/deploy/ops.sh replace <film-id> <folder>   a remade film takes its place (same id
#                                                     and page; the old one to backups/)
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
PY
public=$(curl -s --max-time 8 https://studio.kitcut.ai/api/health | python3 -c 'import json,sys; print(json.load(sys.stdin)["release"])' 2>/dev/null || echo "NOT REACHABLE")
echo "studio.kitcut.ai: $public"
echo "units: $(for u in kitcut-studio kitcut-tunnel kitcut-login-check.timer; do printf '%s=%s ' $u $(systemctl is-active $u); done)"
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
        live.append("  %s  %-9s %3ss  %s  %s" % (os.path.basename(os.path.dirname(p)), s["state"], s.get("length", "?"), s.get("auth", "?"), (s.get("prompt") or "")[:60]))
print("films in progress: %d" % len(live))
print("\n".join(sorted(live)))
PY
at=$(systemctl show kitcut-login-check.service -p ExecMainExitTimestamp --value)
res=$(systemctl show kitcut-login-check.service -p Result --value)
next=$(systemctl show kitcut-login-check.timer -p NextElapseUSecRealtime --value)
if [ -n "$at" ]; then echo "login check: $res at $at (next $next)"; else echo "login check: not run yet (first $next)"; fi
echo "disks: $(df -h / | awk 'NR==2{print "system "$3"/"$2}')  $(df -h /srv/kitcut | awk 'NR==2{print "data "$3"/"$2}')   load $(cut -d' ' -f1-3 /proc/loadavg)   mem free $(free -g | awk '/Mem:/{print $7}') GB"
n=$(journalctl -u kitcut-studio -u kitcut-tunnel --since -24h -p err --no-pager -q | wc -l)
echo "errors in the last 24 h: $n"
[ "$n" = 0 ] || journalctl -u kitcut-studio -u kitcut-tunnel --since -24h -p err --no-pager -q | tail -5 | cut -c1-200
EOF
    ;;

  logs)
    unit=kitcut-studio; n=100; follow=""
    while [ $# -gt 0 ]; do
      case "$1" in
        studio) unit=kitcut-studio ;; tunnel) unit=kitcut-tunnel ;; login) unit=kitcut-login-check ;;
        -n) n="$2"; shift ;; -f) follow="-f" ;; *) die "logs [studio|tunnel|login] [-n N] [-f]" ;;
      esac
      shift
    done
    on "journalctl -u $unit -n $n --no-pager $follow"
    ;;

  ship)
    ref="${1:-origin/studio-poc}"
    git -C "$REPO_LOCAL" fetch -q origin
    sha="$(git -C "$REPO_LOCAL" rev-parse --verify "$ref^{commit}")" || die "no commit $ref"
    # only what the team can see ships: a commit that is not on origin/studio-poc is refused
    git -C "$REPO_LOCAL" merge-base --is-ancestor "$sha" origin/studio-poc ||
      die "$ref (${sha:0:12}) is not on origin/studio-poc -- merge and push it first"
    echo "shipping ${sha:0:12}: $(git -C "$REPO_LOCAL" log --format=%s -1 "$sha")"
    change git -C "$REPO_LOCAL" tag -f studio-stable "$sha"
    change git -C "$REPO_LOCAL" push -q -f origin refs/tags/studio-stable
    if [ "$DRY" = 1 ]; then echo "  would run: push.sh $VM studio-poc"; else bash "$HERE/push.sh" "$VM" studio-poc; fi
    # release.py tests the snapshot before making it current; serve.sh drains before restarting
    change_on "cd $REMOTE && bash studio/serve.sh release"
    if [ "$DRY" = 0 ]; then
      got="$(on "curl -s --max-time 5 http://127.0.0.1:$PORT/api/health" | python -c 'import json,sys; print(json.load(sys.stdin)["release"])')"
      [ "$got" = "${sha:0:12}" ] && echo "live: $got" || die "the studio reports $got, expected ${sha:0:12}"
    fi
    ;;

  releases)
    on "cd $REMOTE && STUDIO_HOME=$HOME_DIR .venv/bin/python -X utf8 studio/release.py --list"
    ;;

  rollback)
    rel="${1:?rollback <sha12> (see: ops.sh releases)}"
    on "test -f $HOME_DIR/releases/$rel/studio/server.py" || die "no release $rel built on $VM"
    change_on "echo $rel > $HOME_DIR/releases/current.tmp && mv $HOME_DIR/releases/current.tmp $HOME_DIR/releases/current && cd $REMOTE && bash studio/serve.sh restart"
    ;;

  film)
    idea="${1:?film \"<idea>\" [--seconds N] [--api]}"; shift
    secs=30; auth=""
    while [ $# -gt 0 ]; do
      case "$1" in --seconds) secs="$2"; shift ;; --api) auth=', "auth": "api"' ;; esac
      shift
    done
    body="$(python -c 'import json,sys; print(json.dumps({"prompt": sys.argv[1], "seconds": int(sys.argv[2])}))' "$idea" "$secs")"
    body="${body%\}}$auth}"
    [ "$DRY" = 1 ] && { echo "  would POST $body to the VM's studio"; exit 0; }
    id="$(printf '%s' "$body" | on "$TOKEN_SH; curl -s -X POST http://127.0.0.1:$PORT/api/films -H \"Authorization: Bearer \$TOKEN\" -H 'Content-Type: application/json' --data-binary @-" | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or sys.exit(json.dumps(d)))')"
    echo "film $id"
    exec bash "$0" watch "$id"
    ;;

  watch)
    id="${1:?watch <film-id>}"
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
STUDIO_HOME="$HOME_DIR" .venv/bin/python studio/media.py --film "$ID" --revision </dev/null  # ffmpeg reads stdin: the rest of this script
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

  *) sed -n 2,28p "$0"; exit 2 ;;
esac
