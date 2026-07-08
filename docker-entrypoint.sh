#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_DB_INIT:-true}" == "true" ]]; then
  echo "Running database initialization in background..."
  python scripts/init_db.py &
fi

echo "Applying database migrations..."
python scripts/migrate.py || echo "WARNING: migrations failed — continuing with existing schema"

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"