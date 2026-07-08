"""Baseline — existing v0.3 schema.

Documents the schema as created by scripts/init_db.py (create_all + the
historical v0x ALTER blocks) at the time Alembic was introduced. Existing
deployments are stamped at this revision by scripts/migrate.py; fresh
installs run init_db.py (which creates everything) and stamp head.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-08
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # schema already exists — see docstring


def downgrade() -> None:
    pass
