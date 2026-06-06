#!/usr/bin/env python3
"""Merge duplicate profile tiles (same platform + username/name per account)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.services.profile_merge_service import merge_duplicate_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Dedupe MatchForge profile tiles")
    parser.add_argument("--account-id", type=int, default=None, help="Limit to one account")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        merged = merge_duplicate_profiles(db, args.account_id)
        print(f"Merged {merged} duplicate profile(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()