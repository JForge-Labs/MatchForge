#!/bin/bash
# Configure CT108 swap. ZFS rootfs cannot use swapfiles; swap is set on the PVE host.
set -euo pipefail

SWAP_MB=512
CTID=108
KEY="/root/.ssh/id_ed25519"
PUBKEY_FILE="/opt/matchforge/data/ct108_to_pve.pub"
PVE_HOSTS=("REDACTED-TAILSCALE-IP" "REDACTED-PROXMOX-HOST-IP" "REDACTED-TAILSCALE-HOSTNAME")

swap_kb() { awk '/^SwapTotal:/ {print $2}' /proc/meminfo; }

echo "=== MatchForge CT108 swap configuration ==="

if [[ "$(swap_kb)" -gt 0 ]]; then
  echo "✓ Swap already active"
  free -h | grep -E '^Mem:|^Swap:'
  swapon --show 2>/dev/null || true
  exit 0
fi

if [[ -f /swapfile ]]; then
  swapoff /swapfile 2>/dev/null || true
  rm -f /swapfile
  echo "Removed non-functional ZFS swapfile"
fi

if [[ ! -f "$KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "matchforge-dev-ct108"
fi
install -m 644 "${KEY}.pub" "$PUBKEY_FILE"

for host in "${PVE_HOSTS[@]}"; do
  echo "Trying PVE host ${host}..."
  if ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    "root@${host}" "bash /pveNAS/subvol-108-disk-0/opt/matchforge/scripts/pve_ct108_swap.sh" 2>/dev/null; then
    echo "✓ Swap configured via ${host}"
    exit 0
  fi
done

echo "✗ Could not reach Proxmox host via SSH (no authorized key yet)."
echo ""
echo "Run once on the Proxmox host shell:"
echo "  bash /pveNAS/subvol-108-disk-0/opt/matchforge/scripts/pve_ct108_swap.sh"
echo ""
echo "That sets swap:${SWAP_MB} on CT${CTID}, installs the automation SSH key, and reboots the CT."
exit 1