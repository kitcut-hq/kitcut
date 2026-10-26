#!/usr/bin/env bash
# The machine's watch (studio/deploy/monitor.py) set up ON the machine, as the checkout's owner
# (passwordless sudo). From the laptop: `ops.sh monitor install|tunnel|status|link|tidy`.
#
#   install  smartmontools (the disk's own health log), the page's key and an Elasticsearch user
#            in STUDIO_HOME/monitor/secret.env (made once, kept after), the user itself in the
#            file realm (made as root: no admin password needed) with a role that may write and
#            read the machine-* indices and nothing else, their templates and lifecycle
#            (monitor.py es-setup), and kitcut-monitor.service enabled and (re)started
#   tunnel   machine.kitcut.ai -> the page (127.0.0.1:8770), a SEPARATE tunnel with its own unit
#            (kitcut-monitor-tunnel) and files (/srv/kitcut/monitor-tunnel), so the studio's
#            tunnel is never touched. The page asks for its key; nothing else is behind it.
#   status   what runs, what the watch sees now, and what stands wrong
#   link     the page's address with its key (opening it once sets a cookie for a year)
#   tidy     clears the failed state of the transient units hand jobs left behind (run-u*.service
#            and the like), so that "failed units" means something again. Lists them first; only
#            units outside monitor.json's `failed_tell` globs are cleared.
#   down     stops the page's tunnel (the watch keeps running)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOME_DIR="${STUDIO_HOME:-$(dirname "$REPO")/studio}"
DIR="$HOME_DIR/monitor"
SECRET="$DIR/secret.env"
HOST="${KITCUT_MONITOR_HOST:-machine.kitcut.ai}"
TDIR=/srv/kitcut/monitor-tunnel
TUNIT=kitcut-monitor-tunnel
ROLE=kc_monitor
ESUSER=kc-monitor
ESBIN=/usr/share/elasticsearch/bin
mode="${1:-status}"
[ "$(id -un)" != root ] || { echo "run as the checkout's owner, not root" >&2; exit 1; }
py() { STUDIO_HOME="$HOME_DIR" /usr/bin/python3 "$REPO/studio/deploy/monitor.py" "$@"; }
setting() { sed -n "s/^$1=//p" "$SECRET" 2>/dev/null | tail -1; }
newpass() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-40; }

case "$mode" in
  install)
    command -v smartctl >/dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q smartmontools >/dev/null
    mkdir -p "$DIR"; chmod 700 "$DIR"
    touch "$SECRET"; chmod 600 "$SECRET"
    [ -n "$(setting MONITOR_KEY)" ] || printf '# the page (studio/deploy/monitor.py): ?key= sets its cookie\nMONITOR_KEY=%s\n' "$(newpass)" >> "$SECRET"
    if [ -d /etc/elasticsearch ]; then
      if ! sudo grep -q "^$ROLE:" /etc/elasticsearch/roles.yml; then
        sudo tee -a /etc/elasticsearch/roles.yml >/dev/null <<EOF

# The machine's own watch (kitcut repo, studio/deploy/monitor.py): its machine-* indices, their
# templates and lifecycle, and the cluster's health. Nothing else.
$ROLE:
  cluster: [ 'monitor', 'manage_ilm', 'manage_index_templates' ]
  indices:
    - names: [ 'machine-metrics-*', 'machine-logs-*', 'machine-events-*' ]
      privileges: [ 'create_doc', 'create_index', 'auto_configure', 'read', 'view_index_metadata' ]
EOF
      fi
      pass="$(setting ES_PASSWORD)"
      if [ -z "$pass" ]; then
        pass="$(newpass)"
        printf '# Elasticsearch, file realm user (studio/deploy/monitor-setup.sh install)\nES_USER=%s\nES_PASSWORD=%s\n' "$ESUSER" "$pass" >> "$SECRET"
      fi
      if sudo "$ESBIN/elasticsearch-users" list 2>/dev/null | grep -q "^$ESUSER "; then
        sudo "$ESBIN/elasticsearch-users" passwd "$ESUSER" -p "$pass" >/dev/null
      else
        sudo "$ESBIN/elasticsearch-users" useradd "$ESUSER" -p "$pass" -r "$ROLE" >/dev/null
      fi
      # the file realm is read again every few seconds
      for _ in $(seq 1 20); do
        code=$(curl -s -o /dev/null -w '%{http_code}' -u "$ESUSER:$pass" http://127.0.0.1:9200/_cluster/health)
        [ "$code" = 200 ] && break
        sleep 2
      done
      echo "elasticsearch as $ESUSER: HTTP $code"
      py es-setup
    else
      echo "no Elasticsearch on this machine: the watch runs without it"
    fi
    bash "$REPO/studio/deploy/install.sh" --home "$HOME_DIR" >/dev/null
    sudo systemctl enable -q kitcut-monitor.service
    sudo systemctl restart kitcut-monitor.service
    sleep 3
    echo "kitcut-monitor: $(systemctl is-active kitcut-monitor.service)"
    ;;
  tunnel)
    CF="$(command -v cloudflared)" || { echo "cloudflared is not installed" >&2; exit 1; }
    [ -n "$(setting MONITOR_KEY)" ] || { echo "no page key yet: run install first" >&2; exit 1; }
    mkdir -p "$TDIR"; chmod 700 "$TDIR"
    [ -f "$TDIR/creds.json" ] || "$CF" tunnel create --credentials-file "$TDIR/creds.json" kitcut-monitor
    chmod 600 "$TDIR/creds.json"
    id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["TunnelID"])' "$TDIR/creds.json")"
    cat > "$TDIR/config.yml" <<EOF
# written by studio/deploy/monitor-setup.sh tunnel: the watch's page and nothing else
tunnel: $id
credentials-file: $TDIR/creds.json
ingress:
  - hostname: $HOST
    service: http://127.0.0.1:8770
  - service: http_status:404
EOF
    "$CF" tunnel route dns "$id" "$HOST" 2>&1 | tail -1
    sudo tee "/etc/systemd/system/$TUNIT.service" >/dev/null <<EOF
# $HOST -> the machine's watch page (studio/deploy/monitor.py, behind its key). Written by
# studio/deploy/monitor-setup.sh; a separate tunnel from the studio's (kitcut-tunnel).
[Unit]
Description=KitCut machine watch page tunnel (cloudflared, $HOST)
After=network-online.target kitcut-monitor.service
Wants=network-online.target

[Service]
User=$(id -un)
Group=$(id -gn)
ExecStart=$CF tunnel --no-autoupdate --config $TDIR/config.yml run
Restart=always
RestartSec=5
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --quiet "$TUNIT"
    sudo systemctl restart "$TUNIT"
    for _ in $(seq 1 20); do
      sudo journalctl -u "$TUNIT" --since -30s --no-pager -q | grep -q 'Registered tunnel connection' && break
      sleep 1
    done
    echo "tunnel: $(systemctl is-active "$TUNIT"), $HOST"
    ;;
  down)
    sudo systemctl disable --now --quiet "$TUNIT"
    ;;
  link)
    py link
    ;;
  tidy)
    failed="$(systemctl list-units --failed --plain --no-legend --no-pager | awk '{print $1}')"
    keep="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["units"]["failed_tell"]))' "$REPO/studio/deploy/monitor.json")"
    for u in $failed; do
      told=0
      for g in $keep; do
        # shellcheck disable=SC2053 -- a glob on purpose
        [[ "$u" == $g ]] && told=1
      done
      if [ "$told" = 1 ]; then echo "kept (it matters): $u"; else echo "cleared: $u"; sudo systemctl reset-failed "$u"; fi
    done
    ;;
  status)
    echo "kitcut-monitor: $(systemctl is-active kitcut-monitor.service 2>/dev/null || true), $(systemctl is-enabled kitcut-monitor.service 2>/dev/null || true)"
    echo "page tunnel: $(systemctl is-active "$TUNIT" 2>/dev/null || true) ($HOST)"
    echo "page: HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8770/healthz)"
    py once
    if [ -f "$DIR/health.json" ]; then
      python3 -c 'import json,sys; h=json.load(open(sys.argv[1])); print("told now (%s):" % h["at"]); [print("  %-4s %s" % (a["level"], a["subject"])) for a in h["alerts"]] or print("  nothing")' "$DIR/health.json"
    fi
    ;;
  *) echo "monitor-setup.sh install|tunnel|down|status|link|tidy" >&2; exit 2 ;;
esac
