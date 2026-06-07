"""Public pages: landing, home, and shared analysis views."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import is_authenticated
from app.core.db import get_db
from app.services import share_service
from app.utils.templates import render

router = APIRouter(tags=["pages"])


@router.get("/share/{token}", response_class=HTMLResponse)
def shared_analysis(request: Request, token: str, db: Session = Depends(get_db)):
    """Public, token-gated view of a shared analysis (includes referrer signup link)."""
    data = share_service.load_public_share(db, token)
    if not data:
        raise HTTPException(404, "Share link expired or invalid")
    return render(
        request,
        "share.html",
        {"authed": is_authenticated(request), "active": None, **data},
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon_redirect():
    return RedirectResponse(url="/static/favicon.svg", status_code=301)


@router.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return RedirectResponse(url="/static/icons/apple-touch-icon.png", status_code=301)


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return render(
        request,
        "landing.html",
        {"authed": is_authenticated(request), "active": None},
    )