"""P3 memory features: profile rename + ranking score history.

- profiles.display_name — user-set name shown on cards; the extracted name
  stays authoritative for dedup identity_key.
- rankings.score_history — JSONB list of {at, trigger, scores} snapshots
  appended before every re-rank, powering the analysis-history timeline.

Revision ID: 0002_p3_memory
Revises: 0001_baseline
Create Date: 2026-07-08
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002_p3_memory"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profiles", sa.Column("display_name", sa.String(256), nullable=True)
    )
    op.add_column(
        "rankings",
        sa.Column("score_history", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("rankings", "score_history")
    op.drop_column("profiles", "display_name")
