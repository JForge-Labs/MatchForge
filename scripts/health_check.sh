#!/bin/bash
# MatchForge CT108 post-restart system health check.
# Exit 0 = all critical checks pass; exit 1 = one or more failures.
set -uo pipefail

BOOT_MODE=false
LOG_FILE="/var/log/matchforge/health_check.log"

usage() {
  echo "Usage: $0 [--boot]"
  echo "  --boot   append output to $LOG_FILE (for systemd @reboot runs)"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --boot) BOOT_MODE=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

FAILURES=0
WARNINGS=0

pass() { echo "✓ $*"; }
fail() { echo "✗ $*"; FAILURES=$((FAILURES + 1)); }
warn() { echo "⚠ $*"; WARNINGS=$((WARNINGS + 1)); }

check_service() {
  local name="$1"
  if systemctl is-active --quiet "$name" 2>/dev/null; then
    pass "$name active"
  else
    fail "$name inactive or missing"
  fi
}

check_port() {
  local port="$1" label="$2"
  if ss -tln 2>/dev/null | grep -qE ":${port}\s"; then
    pass "$label :$port listening"
  else
    fail "$label :$port not listening"
  fi
}

check_http() {
  local url="$1" label="$2"
  if curl -sf --max-time 10 "$url" >/dev/null 2>&1; then
    pass "$label reachable ($url)"
  else
    fail "$label unreachable ($url)"
  fi
}

check_json_field() {
  local url="$1" label="$2" field="$3" expect="$4"
  local body
  body=$(curl -sf --max-time 10 "$url" 2>/dev/null) || { fail "$label unreachable ($url)"; return; }
  if echo "$body" | grep -q "\"$field\"[[:space:]]*:[[:space:]]*\"$expect\""; then
    pass "$label $field=$expect"
  else
    fail "$label unexpected response: $body"
  fi
}

run_checks() {
  echo "=== MatchForge system health check ==="
  echo "Host: $(hostname) | Time: $(date -Is)"

  echo
  echo "--- Boot / resources ---"
  uptime
  df -h / | awk 'NR==1 || NR==2'
  free -h | awk 'NR==1 || /^Mem:/{print}'
  swap_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
  if [[ "$swap_kb" -gt 0 ]]; then
    pass "swap active ($(( swap_kb / 1024 ))MB)"
    swapon --show 2>/dev/null || true
  elif mount | grep -q ' / type zfs'; then
    warn "swap not active — ZFS LXC needs host: pct set 108 -swap 512 (run pve_ct108_swap.sh on PVE)"
  else
    warn "swap not active (expected 512MB per CT108 spec)"
  fi
  if mount | awk '$3=="/"{print $6}' | grep -q rw; then
    pass "root filesystem read-write"
  else
    fail "root filesystem not read-write"
  fi
  avail_kb=$(df / | awk 'NR==2{print $4}')
  if [[ "$avail_kb" -lt 1048576 ]]; then
    warn "disk free < 1GB on /"
  else
    pass "disk free >= 1GB on /"
  fi

  echo
  echo "--- Core services ---"
  for svc in matchforge postgresql redis-server nginx docker tailscaled ollama; do
    check_service "$svc"
  done
  if systemctl --failed --no-legend 2>/dev/null | grep -q .; then
    fail "failed systemd units present"
    systemctl --failed --no-pager
  else
    pass "no failed systemd units"
  fi

  echo
  echo "--- Network / ports ---"
  check_port 8000 "API"
  check_port 80 "nginx"
  check_port 5432 "PostgreSQL"
  check_port 6379 "Redis"
  if tailscale status --self 2>/dev/null | grep -qE '100\.'; then
    pass "Tailscale online ($(tailscale ip -4 2>/dev/null || echo unknown))"
  else
    warn "Tailscale not fully online (see Asana: Re-auth Tailscale)"
  fi

  echo
  echo "--- Application ---"
  check_http "http://127.0.0.1:8000/health" "API /health"
  check_json_field "http://127.0.0.1:8000/health/db" "API /health/db" "database" "ok"
  if curl -sf --max-time 15 "http://127.0.0.1:8000/health/llm" 2>/dev/null | grep -q '"llm"[[:space:]]*:[[:space:]]*"ok"'; then
    pass "API /health/llm llm=ok"
  else
    warn "API /health/llm not ok (cloud/local LLM may be down)"
  fi
  code=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "http://127.0.0.1/dashboard" 2>/dev/null || echo "000")
  if [[ "$code" =~ ^(200|302)$ ]]; then
    pass "nginx /dashboard HTTP $code"
  else
    fail "nginx /dashboard HTTP $code"
  fi

  echo
  echo "--- Data stores ---"
  if sudo -u postgres psql -d matchforge_dev -tAc "SELECT 1" 2>/dev/null | grep -q 1; then
    pass "PostgreSQL matchforge_dev query ok"
  else
    fail "PostgreSQL matchforge_dev query failed"
  fi
  if sudo -u postgres psql -d matchforge_dev -tAc "SELECT extname FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q vector; then
    pass "pgvector extension present"
  else
    fail "pgvector extension missing"
  fi
  if redis-cli ping 2>/dev/null | grep -q PONG; then
    pass "Redis PONG"
  else
    fail "Redis not responding"
  fi

  echo
  echo "--- Secrets / app files ---"
  if [[ -f /opt/matchforge/.env ]]; then
    perms=$(stat -c '%a' /opt/matchforge/.env)
    if [[ "$perms" == "600" ]]; then
      pass ".env present (mode 600)"
    else
      warn ".env mode $perms (expected 600)"
    fi
  else
    fail ".env missing"
  fi
  if [[ -x /opt/matchforge/venv/bin/python ]]; then
    pass "Python venv present"
  else
    fail "Python venv missing"
  fi

  echo
  echo "--- Recent boot errors ---"
  err_count=$(journalctl -b -p err --no-pager -q 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$err_count" -eq 0 ]]; then
    pass "no journal errors this boot"
  else
    warn "$err_count journal error(s) this boot (often benign in unprivileged LXC)"
    journalctl -b -p err --no-pager -n 5 2>/dev/null || true
  fi

  echo
  echo "=== Summary: $FAILURES failure(s), $WARNINGS warning(s) ==="
  if [[ "$FAILURES" -eq 0 ]]; then
    echo "RESULT: PASS"
    return 0
  fi
  echo "RESULT: FAIL"
  return 1
}

mkdir -p "$(dirname "$LOG_FILE")"

if [[ "$BOOT_MODE" == true ]]; then
  {
    echo
    run_checks
  } 2>&1 | tee -a "$LOG_FILE"
  exit "${PIPESTATUS[1]}"
else
  run_checks
fi