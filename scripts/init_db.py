#!/usr/bin/env python3
"""Initialize database schema and seed default preference vector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.db import Base, SessionLocal, engine
from app.models.account import Account, AuthToken  # noqa: F401 — register tables
from app.models.profile import PreferenceVector
from app.models.user import UserProfile

DEFAULT_TRAITS = {
    "values": ["kindness", "intellectual curiosity", "emotional availability"],
    "lifestyle": ["active", "social but not party-heavy", "travel-friendly"],
    "communication": ["direct", "witty", "asks good questions"],
    "dealbreakers": ["dishonesty", "contempt", "substance abuse"],
    "attraction": ["genuine smile", "style intentionality", "healthy presentation"],
    "interests_preferred": [
        "reading",
        "music",
        "outdoors",
        "food",
        "art",
        "tech",
    ],
}

DEFAULT_WEIGHTS = {
    "compatibility": 0.45,
    "attractiveness": 0.25,
    "red_flags": 0.30,
}


def main() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS account_id INTEGER "
                "REFERENCES accounts(id) ON DELETE CASCADE"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_user_profiles_account_id ON user_profiles (account_id)"
            )
        )
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS user_profiles_id_seq"))
        conn.execute(
            text(
                "SELECT setval('user_profiles_id_seq', "
                "COALESCE((SELECT MAX(id) FROM user_profiles), 1))"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE user_profiles "
                "ALTER COLUMN id SET DEFAULT nextval('user_profiles_id_seq')"
            )
        )
        conn.execute(
            text("ALTER SEQUENCE user_profiles_id_seq OWNED BY user_profiles.id")
        )
        conn.execute(
            text(
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS preferred_genders JSONB DEFAULT '[]'::jsonb"
            )
        )
        conn.commit()

    db = SessionLocal()
    try:
        existing = db.query(PreferenceVector).filter(
            PreferenceVector.is_default.is_(True)
        ).first()
        if not existing:
            pref = PreferenceVector(
                name="Default Ideal Match",
                description=(
                    "Seed preference vector for R&D — customize traits and weights "
                    "to match your dating priorities."
                ),
                traits=DEFAULT_TRAITS,
                weights=DEFAULT_WEIGHTS,
                is_default=True,
            )
            db.add(pref)
            db.commit()
            print(f"Seeded preference vector id={pref.id}")
        else:
            print(f"Default preference vector already exists id={existing.id}")

        user = db.query(UserProfile).filter(UserProfile.id == 1).first()
        if not user:
            db.add(UserProfile(id=1))
            db.commit()
            print("Created singleton user profile (onboarding pending)")
        else:
            print(f"User profile exists — onboarding_complete={user.onboarding_complete}")
    finally:
        db.close()

    print("Database initialized successfully.")


if __name__ == "__main__":
    main()