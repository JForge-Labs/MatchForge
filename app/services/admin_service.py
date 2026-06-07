"""Aggregate metrics and operator views for the admin dashboard."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.credits import AccountCredit, CreditTransaction
from app.models.profile import Profile
from app.models.referral import Referral
from app.models.user import UserProfile


def dashboard_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_accounts = db.query(func.count(Account.id)).scalar() or 0
    verified_accounts = (
        db.query(func.count(Account.id))
        .filter(Account.email_verified_at.isnot(None))
        .scalar()
    ) or 0
    new_accounts_7d = (
        db.query(func.count(Account.id))
        .filter(Account.created_at >= week_ago)
        .scalar()
    ) or 0
    total_profiles = db.query(func.count(Profile.id)).scalar() or 0

    purchases = (
        db.query(
            func.count(CreditTransaction.id),
            func.coalesce(
                func.sum(
                    cast(
                        CreditTransaction.metadata_json["topup_usd"].astext,
                        Integer,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(CreditTransaction.delta), 0),
        )
        .filter(CreditTransaction.reason == "stripe_purchase")
        .first()
    )
    purchase_count = int(purchases[0] or 0)
    purchase_usd = float(purchases[1] or 0)
    tokens_sold = int(purchases[2] or 0)

    purchases_7d = (
        db.query(func.count(CreditTransaction.id))
        .filter(
            CreditTransaction.reason == "stripe_purchase",
            CreditTransaction.created_at >= week_ago,
        )
        .scalar()
    ) or 0

    token_balance = (
        db.query(func.coalesce(func.sum(CreditTransaction.delta), 0)).scalar()
    ) or 0

    referrals_locked = (
        db.query(func.count(Referral.id))
        .filter(Referral.status == "locked_in")
        .scalar()
    ) or 0
    referrals_pending = (
        db.query(func.count(Referral.id))
        .filter(Referral.status == "pending")
        .scalar()
    ) or 0

    return {
        "total_accounts": total_accounts,
        "verified_accounts": verified_accounts,
        "new_accounts_7d": new_accounts_7d,
        "total_profiles": total_profiles,
        "stripe_purchases": purchase_count,
        "stripe_revenue_usd": purchase_usd,
        "tokens_sold": tokens_sold,
        "stripe_purchases_7d": purchases_7d,
        "net_token_ledger": int(token_balance),
        "referrals_locked": referrals_locked,
        "referrals_pending": referrals_pending,
        "generated_at": now.isoformat(),
    }


def list_accounts(db: Session, *, limit: int = 50) -> list[dict]:
    accounts = (
        db.query(Account).order_by(Account.created_at.desc()).limit(limit).all()
    )
    if not accounts:
        return []

    ids = [a.id for a in accounts]
    profiles = {
        p.account_id: p
        for p in db.query(UserProfile).filter(UserProfile.account_id.in_(ids)).all()
    }
    credits = {
        c.account_id: c.balance
        for c in db.query(AccountCredit).filter(AccountCredit.account_id.in_(ids)).all()
    }
    profile_counts = dict(
        db.query(Profile.account_id, func.count(Profile.id))
        .filter(Profile.account_id.in_(ids))
        .group_by(Profile.account_id)
        .all()
    )

    rows: list[dict] = []
    for acc in accounts:
        profile = profiles.get(acc.id)
        rows.append(
            {
                "id": acc.id,
                "email": acc.email,
                "verified": acc.email_verified_at is not None,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "display_name": profile.display_name if profile else None,
                "onboarding_complete": bool(profile and profile.onboarding_complete),
                "token_balance": int(credits.get(acc.id, 0)),
                "profiles_vetted": int(profile_counts.get(acc.id, 0)),
                "is_founder": acc.is_founder,
            }
        )
    return rows


def list_transactions(db: Session, *, limit: int = 50) -> list[dict]:
    txs = (
        db.query(CreditTransaction, Account.email)
        .join(Account, CreditTransaction.account_id == Account.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .all()
    )
    rows: list[dict] = []
    for tx, email in txs:
        meta = tx.metadata_json or {}
        rows.append(
            {
                "id": tx.id,
                "account_id": tx.account_id,
                "email": email,
                "delta": tx.delta,
                "reason": tx.reason,
                "note": tx.note,
                "topup_usd": meta.get("topup_usd"),
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
        )
    return rows