#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_DB_INIT:-true}" == "true" ]]; then
  echo "Running database initialization in background..."
  python scripts/init_db.py &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"