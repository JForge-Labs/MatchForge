"""Account signup, email verification, and magic-link login."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account, AuthToken
from app.models.user import UserProfile
from app.services import email_service

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


def request_signup(db: Session, email: str) -> tuple[str, str | None]:
    """Create or refresh a pending account and send verification email."""
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        return "invalid", None

    account = db.query(Account).filter(Account.email == normalized).first()
    if account and account.email_verified_at:
        return "exists", None

    if not account:
        account = Account(email=normalized)
        db.add(account)
        db.commit()
        db.refresh(account)

    raw = _issue_token(db, account, "signup_verify")
    _send_token_email(account, "signup_verify", raw)
    return "sent", raw if not email_service.smtp_configured() else None


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
        return "unverified", raw if not email_service.smtp_configured() else None

    raw = _issue_token(db, account, "login_magic")
    _send_token_email(account, "login_magic", raw)
    return "sent", raw if not email_service.smtp_configured() else None


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
    if purpose == "signup_verify" and not account.email_verified_at:
        account.email_verified_at = now
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