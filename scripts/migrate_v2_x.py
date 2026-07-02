#!/usr/bin/env python3
"""v2 migration — X verification columns and x_profiles cache table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

import app.models  # noqa: F401 — register all tables incl. XProfileCache
from app.core.db import Base, engine

NEW_COLUMNS = [
    ("profiles", "x_social_proof_score", "DOUBLE PRECISION"),
    ("profiles", "x_verification", "JSONB DEFAULT '{}'::jsonb"),
    ("rankings", "x_social_proof_score", "DOUBLE PRECISION"),
]


def main() -> None:
    with engine.connect() as conn:
        for table, col, col_type in NEW_COLUMNS:
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    f"{col} {col_type}"
                )
            )
        conn.commit()
    Base.metadata.create_all(bind=engine)
    print("v2 X verification schema migrated successfully.")


if __name__ == "__main__":
    main()
