#!/usr/bin/env bash
# Render an App Platform spec with secrets from local env files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE_NAME="${1:-matchforge.app.yaml}"
OUT="${2:-/tmp/matchforge-deploy.yaml}"
TEMPLATE="${ROOT}/infrastructure/deploy/${TEMPLATE_NAME}"

source "${HOME}/.grok/secrets/matchforge-prod.env"
if [[ -f "${HOME}/.grok/secrets/stripe.env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.grok/secrets/stripe.env"
elif [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^STRIPE_|^TOKENS_PER_USD|^MIN_TOPUP_USD|^DEFAULT_TOPUP_USD' "${ROOT}/.env")
  set +a
fi
if [[ -f "${HOME}/.grok/secrets/xai.env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.grok/secrets/xai.env"
fi
if [[ -f "${HOME}/.grok/secrets/brave.env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.grok/secrets/brave.env"
elif [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^BRAVE_API_KEY=' "${ROOT}/.env")
  set +a
fi
if [[ -f "${HOME}/.grok/secrets/digitalocean.env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.grok/secrets/digitalocean.env"
  export DIGITALOCEAN_ACCESS_TOKEN="${DIGITALOCEAN_ACCESS_TOKEN:-$DIGITALOCEAN_API_TOKEN}"
fi

: "${STRIPE_SECRET_KEY:=}"
: "${STRIPE_PUBLISHABLE_KEY:=}"
: "${STRIPE_WEBHOOK_SECRET:=}"
: "${STRIPE_PRODUCT_ID:=}"

sed \
  -e "s|__SECRET_KEY__|${SECRET_KEY}|g" \
  -e "s|__AUTH_PASSWORD__|${AUTH_PASSWORD}|g" \
  -e "s|__SMTP_HOST__|${SMTP_HOST}|g" \
  -e "s|__SMTP_PORT__|${SMTP_PORT}|g" \
  -e "s|__SMTP_USER__|${SMTP_USER}|g" \
  -e "s|__SMTP_PASSWORD__|${SMTP_PASSWORD}|g" \
  -e "s|__SMTP_FROM__|${SMTP_FROM}|g" \
  -e "s|__SMTP_USE_TLS__|${SMTP_USE_TLS}|g" \
  -e "s|__XAI_API_KEY__|${XAI_API_KEY}|g" \
  -e "s|__X_BEARER_TOKEN__|${X_BEARER_TOKEN:-}|g" \
  -e "s|__BRAVE_API_KEY__|${BRAVE_API_KEY:-}|g" \
  -e "s|__STRIPE_SECRET_KEY__|${STRIPE_SECRET_KEY}|g" \
  -e "s|__STRIPE_PUBLISHABLE_KEY__|${STRIPE_PUBLISHABLE_KEY}|g" \
  -e "s|__STRIPE_WEBHOOK_SECRET__|${STRIPE_WEBHOOK_SECRET}|g" \
  -e "s|__STRIPE_PRODUCT_ID__|${STRIPE_PRODUCT_ID}|g" \
  "${TEMPLATE}" > "${OUT}"

echo "Rendered: ${OUT}"