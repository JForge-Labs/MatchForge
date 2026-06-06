#!/usr/bin/env bash
# MatchForge dev: Tailscale node auth + Funnel for public HTTPS preview.
# Custom domain match-forge.com → Digital Ocean prod later; dev uses *.ts.net Funnel.
set -euo pipefail

HOSTNAME="${TAILSCALE_HOSTNAME:-matchforge-dev}"
LOCAL_PORT="${TAILSCALE_FUNNEL_PORT:-80}"
DOMAIN="${APP_DOMAIN:-match-forge.com}"

echo "=== MatchForge Tailscale setup (dev) ==="
echo "Target hostname: ${HOSTNAME}"
echo "Public domain (prod): ${DOMAIN}"
echo ""

status_json() {
  tailscale status --json 2>/dev/null || echo '{}'
}

is_logged_in() {
  tailscale status --json 2>/dev/null | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print("yes" if d.get("BackendState")=="Running" else "no")' \
    2>/dev/null || echo "no"
}

if [[ "$(is_logged_in)" != "yes" ]]; then
  echo "Tailscale is not connected. Starting OAuth login..."
  echo ""
  echo "Open this URL in your browser and approve the device:"
  echo ""
  # Blocks until auth completes or times out; prints URL immediately.
  timeout 300 tailscale up --hostname="${HOSTNAME}" --ssh --accept-dns=true || {
    echo ""
    echo "Login not completed. Re-run:"
    echo "  /opt/matchforge/scripts/tailscale_setup.sh"
    exit 1
  }
fi

TS_IP="$(tailscale ip -4 2>/dev/null || true)"
DNS_NAME="$(status_json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); self=d.get("Self",{}); print(self.get("DNSName","").rstrip("."))' \
  2>/dev/null || true)"

echo ""
echo "Tailscale connected."
echo "  Tailnet IP:  ${TS_IP:-unknown}"
echo "  MagicDNS:    ${DNS_NAME:-unknown}"
echo ""

echo "Enabling Tailscale Funnel → localhost:${LOCAL_PORT} (nginx → MatchForge)..."
echo "First run may open the admin console to approve Funnel + HTTPS for your tailnet."
echo ""

if tailscale funnel status 2>/dev/null | grep -q "Funnel on"; then
  echo "Funnel already configured:"
  tailscale funnel status
else
  tailscale funnel --bg --yes "${LOCAL_PORT}" || {
    echo ""
    echo "Funnel setup needs admin approval. Visit https://login.tailscale.com/admin/acls"
    echo "Ensure HTTPS is enabled under DNS, then re-run this script."
    exit 1
  }
  echo ""
  tailscale funnel status
fi

FUNNEL_URL=""
if [[ -n "${DNS_NAME}" ]]; then
  FUNNEL_URL="https://${DNS_NAME}"
fi

echo ""
echo "=== Dev access URLs ==="
[[ -n "${FUNNEL_URL}" ]] && echo "  Public (Funnel):  ${FUNNEL_URL}"
[[ -n "${TS_IP}" ]]     && echo "  Tailnet:          http://${TS_IP}/"
echo "  LAN:              http://192.168.1.108/"
echo ""
echo "match-forge.com DNS will point to Digital Ocean for production."
echo "For dev preview, use the Funnel URL above until prod is live."