"""Referral program: attribution, lock-in milestones, token rewards."""
import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account
from app.models.credits import CreditTransaction
from app.models.referral import Referral
from app.services import credit_service
logger = logging.getLogger(__name__)
settings = get_settings()

# Referred user gets extra tokens when signing up via a valid link
REFERRED_SIGNUP_BONUS = 25
# Referrer reward when referral locks in (onboarding + first upload)
REFERRAL_LOCK_REFERRER_TOKENS = 50
# Founding members earn extra per locked-in referral
REFERRAL_LOCK_FOUNDER_EXTRA = 25


def build_referral_url(code: str) -> str:
    base = settings.app_url.rstrip("/")
    return f"{base}/signup?ref={code}"


def resolve_referrer(
    db: Session, referral_code: str | None, signup_email: str
) -> Account | None:
    if not referral_code or not referral_code.strip():
        return None
    referrer = (
        db.query(Account)
        .filter(Account.referral_code == referral_code.strip())
        .first()
    )
    if not referrer:
        return None
    if referrer.email.lower() == signup_email.lower():
        return None
    return referrer


def ensure_referral_row(db: Session, account: Account) -> Referral | None:
    """Create pending referral row when account was referred at signup."""
    if not account.referred_by_account_id:
        return None
    existing = (
        db.query(Referral)
        .filter(Referral.referred_account_id == account.id)
        .first()
    )
    if existing:
        return existing
    if account.referred_by_account_id == account.id:
        return None
    row = Referral(
        referrer_account_id=account.referred_by_account_id,
        referred_account_id=account.id,
        status="pending",
    )
    db.add(row)
    db.flush()
    return row


def grant_referred_signup_bonus(db: Session, account: Account) -> int | None:
    """Extra tokens for new user who signed up via referral link."""
    if not account.referred_by_account_id:
        return None
    already = (
        db.query(CreditTransaction)
        .filter(
            CreditTransaction.account_id == account.id,
            CreditTransaction.reason == "referred_signup_bonus",
        )
        .first()
    )
    if already:
        return None
    ensure_referral_row(db, account)
    return credit_service.grant_tokens(
        db,
        account.id,
        REFERRED_SIGNUP_BONUS,
        "referred_signup_bonus",
        note="Bonus for joining via referral link",
        metadata={"referrer_account_id": account.referred_by_account_id},
    )


def _referrer_lock_payout(referrer: Account) -> int:
    bonus = REFERRAL_LOCK_REFERRER_TOKENS
    if referrer.is_founder:
        bonus += REFERRAL_LOCK_FOUNDER_EXTRA
    return bonus


def mark_onboarding_complete(db: Session, account_id: int) -> Referral | None:
    ref = (
        db.query(Referral)
        .filter(Referral.referred_account_id == account_id)
        .first()
    )
    if not ref or ref.onboarding_complete_at:
        return ref
    ref.onboarding_complete_at = datetime.now(timezone.utc)
    db.flush()
    return try_lock_referral(db, ref)


def mark_first_upload(db: Session, account_id: int) -> Referral | None:
    ref = (
        db.query(Referral)
        .filter(Referral.referred_account_id == account_id)
        .first()
    )
    if not ref or ref.first_upload_at:
        return ref
    ref.first_upload_at = datetime.now(timezone.utc)
    db.flush()
    return try_lock_referral(db, ref)


def try_lock_referral(db: Session, ref: Referral) -> Referral | None:
    """Lock in and pay referrer when referred user completes onboarding + first upload."""
    if ref.status == "locked_in":
        return ref
    if not ref.onboarding_complete_at or not ref.first_upload_at:
        return ref

    referrer = (
        db.query(Account).filter(Account.id == ref.referrer_account_id).first()
    )
    if not referrer:
        return ref

    payout = _referrer_lock_payout(referrer)
    ref.status = "locked_in"
    ref.locked_in_at = datetime.now(timezone.utc)
    ref.referrer_tokens_awarded = payout
    credit_service.grant_tokens(
        db,
        referrer.id,
        payout,
        "referral_locked",
        note=f"Locked-in referral (account {ref.referred_account_id})",
        metadata={
            "referred_account_id": ref.referred_account_id,
            "is_founder_bonus": referrer.is_founder,
        },
    )
    db.flush()
    logger.info(
        "Referral locked: referrer=%s referred=%s tokens=%s",
        referrer.id,
        ref.referred_account_id,
        payout,
    )
    return ref


def get_referral_stats(db: Session, account_id: int) -> dict:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return {}
    code = credit_service.ensure_referral_code(db, account)

    pending = (
        db.query(func.count(Referral.id))
        .filter(
            Referral.referrer_account_id == account_id,
            Referral.status == "pending",
        )
        .scalar()
    ) or 0
    locked = (
        db.query(func.count(Referral.id))
        .filter(
            Referral.referrer_account_id == account_id,
            Referral.status == "locked_in",
        )
        .scalar()
    ) or 0
    earned = (
        db.query(func.coalesce(func.sum(Referral.referrer_tokens_awarded), 0))
        .filter(Referral.referrer_account_id == account_id)
        .scalar()
    ) or 0

    lock_reward = _referrer_lock_payout(account)
    return {
        "referral_code": code,
        "referral_url": build_referral_url(code),
        "is_founder": account.is_founder,
        "founder_number": account.founder_number,
        "pending_referrals": pending,
        "locked_in_referrals": locked,
        "tokens_earned_from_referrals": int(earned),
        "lock_in_reward_tokens": lock_reward,
        "referred_signup_bonus": REFERRED_SIGNUP_BONUS,
        "lock_in_requires": "onboarding + first profile upload",
    }


