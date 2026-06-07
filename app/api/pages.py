"""Public pages: landing, home, and shared analysis views."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import is_authenticated
from app.core.db import get_db
from app.services import capacity_service, share_service
from app.utils.templates import render

router = APIRouter(tags=["pages"])


@router.get("/share/{token}", response_class=HTMLResponse)
def shared_analysis(request: Request, token: str, db: Session = Depends(get_db)):
    """Public, token-gated view of a shared analysis (includes referrer signup link)."""
    kind, data = share_service.resolve_share_page(
        db, token, user_agent=request.headers.get("user-agent")
    )
    template = "share.html" if kind == "active" else "share_expired.html"
    return render(
        request,
        template,
        {"authed": is_authenticated(request), "active": None, **data},
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon_redirect():
    return RedirectResponse(url="/static/favicon.svg", status_code=301)


@router.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return RedirectResponse(url="/static/icons/apple-touch-icon.png", status_code=301)


@router.get("/at-capacity", response_class=HTMLResponse)
def at_capacity_page(request: Request):
    detail = capacity_service.capacity_detail()
    return render(
        request,
        "at_capacity.html",
        {
            "authed": is_authenticated(request),
            "headline": detail["headline"],
            "message": detail["message"],
            "retry_after_seconds": detail["retry_after_seconds"],
        },
    )


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return render(
        request,
        "landing.html",
        {"authed": is_authenticated(request), "active": None},
    )