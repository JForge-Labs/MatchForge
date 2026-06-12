#!/bin/bash
# Run as root on the Proxmox host (pve / 192.168.1.2).
# Configures 512MB LXC swap for CT108 — the correct method on ZFS rootfs
# (in-container swapfiles fail with "skipping - it appears to have holes").
set -euo pipefail

CTID=108
SWAP_MB=512
PUBKEY_FILE="/pveNAS/subvol-108-disk-0/opt/matchforge/data/ct108_to_pve.pub"

if [[ $(id -u) -ne 0 ]]; then
  echo "Run as root on the Proxmox host." >&2
  exit 1
fi

if ! command -v pct >/dev/null 2>&1; then
  echo "pct not found — this script must run on the Proxmox host." >&2
  exit 1
fi

current=$(pct config "$CTID" 2>/dev/null | awk '/^swap:/{print $2}' || true)
if [[ "${current:-0}" == "$SWAP_MB" ]]; then
  echo "CT${CTID} swap already ${SWAP_MB}MB"
else
  pct set "$CTID" -swap "$SWAP_MB"
  echo "Set CT${CTID} swap to ${SWAP_MB}MB"
fi

if [[ -f "$PUBKEY_FILE" ]]; then
  key=$(tr -d '\n' < "$PUBKEY_FILE")
  if ! grep -qF "$key" /root/.ssh/authorized_keys 2>/dev/null; then
    echo "$key" >> /root/.ssh/authorized_keys
    echo "Installed CT108 automation SSH key on PVE host"
  fi
fi

if pct status "$CTID" 2>/dev/null | grep -q running; then
  echo "Restarting CT${CTID} to apply swap..."
  pct reboot "$CTID"
else
  echo "CT${CTID} is stopped — start it to apply swap."
fi