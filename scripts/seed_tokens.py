#!/usr/bin/env python3
"""One-shot: top up all accounts to SEED_MIN_TOKENS (default 500)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services import credit_service

settings = get_settings()
minimum = settings.seed_min_tokens or 500

db = SessionLocal()
try:
    n = credit_service.seed_accounts_to_minimum(db, minimum)
    db.commit()
    print(f"Topped up {n} account(s) to at least {minimum} tokens.")
finally:
    db.close()