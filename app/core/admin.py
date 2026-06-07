"""Admin access control."""
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import ACCOUNT_EMAIL_KEY, get_account_id
from app.core.config import get_settings


def admin_emails() -> set[str]:
    raw = get_settings().admin_emails or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _session_email(request: Request, db: Session | None = None) -> str:
    email = (request.session.get(ACCOUNT_EMAIL_KEY) or "").strip().lower()
    if email or not db:
        return email
    account_id = get_account_id(request)
    if not account_id:
        return ""
    from app.models.account import Account

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return ""
    email = account.email.strip().lower()
    request.session[ACCOUNT_EMAIL_KEY] = account.email
    return email


def is_admin(request: Request, db: Session | None = None) -> bool:
    email = _session_email(request, db)
    return bool(email and email in admin_emails())


def require_admin(request: Request, db: Session | None = None) -> None:
    if not is_admin(request, db):
        raise HTTPException(403, "Admin access required")