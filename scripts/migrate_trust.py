#!/usr/bin/env python3
"""Add trust/authenticity columns to existing MatchForge schema."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.db import Base, engine

NEW_COLUMNS = [
    ("profiles", "authenticity_score", "DOUBLE PRECISION"),
    ("profiles", "naturalness_score", "DOUBLE PRECISION"),
    ("profiles", "catfish_risk_score", "DOUBLE PRECISION"),
    ("profiles", "bot_risk_score", "DOUBLE PRECISION"),
    ("profiles", "trust_analysis", "JSONB DEFAULT '{}'::jsonb"),
    ("rankings", "authenticity_score", "DOUBLE PRECISION"),
    ("rankings", "naturalness_score", "DOUBLE PRECISION"),
    ("rankings", "catfish_risk_score", "DOUBLE PRECISION"),
    ("rankings", "bot_risk_score", "DOUBLE PRECISION"),
    ("rankings", "trust_explanation", "TEXT"),
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
    print("Trust columns migrated successfully.")


if __name__ == "__main__":
    main()