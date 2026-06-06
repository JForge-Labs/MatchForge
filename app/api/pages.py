"""Public pages: landing and home."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import is_authenticated
from app.core.config import get_settings

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


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