#!/usr/bin/env bash
# The studio's Azure VMs, from the laptop: create, reach, size, delete. Every action is az + ssh
# from here -- nobody logs into these machines by hand, so this file is the whole runbook.
#
#   bash studio/deploy/vm.sh create <name> <size> [--data-gb N] [--dry-run]
#   bash studio/deploy/vm.sh ssh    <name> [command...]
#   bash studio/deploy/vm.sh ip     <name>
#   bash studio/deploy/vm.sh open-ssh <name>        # re-point the SSH rule at this machine's IP
#   bash studio/deploy/vm.sh resize <name> <size>   # stop, resize, start (minutes of downtime)
#   bash studio/deploy/vm.sh stop|start|delete <name>
#   bash studio/deploy/vm.sh price <size>           # list price here, per hour and per month
#
# KITCUT_RG=kitcut-bench puts a throwaway machine in its own group, which then goes in one
# `az group delete`. Otherwise region and group sit beside the films' blob account (kitcutst, kitcut-PROD, southcentralus), so
# the upload of a finished film never leaves the region. Disks are Standard HDD (a decision:
# disk speed is not the bottleneck; `az disk update --sku Premium_LRS` changes it later in place).
# Inbound is SSH from this machine's IP only; the studio itself leaves through the Cloudflare
# tunnel, an outbound connection, so no web port is ever opened.
set -euo pipefail

RG="${KITCUT_RG:-kitcut-PROD}"
LOC="${KITCUT_LOCATION:-southcentralus}"
KEY="${KITCUT_SSH_KEY:-$HOME/.ssh/kitcut-studio}"
ADMIN="kitcut"
IMAGE="Ubuntu2404"
DRY=0

die() { echo "vm.sh: $*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
myip() { curl -fsS https://ifconfig.me; }
vmip() { az vm show -d -g "$RG" -n "$1" --query publicIps -o tsv; }
sshto() {
  local name="$1"; shift
  ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 \
    -o UserKnownHostsFile="$HOME/.ssh/known_hosts.kitcut" "$ADMIN@$(vmip "$name")" "$@"
}

cmd="${1:-}"; shift || true
args=()
DATA_GB=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --data-gb) DATA_GB="$2"; shift ;;
    *) args+=("$1") ;;
  esac
  shift
done

case "$cmd" in
  create)
    [ ${#args[@]} -ge 2 ] || die "create <name> <size>"
    name="${args[0]}"; size="${args[1]}"
    [ -f "$KEY" ] || run ssh-keygen -t ed25519 -N "" -C "kitcut-studio" -f "$KEY"
    ip="$(myip)"
    echo "creating $name ($size) in $RG/$LOC, SSH from $ip only"
    az group show -n "$RG" >/dev/null 2>&1 || run az group create -n "$RG" -l "$LOC" --output none
    run az vm create -g "$RG" -n "$name" -l "$LOC" --image "$IMAGE" --size "$size" \
      --admin-username "$ADMIN" --ssh-key-values "$KEY.pub" \
      --storage-sku Standard_LRS --os-disk-size-gb 128 \
      --public-ip-sku Standard --nsg-rule NONE --tags app=kitcut-studio \
      --vnet-name "${name}VNET" --subnet "${name}Subnet" --nsg "${name}NSG" \
      --os-disk-delete-option Delete --data-disk-delete-option Delete --nic-delete-option Delete \
      --output none
    run az network nsg rule create -g "$RG" --nsg-name "${name}NSG" -n ssh-laptop \
      --priority 1000 --access Allow --protocol Tcp --direction Inbound \
      --source-address-prefixes "$ip/32" --destination-port-ranges 22 --output none
    if [ "$DATA_GB" -gt 0 ]; then
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
  open-ssh)
    ip="$(myip)"
    run az network nsg rule update -g "$RG" --nsg-name "${args[0]}NSG" -n ssh-laptop \
      --source-address-prefixes "$ip/32" --output none
    echo "SSH now allowed from $ip"
    ;;
  resize)
    run az vm deallocate -g "$RG" -n "${args[0]}"
    run az vm resize -g "$RG" -n "${args[0]}" --size "${args[1]}" --output none
    run az vm start -g "$RG" -n "${args[0]}"
    ;;
  stop) run az vm deallocate -g "$RG" -n "${args[0]}" ;;
  start) run az vm start -g "$RG" -n "${args[0]}" ;;
  delete)
    name="${args[0]}"
    # the disks and NIC go with the VM (delete options set at create); the IP, NSG and VNET az
    # made beside it do not, and keep billing -- remove exactly those, by the names az gave them
    run az vm delete -g "$RG" -n "$name" --yes --output none
    run az network public-ip delete -g "$RG" -n "${name}PublicIP" || true
    run az network vnet delete -g "$RG" -n "${name}VNET" || true
    run az network nsg delete -g "$RG" -n "${name}NSG" || true
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
  *) sed -n 2,12p "$0"; exit 2 ;;
esac
