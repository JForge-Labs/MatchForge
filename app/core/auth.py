"""Session-based auth for single-user MatchForge deployments."""
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

SESSION_KEY = "authenticated"


def is_authenticated(request: Request) -> bool:
    return request.session.get(SESSION_KEY) is True


def verify_password(password: str) -> bool:
    settings = get_settings()
    if not settings.auth_password:
        return False
    return secrets.compare_digest(password, settings.auth_password)


def login_user(request: Request) -> None:
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