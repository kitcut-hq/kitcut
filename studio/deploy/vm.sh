#!/usr/bin/env bash
# The studio's Azure VMs, from the laptop: create, reach, size, delete. Every action is az + ssh
# from here -- nobody logs into these machines by hand, so this file is the whole runbook.
#
#   bash studio/deploy/vm.sh network                 # the VPN subnet + its NSG (idempotent)
#   bash studio/deploy/vm.sh create <name> <size> [--data-gb N | --attach <disk>] [--os-gb 32]
#                                                    [--public] [--dry-run]
#   bash studio/deploy/vm.sh ssh    <name> [command...]
#   bash studio/deploy/vm.sh ip     <name>
#   bash studio/deploy/vm.sh resize <name> <size>   # stop, resize, start (minutes of downtime)
#   bash studio/deploy/vm.sh stop|start|delete <name>
#   bash studio/deploy/vm.sh price <size>           # list price here, per hour and per month
#
# The network: no public IP. The studio VM sits in a subnet of our existing WireGuard network
# (tarta-2/tarta-vnet, 10.0.0.0/16; the laptop's VPN routes all of it), and is reached over the
# VPN only -- its NSG lets in SSH from the VPN's clients and nothing else, not even the rest of
# that network. Outbound (Claude, Gemini, MongoDB, the blob account, the Cloudflare tunnel) is
# Azure's default outbound access, as for the other machines there, so there is no IP to pay for
# and no inbound port on the internet at all. `--public` instead gives a machine a public IP and
# SSH from this laptop's address only: throwaway benchmark boxes (KITCUT_RG=kitcut-bench, which
# then goes in one `az group delete`).
#
# Region and group sit beside the films' blob account (kitcutst, kitcut-PROD, southcentralus), so
# the upload of a finished film never leaves the region. Disks are Standard HDD (a decision:
# measured 100 MB/s, and a film writes ~1.5 MB/s; `az disk update --sku Premium_LRS` changes it
# in place). The system disk is 32 GB: Ubuntu, Edge, ffmpeg and Python take ~5 GB, and the
# Whisper models live on the data disk. Azure can grow a disk but never shrink one.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash would rewrite /subscriptions/... ids into Windows paths

RG="${KITCUT_RG:-kitcut-PROD}"
LOC="${KITCUT_LOCATION:-southcentralus}"
KEY="${KITCUT_SSH_KEY:-$HOME/.ssh/kitcut-studio}"
ADMIN="kitcut"
IMAGE="Ubuntu2404"
# the WireGuard network (wg-vm, tarta-wireguard) and the studio's subnet in it
VPN_RG="tarta-2"
VPN_VNET="tarta-vnet"
SUBNET="kitcut-studio"
SUBNET_PREFIX="10.0.13.0/28"
NSG="kitcut-studio-nsg"
VPN_CLIENTS="10.99.0.0/24"  # the WireGuard peers' own addresses
VPN_GATEWAY="10.0.1.10/32"  # wg-vm, should it masquerade its peers
DRY=0

die() { echo "vm.sh: $*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
myip() { curl -fsS https://ifconfig.me; }
vmip() {
  local ip
  ip="$(az vm show -d -g "$RG" -n "$1" --query publicIps -o tsv)"
  [ -n "$ip" ] || ip="$(az vm show -d -g "$RG" -n "$1" --query privateIps -o tsv)"
  echo "$ip"
}
sshto() {
  local name="$1"; shift
  ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ConnectTimeout=15 \
    -o UserKnownHostsFile="$HOME/.ssh/known_hosts.kitcut" "$ADMIN@$(vmip "$name")" "$@"
}
subnet_id() {
  az network vnet subnet show -g "$VPN_RG" --vnet-name "$VPN_VNET" -n "$SUBNET" --query id -o tsv
}

network() {
  if ! az network nsg show -g "$RG" -n "$NSG" >/dev/null 2>&1; then
    run az network nsg create -g "$RG" -n "$NSG" -l "$LOC" --tags app=kitcut-studio --output none
    run az network nsg rule create -g "$RG" --nsg-name "$NSG" -n ssh-from-vpn --priority 100 \
      --access Allow --protocol Tcp --direction Inbound --destination-port-ranges 22 \
      --source-address-prefixes "$VPN_CLIENTS" "$VPN_GATEWAY" --output none
    # Azure's default rules let the whole network in; the studio needs none of it
    run az network nsg rule create -g "$RG" --nsg-name "$NSG" -n no-other-inbound \
      --priority 4000 --access Deny --protocol '*' --direction Inbound \
      --source-address-prefixes VirtualNetwork --destination-port-ranges '*' --output none
  fi
  if ! subnet_id >/dev/null 2>&1; then
    # through the REST API: `subnet create --default-outbound-access` needs a newer az than 2.49,
    # and a subnet made today is private (no way out) unless it says otherwise
    local vnet nsg
    vnet="$(az network vnet show -g "$VPN_RG" -n "$VPN_VNET" --query id -o tsv)"
    nsg="$(az network nsg show -g "$RG" -n "$NSG" --query id -o tsv)"
    run az rest --method put --output none \
      --url "https://management.azure.com$vnet/subnets/$SUBNET?api-version=2023-09-01" \
      --body "{\"properties\": {\"addressPrefix\": \"$SUBNET_PREFIX\", \"defaultOutboundAccess\": true, \"networkSecurityGroup\": {\"id\": \"$nsg\"}}}"
  fi
  echo "network: $VPN_VNET/$SUBNET ($SUBNET_PREFIX), NSG $NSG: SSH from $VPN_CLIENTS only"
}

cmd="${1:-}"; shift || true
args=()
DATA_GB=0
ATTACH=""
OS_GB=32
PUBLIC=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --data-gb) DATA_GB="$2"; shift ;;
    --attach) ATTACH="$2"; shift ;;
    --os-gb) OS_GB="$2"; shift ;;
    --public) PUBLIC=1 ;;
    *) args+=("$1") ;;
  esac
  shift
done

case "$cmd" in
  network) network ;;
  create)
    [ ${#args[@]} -ge 2 ] || die "create <name> <size>"
    name="${args[0]}"; size="${args[1]}"
    [ -f "$KEY" ] || run ssh-keygen -t ed25519 -N "" -C "kitcut-studio" -f "$KEY"
    az group show -n "$RG" >/dev/null 2>&1 || run az group create -n "$RG" -l "$LOC" --output none
    if [ "$PUBLIC" = 1 ]; then
      ip="$(myip)"
      echo "creating $name ($size) in $RG/$LOC, public IP, SSH from $ip only"
      net=(--public-ip-sku Standard --nsg-rule NONE --vnet-name "${name}VNET"
        --subnet "${name}Subnet" --nsg "${name}NSG")
    else
      network
      echo "creating $name ($size) in $RG/$LOC, on the VPN only (no public IP)"
      net=(--subnet "$(subnet_id)" --public-ip-address "" --nsg "")
    fi
    disks=()
    [ -n "$ATTACH" ] && disks=(--attach-data-disks "$(az disk show -g "$RG" -n "$ATTACH" --query id -o tsv)")
    run az vm create -g "$RG" -n "$name" -l "$LOC" --image "$IMAGE" --size "$size" \
      --admin-username "$ADMIN" --ssh-key-values "$KEY.pub" \
      --storage-sku Standard_LRS --os-disk-size-gb "$OS_GB" "${net[@]}" "${disks[@]}" \
      --tags app=kitcut-studio --os-disk-delete-option Delete --nic-delete-option Delete \
      --output none
    if [ "$PUBLIC" = 1 ]; then
      run az network nsg rule create -g "$RG" --nsg-name "${name}NSG" -n ssh-laptop \
        --priority 1000 --access Allow --protocol Tcp --direction Inbound \
        --source-address-prefixes "$ip/32" --destination-port-ranges 22 --output none
    fi
    if [ "$DATA_GB" -gt 0 ]; then
      # the data disk outlives the VM (detach, not delete): rebuilding the machine keeps the films
      run az vm disk attach -g "$RG" --vm-name "$name" --name "${name}-data" --new \
        --size-gb "$DATA_GB" --sku Standard_LRS --output none
    fi
    run az vm boot-diagnostics enable -g "$RG" -n "$name" --output none
    [ "$DRY" = 1 ] || echo "ready: $(vmip "$name")  --  bash studio/deploy/vm.sh ssh $name"
    ;;
  ssh)
    [ ${#args[@]} -ge 1 ] || die "ssh <name> [command]"
    sshto "${args[@]}"
    ;;
  ip) vmip "${args[0]}" ;;
  resize)
    run az vm deallocate -g "$RG" -n "${args[0]}"
    run az vm resize -g "$RG" -n "${args[0]}" --size "${args[1]}" --output none
    run az vm start -g "$RG" -n "${args[0]}"
    ;;
  stop) run az vm deallocate -g "$RG" -n "${args[0]}" ;;
  start) run az vm start -g "$RG" -n "${args[0]}" ;;
  delete)
    name="${args[0]}"
    # the OS disk and NIC go with the VM (delete options set at create) and the data disk is
    # detached, kept; a --public machine's IP, NSG and VNET do not go by themselves, and bill
    run az vm delete -g "$RG" -n "$name" --yes --output none
    run az network public-ip delete -g "$RG" -n "${name}PublicIP" 2>/dev/null || true
    run az network vnet delete -g "$RG" -n "${name}VNET" 2>/dev/null || true
    run az network nsg delete -g "$RG" -n "${name}NSG" 2>/dev/null || true
    ;;
  price)
    size="${args[0]}"
    curl -fsS "https://prices.azure.com/api/retail/prices?\$filter=serviceName%20eq%20'Virtual%20Machines'%20and%20armRegionName%20eq%20'$LOC'%20and%20armSkuName%20eq%20'Standard_$size'%20and%20priceType%20eq%20'Consumption'" |
      python -c "
import json, sys
for i in json.load(sys.stdin)['Items']:
    if 'Windows' in i['productName'] or 'Cloud Services' in i['productName']:
        continue
    print('%-28s %-12s \$%.3f/h  \$%.0f/mo' % (i['skuName'], i['productName'][-10:], i['retailPrice'], i['retailPrice'] * 730))
"
    ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
