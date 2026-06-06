"""Token balance, grants, and per-activity charges."""
import logging
import secrets

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account
from app.models.credits import AccountCredit, CreditTransaction
from app.services.model_router import FOUNDER_CAP, route

logger = logging.getLogger(__name__)
settings = get_settings()


def billing_enabled() -> bool:
    return settings.billing_enabled


def _ensure_credit_row(db: Session, account_id: int) -> AccountCredit:
    row = (
        db.query(AccountCredit)
        .filter(AccountCredit.account_id == account_id)
        .first()
    )
    if row:
        return row
    row = AccountCredit(account_id=account_id, balance=0)
    db.add(row)
    db.flush()
    return row


def get_balance(db: Session, account_id: int) -> int:
    if not billing_enabled():
        return max(settings.signup_grant_tokens, _raw_balance(db, account_id))
    return _raw_balance(db, account_id)


def _raw_balance(db: Session, account_id: int) -> int:
    row = (
        db.query(AccountCredit)
        .filter(AccountCredit.account_id == account_id)
        .first()
    )
    return row.balance if row else 0


def can_afford(db: Session, account_id: int, amount: int) -> bool:
    if not billing_enabled():
        return True
    return _raw_balance(db, account_id) >= amount


def ensure_can_afford(
    db: Session, account_id: int, amount: int, *, activity: str
) -> None:
    if can_afford(db, account_id, amount):
        return
    raise HTTPException(
        402,
        detail={
            "error": "insufficient_tokens",
            "balance": _raw_balance(db, account_id),
            "required": amount,
            "activity": activity,
        },
    )


def grant_tokens(
    db: Session,
    account_id: int,
    amount: int,
    reason: str,
    *,
    note: str | None = None,
    metadata: dict | None = None,
) -> int:
    if amount <= 0:
        return get_balance(db, account_id)
    row = _ensure_credit_row(db, account_id)
    row.balance += amount
    db.add(
        CreditTransaction(
            account_id=account_id,
            delta=amount,
            reason=reason,
            note=note,
            metadata_json=metadata or {},
        )
    )
    db.flush()
    return row.balance


def charge_tokens(
    db: Session,
    account_id: int,
    activity: str,
    *,
    metadata: dict | None = None,
) -> int:
    """Deduct tokens for an activity. No-op when billing is disabled."""
    if not billing_enabled():
        return get_balance(db, account_id)

    llm_route = route(activity)
    row = _ensure_credit_row(db, account_id)
    if row.balance < llm_route.token_cost:
        raise HTTPException(
            402,
            detail={
                "error": "insufficient_tokens",
                "balance": row.balance,
                "required": llm_route.token_cost,
                "activity": activity,
            },
        )
    row.balance -= llm_route.token_cost
    meta = {"activity": activity, "model": llm_route.model, **(metadata or {})}
    db.add(
        CreditTransaction(
            account_id=account_id,
            delta=-llm_route.token_cost,
            reason=activity,
            metadata_json=meta,
        )
    )
    db.flush()
    return row.balance


def seed_accounts_to_minimum(db: Session, minimum: int) -> int:
    """Top up every account to at least `minimum` tokens. Returns accounts updated."""
    if minimum <= 0:
        return 0
    updated = 0
    for account in db.query(Account).all():
        row = _ensure_credit_row(db, account.id)
        if row.balance >= minimum:
            continue
        delta = minimum - row.balance
        row.balance = minimum
        db.add(
            CreditTransaction(
                account_id=account.id,
                delta=delta,
                reason="iteration_seed",
                note=f"Topped up to {minimum} tokens for R&D",
            )
        )
        updated += 1
    db.flush()
    return updated


def assign_founder_status(db: Session, account: Account) -> None:
    if account.is_founder:
        return
    verified_count = (
        db.query(func.count(Account.id))
        .filter(Account.email_verified_at.isnot(None))
        .scalar()
    ) or 0
    if verified_count <= FOUNDER_CAP:
        account.is_founder = True
        account.founder_number = verified_count


def ensure_referral_code(db: Session, account: Account) -> str:
    if account.referral_code:
        return account.referral_code
    code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10]
    account.referral_code = code
    db.flush()
    return code


def grant_signup_credits(db: Session, account: Account) -> int:
    assign_founder_status(db, account)
    ensure_referral_code(db, account)
    return grant_tokens(
        db,
        account.id,
        settings.signup_grant_tokens,
        "signup_grant",
        note="Initial token tranche",
    )