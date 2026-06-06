#!/usr/bin/env python3
"""v0.2 migrations: account scoping, credits, profile evidence, Grok-era schema."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.db import Base, engine
from app.models.account import Account, AuthToken  # noqa: F401
from app.models.credits import AccountCredit, CreditTransaction  # noqa: F401
from app.models.profile import Profile, ProfileEvidence  # noqa: F401
from app.models.referral import Referral  # noqa: F401
from app.models.user import UserProfile  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)

    stmts = [
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_founder BOOLEAN DEFAULT FALSE",
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS founder_number INTEGER",
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16)",
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS referred_by_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_referral_code ON accounts (referral_code)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE",
        "CREATE INDEX IF NOT EXISTS ix_profiles_account_id ON profiles (account_id)",
    ]
    with engine.connect() as conn:
        for sql in stmts:
            conn.execute(text(sql))
        conn.commit()

    print("v0.2 migrations applied.")


if __name__ == "__main__":
    main()