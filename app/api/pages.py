"""Public pages: landing, home, and shared analysis views."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import is_authenticated
from app.core.config import get_settings
from app.core.db import get_db
from app.services import share_service

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/share/{token}", response_class=HTMLResponse)
def shared_analysis(request: Request, token: str, db: Session = Depends(get_db)):
    """Public, token-gated view of a shared analysis (includes referrer signup link)."""
    data = share_service.load_public_share(db, token)
    if not data:
        raise HTTPException(404, "Share link expired or invalid")
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "share.html",
        {
            "authed": is_authenticated(request),
            "app_domain": settings.app_domain,
            "active": None,
            **data,
        },
    )


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "authed": is_authenticated(request),
            "app_domain": settings.app_domain,
            "app_env": settings.app_env,
            "active": None,
        },
    )