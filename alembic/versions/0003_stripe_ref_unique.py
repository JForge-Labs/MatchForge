"""Unique Stripe reference per credited purchase.

The webhook and the success-page reconcile fire within seconds of each
other; both used check-then-insert, so a user could be double-credited.
A partial unique index makes crediting idempotent at the database level.

Revision ID: 0003_stripe_ref_unique
Revises: 0002_p3_memory
Create Date: 2026-07-08
"""
from alembic import op

revision = "0003_stripe_ref_unique"
down_revision = "0002_p3_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_stripe_ref "
        "ON credit_transactions ((metadata_json->>'stripe_ref')) "
        "WHERE reason = 'stripe_purchase'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_credit_tx_stripe_ref")
