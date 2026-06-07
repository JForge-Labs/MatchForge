"""Admin access control."""
from fastapi import HTTPException, Request

from app.core.auth import get_account_id
from app.core.config import get_settings


def admin_emails() -> set[str]:
    raw = get_settings().admin_emails or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin(request: Request) -> bool:
    email = (request.session.get("account_email") or "").lower()
    return bool(email and email in admin_emails())


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(403, "Admin access required")