"""Jinja2 templates with automatic UI context injection."""
from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.admin import is_admin
from app.core.auth import get_account_id
from app.utils.nav_context import nav_user
from app.utils.ui_context import ui_context

templates = Jinja2Templates(directory="templates")


def render(
    request: Request,
    name: str,
    context: dict | None = None,
    *,
    db: Session | None = None,
    **kwargs,
):
    """Render a template with shared branding/env context merged in."""
    merged = ui_context(**(context or {}))
    account_id = get_account_id(request)
    if db and account_id:
        merged.update(nav_user(db, account_id))
    merged["is_admin"] = is_admin(request, db)
    return templates.TemplateResponse(request, name, merged, **kwargs)