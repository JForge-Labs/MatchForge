#!/bin/bash
# MatchForge session bootstrap — run at the start of every dev session.
set -euo pipefail
cd /opt/matchforge
source venv/bin/activate

echo "=== MatchForge session start ==="

# Service health
systemctl is-active --quiet matchforge && echo "✓ matchforge.service active" || echo "✗ matchforge.service down"
curl -sf http://127.0.0.1:8000/health >/dev/null && echo "✓ API :8000" || echo "✗ API unreachable"
curl -sf http://127.0.0.1/health >/dev/null && echo "✓ nginx :80" || echo "✗ nginx proxy unreachable"

# Asana pull
SECRETS="${MATCHFORGE_SECRETS:-$HOME/.matchforge_secrets}"
if [ -f "$SECRETS" ] && grep -q ASANA_PAT "$SECRETS"; then
  export $(grep ASANA_PAT "$SECRETS" | xargs)
  python scripts/asana_sync.py || echo "⚠ Asana sync failed (check PAT)"
else
  echo "⚠ ASANA_PAT not in $SECRETS — skip Asana sync"
fi

echo "=== Read data/asana_state.json before planning work ==="