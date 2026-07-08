"""Account signup, email verification, magic-link login, and deletion."""
import hashlib
import logging
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account, AuthToken
from app.models.profile import Profile, ProfileEvidence, Ranking, SocialEnrichment
from app.models.user import UserProfile
from app.services import affiliate_service, credit_service, email_service, referral_service

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TOKEN_TTL = {
    "signup_verify": timedelta(hours=24),
    "login_magic": timedelta(minutes=15),
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(email)))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def build_auth_url(token: str, purpose: str) -> str:
    settings = get_settings()
    base = settings.app_url.rstrip("/")
    return f"{base}/auth/verify?token={token}&purpose={purpose}"


def _issue_token(db: Session, account: Account, purpose: str) -> str:
    raw = secrets.token_urlsafe(32)
    token = AuthToken(
        account_id=account.id,
        token_hash=_hash_token(raw),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + TOKEN_TTL[purpose],
    )
    db.add(token)
    db.commit()
    return raw


def _send_token_email(account: Account, purpose: str, raw_token: str) -> None:
    link = build_auth_url(raw_token, purpose)
    if purpose == "signup_verify":
        email_service.send_auth_link(
            to=account.email,
            subject="Verify your MatchForge account",
            action="Confirm your email to finish signing up",
            link=link,
        )
    else:
        email_service.send_auth_link(
            to=account.email,
            subject="Your MatchForge sign-in link",
            action="Sign in to MatchForge",
            link=link,
        )


def _dev_link_allowed() -> bool:
    """Raw auth tokens may be shown in the UI only outside production.

    In production an unconfigured SMTP must fail closed: exposing the token
    would let any visitor sign in as any email address.
    """
    if email_service.smtp_configured():
        return False
    if get_settings().app_env == "production":
        logger.error(
            "SMTP is not configured in production — auth emails cannot be "
            "sent and sign-in links are withheld."
        )
        return False
    return True


def request_signup(
    db: Session,
    email: str,
    *,
    referral_code: str | None = None,
    affiliate_ref: str | None = None,
) -> tuple[str, str | None]:
    """Create or refresh a pending account and send verification email."""
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        return "invalid", None

    account = db.query(Account).filter(Account.email == normalized).first()
    if account and account.email_verified_at:
        return "exists", None

    if not account:
        referrer = referral_service.resolve_referrer(db, referral_code, normalized)
        affiliate = affiliate_service.resolve_affiliate(db, affiliate_ref, normalized)
        account = Account(
            email=normalized,
            referred_by_account_id=referrer.id if referrer else None,
            referred_by_affiliate_id=affiliate.id if affiliate else None,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    raw = _issue_token(db, account, "signup_verify")
    _send_token_email(account, "signup_verify", raw)
    return "sent", raw if _dev_link_allowed() else None


def request_login_link(db: Session, email: str) -> tuple[str, str | None]:
    """Send a magic sign-in link to a verified account."""
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        return "invalid", None

    account = db.query(Account).filter(Account.email == normalized).first()
    if not account:
        return "not_found", None
    if not account.email_verified_at:
        raw = _issue_token(db, account, "signup_verify")
        _send_token_email(account, "signup_verify", raw)
        return "unverified", raw if _dev_link_allowed() else None

    raw = _issue_token(db, account, "login_magic")
    _send_token_email(account, "login_magic", raw)
    return "sent", raw if _dev_link_allowed() else None


def verify_token(db: Session, raw_token: str, purpose: str) -> Account | None:
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    row = (
        db.query(AuthToken)
        .filter(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
        .first()
    )
    if not row:
        return None

    account = db.query(Account).filter(Account.id == row.account_id).first()
    if not account:
        return None

    row.used_at = now
    first_verify = purpose == "signup_verify" and not account.email_verified_at
    if first_verify:
        account.email_verified_at = now
        credit_service.grant_signup_credits(db, account)
        referral_service.ensure_referral_row(db, account)
        referral_service.grant_referred_signup_bonus(db, account)
    db.commit()
    db.refresh(account)
    return account


def ensure_profile(db: Session, account: Account) -> UserProfile:
    profile = (
        db.query(UserProfile).filter(UserProfile.account_id == account.id).first()
    )
    if profile:
        return profile
    profile = UserProfile(account_id=account.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _unlink_upload(path_str: str | None) -> None:
    if not path_str:
        return
    path = Path(path_str)
    if path.is_file():
        path.unlink(missing_ok=True)


def _remove_account_upload_dir(account_id: int) -> None:
    upload_dir = Path("data/uploads/users") / str(account_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)


def delete_account(db: Session, account_id: int) -> bool:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return False
    email = account.email

    user = (
        db.query(UserProfile).filter(UserProfile.account_id == account_id).first()
    )
    if user:
        _unlink_upload(user.avatar_path)
        _unlink_upload(user.selfie_path)

    # rankings/social_enrichments have no ON DELETE CASCADE — remove them
    # explicitly or the account delete fails with an IntegrityError.
    profile_ids = [
        pid
        for (pid,) in db.query(Profile.id).filter(Profile.account_id == account_id)
    ]
    if profile_ids:
        for model in (Ranking, SocialEnrichment, ProfileEvidence):
            db.query(model).filter(model.profile_id.in_(profile_ids)).delete(
                synchronize_session=False
            )
    for pid in profile_ids:
        uploads = Path("data/uploads") / str(pid)
        if uploads.is_dir():
            shutil.rmtree(uploads, ignore_errors=True)

    _remove_account_upload_dir(account_id)

    db.delete(account)
    db.commit()
    logger.info("Deleted account id=%s email=%s", account_id, email)
    return True