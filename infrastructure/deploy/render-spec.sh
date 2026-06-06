#!/usr/bin/env bash
# Render matchforge.app.yaml with secrets from local env files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="${ROOT}/infrastructure/deploy/matchforge.app.yaml"
OUT="${1:-/tmp/matchforge-deploy.yaml}"

source "${HOME}/.grok/secrets/matchforge-prod.env"
if [[ -f "${HOME}/.grok/secrets/digitalocean.env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.grok/secrets/digitalocean.env"
  export DIGITALOCEAN_ACCESS_TOKEN="${DIGITALOCEAN_ACCESS_TOKEN:-$DIGITALOCEAN_API_TOKEN}"
fi

sed \
  -e "s|__SECRET_KEY__|${SECRET_KEY}|g" \
  -e "s|__AUTH_PASSWORD__|${AUTH_PASSWORD}|g" \
  -e "s|__SMTP_HOST__|${SMTP_HOST}|g" \
  -e "s|__SMTP_PORT__|${SMTP_PORT}|g" \
  -e "s|__SMTP_USER__|${SMTP_USER}|g" \
  -e "s|__SMTP_PASSWORD__|${SMTP_PASSWORD}|g" \
  -e "s|__SMTP_FROM__|${SMTP_FROM}|g" \
  -e "s|__SMTP_USE_TLS__|${SMTP_USE_TLS}|g" \
  "${TEMPLATE}" > "${OUT}"

echo "Rendered: ${OUT}"