#!/usr/bin/env bash
# Render matchforge.app.yaml with secrets from local env files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="${ROOT}/infrastructure/deploy/matchforge.app.yaml"
OUT="${1:-/tmp/matchforge-deploy.yaml}"

source "${HOME}/.grok/secrets/matchforge-prod.env"
[[ -f "${HOME}/.grok/secrets/digitalocean.env" ]] && source "${HOME}/.grok/secrets/digitalocean.env"

sed \
  -e "s|__SECRET_KEY__|${SECRET_KEY}|g" \
  -e "s|__AUTH_PASSWORD__|${AUTH_PASSWORD}|g" \
  "${TEMPLATE}" > "${OUT}"

echo "Rendered: ${OUT}"