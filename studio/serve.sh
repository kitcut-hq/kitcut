#!/usr/bin/env bash
# The studio on Linux (the Azure VM) -- the counterpart of serve.ps1, over systemd. One server per
# release: a ship starts the new release's server beside the running one and returns once it leads;
# the old one finishes the films it is making and exits by itself. Nothing is drained and nothing
# is restarted, so a ship never stops a film (docs/known-issues.md KI-031).
#
#   bash studio/serve.sh status                  health, the servers (their heartbeats), the units
#   bash studio/serve.sh release [--ref REF]     snapshot REF (default studio-stable), test it, and
#                                                switch to it
#   bash studio/serve.sh switch <sha12>          start a server of a built release, make it current,
#                                                return once it serves and leads
#   bash studio/serve.sh use <sha12>             the same, for a rollback (any release still built)
#   bash studio/serve.sh restart                 a fresh server of the leader's release (after an
#                                                .env change); the old one finishes its films
#   bash studio/serve.sh stop                    maintenance only: drain, stop every server and the
#                                                tunnel, mark the studio offline
#   bash studio/serve.sh start                   the tunnel and the current server, and at every boot
#   bash studio/serve.sh migrate [--ref REF]     ONCE per machine: from the legacy kitcut-studio
#                                                service to one server per release, cutting no film
#   bash studio/serve.sh --dry-run <cmd>         say what would happen, touch nothing
#
# The servers are systemd units kitcut-studio@<instance>, instance <sha12>-<YYYYmmddHHMMSS>
# (deploy/kitcut-studio@.service), all on 127.0.0.1:8765 with SO_REUSEPORT. STUDIO_HOME/servers/ is
# the contract between them (studio/peers.py): `current` names the instance that should serve
# (written here: the intent), leader.lock is held by the one that admits films (the fact), and
# each live server keeps <id>.json, its heartbeat, beside the <id>.lock it holds for its whole
# life. kitcut-studio-boot starts the current instance at boot. Every command but status takes
# deploy.lock (one at a time; a second one stops at once).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${STUDIO_PORT:-8765}"
DRAIN_MINUTES="${DRAIN_MINUTES:-20}"
SWITCH_SECONDS="${SWITCH_SECONDS:-120}"
DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
cmd="${1:-status}"; shift || true
REF="studio-stable"
ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a value}"; shift ;;
    --dry-run) DRY=1 ;;
    *) ARG="$1" ;;
  esac
  shift
done

die() { echo "serve.sh: $*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
put() {  # <path> <body>: a root-owned file
  if [ "$DRY" = 1 ]; then echo "  would write $1: $2" | tr '\n' ' '; echo; else printf '%s\n' "$2" | sudo tee "$1" >/dev/null; fi
}

# The studio's home, where releases are built and servers meet: the units' (install.sh) unless set.
# Without it release.py falls back to <checkout>/../kitcut-studio and builds where no server looks
# -- a ship on 2026-09-28 restarted the studio onto its old code that way, and killed a film for it.
# Never guessed: the template's (any instance name renders it), else the legacy unit's, else say so.
unit_env() { systemctl show "$1" -p Environment --value 2>/dev/null | tr ' ' '\n' | sed -n "s/^$2=//p" || true; }
if [ -z "${STUDIO_HOME:-}" ]; then
  STUDIO_HOME="$(unit_env kitcut-studio@probe.service STUDIO_HOME)"
  [ -n "$STUDIO_HOME" ] || STUDIO_HOME="$(unit_env kitcut-studio.service STUDIO_HOME)"
fi
[ -n "${STUDIO_HOME:-}" ] || die "no STUDIO_HOME: install the units (deploy/install.sh), or name it (STUDIO_HOME=/srv/kitcut/studio)"
export STUDIO_HOME
SERVERS="$STUDIO_HOME/servers"

setting() { grep -E "^\s*$1\s*=" "$REPO/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' \r" || true; }
health() { curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health"; }
field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1" 2>/dev/null; }
word() { local w=""; if [ -f "$1" ]; then read -r w < "$1" || true; fi; printf '%s' "${w//[[:space:]]/}"; }
current_release() { word "$STUDIO_HOME/releases/current"; }   # the last one built and tested (release.py)
current_instance() { word "$SERVERS/current"; }                # the instance that should serve
unit_state() { systemctl is-active "kitcut-studio@$1.service" 2>/dev/null || true; }
legacy() { [ "$(systemctl show kitcut-studio.service -p LoadState --value 2>/dev/null || true)" = loaded ]; }

# The live servers, from their heartbeats (peers.py): <id>.json whose <id>.lock is held. A dead
# server's file lingers until the leader reaps it; its lock is free the moment it dies.
#   beats list | others <instance> | running | leader-release
#   beats leads <instance> <sha12> | serving <instance> | any-leader     (exit status)
beats() {
  python3 - "$SERVERS" "$@" <<'PY'
import json, os, sys
try:
    import fcntl
except ImportError:  # not Linux (a dry run on a laptop): a lock file counts as held
    fcntl = None
d, what, args = sys.argv[1], sys.argv[2], sys.argv[3:]


def alive(sid):
    path = os.path.join(d, "%s.lock" % sid)
    if fcntl is None:
        return os.path.exists(path)
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False  # nobody holds it: its server is gone (closing the fd lets go again)
    except OSError:
        return True
    finally:
        os.close(fd)


live = []
for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
    if not name.endswith(".json"):
        continue
    try:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        continue
    if isinstance(b, dict) and alive(b.get("id") or name[:-5]):
        live.append(b)
live.sort(key=lambda b: (b.get("started") or "", b.get("pid") or 0))


def films(b, status=None):
    return [j for j in b.get("jobs") or [] if status is None or j.get("status") == status]


def serving(b, inst=None):
    return b.get("mode") == "serving" and (inst is None or b.get("instance") == inst)


if what == "leads":
    inst, rel = args
    ok = any(serving(b, inst) and b.get("leader") and b.get("release") == rel for b in live)
    sys.exit(0 if ok else 1)
elif what == "serving":
    sys.exit(0 if any(serving(b, args[0]) for b in live) else 1)
elif what == "any-leader":
    sys.exit(0 if any(serving(b) and b.get("leader") for b in live) else 1)
elif what == "leader-release":
    print(next((b.get("release") or "" for b in live if b.get("leader")), ""))
elif what == "running":
    print(sum(len(films(b, "running")) for b in live))
elif what in ("list", "others"):
    rows = [b for b in live if what == "list" or b.get("instance") != args[0]]
    for b in rows:
        js = films(b)
        print(
            "  %-34s %-12s %-10s %-6s %d film(s)%s"
            % (
                b.get("id"),
                b.get("release"),
                b.get("mode"),
                "leader" if b.get("leader") else "",
                len(js),
                ": " + ", ".join("%s %s" % (j.get("id"), j.get("status")) for j in js) if js else "",
            )
        )
    if not rows:
        print("  (none)")
else:
    sys.exit("beats: what is %r?" % what)
PY
}

leader_release() {  # the release the leader runs: its heartbeat, else what the port answers
  local r
  r="$(beats leader-release 2>/dev/null || true)"
  [ -n "$r" ] || r="$(health 2>/dev/null | field release || true)"
  printf '%s' "$r"
}

films_running() {  # on every server: the heartbeats' count, or the one server's (the legacy has none)
  local a b
  a="$(beats running 2>/dev/null || true)"
  b="$(health 2>/dev/null | field running || true)"
  [[ "$a" =~ ^[0-9]+$ ]] || a=0
  [[ "$b" =~ ^[0-9]+$ ]] || b=0
  echo $(( a > b ? a : b ))
}

units() {
  systemctl list-units --all --no-legend --plain 'kitcut-studio@*' kitcut-studio.service \
    kitcut-studio-boot.service kitcut-tunnel.service 2>/dev/null |
    awk '{ printf "  %-44s %s %s\n", $1, $3, $4 }' || true
  echo "  kitcut-studio-boot at boot: $(systemctl is-enabled kitcut-studio-boot.service 2>/dev/null || echo not installed)"
}

# One deploy at a time. Three ships overlapped on 2026-09-28, each draining and restarting on its
# own; a second one now stops at once and says who holds the lock (the kernel frees it when the
# holder exits, however it exits).
LOCK="$STUDIO_HOME/deploy.lock"
lock() {
  [ "$DRY" = 1 ] && return 0
  exec 9>>"$LOCK"
  flock -n 9 || die "another deploy is running -- $(cat "$LOCK")"
  local from="${SSH_CLIENT:-local}"
  echo "pid $$, '$cmd', since $(date '+%F %T'), from ${from%% *}" > "$LOCK"
}

need_template() {  # a dry run goes on without it (install.sh may be what comes first)
  [ "$(systemctl show kitcut-studio@probe.service -p LoadState --value 2>/dev/null || true)" != loaded ] || return 0
  [ "$DRY" = 1 ] || die "kitcut-studio@.service is not installed: bash studio/deploy/install.sh"
  echo "  (kitcut-studio@.service is not installed yet: install.sh comes first)"
}
check_sysctl() {
  [ "$(sysctl -n net.ipv4.tcp_migrate_req 2>/dev/null || true)" = 1 ] ||
    echo "serve.sh: warning: net.ipv4.tcp_migrate_req is not 1 (install.sh sets it): connections queued on an old server are reset when it stops listening" >&2
}
not_legacy() {
  if legacy; then
    die "this machine still runs the legacy kitcut-studio.service: serve.sh migrate first (once; ops.sh migrate)"
  fi
}

set_current() {  # <instance>, or "" for none (then every server is current: peers.py)
  local to="${1:-}"
  if [ "$DRY" = 1 ]; then echo "  would write $SERVERS/current: ${to:-(removed)}"; return 0; fi
  mkdir -p "$SERVERS"
  if [ -z "$to" ]; then rm -f "$SERVERS/current"; return 0; fi
  printf '%s\n' "$to" > "$SERVERS/current.$$.tmp"
  mv -f "$SERVERS/current.$$.tmp" "$SERVERS/current"  # atomic: no server ever reads half a name
}
set_release() {  # releases/current, which release.py --list marks: the release the leader runs
  if [ "$DRY" = 1 ]; then echo "  would write $STUDIO_HOME/releases/current: $1"; return 0; fi
  printf '%s' "$1" > "$STUDIO_HOME/releases/current.tmp"
  mv -f "$STUDIO_HOME/releases/current.tmp" "$STUDIO_HOME/releases/current"
}

wait_leads() {  # <instance> <sha12> <seconds>: until a server of it serves, leads and runs <sha12>
  local until=$(( $(date +%s) + $3 )) st
  while :; do
    beats leads "$1" "$2" && return 0
    st="$(unit_state "$1")"
    case "$st" in inactive|failed) echo "  kitcut-studio@$1 is $st" >&2; return 1 ;; esac
    [ "$(date +%s)" -lt "$until" ] || return 1
    sleep 1
  done
}

journal_tail() { journalctl -u "kitcut-studio@$1.service" -n "${2:-40}" --no-pager -o short-iso >&2 || true; }

# Start a server of release <sha12> beside the ones running and make it the one that serves. The
# leader sees it serving and hands over: stops listening, takes no new films, finishes its own and
# exits 0. Never drained, never stopped: that is what cut a film (KI-031).
switch() {
  local rel="$1" inst prev lr
  [[ "$rel" =~ ^[0-9a-f]{12}$ ]] || die "not a release: '$rel' (12 hex characters: release.py --list)"
  [ -f "$STUDIO_HOME/releases/$rel/studio/server.py" ] ||
    die "no release '$rel' built in $STUDIO_HOME/releases (release.py --list)"
  not_legacy
  need_template
  check_sysctl
  inst="$rel-$(date +%Y%m%d%H%M%S)"
  prev="$(current_instance)"
  lr="$(leader_release)"
  echo "switching to kitcut-studio@$inst (current: ${prev:-none}; the leader runs ${lr:-nothing})"
  set_current "$inst"
  if [ "$DRY" = 1 ]; then
    echo "  would run: sudo systemctl start kitcut-studio@$inst"
    echo "  would wait up to ${SWITCH_SECONDS}s for it to serve and lead; on failure put back ${prev:-no current} and stop it"
    set_release "$rel"
    return 0
  fi
  if sudo systemctl start "kitcut-studio@$inst.service" && wait_leads "$inst" "$rel" "$SWITCH_SECONDS"; then
    set_release "$rel"
    echo "kitcut-studio@$inst serves and leads: release $rel"
    echo "older servers (each finishes its films, then exits by itself -- nobody stops them):"
    beats others "$inst"
    return 0
  fi
  echo "serve.sh: kitcut-studio@$inst did not serve and lead within ${SWITCH_SECONDS}s: back to ${prev:-no current}" >&2
  set_current "$prev"
  sudo systemctl stop "kitcut-studio@$inst.service" || true
  journal_tail "$inst"
  # The old leader lets go only on seeing the new one serving, so it normally never did and leads
  # on. If it had handed off, it serves no more: the release that served before comes back -- the
  # same instance if it had exited, else a fresh one beside it (it is finishing films).
  local t=0 back
  until beats any-leader || [ "$t" -ge 20 ]; do sleep 1; t=$((t + 1)); done
  if ! beats any-leader && [ -n "$prev" ]; then
    case "$(unit_state "$prev")" in
      inactive|failed) back="$prev" ;;
      *) back="${prev:0:12}-$(date +%Y%m%d%H%M%S)" ;;
    esac
    echo "serve.sh: nobody leads: starting kitcut-studio@$back, the release that served before" >&2
    set_current "$back"
    sudo systemctl start "kitcut-studio@$back.service" || true
    wait_leads "$back" "${back:0:12}" "$SWITCH_SECONDS" || true
  fi
  beats any-leader || echo "serve.sh: NOBODY LEADS NOW -- serve.sh use <sha12> (release.py --list) starts a fresh server" >&2
  beats list >&2
  exit 1
}

# Maintenance only (stop): the serving server takes no new films, and every server's films get up
# to DRAIN_MINUTES to finish. A ship never drains.
admin_drain() {
  if [ "$DRY" = 1 ]; then echo "  would POST /api/admin/drain"; return 0; fi
  curl -fsS -o /dev/null --max-time 5 -X POST -H "Authorization: Bearer $(setting STUDIO_TOKEN)" \
    "http://127.0.0.1:$PORT/api/admin/drain"
}
drain() {
  local n until
  n="$(films_running)"
  [ "$n" != 0 ] || return 0
  admin_drain || { echo "could not ask the server to drain" >&2; return 0; }
  [ "$DRY" = 0 ] || { echo "  would wait up to $DRAIN_MINUTES min for $n film(s)"; return 0; }
  until=$(( $(date +%s) + DRAIN_MINUTES * 60 ))
  while [ "$(date +%s)" -lt "$until" ]; do
    n="$(films_running)"; [ "$n" != 0 ] || return 0
    echo "  draining: $n film(s) still being made..."
    sleep 10
  done
  echo "films still running after $DRAIN_MINUTES min; stopping anyway (they will be marked interrupted)" >&2
}

summary() {
  echo
  echo "== where it stands"
  echo "health: $(health 2>/dev/null || echo 'NOT ANSWERING on 127.0.0.1:'"$PORT")"
  echo "servers (current: $(current_instance); releases/current: $(current_release)):"
  beats list || true
  echo "units:"
  units
  echo "legacy kitcut-studio.service: $(systemctl show kitcut-studio.service -p LoadState --value 2>/dev/null || echo '?')"
  echo "net.ipv4.tcp_migrate_req: $(sysctl -n net.ipv4.tcp_migrate_req 2>/dev/null || echo '?')"
}

# migrate: wait, with no timeout, until the legacy server makes nothing. A paying film is never cut
# (a 150 s one can take two hours on the VM). $1 "idle": nothing running or queued; "running":
# nothing running (after the drain, the queued ones stay queued for the new server). Stops at once
# if the new server already has the port (then the legacy one is not serving).
legacy_quiet() {
  local last=0 h r q
  while :; do
    if beats serving "$inst"; then echo "  kitcut-studio@$inst already has the port"; return 0; fi
    h="$(health 2>/dev/null || true)"
    r="$(printf '%s' "$h" | field running || true)"
    q="$(printf '%s' "$h" | field queued || true)"
    if [ "$r" = 0 ] && { [ "$1" = running ] || [ "$q" = 0 ]; }; then return 0; fi
    if [ $(( $(date +%s) - last )) -ge 60 ]; then
      last=$(date +%s)
      echo "  $(date +%T)  legacy server: ${r:-?} running, ${q:-?} queued -- waiting (no timeout)"
    fi
    sleep 10
  done
}

DROPIN=/etc/systemd/system/kitcut-studio.service.d

case "$cmd" in
  status)
    if h="$(health 2>/dev/null)"; then echo "health: $h"; else echo "health: not answering on 127.0.0.1:$PORT"; fi
    echo "servers (current: $(current_instance)):"
    beats list || true
    echo "units:"
    units
    ;;

  release)
    lock
    not_legacy  # before building: a legacy server restarting would read the releases/current it moves
    want="$(git -C "$REPO" rev-parse --verify -q "$REF^{commit}")" || die "no commit $REF"
    want="${want:0:12}"
    if [ "$(leader_release)" = "$want" ]; then echo "release $want already leads: nothing to do"; exit 0; fi
    echo "building $REF ($want) into $STUDIO_HOME/releases"
    run "$REPO/.venv/bin/python" -X utf8 "$REPO/studio/release.py" --ref "$REF"
    if [ "$DRY" = 1 ] && [ ! -f "$STUDIO_HOME/releases/$want/studio/server.py" ]; then
      echo "  would then switch to $want (start kitcut-studio@$want-<now>, return once it leads)"
      exit 0
    fi
    # the new server runs what was just built and tested, or nothing changes
    [ "$DRY" = 1 ] || [ "$(current_release)" = "$want" ] ||
      die "$STUDIO_HOME/releases/current is '$(current_release)', not $want -- not switching"
    switch "$want"
    ;;

  switch|use)
    [ -n "$ARG" ] || die "$cmd <sha12> (release.py --list)"
    lock
    switch "$ARG"
    ;;

  restart)
    lock
    rel="$(leader_release)"
    [ -n "$rel" ] || { rel="$(current_instance)"; rel="${rel:0:12}"; }
    [ -n "$rel" ] || rel="$(current_release)"
    [ -n "$rel" ] || die "no server and no release to restart: serve.sh release"
    switch "$rel"
    ;;

  start)
    lock
    not_legacy
    need_template
    run sudo systemctl enable kitcut-tunnel.service kitcut-studio-boot.service
    run sudo systemctl start kitcut-tunnel.service
    inst="$(current_instance)"
    if [ -z "$inst" ]; then
      rel="$(current_release)"
      [ -n "$rel" ] || die "no servers/current and no release built: serve.sh release"
      switch "$rel"
      exit 0
    fi
    # the boot unit is a oneshot that stays "active": restart runs it again (start would not)
    run sudo systemctl restart kitcut-studio-boot.service
    [ "$DRY" = 1 ] && exit 0
    wait_leads "$inst" "${inst:0:12}" "$SWITCH_SECONDS" || { journal_tail "$inst"; die "kitcut-studio@$inst did not serve and lead"; }
    echo "kitcut-studio@$inst serves and leads"
    ;;

  stop)
    lock
    drain
    stop=("kitcut-studio@*.service" kitcut-studio-boot.service kitcut-tunnel.service)
    if legacy; then stop+=(kitcut-studio.service); fi
    # the last server unit to go says "offline" (announce.sh off)
    run sudo systemctl stop "${stop[@]}"
    ;;

  migrate)
    # The ONE-TIME move from the legacy kitcut-studio.service (one server, not SO_REUSEPORT,
    # restarted on every ship) to kitcut-studio@<instance>. The new server waits for the port and
    # can neither lead nor adopt a film until it has it, so the legacy server keeps every film
    # until it has none. Re-run it after any failure: each step checks what is already done.
    lock
    need_template
    check_sysctl
    want="$(git -C "$REPO" rev-parse --verify -q "$REF^{commit}")" || die "no commit $REF"
    want="${want:0:12}"
    if ! legacy; then
      echo "no legacy kitcut-studio.service on this machine: nothing to migrate (serve.sh release ships)"
      summary
      exit 0
    fi
    prev="$(current_instance)"
    legacy_rel="$(current_release)"  # what the legacy runs: its run-server.sh reads it at every start

    echo "== 1. build and test release $want ($REF)"
    run "$REPO/.venv/bin/python" -X utf8 "$REPO/studio/release.py" --ref "$REF"
    if [ "$DRY" = 0 ]; then
      [ "$(current_release)" = "$want" ] || die "$STUDIO_HOME/releases/current is '$(current_release)', not $want"
      # until it is stopped, a legacy server restarted by a crash comes back on its own code
      if [ -n "$legacy_rel" ] && [ "$legacy_rel" != "$want" ]; then set_release "$legacy_rel"; fi
    fi

    echo "== 2. a server of $want beside the legacy one"
    if [ "${prev:0:12}" = "$want" ] && [ "$(unit_state "$prev")" = active ]; then
      inst="$prev"
      echo "  kitcut-studio@$inst is already running (an earlier migrate): keeping it"
    else
      inst="$want-$(date +%Y%m%d%H%M%S)"
      set_current "$inst"
      run sudo systemctl start "kitcut-studio@$inst.service"
      # an earlier migrate's server of another release, still waiting for the port, has never had
      # a film: it goes (one that has the port is a server like any other, and is left alone)
      if [ -n "$prev" ] && [ "$(unit_state "$prev")" = active ] && ! beats serving "$prev"; then
        run sudo systemctl stop "kitcut-studio@$prev.service"
      fi
    fi

    echo "== 3. the legacy server finishes its films (no timeout)"
    if [ "$DRY" = 1 ]; then
      h="$(health 2>/dev/null || true)"
      echo "  would wait until it has none running or queued (now: $(printf '%s' "$h" | field running || true) running, $(printf '%s' "$h" | field queued || true) queued)"
    else
      legacy_quiet idle
    fi

    echo "== 4. drain it, so a film asked for from now on stays queued for the new server"
    if [ "$DRY" = 1 ] || ! beats serving "$inst"; then
      admin_drain || echo "  could not ask the legacy server to drain (not answering?)" >&2
      [ "$DRY" = 1 ] || legacy_quiet running
    fi

    echo "== 5. stop the legacy server, without announcing the studio offline"
    run sudo mkdir -p "$DROPIN"
    put "$DROPIN/migrate.conf" "[Service]
ExecStopPost="
    run sudo systemctl daemon-reload
    run sudo systemctl disable --now kitcut-studio.service

    echo "== 6. kitcut-studio@$inst takes the port and leads"
    [ "$DRY" = 0 ] || echo "  would wait up to 60 s; else stop it and put the legacy server back (and exit 1)"
    if [ "$DRY" = 0 ] && ! wait_leads "$inst" "$want" 60; then
      echo "serve.sh: kitcut-studio@$inst did not lead within 60 s: putting the legacy server back" >&2
      journal_tail "$inst"
      sudo systemctl stop "kitcut-studio@$inst.service" || true
      set_current "$prev"
      sudo rm -rf "$DROPIN"
      sudo systemctl daemon-reload
      sudo systemctl enable --now kitcut-studio.service
      exit 1
    fi

    echo "== 7. from now on the current instance starts at boot"
    set_release "$want"
    run sudo systemctl enable --now kitcut-studio-boot.service

    echo "== 8. the legacy unit goes"
    frag="$(systemctl show kitcut-studio.service -p FragmentPath --value 2>/dev/null || true)"
    [ -z "$frag" ] || run sudo rm -f "$frag"
    run sudo rm -rf "$DROPIN"
    run sudo systemctl daemon-reload
    run sudo systemctl reset-failed kitcut-studio.service 2>/dev/null || true

    echo "== 9. tell kitcut.ai where the studio is (it never said offline)"
    run env STUDIO_REPO="$REPO" STUDIO_PORT="$PORT" bash "$REPO/studio/deploy/announce.sh" up
    [ "$DRY" = 1 ] || summary
    ;;

  *) sed -n 2,20p "$0"; exit 2 ;;
esac
