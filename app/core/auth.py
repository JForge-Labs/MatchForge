"""Session-based auth: email accounts + optional shared-password bootstrap."""
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

SESSION_KEY = "authenticated"
ACCOUNT_ID_KEY = "account_id"
ACCOUNT_EMAIL_KEY = "account_email"


def get_account_id(request: Request) -> int | None:
    value = request.session.get(ACCOUNT_ID_KEY)
    return int(value) if value else None


def is_authenticated(request: Request) -> bool:
    if get_account_id(request):
        return True
    return request.session.get(SESSION_KEY) is True


def verify_password(password: str) -> bool:
    settings = get_settings()
    if not settings.auth_password:
        return False
    return secrets.compare_digest(password, settings.auth_password)


def login_user(request: Request, *, account_id: int | None = None, email: str | None = None) -> None:
    request.session.clear()
    if account_id:
        request.session[ACCOUNT_ID_KEY] = account_id
        if email:
            request.session[ACCOUNT_EMAIL_KEY] = email
    else:
        request.session[SESSION_KEY] = True


def logout_user(request: Request) -> None:
    request.session.clear()


def redirect_if_unauthenticated(request: Request) -> RedirectResponse | None:
    if is_authenticated(request):
        return None
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(url=f"/login?next={next_path}", status_code=302)


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")